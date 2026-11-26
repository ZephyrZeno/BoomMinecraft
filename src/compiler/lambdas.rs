//! Compiler-owned lambda templates. Templates become ordinary MASM functions;
//! no JDK bootstrap, JVM interpreter or Rust function executes guest lambda code.
use super::{
    classfile::{ClassFile, DynamicSite, MethodHandle},
    types,
};
use crate::{
    bytecode::{ClassOrigin, GeneratedOrigin},
    files,
};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};

pub const MARKER: &str = "$$BoomLambda$";
pub const FACTORY: &str = "$capture";
pub const BOOTSTRAP: &str = "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;";
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Ty(pub String);
impl Ty {
    fn reference(&self) -> bool {
        self.0.starts_with(['L', '['])
    }
    fn width(&self) -> usize {
        if self.0 == "V" {
            0
        } else if matches!(self.0.as_str(), "J" | "D") {
            2
        } else {
            1
        }
    }
    fn class_name(&self) -> Result<&str> {
        if self.0.starts_with('[') {
            Ok(&self.0)
        } else {
            self.0
                .strip_prefix('L')
                .and_then(|s| s.strip_suffix(';'))
                .context("Expected reference descriptor")
        }
    }
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Sig {
    pub arguments: Vec<Ty>,
    pub result: Ty,
}
impl Sig {
    pub fn parse(s: &str) -> Result<Self> {
        fn ty(s: &str, p: &mut usize, void: bool) -> Result<Ty> {
            let start = *p;
            let mut dimensions = 0;
            while s.as_bytes().get(*p) == Some(&b'[') {
                *p += 1;
                dimensions += 1;
                ensure!(
                    dimensions <= 255,
                    "Array descriptor nesting exceeds Java limit"
                );
            }
            match s
                .as_bytes()
                .get(*p)
                .copied()
                .context("Truncated lambda descriptor")?
            {
                b'Z' | b'B' | b'C' | b'S' | b'I' | b'J' | b'F' | b'D' => *p += 1,
                b'V' if void && dimensions == 0 => *p += 1,
                b'L' => {
                    *p += 1;
                    let end = s[*p..]
                        .find(';')
                        .context("Unterminated reference descriptor")?
                        + *p;
                    ensure!(
                        end > *p && !s[*p..end].contains(['.', '[', '\0']),
                        "Invalid lambda reference name"
                    );
                    *p = end + 1;
                }
                _ => bail!("Invalid lambda descriptor type"),
            }
            Ok(Ty(s[start..*p].into()))
        }
        ensure!(s.starts_with('('), "Invalid lambda method descriptor");
        let mut p = 1;
        let mut arguments = Vec::new();
        while s.as_bytes().get(p) != Some(&b')') {
            arguments.push(ty(s, &mut p, false)?);
            ensure!(arguments.len() <= 16, "Lambda exceeds 16 argument values");
        }
        p += 1;
        let result = ty(s, &mut p, true)?;
        ensure!(p == s.len(), "Trailing lambda descriptor data");
        Ok(Self { arguments, result })
    }
}
fn wrapper(t: &Ty) -> Option<&'static str> {
    Some(match t.0.as_str() {
        "Z" => "java/lang/Boolean",
        "B" => "java/lang/Byte",
        "C" => "java/lang/Character",
        "S" => "java/lang/Short",
        "I" => "java/lang/Integer",
        "J" => "java/lang/Long",
        "F" => "java/lang/Float",
        "D" => "java/lang/Double",
        _ => return None,
    })
}
fn unwrapped(t: &Ty) -> Option<Ty> {
    for p in ["Z", "B", "C", "S", "I", "J", "F", "D"] {
        let v = Ty(p.into());
        if t.0 == format!("L{};", wrapper(&v).unwrap()) {
            return Some(v);
        }
    }
    None
}
fn accessor(t: &Ty) -> Result<&'static str> {
    Ok(match t.0.as_str() {
        "Z" => "booleanValue",
        "B" => "byteValue",
        "C" => "charValue",
        "S" => "shortValue",
        "I" => "intValue",
        "J" => "longValue",
        "F" => "floatValue",
        "D" => "doubleValue",
        _ => bail!("Not an unboxable primitive"),
    })
}
fn widening(from: &Ty, to: &Ty) -> bool {
    from == to
        || match from.0.as_str() {
            "B" => matches!(to.0.as_str(), "S" | "I" | "J" | "F" | "D"),
            "S" | "C" => matches!(to.0.as_str(), "I" | "J" | "F" | "D"),
            "I" => matches!(to.0.as_str(), "J" | "F" | "D"),
            "J" => matches!(to.0.as_str(), "F" | "D"),
            "F" => to.0 == "D",
            _ => false,
        }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub site: u16,
    pub host: String,
    pub class_name: String,
    pub factory_descriptor: String,
    pub interface: String,
    pub method: String,
    pub sam_descriptor: String,
    pub dynamic_descriptor: String,
    pub implementation: MethodHandle,
}
impl Plan {
    pub fn parse(class: &ClassFile, index: u16) -> Result<Self> {
        let site = class.dynamic_site(index)?;
        Self::from_site(class, index, &site)
    }
    fn from_site(class: &ClassFile, index: u16, site: &DynamicSite) -> Result<Self> {
        ensure!(
            site.bootstrap.owner == "java/lang/invoke/LambdaMetafactory"
                && site.bootstrap.name == "metafactory"
                && site.bootstrap.reference_kind == 6
                && !site.bootstrap.interface
                && site.bootstrap.descriptor == BOOTSTRAP
                && site.arguments.len() == 3,
            "Lambda requires the exact standard metafactory protocol; alternate flags/bridges/serialization are not implemented"
        );
        let factory = Sig::parse(&site.descriptor)?;
        ensure!(
            factory.result.0.starts_with('L') && factory.arguments.len() <= 15,
            "Lambda factory must return an interface and fit receiver ABI"
        );
        let sam_descriptor = class.method_type(site.arguments[0])?;
        let dynamic_descriptor = class.method_type(site.arguments[2])?;
        let sam = Sig::parse(&sam_descriptor)?;
        let dynamic = Sig::parse(&dynamic_descriptor)?;
        let implementation = class.method_handle(site.arguments[1])?;
        ensure!(
            (5..=9).contains(&implementation.reference_kind),
            "Lambda implementation must be a direct method/constructor handle"
        );
        let effective = effective(&implementation)?;
        ensure!(
            sam.arguments.len() == dynamic.arguments.len()
                && factory.arguments.len() + sam.arguments.len() == effective.arguments.len(),
            "Lambda capture/SAM/implementation arity mismatch"
        );
        ensure!(
            !site.name.starts_with('<') && !site.name.contains(['.', ';', '[', '/']),
            "Invalid lambda SAM name"
        );
        Ok(Self {
            site: index,
            host: class.name.clone(),
            class_name: format!("{}{MARKER}{index:04x}", class.name),
            factory_descriptor: site.descriptor.clone(),
            interface: factory.result.class_name()?.into(),
            method: site.name.clone(),
            sam_descriptor,
            dynamic_descriptor,
            implementation,
        })
    }
    pub fn validate(&self, registry: &mut types::Registry<'_>, loader: &str) -> Result<()> {
        fn assign(r: &mut types::Registry<'_>, l: &str, a: &Ty, b: &Ty) -> Result<bool> {
            let a = r.field(l, &a.0)?;
            let b = r.field(l, &b.0)?;
            Ok(r.assignable(a, b))
        }
        fn adapt(r: &mut types::Registry<'_>, l: &str, a: &Ty, b: &Ty, ret: bool) -> Result<bool> {
            if b.0 == "V" {
                return Ok(ret);
            }
            if a.reference() && b.reference() {
                return Ok(ret || assign(r, l, a, b)?);
            }
            if !a.reference() && !b.reference() {
                return Ok(widening(a, b));
            }
            if !a.reference() {
                return match wrapper(a) {
                    Some(w) => assign(r, l, &Ty(format!("L{w};")), b),
                    None => Ok(false),
                };
            }
            if let Some(p) = unwrapped(a) {
                return Ok(widening(&p, b));
            }
            Ok(ret) // return-only casts from Object/Number are checked by the generated adapter
        }
        let bootstrap = registry.class("bootstrap", "java/lang/invoke/LambdaMetafactory")?;
        let types::Type::Class { key, origin, .. } = &registry.types[bootstrap] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "Lambda bootstrap is not the pinned JDK metafactory"
        );
        let member = registry
            .definition(bootstrap)
            .unwrap()
            .method("metafactory", Some(BOOTSTRAP))?;
        ensure!(
            member.access & (1 | 8 | 0x100 | 0x400) == 9 && member.code.is_some(),
            "Metafactory member contract changed"
        );
        let interface = registry.class(loader, &self.interface)?;
        ensure!(
            matches!(&registry.types[interface],types::Type::Class{access,..} if access&0x200!=0),
            "Lambda factory return is not an interface"
        );
        let f = Sig::parse(&self.factory_descriptor)?;
        let sam = Sig::parse(&self.sam_descriptor)?;
        let dynamic = Sig::parse(&self.dynamic_descriptor)?;
        let target = effective(&self.implementation)?;
        for (i, (a, b)) in f.arguments.iter().zip(&target.arguments).enumerate() {
            ensure!(
                a == b
                    || (i == 0
                        && self.implementation.reference_kind != 6
                        && self.implementation.reference_kind != 8
                        && a.reference()
                        && b.reference()
                        && assign(registry, loader, a, b)?),
                "Lambda captured type mismatch"
            );
        }
        for (u, t) in sam.arguments.iter().zip(&dynamic.arguments) {
            ensure!(
                u == t || (u.reference() && t.reference() && assign(registry, loader, t, u)?),
                "Lambda instantiated argument is not a SAM subtype"
            );
        }
        ensure!(
            sam.result == dynamic.result
                || (sam.result.reference()
                    && dynamic.result.reference()
                    && assign(registry, loader, &dynamic.result, &sam.result)?),
            "Lambda instantiated return is not a SAM subtype"
        );
        for (a, b) in dynamic
            .arguments
            .iter()
            .zip(&target.arguments[f.arguments.len()..])
        {
            ensure!(
                adapt(registry, loader, a, b, false)?,
                "Lambda argument cannot adapt to implementation"
            );
        }
        ensure!(
            adapt(registry, loader, &target.result, &dynamic.result, true)?,
            "Lambda implementation result cannot adapt to SAM"
        );
        Ok(())
    }
    pub fn definition(&self, origin: &ClassOrigin) -> Result<(Vec<u8>, ClassOrigin)> {
        let bytes = generate(self)?;
        let generated = GeneratedOrigin {
            generator: "boom-lambda".into(),
            abi: 1,
            host_loader: origin.loader.clone(),
            host_class: self.host.clone(),
            host_source_id: origin.source_id.clone(),
            host_sha256: origin.sha256.clone(),
            site: self.site,
        };
        Ok((
            bytes.clone(),
            ClassOrigin {
                loader: origin.loader.clone(),
                binary_name: self.class_name.replace('/', "."),
                source_id: "boom:lambda-v1".into(),
                jar_entry: format!("<generated>/{}.class", self.class_name),
                java_class_major: 65,
                sha256: files::digest_bytes(&bytes).sha256,
                generated: Some(Box::new(generated)),
            },
        ))
    }
}
fn effective(handle: &MethodHandle) -> Result<Sig> {
    let mut s = Sig::parse(&handle.descriptor)?;
    if matches!(handle.reference_kind, 5 | 7 | 9) {
        s.arguments.insert(0, Ty(format!("L{};", handle.owner)));
    }
    if handle.reference_kind == 8 {
        ensure!(
            s.result.0 == "V" && !handle.interface,
            "Invalid lambda constructor handle"
        );
        s.result = Ty(format!("L{};", handle.owner));
    }
    ensure!(
        s.arguments.len() <= 16,
        "Lambda implementation exceeds value ABI"
    );
    Ok(s)
}

pub struct Provider<P> {
    pub base: P,
}
impl<P: types::TypeProvider> types::TypeProvider for Provider<P> {
    fn name_in_use(&self, name: &str) -> Result<bool> {
        self.base.name_in_use(name)
    }
    fn resolve(&self, loader: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
        if let Some(result) = super::records::resolve(&self.base, loader, name)? {
            return Ok(result);
        }
        if let Some(result) = super::jdk_bridges::resolve(&self.base, loader, name)? {
            return Ok(result);
        }
        if let Some((host, site)) = name.rsplit_once(MARKER)
            && !self.base.name_in_use(name)?
        {
            ensure!(
                !host.contains(MARKER) && site.len() == 4,
                "Invalid compiler lambda identity"
            );
            let site = u16::from_str_radix(site, 16)?;
            let (bytes, origin) = self.base.resolve(loader, host)?;
            ensure!(
                origin.generated.is_none(),
                "Lambda creator must be a verified original class"
            );
            let class = ClassFile::parse(&bytes)?;
            ensure!(
                class.name == host
                    && origin.binary_name == host.replace('/', ".")
                    && origin.sha256 == files::digest_bytes(&bytes).sha256,
                "Lambda creator bytes/name disagree with source proof"
            );
            let plan = Plan::parse(&class, site)?;
            ensure!(
                plan.class_name == name,
                "Noncanonical compiler lambda identity"
            );
            return plan.definition(&origin);
        }
        self.base.resolve(loader, name)
    }
}

#[derive(Default)]
struct Pool(Vec<Vec<u8>>);
impl Pool {
    fn push(&mut self, v: Vec<u8>) -> Result<u16> {
        ensure!(self.0.len() < 65534, "Lambda constant pool overflow");
        self.0.push(v);
        Ok(self.0.len() as u16)
    }
    fn utf(&mut self, s: &str) -> Result<u16> {
        ensure!(
            s.is_ascii() && !s.contains('\0') && s.len() < 65536,
            "Lambda template requires supported class/member identifiers"
        );
        let mut b = vec![1];
        b.extend((s.len() as u16).to_be_bytes());
        b.extend(s.as_bytes());
        self.push(b)
    }
    fn class(&mut self, s: &str) -> Result<u16> {
        let i = self.utf(s)?;
        let mut b = vec![7];
        b.extend(i.to_be_bytes());
        self.push(b)
    }
    fn member(&mut self, tag: u8, owner: &str, name: &str, desc: &str) -> Result<u16> {
        let owner = self.class(owner)?;
        let name = self.utf(name)?;
        let desc = self.utf(desc)?;
        let mut nt = vec![12];
        nt.extend(name.to_be_bytes());
        nt.extend(desc.to_be_bytes());
        let nt = self.push(nt)?;
        let mut b = vec![tag];
        b.extend(owner.to_be_bytes());
        b.extend(nt.to_be_bytes());
        self.push(b)
    }
}
fn reference(code: &mut Vec<u8>, op: u8, index: u16) {
    code.push(op);
    code.extend(index.to_be_bytes());
}
fn load(code: &mut Vec<u8>, ty: &Ty, local: usize) {
    code.extend([
        if ty.reference() {
            0x19
        } else {
            match ty.0.as_str() {
                "J" => 0x16,
                "F" => 0x17,
                "D" => 0x18,
                _ => 0x15,
            }
        },
        local as u8,
    ]);
}
fn cast(code: &mut Vec<u8>, p: &mut Pool, target: &Ty) -> Result<()> {
    if target.0 != "Ljava/lang/Object;" {
        reference(code, 0xc0, p.class(target.class_name()?)?);
    }
    Ok(())
}
fn adapt(code: &mut Vec<u8>, p: &mut Pool, from: &Ty, to: &Ty, ret: bool) -> Result<()> {
    if from == to {
        return Ok(());
    }
    if to.0 == "V" {
        if from.0 != "V" {
            code.push(if from.width() == 2 { 0x58 } else { 0x57 });
        }
        return Ok(());
    }
    if from.reference() && to.reference() {
        return cast(code, p, to);
    }
    if !from.reference() && !to.reference() {
        ensure!(
            widening(from, to),
            "Lambda primitive narrowing is forbidden"
        );
        let op = match (from.0.as_str(), to.0.as_str()) {
            ("B" | "S" | "C" | "I", "J") => Some(0x85),
            ("B" | "S" | "C" | "I", "F") => Some(0x86),
            ("B" | "S" | "C" | "I", "D") => Some(0x87),
            ("J", "F") => Some(0x89),
            ("J", "D") => Some(0x8a),
            ("F", "D") => Some(0x8d),
            _ => None,
        };
        if let Some(op) = op {
            code.push(op)
        }
        return Ok(());
    }
    if !from.reference() {
        let owner = wrapper(from).context("Cannot box void")?;
        reference(
            code,
            0xb8,
            p.member(10, owner, "valueOf", &format!("({})L{owner};", from.0))?,
        );
        return Ok(());
    }
    let (owner, primitive) = if let Some(primitive) = unwrapped(from) {
        (wrapper(&primitive).unwrap().to_string(), primitive)
    } else {
        ensure!(ret, "Non-wrapper lambda parameter cannot unbox");
        (
            if matches!(to.0.as_str(), "Z" | "C") {
                wrapper(to).unwrap()
            } else {
                "java/lang/Number"
            }
            .into(),
            to.clone(),
        )
    };
    cast(code, p, &Ty(format!("L{owner};")))?;
    reference(
        code,
        0xb6,
        p.member(
            10,
            &owner,
            accessor(&primitive)?,
            &format!("(){}", primitive.0),
        )?,
    );
    adapt(code, p, &primitive, to, ret)
}
fn generate(plan: &Plan) -> Result<Vec<u8>> {
    let f = Sig::parse(&plan.factory_descriptor)?;
    let sam = Sig::parse(&plan.sam_descriptor)?;
    let dynamic = Sig::parse(&plan.dynamic_descriptor)?;
    let target = effective(&plan.implementation)?;
    let mut p = Pool::default();
    let this = p.class(&plan.class_name)?;
    let parent = p.class("java/lang/Object")?;
    let interface = p.class(&plan.interface)?;
    let code_name = p.utf("Code")?;
    let mut fields = Vec::new();
    let mut field_refs = Vec::new();
    for (i, t) in f.arguments.iter().enumerate() {
        let n = format!("c{i}");
        fields.push((0x1012u16, p.utf(&n)?, p.utf(&t.0)?));
        field_refs.push(p.member(9, &plan.class_name, &n, &t.0)?);
    }
    let ctor_desc = format!(
        "({})V",
        f.arguments.iter().map(|t| t.0.as_str()).collect::<String>()
    );
    let mut ctor = vec![0x2a];
    reference(
        &mut ctor,
        0xb7,
        p.member(10, "java/lang/Object", "<init>", "()V")?,
    );
    let mut local = 1;
    for (i, t) in f.arguments.iter().enumerate() {
        ctor.push(0x2a);
        load(&mut ctor, t, local);
        local += t.width();
        reference(&mut ctor, 0xb5, field_refs[i]);
    }
    ctor.push(0xb1);
    let mut factory = Vec::new();
    if matches!(plan.implementation.reference_kind, 5 | 7 | 9) && !f.arguments.is_empty() {
        load(&mut factory, &f.arguments[0], 0);
        reference(
            &mut factory,
            0xb8,
            p.member(
                10,
                "java/util/Objects",
                "requireNonNull",
                "(Ljava/lang/Object;)Ljava/lang/Object;",
            )?,
        );
        factory.push(0x57);
    }
    reference(&mut factory, 0xbb, this);
    factory.push(0x59);
    let mut at = 0;
    for t in &f.arguments {
        load(&mut factory, t, at);
        at += t.width();
    }
    reference(
        &mut factory,
        0xb7,
        p.member(10, &plan.class_name, "<init>", &ctor_desc)?,
    );
    factory.push(0xb0);
    // The metafactory contract permits reusing an instance. With no captures,
    // ordinary class initialization publishes one rooted object per call site.
    // Both synchronization and the resulting allocation/read paths become MASM.
    let singleton_init = if f.arguments.is_empty() {
        let descriptor = format!("L{};", plan.class_name);
        fields.push((0x101a, p.utf("$instance")?, p.utf(&descriptor)?));
        let field = p.member(9, &plan.class_name, "$instance", &descriptor)?;
        let mut init = factory;
        init.pop(); // replace areturn with putstatic + return
        reference(&mut init, 0xb3, field);
        init.push(0xb1);
        factory = Vec::new();
        reference(&mut factory, 0xb2, field);
        factory.push(0xb0);
        Some(init)
    } else {
        None
    };
    let h = &plan.implementation;
    let mut body = Vec::new();
    if h.reference_kind == 8 {
        reference(&mut body, 0xbb, p.class(&h.owner)?);
        body.push(0x59);
    }
    for field in &field_refs {
        body.push(0x2a);
        reference(&mut body, 0xb4, *field);
    }
    let mut at = 1;
    for (i, (u, t)) in sam.arguments.iter().zip(&dynamic.arguments).enumerate() {
        load(&mut body, u, at);
        at += u.width();
        adapt(&mut body, &mut p, u, t, false)?;
        adapt(
            &mut body,
            &mut p,
            t,
            &target.arguments[f.arguments.len() + i],
            false,
        )?;
    }
    let opcode = match h.reference_kind {
        5 => 0xb6,
        6 => 0xb8,
        7 | 8 => 0xb7,
        9 => 0xb9,
        _ => unreachable!(),
    };
    reference(
        &mut body,
        opcode,
        p.member(
            if h.interface { 11 } else { 10 },
            &h.owner,
            &h.name,
            &h.descriptor,
        )?,
    );
    if opcode == 0xb9 {
        body.extend([
            (Sig::parse(&h.descriptor)?
                .arguments
                .iter()
                .map(Ty::width)
                .sum::<usize>()
                + 1) as u8,
            0,
        ]);
    }
    adapt(&mut body, &mut p, &target.result, &dynamic.result, true)?;
    adapt(&mut body, &mut p, &dynamic.result, &sam.result, true)?;
    body.push(if sam.result.reference() {
        0xb0
    } else {
        match sam.result.0.as_str() {
            "V" => 0xb1,
            "J" => 0xad,
            "F" => 0xae,
            "D" => 0xaf,
            _ => 0xac,
        }
    });
    let mut methods = vec![
        (0x1002, p.utf("<init>")?, p.utf(&ctor_desc)?, local, ctor),
        (
            0x1009,
            p.utf(FACTORY)?,
            p.utf(&plan.factory_descriptor)?,
            f.arguments.iter().map(Ty::width).sum(),
            factory,
        ),
        (
            0x1011,
            p.utf(&plan.method)?,
            p.utf(&plan.sam_descriptor)?,
            at,
            body,
        ),
    ];
    if let Some(init) = singleton_init {
        methods.push((0x1008, p.utf("<clinit>")?, p.utf("()V")?, 0, init));
    }
    let mut bytes = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65];
    bytes.extend(((p.0.len() + 1) as u16).to_be_bytes());
    for item in p.0 {
        bytes.extend(item)
    }
    for v in [0x1030u16, this, parent, 1, interface, fields.len() as u16] {
        bytes.extend(v.to_be_bytes());
    }
    for (access, name, desc) in fields {
        for v in [access, name, desc, 0] {
            bytes.extend(v.to_be_bytes());
        }
    }
    bytes.extend((methods.len() as u16).to_be_bytes());
    for (access, name, desc, locals, code) in methods {
        for v in [access as u16, name, desc, 1, code_name] {
            bytes.extend(v.to_be_bytes());
        }
        bytes.extend(((code.len() + 12) as u32).to_be_bytes());
        for v in [64u16, locals as u16] {
            bytes.extend(v.to_be_bytes());
        }
        bytes.extend((code.len() as u32).to_be_bytes());
        bytes.extend(code);
        bytes.extend([0, 0, 0, 0]);
    }
    bytes.extend([0, 0]);
    Ok(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture(sam: &str, dynamic: &str, target: &str) -> (ClassFile, DynamicSite) {
        let mut pool = Pool::default();
        let this = pool.class("p/Creator").unwrap();
        let parent = pool.class("java/lang/Object").unwrap();
        let mut method_type = |s: &str| {
            let utf = pool.utf(s).unwrap();
            let mut b = vec![16];
            b.extend(utf.to_be_bytes());
            pool.push(b).unwrap()
        };
        let sam = method_type(sam);
        let dynamic = method_type(dynamic);
        let target = pool.member(10, "p/Creator", "body", target).unwrap();
        let mut handle = vec![15, 6];
        handle.extend(target.to_be_bytes());
        let target = pool.push(handle).unwrap();
        let mut bytes = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65];
        bytes.extend(((pool.0.len() + 1) as u16).to_be_bytes());
        for b in pool.0 {
            bytes.extend(b);
        }
        for n in [0x21u16, this, parent, 0, 0, 0, 0] {
            bytes.extend(n.to_be_bytes());
        }
        let class = ClassFile::parse(&bytes).unwrap();
        let site = DynamicSite {
            name: "applyAsInt".into(),
            descriptor: "(JLjava/lang/String;)Ljava/util/function/IntUnaryOperator;".into(),
            bootstrap: MethodHandle {
                reference_kind: 6,
                owner: "java/lang/invoke/LambdaMetafactory".into(),
                name: "metafactory".into(),
                descriptor: BOOTSTRAP.into(),
                interface: false,
            },
            arguments: vec![sam, target, dynamic],
        };
        (class, site)
    }
    fn origin(name: &str, bytes: &[u8]) -> ClassOrigin {
        ClassOrigin {
            loader: "explicit-application".into(),
            binary_name: name.replace('/', "."),
            source_id: "explicit:fixture".into(),
            jar_entry: format!("{name}.class"),
            java_class_major: 65,
            sha256: files::digest_bytes(bytes).sha256,
            generated: None,
        }
    }
    #[test]
    fn protocol_and_capture_arity_are_checked_before_generation() {
        let (class, mut site) = fixture("(I)I", "(I)I", "(JLjava/lang/String;I)I");
        let plan = Plan::from_site(&class, 37, &site).unwrap();
        assert_eq!(plan.class_name, "p/Creator$$BoomLambda$0025");
        site.bootstrap.name = "altMetafactory".into();
        assert!(Plan::from_site(&class, 37, &site).is_err());
        site.bootstrap.name = "metafactory".into();
        site.bootstrap.descriptor = "()V".into();
        assert!(Plan::from_site(&class, 37, &site).is_err());
        site.bootstrap.descriptor = BOOTSTRAP.into();
        site.bootstrap.reference_kind = 5;
        assert!(Plan::from_site(&class, 37, &site).is_err());
        site.bootstrap.reference_kind = 6;
        site.descriptor = "(J)Ljava/util/function/IntUnaryOperator;".into();
        assert!(Plan::from_site(&class, 37, &site).is_err());
        site.descriptor = plan.factory_descriptor;
        site.arguments.pop();
        assert!(Plan::from_site(&class, 37, &site).is_err());
    }
    #[test]
    fn capture_templates_are_deterministic_with_separate_creator_provenance() {
        let (class, site) = fixture("(I)I", "(I)I", "(JLjava/lang/String;I)I");
        let plan = Plan::from_site(&class, 37, &site).unwrap();
        let first = origin("p/Creator", b"first creator");
        let (a, proof_a) = plan.definition(&first).unwrap();
        let (b, proof_b) = plan
            .definition(&origin("p/Creator", b"changed creator"))
            .unwrap();
        assert_eq!(a, b);
        assert_ne!(proof_a, proof_b);
        assert_eq!(
            proof_a.generated.as_ref().unwrap().host_sha256,
            first.sha256
        );
        assert_eq!(proof_a.sha256, files::digest_bytes(&a).sha256);
        let generated = ClassFile::parse(&a).unwrap();
        assert_eq!(
            generated.interface_names,
            vec!["java/util/function/IntUnaryOperator"]
        );
        assert_eq!(
            generated
                .field_info
                .iter()
                .map(|f| f.descriptor.as_str())
                .collect::<Vec<_>>(),
            vec!["J", "Ljava/lang/String;"]
        );
        assert!(generated.field_info.iter().all(|f| f.access & 0x12 == 0x12));
        assert_eq!(generated.methods.len(), 3);
        assert_eq!(
            generated
                .method(FACTORY, Some(&plan.factory_descriptor))
                .unwrap()
                .code
                .as_ref()
                .unwrap()
                .max_locals,
            3
        );
        assert!(generated.method("applyAsInt", Some("(I)I")).is_ok());
    }
    #[test]
    fn malformed_descriptors_and_primitive_narrowing_are_rejected() {
        for s in [
            "",
            "(",
            "(V)I",
            "([V)V",
            "(L;)V",
            "(Ljava.lang.String;)V",
            "()VV",
            "(I)",
            "(IIIIIIIIIIIIIIIII)V",
        ] {
            assert!(Sig::parse(s).is_err(), "{s}");
        }
        assert!(Sig::parse("(J[ILjava/lang/Object;)D").is_ok());
        assert!(!widening(&Ty("D".into()), &Ty("I".into())));
        assert!(!widening(&Ty("Z".into()), &Ty("I".into())));
        assert!(widening(&Ty("C".into()), &Ty("D".into())));
        assert!(
            adapt(
                &mut Vec::new(),
                &mut Pool::default(),
                &Ty("V".into()),
                &Ty("Ljava/lang/Object;".into()),
                true
            )
            .is_err()
        );
    }
    #[test]
    fn stateless_template_has_one_final_root_and_a_read_only_capture_factory() {
        let (class, mut site) = fixture("(I)I", "(I)I", "(I)I");
        site.descriptor = "()Ljava/util/function/IntUnaryOperator;".into();
        let plan = Plan::from_site(&class, 37, &site).unwrap();
        let (bytes, _) = plan.definition(&origin("p/Creator", b"creator")).unwrap();
        let generated = ClassFile::parse(&bytes).unwrap();
        assert_eq!(generated.field_info.len(), 1);
        assert_eq!(generated.field_info[0].access, 0x101a);
        assert_eq!(
            generated.field_info[0].descriptor,
            format!("L{};", plan.class_name)
        );
        let factory = generated
            .method(FACTORY, Some(&plan.factory_descriptor))
            .unwrap()
            .code
            .as_ref()
            .unwrap();
        assert_eq!(factory.bytes.len(), 4);
        assert_eq!(factory.bytes[0], 0xb2);
        assert_eq!(factory.bytes[3], 0xb0);
        let init = generated
            .method("<clinit>", Some("()V"))
            .unwrap()
            .code
            .as_ref()
            .unwrap();
        assert_eq!(init.bytes[0], 0xbb);
        assert_eq!(init.bytes[init.bytes.len() - 4], 0xb3);
        assert_eq!(init.bytes[init.bytes.len() - 1], 0xb1);
    }
    #[test]
    fn existing_prefix_names_are_resolved_as_original_inputs() {
        struct Occupied;
        impl types::TypeProvider for Occupied {
            fn name_in_use(&self, _: &str) -> Result<bool> {
                Ok(true)
            }
            fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
                Ok((b"original".to_vec(), origin(name, b"original")))
            }
        }
        use types::TypeProvider;
        let (bytes, proof) = Provider { base: Occupied }
            .resolve("explicit-application", "p/Creator$$BoomLambda$0025")
            .unwrap();
        assert_eq!(bytes, b"original");
        assert!(proof.generated.is_none());
    }
}
