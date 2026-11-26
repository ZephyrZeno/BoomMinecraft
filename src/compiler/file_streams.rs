//! Original stream initIDs maps fd to its actual translated reference-field slot.
use super::{classfile::ClassFile, numeric, types};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub(super) fn resolves(owner: &str, name: &str, descriptor: &str) -> bool {
    matches!(
        owner,
        "java/io/FileInputStream" | "java/io/FileOutputStream"
    ) && name == "initIDs"
        && descriptor == "()V"
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub class_id: usize,
    pub origin: ClassOrigin,
    pub descriptor_origin: ClassOrigin,
    pub layout: numeric::ObjectLayout,
    pub fd_offset: usize,
    pub bindings: Vec<Binding>,
}
pub(super) fn source(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    origin: &ClassOrigin,
) -> Result<ClassOrigin> {
    ensure!(
        resolves(&caller.name, "initIDs", "()V"),
        "Stream initIDs requires its own original class"
    );
    let id = registry.class("bootstrap", &caller.name)?;
    let types::Type::Class {
        key,
        origin: actual,
        access,
        ..
    } = &registry.types[id]
    else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && actual.source_id == "jdk:java.base"
            && actual.generated.is_none()
            && actual.as_ref() == origin
            && access & 0x601 == 1,
        "Stream initIDs requires its original public bootstrap java.base caller"
    );
    let class = registry
        .definition(id)
        .context("Missing original stream definition")?;
    let member = class.method("initIDs", Some("()V"))?;
    ensure!(
        member.access == 0x10a && member.code.is_none(),
        "Stream initIDs private static native contract changed"
    );
    ensure!(
        class.field_info.iter().any(|f| f.name == "fd"
            && f.descriptor == "Ljava/io/FileDescriptor;"
            && f.access == 0x12),
        "Stream fd private final reference contract changed"
    );
    let fd = registry.class("bootstrap", "java/io/FileDescriptor")?;
    let types::Type::Class { key, origin, .. } = &registry.types[fd] else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "Stream fd type requires original FileDescriptor metadata"
    );
    Ok(origin.as_ref().clone())
}
impl Plan {
    pub(super) fn new(
        class_id: usize,
        origin: ClassOrigin,
        descriptor_origin: ClassOrigin,
        layout: numeric::ObjectLayout,
    ) -> Result<Self> {
        let declaring = origin.binary_name.replace('.', "/");
        let f = layout
            .fields
            .iter()
            .find(|f| {
                f.name == "fd"
                    && f.descriptor == "Ljava/io/FileDescriptor;"
                    && f.declaring_class.as_deref() == Some(declaring.as_str())
            })
            .context("Missing stream fd physical field")?;
        let width = f.storage_bytes.unwrap_or(8);
        ensure!(
            width == 8
                && f.offset % 8 == 0
                && f.offset < layout.reference_prefix_fields * 8
                && f.offset + 8 <= layout.payload_bytes,
            "Stream fd must occupy a complete slot in the live reference prefix"
        );
        Ok(Self {
            abi: 1,
            class_id,
            origin,
            descriptor_origin,
            fd_offset: f.offset,
            layout,
            bindings: vec![],
        })
    }
}

pub(super) fn emit(plans: &[Plan], out: &mut String) -> Result<()> {
    if plans.is_empty() {
        return Ok(());
    }
    out.push_str("EXTERN boom_stream_fields_init:PROC\n");
    for p in plans {
        ensure!(
            p.abi == 1 && !p.bindings.is_empty(),
            "Invalid stream field plan"
        );
        out.push_str(&format!(".const\nALIGN 8\nboom_stream_table{} DWORD 053465442h, 1\n    QWORD OFFSET boom_layout{}\n    DWORD {}, 8\n    QWORD 0\n.data\nALIGN 8\nboom_stream_pool{} DWORD 05346504Ch, 1\n    QWORD OFFSET boom_stream_table{}, 0, 0\n",p.class_id,p.class_id,p.fd_offset,p.class_id,p.class_id));
    }
    out.push_str(".code\nPUBLIC boom_get_stream_pool\nboom_get_stream_pool PROC\n");
    for p in plans {
        out.push_str(&format!(
            "    cmp ecx, {}\n    je boom_stream_pool_return{}\n",
            p.class_id, p.class_id
        ));
    }
    out.push_str("    xor eax, eax\n    ret\n");
    for p in plans {
        out.push_str(&format!(
            "boom_stream_pool_return{}:\n    lea rax, boom_stream_pool{}\n    ret\n",
            p.class_id, p.class_id
        ));
    }
    out.push_str("boom_get_stream_pool ENDP\n");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Provider {
        native: u16,
        field: u16,
        loader: &'static str,
    }
    impl types::TypeProvider for Provider {
        fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let stream = matches!(name, "java/io/FileInputStream" | "java/io/FileOutputStream");
            let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 9];
            fn utf(b: &mut Vec<u8>, s: &str) {
                b.push(1);
                b.extend((s.len() as u16).to_be_bytes());
                b.extend(s.as_bytes());
            }
            utf(&mut b, name);
            b.extend([7, 0, 1]);
            utf(&mut b, "java/lang/Object");
            b.extend([7, 0, 3]);
            for s in ["fd", "Ljava/io/FileDescriptor;", "initIDs", "()V"] {
                utf(&mut b, s);
            }
            for v in [
                0x21u16,
                2,
                if name == "java/lang/Object" { 0 } else { 4 },
                0,
                u16::from(stream),
            ] {
                b.extend(v.to_be_bytes());
            }
            if stream {
                for v in [self.field, 5, 6, 0] {
                    b.extend(v.to_be_bytes());
                }
            }
            b.extend(u16::from(stream).to_be_bytes());
            if stream {
                for v in [self.native, 7, 8, 0] {
                    b.extend(v.to_be_bytes());
                }
            }
            b.extend([0, 0]);
            let origin = ClassOrigin {
                generated: None,
                loader: if stream { self.loader } else { "bootstrap" }.into(),
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
    fn stream_init_ids_requires_original_private_native_and_declared_final_fd() {
        use types::TypeProvider;
        for name in ["java/io/FileInputStream", "java/io/FileOutputStream"] {
            for (native, field, loader, valid) in [
                (0x10a, 0x12, "bootstrap", true),
                (0x109, 0x12, "bootstrap", false),
                (0x10a, 0x2, "bootstrap", false),
                (0x10a, 0x12, "application", false),
            ] {
                let p = Provider {
                    native,
                    field,
                    loader,
                };
                let (bytes, origin) = p.resolve("bootstrap", name).unwrap();
                let class = ClassFile::parse(&bytes).unwrap();
                assert_eq!(
                    source(&mut types::Registry::new(&p), &class, &origin).is_ok(),
                    valid
                );
                if valid {
                    let mut wrong = origin.clone();
                    wrong.sha256 = "changed".into();
                    assert!(source(&mut types::Registry::new(&p), &class, &wrong).is_err());
                }
            }
        }
    }
    #[test]
    fn stream_fd_binding_requires_its_declared_live_reference_slot() {
        use types::TypeProvider;
        let p = Provider {
            native: 0x10a,
            field: 0x12,
            loader: "bootstrap",
        };
        let (_, origin) = p.resolve("bootstrap", "java/io/FileInputStream").unwrap();
        let (_, fd) = p.resolve("bootstrap", "java/io/FileDescriptor").unwrap();
        let layout = numeric::ObjectLayout {
            abi: 2,
            payload_bytes: 17,
            reference_prefix_fields: 2,
            fields: vec![
                numeric::FieldLayout {
                    name: "fd".into(),
                    descriptor: "Ljava/io/FileDescriptor;".into(),
                    offset: 8,
                    declaring_class: Some("java/io/FileInputStream".into()),
                    declaring_field: Some(0),
                    storage_bytes: Some(8),
                },
                numeric::FieldLayout {
                    name: "other".into(),
                    descriptor: "Ljava/lang/Object;".into(),
                    offset: 0,
                    declaring_class: None,
                    declaring_field: None,
                    storage_bytes: Some(8),
                },
                numeric::FieldLayout {
                    name: "closed".into(),
                    descriptor: "Z".into(),
                    offset: 16,
                    declaring_class: None,
                    declaring_field: None,
                    storage_bytes: Some(1),
                },
            ],
        };
        assert!(Plan::new(4, origin.clone(), fd.clone(), layout.clone()).is_ok());
        for issue in 0..6 {
            let mut bad = layout.clone();
            match issue {
                0 => bad.fields[0].offset = 1,
                1 => bad.fields[0].offset = 16,
                2 => bad.reference_prefix_fields = 1,
                3 => bad.payload_bytes = 15,
                4 => bad.fields[0].storage_bytes = Some(4),
                _ => bad.fields[0].declaring_class = Some("java/io/InputStream".into()),
            };
            assert!(Plan::new(4, origin.clone(), fd.clone(), bad).is_err());
        }
    }
}
