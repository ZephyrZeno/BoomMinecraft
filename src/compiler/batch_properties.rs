//! Source-normal SystemProps.Raw: shared Windows queries and frozen VM config.
use super::{
    batch_catalog::Catalog,
    batch_class_state,
    batch_compile::{AssemblyUnit, Symbols, write_unit},
    batch_literals::StringShape,
    batch_metadata, system_properties,
    translation_plan::Artifact,
    vm_properties,
};
use crate::{files, lock::InputLock};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt::Write as _,
    fs,
    io::{BufRead, BufReader, Read, Write},
    path::Path,
};
use zip::{ZipArchive, ZipWriter, write::SimpleFileOptions};

#[derive(Serialize)]
pub struct Method {
    pub method: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub operation: u32,
    pub assembly_unit: usize,
}
#[derive(Serialize)]
pub struct Row {
    pub name: String,
    pub index: usize,
    pub query: u32,
    pub argument: u32,
}
#[derive(Serialize)]
pub struct Pair {
    pub name: String,
    pub key_literal: usize,
    pub value_literal: usize,
}
#[derive(Serialize, Deserialize)]
pub struct Text {
    pub id: usize,
    pub utf16: Vec<u16>,
    pub java_hash: u32,
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub pool_abi: u32,
    pub native_methods: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub array_type: usize,
    pub canonical_strings: usize,
    pub root_cells: usize,
    pub platform_properties: usize,
    pub vm_pairs: usize,
    pub vm_profile: vm_properties::Profile,
    pub kernel_sha256: BTreeMap<String, String>,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub raw_class_initialization_executed: bool,
    pub original_raw_constructor_executed: bool,
    pub full_system_initialization_executed: bool,
    pub automatic_gc: bool,
    pub linked: bool,
}
pub(super) fn body(method: usize, class: usize, op: u32) -> String {
    let (pool, service) = if op == 0 {
        (
            "boom_java_platform_properties_pool",
            "boom_platform_properties",
        )
    } else {
        ("boom_java_vm_properties_pool", "boom_vm_properties")
    };
    format!(
        ".code\nboom_m{method} PROC FRAME\n sub rsp,56\n .allocstack 56\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n test rcx,rcx\n jz boom_m{method}_zero\n cmp DWORD PTR [rcx],0\n jne boom_m{method}_zero\n lea rcx,boom_class{class}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz boom_m{method}_zero\n mov rcx,QWORD PTR [rsp+32]\n mov rdx,QWORD PTR [rsp+40]\n call boom_m{method}_native\n add rsp,56\n ret\nboom_m{method}_zero:\n xor eax,eax\n add rsp,56\n ret\nboom_m{method} ENDP\nboom_m{method}_native PROC\n test rcx,rcx\n jz boom_m{method}_raw_zero\n cmp DWORD PTR [rcx],0\n jne boom_m{method}_raw_zero\n lea r8,{pool}\n jmp {service}\nboom_m{method}_raw_zero:\n xor eax,eax\n ret\nboom_m{method}_native ENDP\n"
    )
}
pub(super) fn data(
    shape: &StringShape,
    array: usize,
    rows: &[Row],
    pairs: &[Pair],
    texts: &[Text],
    fallbacks: &[usize],
) -> Result<String> {
    let n = texts.len();
    let callbacks = " QWORD OFFSET boom_java_property_array,OFFSET boom_java_property_copy,OFFSET boom_java_property_literal,OFFSET boom_java_string_literal\n";
    let mut out = format!(
        ".data?\nALIGN 8\nPUBLIC boom_java_properties_roots\nboom_java_properties_roots QWORD ?\nproperty_java_string_roots QWORD {} DUP(?)\nproperty_java_string_states DWORD {n} DUP(?)\n.const\nPUBLIC boom_java_properties_root_count\nboom_java_properties_root_count QWORD {}\nproperty_java_platform_rows LABEL DWORD\n",
        n * 2,
        n * 2 + 1
    );
    for row in rows {
        writeln!(out, " DWORD {},{},{},0", row.index, row.query, row.argument)?;
    }
    out.push_str("property_java_fallbacks LABEL DWORD\n");
    for id in fallbacks {
        writeln!(out, " DWORD {id}")?;
    }
    out.push_str("property_java_vm_rows LABEL DWORD\n");
    for row in pairs {
        writeln!(out, " DWORD {},{}", row.key_literal, row.value_literal)?;
    }
    out.push_str("ALIGN 8\nproperty_java_string_entries LABEL BYTE\n");
    for t in texts {
        writeln!(
            out,
            " QWORD OFFSET property_java_text_{}\n DWORD {},0{:08X}h",
            t.id,
            t.utf16.len(),
            t.java_hash
        )?;
    }
    for t in texts {
        writeln!(out, "ALIGN 2\nproperty_java_text_{} LABEL WORD", t.id)?;
        if t.utf16.is_empty() {
            out.push_str(" WORD 0\n");
        }
        for chunk in t.utf16.chunks(16) {
            out.push_str(" WORD ");
            for (i, u) in chunk.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write!(out, "0{u:04X}h")?;
            }
            out.push('\n');
        }
    }
    write!(
        out,
        ".data\nALIGN 8\nPUBLIC boom_java_platform_properties_pool\nboom_java_platform_properties_pool DWORD 050524F50h,2,0,0\n QWORD OFFSET boom_heap_ptr,OFFSET property_java_string_pool,OFFSET boom_t{array},OFFSET boom_java_properties_roots,OFFSET property_java_platform_rows\n DWORD {},0\n QWORD OFFSET property_java_fallbacks,0\n",
        rows.len()
    )?;
    out.push_str(callbacks);
    write!(
        out,
        "PUBLIC boom_java_vm_properties_pool\nboom_java_vm_properties_pool DWORD 0564D5052h,2,{},0\n QWORD OFFSET boom_heap_ptr,OFFSET property_java_string_pool,OFFSET boom_t{array},OFFSET property_java_vm_rows,0,0,0,0\n",
        pairs.len()
    )?;
    out.push_str(callbacks);
    write!(
        out,
        "PUBLIC boom_java_properties_string_pool\nboom_java_properties_string_pool LABEL BYTE\nproperty_java_string_pool DWORD 04A534C50h,1,{n},1\n QWORD OFFSET property_java_string_entries,OFFSET property_java_string_roots,OFFSET property_java_string_states,OFFSET boom_layout{}\n DWORD {},{},{},{}\n QWORD 0\n DWORD 0,0\n",
        shape.class_id,
        shape.value_offset,
        shape.coder_offset,
        shape.hash_offset,
        shape.hash_is_zero_offset
    )?;
    Ok(out)
}
fn zip_rows<T: serde::de::DeserializeOwned>(path: &str, name: &str) -> Result<Vec<T>> {
    let mut zip = ZipArchive::new(fs::File::open(path)?)?;
    let mut text = String::new();
    zip.by_name(name)?.read_to_string(&mut text)?;
    text.lines()
        .map(|line| Ok(serde_json::from_str(line)?))
        .collect()
}
pub(super) fn generate(
    inputs: &InputLock,
    catalog: &Catalog,
    shape: &StringShape,
    metadata: &batch_metadata::Summary,
    states: &batch_class_state::Summary,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    let id = catalog.lookup("bootstrap", system_properties::OWNER)?;
    let node = &catalog.nodes[id];
    ensure!(
        node.origin.source_id == "jdk:java.base" && node.origin.generated.is_none(),
        "Raw properties require original java.base source"
    );
    let mut archive = ZipArchive::new(fs::File::open(&states.index.path)?)?;
    let mut found = None;
    for line in BufReader::new(archive.by_name("classes.jsonl")?).lines() {
        let state: serde_json::Value = serde_json::from_str(&line?)?;
        if state["class_id"] == id {
            found = Some(state);
            break;
        }
    }
    let state = found.context("Missing Raw source state")?;
    ensure!(
        state["initializer"].is_null(),
        "Raw initializer requires explicit dependency integration"
    );
    let mut constants = BTreeMap::new();
    for f in state["fields"].as_array().context("Missing Raw fields")? {
        let name = f["name"].as_str().context("Missing Raw field name")?;
        if name == "FIXED_LENGTH" || name.ends_with("_NDX") {
            ensure!(
                f["access"] == 0x1a && f["descriptor"] == "I" && f["constant"].is_u64(),
                "Raw source field contract changed"
            );
            constants.insert(
                name.to_string(),
                f["initial_bits"].as_u64().context("Raw index missing")? as usize,
            );
        }
    }
    ensure!(
        constants.remove("FIXED_LENGTH") == Some(39) && constants.len() == 39,
        "Raw indexed schema changed"
    );
    let mut canonical = BTreeMap::<Vec<u16>, usize>::new();
    let mut literal = |s: &str| {
        canonical.entry(s.encode_utf16().collect()).or_default();
    };
    for s in system_properties::FALLBACKS {
        literal(s);
    }
    for name in constants.keys() {
        if let Some(s) = system_properties::query(name)?.2 {
            literal(s);
        }
    }
    let profile = vm_properties::Profile::for_image(inputs, output)?;
    let values = profile.values()?;
    for (k, v) in &values {
        literal(k);
        literal(v);
    }
    for (i, (_, v)) in canonical.iter_mut().enumerate() {
        *v = i;
    }
    let lookup = |s: &str| -> usize { canonical[&s.encode_utf16().collect::<Vec<_>>()] };
    let mut rows = Vec::new();
    for (name, index) in constants {
        let (q, a, s) = system_properties::query(&name)?;
        rows.push(Row {
            name,
            index,
            query: q,
            argument: s.map_or(a as usize, lookup) as u32,
        });
    }
    rows.sort_by_key(|r| r.index);
    ensure!(
        rows.iter().enumerate().all(|(i, r)| i == r.index),
        "Raw indices not contiguous"
    );
    let fallbacks: Vec<_> = system_properties::FALLBACKS
        .iter()
        .map(|s| lookup(s))
        .collect();
    let pairs: Vec<_> = values
        .iter()
        .map(|(k, v)| Pair {
            name: k.clone(),
            key_literal: lookup(k),
            value_literal: lookup(v),
        })
        .collect();
    let texts: Vec<_> = canonical
        .into_iter()
        .map(|(utf16, id)| {
            let java_hash = utf16
                .iter()
                .fold(0u32, |h, u| h.wrapping_mul(31).wrapping_add(u32::from(*u)));
            Text {
                id,
                utf16,
                java_hash,
            }
        })
        .collect();
    let types = zip_rows::<batch_metadata::TypeRecord>(&metadata.index.path, "types.jsonl")?;
    let array = types
        .iter()
        .find(|t| t.name == "[Ljava/lang/String;" && t.defining_loader == "bootstrap")
        .context("Missing source String[] type")?;
    ensure!(
        array.kind == 3 && array.parent_component == Some(shape.class_id),
        "String[] component source differs"
    );
    let mut assembly = data(shape, array.id, &rows, &pairs, &texts, &fallbacks)?;
    let mut methods = Vec::new();
    let mut provided = BTreeSet::new();
    for (op, name) in [(0, "platformProperties"), (1, "vmProperties")] {
        let (i, m) = node
            .methods
            .iter()
            .enumerate()
            .find(|(_, m)| m.name == name && m.descriptor == system_properties::DESCRIPTOR)
            .context("Missing source Raw native")?;
        ensure!(m.access == 0x10a, "Raw native access changed");
        let method = node.method_ids[i];
        assembly.push_str(&body(method, id, op));
        provided.insert(method);
        methods.push(Method {
            method,
            class_id: id,
            class_sha256: node.origin.sha256.clone(),
            name: name.into(),
            descriptor: system_properties::DESCRIPTOR.into(),
            access: m.access,
            operation: op,
            assembly_unit: 0,
        });
    }
    let directory = output.join("properties");
    fs::create_dir_all(&directory)?;
    let unit = write_unit(
        &Symbols::new()?,
        &directory.join("0000.asm"),
        0,
        &assembly,
        assemble,
    )?;
    let path = directory.join("index.zip");
    let mut temporary = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut zip = ZipWriter::new(temporary.as_file_mut());
        let options =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, records) in [
            ("methods.jsonl", serde_json::to_value(&methods)?),
            ("platform.jsonl", serde_json::to_value(&rows)?),
            ("vm.jsonl", serde_json::to_value(&pairs)?),
            ("strings.jsonl", serde_json::to_value(&texts)?),
        ] {
            zip.start_file(name, options)?;
            for r in records.as_array().context("Invalid property rows")? {
                serde_json::to_writer(&mut zip, r)?;
                zip.write_all(b"\n")?;
            }
        }
        zip.start_file("fallbacks.json", options)?;
        serde_json::to_writer(&mut zip, &fallbacks)?;
        zip.finish()?;
    }
    temporary.persist(&path).map_err(|e| e.error)?;
    Ok((
        Summary {
            abi: 1,
            context_bytes: 32,
            pool_abi: 2,
            native_methods: 2,
            class_id: id,
            class_sha256: node.origin.sha256.clone(),
            array_type: array.id,
            canonical_strings: texts.len(),
            root_cells: 1 + texts.len() * 2,
            platform_properties: 39,
            vm_pairs: pairs.len(),
            vm_profile: profile,
            kernel_sha256: BTreeMap::from([
                (
                    "native/runtime/system_properties.asm".into(),
                    files::digest_bytes(include_bytes!(
                        "../../native/runtime/system_properties.asm"
                    ))
                    .sha256,
                ),
                (
                    "native/runtime/vm_properties.asm".into(),
                    files::digest_bytes(include_bytes!("../../native/runtime/vm_properties.asm"))
                        .sha256,
                ),
                (
                    "native/runtime/java_properties.asm".into(),
                    files::digest_bytes(include_bytes!("../../native/runtime/java_properties.asm"))
                        .sha256,
                ),
            ]),
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units: vec![unit],
            raw_class_initialization_executed: false,
            original_raw_constructor_executed: false,
            full_system_initialization_executed: false,
            automatic_gc: false,
            linked: false,
        },
        provided,
    ))
}
