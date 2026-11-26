//! Locked-JDK word boundary tables; execution is the assembly DFA.
use crate::{bytecode::ClassOrigin, files, jdk::JdkBase, lock::InputLock, tools};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fmt::Write as _, fs, path::Path, process::Command};

const CONTEXT: &str = include_str!("../../native/runtime/unicode_context.json");
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ContextData {
    pub abi: u32,
    pub unicode_version: String,
    pub source_sha256: String,
    pub sigma_cased_profile: String,
    pub rows: usize,
    pub codewords_sha256: String,
    pub row_bytes_sha256: String,
    pub jdk_sources: BTreeMap<String, String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tables {
    pub abi: u32,
    pub resource: String,
    pub resource_sha256: String,
    pub image_sha256: String,
    pub source_checksum: u64,
    pub categories: usize,
    pub states: Vec<u16>,
    pub backwards: Vec<u16>,
    pub ends: Vec<u8>,
    pub lookahead: Vec<u8>,
    pub bmp_index: Vec<u16>,
    pub bmp: Vec<u8>,
    pub supplementary: Vec<u32>,
    pub context: ContextData,
    pub original_classes: Vec<ClassOrigin>,
    pub native_source_sha256: String,
    pub context_source_sha256: String,
    pub dictionary_word_boundaries: bool,
    pub dynamic_locale_providers: bool,
}
impl Tables {
    pub fn prepare(inputs: &InputLock, manifest: &Path) -> Result<Self> {
        let jdk = JdkBase::read(manifest, inputs)?;
        let context: ContextData = serde_json::from_str(CONTEXT)?;
        validate_context(&context)?;
        ensure!(
            context.abi == 1
                && context.unicode_version == "15.0.0"
                && context.rows == 535
                && context.jdk_sources.len() == 5
                && context.source_sha256
                    == "806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73",
            "Unsupported Unicode context profile"
        );
        let mut original_classes = Vec::new();
        for (name, expected) in &context.jdk_sources {
            let (_, origin) = jdk.read_class(manifest, &name.replace('.', "/"))?;
            ensure!(
                &origin.sha256 == expected,
                "Word/case rules require revalidation for {name}"
            );
            original_classes.push(origin);
        }
        ensure!(
            files::digest(&jdk.extractor.path)? == jdk.extractor.digest,
            "JDK word data extractor changed"
        );
        let temp = tempfile::Builder::new()
            .prefix("word-case-")
            .tempdir_in(manifest.parent().context("JDK metadata has no parent")?)?;
        let resource = "java.base/sun/text/resources/WordBreakIteratorData";
        let mut cmd = Command::new(&jdk.extractor.path);
        tools::clean_java_environment(&mut cmd);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000);
        }
        let result = cmd
            .args([
                "extract",
                "--include",
                "glob:/java.base/sun/text/resources/WordBreakIteratorData",
                "--dir",
            ])
            .arg(temp.path())
            .arg(&jdk.image.path)
            .output()?;
        ensure!(
            result.status.success(),
            "Word data extraction failed: {}",
            String::from_utf8_lossy(&result.stderr)
        );
        ensure!(
            files::digest(&jdk.image.path)? == jdk.image.digest
                && files::digest(&jdk.extractor.path)? == jdk.extractor.digest,
            "JDK word input changed during extraction"
        );
        let raw = fs::read(temp.path().join(resource)).context("Missing extracted word rules")?;
        let mut tables = Self::parse(&raw)?;
        tables.image_sha256 = jdk.image.digest.sha256;
        tables.original_classes = original_classes;
        Ok(tables)
    }
    fn parse(raw: &[u8]) -> Result<Self> {
        ensure!(
            raw.len() >= 48 && raw.len() <= 4 * 1024 * 1024 && &raw[..8] == b"BIdata\0\x01",
            "Invalid word data header/version"
        );
        let mut at = 8usize;
        let take = |at: &mut usize, n: usize| -> Result<&[u8]> {
            let end = at.checked_add(n).context("Word table length overflow")?;
            let out = raw.get(*at..end).context("Truncated word data")?;
            *at = end;
            Ok(out)
        };
        let u32 =
            |at: &mut usize| -> Result<u32> { Ok(u32::from_be_bytes(take(at, 4)?.try_into()?)) };
        ensure!(
            u32(&mut at)? as usize == raw.len() - 12,
            "Word data total length mismatch"
        );
        let mut lengths = [0usize; 7];
        for n in &mut lengths {
            *n = u32(&mut at)? as usize;
            ensure!(*n <= 1024 * 1024, "Word table exceeds budget");
        }
        let source_checksum = u64::from_be_bytes(take(&mut at, 8)?.try_into()?);
        let [
            states_len,
            back_len,
            ends_len,
            look_len,
            bmp_len,
            supp_len,
            extra_len,
        ] = lengths;
        ensure!(
            (2..=4096).contains(&ends_len)
                && ends_len == look_len
                && states_len % ends_len == 0
                && (1..=255).contains(&(states_len / ends_len))
                && (128..=65536).contains(&bmp_len)
                && (2..=65536).contains(&supp_len)
                && extra_len == 0,
            "Unsupported word DFA dimensions/dictionary data"
        );
        let categories = states_len / ends_len;
        ensure!(
            back_len % categories == 0 && (2..=4096).contains(&(back_len / categories)),
            "Invalid backward word DFA dimensions"
        );
        let words = |at: &mut usize, n: usize| -> Result<Vec<u16>> {
            Ok(take(at, n.checked_mul(2).context("Word array overflow")?)?
                .as_chunks::<2>()
                .0
                .iter()
                .map(|b| u16::from_be_bytes(*b))
                .collect())
        };
        let states = words(&mut at, states_len)?;
        let back = words(&mut at, back_len)?;
        let ends = take(&mut at, ends_len)?.to_vec();
        let lookahead = take(&mut at, look_len)?.to_vec();
        let bmp_index = words(&mut at, 512)?;
        let bmp = take(&mut at, bmp_len)?.to_vec();
        let supplementary = (0..supp_len)
            .map(|_| u32(&mut at))
            .collect::<Result<Vec<_>>>()?;
        ensure!(
            at == raw.len()
                && states.iter().all(|s| usize::from(*s) < ends_len)
                && back.iter().all(|s| usize::from(*s) < back_len / categories)
                && back_len % categories == 0
                && ends.iter().chain(&lookahead).all(|v| *v <= 1),
            "Invalid word DFA state/flags"
        );
        ensure!(
            bmp_index.iter().all(|i| usize::from(*i) + 127 < bmp_len)
                && bmp
                    .iter()
                    .all(|c| usize::from(*c) < categories || *c == 255),
            "Invalid word BMP categories"
        );
        ensure!(
            supplementary[0] >> 8 == 0x10000
                && supplementary.last().unwrap() >> 8 == 0x110000
                && supplementary.windows(2).all(|w| w[0] >> 8 <= w[1] >> 8)
                && supplementary
                    .iter()
                    .all(|v| (*v & 255) < categories as u32 || (*v & 255) == 255),
            "Invalid word supplementary categories"
        );
        Ok(Self {
            abi: 2,
            resource: "java.base/sun/text/resources/WordBreakIteratorData".into(),
            resource_sha256: files::digest_bytes(raw).sha256,
            image_sha256: String::new(),
            source_checksum,
            categories,
            states,
            backwards: back,
            ends,
            lookahead,
            bmp_index,
            bmp,
            supplementary,
            context: serde_json::from_str(CONTEXT)?,
            original_classes: Vec::new(),
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/word_break.asm"
            ))
            .sha256,
            context_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/unicode_context.asm"
            ))
            .sha256,
            dictionary_word_boundaries: false,
            dynamic_locale_providers: false,
        })
    }
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        out.push_str(".const\n");
        fn rows(
            out: &mut String,
            label: &str,
            kind: &str,
            values: impl IntoIterator<Item = u32>,
        ) -> Result<()> {
            writeln!(out, "ALIGN 4\n{label} LABEL {kind}")?;
            let values: Vec<_> = values.into_iter().collect();
            for chunk in values.chunks(12) {
                writeln!(
                    out,
                    "    {kind} {}",
                    chunk
                        .iter()
                        .map(u32::to_string)
                        .collect::<Vec<_>>()
                        .join(",")
                )?;
            }
            Ok(())
        }
        rows(
            out,
            "boom_word_states",
            "WORD",
            self.states.iter().map(|n| u32::from(*n)),
        )?;
        rows(
            out,
            "boom_word_backwards",
            "WORD",
            self.backwards.iter().map(|n| u32::from(*n)),
        )?;
        rows(
            out,
            "boom_word_ends",
            "BYTE",
            self.ends.iter().map(|n| u32::from(*n)),
        )?;
        rows(
            out,
            "boom_word_lookahead",
            "BYTE",
            self.lookahead.iter().map(|n| u32::from(*n)),
        )?;
        rows(
            out,
            "boom_word_bmp_index",
            "WORD",
            self.bmp_index.iter().map(|n| u32::from(*n)),
        )?;
        rows(
            out,
            "boom_word_bmp",
            "BYTE",
            self.bmp.iter().map(|n| u32::from(*n)),
        )?;
        rows(
            out,
            "boom_word_supplementary",
            "DWORD",
            self.supplementary.iter().copied(),
        )?;
        writeln!(
            out,
            "ALIGN 8\nboom_word_plan DWORD 050524257h,2,{},{}\n    QWORD OFFSET boom_word_states,OFFSET boom_word_ends,OFFSET boom_word_lookahead,OFFSET boom_word_bmp_index,OFFSET boom_word_bmp,OFFSET boom_word_supplementary\n    DWORD {},{},{},0\n    QWORD OFFSET boom_word_backwards\n    DWORD {},{}\n.code\nPUBLIC boom_get_word_plan\nboom_get_word_plan PROC\n    lea rax,boom_word_plan\n    ret\nboom_get_word_plan ENDP",
            self.ends.len(),
            self.categories,
            self.states.len(),
            self.bmp.len(),
            self.supplementary.len(),
            self.backwards.len(),
            self.backwards.len() / self.categories
        )?;
        Ok(())
    }
}

fn validate_context(data: &ContextData) -> Result<()> {
    let asm = include_str!("../../native/runtime/unicode_context.asm");
    let body = asm
        .split_once("; BEGIN GENERATED UNICODE CONTEXT DATA")
        .context("Missing Unicode context start")?
        .1
        .split_once("; END GENERATED UNICODE CONTEXT DATA")
        .context("Missing Unicode context end")?
        .0;
    let mut rows = Vec::new();
    let mut words = vec![0u8; 0x220000];
    let mut previous = None;
    for line in body.lines().filter_map(|s| s.trim().strip_prefix("DWORD ")) {
        let row = line
            .split(',')
            .map(|s| {
                u32::from_str_radix(
                    s.trim()
                        .strip_prefix('0')
                        .context("Invalid Unicode context prefix")?
                        .strip_suffix('h')
                        .context("Invalid Unicode context hex")?,
                    16,
                )
                .map_err(anyhow::Error::from)
            })
            .collect::<Result<Vec<_>>>()?;
        ensure!(
            row.len() == 3
                && row[0] <= row[1]
                && row[1] <= 0x10ffff
                && (1..=511).contains(&row[2])
                && previous.is_none_or(|p| p < row[0]),
            "Invalid Unicode context range"
        );
        previous = Some(row[1]);
        for value in &row {
            rows.extend(value.to_le_bytes());
        }
        for cp in row[0]..=row[1] {
            words[cp as usize * 2..cp as usize * 2 + 2]
                .copy_from_slice(&(row[2] as u16).to_le_bytes());
        }
    }
    ensure!(
        rows.len() == data.rows * 12
            && files::digest_bytes(&rows).sha256 == data.row_bytes_sha256
            && files::digest_bytes(&words).sha256 == data.codewords_sha256,
        "Generated Unicode context differs from its manifest"
    );
    Ok(())
}

pub fn inspect(inputs: &InputLock, manifest: &Path, output: &Path) -> Result<Tables> {
    let tables = Tables::prepare(inputs, manifest)?;
    fs::create_dir_all(output)?;
    let mut assembly = "option casemap:none\n".to_owned();
    tables.emit(&mut assembly)?;
    assembly.push_str("END\n");
    fs::write(output.join("word-plan.asm"), assembly)?;
    fs::write(
        output.join("word-plan.json"),
        serde_json::to_vec_pretty(&tables)?,
    )?;
    Ok(tables)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn word_tables_reject_invalid_dimensions_before_allocating_vectors() {
        let mut raw = vec![0u8; 48];
        raw[..8].copy_from_slice(b"BIdata\0\x01");
        raw[8..12].copy_from_slice(&36u32.to_be_bytes());
        assert!(Tables::parse(&raw).is_err());
        raw[12..16].copy_from_slice(&u32::MAX.to_be_bytes());
        assert!(Tables::parse(&raw).is_err());
    }
}
