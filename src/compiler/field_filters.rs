//! AOT-proven Class literal + Set.of(two String literals) filter registration.
//! Actual Set construction remains Java->ASM; activation and lookup are ASM.
use super::{
    classfile::{ClassFile, Code},
    exceptions, numeric, types,
};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const SET12: &str = "java/util/ImmutableCollections$Set12";
pub const DESCRIPTOR: &str = "(Ljava/lang/Class;Ljava/util/Set;)V";
pub(super) fn is_call(o: &str, n: &str, d: &str) -> bool {
    o == super::reflect_fields::REFLECTION && n == "registerFieldsToFilter" && d == DESCRIPTOR
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Proof {
    pub method: String,
    pub descriptor: String,
    pub code_sha256: String,
    pub pc: usize,
    pub class_pc: usize,
    pub class_constant: u16,
    pub containing_class: String,
    pub names: Vec<Vec<u16>>,
    pub name_constants: Vec<u16>,
    pub set_pc: usize,
    pub set_constant: u16,
    pub alternative_entries_excluded: bool,
}
fn ldc(code: &Code, pc: usize) -> Result<u16> {
    match code.bytes[pc] {
        0x12 => Ok(code.bytes[pc + 1] as u16),
        0x13 => Ok(u16::from_be_bytes([code.bytes[pc + 1], code.bytes[pc + 2]])),
        _ => anyhow::bail!("Field filter registration needs adjacent constant operands"),
    }
}
pub(super) fn prove(class: &ClassFile, code: &Code, pc: usize) -> Result<Proof> {
    ensure!(
        code.bytes.get(pc) == Some(&0xb8),
        "Field filter proof must select invokestatic"
    );
    let call = u16::from_be_bytes(
        code.bytes
            .get(pc + 1..pc + 3)
            .context("Truncated filter call")?
            .try_into()?,
    );
    let (o, n, d, i) = class.static_method_reference(call)?;
    ensure!(
        !i && is_call(&o, &n, &d),
        "Field filter proof selected a different call"
    );
    let starts = exceptions::boundaries(&code.bytes)?;
    let prev = starts
        .range(..pc)
        .rev()
        .take(4)
        .copied()
        .collect::<Vec<_>>();
    ensure!(
        starts.contains(&pc) && prev.len() == 4,
        "Field filter registration needs adjacent Class and Set.of literals"
    );
    let (set_pc, name1_pc, name0_pc, class_pc) = (prev[0], prev[1], prev[2], prev[3]);
    ensure!(
        code.bytes[set_pc] == 0xb8,
        "Field filter registration requires original Set.of"
    );
    let set_constant = u16::from_be_bytes([code.bytes[set_pc + 1], code.bytes[set_pc + 2]]);
    let (o, n, d, i) = class.static_method_reference(set_constant)?;
    ensure!(
        i && o == "java/util/Set"
            && n == "of"
            && d == "(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/Set;",
        "Only proven two-literal Set.of Field filters are currently supported"
    );
    let class_constant = ldc(code, class_pc)?;
    let containing_class = class.constant_class(class_constant)?;
    let name_constants = vec![ldc(code, name0_pc)?, ldc(code, name1_pc)?];
    let names = name_constants
        .iter()
        .map(|&i| {
            class
                .string_literal(i)?
                .context("Field filter names must be String literals")
        })
        .collect::<Result<Vec<_>>>()?;
    let forbidden = |target: i64| target > class_pc as i64 && target <= pc as i64;
    let b = &code.bytes;
    let i32at = |p: usize| i32::from_be_bytes(b[p..p + 4].try_into().unwrap()) as i64;
    for &at in &starts {
        match b[at] {
            0x99..=0xa8 | 0xc6..=0xc7 => ensure!(
                !forbidden(at as i64 + i16::from_be_bytes([b[at + 1], b[at + 2]]) as i64),
                "Field filter literals have a branch entry"
            ),
            0xc8..=0xc9 => ensure!(
                !forbidden(at as i64 + i32at(at + 1)),
                "Field filter literals have a wide branch entry"
            ),
            0xaa | 0xab => {
                let base = (at + 4) & !3;
                ensure!(
                    !forbidden(at as i64 + i32at(base)),
                    "Field filter literals have a switch entry"
                );
                let (count, offset, stride) = if b[at] == 0xaa {
                    (i32at(base + 8) - i32at(base + 4) + 1, base + 12, 4)
                } else {
                    (i32at(base + 4), base + 12, 8)
                };
                for k in 0..count as usize {
                    ensure!(
                        !forbidden(at as i64 + i32at(offset + k * stride)),
                        "Field filter literals have a switch entry"
                    );
                }
            }
            _ => {}
        }
    }
    ensure!(
        code.handlers
            .iter()
            .all(|h| !forbidden(h.handler_pc as i64)),
        "Field filter literals have a handler entry"
    );
    let m = class
        .methods
        .iter()
        .find(|m| m.code.as_ref().is_some_and(|c| std::ptr::eq(c, code)))
        .context("Field filter proof must refer to original Code")?;
    Ok(Proof {
        method: m.name.clone(),
        descriptor: m.descriptor.clone(),
        code_sha256: files::digest_bytes(&code.bytes).sha256,
        pc,
        class_pc,
        class_constant,
        containing_class,
        names,
        name_constants,
        set_pc,
        set_constant,
        alternative_entries_excluded: true,
    })
}

/// Development inspection only. No Java method, Set factory or registration runs.
pub fn inspect(path: &std::path::Path, output: &std::path::Path) -> Result<serde_json::Value> {
    let raw = std::fs::read(path)?;
    let class = ClassFile::parse(&raw)?;
    let mut proofs = vec![];
    for m in &class.methods {
        if let Some(code) = &m.code {
            for pc in exceptions::boundaries(&code.bytes)? {
                if code.bytes[pc] != 0xb8 {
                    continue;
                }
                let constant = u16::from_be_bytes([code.bytes[pc + 1], code.bytes[pc + 2]]);
                let (o, n, d, i) = class.static_method_reference(constant)?;
                if !i && is_call(&o, &n, &d) {
                    proofs.push(prove(&class, code, pc)?);
                }
            }
        }
    }
    ensure!(
        !proofs.is_empty(),
        "No Field filter registration sites found"
    );
    let result = serde_json::json!({"source_class":class.name,"source_path":std::path::absolute(path)?,"source_sha256":files::digest_bytes(&raw).sha256,"proofs":proofs,"execution_complete":false,"game_started":false});
    files::write_atomic(output, &serde_json::to_vec_pretty(&result)?)?;
    Ok(result)
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub method_id: usize,
    pub containing_type: usize,
    pub set_class_id: usize,
    pub set_type: usize,
    pub set_origin: ClassOrigin,
    pub set_factory_origin: ClassOrigin,
    pub set_factory_code_sha256: String,
    pub offsets: Vec<usize>,
    pub proof: Proof,
}
pub(super) fn bind(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    context: (usize, usize, usize),
    layout: &numeric::ObjectLayout,
    proof: Proof,
) -> Result<Binding> {
    let (method_id, containing_type, set_class_id) = context;
    super::reflect_fields::register(registry)?;
    let (o, n, d, i) = caller.static_method_reference(constant)?;
    ensure!(!i && is_call(&o, &n, &d), "Field filter call changed");
    let m = caller.method(&proof.method, Some(&proof.descriptor))?;
    ensure!(
        prove(caller, m.code.as_ref().unwrap(), proof.pc)? == proof,
        "Field filter proof changed"
    );
    let set_type = registry.class("bootstrap", SET12)?;
    let types::Type::Class {
        origin: set_origin,
        access,
        ..
    } = &registry.types[set_type]
    else {
        unreachable!()
    };
    ensure!(
        set_origin.source_id == "jdk:java.base"
            && set_origin.generated.is_none()
            && access & 0x610 == 0x10,
        "Field filter Set must be original final Set12"
    );
    let set_origin = set_origin.as_ref().clone();
    ensure!(
        layout.abi == 2 && layout.payload_bytes == 16 && layout.reference_prefix_fields == 2,
        "Field filter Set12 layout changed"
    );
    let offsets = ["e0", "e1"]
        .iter()
        .map(|name| {
            let f = layout
                .fields
                .iter()
                .find(|f| {
                    f.name == *name
                        && f.descriptor == "Ljava/lang/Object;"
                        && f.declaring_class.as_deref() == Some(SET12)
                })
                .context("Missing Set12 element field")?;
            ensure!(f.storage_bytes == Some(8), "Set12 element width changed");
            Ok(f.offset)
        })
        .collect::<Result<Vec<_>>>()?;
    let id = registry.class("bootstrap", "java/util/Set")?;
    let types::Type::Class { origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    let set_factory_origin = origin.as_ref().clone();
    let m = registry.definition(id).unwrap().method(
        "of",
        Some("(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/Set;"),
    )?;
    ensure!(
        m.access == 9 && m.code.is_some(),
        "Set.of factory source changed"
    );
    Ok(Binding {
        caller: source.clone(),
        constant,
        method_id,
        containing_type,
        set_class_id,
        set_type,
        set_origin,
        set_factory_origin,
        set_factory_code_sha256: files::digest_bytes(&m.code.as_ref().unwrap().bytes).sha256,
        offsets,
        proof,
    })
}
