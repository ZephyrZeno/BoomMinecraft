//! Source-bound String constants for the bulk backend. All guest code is MASM.
//! These factories use ordinary Java String fields, not the legacy VM String ABI.
use super::{
    batch_catalog::{Catalog, Layout},
    batch_compile::{ASSEMBLY_BODY_BUDGET, AssemblyBodies, AssemblyUnit, Symbols, write_unit},
    batch_types::Universe,
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{collections::BTreeMap, fmt::Write as _, fs, io::Write, path::Path};
use zip::{ZipWriter, write::SimpleFileOptions};

pub(super) struct Request {
    pub class_id: usize,
    pub constant: u16,
    pub utf16: Vec<u16>,
}
#[derive(Clone, Serialize)]
pub struct StringShape {
    pub class_id: usize,
    pub source_sha256: String,
    pub payload_bytes: usize,
    pub reference_prefix: usize,
    pub fields: usize,
    pub value_offset: usize,
    pub coder_offset: usize,
    pub hash_offset: usize,
    pub hash_is_zero_offset: usize,
    pub field_maps: Vec<StringFieldMap>,
}
#[derive(Clone, Serialize)]
pub struct StringFieldMap {
    pub symbol: String,
    pub declaring_field: usize,
    pub offset: usize,
}
impl StringShape {
    fn from_source(catalog: &Catalog, layouts: &[Layout], universe: &Universe) -> Result<Self> {
        let id = catalog.lookup("bootstrap", "java/lang/String")?;
        let node = &catalog.nodes[id];
        ensure!(
            node.origin.source_id == "jdk:java.base" && node.access & 0x10 != 0,
            "Literal factory requires original final java.base String"
        );
        let row = &layouts[id];
        let layout = row
            .candidate
            .as_ref()
            .context("Missing source String layout")?;
        ensure!(
            layout.class == id
                && layout.reference_prefix == 1
                && layout.fields.len() == 4
                && (14..=32).contains(&layout.payload_bytes),
            "Unsupported source String layout"
        );
        let field =
            |name: &str, descriptor: &str, bytes: usize, reference: bool| -> Result<usize> {
                let fields: Vec<_> = layout
                    .fields
                    .iter()
                    .filter(|f| {
                        f.member.owner == id
                            && f.member.name == name
                            && f.member.descriptor == descriptor
                            && f.storage_bytes == bytes
                            && f.reference == reference
                    })
                    .collect();
                ensure!(fields.len() == 1, "Invalid source String field {name}");
                Ok(fields[0].offset)
            };
        let shape = Self {
            class_id: id,
            source_sha256: row.source_sha256.clone(),
            payload_bytes: layout.payload_bytes,
            reference_prefix: layout.reference_prefix,
            fields: layout.fields.len(),
            value_offset: field("value", "[B", 8, true)?,
            coder_offset: field("coder", "B", 1, false)?,
            hash_offset: field("hash", "I", 4, false)?,
            hash_is_zero_offset: field("hashIsZero", "Z", 1, false)?,
            field_maps: layout
                .fields
                .iter()
                .map(|slot| StringFieldMap {
                    symbol: format!(
                        "boom_field_map{}",
                        universe.field_ids[id] + slot.member.index
                    ),
                    declaring_field: slot.member.index,
                    offset: slot.offset,
                })
                .collect(),
        };
        ensure!(
            shape.value_offset == 0,
            "String reference must occupy the traced prefix"
        );
        Ok(shape)
    }
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub canonical_strings: usize,
    pub source_bindings: usize,
    pub compact_strings: bool,
    pub entry_page_size: usize,
    pub root_cells: usize,
    pub source_layout: StringShape,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub general_string_intern: bool,
    pub original_string_java_bodies_executed: bool,
    pub automatic_gc: bool,
    pub linked: bool,
}
#[derive(Serialize)]
struct Canonical<'a> {
    id: usize,
    utf16: &'a [u16],
    java_hash: u32,
}
#[derive(Serialize)]
struct Binding {
    class_id: usize,
    constant: u16,
    canonical: usize,
    symbol: String,
}
fn java_hash(units: &[u16]) -> u32 {
    units.iter().fold(0u32, |hash, unit| {
        hash.wrapping_mul(31).wrapping_add(u32::from(*unit))
    })
}
fn resolver(class_id: usize, constant: u16) -> String {
    format!("boom_batch_literal_load_{class_id}_{constant}")
}

pub(super) fn generate(
    catalog: &Catalog,
    layouts: &[Layout],
    universe: &Universe,
    mut requests: Vec<Request>,
    output: &Path,
    assemble: bool,
) -> Result<Summary> {
    let shape = StringShape::from_source(catalog, layouts, universe)?;
    requests.sort_by_key(|r| (r.class_id, r.constant));
    ensure!(
        requests
            .windows(2)
            .all(|p| (p[0].class_id, p[0].constant) != (p[1].class_id, p[1].constant)),
        "Duplicate source literal identity"
    );
    let mut canonical = BTreeMap::<Vec<u16>, usize>::new();
    for request in &requests {
        ensure!(
            request.utf16.len() <= 65535,
            "String constant exceeds class-file bound"
        );
        canonical.entry(request.utf16.clone()).or_default();
    }
    for (id, (_, value)) in canonical.iter_mut().enumerate() {
        *value = id;
    }
    let count = canonical.len();
    ensure!(
        (1..=0x100000).contains(&count),
        "Unsupported canonical String count"
    );
    let directory = output.join("string-literals");
    fs::create_dir_all(&directory)?;
    let index_path = directory.join("index.zip");
    let mut temp = tempfile::NamedTempFile::new_in(&directory)?;
    let mut bodies = AssemblyBodies::new(ASSEMBLY_BODY_BUDGET);
    let pages = count.div_ceil(256);
    let mut header = format!(
        ".data\nALIGN 8\nPUBLIC boom_layout{class}\nboom_layout{class} DWORD 04F424A43h,2\n QWORD {bytes}\n DWORD 1,4\n\
         PUBLIC boom_heap_ptr\nboom_heap_ptr QWORD 0\nPUBLIC boom_java_string_literal_pool\n\
         boom_java_string_literal_pool DWORD 04A534C50h,1,{count},1\n\
          QWORD OFFSET boom_java_string_literal_pages,OFFSET boom_java_string_literal_roots,OFFSET boom_java_string_literal_states,OFFSET boom_layout{class}\n\
          DWORD {value},{coder},{hash},{zero}\n QWORD 0\n DWORD 1,0\n\
         PUBLIC boom_java_string_literal_root_count\nboom_java_string_literal_root_count QWORD {root_cells}\n\
         boom_java_string_literal_pages LABEL QWORD\n",
        class = shape.class_id,
        bytes = shape.payload_bytes,
        value = shape.value_offset,
        coder = shape.coder_offset,
        hash = shape.hash_offset,
        zero = shape.hash_is_zero_offset,
        root_cells = count * 2
    );
    for page in 0..pages {
        writeln!(header, " QWORD OFFSET boom_java_string_literal_page_{page}")?;
    }
    writeln!(
        header,
        ".data?\nALIGN 8\nPUBLIC boom_java_string_literal_roots\nboom_java_string_literal_roots QWORD {} DUP(?)\nboom_java_string_literal_states DWORD {count} DUP(?)\n.code",
        count * 2
    )?;
    header.push_str(BIND_HEAP);
    // String is final: the source-bound layout is the sole valid receiver tag.
    // Return a checked address, preserving compact widths in the Java emitter.
    for field in &shape.field_maps {
        let symbol = &field.symbol;
        writeln!(
            header,
            "{symbol} PROC FRAME\n sub rsp,40\n .allocstack 40\n .endprolog\n mov r8,rdx\n lea rdx,boom_layout{}\n call boom_object_check\n test rax,rax\n jz {symbol}_done\n add rax,{}\n{symbol}_done:\n add rsp,40\n ret\n{symbol} ENDP",
            shape.class_id, field.offset
        )?;
    }
    bodies.push(&header);
    {
        let mut zip = ZipWriter::new(temp.as_file_mut());
        let options = SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .compression_level(Some(1));
        zip.start_file("canonical.jsonl", options)?;
        let rows: Vec<_> = canonical.iter().collect();
        for (page, group) in rows.chunks(256).enumerate() {
            let mut metadata = format!(
                ".const\nALIGN 8\nPUBLIC boom_java_string_literal_page_{page}\nboom_java_string_literal_page_{page} LABEL BYTE\n"
            );
            for (units, id) in group {
                let hash = java_hash(units);
                writeln!(
                    metadata,
                    " QWORD OFFSET boom_java_string_literal_text_{id}\n DWORD {},0{hash:08X}h",
                    units.len()
                )?;
                serde_json::to_writer(
                    &mut zip,
                    &Canonical {
                        id: **id,
                        utf16: units,
                        java_hash: hash,
                    },
                )?;
                zip.write_all(b"\n")?;
                let mut text = format!(
                    ".const\nALIGN 2\nPUBLIC boom_java_string_literal_text_{id}\nboom_java_string_literal_text_{id} LABEL WORD\n"
                );
                if units.is_empty() {
                    text.push_str(" WORD 0\n");
                }
                for chunk in units.chunks(16) {
                    text.push_str(" WORD ");
                    for (at, unit) in chunk.iter().enumerate() {
                        if at != 0 {
                            text.push(',');
                        }
                        write!(text, "0{unit:04X}h")?;
                    }
                    text.push('\n');
                }
                bodies.push(&text);
            }
            bodies.push(&metadata);
        }
        zip.start_file("bindings.jsonl", options)?;
        for request in &requests {
            let id = canonical[&request.utf16];
            let symbol = resolver(request.class_id, request.constant);
            bodies.push(&format!(".code\n{symbol} PROC\n lea rdx,boom_java_string_literal_pool\n mov r8d,{id}\n jmp boom_java_string_literal\n{symbol} ENDP\n"));
            serde_json::to_writer(
                &mut zip,
                &Binding {
                    class_id: request.class_id,
                    constant: request.constant,
                    canonical: id,
                    symbol,
                },
            )?;
            zip.write_all(b"\n")?;
        }
        zip.finish()?;
    }
    temp.persist(&index_path).map_err(|e| e.error)?;
    // The shared writer derives boom_* externals; preserve only OS declarations here.
    let kernel = include_str!("../../native/kernels/java_string_literals.inc")
        .lines()
        .filter(|line| !line.starts_with("EXTERN boom_") && !line.starts_with("PUBLIC boom_"))
        .collect::<Vec<_>>()
        .join("\n");
    bodies.push(&kernel);
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
        abi: 1,
        canonical_strings: count,
        source_bindings: requests.len(),
        compact_strings: true,
        entry_page_size: 256,
        root_cells: count * 2,
        source_layout: shape,
        index: Artifact {
            path: index_path.display().to_string(),
            digest: files::digest(&index_path)?,
        },
        units,
        general_string_intern: false,
        original_string_java_bodies_executed: false,
        automatic_gc: false,
        linked: false,
    })
}

// One immutable pool belongs to one heap lifetime. A second heap is rejected;
// recycling the same address after destruction is outside this ABI's lifetime.
const BIND_HEAP: &str = "boom_java_string_literals_bind_heap PROC\n\
 test rcx,rcx\n jz boom_literal_bind_bad\n cmp DWORD PTR [rcx],048454150h\n jne boom_literal_bind_bad\n\
 cmp DWORD PTR [rcx+4],1\n jne boom_literal_bind_bad\n xor eax,eax\n\
 lock cmpxchg QWORD PTR [boom_java_string_literal_pool+64],rcx\n je boom_literal_bind_good\n\
 cmp rax,rcx\n jne boom_literal_bind_bad\nboom_literal_bind_good:\n mov QWORD PTR [boom_heap_ptr],rcx\n\
 mov eax,1\n ret\nboom_literal_bind_bad:\n xor eax,eax\n ret\nboom_java_string_literals_bind_heap ENDP\n";

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn java_hash_keeps_utf16_code_units_and_wraps() {
        assert_eq!(java_hash(&[]), 0);
        assert_eq!(java_hash(&[0x41, 0x61]), java_hash(&[0x42, 0x42]));
        assert_eq!(java_hash(&[0xd83d, 0xde00]), 1772899);
        assert_eq!(java_hash(&[65535; 65535]), 2_787_146_719);
    }
}
