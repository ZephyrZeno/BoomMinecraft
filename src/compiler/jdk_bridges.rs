//! Original JDK Java methods, retained as Java bytecode and
//! compiled normally under a compiler-owned holder. No guest interpreter.
use super::{classfile::ClassFile, types};
use crate::{
    bytecode::{ClassOrigin, GeneratedOrigin},
    files,
};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
pub const MARKER: &str = "$$BoomJdk$";
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Kind {
    CheckIndex,
    CheckOffset,
    CheckOffCount,
    CheckBeginEnd,
    ValueOfObject,
    ClassToString,
    ClassDescriptorString,
    ClassComponentType,
    Format,
    FormatLocale,
    StartsWith,
    EndsWith,
    Contains,
    ClassGetClassLoader,
    ClassGetClassLoader0,
    ClassAsSubclass,
    Split,
    SplitLimit,
    SplitWithDelimiters,
    ClassForName,
    ClassForNameLoader,
    ClassForNameCaller,
    ClassForNameChecked,
    ReplaceFirst,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub kind: Kind,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub target: ClassOrigin,
}
impl Kind {
    pub(super) fn id(self) -> u16 {
        match self {
            Self::CheckIndex => 1,
            Self::CheckOffset => 2,
            Self::CheckOffCount => 3,
            Self::CheckBeginEnd => 4,
            Self::ValueOfObject => 5,
            Self::ClassToString => 6,
            Self::ClassDescriptorString => 7,
            Self::ClassComponentType => 8,
            Self::Format => 9,
            Self::FormatLocale => 10,
            Self::StartsWith => 11,
            Self::EndsWith => 12,
            Self::Contains => 13,
            Self::ClassGetClassLoader => 14,
            Self::ClassGetClassLoader0 => 15,
            Self::ClassAsSubclass => 16,
            Self::Split => 17,
            Self::SplitLimit => 18,
            Self::SplitWithDelimiters => 19,
            Self::ClassForName => 20,
            Self::ClassForNameLoader => 21,
            Self::ClassForNameCaller => 22,
            Self::ClassForNameChecked => 23,
            Self::ReplaceFirst => 24,
        }
    }
    fn from_id(id: u16) -> Result<Self> {
        Ok(match id {
            1 => Self::CheckIndex,
            2 => Self::CheckOffset,
            3 => Self::CheckOffCount,
            4 => Self::CheckBeginEnd,
            5 => Self::ValueOfObject,
            6 => Self::ClassToString,
            7 => Self::ClassDescriptorString,
            8 => Self::ClassComponentType,
            9 => Self::Format,
            10 => Self::FormatLocale,
            11 => Self::StartsWith,
            12 => Self::EndsWith,
            13 => Self::Contains,
            14 => Self::ClassGetClassLoader,
            15 => Self::ClassGetClassLoader0,
            16 => Self::ClassAsSubclass,
            17 => Self::Split,
            18 => Self::SplitLimit,
            19 => Self::SplitWithDelimiters,
            20 => Self::ClassForName,
            21 => Self::ClassForNameLoader,
            22 => Self::ClassForNameCaller,
            23 => Self::ClassForNameChecked,
            24 => Self::ReplaceFirst,
            _ => bail!("Unknown JDK bridge identity"),
        })
    }
    pub(super) fn owner(self) -> &'static str {
        if matches!(
            self,
            Self::ClassToString
                | Self::ClassDescriptorString
                | Self::ClassComponentType
                | Self::ClassGetClassLoader
                | Self::ClassGetClassLoader0
                | Self::ClassAsSubclass
                | Self::ClassForName
                | Self::ClassForNameLoader
                | Self::ClassForNameCaller
                | Self::ClassForNameChecked
        ) {
            "java/lang/Class"
        } else {
            "java/lang/String"
        }
    }
    pub(super) fn name(self) -> &'static str {
        match self {
            Self::CheckIndex => "checkIndex",
            Self::CheckOffset => "checkOffset",
            Self::CheckOffCount => "checkBoundsOffCount",
            Self::CheckBeginEnd => "checkBoundsBeginEnd",
            Self::ValueOfObject => "valueOf",
            Self::ClassToString => "toString",
            Self::ClassDescriptorString => "descriptorString",
            Self::ClassComponentType => "componentType",
            Self::Format | Self::FormatLocale => "format",
            Self::StartsWith => "startsWith",
            Self::EndsWith => "endsWith",
            Self::Contains => "contains",
            Self::ReplaceFirst => "replaceFirst",
            Self::ClassGetClassLoader => "getClassLoader",
            Self::ClassGetClassLoader0 => "getClassLoader0",
            Self::ClassAsSubclass => "asSubclass",
            Self::Split | Self::SplitLimit => "split",
            Self::SplitWithDelimiters => "splitWithDelimiters",
            Self::ClassForName
            | Self::ClassForNameLoader
            | Self::ClassForNameCaller
            | Self::ClassForNameChecked => "forName",
        }
    }
    pub(super) fn original_descriptor(self) -> &'static str {
        match self {
            Self::CheckIndex | Self::CheckOffset => "(II)V",
            Self::CheckOffCount => "(III)I",
            Self::CheckBeginEnd => "(III)V",
            Self::ValueOfObject => "(Ljava/lang/Object;)Ljava/lang/String;",
            Self::ClassToString | Self::ClassDescriptorString => "()Ljava/lang/String;",
            Self::ClassComponentType => "()Ljava/lang/Class;",
            Self::Format => "(Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/String;",
            Self::FormatLocale => {
                "(Ljava/util/Locale;Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/String;"
            }
            Self::StartsWith | Self::EndsWith => "(Ljava/lang/String;)Z",
            Self::Contains => "(Ljava/lang/CharSequence;)Z",
            Self::ReplaceFirst => "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;",
            Self::ClassGetClassLoader | Self::ClassGetClassLoader0 => "()Ljava/lang/ClassLoader;",
            Self::ClassAsSubclass => "(Ljava/lang/Class;)Ljava/lang/Class;",
            Self::ClassForName => "(Ljava/lang/String;)Ljava/lang/Class;",
            Self::ClassForNameLoader => {
                "(Ljava/lang/String;ZLjava/lang/ClassLoader;)Ljava/lang/Class;"
            }
            Self::ClassForNameCaller => "(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Class;",
            Self::ClassForNameChecked => {
                "(Ljava/lang/String;ZLjava/lang/ClassLoader;Ljava/lang/Class;)Ljava/lang/Class;"
            }
            Self::Split => "(Ljava/lang/String;)[Ljava/lang/String;",
            Self::SplitLimit | Self::SplitWithDelimiters => {
                "(Ljava/lang/String;I)[Ljava/lang/String;"
            }
        }
    }
    pub(super) fn descriptor(self) -> &'static str {
        if self == Self::ReplaceFirst {
            "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;"
        } else if self == Self::Split {
            "(Ljava/lang/String;Ljava/lang/String;)[Ljava/lang/String;"
        } else if matches!(self, Self::SplitLimit | Self::SplitWithDelimiters) {
            "(Ljava/lang/String;Ljava/lang/String;I)[Ljava/lang/String;"
        } else if self == Self::ClassAsSubclass {
            "(Ljava/lang/Class;Ljava/lang/Class;)Ljava/lang/Class;"
        } else if matches!(self, Self::ClassGetClassLoader | Self::ClassGetClassLoader0) {
            "(Ljava/lang/Class;)Ljava/lang/ClassLoader;"
        } else if self == Self::Contains {
            "(Ljava/lang/String;Ljava/lang/CharSequence;)Z"
        } else if matches!(self, Self::StartsWith | Self::EndsWith) {
            "(Ljava/lang/String;Ljava/lang/String;)Z"
        } else if self == Self::ClassComponentType {
            "(Ljava/lang/Class;)Ljava/lang/Class;"
        } else if self.instance() {
            "(Ljava/lang/Class;)Ljava/lang/String;"
        } else {
            self.original_descriptor()
        }
    }
    pub(super) fn class_name(self) -> String {
        format!("{}{}{:04x}", self.owner(), MARKER, self.id())
    }
    pub(super) fn instance(self) -> bool {
        matches!(
            self,
            Self::ClassToString
                | Self::ClassDescriptorString
                | Self::ClassComponentType
                | Self::StartsWith
                | Self::EndsWith
                | Self::Contains
                | Self::ReplaceFirst
                | Self::ClassGetClassLoader
                | Self::ClassGetClassLoader0
                | Self::ClassAsSubclass
                | Self::Split
                | Self::SplitLimit
                | Self::SplitWithDelimiters
        )
    }
    pub(super) fn private_api(self) -> bool {
        matches!(self, Self::ClassForNameCaller | Self::ClassForNameChecked)
    }
    pub(super) fn public_api(self) -> bool {
        (self.instance() && self != Self::ClassGetClassLoader0)
            || matches!(
                self,
                Self::ValueOfObject
                    | Self::Format
                    | Self::FormatLocale
                    | Self::ClassForName
                    | Self::ClassForNameLoader
            )
    }
    pub(super) fn resolve(o: &str, n: &str, d: &str, static_call: bool) -> Option<Self> {
        [
            Self::CheckIndex,
            Self::CheckOffset,
            Self::CheckOffCount,
            Self::CheckBeginEnd,
            Self::ValueOfObject,
            Self::ClassToString,
            Self::ClassDescriptorString,
            Self::ClassComponentType,
            Self::Format,
            Self::FormatLocale,
            Self::StartsWith,
            Self::EndsWith,
            Self::Contains,
            Self::ClassGetClassLoader,
            Self::ClassGetClassLoader0,
            Self::ClassAsSubclass,
            Self::Split,
            Self::SplitLimit,
            Self::SplitWithDelimiters,
            Self::ClassForName,
            Self::ClassForNameLoader,
            Self::ClassForNameCaller,
            Self::ClassForNameChecked,
            Self::ReplaceFirst,
        ]
        .into_iter()
        .find(|k| {
            k.owner() == o
                && k.name() == n
                && k.original_descriptor() == d
                && (static_call != k.instance())
        })
    }
}
struct Cursor<'a> {
    b: &'a [u8],
    p: usize,
}
impl<'a> Cursor<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8]> {
        let end = self.p.checked_add(n).context("Bridge offset overflow")?;
        let v = self.b.get(self.p..end).context("Truncated bridge source")?;
        self.p = end;
        Ok(v)
    }
    fn u1(&mut self) -> Result<u8> {
        Ok(self.take(1)?[0])
    }
    fn u2(&mut self) -> Result<u16> {
        Ok(u16::from_be_bytes(self.take(2)?.try_into()?))
    }
    fn u4(&mut self) -> Result<u32> {
        Ok(u32::from_be_bytes(self.take(4)?.try_into()?))
    }
    fn attrs(&mut self) -> Result<Vec<(u16, &'a [u8])>> {
        let n = self.u2()?;
        let mut a = vec![];
        for _ in 0..n {
            let start = self.p;
            let name = self.u2()?;
            let n = self.u4()? as usize;
            self.take(n)?;
            a.push((name, &self.b[start..self.p]));
        }
        Ok(a)
    }
}
fn utf(out: &mut Vec<u8>, s: &str) -> Result<()> {
    out.push(1);
    out.extend(u16::try_from(s.len())?.to_be_bytes());
    out.extend(s.as_bytes());
    Ok(())
}
fn generate(bytes: &[u8], origin: &ClassOrigin, kind: Kind) -> Result<(Vec<u8>, ClassOrigin)> {
    let class = ClassFile::parse(bytes)?;
    ensure!(
        origin.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none()
            && class.name == kind.owner()
            && origin.sha256 == files::digest_bytes(bytes).sha256,
        "JDK bridge requires verified original source"
    );
    let method = class.method(kind.name(), Some(kind.original_descriptor()))?;
    let expected = if kind == Kind::ClassGetClassLoader0 {
        0
    } else if matches!(kind, Kind::Format | Kind::FormatLocale) {
        0x89
    } else if kind.instance() {
        1
    } else if kind.private_api() {
        10
    } else if matches!(
        kind,
        Kind::ValueOfObject | Kind::ClassForName | Kind::ClassForNameLoader
    ) {
        9
    } else {
        8
    };
    ensure!(
        method.access == expected && method.code.is_some(),
        "JDK bridge source access or Code changed"
    );
    // Approval is limited to these exact API bodies; their source hash is retained.
    let mut r = Cursor { b: bytes, p: 8 };
    let cp_count = r.u2()?;
    let mut names = vec![String::new(); cp_count as usize];
    let mut i = 1;
    while i < cp_count {
        match r.u1()? {
            1 => {
                let n = r.u2()? as usize;
                names[i as usize] = String::from_utf8_lossy(r.take(n)?).into_owned();
            }
            3 | 4 => {
                r.take(4)?;
            }
            5 | 6 => {
                r.take(8)?;
                i += 1;
            }
            7 | 8 | 16 | 19 | 20 => {
                r.take(2)?;
            }
            9 | 10 | 11 | 12 | 17 | 18 => {
                r.take(4)?;
            }
            15 => {
                r.take(3)?;
            }
            _ => bail!("Unknown bridge source constant"),
        };
        i += 1;
    }
    let cp_end = r.p;
    r.take(4)?;
    let super_class = r.u2()?;
    let n = r.u2()?;
    r.take(n as usize * 2)?;
    let n = r.u2()?;
    for _ in 0..n {
        r.take(6)?;
        r.attrs()?;
    }
    let n = r.u2()?;
    let mut selected = None;
    for _ in 0..n {
        let start = r.p;
        r.take(2)?;
        let name = r.u2()?;
        let desc = r.u2()?;
        r.attrs()?;
        if names[name as usize] == kind.name() && names[desc as usize] == kind.original_descriptor()
        {
            ensure!(selected.is_none(), "Duplicate bridge method");
            selected = Some((name, desc, &bytes[start + 6..r.p]));
        }
    }
    let attrs = r.attrs()?;
    ensure!(r.p == bytes.len(), "Trailing bridge source data");
    let (name, desc, method_attrs) = selected.context("Missing raw bridge method")?;
    let extra = if kind.instance() { 3 } else { 2 };
    let count = cp_count
        .checked_add(extra)
        .context("Bridge pool overflow")?;
    let this = cp_count + 1;
    let generated_name = kind.class_name();
    let mut out = bytes[..8].to_vec();
    out.extend(count.to_be_bytes());
    out.extend(&bytes[10..cp_end]);
    utf(&mut out, &generated_name)?;
    out.push(7);
    out.extend(cp_count.to_be_bytes());
    if extra == 3 {
        utf(&mut out, kind.descriptor())?;
    }
    out.extend(0x31u16.to_be_bytes());
    out.extend(this.to_be_bytes());
    out.extend(super_class.to_be_bytes());
    out.extend(0u16.to_be_bytes());
    out.extend(0u16.to_be_bytes());
    out.extend(1u16.to_be_bytes());
    out.extend(9u16.to_be_bytes());
    out.extend(name.to_be_bytes());
    out.extend(if extra == 3 { cp_count + 2 } else { desc }.to_be_bytes());
    out.extend(method_attrs);
    let retained: Vec<_> = attrs
        .into_iter()
        .filter(|(n, _)| {
            matches!(
                names[*n as usize].as_str(),
                "BootstrapMethods" | "SourceFile"
            )
        })
        .collect();
    out.extend(u16::try_from(retained.len())?.to_be_bytes());
    for (_, a) in retained {
        out.extend(a);
    }
    let parsed = ClassFile::parse(&out)?;
    ensure!(
        parsed.name == generated_name
            && parsed.methods.len() == 1
            && parsed.methods[0].code.as_ref().unwrap().bytes
                == method.code.as_ref().unwrap().bytes,
        "Bridge changed original Java bytecode"
    );
    let generated = GeneratedOrigin {
        generator: "boom-jdk-bridge".into(),
        abi: 1,
        host_loader: "bootstrap".into(),
        host_class: kind.owner().into(),
        host_source_id: origin.source_id.clone(),
        host_sha256: origin.sha256.clone(),
        site: kind.id(),
    };
    let proof = ClassOrigin {
        loader: "bootstrap".into(),
        binary_name: generated_name.replace('/', "."),
        source_id: "boom:jdk-bridge-v1".into(),
        jar_entry: format!("<generated>/{generated_name}.class"),
        java_class_major: parsed.major,
        sha256: files::digest_bytes(&out).sha256,
        generated: Some(Box::new(generated)),
    };
    Ok((out, proof))
}
pub(super) fn resolve<P: types::TypeProvider>(
    base: &P,
    loader: &str,
    name: &str,
) -> Result<Option<(Vec<u8>, ClassOrigin)>> {
    let Some((host, id)) = name.rsplit_once(MARKER) else {
        return Ok(None);
    };
    if base.name_in_use(name)? {
        return Ok(None);
    }
    ensure!(
        loader == "bootstrap"
            || loader == "vanilla-application"
            || loader == "explicit-application",
        "Unsupported JDK bridge loader"
    );
    let kind = Kind::from_id(u16::from_str_radix(id, 16)?)?;
    ensure!(
        id.len() == 4 && kind.owner() == host && kind.class_name() == name,
        "Noncanonical JDK bridge identity"
    );
    let (bytes, origin) = base.resolve("bootstrap", host)?;
    Ok(Some(generate(&bytes, &origin, kind)?))
}
pub(super) fn validate(class: &ClassFile, origin: &ClassOrigin) -> Result<()> {
    let g = origin
        .generated
        .as_ref()
        .context("Missing JDK bridge proof")?;
    let kind = Kind::from_id(g.site)?;
    ensure!(
        g.generator == "boom-jdk-bridge"
            && g.abi == 1
            && g.host_loader == "bootstrap"
            && g.host_class == kind.owner()
            && g.host_source_id == "jdk:java.base"
            && origin.loader == "bootstrap"
            && origin.source_id == "boom:jdk-bridge-v1"
            && class.name == kind.class_name()
            && class.field_info.is_empty()
            && class.methods.len() == 1
            && class.methods[0].name == kind.name()
            && class.methods[0].descriptor == kind.descriptor()
            && class.methods[0].access == 9,
        "JDK bridge provenance or shape changed"
    );
    Ok(())
}
/// A retained API frame has its original declaring class for security walks.
pub(super) fn original_holder(
    registry: &types::Registry<'_>,
    class: &ClassFile,
    origin: &ClassOrigin,
) -> Result<Option<usize>> {
    let Some(g) = origin
        .generated
        .as_ref()
        .filter(|g| g.generator == "boom-jdk-bridge")
    else {
        return Ok(None);
    };
    validate(class, origin)?;
    let id=registry.types.iter().position(|t|matches!(t,types::Type::Class{key,origin,..} if key.loader==g.host_loader&&key.name==g.host_class&&origin.source_id==g.host_source_id&&origin.sha256==g.host_sha256&&origin.generated.is_none())).context("Missing original JDK bridge holder identity")?;
    Ok(Some(id))
}

#[derive(Debug, Serialize)]
pub struct Inspection {
    pub kind: Kind,
    pub original: ClassOrigin,
    pub generated: ClassOrigin,
    pub original_class: std::path::PathBuf,
    pub generated_class: std::path::PathBuf,
    pub code_sha256: String,
    pub original_code_retained: bool,
    pub execution_complete: bool,
    pub full_game_ready: bool,
}
pub fn inspect(
    inputs: &crate::lock::InputLock,
    manifest: &std::path::Path,
    ids: &[u16],
    output: &std::path::Path,
) -> Result<Vec<Inspection>> {
    use types::TypeProvider;
    ensure!(
        !ids.is_empty() && ids.len() <= 12,
        "Inspect 1..12 JDK bridges"
    );
    let kinds = ids
        .iter()
        .map(|&id| Kind::from_id(id))
        .collect::<Result<Vec<_>>>()?;
    let base = types::VanillaTypes::new(inputs, manifest)?;
    let output = std::path::absolute(output)?;
    let mut result = Vec::new();
    for kind in kinds {
        let (bytes, origin) = base.resolve("bootstrap", kind.owner())?;
        let (generated, proof) = generate(&bytes, &origin, kind)?;
        let source = ClassFile::parse(&bytes)?;
        let target = ClassFile::parse(&generated)?;
        validate(&target, &proof)?;
        let original_code = source
            .method(kind.name(), Some(kind.original_descriptor()))?
            .code
            .as_ref()
            .unwrap();
        let generated_code = target.methods[0].code.as_ref().unwrap();
        ensure!(
            original_code.bytes == generated_code.bytes
                && original_code.max_stack == generated_code.max_stack
                && original_code.max_locals == generated_code.max_locals
                && original_code.handlers == generated_code.handlers,
            "Original bridge Code changed"
        );
        let original_class = output.join(format!("{:04x}-original.class", kind.id()));
        let generated_class = output.join(format!("{:04x}-generated.class", kind.id()));
        files::write_atomic(&original_class, &bytes)?;
        files::write_atomic(&generated_class, &generated)?;
        result.push(Inspection {
            kind,
            original: origin,
            generated: proof,
            original_class,
            generated_class,
            code_sha256: files::digest_bytes(&original_code.bytes).sha256,
            original_code_retained: true,
            execution_complete: false,
            full_game_ready: false,
        });
    }
    files::write_atomic(
        &output.join("inspection.json"),
        &serde_json::to_vec_pretty(&result)?,
    )?;
    Ok(result)
}
