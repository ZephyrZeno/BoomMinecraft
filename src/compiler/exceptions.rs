//! Exception-table input validation and loader-aware plans, separate from execution.
//! Context16 code generation remains gated until Throwable allocation, init-failure
//! roots, automatic safepoints and a Context32 call chain have been integrated.
use super::{
    classfile::ClassFile,
    types::{self, TypeProvider},
};
use crate::{files, lock::InputLock};
use anyhow::{Context, Result, bail, ensure};
use serde::Serialize;
use std::{collections::BTreeSet, fmt::Write, path::Path};

/// Structural decoder for all ordinary Java 21 opcodes. This is not an executable
/// backend, nor a replacement for type/stack verification or branch validation.
pub fn boundaries(bytes: &[u8]) -> Result<BTreeSet<usize>> {
    ensure!(
        !bytes.is_empty() && bytes.len() <= 65535,
        "Invalid Code length"
    );
    let read_i32 = |at: usize| -> Result<i32> {
        Ok(i32::from_be_bytes(
            bytes
                .get(at..at + 4)
                .context("Truncated switch")?
                .try_into()?,
        ))
    };
    let mut starts = BTreeSet::new();
    let mut pc = 0;
    while pc < bytes.len() {
        starts.insert(pc);
        let opcode = bytes[pc];
        let length = match opcode {
            0x00..=0x0f
            | 0x1a..=0x35
            | 0x3b..=0x83
            | 0x85..=0x98
            | 0xac..=0xb1
            | 0xbe..=0xbf
            | 0xc2..=0xc3 => 1,
            0x10 | 0x12 | 0x15..=0x19 | 0x36..=0x3a | 0xa9 | 0xbc => 2,
            0x11
            | 0x13..=0x14
            | 0x84
            | 0x99..=0xa8
            | 0xb2..=0xb8
            | 0xbb
            | 0xbd
            | 0xc0..=0xc1
            | 0xc6..=0xc7 => 3,
            0xc5 => 4,
            0xb9..=0xba | 0xc8..=0xc9 => 5,
            0xc4 => match *bytes.get(pc + 1).context("Truncated wide")? {
                0x15..=0x19 | 0x36..=0x3a | 0xa9 => 4,
                0x84 => 6,
                _ => bail!("Invalid wide opcode at {pc}"),
            },
            0xaa..=0xab => {
                let base = (pc + 4) & !3;
                ensure!(
                    bytes
                        .get(pc + 1..base)
                        .context("Truncated switch padding")?
                        .iter()
                        .all(|b| *b == 0),
                    "Nonzero switch padding"
                );
                read_i32(base)?; // default offset
                let end = if opcode == 0xaa {
                    let low = read_i32(base + 4)?;
                    let high = read_i32(base + 8)?;
                    let count = i64::from(high) - i64::from(low) + 1;
                    ensure!((1..=16384).contains(&count), "Invalid tableswitch bounds");
                    base + 12 + count as usize * 4
                } else {
                    let count = read_i32(base + 4)?;
                    ensure!((0..=8191).contains(&count), "Invalid lookupswitch size");
                    let mut previous = None;
                    for index in 0..count as usize {
                        let key = read_i32(base + 8 + index * 8)?;
                        ensure!(
                            previous.is_none_or(|old| old < key),
                            "Unsorted lookupswitch keys"
                        );
                        previous = Some(key);
                    }
                    base + 8 + count as usize * 8
                };
                end - pc
            }
            _ => bail!("Reserved/invalid JVM opcode 0x{opcode:02x} at {pc}"),
        };
        pc += length;
        ensure!(
            pc <= bytes.len(),
            "Truncated instruction at bytecode {}",
            starts.last().unwrap()
        );
    }
    Ok(starts)
}

#[derive(Debug, Serialize)]
pub struct Handler {
    pub start_pc: u16,
    pub end_pc: u16,
    pub handler_pc: u16,
    pub catch_type: Option<usize>,
}
#[derive(Debug, Serialize)]
pub struct Method {
    pub name: String,
    pub descriptor: String,
    pub code_length: usize,
    pub throw_pcs: Vec<usize>,
    pub handlers: Vec<Handler>,
}
#[derive(Debug, Serialize)]
pub struct Plan {
    pub schema: u32,
    pub input_fingerprint: String,
    pub source: crate::bytecode::ClassOrigin,
    pub throwable_type: usize,
    pub types: Vec<types::Type>,
    pub methods: Vec<Method>,
    pub metadata_digest: files::FileDigest,
    pub rows_digest: files::FileDigest,
    pub execution_wired: bool,
    pub full_game_ready: bool,
}

/// Read verified vanilla/JDK bytes. No class initialization or game execution occurs.
pub fn plan(inputs: &InputLock, manifest: &Path, name: &str, output: &Path) -> Result<Plan> {
    let provider = types::VanillaTypes::new(inputs, manifest)?;
    let (bytes, source) = provider.resolve("vanilla-application", &name.replace('.', "/"))?;
    let class = ClassFile::parse(&bytes)?;
    let mut registry = types::Registry::new(&provider);
    registry.class(&source.loader, &class.name)?;
    let throwable_type = registry.class("bootstrap", "java/lang/Throwable")?;
    let mut methods = Vec::new();
    let mut rows = String::from(
        "; Ordered exception rows only. No executable Java body or type map.\noption casemap:none\n.const\n",
    );
    for method in &class.methods {
        let Some(code) = &method.code else {
            continue;
        };
        let starts = boundaries(&code.bytes)?;
        let throw_pcs: Vec<_> = starts
            .iter()
            .copied()
            .filter(|pc| code.bytes[*pc] == 0xbf)
            .collect();
        if code.handlers.is_empty() && throw_pcs.is_empty() {
            continue;
        }
        let mut handlers = Vec::new();
        for handler in &code.handlers {
            ensure!(
                starts.contains(&usize::from(handler.start_pc))
                    && (usize::from(handler.end_pc) == code.bytes.len()
                        || starts.contains(&usize::from(handler.end_pc)))
                    && starts.contains(&usize::from(handler.handler_pc)),
                "Exception range/target is not an instruction boundary"
            );
            let catch_type = handler
                .catch_type
                .as_ref()
                .map(|name| -> Result<_> {
                    let id = registry.class(&source.loader, name)?;
                    ensure!(
                        registry.assignable(id, throwable_type),
                        "Catch type {name} is not a bootstrap Throwable subclass"
                    );
                    Ok(id)
                })
                .transpose()?;
            handlers.push(Handler {
                start_pc: handler.start_pc,
                end_pc: handler.end_pc,
                handler_pc: handler.handler_pc,
                catch_type,
            });
        }
        if !handlers.is_empty() {
            writeln!(
                rows,
                "ALIGN 8\nboom_exception_rows{} LABEL BYTE",
                methods.len()
            )?;
            for row in &handlers {
                writeln!(
                    rows,
                    "    DD {}, {}, {}, 0\n    DQ {}",
                    row.start_pc,
                    row.end_pc,
                    row.handler_pc,
                    row.catch_type
                        .map_or("0".into(), |id| format!("boom_t{id}"))
                )?;
            }
        }
        methods.push(Method {
            name: method.name.clone(),
            descriptor: method.descriptor.clone(),
            code_length: code.bytes.len(),
            throw_pcs,
            handlers,
        });
    }
    let metadata = types::emit_metadata(&registry.types)?;
    let result = Plan {
        schema: 1,
        input_fingerprint: inputs.fingerprint.clone(),
        source,
        throwable_type,
        types: registry.types,
        methods,
        metadata_digest: files::digest_bytes(metadata.as_bytes()),
        rows_digest: files::digest_bytes(rows.as_bytes()),
        execution_wired: false,
        full_game_ready: false,
    };
    files::write_atomic(&output.join("types.asm"), metadata.as_bytes())?;
    files::write_atomic(&output.join("handler-rows.asm"), rows.as_bytes())?;
    files::write_atomic(
        &output.join("exceptions.json"),
        &serde_json::to_vec_pretty(&result)?,
    )?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn instruction_lengths_keep_throw_operands_and_wide_switch_data_separate() {
        assert_eq!(
            boundaries(&[0x11, 0xbf, 0, 0xc4, 0x84, 0, 2, 0xbf, 0, 0xbf]).unwrap(),
            BTreeSet::from([0, 3, 9])
        );
        let mut table = vec![0xaa, 0, 0, 0];
        for value in [0i32, 0, 1, 0xbf, 0] {
            table.extend_from_slice(&value.to_be_bytes());
        }
        table.push(0xbf);
        assert_eq!(boundaries(&table).unwrap(), BTreeSet::from([0, 24]));
        table[1] = 1;
        assert!(boundaries(&table).is_err());
        for bytes in [
            &[0xc4, 0xb1][..],
            &[0x11, 0],
            &[0xbf, 0xca],
            &[0xaa],
            &[0xab, 0, 0, 0, 0, 0, 0, 0, 255, 255, 255, 255],
        ] {
            assert!(boundaries(bytes).is_err(), "{bytes:?}");
        }
    }
}
