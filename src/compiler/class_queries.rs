//! VM-owned Class fields and native queries. Existing mirror ABIs stay unchanged.
use super::{classfile::ClassFile, jdk_bridges, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Kind {
    IsHidden,
    IsInstance,
    ComponentField,
    CanonicalName,
    SimpleName,
    ClassValueLoad,
    ClassValueStore,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub kind: Kind,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub origin: ClassOrigin,
}
pub(super) fn component_field(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == "java/lang/Class" && name == "componentType" && descriptor == "Ljava/lang/Class;"
}
pub const CLASS_VALUE_TYPE: &str = "java/lang/ClassValue$ClassValueMap";
pub(super) fn class_value_field(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == "java/lang/Class"
        && name == "classValueMap"
        && descriptor == "Ljava/lang/ClassValue$ClassValueMap;"
}
pub(super) fn class_value_descriptor(write: bool) -> &'static str {
    if write {
        "(Ljava/lang/Class;Ljava/lang/ClassValue$ClassValueMap;)V"
    } else {
        "(Ljava/lang/Class;)Ljava/lang/ClassValue$ClassValueMap;"
    }
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    kind: Kind,
) -> Result<Binding> {
    ensure!(
        source.binary_name == caller.name.replace('/', "."),
        "Class query caller identity changed"
    );
    let id = registry.class("bootstrap", "java/lang/Class")?;
    let types::Type::Class {
        key,
        origin,
        access,
        ..
    } = &registry.types[id]
    else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none()
            && access & 0x211 == 0x11,
        "Class queries require original final Class"
    );
    let origin = origin.as_ref().clone();
    let class = registry.definition(id).context("Missing original Class")?;
    match kind {
        Kind::ClassValueLoad | Kind::ClassValueStore => {
            let (owner, name, descriptor) = caller.field_reference(constant)?;
            ensure!(
                class_value_field(&owner, &name, &descriptor),
                "ClassValue field reference changed"
            );
            let field = class
                .field_info
                .iter()
                .find(|f| f.name == name && f.descriptor == descriptor)
                .context("Missing ClassValue field")?;
            ensure!(
                field.access == 0x80 && field.constant_value.is_none(),
                "ClassValue field access contract changed"
            );
            let caller_id = registry.class("bootstrap", "java/lang/ClassValue")?;
            let types::Type::Class {
                origin: expected, ..
            } = &registry.types[caller_id]
            else {
                unreachable!()
            };
            ensure!(
                caller.name == "java/lang/ClassValue"
                    && source == expected.as_ref()
                    && source.source_id == "jdk:java.base"
                    && source.generated.is_none(),
                "ClassValue field requires original package caller"
            );
            registry.class("bootstrap", CLASS_VALUE_TYPE)?;
        }
        Kind::CanonicalName | Kind::SimpleName => {
            let name = if kind == Kind::CanonicalName {
                "getCanonicalName"
            } else {
                "getSimpleName"
            };
            ensure!(
                caller.method_reference(constant)?
                    == (
                        "java/lang/Class".into(),
                        name.into(),
                        "()Ljava/lang/String;".into()
                    ),
                "Class name call changed"
            );
            let m = class.method(name, Some("()Ljava/lang/String;"))?;
            ensure!(
                m.access == 1 && m.code.is_some(),
                "Class name Java source changed"
            );
        }
        Kind::IsInstance => {
            ensure!(
                caller.method_reference(constant)?
                    == (
                        "java/lang/Class".into(),
                        "isInstance".into(),
                        "(Ljava/lang/Object;)Z".into()
                    ),
                "Class.isInstance call changed"
            );
            let method = class.method("isInstance", Some("(Ljava/lang/Object;)Z"))?;
            ensure!(
                method.access == 0x101 && method.code.is_none(),
                "Class.isInstance must be original public native"
            );
        }
        Kind::IsHidden => {
            ensure!(
                caller.method_reference(constant)?
                    == ("java/lang/Class".into(), "isHidden".into(), "()Z".into()),
                "Class.isHidden call changed"
            );
            let m = class.method("isHidden", Some("()Z"))?;
            ensure!(
                m.access == 0x101 && m.code.is_none(),
                "Class.isHidden must be original public native"
            );
        }
        Kind::ComponentField => {
            let (o, n, d) = caller.field_reference(constant)?;
            ensure!(
                component_field(&o, &n, &d),
                "Class component field reference changed"
            );
            jdk_bridges::validate(caller, source)?;
            let g = source
                .generated
                .as_ref()
                .context("Private Class field needs original Code bridge")?;
            ensure!(
                matches!(g.site, 7 | 8)
                    && g.host_class == "java/lang/Class"
                    && g.host_sha256 == origin.sha256,
                "Class component field requires original descriptor/component method Code"
            );
            let f = class
                .field_info
                .iter()
                .find(|f| f.name == n && f.descriptor == d)
                .context("Missing Class component field")?;
            ensure!(
                f.access == 0x12 && f.constant_value.is_none(),
                "Class component field must be private final"
            );
        }
    }
    Ok(Binding {
        abi: 1,
        kind,
        caller: source.clone(),
        constant,
        origin,
    })
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub type_count: usize,
    pub nominal_definitions_only: bool,
    pub bindings: Vec<Binding>,
    pub native_source_sha256: String,
    pub mirror_source_sha256: String,
    pub heap_abi: u32,
    pub heap_source_sha256: String,
    pub names: Option<Names>,
    pub class_value_map: Option<ClassValueMap>,
}
impl Plan {
    pub(super) fn new(bindings: Vec<Binding>, types: &[types::Type]) -> Result<Self> {
        ensure!(
            !bindings.is_empty() && !types.is_empty() && types.len() <= 65536,
            "Invalid Class query metadata"
        );
        // The current registry contains nominal class definitions only. Generated
        // lambda holders are ordinary named classes; defineHiddenClass is gated.
        // A future hidden-class registry must change this profile/ABI explicitly.
        for t in types {
            if let types::Type::Class { origin, .. } = t
                && let Some(g) = &origin.generated
            {
                ensure!(
                    g.abi == 1
                        && matches!(
                            g.generator.as_str(),
                            "boom-lambda" | "boom-jdk-bridge" | "boom-record"
                        ),
                    "Unknown generated Class definition kind"
                );
            }
        }
        let class_value_map = if bindings
            .iter()
            .any(|b| matches!(b.kind, Kind::ClassValueLoad | Kind::ClassValueStore))
        {
            Some(ClassValueMap { abi:1,value_type:types.iter().position(|t|matches!(t,types::Type::Class { key,.. } if key.loader=="bootstrap" && key.name==CLASS_VALUE_TYPE)).context("Missing ClassValueMap type")? })
        } else {
            None
        };
        Ok(Self {
            abi: 1,
            type_count: types.len(),
            nominal_definitions_only: true,
            bindings,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/class_queries.asm"
            ))
            .sha256,
            mirror_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/mirrors.asm"
            ))
            .sha256,
            heap_abi: 1,
            heap_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/heap.asm"
            ))
            .sha256,
            names: None,
            class_value_map,
        })
    }
    pub(super) fn emit(&self, out: &mut String) {
        if let Some(plan) = &self.class_value_map {
            out.push_str(&format!("EXTERN boom_class_value_field:PROC\nEXTERN boom_runtime_type:PROC\nEXTERN boom_type_assignable:PROC\n.const\nALIGN 8\nboom_class_value_pool DWORD 04356414Ch,1,{},0\n    QWORD OFFSET boom_mirror_pool,OFFSET boom_class_value_roots,OFFSET boom_runtime_type_map,OFFSET boom_t{},OFFSET boom_runtime_type,OFFSET boom_type_assignable\n.code\nPUBLIC boom_get_class_value_pool\nboom_get_class_value_pool PROC\n    lea rax,boom_class_value_pool\n    ret\nboom_get_class_value_pool ENDP\n",self.type_count,plan.value_type));
        }
        if let Some(names) = &self.names {
            out.push_str(&format!("EXTERN boom_class_name:PROC\n.const\nALIGN 8\nboom_class_name_pool DWORD 0434C4E4Dh,2,{},0\n    QWORD OFFSET boom_mirror_pool,OFFSET boom_string_pool,OFFSET boom_class_name_rows,OFFSET boom_class_name_roots,OFFSET boom_class_name_locks,0\nboom_class_name_rows LABEL DWORD\n",self.type_count));
            for row in &names.rows {
                out.push_str(&format!(
                    "    DWORD {},{},{},0\n",
                    row.canonical.unwrap_or(u32::MAX as usize),
                    row.simple,
                    u32::from(row.fresh_canonical) | (u32::from(row.fresh_simple) << 1)
                ));
            }
            out.push_str(&format!(".data\nALIGN 4\nboom_class_name_locks DWORD {} DUP(0)\n.code\nPUBLIC boom_get_class_name_pool\nboom_get_class_name_pool PROC\n    lea rax,boom_class_name_pool\n    ret\nboom_get_class_name_pool ENDP\n",self.type_count*2));
        }
        if self.bindings.iter().any(|b| b.kind == Kind::IsInstance) {
            out.push_str("EXTERN boom_class_is_instance:PROC\n");
        }
        out.push_str(&format!("EXTERN boom_class_is_hidden:PROC\n.const\nALIGN 8\nboom_class_query_pool DWORD 0434C5152h, 1, {}, 1\n    QWORD OFFSET boom_mirror_pool, 0\n.code\nPUBLIC boom_get_class_query_pool\nboom_get_class_query_pool PROC\n    lea rax, boom_class_query_pool\n    ret\nboom_get_class_query_pool ENDP\n",self.type_count));
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClassValueMap {
    pub abi: u32,
    pub value_type: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NameRow {
    pub canonical: Option<usize>,
    pub simple: usize,
    pub origin: Option<ClassOrigin>,
    pub declaring_type: Option<usize>,
    pub local_or_anonymous: bool,
    pub fresh_canonical: bool,
    pub fresh_simple: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Names {
    pub abi: u32,
    pub rows: Vec<NameRow>,
    pub original_java_name_bodies_executed: bool,
}
pub(super) fn prepare_names(
    registry: &mut types::Registry<'_>,
    mut intern: impl FnMut(Vec<u16>) -> Result<usize>,
) -> Result<Names> {
    // Resolve the declaring chain before freezing mirror/type/literal tables.
    let mut parents = Vec::new();
    let mut id = 0;
    while id < registry.types.len() {
        let parent = match &registry.types[id] {
            types::Type::Class { key, .. } => registry
                .definition(id)
                .and_then(|c| c.declaring_class.clone())
                .map(|name| (key.loader.clone(), name)),
            _ => None,
        };
        parents.push(
            parent
                .map(|(loader, name)| registry.class(&loader, &name))
                .transpose()?,
        );
        ensure!(
            registry.types.len() <= 65536,
            "Class name metadata limit exceeded"
        );
        id += 1;
    }
    fn names(
        id: usize,
        registry: &types::Registry<'_>,
        parents: &[Option<usize>],
        memo: &mut [Option<(Option<String>, String)>],
        active: &mut std::collections::BTreeSet<usize>,
    ) -> Result<(Option<String>, String)> {
        if let Some(value) = &memo[id] {
            return Ok(value.clone());
        }
        ensure!(
            active.insert(id),
            "Cyclic Class declaring/component metadata"
        );
        let value = match &registry.types[id] {
            types::Type::Primitive { .. } => {
                let name = super::mirrors::name(&registry.types, id);
                (Some(name.clone()), name)
            }
            types::Type::Array { component } => {
                let (canonical, simple) = names(*component, registry, parents, memo, active)?;
                (canonical.map(|s| format!("{s}[]")), format!("{simple}[]"))
            }
            types::Type::Class { key, .. } => {
                let c = registry
                    .definition(id)
                    .context("Missing Class name declaration")?;
                let simple = if c.inner_class_entry {
                    c.inner_simple_name.clone().unwrap_or_default()
                } else {
                    key.name.rsplit('/').next().unwrap().to_owned()
                };
                let canonical = if c.enclosing_class.is_some()
                    || (c.inner_class_entry && c.inner_simple_name.is_none())
                {
                    None
                } else if let Some(parent) = parents[id] {
                    names(parent, registry, parents, memo, active)?
                        .0
                        .map(|p| format!("{p}.{simple}"))
                } else {
                    Some(key.name.replace('/', "."))
                };
                (canonical, simple)
            }
        };
        active.remove(&id);
        memo[id] = Some(value.clone());
        Ok(value)
    }
    let mut memo = vec![None; registry.types.len()];
    let mut rows = Vec::new();
    for id in 0..registry.types.len() {
        let (canonical, simple) =
            names(id, registry, &parents, &mut memo, &mut Default::default())?;
        rows.push(NameRow {
            fresh_canonical: canonical.is_some()
                && (parents[id].is_some()
                    || matches!(&registry.types[id], types::Type::Array { .. })),
            fresh_simple: !simple.is_empty()
                && match &registry.types[id] {
                    types::Type::Primitive { .. } => false,
                    types::Type::Array { .. } => true,
                    types::Type::Class { key, .. } => {
                        registry.definition(id).unwrap().inner_class_entry || key.name.contains('/')
                    }
                },
            canonical: canonical
                .map(|s| intern(s.encode_utf16().collect()))
                .transpose()?,
            simple: intern(simple.encode_utf16().collect())?,
            origin: match &registry.types[id] {
                types::Type::Class { origin, .. } => Some(origin.as_ref().clone()),
                _ => None,
            },
            declaring_type: parents[id],
            local_or_anonymous: registry.definition(id).is_some_and(|c| {
                c.enclosing_class.is_some()
                    || (c.inner_class_entry && c.inner_simple_name.is_none())
            }),
        });
    }
    Ok(Names {
        abi: 2,
        rows,
        original_java_name_bodies_executed: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bytecode::GeneratedOrigin;
    #[test]
    fn nominal_query_profile_rejects_unknown_definition_kinds_and_generator_abis() {
        let origin = ClassOrigin {
            loader: "explicit-application".into(),
            binary_name: "p.C".into(),
            source_id: "fixture".into(),
            jar_entry: "p/C.class".into(),
            java_class_major: 65,
            sha256: "fixture".into(),
            generated: None,
        };
        let binding = Binding {
            abi: 1,
            kind: Kind::IsHidden,
            caller: origin.clone(),
            constant: 1,
            origin: origin.clone(),
        };
        let mut ty = types::Type::Class {
            key: types::ClassKey {
                loader: "explicit-application".into(),
                name: "p/C".into(),
            },
            origin: Box::new(origin),
            access: 0x11,
            superclass: None,
            interfaces: vec![],
        };
        assert_eq!(
            Plan::new(vec![binding.clone()], std::slice::from_ref(&ty))
                .unwrap()
                .type_count,
            1
        );
        for (name, abi) in [
            ("boom-lambda", 1),
            ("boom-jdk-bridge", 1),
            ("boom-hidden-class", 1),
            ("boom-lambda", 2),
        ] {
            let types::Type::Class { origin, .. } = &mut ty else {
                unreachable!()
            };
            origin.generated = Some(Box::new(GeneratedOrigin {
                generator: name.into(),
                abi,
                host_loader: "explicit-application".into(),
                host_class: "p/Host".into(),
                host_source_id: "fixture".into(),
                host_sha256: "fixture".into(),
                site: 1,
            }));
            assert_eq!(
                Plan::new(vec![binding.clone()], std::slice::from_ref(&ty)).is_ok(),
                abi == 1 && name != "boom-hidden-class"
            );
        }
        assert!(Plan::new(vec![binding], &[]).is_err());
    }
}
