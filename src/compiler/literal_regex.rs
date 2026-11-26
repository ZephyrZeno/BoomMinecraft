//! AOT proof for literal, single-character replaceAll -> assembly char replacement.
//! No regular-expression interpreter or general regex fallback is introduced.
use super::{
    classfile::{ClassFile, Code},
    exceptions, numeric, types,
};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const DESCRIPTOR: &str = "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;";
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Proof {
    pub method: String,
    pub descriptor: String,
    pub code_sha256: String,
    pub pc: usize,
    pub pattern_pc: usize,
    pub replacement_pc: usize,
    pub pattern_constant: u16,
    pub replacement_constant: u16,
    pub old: u16,
    pub new: u16,
    pub branch_and_handler_entries_excluded: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub proof: Proof,
    pub string_origin: ClassOrigin,
    pub replace_all_code_sha256: String,
    pub char_replace_code_sha256: String,
    pub native_source_sha256: String,
    pub original_replace_all_java_body_executed: bool,
    pub regex_engine_complete: bool,
}
pub(super) fn is_call(o: &str, n: &str, d: &str) -> bool {
    o == "java/lang/String" && n == "replaceAll" && d == DESCRIPTOR
}
pub(super) fn signature() -> numeric::Signature {
    numeric::Signature {
        arguments: vec![numeric::Type::BootstrapString; 3],
        result: numeric::Type::BootstrapString,
    }
}
fn pair(pattern: &[u16], replacement: &[u16]) -> Option<(u16, u16)> {
    if pattern.len() != 1 || replacement.len() != 1 {
        return None;
    }
    let (a, b) = (pattern[0], replacement[0]);
    if a == b
        || (0xd800..=0xdfff).contains(&a)
        || b == b'$' as u16
        || b == b'\\' as u16
        || ".^$*+?{}[]\\|()".encode_utf16().any(|c| c == a)
    {
        None
    } else {
        Some((a, b))
    }
}
fn literal(class: &ClassFile, code: &Code, pc: usize) -> Result<Option<(u16, Vec<u16>)>> {
    let i = match code.bytes[pc] {
        0x12 => code.bytes[pc + 1] as u16,
        0x13 => u16::from_be_bytes([code.bytes[pc + 1], code.bytes[pc + 2]]),
        _ => return Ok(None),
    };
    Ok(class.string_literal(i)?.map(|s| (i, s)))
}
/// Both operands must execute on every path reaching the call. In particular,
/// a branch to the second ldc or the invocation invalidates adjacent-load proof.
pub(super) fn prove(class: &ClassFile, code: &Code, pc: usize) -> Result<Proof> {
    let starts = exceptions::boundaries(&code.bytes)?;
    let previous = starts
        .range(..pc)
        .rev()
        .take(2)
        .copied()
        .collect::<Vec<_>>();
    ensure!(
        starts.contains(&pc) && previous.len() == 2,
        "replaceAll requires two adjacent, proven String literals; general regex is not implemented"
    );
    let (replacement_pc, pattern_pc) = (previous[0], previous[1]);
    let (pattern_constant, pattern) = literal(class, code, pattern_pc)?
        .context("replaceAll pattern must be an adjacent literal")?;
    let (replacement_constant, replacement) = literal(class, code, replacement_pc)?
        .context("replaceAll replacement must be an adjacent literal")?;
    let (old,new)=pair(&pattern,&replacement).context("replaceAll literal optimization requires distinct single characters, a non-surrogate literal pattern and an unescaped literal replacement; general regex is not implemented")?;
    let forbidden = |target: i64| target > pattern_pc as i64 && target <= pc as i64;
    for &at in &starts {
        let bytes = &code.bytes;
        let i32_at = |i: usize| i32::from_be_bytes(bytes[i..i + 4].try_into().unwrap()) as i64;
        match bytes[at] {
            0x99..=0xa8 | 0xc6..=0xc7 => ensure!(
                !forbidden(at as i64 + i16::from_be_bytes([bytes[at + 1], bytes[at + 2]]) as i64),
                "replaceAll literal operands have an alternative branch entry"
            ),
            0xc8..=0xc9 => ensure!(
                !forbidden(at as i64 + i32_at(at + 1)),
                "replaceAll literal operands have an alternative wide branch entry"
            ),
            0xaa | 0xab => {
                let base = (at + 4) & !3;
                ensure!(
                    !forbidden(at as i64 + i32_at(base)),
                    "replaceAll literal operands have a switch default entry"
                );
                if bytes[at] == 0xaa {
                    let count = i32_at(base + 8) - i32_at(base + 4) + 1;
                    for i in 0..count as usize {
                        ensure!(
                            !forbidden(at as i64 + i32_at(base + 12 + i * 4)),
                            "replaceAll literal operands have a tableswitch entry"
                        )
                    }
                } else {
                    for i in 0..i32_at(base + 4) as usize {
                        ensure!(
                            !forbidden(at as i64 + i32_at(base + 12 + i * 8)),
                            "replaceAll literal operands have a lookupswitch entry"
                        )
                    }
                }
            }
            _ => {}
        }
    }
    ensure!(
        code.handlers
            .iter()
            .all(|h| !forbidden(h.handler_pc as i64)),
        "replaceAll literal operands have an exception-handler entry"
    );
    let m = class
        .methods
        .iter()
        .find(|m| m.code.as_ref().is_some_and(|c| std::ptr::eq(c, code)))
        .context("Literal replacement proof must refer to original caller Code")?;
    Ok(Proof {
        method: m.name.clone(),
        descriptor: m.descriptor.clone(),
        code_sha256: files::digest_bytes(&code.bytes).sha256,
        pc,
        pattern_pc,
        replacement_pc,
        pattern_constant,
        replacement_constant,
        old,
        new,
        branch_and_handler_entries_excluded: true,
    })
}
pub(super) fn bind(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    proof: Proof,
) -> Result<Binding> {
    let (o, n, d) = caller.method_reference(constant)?;
    ensure!(
        is_call(&o, &n, &d) && source.binary_name == caller.name.replace('/', "."),
        "Literal regex caller identity changed"
    );
    let m = caller.method(&proof.method, Some(&proof.descriptor))?;
    let code = m
        .code
        .as_ref()
        .context("Missing literal replacement caller Code")?;
    ensure!(
        prove(caller, code, proof.pc)? == proof,
        "Literal regex proof changed"
    );
    ensure!(
        code.bytes[proof.pc] == 0xb6
            && u16::from_be_bytes([code.bytes[proof.pc + 1], code.bytes[proof.pc + 2]]) == constant,
        "Literal regex invocation changed"
    );
    let id = registry.class("bootstrap", "java/lang/String")?;
    let types::Type::Class { origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    let origin = origin.as_ref().clone();
    ensure!(
        origin.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "Literal regex requires original java.base String"
    );
    let string = registry.definition(id).unwrap();
    ensure!(
        string.access & 0x211 == 0x11,
        "String final public class contract changed"
    );
    let member = |name, descriptor| -> Result<String> {
        let m = string.method(name, Some(descriptor))?;
        ensure!(
            m.access == 1,
            "String replacement public Java contract changed"
        );
        Ok(files::digest_bytes(
            &m.code
                .as_ref()
                .context("Missing original String Code")?
                .bytes,
        )
        .sha256)
    };
    Ok(Binding {
        abi: 1,
        caller: source.clone(),
        constant,
        proof,
        string_origin: origin,
        replace_all_code_sha256: member("replaceAll", DESCRIPTOR)?,
        char_replace_code_sha256: member("replace", super::string_replace::DESCRIPTOR)?,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/string_replace.asm"
        ))
        .sha256,
        original_replace_all_java_body_executed: false,
        regex_engine_complete: false,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn literal_fold_rejects_regex_syntax_identity_changes_and_surrogate_patterns() {
        assert_eq!(pair(&[b'_' as u16], &[b'-' as u16]), Some((95, 45)));
        for c in ".^$*+?{}[]\\|()".encode_utf16() {
            assert_eq!(pair(&[c], &[65]), None)
        }
        for a in [0xd800, 0xdbff, 0xdc00, 0xdfff] {
            assert_eq!(pair(&[a], &[65]), None)
        }
        for b in [95, 36, 92] {
            assert_eq!(pair(&[95], &[b]), None)
        }
        assert_eq!(pair(&[], &[65]), None);
        assert_eq!(pair(&[65, 66], &[67]), None);
    }
}
