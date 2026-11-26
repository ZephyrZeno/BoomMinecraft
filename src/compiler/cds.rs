//! A frozen no-CDS runtime profile. Original Java initializers still execute.
use super::{classfile::ClassFile, numeric, types};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

pub const OWNER: &str = "jdk/internal/misc/CDS";
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum Operation {
    InitializeFromArchive = 0,
    IsDumpingClassList = 1,
    IsDumpingArchive = 2,
    IsSharingEnabled = 3,
    GetRandomSeedForDumping = 4,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, descriptor: &str) -> Option<Self> {
        if owner != OWNER {
            return None;
        }
        [
            Self::InitializeFromArchive,
            Self::IsDumpingClassList,
            Self::IsDumpingArchive,
            Self::IsSharingEnabled,
            Self::GetRandomSeedForDumping,
        ]
        .into_iter()
        .find(|op| op.name() == name && op.descriptor() == descriptor)
    }
    pub(super) fn name(self) -> &'static str {
        match self {
            Self::InitializeFromArchive => "initializeFromArchive",
            Self::IsDumpingClassList => "isDumpingClassList0",
            Self::IsDumpingArchive => "isDumpingArchive0",
            Self::IsSharingEnabled => "isSharingEnabled0",
            Self::GetRandomSeedForDumping => "getRandomSeedForDumping",
        }
    }
    pub(super) fn descriptor(self) -> &'static str {
        match self {
            Self::InitializeFromArchive => "(Ljava/lang/Class;)V",
            Self::GetRandomSeedForDumping => "()J",
            _ => "()Z",
        }
    }
    fn private(self) -> bool {
        !matches!(
            self,
            Self::InitializeFromArchive | Self::GetRandomSeedForDumping
        )
    }
    pub(super) fn code(self) -> u32 {
        self as u32
    }
    pub(super) fn signature(self) -> numeric::Signature {
        use numeric::{Signature, Type};
        Signature {
            arguments: if self == Self::InitializeFromArchive {
                vec![Type::BootstrapClass]
            } else {
                vec![]
            },
            result: match self {
                Self::InitializeFromArchive => Type::Void,
                Self::GetRandomSeedForDumping => Type::I64,
                _ => Type::I32,
            },
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub operation: Operation,
    pub origin: ClassOrigin,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub class_id: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub shared_archive_mapped: bool,
    pub dumping_archive: bool,
    pub dumping_class_list: bool,
    pub bindings: Vec<Binding>,
}
impl Plan {
    pub(super) fn no_archive(bindings: Vec<Binding>) -> Option<Self> {
        (!bindings.is_empty()).then_some(Self {
            abi: 1,
            shared_archive_mapped: false,
            dumping_archive: false,
            dumping_class_list: false,
            bindings,
        })
    }
    pub(super) fn emit(&self, assembly: &mut String) -> Result<()> {
        ensure!(
            self.abi == 1
                && !self.shared_archive_mapped
                && !self.dumping_archive
                && !self.dumping_class_list
                && !self.bindings.is_empty(),
            "Unsupported CDS profile"
        );
        assembly.push_str("EXTERN boom_cds_service:PROC\n.const\nALIGN 8\nboom_cds_profile DWORD 043445350h, 1, 0, 0\n    QWORD OFFSET boom_mirror_pool, 0\n.code\n");
        Ok(())
    }
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    operation: Operation,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    class_id: usize,
) -> Result<Binding> {
    let id = registry.class("bootstrap", OWNER)?;
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
            && access & 0x601 == 1,
        "CDS binding requires the original public bootstrap java.base class"
    );
    let origin = origin.as_ref().clone();
    let method = registry
        .definition(id)
        .context("Missing CDS definition")?
        .method(operation.name(), Some(operation.descriptor()))?;
    ensure!(
        method.access == if operation.private() { 0x10a } else { 0x109 } && method.code.is_none(),
        "CDS native member contract changed"
    );
    if operation.private() {
        ensure!(
            caller.name == OWNER && source == &origin,
            "CDS private native query requires its original bootstrap caller"
        );
    }
    Ok(Binding {
        operation,
        origin,
        caller: source.clone(),
        constant,
        class_id,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Provider {
        operation: Operation,
        access: u16,
        loader: &'static str,
    }
    impl types::TypeProvider for Provider {
        fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 7];
            fn utf(b: &mut Vec<u8>, s: &str) {
                b.push(1);
                b.extend((s.len() as u16).to_be_bytes());
                b.extend(s.as_bytes());
            }
            utf(&mut b, name);
            b.extend([7, 0, 1]);
            utf(&mut b, "java/lang/Object");
            b.extend([7, 0, 3]);
            utf(&mut b, self.operation.name());
            utf(&mut b, self.operation.descriptor());
            let owner = name == OWNER;
            for n in [
                0x21u16,
                2,
                if name == "java/lang/Object" { 0 } else { 4 },
                0,
                0,
                u16::from(owner),
            ] {
                b.extend(n.to_be_bytes());
            }
            if owner {
                for n in [self.access, 5, 6, 0] {
                    b.extend(n.to_be_bytes());
                }
            }
            b.extend([0, 0]);
            let origin = ClassOrigin {
                generated: None,
                loader: if owner { self.loader } else { "bootstrap" }.into(),
                binary_name: name.replace('/', "."),
                source_id: "jdk:java.base".into(),
                jar_entry: format!("{name}.class"),
                java_class_major: 65,
                sha256: crate::files::digest_bytes(&b).sha256,
            };
            Ok((b, origin))
        }
    }
    #[test]
    fn cds_members_and_private_callers_keep_their_original_definition() {
        use types::TypeProvider;
        for operation in [
            Operation::InitializeFromArchive,
            Operation::IsDumpingClassList,
            Operation::IsDumpingArchive,
            Operation::IsSharingEnabled,
            Operation::GetRandomSeedForDumping,
        ] {
            let expected = if operation.private() { 0x10a } else { 0x109 };
            for (access, loader, valid) in [
                (expected, "bootstrap", true),
                (8, "bootstrap", false),
                (expected, "application", false),
            ] {
                let p = Provider {
                    operation,
                    access,
                    loader,
                };
                let (bytes, origin) = p.resolve("bootstrap", OWNER).unwrap();
                let caller = ClassFile::parse(&bytes).unwrap();
                assert_eq!(
                    binding(
                        &mut types::Registry::new(&p),
                        operation,
                        &caller,
                        &origin,
                        1,
                        2
                    )
                    .is_ok(),
                    valid
                );
                if valid {
                    let mut changed = origin.clone();
                    changed.sha256 = "changed".into();
                    assert_eq!(
                        binding(
                            &mut types::Registry::new(&p),
                            operation,
                            &caller,
                            &changed,
                            1,
                            2
                        )
                        .is_ok(),
                        !operation.private()
                    );
                }
            }
        }
    }
    #[test]
    fn cds_profile_has_no_silent_archive_mode() {
        assert!(Plan::no_archive(vec![]).is_none());
        let mut p = Plan {
            abi: 1,
            shared_archive_mapped: true,
            dumping_archive: false,
            dumping_class_list: false,
            bindings: vec![],
        };
        assert!(p.emit(&mut String::new()).is_err());
        p.shared_archive_mapped = false;
        assert!(p.emit(&mut String::new()).is_err());
        for op in [
            Operation::InitializeFromArchive,
            Operation::IsDumpingClassList,
            Operation::IsDumpingArchive,
            Operation::IsSharingEnabled,
            Operation::GetRandomSeedForDumping,
        ] {
            assert_eq!(
                Operation::resolve(OWNER, op.name(), op.descriptor()),
                Some(op)
            );
            assert!(Operation::resolve("app/CDS", op.name(), op.descriptor()).is_none());
        }
        assert!(
            Operation::resolve(
                OWNER,
                "defineArchivedModules",
                "(Ljava/lang/ClassLoader;Ljava/lang/ClassLoader;)V"
            )
            .is_none()
        );
    }
}
