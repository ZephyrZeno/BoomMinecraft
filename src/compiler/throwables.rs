//! Native Throwable backtrace capture; original Java constructors remain executable.
use super::{classfile::ClassFile, numeric, program::ProgramObjectLayout, types};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/lang/Throwable";
pub(super) fn is_fill(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == OWNER && name == "fillInStackTrace" && descriptor == "(I)Ljava/lang/Throwable;"
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub origin: ClassOrigin,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub type_id: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub vm_factory: Option<bool>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Receiver {
    pub class_id: usize,
    pub type_id: usize,
    pub source: ClassOrigin,
    pub layout: numeric::ObjectLayout,
    pub backtrace_offset: usize,
    pub depth_offset: usize,
    pub depth_width: usize,
    pub stack_trace_offset: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub binding: Binding,
    pub receivers: Vec<Receiver>,
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
) -> Result<Binding> {
    let mut result = runtime_binding(registry)?;
    ensure!(
        caller.name == OWNER && source == &result.origin,
        "Throwable native requires its original bootstrap caller"
    );
    result.caller = source.clone();
    result.constant = constant;
    result.vm_factory = None;
    Ok(result)
}
pub(super) fn runtime_binding(registry: &mut types::Registry<'_>) -> Result<Binding> {
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
        "Throwable native requires its original bootstrap caller"
    );
    let class = registry
        .definition(id)
        .context("Missing original Throwable")?;
    let member = class.method("fillInStackTrace", Some("(I)Ljava/lang/Throwable;"))?;
    ensure!(
        member.access == 0x102 && member.code.is_none(),
        "Throwable fillInStackTrace private native contract changed"
    );
    for (name, descriptor) in [("backtrace", "Ljava/lang/Object;"), ("depth", "I")] {
        ensure!(
            class
                .field_info
                .iter()
                .any(|f| f.name == name && f.descriptor == descriptor && f.access == 0x82),
            "Throwable native field contract changed"
        );
    }
    ensure!(
        class.field_info.iter().any(|f| f.name == "stackTrace"
            && f.descriptor == "[Ljava/lang/StackTraceElement;"
            && f.access == 2),
        "Throwable stackTrace field contract changed"
    );
    Ok(Binding {
        origin: origin.as_ref().clone(),
        caller: origin.as_ref().clone(),
        constant: 0,
        type_id: id,
        vm_factory: Some(true),
    })
}
pub(super) fn plan(
    registry: &mut types::Registry<'_>,
    binding: Binding,
    classes: &[ClassFile],
    sources: &[Option<ClassOrigin>],
    layouts: &[ProgramObjectLayout],
) -> Result<Plan> {
    let mut receivers = Vec::new();
    for prepared in layouts {
        let class = &classes[prepared.class_id];
        if class.access & 0x600 != 0 {
            continue;
        }
        let source = sources[prepared.class_id]
            .as_ref()
            .context("Missing throwable receiver origin")?;
        let ty = registry.class(&source.loader, &class.name)?;
        if !registry.assignable(ty, binding.type_id) {
            continue;
        }
        let find = |name: &str, descriptor: &str| {
            prepared
                .layout
                .fields
                .iter()
                .find(|f| {
                    f.name == name
                        && f.descriptor == descriptor
                        && f.declaring_class.as_deref() == Some(OWNER)
                })
                .context("Missing actual inherited Throwable native field")
        };
        let backtrace = find("backtrace", "Ljava/lang/Object;")?;
        let depth = find("depth", "I")?;
        let stack_trace = find("stackTrace", "[Ljava/lang/StackTraceElement;")?;
        let depth_width = depth.storage_bytes.unwrap_or(8);
        ensure!(
            backtrace.storage_bytes.unwrap_or(8) == 8
                && backtrace.offset % 8 == 0
                && backtrace.offset < prepared.layout.reference_prefix_fields * 8
                && stack_trace.storage_bytes.unwrap_or(8) == 8
                && stack_trace.offset % 8 == 0
                && stack_trace.offset < prepared.layout.reference_prefix_fields * 8
                && stack_trace.offset != backtrace.offset
                && matches!(depth_width, 4 | 8)
                && depth.offset % depth_width == 0
                && depth.offset >= prepared.layout.reference_prefix_fields * 8
                && depth.offset + depth_width <= prepared.layout.payload_bytes,
            "Invalid Throwable reference/scalar native field layout"
        );
        receivers.push(Receiver {
            class_id: prepared.class_id,
            type_id: ty,
            source: source.clone(),
            layout: prepared.layout.clone(),
            backtrace_offset: backtrace.offset,
            depth_offset: depth.offset,
            depth_width,
            stack_trace_offset: stack_trace.offset,
        });
    }
    ensure!(
        !receivers.is_empty() && receivers.len() <= 4096,
        "Missing/excessive Throwable receiver layouts"
    );
    Ok(Plan {
        abi: 1,
        binding,
        receivers,
    })
}
impl Plan {
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        ensure!(self.abi == 1, "Unsupported Throwable native ABI");
        out.push_str("EXTERN boom_throwable_fill:PROC\n.const\nALIGN 8\nboom_throwable_receivers LABEL BYTE\n");
        for r in &self.receivers {
            out.push_str(&format!("    QWORD OFFSET boom_layout{}\n    DWORD {}, {}, {}, {}\n    QWORD 0, OFFSET boom_t{}, 0\n",r.class_id,r.backtrace_offset,r.depth_offset,r.depth_width,r.stack_trace_offset,r.type_id));
        }
        out.push_str(&format!("ALIGN 8\nboom_throwable_plan DWORD 054485250h, 1, {}, 0\n    QWORD OFFSET boom_throwable_receivers, OFFSET boom_trace_pool, OFFSET boom_heap_ptr, OFFSET boom_t{}, 0, 0\n",self.receivers.len(),self.binding.type_id));
        out.push_str(".code\nPUBLIC boom_get_throwable_plan\nboom_get_throwable_plan PROC\n    lea rax, boom_throwable_plan\n    ret\nboom_get_throwable_plan ENDP\n");
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Provider {
        native: u16,
        transient: u16,
        stack: u16,
        loader: &'static str,
    }
    impl types::TypeProvider for Provider {
        fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let own = name == OWNER;
            let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 13];
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
                "backtrace",
                "Ljava/lang/Object;",
                "depth",
                "I",
                "stackTrace",
                "[Ljava/lang/StackTraceElement;",
                "fillInStackTrace",
                "(I)Ljava/lang/Throwable;",
            ] {
                utf(&mut b, s);
            }
            for v in [
                0x21u16,
                2,
                if name == "java/lang/Object" { 0 } else { 4 },
                0,
                if own { 3 } else { 0 },
            ] {
                b.extend(v.to_be_bytes());
            }
            if own {
                for (access, n) in [(self.transient, 5u16), (self.transient, 7), (self.stack, 9)] {
                    for v in [access, n, n + 1, 0] {
                        b.extend(v.to_be_bytes());
                    }
                }
            }
            b.extend(u16::from(own).to_be_bytes());
            if own {
                for v in [self.native, 11, 12, 0] {
                    b.extend(v.to_be_bytes());
                }
            }
            b.extend([0, 0]);
            let source = ClassOrigin {
                generated: None,
                loader: if own { self.loader } else { "bootstrap" }.into(),
                binary_name: name.replace('/', "."),
                source_id: "jdk:java.base".into(),
                jar_entry: format!("{name}.class"),
                java_class_major: 65,
                sha256: crate::files::digest_bytes(&b).sha256,
            };
            Ok((b, source))
        }
    }
    #[test]
    fn throwable_capture_requires_original_private_native_and_exact_mutable_fields() {
        use types::TypeProvider;
        for (native, transient, stack, loader, valid) in [
            (0x102, 0x82, 2, "bootstrap", true),
            (0x101, 0x82, 2, "bootstrap", false),
            (0x102, 2, 2, "bootstrap", false),
            (0x102, 0x82, 0x12, "bootstrap", false),
            (0x102, 0x82, 2, "application", false),
        ] {
            let provider = Provider {
                native,
                transient,
                stack,
                loader,
            };
            let (bytes, source) = provider.resolve("bootstrap", OWNER).unwrap();
            let class = ClassFile::parse(&bytes).unwrap();
            assert_eq!(
                binding(&mut types::Registry::new(&provider), &class, &source, 0).is_ok(),
                valid
            );
            if valid {
                let mut wrong = source.clone();
                wrong.sha256 = "different".into();
                assert!(binding(&mut types::Registry::new(&provider), &class, &wrong, 0).is_err());
            }
        }
    }
}
