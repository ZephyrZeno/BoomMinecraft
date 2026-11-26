//! Normal Class.name caches use the existing source-layout ASM String factory.
use super::{batch_literals, batch_metadata::TypeRecord};
use anyhow::{Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fmt::Write};

#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub types: usize,
    pub canonical_names: usize,
    pub source_literal_aliases: usize,
    pub root_cells: usize,
    pub source_string_class: usize,
    pub source_string_sha256: String,
    pub general_string_intern: bool,
}
#[derive(Serialize)]
pub struct Name {
    pub type_id: usize,
    pub canonical: usize,
}
#[derive(Serialize)]
pub struct Canonical {
    pub id: usize,
    pub utf16: Vec<u16>,
    pub java_hash: u32,
    pub literal: Option<usize>,
}
#[derive(Deserialize)]
struct Literal {
    id: usize,
    utf16: Vec<u16>,
}
fn name(ty: &TypeRecord) -> Result<Vec<u16>> {
    let text = if ty.kind == 0 {
        match ty.name.as_str() {
            "Z" => "boolean",
            "B" => "byte",
            "C" => "char",
            "S" => "short",
            "I" => "int",
            "J" => "long",
            "F" => "float",
            "D" => "double",
            "V" => "void",
            _ => bail!("Invalid primitive Class name"),
        }
        .into()
    } else {
        ty.name.replace('/', ".")
    };
    let value: Vec<u16> = text.encode_utf16().collect();
    ensure!(
        !value.is_empty() && value.len() <= 65535,
        "Class name exceeds factory budget"
    );
    Ok(value)
}
pub fn generate(
    types: &BTreeMap<usize, TypeRecord>,
    capacity: usize,
    offset: usize,
    strings: &batch_literals::Summary,
) -> Result<(Summary, String, Vec<Name>, Vec<Canonical>)> {
    let requested: BTreeMap<_, _> = types
        .values()
        .map(|t| Ok((t.id, name(t)?)))
        .collect::<Result<_>>()?;
    let mut canonical: BTreeMap<_, usize> = requested.values().cloned().map(|s| (s, 0)).collect();
    for (id, (_, value)) in canonical.iter_mut().enumerate() {
        *value = id;
    }
    let names: Vec<_> = requested
        .iter()
        .map(|(id, text)| Name {
            type_id: *id,
            canonical: canonical[text],
        })
        .collect();
    let string = &strings.source_layout;
    let mut archive = zip::ZipArchive::new(std::fs::File::open(&strings.index.path)?)?;
    use std::io::{BufRead, BufReader};
    let literals: BTreeMap<Vec<u16>, usize> = BufReader::new(archive.by_name("canonical.jsonl")?)
        .lines()
        .map(|line| -> Result<_> {
            let row: Literal = serde_json::from_str(&line?)?;
            Ok((row.utf16, row.id))
        })
        .collect::<Result<_>>()?;
    let values: Vec<_> = canonical
        .iter()
        .map(|(text, id)| Canonical {
            id: *id,
            utf16: text.clone(),
            java_hash: text.iter().fold(0u32, |hash, unit| {
                hash.wrapping_mul(31).wrapping_add(u32::from(*unit))
            }),
            literal: literals.get(text).copied(),
        })
        .collect();
    let count = values.len();
    ensure!(
        count <= 0x100000 && requested.keys().all(|id| *id < capacity),
        "Class name identity budget exceeded"
    );
    let mut body = format!(
        ".data\nALIGN 8\nPUBLIC boom_java_class_name_pool\nboom_java_class_name_pool DWORD 04A434E50h,1,{offset},{capacity}\n QWORD OFFSET java_class_name_indices,OFFSET java_class_name_literals,OFFSET boom_layout{class},OFFSET boom_java_string_literal\n QWORD OFFSET boom_java_string_literal_pool,OFFSET java_class_name_aliases\njava_class_name_literals DWORD 04A534C50h,1,{count},1\n QWORD OFFSET java_class_name_entries,OFFSET boom_java_class_name_roots,OFFSET java_class_name_states,OFFSET boom_layout{class}\n DWORD {value},{coder},{hash},{zero}\n QWORD 0\n DWORD 0,0\n.const\nPUBLIC boom_java_class_name_root_count\nboom_java_class_name_root_count QWORD {roots}\njava_class_name_indices LABEL DWORD\n",
        class = string.class_id,
        value = string.value_offset,
        coder = string.coder_offset,
        hash = string.hash_offset,
        zero = string.hash_is_zero_offset,
        roots = count * 2
    );
    for id in 0..capacity {
        writeln!(
            body,
            " DWORD {}",
            requested
                .get(&id)
                .map_or(u32::MAX as usize, |text| canonical[text])
        )?;
    }
    body.push_str("java_class_name_aliases LABEL DWORD\n");
    for value in &values {
        writeln!(
            body,
            " DWORD {}",
            value.literal.unwrap_or(u32::MAX as usize)
        )?;
    }
    body.push_str("ALIGN 8\njava_class_name_entries LABEL BYTE\n");
    for value in &values {
        writeln!(
            body,
            " QWORD OFFSET java_class_name_text_{}\n DWORD {},0{:08X}h",
            value.id,
            value.utf16.len(),
            value.java_hash
        )?;
    }
    for value in &values {
        writeln!(
            body,
            "ALIGN 2\njava_class_name_text_{} LABEL WORD",
            value.id
        )?;
        for chunk in value.utf16.chunks(16) {
            body.push_str(" WORD ");
            for (id, unit) in chunk.iter().enumerate() {
                if id != 0 {
                    body.push(',');
                }
                write!(body, "0{unit:04X}h")?;
            }
            body.push('\n');
        }
    }
    writeln!(
        body,
        ".data?\nALIGN 8\nPUBLIC boom_java_class_name_roots\nboom_java_class_name_roots QWORD {} DUP(?)\njava_class_name_states DWORD {count} DUP(?)\n.code",
        count * 2
    )?;
    Ok((
        Summary {
            abi: 1,
            types: requested.len(),
            canonical_names: count,
            source_literal_aliases: values.iter().filter(|v| v.literal.is_some()).count(),
            root_cells: count * 2,
            source_string_class: string.class_id,
            source_string_sha256: string.source_sha256.clone(),
            general_string_intern: false,
        },
        body,
        names,
        values,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn names_keep_array_descriptors_and_convert_primitive_names() {
        let mut t: TypeRecord = serde_json::from_value(serde_json::json!({"id":0,"kind":0,"marker_flags":0,"ancestors":[],"source_sha256":null,"parent_component":null,"defining_loader":"bootstrap","name":"I"})).unwrap();
        assert_eq!(name(&t).unwrap(), "int".encode_utf16().collect::<Vec<_>>());
        t.kind = 3;
        t.name = "[[Ljava/lang/String;".into();
        assert_eq!(
            name(&t).unwrap(),
            "[[Ljava.lang.String;".encode_utf16().collect::<Vec<_>>()
        );
        t.kind = 0;
        t.name = "bad".into();
        assert!(name(&t).is_err());
    }
}
