//! Original System native registration; generated envelopes execute MASM only.
//! This is System.<clinit> infrastructure, not System.initPhase1/2/3 completion.
use super::{
    batch_catalog::Catalog,
    batch_compile::{AssemblyUnit, Symbols, write_unit},
    hierarchy::Metadata,
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Write,
    path::Path,
};
use zip::{ZipWriter, write::SimpleFileOptions};

const SPECS: [(&str, &str, u16, Option<u32>); 7] = [
    ("registerNatives", "()V", 0x10a, None),
    ("currentTimeMillis", "()J", 0x109, Some(0)),
    ("nanoTime", "()J", 0x109, Some(1)),
    (
        "arraycopy",
        "(Ljava/lang/Object;ILjava/lang/Object;II)V",
        0x109,
        Some(2),
    ),
    ("setIn0", "(Ljava/io/InputStream;)V", 0x10a, Some(3)),
    ("setOut0", "(Ljava/io/PrintStream;)V", 0x10a, Some(4)),
    ("setErr0", "(Ljava/io/PrintStream;)V", 0x10a, Some(5)),
];
pub(super) const POOL: &str = ".const\nALIGN 8\nPUBLIC boom_batch_system_native_table\nboom_batch_system_native_table DWORD 05359534Dh,1,3,0\n QWORD OFFSET boom_vm_current_time_millis,OFFSET boom_vm_nano_time,OFFSET boom_system_arraycopy\n.data\nALIGN 8\nPUBLIC boom_batch_system_native_pool\nboom_batch_system_native_pool DWORD 053595350h,1\n QWORD 0,OFFSET boom_batch_system_native_table,OFFSET boom_runtime_type_map\n";
#[derive(Serialize)]
pub struct Method {
    pub method: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub operation: Option<u32>,
    pub assembly_unit: usize,
}
#[derive(Serialize)]
pub struct StreamSlot {
    pub operation: u32,
    pub field: String,
    pub descriptor: String,
    pub field_index: usize,
    pub type_id: usize,
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub pool_abi: u32,
    pub runtime_map_abi: u32,
    pub initial_registration_null: bool,
    pub class_id: usize,
    pub class_sha256: String,
    pub native_methods: usize,
    pub registered_methods: usize,
    pub stream_slots: Vec<StreamSlot>,
    pub stream_pool_unit: usize,
    pub kernel_sha256: BTreeMap<String, String>,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub linked: bool,
    pub system_class_initialization_executed: bool,
    pub system_boot_phases_completed: bool,
}
pub(super) fn body(method: usize, class: usize, operation: Option<u32>) -> String {
    let native = match operation {
        None => {
            "    lea r8,boom_batch_system_native_pool\n    jmp boom_system_register\n".to_string()
        }
        Some(index) if index >= 3 => format!(
            "    lea r8,boom_batch_system_stream_pool\n    mov r9d,{}\n    jmp boom_system_stream_set\n",
            index - 3
        ),
        Some(index) => format!(
            "    lea r8,boom_batch_system_native_pool\n    mov r9d,{index}\n    jmp boom_system_dispatch\n"
        ),
    };
    let argv = if operation.is_some_and(|index| index >= 2) {
        format!(
            "    test rdx,rdx\n    jnz boom_m{method}_native_ready\n    mov DWORD PTR [rcx],7\n    jmp boom_m{method}_native_zero\nboom_m{method}_native_ready:\n"
        )
    } else {
        String::new()
    };
    format!(
        ".code\nboom_m{method} PROC FRAME\n    sub rsp,72\n    .allocstack 72\n    .endprolog\n    mov QWORD PTR [rsp+48],rcx\n    mov QWORD PTR [rsp+56],rdx\n    test rcx,rcx\n    jz boom_m{method}_native_entry_zero\n    cmp DWORD PTR [rcx],0\n    jne boom_m{method}_native_entry_zero\n    lea rcx,boom_class{class}\n    mov rdx,QWORD PTR [rsp+48]\n    call boom_class_ensure32\n    test eax,eax\n    jnz boom_m{method}_native_entry_zero\n    mov rcx,QWORD PTR [rsp+48]\n    mov rdx,QWORD PTR [rsp+56]\n    call boom_m{method}_native\n    add rsp,72\n    ret\nboom_m{method}_native_entry_zero:\n    xor eax,eax\n    add rsp,72\n    ret\nboom_m{method} ENDP\nboom_m{method}_native PROC\n    test rcx,rcx\n    jz boom_m{method}_native_zero\n    cmp DWORD PTR [rcx],0\n    jne boom_m{method}_native_zero\n{argv}{native}boom_m{method}_native_zero:\n    xor eax,eax\n    ret\nboom_m{method}_native ENDP\n"
    )
}
pub(super) fn stream_pool(class: usize, slots: &[StreamSlot]) -> String {
    let mut out = String::from(
        ".const\nALIGN 8\nPUBLIC boom_batch_system_stream_rows\nboom_batch_system_stream_rows LABEL QWORD\n",
    );
    for slot in slots {
        out.push_str(&format!(
            " QWORD OFFSET boom_s{class}_{},OFFSET boom_t{}\n",
            slot.field_index, slot.type_id
        ));
    }
    out.push_str(&format!("PUBLIC boom_batch_system_stream_pool\nboom_batch_system_stream_pool DWORD 053595349h,1\n QWORD OFFSET boom_class{class},OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_batch_system_stream_rows\n DWORD 3,0\n QWORD 0,0\n"));
    out
}
pub(super) fn generate(
    catalog: &Catalog,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    let class = catalog.lookup("bootstrap", "java/lang/System")?;
    let node = &catalog.nodes[class];
    ensure!(
        node.origin.source_id == "jdk:java.base"
            && node.origin.generated.is_none()
            && node.access == 0x31
            && node.superclass == Some(catalog.root_object()?),
        "System native bindings require original final bootstrap System source"
    );
    let mut methods = vec![];
    let mut provided = BTreeSet::new();
    let mut assembly = POOL.to_string();
    let mut stream_slots = vec![];
    for (operation, (field, desc, target)) in [
        ("in", "Ljava/io/InputStream;", "java/io/InputStream"),
        ("out", "Ljava/io/PrintStream;", "java/io/PrintStream"),
        ("err", "Ljava/io/PrintStream;", "java/io/PrintStream"),
    ]
    .into_iter()
    .enumerate()
    {
        let (index, f) = node
            .fields
            .iter()
            .enumerate()
            .find(|(_, f)| f.name == field && f.descriptor == desc)
            .context("Missing original System stream field")?;
        ensure!(
            f.access == 0x19,
            "System stream field access differs from public static final"
        );
        stream_slots.push(StreamSlot {
            operation: operation as u32,
            field: field.into(),
            descriptor: desc.into(),
            field_index: index,
            type_id: catalog.lookup("bootstrap", target)?,
        });
    }
    assembly.push_str(&stream_pool(class, &stream_slots));
    for (name, descriptor, flags, operation) in SPECS {
        let (index, m) = node
            .methods
            .iter()
            .enumerate()
            .find(|(_, m)| m.name == name && m.descriptor == descriptor)
            .with_context(|| format!("Missing original System.{name}{descriptor}"))?;
        ensure!(
            m.access == flags,
            "Original System.{name} native access differs"
        );
        let id = node.method_ids[index];
        provided.insert(id);
        assembly.push_str(&body(id, class, operation));
        methods.push(Method {
            method: id,
            class_id: class,
            class_sha256: node.origin.sha256.clone(),
            name: name.into(),
            descriptor: descriptor.into(),
            access: flags,
            operation,
            assembly_unit: 0,
        });
    }
    let directory = output.join("system-natives");
    fs::create_dir_all(&directory)?;
    let unit = write_unit(
        &Symbols::new()?,
        &directory.join("0000.asm"),
        0,
        &assembly,
        assemble,
    )?;
    let path = directory.join("index.zip");
    let mut temp = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut zip = ZipWriter::new(temp.as_file_mut());
        zip.start_file(
            "methods.jsonl",
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )?;
        for method in methods {
            serde_json::to_writer(&mut zip, &method)?;
            zip.write_all(b"\n")?;
        }
        zip.finish()?;
    }
    temp.persist(&path).map_err(|e| e.error)?;
    let kernel_sha256 = BTreeMap::from([
        (
            "native/runtime/system.asm".into(),
            files::digest_bytes(include_bytes!("../../native/runtime/system.asm")).sha256,
        ),
        (
            "native/runtime/vm_clock.asm".into(),
            files::digest_bytes(include_bytes!("../../native/runtime/vm_clock.asm")).sha256,
        ),
        (
            "native/runtime/system_streams.asm".into(),
            files::digest_bytes(include_bytes!("../../native/runtime/system_streams.asm")).sha256,
        ),
    ]);
    Ok((
        Summary {
            abi: 2,
            context_bytes: 32,
            pool_abi: 1,
            runtime_map_abi: 2,
            initial_registration_null: true,
            class_id: class,
            class_sha256: node.origin.sha256.clone(),
            native_methods: 7,
            registered_methods: 3,
            stream_slots,
            stream_pool_unit: 0,
            kernel_sha256,
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units: vec![unit],
            linked: false,
            system_class_initialization_executed: false,
            system_boot_phases_completed: false,
        },
        provided,
    ))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_entries_initialize_source_class_and_keep_pending_error_guards() {
        let code = body(7, 2, Some(2));
        assert!(code.contains("lea rcx,boom_class2") && code.contains("call boom_class_ensure32"));
        assert!(code.contains("cmp DWORD PTR [rcx],0\n    jne boom_m7_native_zero"));
        assert!(code.contains("test rdx,rdx\n    jnz boom_m7_native_ready"));
        assert!(code.contains("mov r9d,2\n    jmp boom_system_dispatch"));
        assert!(!code.contains("mov DWORD PTR [rcx+4]"));
    }
    #[test]
    fn registration_calls_real_atomic_publication_not_empty_success() {
        let code = body(11, 2, None);
        assert!(
            code.contains("lea r8,boom_batch_system_native_pool\n    jmp boom_system_register")
        );
        assert!(POOL.contains(
            "QWORD 0,OFFSET boom_batch_system_native_table,OFFSET boom_runtime_type_map"
        ));
        assert!(POOL.contains("OFFSET boom_vm_current_time_millis,OFFSET boom_vm_nano_time,OFFSET boom_system_arraycopy"));
    }
    #[test]
    fn stream_entries_keep_argv_guards_and_point_to_original_rooted_cells() {
        let code = body(19, 2, Some(4));
        assert!(code.contains("test rdx,rdx\n    jnz boom_m19_native_ready"));
        assert!(code.contains(
            "lea r8,boom_batch_system_stream_pool\n    mov r9d,1\n    jmp boom_system_stream_set"
        ));
        let pool = stream_pool(
            2,
            &[StreamSlot {
                operation: 0,
                field: "in".into(),
                descriptor: "Ljava/io/InputStream;".into(),
                field_index: 4,
                type_id: 8,
            }],
        );
        assert!(pool.contains("QWORD OFFSET boom_s2_4,OFFSET boom_t8"));
        assert!(
            pool.contains("OFFSET boom_class2,OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map")
        );
    }
}
