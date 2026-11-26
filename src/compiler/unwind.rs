//! Closed-image Context32 exception factories and ordered executable handlers.
use super::{
    classfile::{ClassFile, Method},
    numeric,
    program::ProgramObjectLayout,
    types,
};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const KINDS: &[(u32, &str)] = &[
    (1, "java/lang/ArithmeticException"),
    (2, "java/lang/NegativeArraySizeException"),
    (3, "java/lang/OutOfMemoryError"),
    (4, "java/lang/NullPointerException"),
    (5, "java/lang/ArrayIndexOutOfBoundsException"),
    (6, "java/lang/ArrayStoreException"),
    (7, "java/lang/VerifyError"),
    (8, "java/lang/ExceptionInInitializerError"),
    (9, "java/lang/NoClassDefFoundError"),
    (10, "java/lang/StackOverflowError"),
    (11, "java/lang/StringIndexOutOfBoundsException"),
    (12, "java/lang/ClassCastException"),
    (13, "java/lang/IncompatibleClassChangeError"),
    (14, "java/lang/AbstractMethodError"),
    (15, "java/lang/IllegalAccessError"),
    (17, "java/lang/IllegalMonitorStateException"),
    (18, "java/lang/IllegalArgumentException"),
    (19, "java/lang/ClassNotFoundException"),
    (20, "java/lang/UnsatisfiedLinkError"),
    (21, "java/io/IOException"),
    (22, "java/io/SyncFailedException"),
    (23, "java/lang/InternalError"),
    (24, "java/lang/InstantiationException"),
    (25, "java/lang/IllegalAccessException"),
    (26, "java/lang/NoSuchMethodException"),
    (27, "java/lang/reflect/InvocationTargetException"),
    (28, "java/lang/NoSuchFieldException"),
];
pub(super) fn required(method: &Method) -> Result<bool> {
    let Some(code) = &method.code else {
        return Ok(false);
    };
    Ok(!code.handlers.is_empty()
        || super::exceptions::boundaries(&code.bytes)?
            .iter()
            .any(|pc| matches!(code.bytes[*pc], 0xbf | 0xc2 | 0xc3)))
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Field {
    pub name: String,
    pub offset: usize,
    pub width: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Factory {
    pub kind: u32,
    pub class_id: usize,
    pub type_id: usize,
    pub origin: ClassOrigin,
    pub fields: Vec<Field>,
    pub default_message: Option<usize>,
    pub name_literal: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Diagnostic {
    pub method: usize,
    pub pc: usize,
    pub literal: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub context_bytes: usize,
    pub external_bridge_bytes: usize,
    pub class_state_abi: u32,
    pub throwable_type: usize,
    pub error_type: usize,
    pub throwable_class: usize,
    pub suppressed_field: usize,
    pub stack_field: usize,
    pub factories: Vec<Factory>,
    pub diagnostics: Vec<Diagnostic>,
    pub npe_bindings: std::collections::BTreeMap<u16, ClassOrigin>,
}
pub(super) fn fields(class_name: &str, layout: &numeric::ObjectLayout) -> Result<Vec<Field>> {
    let mut result = Vec::new();
    for (name, descriptor) in [
        ("backtrace", "Ljava/lang/Object;"),
        ("depth", "I"),
        ("detailMessage", "Ljava/lang/String;"),
        ("cause", "Ljava/lang/Throwable;"),
        ("stackTrace", "[Ljava/lang/StackTraceElement;"),
        ("suppressedExceptions", "Ljava/util/List;"),
    ] {
        let f = layout
            .fields
            .iter()
            .find(|f| {
                f.name == name
                    && f.descriptor == descriptor
                    && f.declaring_class.as_deref() == Some("java/lang/Throwable")
            })
            .context("Missing VM Throwable field declared by java.lang.Throwable")?;
        let width = f.storage_bytes.unwrap_or(8);
        ensure!(
            matches!(width, 4 | 8)
                && f.offset % width == 0
                && f.offset
                    .checked_add(width)
                    .is_some_and(|end| end <= layout.payload_bytes)
                && if descriptor == "I" {
                    matches!(width, 4 | 8) && f.offset >= layout.reference_prefix_fields * 8
                } else {
                    width == 8 && f.offset < layout.reference_prefix_fields * 8
                },
            "Invalid VM Throwable field storage"
        );
        result.push(Field {
            name: name.into(),
            offset: f.offset,
            width,
        });
    }
    for f in &layout.fields {
        if f.declaring_class.as_deref() == Some("java/lang/Throwable") {
            continue;
        }
        ensure!(
            (f.declaring_class.as_deref() == Some("java/lang/NullPointerException")
                && matches!(
                    (f.name.as_str(), f.descriptor.as_str()),
                    ("extendedMessageState", "I") | ("extendedMessage", "Ljava/lang/String;")
                ))
                || (class_name == "java/lang/reflect/InvocationTargetException"
                    && f.declaring_class.as_deref() == Some(class_name)
                    && f.name == "target"
                    && f.descriptor == "Ljava/lang/Throwable;"),
            "VM builtin {} has additional state requiring a dedicated factory",
            class_name
        );
        result.push(Field {
            name: f.name.clone(),
            offset: f.offset,
            width: f.storage_bytes.unwrap_or(8),
        });
        let width = f.storage_bytes.unwrap_or(8);
        ensure!(
            matches!(width, 4 | 8)
                && f.offset % width == 0
                && f.offset
                    .checked_add(width)
                    .is_some_and(|end| end <= layout.payload_bytes)
                && if f.descriptor == "I" {
                    matches!(width, 4 | 8) && f.offset >= layout.reference_prefix_fields * 8
                } else {
                    width == 8 && f.offset < layout.reference_prefix_fields * 8
                },
            "Invalid additional NPE field layout"
        );
    }
    Ok(result)
}
pub(super) fn factory(
    registry: &mut types::Registry<'_>,
    kind: u32,
    class_id: usize,
    class: &ClassFile,
    origin: &ClassOrigin,
    layout: &ProgramObjectLayout,
    literals: (Option<usize>, usize),
) -> Result<Factory> {
    ensure!(
        KINDS.contains(&(kind, class.name.as_str())) && layout.class_name == class.name,
        "VM exception kind/class/layout mismatch"
    );
    let id = registry.class("bootstrap", &class.name)?;
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
        "VM exception factory requires its original public bootstrap class"
    );
    let root = registry.class("bootstrap", "java/lang/Throwable")?;
    ensure!(
        registry.assignable(id, root),
        "VM exception factory type is not Throwable"
    );
    Ok(Factory {
        kind,
        class_id,
        type_id: id,
        origin: origin.clone(),
        fields: fields(&class.name, &layout.layout)?,
        default_message: literals.0,
        name_literal: literals.1,
    })
}
impl Plan {
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        ensure!(
            self.abi == 1
                && self.context_bytes == 32
                && self.external_bridge_bytes == 16
                && self.class_state_abi == 2,
            "Unsupported exception program ABI"
        );
        out.push_str("EXTERN boom_exception_prepare:PROC\nEXTERN boom_exception_materialize:PROC\nEXTERN boom_exception_set32:PROC\nEXTERN boom_exception_match32:PROC\nEXTERN boom_exception_take32:PROC\nEXTERN boom_class_ensure32:PROC\nEXTERN boom_exception_npe_message:PROC\n.const\nALIGN 8\nboom_exception_factories LABEL BYTE\n");
        for f in &self.factories {
            let field = |name: &str| f.fields.iter().find(|f| f.name == name);
            let off = |name: &str| field(name).map_or(u32::MAX as usize, |f| f.offset);
            let message = f.default_message.unwrap_or(u32::MAX as usize);
            out.push_str(&format!("    DWORD {}, 0\n    QWORD OFFSET boom_layout{}, OFFSET boom_class{}, OFFSET boom_t{}\n    DWORD {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, 0\n",f.kind,f.class_id,f.class_id,f.type_id,off("backtrace"),off("depth"),field("depth").unwrap().width,off("detailMessage"),off("cause"),off("stackTrace"),off("suppressedExceptions"),off("extendedMessageState"),off("extendedMessage"),message,f.name_literal));
        }
        out.push_str("ALIGN 8\nboom_exception_diagnostics LABEL DWORD\n");
        if self.diagnostics.is_empty() {
            out.push_str("    DWORD 0, 0, 0, 0\n");
        }
        for d in &self.diagnostics {
            out.push_str(&format!(
                "    DWORD {}, {}, {}, 0\n",
                d.method, d.pc, d.literal
            ));
        }
        out.push_str(&format!(".data\nALIGN 8\nboom_exception_vm DWORD 04558564Dh, 1, 0, 0\n    QWORD OFFSET boom_heap_ptr, OFFSET boom_throwable_plan, OFFSET boom_runtime_type_map, OFFSET boom_t{}, OFFSET boom_t{}, OFFSET boom_exception_factories\n    DWORD {}, 0\n    QWORD OFFSET boom_exception_java_bootstrap, OFFSET boom_s{}_{}, OFFSET boom_s{}_{}, OFFSET boom_emergency_oom_root, OFFSET boom_emergency_stack_root\n    QWORD OFFSET boom_exception_diagnostics, OFFSET boom_string_pool, OFFSET boom_trace_pool\n    DWORD {}, 0\n    QWORD OFFSET boom_class{}, 0\n.code\n",self.throwable_type,self.error_type,self.factories.len(),self.throwable_class,self.suppressed_field,self.throwable_class,self.stack_field,self.diagnostics.len(),self.throwable_class));
        out.push_str(&format!("boom_exception_java_bootstrap PROC FRAME\n    sub rsp, 40\n    .allocstack 40\n    .endprolog\n    mov rdx, rcx\n    lea rcx, boom_class{}\n    call boom_class_ensure32\n    add rsp, 40\n    ret\nboom_exception_java_bootstrap ENDP\nPUBLIC boom_get_exception_vm\nboom_get_exception_vm PROC\n    lea rax, boom_exception_vm\n    ret\nboom_get_exception_vm ENDP\n",self.throwable_class));
        Ok(())
    }
}

pub(super) fn diagnostic(class: &ClassFile, code: &[u8], pc: usize) -> Result<Option<String>> {
    let op = code[pc];
    let value = match op {
        0x2e..=0x35 => "Cannot load from a null array".into(),
        0x4f..=0x56 => "Cannot store into a null array".into(),
        0xbe => "Cannot read the length of a null array".into(),
        0xbf => "Cannot throw a null exception".into(),
        0xc2 => "Cannot enter a monitor because the reference is null".into(),
        0xc3 => "Cannot exit a monitor because the reference is null".into(),
        0xb4 | 0xb5 => {
            let constant = u16::from_be_bytes([code[pc + 1], code[pc + 2]]);
            let (owner, name, _) = class.field_reference(constant)?;
            format!(
                "Cannot {} field \"{}.{}\" because the receiver is null",
                if op == 0xb4 { "read" } else { "assign" },
                owner.replace('/', "."),
                name
            )
        }
        0xb6 | 0xb7 | 0xb9 => {
            let constant = u16::from_be_bytes([code[pc + 1], code[pc + 2]]);
            let (owner, name, descriptor) = if op == 0xb9 {
                class.interface_method_reference(constant)?
            } else if op == 0xb7 {
                let (o, n, d, _) = class.special_method_reference(constant)?;
                (o, n, d)
            } else {
                class.method_reference(constant)?
            };
            if name == "<init>" {
                return Ok(None);
            }
            format!(
                "Cannot invoke \"{}.{}{}\" because the receiver is null",
                owner.replace('/', "."),
                name,
                descriptor
            )
        }
        _ => return Ok(None),
    };
    Ok(Some(value))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn layout() -> numeric::ObjectLayout {
        let mut fields = Vec::new();
        for (i, (name, descriptor)) in [
            ("backtrace", "Ljava/lang/Object;"),
            ("detailMessage", "Ljava/lang/String;"),
            ("cause", "Ljava/lang/Throwable;"),
            ("stackTrace", "[Ljava/lang/StackTraceElement;"),
            ("suppressedExceptions", "Ljava/util/List;"),
            ("depth", "I"),
        ]
        .into_iter()
        .enumerate()
        {
            fields.push(numeric::FieldLayout {
                name: name.into(),
                descriptor: descriptor.into(),
                offset: i * 8,
                declaring_class: Some("java/lang/Throwable".into()),
                declaring_field: Some(i),
                storage_bytes: Some(if i == 5 { 4 } else { 8 }),
            });
        }
        numeric::ObjectLayout {
            abi: 2,
            payload_bytes: 48,
            reference_prefix_fields: 5,
            fields,
        }
    }
    #[test]
    fn vm_exception_fields_reject_untracked_references_and_malformed_widths() {
        let l = layout();
        assert!(fields("java/lang/ArithmeticException", &l).is_ok());
        for (index, width, offset) in [
            (0, 0, 0),
            (0, 4, 0),
            (5, 8, 44),
            (5, 4, 0),
            (0, 8, usize::MAX),
        ] {
            let mut bad = l.clone();
            bad.fields[index].storage_bytes = Some(width);
            bad.fields[index].offset = offset;
            assert!(fields("java/lang/ArithmeticException", &bad).is_err());
        }
        let mut foreign = l.clone();
        foreign.fields[2].declaring_class = Some("application/Shadow".into());
        assert!(fields("java/lang/ArithmeticException", &foreign).is_err());
        let mut extra = l;
        let mut f = extra.fields[0].clone();
        f.name = "extra".into();
        f.declaring_class = Some("java/lang/ArithmeticException".into());
        extra.fields.push(f);
        assert!(fields("java/lang/ArithmeticException", &extra).is_err());
    }
    #[test]
    fn npe_private_state_uses_reference_prefix_and_scalar_tail() {
        let mut l = layout();
        l.fields[5].offset = 48;
        l.reference_prefix_fields = 6;
        l.payload_bytes = 56;
        for (name, descriptor, offset, width) in [
            ("extendedMessage", "Ljava/lang/String;", 40, 8),
            ("extendedMessageState", "I", 52, 4),
        ] {
            l.fields.push(numeric::FieldLayout {
                name: name.into(),
                descriptor: descriptor.into(),
                offset,
                declaring_class: Some("java/lang/NullPointerException".into()),
                declaring_field: None,
                storage_bytes: Some(width),
            });
        }
        assert!(fields("java/lang/NullPointerException", &l).is_ok());
        l.fields[6].offset = 48;
        assert!(fields("java/lang/NullPointerException", &l).is_err());
        l.fields[6].offset = 40;
        l.fields[7].storage_bytes = Some(0);
        assert!(fields("java/lang/NullPointerException", &l).is_err());
    }
}
