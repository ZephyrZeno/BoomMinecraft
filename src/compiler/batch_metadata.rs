//! Source-bound runtime type/layout/field metadata for bulk-generated Java code.
//! No host-language guest execution: lookup and field-address code is MASM.
use super::{
    batch_catalog::{Catalog, Layout},
    batch_compile::{ASSEMBLY_BODY_BUDGET, AssemblyBodies, AssemblyUnit, Symbols, write_unit},
    batch_types::Universe,
    symbolic::JavaType,
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{collections::BTreeMap, fmt::Write as _, fs, io::Write, path::Path};
use zip::{ZipWriter, write::SimpleFileOptions};

#[derive(Serialize, serde::Deserialize)]
pub struct TypeRecord {
    pub id: usize,
    pub kind: u32,
    pub marker_flags: u32,
    pub parent_component: Option<usize>,
    pub ancestors: Vec<usize>,
    pub defining_loader: String,
    pub name: String,
    pub source_sha256: Option<String>,
}
#[derive(Serialize)]
pub struct RuntimeRow {
    pub tag_symbol: Option<String>,
    pub primitive_tag: Option<u32>,
    pub type_id: usize,
    pub kind: u32,
    pub payload_bytes: usize,
    pub reference_prefix: usize,
    pub shift: usize,
}
#[derive(Serialize)]
pub struct FieldMap {
    pub id: usize,
    pub declaring_class: usize,
    pub declaring_field: usize,
    pub storage_bytes: usize,
    pub reference: bool,
    pub rows: Vec<FieldRow>,
}
#[derive(Serialize)]
pub struct FieldRow {
    pub receiver_class: usize,
    pub offset: usize,
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub type_capacity: usize,
    pub provided_types: usize,
    pub runtime_rows: usize,
    pub hash_slots: usize,
    pub field_capacity: usize,
    pub provided_field_maps: usize,
    pub receiver_offsets: usize,
    pub layouts: usize,
    pub omitted_classes: Vec<usize>,
    pub omitted_arrays: Vec<usize>,
    pub string_layout_owned_by_literal_module: usize,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub linked: bool,
    pub class_initialization_provided: bool,
    pub java_constructors_executed: bool,
    pub automatic_gc: bool,
}

const PRIMITIVES: [&str; 9] = ["Z", "B", "C", "S", "I", "J", "F", "D", "V"];
fn array_component(
    catalog: &Catalog,
    universe: &Universe,
    loader: &str,
    text: &str,
) -> Result<usize> {
    let component = text.strip_prefix('[').context("Missing array prefix")?;
    if component.starts_with('[') {
        return universe.array_id(catalog, loader, &JavaType::field(component)?);
    }
    if let Some(name) = component
        .strip_prefix('L')
        .and_then(|c| c.strip_suffix(';'))
    {
        return catalog.lookup(loader, name);
    }
    Ok(catalog.nodes.len()
        + universe.arrays.len()
        + PRIMITIVES
            .iter()
            .position(|p| *p == component)
            .context("Invalid primitive component")?)
}

pub(super) fn generate(
    catalog: &Catalog,
    layouts: &[Layout],
    universe: &Universe,
    output: &Path,
    assemble: bool,
) -> Result<Summary> {
    let string_id = catalog.lookup("bootstrap", "java/lang/String")?;
    let primitives_start = catalog.nodes.len() + universe.arrays.len();
    let type_capacity = primitives_start + PRIMITIVES.len();
    ensure!(
        type_capacity <= 0x100000,
        "Runtime source type capacity exceeded"
    );
    let mut types = BTreeMap::<usize, TypeRecord>::new();
    let mut runtime = vec![];
    let mut maps = BTreeMap::<usize, FieldMap>::new();
    let mut omitted_classes = vec![];
    let mut bodies = AssemblyBodies::new(ASSEMBLY_BODY_BUDGET);
    for node in &catalog.nodes {
        if node.access & 0x8000 != 0 || node.hierarchy_error.is_some() {
            omitted_classes.push(node.id);
            continue;
        }
        let ancestors = catalog
            .ancestors(node.id)?
            .iter()
            .copied()
            .filter(|id| *id != node.id)
            .collect();
        let marker_flags = if node.key.loader == "bootstrap" {
            match node.key.name.as_str() {
                "java/lang/Object" => 1,
                "java/lang/Cloneable" => 2,
                "java/io/Serializable" => 4,
                _ => 0,
            }
        } else {
            0
        };
        types.insert(
            node.id,
            TypeRecord {
                id: node.id,
                kind: if node.access & 0x200 != 0 { 2 } else { 1 },
                marker_flags,
                parent_component: node.superclass,
                ancestors,
                defining_loader: node.key.loader.clone(),
                name: node.key.name.clone(),
                source_sha256: Some(node.origin.sha256.clone()),
            },
        );
        let Some(layout) = layouts[node.id].candidate.as_ref() else {
            continue;
        };
        runtime.push(RuntimeRow {
            tag_symbol: Some(format!("boom_layout{}", node.id)),
            primitive_tag: None,
            type_id: node.id,
            kind: 0,
            payload_bytes: layout.payload_bytes,
            reference_prefix: layout.reference_prefix,
            shift: 0,
        });
        if node.id != string_id {
            bodies.push(&format!(".const\nALIGN 8\nPUBLIC boom_layout{0}\nboom_layout{0} DWORD 04F424A43h,2\n QWORD {1}\n DWORD {2},{3}\n",node.id,layout.payload_bytes,layout.reference_prefix,layout.fields.len()));
        }
        for slot in &layout.fields {
            // The v86 literal module owns these four proven final-String maps.
            if slot.member.owner == string_id {
                continue;
            }
            let id = universe.field_ids[slot.member.owner] + slot.member.index;
            let map = maps.entry(id).or_insert_with(|| FieldMap {
                id,
                declaring_class: slot.member.owner,
                declaring_field: slot.member.index,
                storage_bytes: slot.storage_bytes,
                reference: slot.reference,
                rows: vec![],
            });
            ensure!(
                map.storage_bytes == slot.storage_bytes && map.reference == slot.reference,
                "Inconsistent source field storage"
            );
            map.rows.push(FieldRow {
                receiver_class: node.id,
                offset: slot.offset,
            });
        }
    }
    for (index, name) in PRIMITIVES.iter().enumerate() {
        let id = primitives_start + index;
        types.insert(
            id,
            TypeRecord {
                id,
                kind: 0,
                marker_flags: index as u32,
                parent_component: None,
                ancestors: vec![],
                defining_loader: "bootstrap".into(),
                name: (*name).into(),
                source_sha256: None,
            },
        );
    }
    let mut omitted_arrays = vec![];
    // Resolve arrays by increasing dimensions so every component is either
    // source-proven already or the whole unresolved array remains an external.
    let mut arrays: Vec<_> = universe.arrays.iter().collect();
    arrays.sort_by_key(|a| a.descriptor.bytes().take_while(|b| *b == b'[').count());
    for array in arrays {
        let Ok(component) =
            array_component(catalog, universe, &array.defining_loader, &array.descriptor)
        else {
            omitted_arrays.push(array.id);
            continue;
        };
        if !types.contains_key(&component) {
            omitted_arrays.push(array.id);
            continue;
        }
        let primitive = types[&component].kind == 0;
        types.insert(
            array.id,
            TypeRecord {
                id: array.id,
                kind: 3,
                marker_flags: 0,
                parent_component: Some(component),
                ancestors: vec![],
                defining_loader: array.defining_loader.clone(),
                name: array.descriptor.clone(),
                source_sha256: None,
            },
        );
        let primitive_index = component.saturating_sub(primitives_start);
        let (tag, shift) = if primitive {
            ensure!(primitive_index < 8, "Void array is invalid");
            (
                [260, 264, 261, 265, 266, 267, 262, 263][primitive_index],
                [0, 0, 1, 1, 2, 3, 2, 3][primitive_index],
            )
        } else {
            (0, 3)
        };
        runtime.push(RuntimeRow {
            tag_symbol: (!primitive).then(|| format!("boom_t{}", array.id)),
            primitive_tag: primitive.then_some(tag),
            type_id: array.id,
            kind: if primitive { 1 } else { 2 },
            payload_bytes: 0,
            reference_prefix: 0,
            shift,
        });
    }
    omitted_arrays.sort_unstable();
    runtime.sort_by_key(|r| r.type_id);
    for ty in types.values() {
        let id = ty.id;
        let component = ty
            .parent_component
            .map_or("0".into(), |id| format!("OFFSET boom_t{id}"));
        let ancestors = if ty.ancestors.is_empty() {
            "0".into()
        } else {
            format!("OFFSET boom_ancestors{id}")
        };
        let mut body = format!(
            ".const\nALIGN 8\nPUBLIC boom_t{id}\nboom_t{id} DWORD 054595045h,1,{kind},{flags}\n QWORD {component},{ancestors}\n DWORD {count},0\n",
            kind = ty.kind,
            flags = ty.marker_flags,
            count = ty.ancestors.len()
        );
        ensure!(
            ty.ancestors.len() <= 4096,
            "Runtime ancestor budget exceeded"
        );
        if !ty.ancestors.is_empty() {
            writeln!(body, "boom_ancestors{id} LABEL QWORD")?;
            for ancestor in &ty.ancestors {
                writeln!(body, " QWORD OFFSET boom_t{ancestor}")?;
            }
        }
        bodies.push(&body);
    }
    let field_capacity = catalog.nodes.iter().map(|n| n.fields.len()).sum::<usize>();
    let hash_slots = (runtime.len() * 2).max(16).next_power_of_two();
    ensure!(
        hash_slots <= 0x200000,
        "Runtime hash table exceeds ABI2 capacity"
    );
    let mut globals = format!(
        ".data\nALIGN 8\nPUBLIC boom_runtime_type_map\nboom_runtime_type_map DWORD 052545950h,2,{rows},{type_capacity}\n QWORD OFFSET boom_batch_runtime_rows,0,OFFSET boom_batch_runtime_slots\n DWORD {mask},0\n.const\nPUBLIC boom_batch_type_descriptors\nboom_batch_type_descriptors LABEL QWORD\n",
        rows = runtime.len(),
        mask = hash_slots - 1
    );
    for id in 0..type_capacity {
        writeln!(
            globals,
            " QWORD {}",
            if types.contains_key(&id) {
                format!("OFFSET boom_t{id}")
            } else {
                "0".into()
            }
        )?;
    }
    globals.push_str("PUBLIC boom_batch_field_records\nboom_batch_field_records LABEL QWORD\n");
    for id in 0..field_capacity {
        writeln!(
            globals,
            " QWORD {}",
            if maps.contains_key(&id) {
                format!("OFFSET boom_batch_field_record{id}")
            } else {
                "0".into()
            }
        )?;
    }
    writeln!(
        globals,
        ".data?\nALIGN 8\nboom_batch_runtime_slots QWORD {hash_slots} DUP(?)"
    )?;
    bodies.push(&globals);
    // Row table is one source-bound contiguous block, kept as an atomic body.
    let mut rows = String::from(
        ".const\nALIGN 8\nPUBLIC boom_batch_runtime_rows\nboom_batch_runtime_rows LABEL BYTE\n",
    );
    for row in &runtime {
        let tag = row.tag_symbol.as_ref().map_or_else(
            || row.primitive_tag.unwrap().to_string(),
            |tag| format!("OFFSET {tag}"),
        );
        writeln!(
            rows,
            " QWORD {tag},OFFSET boom_t{}\n DWORD {},{}\n QWORD {}\n DWORD {},{}",
            row.type_id, row.type_id, row.kind, row.payload_bytes, row.reference_prefix, row.shift
        )?;
    }
    // Physical Row40 data is at most 40 MiB; its assembly can be larger than
    // the usual function-body budget. A later segmented row ABI can split it.
    bodies.push(&rows);
    for map in maps.values() {
        let id = map.id;
        let mut body = format!(
            ".const\nALIGN 8\nPUBLIC boom_batch_field_record{id}\nboom_batch_field_record{id} DWORD 0464D4150h,1,{count},{bytes},{reference},0\n QWORD OFFSET boom_batch_field_rows{id}\nboom_batch_field_rows{id} LABEL DWORD\n",
            count = map.rows.len(),
            bytes = map.storage_bytes,
            reference = u32::from(map.reference)
        );
        for row in &map.rows {
            writeln!(body, " DWORD {},{}", row.receiver_class, row.offset)?;
        }
        writeln!(
            body,
            ".code\nboom_field_map{id} PROC\n lea r8,boom_batch_field_record{id}\n lea r9,boom_runtime_type_map\n jmp boom_field_address\nboom_field_map{id} ENDP"
        )?;
        bodies.push(&body);
    }
    let directory = output.join("runtime-metadata");
    fs::create_dir_all(&directory)?;
    let index_path = directory.join("index.zip");
    let mut temp = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut zip = ZipWriter::new(temp.as_file_mut());
        let options = SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .compression_level(Some(1));
        macro_rules! rows {
            ($name:literal,$rows:expr) => {{
                zip.start_file($name, options)?;
                for row in $rows {
                    serde_json::to_writer(&mut zip, row)?;
                    zip.write_all(b"\n")?;
                }
            }};
        }
        rows!("types.jsonl", types.values());
        rows!("runtime.jsonl", &runtime);
        rows!("fields.jsonl", maps.values());
        zip.finish()?;
    }
    temp.persist(&index_path).map_err(|e| e.error)?;
    let symbols = Symbols::new()?;
    let mut units = vec![];
    for (id, body) in bodies.parts.into_iter().enumerate() {
        units.push(write_unit(
            &symbols,
            &directory.join(format!("{id:04}.asm")),
            id,
            &body,
            assemble,
        )?);
    }
    Ok(Summary {
        abi: 2,
        type_capacity,
        provided_types: types.len(),
        runtime_rows: runtime.len(),
        hash_slots,
        field_capacity,
        provided_field_maps: maps.len(),
        receiver_offsets: maps.values().map(|m| m.rows.len()).sum(),
        layouts: runtime.iter().filter(|r| r.kind == 0).count(),
        omitted_classes,
        omitted_arrays,
        string_layout_owned_by_literal_module: string_id,
        index: Artifact {
            path: index_path.display().to_string(),
            digest: files::digest(&index_path)?,
        },
        units,
        linked: false,
        class_initialization_provided: false,
        java_constructors_executed: false,
        automatic_gc: false,
    })
}
