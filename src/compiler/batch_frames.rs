//! Source-bound ABI3 Java frames and the normal Reflection caller service.
use super::{
    batch_catalog::Catalog,
    batch_class_bootstrap::Method,
    batch_compile::{AssemblyUnit, MethodResult, Symbols, write_unit},
    batch_metadata,
    classfile::ClassFile,
    translation_plan::Artifact,
};
use crate::{bytecode::ClassOrigin, files, lock::InputLock};
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt::Write as _,
    fs,
    io::{Read, Write},
    path::Path,
};
use zip::{ZipArchive, ZipWriter, write::SimpleFileOptions};

#[derive(Serialize, Deserialize)]
pub struct FrameMethod {
    pub id: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub loader: String,
    pub source_id: String,
    pub class_name: String,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub code_sha256: Option<String>,
    pub code_length: usize,
    pub annotations: Vec<String>,
    pub flags: u32,
    pub assembly_emitted: bool,
}
fn wanted_native(owner: &str, name: &str, desc: &str) -> bool {
    matches!(
        (owner, name, desc),
        (
            "java/lang/Class",
            "forName0",
            "(Ljava/lang/String;ZLjava/lang/ClassLoader;Ljava/lang/Class;)Ljava/lang/Class;"
        ) | (
            "java/lang/ClassLoader",
            "findBootstrapClass",
            "(Ljava/lang/String;)Ljava/lang/Class;"
        ) | (
            "jdk/internal/reflect/Reflection",
            "getCallerClass",
            "()Ljava/lang/Class;"
        )
    )
}
pub(super) fn capture(
    catalog: &Catalog,
    class: &ClassFile,
    id: usize,
    origin: &ClassOrigin,
    results: &[MethodResult],
) -> Vec<FrameMethod> {
    let trusted = matches!(origin.loader.as_str(), "bootstrap" | "platform")
        && origin.source_id.starts_with("jdk:")
        && origin.generated.is_none();
    let mut accessor = false;
    let mut parent = Some(id);
    for _ in 0..catalog.nodes.len() {
        let Some(i) = parent else { break };
        let n = &catalog.nodes[i];
        if n.key.loader == "bootstrap"
            && n.key.name == "jdk/internal/reflect/MethodAccessorImpl"
            && n.origin.source_id == "jdk:java.base"
        {
            accessor = true;
            break;
        }
        parent = n.superclass;
    }
    class
        .methods
        .iter()
        .enumerate()
        .filter(|(_, m)| m.code.is_some() || wanted_native(&class.name, &m.name, &m.descriptor))
        .map(|(index, m)| {
            let annotated =
                |name: &str| trusted && m.runtime_visible_annotations.iter().any(|a| a == name);
            let mh = trusted
                && class.name == "java/lang/invoke/MethodHandle"
                && matches!(
                    m.name.as_str(),
                    "invoke"
                        | "invokeExact"
                        | "invokeBasic"
                        | "linkToVirtual"
                        | "linkToStatic"
                        | "linkToSpecial"
                        | "linkToInterface"
                        | "linkToNative"
                );
            let ignore = accessor
                || (trusted
                    && class.name == "java/lang/reflect/Method"
                    && m.name == "invoke"
                    && m.descriptor == "(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;")
                || mh
                || annotated("Ljava/lang/invoke/LambdaForm$Compiled;");
            let flags = u32::from(m.name == "<init>")
                | (u32::from(m.name == "fillInStackTrace") << 1)
                | (u32::from(origin.generated.is_some()) << 2)
                | (u32::from(annotated("Ljdk/internal/reflect/CallerSensitive;")) << 3)
                | (u32::from(annotated("Ljdk/internal/vm/annotation/Hidden;")) << 4)
                | (u32::from(m.access & 0x100 != 0) << 5)
                | (u32::from(ignore) << 6);
            FrameMethod {
                id: catalog.nodes[id].method_ids[index],
                class_id: id,
                class_sha256: origin.sha256.clone(),
                loader: origin.loader.clone(),
                source_id: origin.source_id.clone(),
                class_name: class.name.clone(),
                name: m.name.clone(),
                descriptor: m.descriptor.clone(),
                access: m.access,
                code_sha256: m
                    .code
                    .as_ref()
                    .map(|c| files::digest_bytes(&c.bytes).sha256),
                code_length: m.code.as_ref().map_or(0, |c| c.bytes.len()),
                annotations: m.runtime_visible_annotations.clone(),
                flags,
                assembly_emitted: results[index].assembly_emitted,
            }
        })
        .collect()
}
pub(super) fn source_methods(catalog: &Catalog) -> Result<Vec<Method>> {
    let class_id = catalog.lookup("bootstrap", "jdk/internal/reflect/Reflection")?;
    let c = &catalog.nodes[class_id];
    ensure!(
        c.origin.source_id == "jdk:java.base" && c.origin.generated.is_none(),
        "Caller native requires original java.base Reflection"
    );
    let found: Vec<_> = c
        .methods
        .iter()
        .enumerate()
        .filter(|(_, m)| m.name == "getCallerClass" && m.descriptor == "()Ljava/lang/Class;")
        .collect();
    ensure!(
        found.len() == 1 && found[0].1.access == 0x109,
        "Original caller declaration changed"
    );
    Ok(vec![Method {
        method: c.method_ids[found[0].0],
        class_id,
        class_sha256: c.origin.sha256.clone(),
        name: "getCallerClass".into(),
        descriptor: "()Ljava/lang/Class;".into(),
        access: 0x109,
        operation: 0,
        assembly_unit: 1,
    }])
}
pub(super) fn native_adapter(
    id: usize,
    class: usize,
    pool: &str,
    service: &str,
    op: u32,
) -> String {
    format!(
        ".code\nboom_m{id} PROC FRAME\n sub rsp,120\n .allocstack 120\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n test rcx,rcx\n jz boom_m{id}_zero\n cmp DWORD PTR [rcx],0\n jne boom_m{id}_zero\n lea rcx,boom_class{class}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz boom_m{id}_zero\n mov rcx,QWORD PTR [rsp+32]\n cmp DWORD PTR [rcx+12],128\n jae boom_m{id}_limit\n inc DWORD PTR [rcx+12]\n mov QWORD PTR [rsp+56],0\n lea rcx,boom_trace_pool\n lea rdx,[rsp+56]\n lea r8,boom_trace_method{id}\n mov r9,QWORD PTR [rsp+32]\n call boom_trace_enter\n test eax,eax\n jnz boom_m{id}_entered_error\n mov rcx,QWORD PTR [rsp+32]\n mov rdx,QWORD PTR [rsp+40]\n call boom_m{id}_native\n jmp boom_m{id}_leave\nboom_m{id}_entered_error:\n xor eax,eax\nboom_m{id}_leave:\n mov QWORD PTR [rsp+48],rax\n lea rcx,boom_trace_pool\n lea rdx,[rsp+56]\n mov r8,QWORD PTR [rsp+32]\n call boom_trace_leave\n mov rcx,QWORD PTR [rsp+32]\n dec DWORD PTR [rcx+12]\n cmp DWORD PTR [rcx],0\n jne boom_m{id}_zero\n mov rax,QWORD PTR [rsp+48]\n add rsp,120\n ret\nboom_m{id}_limit:\n mov DWORD PTR [rcx],10\nboom_m{id}_zero:\n xor eax,eax\n add rsp,120\n ret\nboom_m{id} ENDP\nboom_m{id}_native PROC\n lea r8,{pool}\n mov r9d,{op}\n jmp {service}\nboom_m{id}_native ENDP\n"
    )
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub pool_bytes: usize,
    pub node_bytes: usize,
    pub method_row_bytes: usize,
    pub methods: usize,
    pub java_methods: usize,
    pub native_frame_methods: usize,
    pub generated_java_frames: usize,
    pub unavailable_declaring_types: usize,
    pub native_methods: usize,
    pub caller_pool_bytes: usize,
    pub original_system_catalog: Artifact,
    pub original_input_files: BTreeMap<String, Artifact>,
    pub kernel_sha256: BTreeMap<String, String>,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub every_emitted_java_method_traced: bool,
    pub native_upcall_frames: usize,
    pub all_native_frames: bool,
    pub stack_roots: bool,
    pub automatic_gc: bool,
    pub game_started: bool,
}
pub(super) fn generate(
    catalog: &Catalog,
    metadata: &batch_metadata::Summary,
    mut methods: Vec<FrameMethod>,
    inputs: &InputLock,
    jdk_path: &Path,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    methods.sort_by_key(|m| m.id);
    ensure!(
        !methods.is_empty()
            && methods.len() <= 1048576
            && methods.windows(2).all(|w| w[0].id < w[1].id),
        "Invalid frame source identities"
    );
    let mut z = ZipArchive::new(fs::File::open(&metadata.index.path)?)?;
    let mut data = String::new();
    z.by_name("types.jsonl")?.read_to_string(&mut data)?;
    let types: BTreeSet<_> = data
        .lines()
        .map(|l| Ok(serde_json::from_str::<batch_metadata::TypeRecord>(l)?.id))
        .collect::<Result<_>>()?;
    let mut unavailable = 0;
    for m in &mut methods {
        if !types.contains(&m.class_id) {
            m.flags |= 128;
            unavailable += 1;
        }
    }
    let natives = source_methods(catalog)?;
    let caller = &natives[0];
    let source = methods.iter().find(|m| m.id == caller.method).unwrap();
    ensure!(
        source.flags & 40 == 40 && source.code_length == 0,
        "Caller native lacks original CallerSensitive declaration"
    );
    let mut body =
        String::from(".const\nALIGN 8\nPUBLIC boom_trace_methods\nboom_trace_methods LABEL BYTE\n");
    for m in &methods {
        let declaring = if m.flags & 128 == 0 {
            format!("OFFSET boom_t{}", m.class_id)
        } else {
            "0".into()
        };
        writeln!(
            body,
            "PUBLIC boom_trace_method{}\nboom_trace_method{} DWORD {},{}\n QWORD {declaring}\n DWORD {},{}\n QWORD 0",
            m.id, m.id, m.id, m.flags, m.code_length, m.class_id
        )?;
    }
    writeln!(
        body,
        ".data\nALIGN 8\nPUBLIC boom_trace_pool\nboom_trace_pool DWORD 05452504Ch,3,0,0FFFFFFFFh\n DWORD {},0\n QWORD OFFSET boom_trace_methods,0,0\n.code\nPUBLIC boom_release_trace_pool\nboom_release_trace_pool PROC\n lea rcx,boom_trace_pool\n jmp boom_trace_release\nboom_release_trace_pool ENDP\n",
        methods.len()
    )?;
    let mut caller_body = format!(
        ".const\nALIGN 8\nPUBLIC boom_java_caller_pool\nboom_java_caller_pool DWORD 04A434352h,1\n QWORD OFFSET boom_java_class_pool,OFFSET boom_trace_pool\n DWORD {},{},32,32,0,0\n QWORD 0,0\n",
        caller.method, caller.class_id
    );
    caller_body.push_str(&native_adapter(
        caller.method,
        caller.class_id,
        "boom_java_caller_pool",
        "boom_java_caller",
        0,
    ));
    let directory = output.join("frames");
    fs::create_dir_all(&directory)?;
    let symbols = Symbols::new()?;
    let units = vec![
        write_unit(&symbols, &directory.join("0000.asm"), 0, &body, assemble)?,
        write_unit(
            &symbols,
            &directory.join("0001.asm"),
            1,
            &caller_body,
            assemble,
        )?,
    ];
    let path = directory.join("index.zip");
    let mut tmp = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut z = ZipWriter::new(tmp.as_file_mut());
        z.start_file(
            "methods.jsonl",
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )?;
        for m in &methods {
            serde_json::to_writer(&mut z, m)?;
            z.write_all(b"\n")?;
        }
        z.start_file(
            "natives.jsonl",
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )?;
        for m in &natives {
            serde_json::to_writer(&mut z, m)?;
            z.write_all(b"\n")?;
        }
        z.finish()?;
    }
    tmp.persist(&path).map_err(|e| e.error)?;
    let original_input_files = inputs
        .files
        .iter()
        .map(|f| {
            (
                f.id.clone(),
                Artifact {
                    path: f.path.display().to_string(),
                    digest: f.digest.clone(),
                },
            )
        })
        .collect();
    let kernels = [
        "frames.asm",
        "stack_probe.asm",
        "java_caller.asm",
        "java_classes.asm",
        "classes32.asm",
    ];
    let kernel_sha256 = kernels
        .into_iter()
        .map(|name| {
            let p = format!("native/runtime/{name}");
            Ok((p.clone(), files::digest(Path::new(&p))?.sha256))
        })
        .collect::<Result<_>>()?;
    let java = methods.iter().filter(|m| m.code_length > 0).count();
    let emitted = methods.iter().filter(|m| m.assembly_emitted).count();
    Ok((
        Summary {
            abi: 3,
            pool_bytes: 48,
            node_bytes: 48,
            method_row_bytes: 32,
            methods: methods.len(),
            java_methods: java,
            native_frame_methods: methods.len() - java,
            generated_java_frames: emitted,
            unavailable_declaring_types: unavailable,
            native_methods: 1,
            caller_pool_bytes: 64,
            original_system_catalog: Artifact {
                path: jdk_path.display().to_string(),
                digest: files::digest(jdk_path)?,
            },
            original_input_files,
            kernel_sha256,
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units,
            every_emitted_java_method_traced: true,
            native_upcall_frames: 2,
            all_native_frames: false,
            stack_roots: false,
            automatic_gc: false,
            game_started: false,
        },
        natives.iter().map(|m| m.method).collect(),
    ))
}
