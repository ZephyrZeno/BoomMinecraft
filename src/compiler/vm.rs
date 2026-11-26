//! Source-verified bindings for VM-native services; execution is handwritten MASM.
use super::types;
use crate::bytecode::ClassOrigin;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Operation {
    CurrentTimeMillis,
    NanoTime,
    ArrayCopy,
    RegisterNatives,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, descriptor: &str) -> Option<Self> {
        if owner != "java/lang/System" {
            return None;
        }
        match (name, descriptor) {
            ("currentTimeMillis", "()J") => Some(Self::CurrentTimeMillis),
            ("nanoTime", "()J") => Some(Self::NanoTime),
            ("arraycopy", "(Ljava/lang/Object;ILjava/lang/Object;II)V") => Some(Self::ArrayCopy),
            ("registerNatives", "()V") => Some(Self::RegisterNatives),
            _ => None,
        }
    }
    pub(super) fn name(self) -> &'static str {
        match self {
            Self::CurrentTimeMillis => "currentTimeMillis",
            Self::NanoTime => "nanoTime",
            Self::ArrayCopy => "arraycopy",
            Self::RegisterNatives => "registerNatives",
        }
    }
    pub(super) fn descriptor(self) -> &'static str {
        match self {
            Self::ArrayCopy => "(Ljava/lang/Object;ILjava/lang/Object;II)V",
            Self::RegisterNatives => "()V",
            _ => "()J",
        }
    }
    pub(super) fn signature(self) -> super::numeric::Signature {
        use super::numeric::{Signature, Type::*};
        match self {
            Self::ArrayCopy => Signature {
                arguments: vec![AnyRef, I32, AnyRef, I32, I32],
                result: Void,
            },
            Self::RegisterNatives => Signature {
                arguments: vec![],
                result: Void,
            },
            _ => Signature {
                arguments: vec![],
                result: I64,
            },
        }
    }
    pub(super) fn symbol(self) -> &'static str {
        match self {
            Self::CurrentTimeMillis => "boom_vm_current_time_millis",
            Self::NanoTime => "boom_vm_nano_time",
            Self::ArrayCopy => "boom_system_arraycopy",
            Self::RegisterNatives => "boom_system_register",
        }
    }
    pub(super) fn native_index(self) -> Option<u32> {
        match self {
            Self::CurrentTimeMillis => Some(0),
            Self::NanoTime => Some(1),
            Self::ArrayCopy => Some(2),
            Self::RegisterNatives => None,
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub operation: Operation,
    pub owner: String,
    pub method: String,
    pub descriptor: String,
    pub assembly_symbol: String,
    pub origin: ClassOrigin,
}

pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    loader: &str,
    op: Operation,
) -> anyhow::Result<Binding> {
    use anyhow::{Context, ensure};
    let id = registry.class(loader, "java/lang/System")?;
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
        key.loader == "bootstrap" && origin.source_id == "jdk:java.base" && access & 0x201 == 1,
        "VM native binding requires pinned bootstrap System identity"
    );
    ensure!(
        op != Operation::RegisterNatives || access & 0x10 != 0,
        "Native registration requires the final System identity"
    );
    let origin = origin.as_ref().clone();
    let method = registry
        .definition(id)
        .context("Missing pinned System definition")?
        .method(op.name(), Some(op.descriptor()))?;
    ensure!(
        method.access
            == if op == Operation::RegisterNatives {
                0x10a
            } else {
                0x109
            }
            && method.code.is_none(),
        "VM binding must name the original static native System member with its exact access"
    );
    Ok(Binding {
        operation: op,
        owner: "java/lang/System".into(),
        method: op.name().into(),
        descriptor: op.descriptor().into(),
        assembly_symbol: op.symbol().into(),
        origin,
    })
}

pub(super) fn registration_caller(
    class: &super::classfile::ClassFile,
    source: &ClassOrigin,
    binding: &Binding,
) -> anyhow::Result<()> {
    anyhow::ensure!(
        class.name == "java/lang/System"
            && source.loader == "bootstrap"
            && source == &binding.origin,
        "System.registerNatives is private to its verified bootstrap System caller"
    );
    Ok(())
}

pub(super) fn emit_registration(assembly: &mut String, bindings: &[Binding]) -> anyhow::Result<()> {
    use anyhow::{Context, ensure};
    let Some(register) = bindings
        .iter()
        .find(|b| b.operation == Operation::RegisterNatives)
    else {
        return Ok(());
    };
    for op in [
        Operation::CurrentTimeMillis,
        Operation::NanoTime,
        Operation::ArrayCopy,
    ] {
        let b = bindings
            .iter()
            .find(|b| b.operation == op)
            .context("Missing registered System native implementation")?;
        ensure!(
            b.origin == register.origin
                && b.descriptor == op.descriptor()
                && b.assembly_symbol == op.symbol(),
            "System native registration origin/contract mismatch"
        );
    }
    assembly.push_str("EXTERN boom_system_dispatch:PROC\n.const\nALIGN 8\nboom_system_native_table DWORD 05359534Dh, 1, 3, 0\n    QWORD OFFSET boom_vm_current_time_millis, OFFSET boom_vm_nano_time, OFFSET boom_system_arraycopy\n.data\nALIGN 8\nboom_system_native_pool DWORD 053595350h, 1\n    QWORD 0, OFFSET boom_system_native_table, OFFSET boom_runtime_type_map\n.code\n");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::Result;
    fn fixture(name: &str, access: u16, op: Operation) -> Vec<u8> {
        let mut bytes = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 8];
        fn utf(bytes: &mut Vec<u8>, value: &str) {
            bytes.push(1);
            bytes.extend((value.len() as u16).to_be_bytes());
            bytes.extend(value.as_bytes());
        }
        utf(&mut bytes, name);
        bytes.extend([7, 0, 1]);
        utf(&mut bytes, "java/lang/Object");
        bytes.extend([7, 0, 3]);
        for value in [op.name(), op.descriptor(), "Code"] {
            utf(&mut bytes, value);
        }
        for n in [
            if name == "java/lang/System" {
                0x31u16
            } else {
                0x21
            },
            2,
            if name == "java/lang/Object" { 0 } else { 4 },
            0,
            0,
            if name == "java/lang/Object" { 0 } else { 1 },
        ] {
            bytes.extend(n.to_be_bytes());
        }
        if name != "java/lang/Object" {
            for n in [access, 5, 6, if access & 0x100 != 0 { 0 } else { 1 }] {
                bytes.extend(n.to_be_bytes());
            }
            if access & 0x100 == 0 {
                bytes.extend([0, 7]);
                bytes.extend(14u32.to_be_bytes());
                bytes.extend([0, 2, 0, 0, 0, 0, 0, 2, 0x09, 0xad, 0, 0, 0, 0]);
            }
        }
        bytes.extend([0, 0]);
        bytes
    }
    struct Provider {
        access: u16,
        loader: &'static str,
        operation: Operation,
    }
    impl types::TypeProvider for Provider {
        fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let bytes = fixture(name, self.access, self.operation);
            let loader = if name == "java/lang/Object" {
                "bootstrap"
            } else {
                self.loader
            };
            Ok((
                bytes.clone(),
                ClassOrigin {
                    generated: None,
                    loader: loader.into(),
                    binary_name: name.replace('/', "."),
                    source_id: "jdk:java.base".into(),
                    jar_entry: format!("{name}.class"),
                    java_class_major: 65,
                    sha256: crate::files::digest_bytes(&bytes).sha256,
                },
            ))
        }
    }
    #[test]
    fn native_clock_binding_requires_the_sealed_native_contract() {
        for (access, loader, valid) in [
            (0x109, "bootstrap", true),
            (9, "bootstrap", false),
            (0x129, "bootstrap", false),
            (0x109, "vanilla-application", false),
        ] {
            let provider = Provider {
                access,
                loader,
                operation: Operation::CurrentTimeMillis,
            };
            let mut registry = types::Registry::new(&provider);
            let result = binding(
                &mut registry,
                "vanilla-application",
                Operation::CurrentTimeMillis,
            );
            assert_eq!(
                result.is_ok(),
                valid,
                "access={access:x} loader={loader}: {result:?}"
            );
        }
        assert!(Operation::resolve("p/System", "nanoTime", "()J").is_none());
        assert!(Operation::resolve("java/lang/System", "nanoTime", "(I)J").is_none());
        assert!(Operation::resolve("java/lang/System", "exit", "(I)V").is_none());
    }
    #[test]
    fn native_arraycopy_and_registration_keep_distinct_signatures_and_access() {
        for op in [Operation::ArrayCopy, Operation::RegisterNatives] {
            for access in [0x109, 0x10a, 9, 0x129] {
                let provider = Provider {
                    access,
                    loader: "bootstrap",
                    operation: op,
                };
                let result = binding(&mut types::Registry::new(&provider), "bootstrap", op);
                assert_eq!(
                    result.is_ok(),
                    access
                        == if op == Operation::ArrayCopy {
                            0x109
                        } else {
                            0x10a
                        }
                );
            }
        }
        assert_eq!(Operation::ArrayCopy.signature().arguments.len(), 5);
        assert_eq!(
            Operation::ArrayCopy.signature().result,
            super::super::numeric::Type::Void
        );
        assert_eq!(
            Operation::RegisterNatives.signature().result,
            super::super::numeric::Type::Void
        );
        assert!(Operation::resolve("java/lang/System", "arraycopy", "(IIIII)V").is_none());
    }
    #[test]
    fn registration_rejects_foreign_callers_and_incomplete_native_tables() {
        let provider = Provider {
            access: 0x10a,
            loader: "bootstrap",
            operation: Operation::RegisterNatives,
        };
        let b = binding(
            &mut types::Registry::new(&provider),
            "bootstrap",
            Operation::RegisterNatives,
        )
        .unwrap();
        let class = super::super::classfile::ClassFile::parse(&fixture(
            "java/lang/System",
            0x10a,
            Operation::RegisterNatives,
        ))
        .unwrap();
        registration_caller(&class, &b.origin, &b).unwrap();
        let other = super::super::classfile::ClassFile::parse(&fixture(
            "app/System",
            0x10a,
            Operation::RegisterNatives,
        ))
        .unwrap();
        assert!(registration_caller(&other, &b.origin, &b).is_err());
        for change in 0..2 {
            let mut source = b.origin.clone();
            if change == 0 {
                source.loader = "application".into()
            } else {
                source.sha256 = "changed".into()
            }
            assert!(registration_caller(&class, &source, &b).is_err());
        }
        let mut bindings = vec![b.clone()];
        for op in [
            Operation::CurrentTimeMillis,
            Operation::NanoTime,
            Operation::ArrayCopy,
        ] {
            bindings.push(Binding {
                operation: op,
                owner: "java/lang/System".into(),
                method: op.name().into(),
                descriptor: op.descriptor().into(),
                assembly_symbol: op.symbol().into(),
                origin: b.origin.clone(),
            });
        }
        emit_registration(&mut String::new(), &bindings).unwrap();
        let last = bindings.pop().unwrap();
        assert!(emit_registration(&mut String::new(), &bindings).is_err());
        bindings.push(last);
        bindings[1].assembly_symbol = "foreign_native".into();
        assert!(emit_registration(&mut String::new(), &bindings).is_err());
    }
}
