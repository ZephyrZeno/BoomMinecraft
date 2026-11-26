//! Nominal declarations and candidate Java layouts from verified IR payloads.
//! Plan IDs are compiler identities, never existing runtime table indices.
use super::{
    classfile::{Field, Method},
    hierarchy::{self, Metadata},
    translation_ir,
    types::ClassKey,
};
use crate::{
    bytecode::ClassOrigin,
    jdk_classes::{self, Packages},
};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Deserialize)]
pub struct MethodHeader {
    pub id: usize,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub code_sha256: Option<String>,
}
#[derive(Debug, Deserialize)]
pub struct Header {
    pub schema: u32,
    pub class_id: usize,
    pub origin: ClassOrigin,
    pub name: String,
    pub access: u16,
    pub superclass: String,
    pub interfaces: Vec<String>,
    pub fields: Vec<translation_ir::Field>,
    pub nest_host: Option<String>,
    pub nest_members: Option<Vec<String>>,
    pub methods: Vec<MethodHeader>,
    pub diagnostic: Option<String>,
    #[serde(default)]
    pub constants: TypeMentions,
}
#[derive(Debug, Default)]
pub struct TypeMentions(pub Vec<String>);
impl<'de> Deserialize<'de> for TypeMentions {
    fn deserialize<D: serde::Deserializer<'de>>(
        deserializer: D,
    ) -> std::result::Result<Self, D::Error> {
        struct Constants;
        #[derive(Deserialize)]
        struct Descriptor {
            descriptor: String,
        }
        struct Mention(Option<String>);
        impl<'de> Deserialize<'de> for Mention {
            fn deserialize<D: serde::Deserializer<'de>>(
                deserializer: D,
            ) -> std::result::Result<Self, D::Error> {
                struct Value;
                impl<'de> serde::de::Visitor<'de> for Value {
                    type Value = Mention;
                    fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                        f.write_str("a symbolic constant")
                    }
                    fn visit_map<A: serde::de::MapAccess<'de>>(
                        self,
                        mut map: A,
                    ) -> std::result::Result<Mention, A::Error> {
                        let Some(kind) = map.next_key::<String>()? else {
                            return Ok(Mention(None));
                        };
                        let value = match kind.as_str() {
                            "Class" => {
                                let name = map.next_value::<String>()?;
                                Some(if name.starts_with('[') {
                                    name
                                } else {
                                    format!("L{name};")
                                })
                            }
                            "Field" | "Method" | "Handle" | "Dynamic" | "InvokeDynamic" => {
                                Some(map.next_value::<Descriptor>()?.descriptor)
                            }
                            "MethodType" => Some(map.next_value::<String>()?),
                            _ => {
                                map.next_value::<serde::de::IgnoredAny>()?;
                                None
                            }
                        };
                        ensure_empty(&mut map)?;
                        Ok(Mention(value))
                    }
                }
                deserializer.deserialize_map(Value)
            }
        }
        fn ensure_empty<'de, A: serde::de::MapAccess<'de>>(
            map: &mut A,
        ) -> std::result::Result<(), A::Error> {
            if map.next_key::<serde::de::IgnoredAny>()?.is_some() {
                return Err(serde::de::Error::custom("Extra symbolic constant variant"));
            }
            Ok(())
        }
        impl<'de> serde::de::Visitor<'de> for Constants {
            type Value = TypeMentions;
            fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                f.write_str("symbolic constant map")
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut map: A,
            ) -> std::result::Result<TypeMentions, A::Error> {
                let mut values = BTreeSet::new();
                while map.next_key::<serde::de::IgnoredAny>()?.is_some() {
                    if let Some(value) = map.next_value::<Mention>()?.0 {
                        values.insert(value);
                    }
                }
                Ok(TypeMentions(values.into_iter().collect()))
            }
        }
        deserializer.deserialize_map(Constants)
    }
}
pub struct Node {
    pub id: usize,
    pub key: ClassKey,
    pub origin: ClassOrigin,
    pub access: u16,
    pub superclass: Option<usize>,
    pub interfaces: Vec<usize>,
    pub fields: Vec<Field>,
    pub methods: Vec<Method>,
    pub method_ids: Vec<usize>,
    pub nest_host: Option<String>,
    pub nest_members: Option<Vec<String>>,
    pub hierarchy_error: Option<String>,
}
pub struct Catalog {
    pub nodes: Vec<Node>,
    pub methods: usize,
    index: BTreeMap<ClassKey, usize>,
    packages: Packages,
    ancestors: Vec<BTreeSet<usize>>,
    pub type_mentions: Vec<(String, String)>,
}
#[derive(Debug, Serialize)]
pub struct Layout {
    pub class_id: usize,
    pub defining_loader: String,
    pub name: String,
    pub source_sha256: String,
    pub candidate: Option<hierarchy::Layout>,
    pub static_fields: Vec<StaticField>,
    pub requires_vm_layout_contract: bool,
    pub runtime_abi_verified: bool,
    pub diagnostic: Option<String>,
}
#[derive(Debug, Serialize)]
pub struct StaticField {
    pub declaring_field: usize,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub storage_bytes: usize,
    pub reference: bool,
}
pub fn vm_owned(name: &str) -> bool {
    matches!(
        name,
        "java/lang/String"
            | "java/lang/Class"
            | "java/lang/ModuleLayer"
            | "java/lang/reflect/Field"
            | "java/lang/reflect/Constructor"
    )
}
fn lookup(
    index: &BTreeMap<ClassKey, usize>,
    packages: &Packages,
    loader: &str,
    name: &str,
) -> Option<usize> {
    jdk_classes::lookup(packages, loader, name, |loader, name| {
        index
            .get(&ClassKey {
                loader: loader.into(),
                name: name.into(),
            })
            .copied()
    })
}
impl Catalog {
    pub fn new(headers: Vec<Header>) -> Result<Self> {
        let packages = jdk_classes::inferred_packages(headers.iter().map(|header| &header.origin))?;
        Self::with_packages(headers, packages)
    }
    pub fn with_packages(headers: Vec<Header>, mut packages: Packages) -> Result<Self> {
        for (package, owner) in jdk_classes::inferred_packages(headers.iter().map(|h| &h.origin))? {
            jdk_classes::add_package(&mut packages, package, owner)?;
        }
        ensure!(
            !headers.is_empty() && headers.len() <= 100_000,
            "Invalid nominal class count"
        );
        let mut index = BTreeMap::new();
        let mut methods = 0;
        for (id, header) in headers.iter().enumerate() {
            ensure!(
                header.class_id == id && header.schema == super::symbolic::SCHEMA,
                "Invalid IR class header identity"
            );
            ensure!(
                header.name == header.origin.binary_name.replace('.', "/"),
                "IR class name differs from source origin"
            );
            ensure!(
                matches!(
                    header.origin.loader.as_str(),
                    "bootstrap" | "platform" | "vanilla-application"
                ),
                "Additional defining loader policy is required"
            );
            ensure!(
                jdk_classes::is_system(&header.origin)
                    || header.origin.loader == "bootstrap"
                    || !header.name.starts_with("java/"),
                "Application java.* definition is forbidden"
            );
            let key = ClassKey {
                loader: header.origin.loader.clone(),
                name: header.name.clone(),
            };
            ensure!(
                index.insert(key, id).is_none(),
                "Duplicate defining-loader class identity"
            );
            for method in &header.methods {
                ensure!(
                    method.id == methods,
                    "Noncontiguous nominal method identities"
                );
                methods += 1;
            }
        }
        ensure!(methods <= 1_000_000, "Nominal method budget exceeded");
        let mut nodes = vec![];
        for header in &headers {
            let mut errors = vec![];
            if let Some(diagnostic) = &header.diagnostic {
                errors.push(format!("IR frontend: {diagnostic}"));
            }
            let superclass = if header.superclass.is_empty() {
                None
            } else {
                match lookup(&index, &packages, &header.origin.loader, &header.superclass) {
                    Some(parent) => Some(parent),
                    None => {
                        errors.push(format!("Definition required: {}", header.superclass));
                        None
                    }
                }
            };
            let mut interfaces = vec![];
            for name in &header.interfaces {
                match lookup(&index, &packages, &header.origin.loader, name) {
                    Some(parent) => interfaces.push(parent),
                    None => errors.push(format!("Definition required: {name}")),
                }
            }
            nodes.push(Node {
                id: header.class_id,
                key: ClassKey {
                    loader: header.origin.loader.clone(),
                    name: header.name.clone(),
                },
                origin: header.origin.clone(),
                access: header.access,
                superclass,
                interfaces,
                fields: header
                    .fields
                    .iter()
                    .map(|f| Field {
                        name: f.name.clone(),
                        descriptor: f.descriptor.clone(),
                        access: f.access,
                        constant_value: f.constant_value,
                    })
                    .collect(),
                methods: header
                    .methods
                    .iter()
                    .map(|m| Method {
                        name: m.name.clone(),
                        descriptor: m.descriptor.clone(),
                        access: m.access,
                        code: None,
                        line_numbers: vec![],
                        runtime_visible_annotations: vec![],
                    })
                    .collect(),
                method_ids: header.methods.iter().map(|m| m.id).collect(),
                nest_host: header.nest_host.clone(),
                nest_members: header.nest_members.clone(),
                hierarchy_error: (!errors.is_empty()).then(|| errors.join("; ")),
            });
        }
        for node in &mut nodes {
            if node.key.loader == "bootstrap" && node.key.name == "java/lang/Object" {
                if node.superclass.is_some() || node.access & 0x200 != 0 {
                    node.hierarchy_error = Some("Invalid bootstrap Object definition".into());
                }
            } else if node.superclass.is_none()
                && node.access & 0x8000 == 0
                && node.hierarchy_error.is_none()
            {
                node.hierarchy_error = Some("Non-Object class requires a superclass".into());
            }
        }
        let mut type_mentions = vec![];
        for header in &headers {
            for descriptor in header
                .constants
                .0
                .iter()
                .chain(header.fields.iter().map(|f| &f.descriptor))
                .chain(header.methods.iter().map(|m| &m.descriptor))
            {
                type_mentions.push((header.origin.loader.clone(), descriptor.clone()));
            }
        }
        let mut catalog = Self {
            ancestors: vec![BTreeSet::new(); nodes.len()],
            nodes,
            index,
            packages,
            methods,
            type_mentions,
        };
        let mut states = vec![0; catalog.nodes.len()];
        for id in 0..catalog.nodes.len() {
            let _ = catalog.build_ancestors(id, &mut states, 0);
        }
        Ok(catalog)
    }
    fn build_ancestors(&mut self, id: usize, states: &mut [u8], depth: usize) -> Result<()> {
        if states[id] == 2 {
            return Ok(());
        }
        if states[id] == 3 {
            bail!(
                "{}",
                self.nodes[id]
                    .hierarchy_error
                    .as_deref()
                    .unwrap_or("Incomplete hierarchy")
            )
        }
        let result = (|| -> Result<BTreeSet<usize>> {
            ensure!(
                depth < 128 && states[id] != 1,
                "Circular or excessive class hierarchy"
            );
            ensure!(
                self.nodes[id].hierarchy_error.is_none(),
                "{}",
                self.nodes[id].hierarchy_error.as_deref().unwrap_or("")
            );
            states[id] = 1;
            let interface = self.nodes[id].access & 0x200 != 0;
            ensure!(
                !interface || self.nodes[id].access & 0x410 == 0x400,
                "Interface must be abstract and non-final"
            );
            let mut ancestors = BTreeSet::from([id]);
            if let Some(parent) = self.nodes[id].superclass {
                ensure!(
                    self.nodes[parent].access & (0x200 | 0x10) == 0,
                    "Superclass is an interface or final class"
                );
                ensure!(
                    !interface
                        || (self.nodes[parent].key.loader == "bootstrap"
                            && self.nodes[parent].key.name == "java/lang/Object"),
                    "Interface superclass must be bootstrap Object"
                );
                self.build_ancestors(parent, states, depth + 1)?;
                ancestors.extend(self.ancestors[parent].iter().copied());
            }
            let mut seen = BTreeSet::new();
            for parent in self.nodes[id].interfaces.clone() {
                ensure!(
                    seen.insert(parent) && self.nodes[parent].access & 0x200 != 0,
                    "Invalid or duplicate superinterface"
                );
                self.build_ancestors(parent, states, depth + 1)?;
                ancestors.extend(self.ancestors[parent].iter().copied());
            }
            Ok(ancestors)
        })();
        match result {
            Ok(ancestors) => {
                self.ancestors[id] = ancestors;
                states[id] = 2;
                Ok(())
            }
            Err(error) => {
                states[id] = 3;
                self.nodes[id].hierarchy_error = Some(format!("{error:#}"));
                Err(error)
            }
        }
    }
    pub fn lookup(&self, loader: &str, name: &str) -> Result<usize> {
        let id = lookup(&self.index, &self.packages, loader, name)
            .with_context(|| format!("Definition required: {name} from {loader}"))?;
        self.class_view(id)?;
        Ok(id)
    }
    pub fn find(&self, loader: &str, name: &str) -> Option<usize> {
        lookup(&self.index, &self.packages, loader, name)
    }
    pub fn key(&self, id: usize) -> Result<&ClassKey> {
        Ok(&self.nodes.get(id).context("Invalid nominal class ID")?.key)
    }
    pub fn declared_method_id(&self, member: &hierarchy::Member) -> Result<usize> {
        self.nodes
            .get(member.owner)
            .and_then(|n| n.method_ids.get(member.index))
            .copied()
            .context("Invalid method declaration identity")
    }
    pub fn same_package(&self, left: usize, right: usize) -> Result<bool> {
        let a = self.key(left)?;
        let b = self.key(right)?;
        Ok(a.loader == b.loader
            && a.name.rsplit_once('/').map(|p| p.0) == b.name.rsplit_once('/').map(|p| p.0))
    }
    fn nest_host(&self, id: usize) -> usize {
        let node = &self.nodes[id];
        let Some(name) = &node.nest_host else {
            return id;
        };
        let Some(candidate) = lookup(&self.index, &self.packages, &node.key.loader, name) else {
            return id;
        };
        if !self.same_package(id, candidate).unwrap_or(false) {
            return id;
        }
        if self.nodes[candidate]
            .nest_members
            .as_ref()
            .is_some_and(|m| m.contains(&node.key.name))
        {
            candidate
        } else {
            id
        }
    }
    pub fn accessible(
        &self,
        caller: usize,
        symbolic_owner: usize,
        member: &hierarchy::Member,
    ) -> Result<Option<usize>> {
        self.class_view(caller)?;
        self.class_view(symbolic_owner)?;
        let owner = member.owner;
        let flags = self.nodes[symbolic_owner].access;
        ensure!(
            flags & 1 != 0 || self.same_package(caller, symbolic_owner)?,
            "Class access requires a module/package check"
        );
        if member.access & 1 != 0 || caller == owner {
            return Ok(None);
        }
        if member.access & 2 != 0 {
            ensure!(
                self.same_package(caller, owner)?
                    && self.nest_host(caller) == self.nest_host(owner),
                "Private member is not in the caller's validated nest"
            );
            return Ok(None);
        }
        if self.same_package(caller, owner)? {
            return Ok(None);
        }
        ensure!(
            member.access & 4 != 0 && Metadata::assignable(self, caller, owner),
            "Member access is not permitted"
        );
        Ok((member.access & 8 == 0).then_some(caller))
    }
    pub(super) fn ancestors(&self, id: usize) -> Result<&BTreeSet<usize>> {
        self.class_view(id)?;
        Ok(&self.ancestors[id])
    }
    pub fn layouts(&self) -> Vec<Layout> {
        self.nodes
            .iter()
            .map(|node| {
                let layout = if node.access & (0x200 | 0x8000) == 0 {
                    Some(hierarchy::compact_layout(self, node.id))
                } else {
                    None
                };
                let (candidate, diagnostic) = match layout {
                    Some(Ok(layout)) => (Some(layout), None),
                    Some(Err(e)) => (None, Some(format!("{e:#}"))),
                    None => (None, node.hierarchy_error.clone()),
                };
                let mut static_fields = vec![];
                for (index, field) in node
                    .fields
                    .iter()
                    .enumerate()
                    .filter(|(_, f)| f.access & 8 != 0)
                {
                    if let Ok(storage_bytes) = hierarchy::storage_bytes(&field.descriptor) {
                        static_fields.push(StaticField {
                            declaring_field: index,
                            name: field.name.clone(),
                            descriptor: field.descriptor.clone(),
                            access: field.access,
                            storage_bytes,
                            reference: field.descriptor.starts_with(['L', '[']),
                        });
                    }
                }
                Layout {
                    class_id: node.id,
                    defining_loader: node.key.loader.clone(),
                    name: node.key.name.clone(),
                    source_sha256: node.origin.sha256.clone(),
                    candidate,
                    static_fields,
                    requires_vm_layout_contract: node.key.loader == "bootstrap"
                        && vm_owned(&node.key.name),
                    runtime_abi_verified: false,
                    diagnostic,
                }
            })
            .collect()
    }
}
impl Metadata for Catalog {
    fn class_view(&self, id: usize) -> Result<(&ClassKey, u16, Option<usize>, &[usize])> {
        let node = self.nodes.get(id).context("Invalid nominal class ID")?;
        ensure!(
            node.hierarchy_error.is_none(),
            "{}",
            node.hierarchy_error.as_deref().unwrap_or("")
        );
        Ok((&node.key, node.access, node.superclass, &node.interfaces))
    }
    fn methods(&self, id: usize) -> Result<&[Method]> {
        self.class_view(id)?;
        Ok(&self.nodes[id].methods)
    }
    fn fields(&self, id: usize) -> Result<&[Field]> {
        self.class_view(id)?;
        Ok(&self.nodes[id].fields)
    }
    fn assignable(&self, from: usize, to: usize) -> bool {
        self.ancestors.get(from).is_some_and(|a| a.contains(&to))
    }
    fn root_object(&self) -> Result<usize> {
        self.lookup("bootstrap", "java/lang/Object")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn header(id: usize, name: &str, parent: &str, loader: &str) -> Header {
        Header {
            schema: 1,
            class_id: id,
            origin: ClassOrigin {
                loader: loader.into(),
                binary_name: name.replace('/', "."),
                source_id: "fixture".into(),
                jar_entry: format!("{name}.class"),
                java_class_major: 65,
                sha256: "a".repeat(64),
                generated: None,
            },
            name: name.into(),
            access: 1,
            superclass: parent.into(),
            interfaces: vec![],
            fields: vec![],
            nest_host: None,
            nest_members: None,
            methods: vec![],
            diagnostic: None,
            constants: TypeMentions::default(),
        }
    }
    #[test]
    fn compact_layout_and_member_rules_are_shared_with_original_linker() {
        let mut base = header(1, "p/Base", "java/lang/Object", "vanilla-application");
        base.fields = vec![translation_ir::Field {
            name: "x".into(),
            descriptor: "I".into(),
            access: 1,
            constant_value: None,
        }];
        let mut child = header(2, "p/Child", "p/Base", "vanilla-application");
        child.fields = vec![translation_ir::Field {
            name: "ref".into(),
            descriptor: "Ljava/lang/Object;".into(),
            access: 1,
            constant_value: None,
        }];
        let catalog = Catalog::new(vec![
            header(0, "java/lang/Object", "", "bootstrap"),
            base,
            child,
        ])
        .unwrap();
        let field = hierarchy::resolve_field(&catalog, 2, "x", "I").unwrap();
        assert_eq!(field.owner, 1);
        let base = hierarchy::compact_layout(&catalog, 1).unwrap();
        let child = hierarchy::compact_layout(&catalog, 2).unwrap();
        assert_eq!(base.fields[0].offset, 0);
        assert_eq!(child.fields[1].offset, 8);
        assert!(Metadata::assignable(&catalog, 2, 1));
    }
    #[test]
    fn missing_and_circular_parents_do_not_become_object() {
        let catalog = Catalog::new(vec![
            header(0, "java/lang/Object", "", "bootstrap"),
            header(1, "p/A", "p/B", "vanilla-application"),
            header(2, "p/B", "p/A", "vanilla-application"),
            header(3, "p/Missing", "q/Absent", "vanilla-application"),
        ])
        .unwrap();
        for id in [1, 2, 3] {
            assert!(catalog.class_view(id).is_err());
            assert!(!Metadata::assignable(&catalog, id, 0));
        }
    }
}
