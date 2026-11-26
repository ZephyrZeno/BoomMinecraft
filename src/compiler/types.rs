//! Loader-aware metadata and descriptor types for the future general linker.
//! This plan never licenses numeric.rs's erased single-class object operations.
use super::classfile::ClassFile;
use crate::{
    bytecode::{BytecodeProvider, ClassArchives, ClassOrigin, ClassSet, VanillaBytecodeProvider},
    files,
    jdk::JdkBase,
    lock::InputLock,
};
use anyhow::{Context, Result, bail, ensure};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

pub trait TypeProvider {
    fn name_in_use(&self, _name: &str) -> Result<bool> {
        anyhow::bail!("Compiler-generated classes require an inventory-aware provider")
    }
    fn resolve(&self, initiating_loader: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)>;
}

impl<T: TypeProvider + ?Sized> TypeProvider for &T {
    fn resolve(&self, loader: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
        (**self).resolve(loader, name)
    }
    fn name_in_use(&self, name: &str) -> Result<bool> {
        (**self).name_in_use(name)
    }
}

pub struct VanillaTypes<'a> {
    inputs: &'a InputLock,
    application: ClassSet,
    base: JdkBase,
    manifest: &'a Path,
    archives: ClassArchives,
}
impl<'a> VanillaTypes<'a> {
    pub fn bootstrap_contains(&self, name: &str) -> bool {
        self.base.classes.contains_key(&name.replace('/', "."))
    }
    pub fn new(inputs: &'a InputLock, manifest: &'a Path) -> Result<Self> {
        let application = VanillaBytecodeProvider { inputs }.snapshot()?;
        let base = JdkBase::read(manifest, inputs)?;
        Ok(Self {
            inputs,
            application,
            base,
            manifest,
            archives: ClassArchives::default(),
        })
    }
}
impl TypeProvider for VanillaTypes<'_> {
    fn name_in_use(&self, name: &str) -> Result<bool> {
        let name = name.replace('/', ".");
        Ok(self.application.classes.contains_key(&name) || self.base.classes.contains_key(&name))
    }
    fn resolve(&self, loader: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
        ensure!(
            matches!(loader, "bootstrap" | "vanilla-application"),
            "Unsupported initiating loader {loader}"
        );
        let binary = name.replace('/', ".");
        if self.base.classes.contains_key(&binary) {
            return self.base.read_class(self.manifest, name);
        }
        ensure!(
            loader != "bootstrap",
            "Bootstrap class {name} is absent from java.base; other JDK module providers are not implemented"
        );
        ensure!(
            !name.starts_with("java/"),
            "Class {name} requires another JDK/platform module provider; application java.* definitions are forbidden"
        );
        let origin = self.application.classes.get(&binary).with_context(|| {
            format!(
                "Missing application type {name}; platform/other module providers may be required"
            )
        })?;
        Ok((
            self.archives
                .read(&self.inputs.file(&origin.source_id)?.path, origin)?,
            origin.clone(),
        ))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, serde::Deserialize)]
pub enum Primitive {
    Boolean,
    Byte,
    Char,
    Short,
    Int,
    Long,
    Float,
    Double,
    Void,
}
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, serde::Deserialize)]
pub struct ClassKey {
    pub loader: String,
    pub name: String,
}
#[derive(Debug, Serialize, serde::Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Type {
    Primitive {
        value: Primitive,
    },
    Class {
        key: ClassKey,
        origin: Box<ClassOrigin>,
        access: u16,
        superclass: Option<usize>,
        interfaces: Vec<usize>,
    },
    Array {
        component: usize,
    },
}
impl Type {
    fn reference(&self) -> bool {
        !matches!(self, Self::Primitive { .. })
    }
}
#[derive(Debug, Serialize)]
pub struct MethodType {
    pub arguments: Vec<usize>,
    pub result: Option<usize>,
}
#[derive(Debug, Serialize)]
pub struct FieldType {
    pub name: String,
    pub descriptor: String,
    pub value: usize,
}
#[derive(Debug, Serialize)]
pub struct MemberType {
    pub name: String,
    pub descriptor: String,
    pub signature: MethodType,
}
#[derive(Debug, Serialize)]
pub struct Root {
    pub class: usize,
    pub fields: Vec<FieldType>,
    pub methods: Vec<MemberType>,
}
#[derive(Debug, Serialize)]
pub struct Plan {
    pub schema: u32,
    pub input_fingerprint: String,
    pub jdk_fingerprint: String,
    pub types: Vec<Type>,
    pub roots: Vec<Root>,
    pub requested_types: Vec<usize>,
    pub metadata_assembly: std::path::PathBuf,
    pub metadata_digest: files::FileDigest,
    pub assembly_emitted: bool,
    pub full_game_ready: bool,
}

pub struct Registry<'a> {
    provider: &'a dyn TypeProvider,
    pub types: Vec<Type>,
    classes: BTreeMap<ClassKey, usize>,
    primitive: BTreeMap<Primitive, usize>,
    arrays: BTreeMap<usize, usize>,
    active: BTreeSet<ClassKey>,
    definitions: BTreeMap<usize, ClassFile>,
    bytes: usize,
}
fn valid_name(name: &str) -> Result<()> {
    ensure!(
        !name.is_empty()
            && name
                .split('/')
                .all(|part| !part.is_empty() && !part.contains(['.', ';', '[', '\0'])),
        "Invalid internal class name {name:?}"
    );
    Ok(())
}
impl<'a> Registry<'a> {
    pub fn new(provider: &'a dyn TypeProvider) -> Self {
        Self {
            provider,
            types: Vec::new(),
            classes: BTreeMap::new(),
            primitive: BTreeMap::new(),
            arrays: BTreeMap::new(),
            active: BTreeSet::new(),
            definitions: BTreeMap::new(),
            bytes: 0,
        }
    }
    pub(super) fn contains_name(&self, name: &str) -> Result<bool> {
        self.provider.name_in_use(name)
    }
    fn push(&mut self, ty: Type) -> Result<usize> {
        ensure!(self.types.len() < 16384, "Type graph exceeds 16384 nodes");
        let id = self.types.len();
        self.types.push(ty);
        Ok(id)
    }
    pub fn class(&mut self, loader: &str, name: &str) -> Result<usize> {
        valid_name(name)?;
        ensure!(
            self.active.len() < 128,
            "Type hierarchy exceeds depth limit"
        );
        let (bytes, origin) = self
            .provider
            .resolve(loader, name)
            .with_context(|| format!("Resolving type {name} from {loader}"))?;
        ensure!(
            origin.binary_name == name.replace('/', ".")
                && origin.sha256 == files::digest_bytes(&bytes).sha256,
            "Type provider origin/bytes mismatch"
        );
        let key = ClassKey {
            loader: origin.loader.clone(),
            name: name.into(),
        };
        ensure!(
            !self.active.contains(&key),
            "Circular class/interface hierarchy at {name}"
        );
        if let Some(&id) = self.classes.get(&key) {
            let Type::Class {
                origin: previous, ..
            } = &self.types[id]
            else {
                unreachable!()
            };
            ensure!(
                previous.sha256 == origin.sha256 && previous.generated == origin.generated,
                "Class definition changed within a type graph"
            );
            return Ok(id);
        }
        ensure!(self.classes.len() < 4096, "Type graph exceeds 4096 classes");
        self.bytes = self
            .bytes
            .checked_add(bytes.len())
            .context("Type graph byte overflow")?;
        ensure!(
            self.bytes <= 256 * 1024 * 1024,
            "Type graph exceeds 256 MiB"
        );
        let class = ClassFile::parse(&bytes)?;
        ensure!(
            class.name == name && class.major == origin.java_class_major,
            "Type class/name/version mismatch"
        );
        let is_interface = class.access & 0x200 != 0;
        ensure!(
            !is_interface || class.access & 0x410 == 0x400,
            "Interface must be abstract and non-final"
        );
        self.active.insert(key.clone());
        let id = self.push(Type::Class {
            key: key.clone(),
            origin: Box::new(origin),
            access: class.access,
            superclass: None,
            interfaces: Vec::new(),
        })?;
        self.classes.insert(key.clone(), id);
        let superclass = if name == "java/lang/Object" {
            ensure!(
                key.loader == "bootstrap" && class.super_name.is_empty() && !is_interface,
                "Invalid root Object identity"
            );
            None
        } else {
            ensure!(
                !class.super_name.is_empty(),
                "Non-Object class requires a superclass"
            );
            ensure!(
                !is_interface || class.super_name == "java/lang/Object",
                "Interface superclass must be Object"
            );
            let parent = self.class(&key.loader, &class.super_name)?;
            let Type::Class { access, .. } = &self.types[parent] else {
                unreachable!()
            };
            ensure!(
                access & (0x200 | 0x10) == 0,
                "Superclass is an interface or final class"
            );
            Some(parent)
        };
        let mut interfaces = Vec::new();
        for name in &class.interface_names {
            let interface = self.class(&key.loader, name)?;
            let Type::Class { access, .. } = &self.types[interface] else {
                unreachable!()
            };
            ensure!(
                access & 0x200 != 0 && !interfaces.contains(&interface),
                "Invalid or duplicate superinterface"
            );
            interfaces.push(interface);
        }
        let Type::Class {
            superclass: parent,
            interfaces: edges,
            ..
        } = &mut self.types[id]
        else {
            unreachable!()
        };
        *parent = superclass;
        *edges = interfaces;
        self.definitions.insert(id, class);
        self.active.remove(&key);
        Ok(id)
    }
    pub(super) fn primitive(&mut self, value: Primitive) -> Result<usize> {
        if let Some(&id) = self.primitive.get(&value) {
            return Ok(id);
        }
        let id = self.push(Type::Primitive { value })?;
        self.primitive.insert(value, id);
        Ok(id)
    }
    pub(super) fn array(&mut self, component: usize) -> Result<usize> {
        ensure!(
            !matches!(
                self.types[component],
                Type::Primitive {
                    value: Primitive::Void
                }
            ),
            "void cannot be an array component"
        );
        if let Some(&id) = self.arrays.get(&component) {
            return Ok(id);
        }
        let id = self.push(Type::Array { component })?;
        self.arrays.insert(component, id);
        Ok(id)
    }
    fn parse(&mut self, loader: &str, text: &[u8], position: &mut usize) -> Result<usize> {
        let mut dimensions = 0;
        while text.get(*position) == Some(&b'[') {
            *position += 1;
            dimensions += 1;
            ensure!(dimensions <= 255, "Array descriptor exceeds 255 dimensions");
        }
        let tag = *text.get(*position).context("Truncated type descriptor")?;
        *position += 1;
        let mut id = if tag == b'L' {
            let start = *position;
            while text.get(*position).is_some_and(|b| *b != b';') {
                *position += 1;
            }
            ensure!(
                text.get(*position) == Some(&b';'),
                "Unterminated object descriptor"
            );
            let name = std::str::from_utf8(&text[start..*position])?;
            *position += 1;
            self.class(loader, name)?
        } else {
            self.primitive(match tag {
                b'Z' => Primitive::Boolean,
                b'B' => Primitive::Byte,
                b'C' => Primitive::Char,
                b'S' => Primitive::Short,
                b'I' => Primitive::Int,
                b'J' => Primitive::Long,
                b'F' => Primitive::Float,
                b'D' => Primitive::Double,
                _ => bail!("Invalid field type descriptor"),
            })?
        };
        for _ in 0..dimensions {
            id = self.array(id)?;
        }
        Ok(id)
    }
    pub fn field(&mut self, loader: &str, descriptor: &str) -> Result<usize> {
        let mut position = 0;
        let id = self.parse(loader, descriptor.as_bytes(), &mut position)?;
        ensure!(
            position == descriptor.len(),
            "Trailing field descriptor data"
        );
        Ok(id)
    }
    /// Resolve an ldc Class symbol without preparing or initializing its target.
    pub fn literal(&mut self, loader: &str, name: &str) -> Result<usize> {
        if name.starts_with('[') {
            self.field(loader, name)
        } else {
            self.class(loader, name)
        }
    }
    pub fn definition(&self, id: usize) -> Option<&ClassFile> {
        self.definitions.get(&id)
    }
    pub fn method(&mut self, loader: &str, descriptor: &str) -> Result<MethodType> {
        let text = descriptor.as_bytes();
        ensure!(
            text.first() == Some(&b'('),
            "Missing method descriptor arguments"
        );
        let mut position = 1;
        let mut arguments = Vec::new();
        let mut slots = 0;
        while text.get(position) != Some(&b')') {
            let id = self.parse(loader, text, &mut position)?;
            slots += if matches!(
                self.types[id],
                Type::Primitive {
                    value: Primitive::Long | Primitive::Double
                }
            ) {
                2
            } else {
                1
            };
            ensure!(
                slots <= 255,
                "Method descriptor exceeds 255 parameter slots"
            );
            arguments.push(id);
        }
        position += 1;
        let result = if text.get(position) == Some(&b'V') {
            position += 1;
            None
        } else {
            Some(self.parse(loader, text, &mut position)?)
        };
        ensure!(position == text.len(), "Trailing method descriptor data");
        Ok(MethodType { arguments, result })
    }
    pub fn root(&mut self, loader: &str, name: &str) -> Result<Root> {
        let id = self.class(loader, name)?;
        let Type::Class { key, .. } = &self.types[id] else {
            unreachable!()
        };
        let loader = key.loader.clone();
        let class = &self.definitions[&id];
        let fields: Vec<_> = class
            .field_info
            .iter()
            .map(|f| (f.name.clone(), f.descriptor.clone()))
            .collect();
        let methods: Vec<_> = class
            .methods
            .iter()
            .map(|m| (m.name.clone(), m.descriptor.clone()))
            .collect();
        let fields = fields
            .into_iter()
            .map(|(name, descriptor)| {
                Ok(FieldType {
                    value: self.field(&loader, &descriptor)?,
                    name,
                    descriptor,
                })
            })
            .collect::<Result<_>>()?;
        let methods = methods
            .into_iter()
            .map(|(name, descriptor)| {
                Ok(MemberType {
                    signature: self.method(&loader, &descriptor)?,
                    name,
                    descriptor,
                })
            })
            .collect::<Result<_>>()?;
        Ok(Root {
            class: id,
            fields,
            methods,
        })
    }
    /// Assignment conversion between already loaded types. No class initialization.
    pub fn assignable(&self, from: usize, to: usize) -> bool {
        if from == to {
            return self.types.get(from).is_some();
        }
        let (Some(source), Some(target)) = (self.types.get(from), self.types.get(to)) else {
            return false;
        };
        match (source, target) {
            (Type::Array { component: a }, Type::Array { component: b }) => {
                self.types[*a].reference() && self.types[*b].reference() && self.assignable(*a, *b)
            }
            (Type::Array { .. }, Type::Class { key, .. }) => {
                key.loader == "bootstrap"
                    && matches!(
                        key.name.as_str(),
                        "java/lang/Object" | "java/lang/Cloneable" | "java/io/Serializable"
                    )
            }
            (
                Type::Class {
                    superclass,
                    interfaces,
                    ..
                },
                Type::Class { .. },
            ) => {
                superclass.is_some_and(|parent| self.assignable(parent, to))
                    || interfaces
                        .iter()
                        .any(|&interface| self.assignable(interface, to))
            }
            _ => false,
        }
    }
}

pub fn plan(
    inputs: &InputLock,
    manifest: &Path,
    names: &[String],
    descriptors: &[String],
    output: &Path,
) -> Result<Plan> {
    ensure!(
        !names.is_empty() && names.len() <= 128,
        "Supply 1..128 root classes"
    );
    let provider = VanillaTypes::new(inputs, manifest)?;
    let mut registry = Registry::new(&provider);
    let roots = names
        .iter()
        .map(|name| registry.root("vanilla-application", &name.replace('.', "/")))
        .collect::<Result<_>>()?;
    ensure!(
        descriptors.len() <= 128,
        "Too many requested type descriptors"
    );
    let requested_types = descriptors
        .iter()
        .map(|descriptor| registry.field("vanilla-application", descriptor))
        .collect::<Result<_>>()?;
    let metadata = output.with_extension("asm");
    files::write_atomic(&metadata, emit_metadata(&registry.types)?.as_bytes())?;
    let result = Plan {
        schema: 1,
        input_fingerprint: inputs.fingerprint.clone(),
        jdk_fingerprint: provider.base.fingerprint.clone(),
        types: registry.types,
        roots,
        requested_types,
        metadata_assembly: files::absolute(&metadata)?,
        metadata_digest: files::digest(&metadata)?,
        assembly_emitted: false,
        full_game_ready: false,
    };
    files::write_atomic(output, &serde_json::to_vec_pretty(&result)?)?;
    Ok(result)
}

/// Read-only metadata only: separate from the legacy single-class heap layout.
pub fn emit_metadata(types: &[Type]) -> Result<String> {
    use std::fmt::Write;
    ensure!(
        !types.is_empty() && types.len() <= 16384,
        "Invalid type metadata count"
    );
    let mut text = String::from(
        "; Loader-aware type metadata. No Java code is executed here.\noption casemap:none\n.const\nALIGN 8\nboom_type_table LABEL QWORD\n",
    );
    for id in 0..types.len() {
        writeln!(text, "    DQ boom_t{id}")?;
    }
    for (id, ty) in types.iter().enumerate() {
        let (kind, flags, parent) = match ty {
            Type::Primitive { value } => (0, *value as u32, None),
            Type::Array { component } => {
                ensure!(*component < types.len(), "Invalid array component");
                ensure!(
                    !matches!(
                        types[*component],
                        Type::Primitive {
                            value: Primitive::Void
                        }
                    ),
                    "void cannot be an array component"
                );
                (3, 0, Some(*component))
            }
            Type::Class {
                key,
                access,
                superclass,
                ..
            } => {
                let flags = if key.loader == "bootstrap" {
                    match key.name.as_str() {
                        "java/lang/Object" => 1,
                        "java/lang/Cloneable" => 2,
                        "java/io/Serializable" => 4,
                        _ => 0,
                    }
                } else {
                    0
                };
                (if access & 0x200 != 0 { 2 } else { 1 }, flags, *superclass)
            }
        };
        let mut ancestors = BTreeSet::<usize>::new();
        let mut pending = Vec::<usize>::new();
        if let Type::Class {
            superclass,
            interfaces,
            ..
        } = ty
        {
            pending.extend(superclass);
            pending.extend(interfaces);
        }
        while let Some(ancestor) = pending.pop() {
            ensure!(ancestor != id, "Circular metadata hierarchy");
            if !ancestors.insert(ancestor) {
                continue;
            }
            let Some(Type::Class {
                superclass,
                interfaces,
                ..
            }) = types.get(ancestor)
            else {
                bail!("Invalid metadata ancestor")
            };
            pending.extend(superclass);
            pending.extend(interfaces);
        }
        ensure!(
            ancestors.len() <= 4096,
            "Type metadata exceeds ancestor budget"
        );
        writeln!(
            text,
            "ALIGN 8\nboom_t{id} LABEL BYTE\n    DD 054595045h, 1, {kind}, {flags}"
        )?;
        writeln!(
            text,
            "    DQ {}",
            parent.map_or("0".into(), |id| format!("boom_t{id}"))
        )?;
        if ancestors.is_empty() {
            writeln!(text, "    DQ 0")?;
        } else {
            writeln!(text, "    DQ boom_t{id}_ancestors")?;
        }
        writeln!(text, "    DD {}, 0", ancestors.len())?;
        if !ancestors.is_empty() {
            writeln!(text, "boom_t{id}_ancestors LABEL QWORD")?;
            for ancestor in ancestors {
                writeln!(text, "    DQ boom_t{ancestor}")?;
            }
        }
        ensure!(
            text.len() <= 256 * 1024 * 1024,
            "Type metadata assembly exceeds 256 MiB"
        );
    }
    writeln!(
        text,
        ".code\nPUBLIC boom_get_type_count\nPUBLIC boom_get_type_descriptor\nboom_get_type_count PROC\n    mov eax, {}\n    ret\nboom_get_type_count ENDP\nboom_get_type_descriptor PROC\n    cmp ecx, {}\n    jae boom_type_missing\n    lea rax, boom_type_table\n    mov rax, QWORD PTR [rax+rcx*8]\n    ret\nboom_type_missing:\n    xor eax, eax\n    ret\nboom_get_type_descriptor ENDP\nEND",
        types.len(),
        types.len()
    )?;
    Ok(text)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn void_mirror_is_unique_and_never_a_value_or_array_component() {
        let mut registry = Registry::new(&Empty);
        let id = registry.primitive(Primitive::Void).unwrap();
        assert_eq!(id, registry.primitive(Primitive::Void).unwrap());
        assert!(!registry.types[id].reference());
        for descriptor in ["V", "[V", "[[V", "(V)I", "([V)V"] {
            assert!(
                if descriptor.starts_with('(') {
                    registry.method("bootstrap", descriptor).is_err()
                } else {
                    registry.field("bootstrap", descriptor).is_err()
                },
                "{descriptor}"
            );
        }
        assert!(registry.array(id).is_err());
        assert!(
            emit_metadata(&[
                Type::Primitive {
                    value: Primitive::Void
                },
                Type::Array { component: 0 }
            ])
            .is_err()
        );
        assert_eq!(registry.method("bootstrap", "()V").unwrap().result, None);
        assert!(registry.assignable(id, id));
        let integer = registry.primitive(Primitive::Int).unwrap();
        assert!(!registry.assignable(id, integer));
        assert!(!registry.assignable(integer, id));
    }
    struct Empty;
    impl TypeProvider for Empty {
        fn resolve(&self, _: &str, _: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            bail!("No classes")
        }
    }
    fn fixture(name: &str, parent: &str, interfaces: &[&str], access: u16) -> Vec<u8> {
        fn short(bytes: &mut Vec<u8>, value: u16) {
            bytes.extend_from_slice(&value.to_be_bytes());
        }
        let mut names = vec![name];
        if !parent.is_empty() {
            names.push(parent);
        }
        names.extend(interfaces);
        let mut bytes = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65];
        short(&mut bytes, (names.len() * 2 + 1) as u16);
        for (index, name) in names.iter().enumerate() {
            bytes.push(1);
            short(&mut bytes, name.len() as u16);
            bytes.extend_from_slice(name.as_bytes());
            bytes.push(7);
            short(&mut bytes, (index * 2 + 1) as u16);
        }
        short(&mut bytes, access);
        short(&mut bytes, 2);
        short(&mut bytes, if parent.is_empty() { 0 } else { 4 });
        short(&mut bytes, interfaces.len() as u16);
        for index in 0..interfaces.len() {
            short(&mut bytes, ((index + 2) * 2 + 2) as u16);
        }
        for _ in 0..3 {
            short(&mut bytes, 0);
        }
        bytes
    }
    struct Memory(BTreeMap<String, Vec<u8>>);
    impl TypeProvider for Memory {
        fn resolve(&self, loader: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let bytes = self.0.get(name).context("Missing test type")?.clone();
            Ok((
                bytes.clone(),
                ClassOrigin {
                    generated: None,
                    loader: if name == "java/lang/Object" {
                        "bootstrap"
                    } else {
                        loader
                    }
                    .into(),
                    binary_name: name.replace('/', "."),
                    source_id: "fixture".into(),
                    jar_entry: format!("{name}.class"),
                    java_class_major: 65,
                    sha256: files::digest_bytes(&bytes).sha256,
                },
            ))
        }
    }
    #[test]
    fn metadata_loads_actual_interfaces_and_separates_equal_names_in_two_loaders() {
        let provider = Memory(BTreeMap::from([
            (
                "java/lang/Object".into(),
                fixture("java/lang/Object", "", &[], 1),
            ),
            ("p/I".into(), fixture("p/I", "java/lang/Object", &[], 0x601)),
            (
                "p/Node".into(),
                fixture("p/Node", "java/lang/Object", &["p/I"], 1),
            ),
        ]));
        let mut registry = Registry::new(&provider);
        let a = registry.class("mod-a", "p/Node").unwrap();
        let b = registry.class("mod-b", "p/Node").unwrap();
        assert_ne!(a, b);
        assert!(!registry.assignable(a, b));
        let interface = registry.class("mod-a", "p/I").unwrap();
        assert!(registry.assignable(a, interface));
        assert!(!registry.assignable(b, interface));
        let root = registry.class("bootstrap", "java/lang/Object").unwrap();
        assert!(registry.assignable(a, root));
        assert!(registry.assignable(b, root));
        assert_eq!(
            registry
                .method("mod-a", "(Lp/Node;)Lp/I;")
                .unwrap()
                .arguments,
            vec![a]
        );
    }
    #[test]
    fn circular_final_and_class_as_interface_edges_are_rejected() {
        let base = (
            "java/lang/Object".into(),
            fixture("java/lang/Object", "", &[], 1),
        );
        for (a, b) in [
            (fixture("p/A", "p/B", &[], 1), fixture("p/B", "p/A", &[], 1)),
            (
                fixture("p/A", "p/B", &[], 1),
                fixture("p/B", "java/lang/Object", &[], 0x11),
            ),
            (
                fixture("p/A", "java/lang/Object", &["p/B"], 1),
                fixture("p/B", "java/lang/Object", &[], 1),
            ),
        ] {
            let provider = Memory(BTreeMap::from([
                base.clone(),
                ("p/A".into(), a),
                ("p/B".into(), b),
            ]));
            assert!(
                Registry::new(&provider)
                    .class("application", "p/A")
                    .is_err()
            );
        }
        let wrong = Memory(BTreeMap::from([(
            "p/A".into(),
            fixture("p/Wrong", "java/lang/Object", &[], 1),
        )]));
        assert!(Registry::new(&wrong).class("application", "p/A").is_err());
    }
    #[test]
    fn descriptors_keep_primitive_identity_dimensions_and_slot_limits() {
        let mut types = Registry::new(&Empty);
        let a = types.field("bootstrap", "[[I").unwrap();
        let b = types.field("bootstrap", "[I").unwrap();
        assert_eq!(types.literal("bootstrap", "[[I").unwrap(), a);
        // CONSTANT_Class "I" is a class name, never the primitive descriptor I.
        assert!(types.literal("bootstrap", "I").is_err());
        assert_ne!(a, b);
        assert!(!types.assignable(a, b));
        assert_ne!(
            types.field("bootstrap", "Z").unwrap(),
            types.field("bootstrap", "B").unwrap()
        );
        for descriptor in ["V", "[V", "Iextra", "L;", "[", "()I"] {
            assert!(types.field("bootstrap", descriptor).is_err());
        }
        for descriptor in ["(I", "(V)V", "()VI", "(I)Vx"] {
            assert!(types.method("bootstrap", descriptor).is_err());
        }
        assert!(
            types
                .method("bootstrap", &format!("({})V", "J".repeat(128)))
                .is_err()
        );
        assert!(
            types
                .field("bootstrap", &format!("{}I", "[".repeat(256)))
                .is_err()
        );
        assert_eq!(
            types
                .method("bootstrap", "(IJ[[D)V")
                .unwrap()
                .arguments
                .len(),
            3
        );
    }
    fn object(
        types: &mut Registry<'_>,
        loader: &str,
        name: &str,
        parent: Option<usize>,
        interfaces: Vec<usize>,
    ) -> usize {
        types
            .push(Type::Class {
                key: ClassKey {
                    loader: loader.into(),
                    name: name.into(),
                },
                origin: Box::new(ClassOrigin {
                    generated: None,
                    loader: loader.into(),
                    binary_name: name.replace('/', "."),
                    source_id: String::new(),
                    jar_entry: String::new(),
                    java_class_major: 65,
                    sha256: String::new(),
                }),
                access: 1,
                superclass: parent,
                interfaces,
            })
            .unwrap()
    }
    #[test]
    fn identity_and_covariance_preserve_defining_loader() {
        let mut types = Registry::new(&Empty);
        let root = object(&mut types, "bootstrap", "java/lang/Object", None, vec![]);
        let interface = object(
            &mut types,
            "bootstrap",
            "java/io/Serializable",
            Some(root),
            vec![],
        );
        let a = object(
            &mut types,
            "mod-a",
            "example/Node",
            Some(root),
            vec![interface],
        );
        let b = object(&mut types, "mod-b", "example/Node", Some(root), vec![]);
        assert!(!types.assignable(a, b));
        assert!(types.assignable(a, root));
        assert!(types.assignable(a, interface));
        let aa = types.array(a).unwrap();
        let ba = types.array(b).unwrap();
        let objects = types.array(root).unwrap();
        assert!(!types.assignable(aa, ba));
        assert!(types.assignable(aa, objects));
        assert!(types.assignable(aa, interface));
        let ints = types.field("bootstrap", "[I").unwrap();
        let int2 = types.array(ints).unwrap();
        assert!(!types.assignable(ints, objects));
        assert!(types.assignable(int2, objects));
        let fake = object(&mut types, "mod-a", "java/lang/Object", None, vec![]);
        assert!(!types.assignable(ints, fake));
    }
}
