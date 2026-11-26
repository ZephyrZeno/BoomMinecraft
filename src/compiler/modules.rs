//! Closed classpath module identities; all guest operations execute in MASM.
use super::{classfile::ClassFile, numeric, types};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fmt::Write};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Operation {
    ClassGetModule,
    GetName,
    IsNamed,
    GetLayer,
    LayerBoot,
    LayerEmpty,
    LayerFindModule,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, descriptor: &str) -> Result<Option<Self>> {
        Ok(match (owner, name, descriptor) {
            ("java/lang/Class", "getModule", "()Ljava/lang/Module;") => Some(Self::ClassGetModule),
            ("java/lang/Module", "getName", "()Ljava/lang/String;") => Some(Self::GetName),
            ("java/lang/Module", "isNamed", "()Z") => Some(Self::IsNamed),
            ("java/lang/Module", "getLayer", "()Ljava/lang/ModuleLayer;") => Some(Self::GetLayer),
            ("java/lang/ModuleLayer", "boot", "()Ljava/lang/ModuleLayer;") => Some(Self::LayerBoot),
            ("java/lang/ModuleLayer", "empty", "()Ljava/lang/ModuleLayer;") => {
                Some(Self::LayerEmpty)
            }
            ("java/lang/ModuleLayer", "findModule", "(Ljava/lang/String;)Ljava/util/Optional;") => {
                Some(Self::LayerFindModule)
            }
            // Keep this original Java wrapper on the ordinary backend path.
            // Its package access and Unsafe dependencies are checked normally;
            // accepting the wrapper does not implement the underlying atomics.
            ("java/lang/Module", "implAddEnableNativeAccess", "()Ljava/lang/Module;") => None,
            ("java/lang/Module" | "java/lang/ModuleLayer", _, _) => {
                bail!(
                    "Module operation {name}{descriptor} requires further module runtime integration"
                )
            }
            _ => None,
        })
    }
    fn member(self) -> (&'static str, &'static str, &'static str) {
        match self {
            Self::ClassGetModule => ("java/lang/Class", "getModule", "()Ljava/lang/Module;"),
            Self::GetName => ("java/lang/Module", "getName", "()Ljava/lang/String;"),
            Self::IsNamed => ("java/lang/Module", "isNamed", "()Z"),
            Self::GetLayer => ("java/lang/Module", "getLayer", "()Ljava/lang/ModuleLayer;"),
            Self::LayerBoot => ("java/lang/ModuleLayer", "boot", "()Ljava/lang/ModuleLayer;"),
            Self::LayerEmpty => (
                "java/lang/ModuleLayer",
                "empty",
                "()Ljava/lang/ModuleLayer;",
            ),
            Self::LayerFindModule => (
                "java/lang/ModuleLayer",
                "findModule",
                "(Ljava/lang/String;)Ljava/util/Optional;",
            ),
        }
    }
    pub(super) fn is_static(self) -> bool {
        matches!(self, Self::LayerBoot | Self::LayerEmpty)
    }
    pub(super) fn uses_layer(self) -> bool {
        self as u32 >= Self::GetLayer as u32
    }
    pub(super) fn signature(
        self,
        module_type: numeric::Type,
        layer_type: numeric::Type,
        optional_type: numeric::Type,
    ) -> numeric::Signature {
        use numeric::Type as T;
        numeric::Signature {
            arguments: match self {
                Self::ClassGetModule => vec![T::BootstrapClass],
                Self::LayerBoot | Self::LayerEmpty => vec![],
                Self::LayerFindModule => vec![layer_type, T::BootstrapString],
                _ => vec![module_type],
            },
            result: match self {
                Self::ClassGetModule => module_type,
                Self::GetName => T::BootstrapString,
                Self::IsNamed => T::I32,
                Self::GetLayer | Self::LayerBoot | Self::LayerEmpty => layer_type,
                Self::LayerFindModule => optional_type,
            },
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub operation: Operation,
    pub origin: ClassOrigin,
}
fn verify_member(ty: &types::Type, class: &ClassFile, op: Operation) -> Result<ClassOrigin> {
    let (owner, name, descriptor) = op.member();
    let types::Type::Class {
        key,
        origin,
        access,
        ..
    } = ty
    else {
        bail!("Module service owner is not a class")
    };
    ensure!(
        key.loader == "bootstrap"
            && key.name == owner
            && origin.source_id == "jdk:java.base"
            && access & 0x211 == 0x11,
        "Module service requires the pinned final bootstrap class {owner}"
    );
    let method = class.method(name, Some(descriptor))?;
    ensure!(
        method.access & (1 | 8 | 0x20 | 0x100 | 0x400) == (1 | if op.is_static() { 8 } else { 0 })
            && method.code.is_some(),
        "Module service must match the public Java method {owner}.{name}{descriptor} with its static/instance contract"
    );
    Ok(origin.as_ref().clone())
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    op: Operation,
) -> Result<(Binding, numeric::Signature)> {
    let (owner, _, _) = op.member();
    let id = registry.class("bootstrap", owner)?;
    let origin = verify_member(
        &registry.types[id],
        registry
            .definition(id)
            .context("Missing module service definition")?,
        op,
    )?;
    let module_type = registry.class("bootstrap", "java/lang/Module")?;
    // Class is used to validate runtime mirror identity even by Module-only entries.
    registry.class("bootstrap", "java/lang/Class")?;
    registry.class("bootstrap", "java/lang/String")?;
    let layer_type = if op.uses_layer() {
        numeric::Type::MetadataReference(registry.class("bootstrap", "java/lang/ModuleLayer")?)
    } else {
        numeric::Type::Void
    };
    let optional_type = if op == Operation::LayerFindModule {
        numeric::Type::MetadataReference(registry.class("bootstrap", "java/util/Optional")?)
    } else {
        numeric::Type::Void
    };
    Ok((
        Binding {
            operation: op,
            origin,
        },
        op.signature(
            numeric::Type::MetadataReference(module_type),
            layer_type,
            optional_type,
        ),
    ))
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Identity {
    pub defining_loader: String,
    pub name: Option<String>,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub identities: Vec<Identity>,
    pub type_modules: Vec<usize>,
    pub bindings: Vec<Binding>,
    pub base_name_literal: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub boot: Option<Boot>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub objects: Option<super::module_objects::Plan>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub object_loader_keys: Vec<usize>,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Boot {
    pub snapshot_fingerprint: String,
    pub graph: crate::boot_modules::Graph,
    pub name_literals: Vec<Option<usize>>,
    pub named_modules: BTreeMap<String, usize>,
}
impl Plan {
    pub(super) fn prepare(
        types: &[types::Type],
        bindings: Vec<Binding>,
        base_name_literal: usize,
    ) -> Result<Self> {
        fn identity(types: &[types::Type], id: usize, depth: usize) -> Result<Identity> {
            ensure!(depth < 256, "Module component nesting exceeds budget");
            Ok(
                match types.get(id).context("Invalid module component identity")? {
                    types::Type::Primitive { .. } => Identity {
                        defining_loader: "bootstrap".into(),
                        name: Some("java.base".into()),
                    },
                    types::Type::Array { component } => identity(types, *component, depth + 1)?,
                    types::Type::Class { key, origin, .. } => {
                        ensure!(
                            key.loader == origin.loader,
                            "Module defining loader disagrees with class origin"
                        );
                        if key.loader == "bootstrap" {
                            ensure!(
                                origin.source_id == "jdk:java.base"
                                    || origin
                                        .generated
                                        .as_ref()
                                        .is_some_and(|proof| proof.host_source_id
                                            == "jdk:java.base"
                                            && proof.host_loader == key.loader),
                                "Other named module providers are not implemented"
                            );
                            Identity {
                                defining_loader: key.loader.clone(),
                                name: Some("java.base".into()),
                            }
                        } else {
                            ensure!(
                                !origin.source_id.starts_with("jdk:"),
                                "JDK module cannot be assigned to an application unnamed module"
                            );
                            Identity {
                                defining_loader: key.loader.clone(),
                                name: None,
                            }
                        }
                    }
                },
            )
        }
        let base = Identity {
            defining_loader: "bootstrap".into(),
            name: Some("java.base".into()),
        };
        let mut identities = vec![base.clone()];
        let mut ids = BTreeMap::from([(base, 0)]);
        let mut type_modules = Vec::new();
        for id in 0..types.len() {
            let key = identity(types, id, 0)?;
            let next = identities.len();
            if !ids.contains_key(&key) {
                identities.push(key.clone());
            }
            type_modules.push(*ids.entry(key).or_insert(next));
        }
        ensure!(
            !types.is_empty() && types.len() <= 16384 && identities.len() <= 1024,
            "Module metadata exceeds runtime budget"
        );
        Ok(Self {
            abi: 1,
            identities,
            type_modules,
            bindings,
            base_name_literal,
            boot: None,
            objects: None,
            object_loader_keys: Vec::new(),
        })
    }
    pub(super) fn attach_boot(
        &mut self,
        snapshot: &crate::boot_modules::Snapshot,
        application_loader: &str,
        intern: &mut dyn FnMut(&str) -> Result<usize>,
    ) -> Result<()> {
        ensure!(self.boot.is_none(), "Boot graph attached more than once");
        let mut named_modules = BTreeMap::new();
        for (name, resolved) in &snapshot.graph.resolved {
            let defining_loader = match resolved.loader {
                crate::boot_modules::Loader::Bootstrap => "bootstrap",
                crate::boot_modules::Loader::Platform => "platform",
                crate::boot_modules::Loader::Application => application_loader,
            };
            let identity = Identity {
                defining_loader: defining_loader.into(),
                name: Some(name.clone()),
            };
            let id = if let Some(id) = self.identities.iter().position(|i| *i == identity) {
                id
            } else {
                self.identities.push(identity);
                self.identities.len() - 1
            };
            named_modules.insert(name.clone(), id);
        }
        ensure!(
            self.identities.len() <= 1024 && named_modules.get("java.base") == Some(&0),
            "Invalid boot module identity table"
        );
        let name_literals = self
            .identities
            .iter()
            .map(|i| i.name.as_deref().map(&mut *intern).transpose())
            .collect::<Result<Vec<_>>>()?;
        self.boot = Some(Boot {
            snapshot_fingerprint: snapshot.fingerprint.clone(),
            graph: snapshot.graph.clone(),
            name_literals,
            named_modules,
        });
        self.abi = 2;
        Ok(())
    }
    pub(super) fn emit(&self, assembly: &mut String) -> Result<()> {
        if self.objects.is_some() {
            return self.emit_objects(assembly);
        }
        assembly.push_str("\nEXTERN boom_module_intrinsic:PROC\n.const\nALIGN 8\nboom_module_layout DWORD 04F424A43h, 1\n    QWORD 8\n    DWORD 0, 1\nboom_module_rows LABEL DWORD\n");
        for (id, identity) in self.identities.iter().enumerate() {
            writeln!(
                assembly,
                "    DWORD {}, {}",
                if identity.name.is_some() {
                    self.boot
                        .as_ref()
                        .map_or(self.base_name_literal, |b| b.name_literals[id].unwrap())
                } else {
                    u32::MAX as usize
                },
                u32::from(identity.name.is_some())
            )?;
        }
        assembly.push_str("boom_module_membership LABEL DWORD\n");
        for id in &self.type_modules {
            writeln!(assembly, "    DWORD {id}")?;
        }
        writeln!(
            assembly,
            ".data\nALIGN 8\nboom_module_pool DWORD 04D4F4455h, {}, 0, {}\n    QWORD OFFSET boom_module_roots, OFFSET boom_module_rows, OFFSET boom_module_layout, OFFSET boom_string_pool, 0, OFFSET boom_mirror_pool\n    DWORD {}, 0\n    QWORD OFFSET boom_module_membership",
            self.abi,
            self.identities.len(),
            self.type_modules.len()
        )?;
        if self.boot.is_some() {
            assembly.push_str("    QWORD OFFSET boom_layer_pool, OFFSET boom_heap_ptr\n.const\nALIGN 8\nboom_layer_layout DWORD 04F424A43h, 1\n    QWORD 8\n    DWORD 0, 1\n.data\nALIGN 8\nboom_layer_pool DWORD 04C415952h, 1, 0, 2\n    QWORD OFFSET boom_layer_roots, OFFSET boom_layer_layout, OFFSET boom_module_pool, OFFSET boom_heap_ptr, 0, 0\nEXTERN boom_layer_intrinsic:PROC\n");
        }
        assembly.push_str(".code\n");
        Ok(())
    }
    fn emit_objects(&self, out: &mut String) -> Result<()> {
        let p = self.objects.as_ref().unwrap();
        ensure!(
            self.abi == 3 && self.object_loader_keys.len() == self.identities.len(),
            "Physical module loader table is not frozen"
        );
        out.push_str("EXTERN boom_module_intrinsic:PROC\nEXTERN boom_module_objects_pool_valid:PROC\nEXTERN boom_module_objects_index:PROC\nEXTERN boom_module_objects_load:PROC\nEXTERN boom_module_objects_intrinsic:PROC\n.const\nALIGN 8\nboom_module_rows LABEL DWORD\n");
        for (id, identity) in self.identities.iter().enumerate() {
            let name = if identity.name.is_some() {
                self.boot
                    .as_ref()
                    .map_or(self.base_name_literal, |b| b.name_literals[id].unwrap())
            } else {
                u32::MAX as usize
            };
            writeln!(
                out,
                "    DWORD {name},{}",
                u32::from(identity.name.is_some())
            )?;
        }
        out.push_str("boom_module_membership LABEL DWORD\n");
        for id in &self.type_modules {
            writeln!(out, "    DWORD {id}")?;
        }
        out.push_str("boom_module_loader_keys LABEL DWORD\n");
        for id in &self.object_loader_keys {
            writeln!(out, "    DWORD {id}")?;
        }
        writeln!(
            out,
            ".data\nALIGN 8\nboom_module_pool DWORD 04D4F4455h,3,0,{}\n    QWORD OFFSET boom_module_roots,OFFSET boom_module_rows,OFFSET boom_layout{},OFFSET boom_string_pool,0,OFFSET boom_mirror_pool\n    DWORD {},0\n    QWORD OFFSET boom_module_membership\n    QWORD {},OFFSET boom_heap_ptr,OFFSET boom_loader_pool,OFFSET boom_module_loader_keys\n    DWORD {},{},{},{},{},0\n    QWORD 0",
            self.identities.len(),
            p.class_id,
            self.type_modules.len(),
            if self.boot.is_some() {
                "OFFSET boom_layer_pool"
            } else {
                "0"
            },
            p.name_offset,
            p.loader_offset,
            p.layer_offset,
            p.loader_unnamed_offset,
            p.descriptor_offset
        )?;
        if self.boot.is_some() {
            out.push_str(".const\nALIGN 8\nboom_layer_layout DWORD 04F424A43h,1\n    QWORD 8\n    DWORD 0,1\n.data\nALIGN 8\nboom_layer_pool DWORD 04C415952h,1,0,2\n    QWORD OFFSET boom_layer_roots,OFFSET boom_layer_layout,OFFSET boom_module_pool,OFFSET boom_heap_ptr,0,0\nEXTERN boom_layer_intrinsic:PROC\n");
        }
        out.push_str(".code\nPUBLIC boom_get_module_pool\nboom_get_module_pool PROC\n    lea rax,boom_module_pool\n    ret\nboom_get_module_pool ENDP\n");
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn class(loader: &str, source: &str) -> types::Type {
        types::Type::Class {
            key: types::ClassKey {
                loader: loader.into(),
                name: "p/T".into(),
            },
            origin: Box::new(ClassOrigin {
                generated: None,
                loader: loader.into(),
                binary_name: "p.T".into(),
                source_id: source.into(),
                jar_entry: "p/T.class".into(),
                java_class_major: 65,
                sha256: "fixture".into(),
            }),
            access: 0x11,
            superclass: None,
            interfaces: vec![],
        }
    }
    #[test]
    fn membership_preserves_component_and_defining_loader_identity() {
        let mut types = vec![
            class("bootstrap", "jdk:java.base"),
            class("app-a", "jar-a"),
            class("app-b", "jar-a"),
            class("app-a", "jar-b"),
            types::Type::Primitive {
                value: types::Primitive::Int,
            },
        ];
        types.extend([
            types::Type::Array { component: 1 },
            types::Type::Array { component: 5 },
            types::Type::Array { component: 4 },
        ]);
        let p = Plan::prepare(&types, vec![], 31).unwrap();
        assert_eq!(p.type_modules, vec![0, 1, 2, 1, 0, 1, 1, 0]);
        assert_eq!(p.identities.len(), 3);
        let mut assembly = String::new();
        p.emit(&mut assembly).unwrap();
        assert!(assembly.contains("DWORD 31, 1\n    DWORD 4294967295, 0"));
        assert!(Plan::prepare(&[class("bootstrap", "jdk:jdk.jfr")], vec![], 0).is_err());
        assert!(Plan::prepare(&[class("app-a", "jdk:java.base")], vec![], 0).is_err());
        assert!(Plan::prepare(&[types::Type::Array { component: 0 }], vec![], 0).is_err());
        assert!(Plan::prepare(&[types::Type::Array { component: 4 }], vec![], 0).is_err());
    }
    #[test]
    fn operations_require_exact_signatures_and_preserve_reference_types() {
        assert_eq!(
            Operation::resolve("java/lang/Class", "getModule", "()Ljava/lang/Module;").unwrap(),
            Some(Operation::ClassGetModule)
        );
        assert!(
            Operation::resolve("java/lang/Class", "getModule", "()Ljava/lang/Object;")
                .unwrap()
                .is_none()
        );
        assert!(
            Operation::resolve("p/Module", "isNamed", "()Z")
                .unwrap()
                .is_none()
        );
        assert!(
            Operation::resolve(
                "java/lang/Module",
                "getDescriptor",
                "()Ljava/lang/module/ModuleDescriptor;"
            )
            .is_err()
        );
        let ty = numeric::Type::MetadataReference(23);
        assert_eq!(Operation::ClassGetModule.signature(ty, ty, ty).result, ty);
        assert_eq!(Operation::GetName.signature(ty, ty, ty).arguments, vec![ty]);
        assert_eq!(
            Operation::GetName.signature(ty, ty, ty).result,
            numeric::Type::BootstrapString
        );
    }
    #[test]
    fn binding_rejects_altered_method_contract_or_untrusted_origin() {
        fn definition(access: u16) -> ClassFile {
            let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 8];
            fn utf(b: &mut Vec<u8>, s: &str) {
                b.push(1);
                b.extend((s.len() as u16).to_be_bytes());
                b.extend(s.as_bytes());
            }
            utf(&mut b, "java/lang/Module");
            b.extend([7, 0, 1]);
            utf(&mut b, "java/lang/Object");
            b.extend([7, 0, 3]);
            for s in ["getName", "()Ljava/lang/String;", "Code"] {
                utf(&mut b, s);
            }
            for v in [
                0x31u16,
                2,
                4,
                0,
                0,
                1,
                access,
                5,
                6,
                if access & 0x500 == 0 { 1 } else { 0 },
            ] {
                b.extend(v.to_be_bytes());
            }
            if access & 0x500 == 0 {
                b.extend([0, 7]);
                b.extend(14u32.to_be_bytes());
                b.extend([0, 1, 0, 1, 0, 0, 0, 2, 1, 0xb0, 0, 0, 0, 0]);
            }
            b.extend([0, 0]);
            ClassFile::parse(&b).unwrap()
        }
        let mut ty = class("bootstrap", "jdk:java.base");
        if let types::Type::Class { key, origin, .. } = &mut ty {
            key.name = "java/lang/Module".into();
            origin.binary_name = "java.lang.Module".into();
        }
        assert!(verify_member(&ty, &definition(1), Operation::GetName).is_ok());
        for flags in [9, 0x21, 0x101, 0x401] {
            assert!(verify_member(&ty, &definition(flags), Operation::GetName).is_err());
        }
        if let types::Type::Class { origin, .. } = &mut ty {
            origin.source_id = "app:lookalike".into();
        }
        assert!(verify_member(&ty, &definition(1), Operation::GetName).is_err());
    }
}
