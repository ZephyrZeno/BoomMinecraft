//! Original System private native stream setters and their rooted field cells.
use super::{classfile::ClassFile, hierarchy, numeric, runtime_types, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum Operation {
    In = 0,
    Out = 1,
    Err = 2,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, desc: &str) -> Option<Self> {
        if owner != "java/lang/System" {
            return None;
        }
        [Self::In, Self::Out, Self::Err]
            .into_iter()
            .find(|op| op.name() == name && op.descriptor() == desc)
    }
    pub(super) fn name(self) -> &'static str {
        match self {
            Self::In => "setIn0",
            Self::Out => "setOut0",
            Self::Err => "setErr0",
        }
    }
    pub(super) fn descriptor(self) -> &'static str {
        match self {
            Self::In => "(Ljava/io/InputStream;)V",
            _ => "(Ljava/io/PrintStream;)V",
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Slot {
    pub operation: Operation,
    pub field: String,
    pub descriptor: String,
    pub field_index: usize,
    pub type_id: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Storage {
    pub type_id: usize,
    pub class_name: String,
    pub origins: Vec<ClassOrigin>,
    pub layout: numeric::ObjectLayout,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub operation: Operation,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub class_id: usize,
    pub slots: Vec<Slot>,
    pub storage: Vec<Storage>,
    pub bindings: Vec<Binding>,
    pub entry: Option<(usize, Operation)>,
    pub native_source_sha256: String,
    pub heap_source_sha256: String,
    pub runtime_types_source_sha256: String,
    pub types_source_sha256: String,
    pub automatic_gc: bool,
    pub completes_system_startup: bool,
}
fn original(registry: &mut types::Registry<'_>, name: &str) -> Result<(usize, ClassOrigin)> {
    let id = registry.class("bootstrap", name)?;
    let types::Type::Class { key, origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "System streams require original java.base definitions"
    );
    Ok((id, origin.as_ref().clone()))
}
pub(super) fn verify(class: &ClassFile, origin: &ClassOrigin) -> Result<()> {
    ensure!(
        class.name == "java/lang/System"
            && class.access & 0x611 == 0x11
            && origin.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "System streams require the original final bootstrap System"
    );
    for op in [Operation::In, Operation::Out, Operation::Err] {
        let m = class.method(op.name(), Some(op.descriptor()))?;
        ensure!(
            m.access == 0x10a && m.code.is_none(),
            "System private native stream declaration changed"
        );
    }
    Ok(())
}
impl Plan {
    pub(super) fn prepare(registry: &mut types::Registry<'_>, class_id: usize) -> Result<Self> {
        let (id, origin) = original(registry, "java/lang/System")?;
        let class = registry.definition(id).context("Missing System source")?;
        verify(class, &origin)?;
        let mut slots = Vec::new();
        for (op, name, desc) in [
            (Operation::In, "in", "Ljava/io/InputStream;"),
            (Operation::Out, "out", "Ljava/io/PrintStream;"),
            (Operation::Err, "err", "Ljava/io/PrintStream;"),
        ] {
            let index = class
                .field_info
                .iter()
                .position(|f| f.name == name && f.descriptor == desc)
                .context("Missing System stream field")?;
            ensure!(
                class.field_info[index].access == 0x19,
                "System stream field must retain public static final access"
            );
            slots.push(Slot {
                operation: op,
                field: name.into(),
                descriptor: desc.into(),
                field_index: index,
                type_id: 0,
            });
        }
        for slot in &mut slots {
            slot.type_id = registry.field("bootstrap", &slot.descriptor)?;
        }
        // VM storage views use the complete source-defined physical shapes. They
        // do not run constructors and are never claimed to be initialized streams.
        let mut storage = Vec::new();
        for name in ["java/io/ByteArrayInputStream", "java/io/PrintStream"] {
            let (ty, _) = original(registry, name)?;
            let layout = hierarchy::compact_layout(registry, ty)?;
            let mut origins = Vec::new();
            let mut current = Some(ty);
            while let Some(id) = current {
                let types::Type::Class {
                    key,
                    origin,
                    superclass,
                    ..
                } = &registry.types[id]
                else {
                    unreachable!()
                };
                ensure!(
                    key.loader == "bootstrap"
                        && origin.source_id == "jdk:java.base"
                        && origin.generated.is_none(),
                    "Stream storage ancestor changed"
                );
                origins.push(origin.as_ref().clone());
                current = *superclass;
            }
            let fields = layout
                .fields
                .iter()
                .map(|f| {
                    let types::Type::Class { key, .. } = &registry.types[f.member.owner] else {
                        unreachable!()
                    };
                    numeric::FieldLayout {
                        name: f.member.name.clone(),
                        descriptor: f.member.descriptor.clone(),
                        offset: f.offset,
                        declaring_class: Some(key.name.clone()),
                        declaring_field: Some(f.member.index),
                        storage_bytes: Some(f.storage_bytes),
                    }
                })
                .collect();
            storage.push(Storage {
                type_id: ty,
                class_name: name.into(),
                origins,
                layout: numeric::ObjectLayout {
                    abi: 2,
                    payload_bytes: layout.payload_bytes,
                    reference_prefix_fields: layout.reference_prefix,
                    fields,
                },
            });
        }
        Ok(Self {
            abi: 1,
            origin,
            class_id,
            slots,
            storage,
            bindings: Vec::new(),
            entry: None,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/system_streams.asm"
            ))
            .sha256,
            heap_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/heap.asm"
            ))
            .sha256,
            runtime_types_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/runtime_types.asm"
            ))
            .sha256,
            types_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/types.asm"
            ))
            .sha256,
            automatic_gc: false,
            completes_system_startup: false,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        origin: &ClassOrigin,
        constant: u16,
        operation: Operation,
    ) -> Result<()> {
        let (o, n, d, i) = caller.static_method_reference(constant)?;
        ensure!(
            !i && Operation::resolve(&o, &n, &d) == Some(operation)
                && caller.name == "java/lang/System"
                && origin == &self.origin,
            "System stream setters are private to the original System caller"
        );
        if !self
            .bindings
            .iter()
            .any(|b| b.caller == *origin && b.constant == constant)
        {
            self.bindings.push(Binding {
                caller: origin.clone(),
                constant,
                operation,
            });
            self.bindings.sort_by_key(|b| b.constant);
        }
        Ok(())
    }
    pub(super) fn extend_rows(&self, rows: &mut Vec<runtime_types::Binding>) {
        for (i, p) in self.storage.iter().enumerate() {
            rows.push(runtime_types::Binding {
                tag: format!("OFFSET boom_stream_storage{i}"),
                type_id: p.type_id,
                kind: 0,
                payload_bytes: p.layout.payload_bytes,
                references: p.layout.reference_prefix_fields,
                element_shift: 0,
            });
        }
    }
    pub(super) fn emit(&self, out: &mut String) {
        out.push_str("EXTERN boom_system_stream_set:PROC\n.const\nALIGN 8\nboom_system_stream_rows LABEL QWORD\n");
        for s in &self.slots {
            out.push_str(&format!(
                "    QWORD OFFSET boom_s{}_{}, OFFSET boom_t{}\n",
                self.class_id, s.field_index, s.type_id
            ));
        }
        out.push_str(&format!("ALIGN 8\nboom_system_stream_pool DWORD 053595349h, 1\n    QWORD OFFSET boom_class{}, OFFSET boom_heap_ptr, OFFSET boom_runtime_type_map, OFFSET boom_system_stream_rows\n    DWORD 3, 0\n    QWORD 0, 0\n",self.class_id));
        for (i, p) in self.storage.iter().enumerate() {
            out.push_str(&format!("ALIGN 8\nboom_stream_storage{i} DWORD 04F424A43h, 2\n    QWORD {}\n    DWORD {}, {}\n",p.layout.payload_bytes,p.layout.reference_prefix_fields,p.layout.fields.len()));
        }
        out.push_str(".code\nPUBLIC boom_get_system_stream_pool\nboom_get_system_stream_pool PROC\n    lea rax, boom_system_stream_pool\n    ret\nboom_get_system_stream_pool ENDP\nPUBLIC boom_get_stream_storage\nboom_get_stream_storage PROC\n");
        for i in 0..self.storage.len() {
            out.push_str(&format!(
                "    cmp ecx, {i}\n    je boom_stream_storage_get{i}\n"
            ));
        }
        out.push_str("    xor eax,eax\n    ret\n");
        for i in 0..self.storage.len() {
            out.push_str(&format!(
                "boom_stream_storage_get{i}:\n    lea rax, boom_stream_storage{i}\n    ret\n"
            ));
        }
        out.push_str("boom_get_stream_storage ENDP\n");
        if let Some((m, op)) = self.entry {
            out.push_str(&format!("; VM invocation of original private System native setter; not System startup.\nboom_m{m} PROC FRAME\n    sub rsp,72\n    .allocstack 72\n    .endprolog\n    mov QWORD PTR [rsp+40],rcx\n    mov QWORD PTR [rsp+48],rdx\n    cmp DWORD PTR [rcx],0\n    jne boom_stream_entry{m}_done\n    lea rcx,boom_class{}\n    mov rdx,QWORD PTR [rsp+40]\n    call boom_class_ensure\n    test eax,eax\n    jnz boom_stream_entry{m}_done\n    mov rcx,QWORD PTR [rsp+40]\n    mov rdx,QWORD PTR [rsp+48]\n    lea r8,boom_system_stream_pool\n    mov r9d,{}\n    call boom_system_stream_set\nboom_stream_entry{m}_done:\n    xor eax,eax\n    add rsp,72\n    ret\nboom_m{m} ENDP\n",self.class_id,op as u32));
        }
    }
}
