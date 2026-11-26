//! Original FileDescriptor initialization and its Windows handle services.
use super::{classfile::ClassFile, numeric, types};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/io/FileDescriptor";
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum Operation {
    InitIds = 0,
    GetHandle = 1,
    GetAppend = 2,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, descriptor: &str) -> Option<Self> {
        if owner != OWNER {
            return None;
        }
        [Self::InitIds, Self::GetHandle, Self::GetAppend]
            .into_iter()
            .find(|o| o.name() == name && o.descriptor() == descriptor)
    }
    fn name(self) -> &'static str {
        match self {
            Self::InitIds => "initIDs",
            Self::GetHandle => "getHandle",
            Self::GetAppend => "getAppend",
        }
    }
    fn descriptor(self) -> &'static str {
        match self {
            Self::InitIds => "()V",
            Self::GetHandle => "(I)J",
            Self::GetAppend => "(I)Z",
        }
    }
    pub(super) fn signature(self) -> numeric::Signature {
        use numeric::{Signature, Type};
        Signature {
            arguments: if self == Self::InitIds {
                vec![]
            } else {
                vec![Type::I32]
            },
            result: match self {
                Self::InitIds => Type::Void,
                Self::GetHandle => Type::I64,
                Self::GetAppend => Type::I32,
            },
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub operation: Operation,
    pub caller: ClassOrigin,
    pub constant: u16,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Field {
    pub name: String,
    pub descriptor: String,
    pub offset: usize,
    pub width: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub class_id: usize,
    pub origin: ClassOrigin,
    pub layout: numeric::ObjectLayout,
    pub fields: Vec<Field>,
    pub bindings: Vec<Binding>,
}
pub(super) fn source(
    registry: &mut types::Registry<'_>,
    op: Operation,
    caller: &ClassFile,
    source: &ClassOrigin,
) -> Result<ClassOrigin> {
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
            && access & 0x611 == 0x11,
        "FileDescriptor binding requires the original final bootstrap class"
    );
    ensure!(
        caller.name == OWNER && source == origin.as_ref(),
        "FileDescriptor private native requires its original caller"
    );
    let origin = origin.as_ref().clone();
    let class = registry
        .definition(id)
        .context("Missing FileDescriptor definition")?;
    let member = class.method(op.name(), Some(op.descriptor()))?;
    ensure!(
        member.access == 0x10a && member.code.is_none(),
        "FileDescriptor private static native contract changed"
    );
    for (name, descriptor) in [("fd", "I"), ("handle", "J"), ("append", "Z")] {
        ensure!(
            class
                .field_info
                .iter()
                .any(|f| f.name == name && f.descriptor == descriptor && f.access == 2),
            "FileDescriptor field contract changed"
        );
    }
    Ok(origin)
}
impl Plan {
    pub(super) fn new(
        class_id: usize,
        origin: ClassOrigin,
        layout: numeric::ObjectLayout,
    ) -> Result<Self> {
        let mut fields = Vec::new();
        for (name, descriptor, minimum) in [("fd", "I", 4), ("handle", "J", 8), ("append", "Z", 1)]
        {
            let f = layout
                .fields
                .iter()
                .find(|f| f.name == name && f.descriptor == descriptor)
                .context("Missing native descriptor field layout")?;
            let width = f.storage_bytes.unwrap_or(8);
            ensure!(
                (width == minimum || width == 8)
                    && f.offset >= layout.reference_prefix_fields * 8
                    && f.offset + width <= layout.payload_bytes
                    && f.offset % width == 0,
                "Invalid native descriptor field offset or width"
            );
            fields.push(Field {
                name: name.into(),
                descriptor: descriptor.into(),
                offset: f.offset,
                width,
            });
        }
        for (i, a) in fields.iter().enumerate() {
            for b in &fields[i + 1..] {
                ensure!(
                    a.offset + a.width <= b.offset || b.offset + b.width <= a.offset,
                    "Overlapping native descriptor fields"
                );
            }
        }
        Ok(Self {
            abi: 1,
            class_id,
            origin,
            layout,
            fields,
            bindings: Vec::new(),
        })
    }
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        ensure!(
            self.abi == 1 && self.fields.len() == 3 && !self.bindings.is_empty(),
            "Invalid FileDescriptor native plan"
        );
        out.push_str(
            "EXTERN boom_fd_service:PROC\n.const\nALIGN 8\nboom_fd_table DWORD 046445442h, 1\n",
        );
        out.push_str(&format!("    QWORD OFFSET boom_layout{}\n", self.class_id));
        for f in &self.fields {
            out.push_str(&format!("    DWORD {}, {}\n", f.offset, f.width));
        }
        out.push_str("    QWORD 0\n.data\nALIGN 8\nboom_fd_pool DWORD 04644504Ch, 1\n    QWORD OFFSET boom_fd_table, 0, 0\n.code\nPUBLIC boom_get_fd_pool\nboom_get_fd_pool PROC\n    lea rax, boom_fd_pool\n    ret\nboom_get_fd_pool ENDP\n");
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Provider {
        access: u16,
        append: u16,
        loader: &'static str,
    }
    impl types::TypeProvider for Provider {
        fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 17];
            fn utf(b: &mut Vec<u8>, s: &str) {
                b.push(1);
                b.extend((s.len() as u16).to_be_bytes());
                b.extend(s.as_bytes());
            }
            utf(&mut b, name);
            b.extend([7, 0, 1]);
            utf(&mut b, "java/lang/Object");
            b.extend([7, 0, 3]);
            for s in [
                "fd",
                "I",
                "handle",
                "J",
                "append",
                "Z",
                "initIDs",
                "()V",
                "getHandle",
                "(I)J",
                "getAppend",
                "(I)Z",
            ] {
                utf(&mut b, s);
            }
            let owner = name == OWNER;
            for n in [
                if owner { 0x31u16 } else { 0x21 },
                2,
                if name == "java/lang/Object" { 0 } else { 4 },
                0,
                if owner { 3 } else { 0 },
            ] {
                b.extend(n.to_be_bytes());
            }
            if owner {
                for (n, a) in [(5u16, 2), (7, 2), (9, self.append)] {
                    for v in [a, n, n + 1, 0] {
                        b.extend(v.to_be_bytes());
                    }
                }
            }
            b.extend(u16::from(owner).wrapping_mul(3).to_be_bytes());
            if owner {
                for n in [11u16, 13, 15] {
                    for v in [self.access, n, n + 1, 0] {
                        b.extend(v.to_be_bytes());
                    }
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
    fn descriptor_natives_keep_private_original_callers_and_fields() {
        use types::TypeProvider;
        for op in [
            Operation::InitIds,
            Operation::GetHandle,
            Operation::GetAppend,
        ] {
            for (access, append, loader, valid) in [
                (0x10a, 2, "bootstrap", true),
                (0x109, 2, "bootstrap", false),
                (0x10a, 10, "bootstrap", false),
                (0x10a, 2, "application", false),
            ] {
                let p = Provider {
                    access,
                    append,
                    loader,
                };
                let (bytes, origin) = p.resolve("bootstrap", OWNER).unwrap();
                let c = ClassFile::parse(&bytes).unwrap();
                assert_eq!(
                    source(&mut types::Registry::new(&p), op, &c, &origin).is_ok(),
                    valid
                );
                if valid {
                    let mut wrong = origin.clone();
                    wrong.sha256 = "changed".into();
                    assert!(source(&mut types::Registry::new(&p), op, &c, &wrong).is_err());
                }
            }
        }
    }
    #[test]
    fn descriptor_native_layout_keeps_alignment_bounds_and_disjoint_fields() {
        use types::TypeProvider;
        let p = Provider {
            access: 0x10a,
            append: 2,
            loader: "bootstrap",
        };
        let (_, origin) = p.resolve("bootstrap", OWNER).unwrap();
        let layout = numeric::ObjectLayout {
            abi: 1,
            payload_bytes: 24,
            reference_prefix_fields: 0,
            fields: [("fd", "I"), ("handle", "J"), ("append", "Z")]
                .into_iter()
                .enumerate()
                .map(|(i, (n, d))| numeric::FieldLayout {
                    name: n.into(),
                    descriptor: d.into(),
                    offset: i * 8,
                    declaring_class: None,
                    declaring_field: None,
                    storage_bytes: None,
                })
                .collect(),
        };
        Plan::new(0, origin.clone(), layout.clone()).unwrap();
        let mut bad = layout.clone();
        bad.fields[1].offset = 0;
        assert!(Plan::new(0, origin.clone(), bad).is_err());
        let mut bad = layout.clone();
        bad.fields[0].offset = 4;
        assert!(Plan::new(0, origin.clone(), bad).is_err());
        let mut bad = layout;
        bad.payload_bytes = 16;
        assert!(Plan::new(0, origin, bad).is_err());
    }
}
