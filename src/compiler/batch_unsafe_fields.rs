//! Source-declared field cookies and normal-layout address maps. No VM offsets
//! are guessed: the actual receiver selects the existing generated field map.
use super::{
    batch_catalog::Catalog,
    batch_class_bootstrap::{Method, native_adapter},
    batch_compile::{ASSEMBLY_BODY_BUDGET, AssemblyBodies, AssemblyUnit, Symbols, write_unit},
    batch_literals::StringShape,
    batch_metadata,
    batch_types::Universe,
    hierarchy,
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt::Write as _,
    fs,
    io::{BufRead, BufReader, Write},
    path::Path,
};
use zip::{ZipArchive, ZipWriter, write::SimpleFileOptions};

pub const COOKIE_TAG: u64 = 0x55464c4400000000;
pub const PAGE_FIELDS: usize = 1024;
const OWNER: &str = "jdk/internal/misc/Unsafe";

#[derive(Serialize)]
pub struct Field {
    pub id: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub field_index: usize,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub kind: u32,
    pub storage_bytes: usize,
    pub reference: bool,
    pub name_offset: usize,
    pub name_units: usize,
    pub address_map: Option<usize>,
}

#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub pool_bytes: usize,
    pub record_bytes: usize,
    pub page_fields: usize,
    pub pages: usize,
    pub type_capacity: usize,
    pub declared_fields: usize,
    pub instance_fields: usize,
    pub address_maps: usize,
    pub name_units: usize,
    pub native_methods: usize,
    pub source_native_declarations: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub cookie_tag: u64,
    pub kernel_sha256: BTreeMap<String, String>,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub target_class_initialization_required: bool,
    pub typed_memory_natives_provided: bool,
    pub original_initialization_executed: bool,
    pub game_started: bool,
}

pub(super) fn source_methods(catalog: &Catalog) -> Result<Vec<Method>> {
    let class_id = catalog.lookup("bootstrap", OWNER)?;
    let node = &catalog.nodes[class_id];
    ensure!(
        node.origin.source_id == "jdk:java.base"
            && node.origin.generated.is_none()
            && node.access == 0x31,
        "Unsafe field lookup requires original final java.base Unsafe"
    );
    let matches: Vec<_> = node
        .methods
        .iter()
        .enumerate()
        .filter(|(_, m)| {
            m.name == "objectFieldOffset1"
                && m.descriptor == "(Ljava/lang/Class;Ljava/lang/String;)J"
        })
        .collect();
    ensure!(
        matches.len() == 1 && matches[0].1.access == 0x102,
        "Original Unsafe field native differs"
    );
    Ok(vec![Method {
        method: node.method_ids[matches[0].0],
        class_id,
        class_sha256: node.origin.sha256.clone(),
        name: "objectFieldOffset1".into(),
        descriptor: "(Ljava/lang/Class;Ljava/lang/String;)J".into(),
        access: 0x102,
        operation: 0,
        assembly_unit: 0,
    }])
}

fn field_kind(descriptor: &str) -> Result<u32> {
    Ok(match descriptor {
        "Z" => 1,
        "B" => 2,
        "C" => 3,
        "S" => 4,
        "I" => 5,
        "J" => 6,
        "F" => 7,
        "D" => 8,
        text if text.starts_with(['L', '[']) => 9,
        _ => anyhow::bail!("Invalid source field descriptor"),
    })
}

pub(super) fn generate(
    catalog: &Catalog,
    universe: &Universe,
    metadata: &batch_metadata::Summary,
    string: &StringShape,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    let mut methods = source_methods(catalog)?;
    let class_id = methods[0].class_id;
    let mut maps = BTreeSet::new();
    let mut bundle = ZipArchive::new(fs::File::open(&metadata.index.path)?)?;
    for line in BufReader::new(bundle.by_name("fields.jsonl")?).lines() {
        let row: serde_json::Value = serde_json::from_str(&line?)?;
        ensure!(
            maps.insert(row["id"].as_u64().context("Missing source field map ID")? as usize),
            "Duplicate source field map"
        );
    }
    ensure!(
        maps.len() == metadata.provided_field_maps,
        "Field map coverage differs"
    );
    for map in &string.field_maps {
        let id = map
            .symbol
            .strip_prefix("boom_field_map")
            .context("Invalid String field map")?
            .parse::<usize>()?;
        ensure!(
            maps.insert(id),
            "String field map overlaps normal field metadata"
        );
    }
    let mut names = BTreeMap::<Vec<u16>, usize>::new();
    for node in &catalog.nodes {
        for field in &node.fields {
            names
                .entry(field.name.encode_utf16().collect())
                .or_default();
        }
    }
    let mut arena = vec![];
    for (name, offset) in &mut names {
        *offset = arena.len();
        arena.extend(name);
    }
    ensure!(
        !arena.is_empty() && arena.len() <= 0x1000000,
        "Unsafe field-name budget exceeded"
    );
    let mut fields = vec![];
    let mut ranges = vec![(0_usize, 0_usize); metadata.type_capacity];
    for node in &catalog.nodes {
        ensure!(
            universe.field_ids[node.id] == fields.len(),
            "Source field identity reordered"
        );
        ranges[node.id] = (fields.len(), node.fields.len());
        for (index, field) in node.fields.iter().enumerate() {
            let name: Vec<_> = field.name.encode_utf16().collect();
            ensure!(
                !name.is_empty() && name.len() <= 65535,
                "Invalid source field name"
            );
            let id = fields.len();
            let kind = field_kind(&field.descriptor)?;
            fields.push(Field {
                id,
                class_id: node.id,
                class_sha256: node.origin.sha256.clone(),
                field_index: index,
                name: field.name.clone(),
                descriptor: field.descriptor.clone(),
                access: field.access,
                kind,
                storage_bytes: hierarchy::storage_bytes(&field.descriptor)?,
                reference: kind == 9,
                name_offset: names[&name],
                name_units: name.len(),
                address_map: maps.contains(&id).then_some(id),
            });
        }
    }
    ensure!(
        fields.len() == metadata.field_capacity && fields.len() <= 0xffffff,
        "Source field capacity differs"
    );
    let pages = fields.len().div_ceil(PAGE_FIELDS);
    let mut bodies = AssemblyBodies::new(ASSEMBLY_BODY_BUDGET);
    let mut text = String::from(
        ".const\nALIGN 2\nPUBLIC boom_java_unsafe_field_names\nboom_java_unsafe_field_names LABEL WORD\n",
    );
    for part in arena.chunks(16) {
        writeln!(
            text,
            " WORD {}",
            part.iter()
                .map(u16::to_string)
                .collect::<Vec<_>>()
                .join(",")
        )?;
    }
    bodies.push(&text);
    text = String::from(
        ".const\nALIGN 8\nPUBLIC boom_java_unsafe_field_ranges\nboom_java_unsafe_field_ranges LABEL DWORD\n",
    );
    for (start, count) in &ranges {
        writeln!(text, " DWORD {start},{count}")?;
    }
    bodies.push(&text);
    text = String::from(
        ".const\nALIGN 8\nPUBLIC boom_java_unsafe_field_pages\nboom_java_unsafe_field_pages LABEL QWORD\n",
    );
    for page in 0..pages {
        writeln!(text, " QWORD OFFSET boom_java_unsafe_field_page{page}")?;
    }
    bodies.push(&text);
    for (page, rows) in fields.chunks(PAGE_FIELDS).enumerate() {
        text = format!(
            ".const\nALIGN 8\nPUBLIC boom_java_unsafe_field_page{page}\nboom_java_unsafe_field_page{page} LABEL BYTE\n"
        );
        for row in rows {
            let map = row
                .address_map
                .map_or_else(|| "0".into(), |id| format!("OFFSET boom_field_map{id}"));
            let flags = u32::from(row.reference) | if row.access & 8 != 0 { 2 } else { 0 };
            writeln!(
                text,
                " DWORD {},{},{},{}\n DWORD {},{},{},{flags}\n QWORD {map},0\n DWORD {},0\n QWORD 0",
                row.class_id,
                row.field_index,
                row.access,
                row.kind,
                row.name_offset,
                row.name_units,
                row.storage_bytes,
                row.id
            )?;
        }
        bodies.push(&text);
    }
    let pool = format!(
        ".const\nALIGN 8\nPUBLIC boom_java_unsafe_field_pool\nboom_java_unsafe_field_pool DWORD 055464D50h,1,{},{}\n QWORD OFFSET boom_heap_ptr,OFFSET boom_java_class_pool,OFFSET boom_runtime_type_map,OFFSET boom_layout{class_id}\n QWORD OFFSET boom_java_unsafe_pool,OFFSET boom_layout{}\n QWORD OFFSET boom_java_unsafe_field_names,OFFSET boom_java_unsafe_field_ranges,OFFSET boom_java_unsafe_field_pages\n DWORD {},{pages},{},{},{class_id},64\n QWORD 055464C4400000000h,0\n",
        metadata.type_capacity,
        fields.len(),
        string.class_id,
        arena.len(),
        string.value_offset,
        string.coder_offset
    );
    let adapter = native_adapter(
        methods[0].method,
        class_id,
        "boom_java_unsafe_field_pool",
        "boom_java_unsafe_field",
        0,
    );
    methods[0].assembly_unit = bodies.push(&(pool + &adapter));
    let directory = output.join("unsafe-fields");
    fs::create_dir_all(&directory)?;
    let symbols = Symbols::new()?;
    let units = bodies
        .parts
        .iter()
        .enumerate()
        .map(|(id, body)| {
            write_unit(
                &symbols,
                &directory.join(format!("{id:04}.asm")),
                id,
                body,
                assemble,
            )
        })
        .collect::<Result<Vec<_>>>()?;
    let path = directory.join("index.zip");
    let mut temporary = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut zip = ZipWriter::new(temporary.as_file_mut());
        let options =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        zip.start_file("methods.jsonl", options)?;
        for m in &methods {
            serde_json::to_writer(&mut zip, m)?;
            zip.write_all(b"\n")?;
        }
        zip.start_file("fields.jsonl", options)?;
        for f in &fields {
            serde_json::to_writer(&mut zip, f)?;
            zip.write_all(b"\n")?;
        }
        zip.start_file("names.json", options)?;
        serde_json::to_writer(&mut zip, &arena)?;
        zip.start_file("ranges.json", options)?;
        serde_json::to_writer(&mut zip, &ranges)?;
        zip.finish()?;
    }
    temporary.persist(&path).map_err(|e| e.error)?;
    let kernel_sha256 = [
        "java_unsafe_fields.asm",
        "field_address.asm",
        "java_unsafe.asm",
        "java_classes.asm",
        "objects.asm",
        "heap.asm",
    ]
    .into_iter()
    .map(|name| {
        let path = format!("native/runtime/{name}");
        Ok((path.clone(), files::digest(Path::new(&path))?.sha256))
    })
    .collect::<Result<_>>()?;
    let instance_fields = fields.iter().filter(|f| f.access & 8 == 0).count();
    let summary = Summary {
        abi: 1,
        context_bytes: 32,
        pool_bytes: 128,
        record_bytes: 64,
        page_fields: PAGE_FIELDS,
        pages,
        type_capacity: metadata.type_capacity,
        declared_fields: fields.len(),
        instance_fields,
        address_maps: maps.len(),
        name_units: arena.len(),
        native_methods: 1,
        source_native_declarations: catalog.nodes[class_id]
            .methods
            .iter()
            .filter(|m| m.access & 0x100 != 0)
            .count(),
        class_id,
        class_sha256: catalog.nodes[class_id].origin.sha256.clone(),
        cookie_tag: COOKIE_TAG,
        kernel_sha256,
        index: Artifact {
            path: path.display().to_string(),
            digest: files::digest(&path)?,
        },
        units,
        target_class_initialization_required: false,
        typed_memory_natives_provided: false,
        original_initialization_executed: false,
        game_started: false,
    };
    Ok((summary, methods.iter().map(|m| m.method).collect()))
}
