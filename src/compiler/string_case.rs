//! Source-bound Unicode simple mappings for bootstrap String comparison.
use super::{classfile::ClassFile, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

const ASM: &str = include_str!("../../native/runtime/unicode_case.asm");
const MANIFEST: &str = include_str!("../../native/runtime/unicode_case.json");
const MEMBERS: &[(&str, &str)] = &[
    ("codePointAt", "(I)I"),
    ("regionMatches", "(ILjava/lang/String;II)Z"),
    ("regionMatches", "(ZILjava/lang/String;II)Z"),
    ("trim", "()Ljava/lang/String;"),
    ("toLowerCase", "(Ljava/util/Locale;)Ljava/lang/String;"),
    ("equalsIgnoreCase", "(Ljava/lang/String;)Z"),
    ("indexOf", "(I)I"),
    ("indexOf", "(II)I"),
    ("lastIndexOf", "(I)I"),
    ("lastIndexOf", "(II)I"),
    ("indexOf", "(Ljava/lang/String;)I"),
    ("indexOf", "(Ljava/lang/String;I)I"),
    ("lastIndexOf", "(Ljava/lang/String;)I"),
    ("lastIndexOf", "(Ljava/lang/String;I)I"),
    ("substring", "(I)Ljava/lang/String;"),
    ("substring", "(II)Ljava/lang/String;"),
];
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Data {
    pub abi: u32,
    pub unicode_version: String,
    pub source_url: String,
    pub source_sha256: String,
    pub mapping_rows: usize,
    pub mapping_bytes_sha256: String,
    pub exhaustive_code_points: usize,
    pub jdk_character_sources: BTreeMap<String, String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub name: String,
    pub descriptor: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub data: Data,
    pub native_source_sha256: String,
    pub string_runtime_source_sha256: String,
    pub string_origin: ClassOrigin,
    pub character_origins: Vec<ClassOrigin>,
    pub bindings: Vec<Binding>,
}
fn validate_data(source: &str, data: &Data) -> Result<()> {
    ensure!(
        data.abi == 1
            && data.unicode_version == "15.0.0"
            && data.source_sha256
                == "806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73"
            && data.mapping_rows == 2879
            && data.exhaustive_code_points == 0x110000
            && data.jdk_character_sources.len() == 10,
        "Unsupported Unicode simple case data profile"
    );
    let body = source
        .split_once("; BEGIN GENERATED UNICODE SIMPLE CASE DATA")
        .context("Missing Unicode data marker")?
        .1
        .split_once("; END GENERATED UNICODE SIMPLE CASE DATA")
        .context("Missing Unicode data end marker")?
        .0;
    let mut bytes = Vec::new();
    let mut previous = None;
    for line in body.lines().filter_map(|l| l.trim().strip_prefix("DWORD ")) {
        let row = line
            .split(',')
            .map(|v| {
                u32::from_str_radix(
                    v.trim()
                        .strip_prefix('0')
                        .context("Invalid MASM hex prefix")?
                        .strip_suffix('h')
                        .context("Invalid MASM hex suffix")?,
                    16,
                )
                .map_err(anyhow::Error::from)
            })
            .collect::<Result<Vec<_>>>()?;
        ensure!(
            row.len() == 3
                && row.iter().all(|v| *v <= 0x10ffff)
                && previous.is_none_or(|old| old < row[0])
                && (row[0] != row[1] || row[0] != row[2]),
            "Malformed Unicode mapping row"
        );
        previous = Some(row[0]);
        for value in row {
            bytes.extend(value.to_le_bytes());
        }
    }
    ensure!(
        bytes.len() == data.mapping_rows * 12
            && files::digest_bytes(&bytes).sha256 == data.mapping_bytes_sha256,
        "Unicode mapping rows/digest changed"
    );
    ensure!(
        body.lines()
            .any(|l| l == format!("unicode_case_count EQU {}", data.mapping_rows)),
        "Unicode search bound changed"
    );
    Ok(())
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
        "String case tables require original bootstrap definitions"
    );
    Ok((id, origin.as_ref().clone()))
}
impl Plan {
    pub(super) fn prepare(registry: &mut types::Registry<'_>) -> Result<Self> {
        let data: Data = serde_json::from_str(MANIFEST)?;
        validate_data(ASM, &data)?;
        let (id, string_origin) = original(registry, "java/lang/String")?;
        let class = registry.definition(id).context("Missing original String")?;
        ensure!(
            class.access & 0x211 == 0x11,
            "String case class contract changed"
        );
        for (name, descriptor) in MEMBERS {
            let method = class.method(name, Some(descriptor))?;
            ensure!(
                method.access == 1 && method.code.is_some(),
                "String member contract changed: {name}{descriptor}"
            );
        }
        let mut character_origins = Vec::new();
        for (name, expected) in &data.jdk_character_sources {
            let (_, origin) = original(registry, &name.replace('.', "/"))?;
            ensure!(
                &origin.sha256 == expected,
                "Unicode simple mappings need revalidation for {}",
                name
            );
            character_origins.push(origin);
        }
        Ok(Self {
            abi: 1,
            data,
            native_source_sha256: files::digest_bytes(ASM.as_bytes()).sha256,
            string_runtime_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/strings.asm"
            ))
            .sha256,
            string_origin,
            character_origins,
            bindings: Vec::new(),
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
    ) -> Result<()> {
        let (owner, name, descriptor) = caller.method_reference(constant)?;
        ensure!(
            owner == "java/lang/String"
                && MEMBERS.contains(&(name.as_str(), descriptor.as_str()))
                && source.binary_name == caller.name.replace('/', "."),
            "Invalid String case caller proof"
        );
        if !self
            .bindings
            .iter()
            .any(|b| b.caller == *source && b.constant == constant)
        {
            self.bindings.push(Binding {
                caller: source.clone(),
                constant,
                name,
                descriptor,
            });
            self.bindings.sort_by(|a, b| {
                (&a.caller.loader, &a.caller.binary_name, a.constant).cmp(&(
                    &b.caller.loader,
                    &b.caller.binary_name,
                    b.constant,
                ))
            });
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unicode_table_matches_its_full_mapping_digest_and_search_bound() {
        let data: Data = serde_json::from_str(MANIFEST).unwrap();
        validate_data(ASM, &data).unwrap();
        for bad in [
            ASM.replace("unicode_case_count EQU 2879", "unicode_case_count EQU 2878"),
            ASM.replacen(
                "000000041h, 000000041h, 000000061h",
                "000000042h, 000000041h, 000000061h",
                1,
            ),
        ] {
            assert!(validate_data(&bad, &data).is_err());
        }
    }
    #[test]
    fn changed_unicode_profile_requires_regeneration_and_jdk_revalidation() {
        let mut data: Data = serde_json::from_str(MANIFEST).unwrap();
        data.unicode_version = "16.0.0".into();
        assert!(validate_data(ASM, &data).is_err());
        data.unicode_version = "15.0.0".into();
        data.jdk_character_sources.clear();
        assert!(validate_data(ASM, &data).is_err());
    }
}
