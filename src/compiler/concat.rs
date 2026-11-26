//! StringConcatFactory recipe validation and MASM metadata generation.
use super::classfile::{ClassFile, DynamicSite};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Argument {
    Int,
    Long,
    Boolean,
    Char,
    String,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Part {
    Literal { utf16: Vec<u16> },
    Argument { index: usize, value: Argument },
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Plan {
    pub descriptor: String,
    pub arguments: Vec<Argument>,
    pub parts: Vec<Part>,
}
pub(super) fn emit(assembly: &mut String, plans: &[Plan]) -> Result<()> {
    use std::fmt::Write;
    assembly.push_str("\nEXTERN boom_string_concat:PROC\n.const\n");
    for (id, plan) in plans.iter().enumerate() {
        for (part_id, part) in plan.parts.iter().enumerate() {
            if let Part::Literal { utf16 } = part {
                writeln!(assembly, "ALIGN 2\nboom_concat_{id}_{part_id} LABEL WORD")?;
                for chunk in utf16.chunks(16) {
                    writeln!(
                        assembly,
                        "    WORD {}",
                        chunk
                            .iter()
                            .map(|v| format!("0{v:04X}h"))
                            .collect::<Vec<_>>()
                            .join(", ")
                    )?;
                }
            }
        }
        writeln!(assembly, "ALIGN 8\nboom_concat_rows{id} LABEL BYTE")?;
        if plan.parts.is_empty() {
            assembly.push_str("    QWORD 0, 0, 0\n");
        }
        for (part_id, part) in plan.parts.iter().enumerate() {
            match part {
                Part::Literal { utf16 } => writeln!(
                    assembly,
                    "    DWORD 0, 0\n    QWORD OFFSET boom_concat_{id}_{part_id}, {}",
                    utf16.len()
                )?,
                Part::Argument { index, value } => writeln!(
                    assembly,
                    "    DWORD {}, {index}\n    QWORD 0, 0",
                    match value {
                        Argument::Int => 1,
                        Argument::Long => 2,
                        Argument::Boolean => 3,
                        Argument::Char => 4,
                        Argument::String => 5,
                    }
                )?,
            }
        }
        writeln!(
            assembly,
            "ALIGN 8\nboom_concat_plan{id} DWORD 0434F4E43h, 1, {}, {}\n    QWORD OFFSET boom_concat_rows{id}, OFFSET boom_string_pool",
            plan.parts.len(),
            plan.arguments.len()
        )?;
    }
    assembly.push_str(".code\n");
    Ok(())
}

fn arguments(descriptor: &str) -> Result<Vec<Argument>> {
    let mut text = descriptor
        .strip_prefix('(')
        .context("Invalid concat descriptor")?;
    let mut output = Vec::new();
    while !text.starts_with(')') {
        let (kind, size) = if text.starts_with("Ljava/lang/String;") {
            (Argument::String, 18)
        } else {
            (
                match text.as_bytes().first() {
                    Some(b'I' | b'B' | b'S') => Argument::Int,
                    Some(b'J') => Argument::Long,
                    Some(b'Z') => Argument::Boolean,
                    Some(b'C') => Argument::Char,
                    _ => {
                        bail!("Concat argument requires additional Java conversion support: {text}")
                    }
                },
                1,
            )
        };
        output.push(kind);
        text = &text[size..];
        ensure!(
            output.len() <= 16,
            "Concat currently supports at most 16 values"
        );
    }
    ensure!(
        text == ")Ljava/lang/String;",
        "Concat currently requires a String return type"
    );
    Ok(output)
}
fn recipe(arguments: &[Argument], units: &[u16], constants: &[Vec<u16>]) -> Result<Vec<Part>> {
    let (mut dynamic, mut constant) = (0, 0);
    let mut literal = Vec::new();
    let mut parts = Vec::new();
    for &unit in units {
        match unit {
            1 => {
                if !literal.is_empty() {
                    parts.push(Part::Literal {
                        utf16: std::mem::take(&mut literal),
                    });
                }
                let &value = arguments
                    .get(dynamic)
                    .context("Too many concat argument markers")?;
                parts.push(Part::Argument {
                    index: dynamic,
                    value,
                });
                dynamic += 1;
            }
            2 => {
                literal.extend_from_slice(
                    constants
                        .get(constant)
                        .context("Too many concat constant markers")?,
                );
                constant += 1;
            }
            _ => literal.push(unit),
        }
        ensure!(
            literal.len() <= 65535,
            "Expanded concat literal exceeds per-part UTF16 budget"
        );
    }
    if !literal.is_empty() {
        parts.push(Part::Literal { utf16: literal });
    }
    ensure!(
        dynamic == arguments.len() && constant == constants.len(),
        "Concat recipe argument/constant count mismatch"
    );
    ensure!(parts.len() <= 256, "Concat recipe exceeds part budget");
    Ok(parts)
}
pub fn plan(class: &ClassFile, site: &DynamicSite) -> Result<Plan> {
    let bootstrap = &site.bootstrap;
    ensure!(
        bootstrap.reference_kind == 6
            && !bootstrap.interface
            && bootstrap.owner == "java/lang/invoke/StringConcatFactory",
        "Invokedynamic bootstrap {}.{} requires its own runtime",
        bootstrap.owner,
        bootstrap.name
    );
    let arguments = arguments(&site.descriptor)?;
    let parts = match (bootstrap.name.as_str(), bootstrap.descriptor.as_str()) {
        (
            "makeConcat",
            "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;",
        ) => {
            ensure!(
                site.arguments.is_empty(),
                "makeConcat does not take static arguments"
            );
            recipe(&arguments, &vec![1; arguments.len()], &[])?
        }
        (
            "makeConcatWithConstants",
            "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/invoke/CallSite;",
        ) => {
            let (&index, constants) = site
                .arguments
                .split_first()
                .context("Missing concat recipe")?;
            let units = class
                .string_literal(index)?
                .context("Concat recipe must be a String constant")?;
            let mut values = Vec::new();
            let mut total = 0usize;
            for &id in constants {
                let value=class.string_literal(id)?.context("Static concat constants currently require String values; other conversions are not implemented")?;
                total = total
                    .checked_add(value.len())
                    .context("Concat constants size overflow")?;
                ensure!(
                    total <= 8 * 1024 * 1024,
                    "Concat static constants exceed UTF16 budget"
                );
                values.push(value);
            }
            recipe(&arguments, &units, &values)?
        }
        _ => bail!("Unsupported StringConcatFactory bootstrap signature"),
    };
    Ok(Plan {
        descriptor: site.descriptor.clone(),
        arguments,
        parts,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn recipe_preserves_utf16_and_does_not_reinterpret_static_constants() {
        let parts = recipe(
            &[Argument::Long, Argument::String],
            &[65, 1, 2, 0, 1],
            &[vec![1, 2, 0xd800]],
        )
        .unwrap();
        assert_eq!(
            parts,
            vec![
                Part::Literal { utf16: vec![65] },
                Part::Argument {
                    index: 0,
                    value: Argument::Long
                },
                Part::Literal {
                    utf16: vec![1, 2, 0xd800, 0]
                },
                Part::Argument {
                    index: 1,
                    value: Argument::String
                }
            ]
        );
        assert!(recipe(&[], &[1], &[]).is_err());
        assert!(recipe(&[Argument::Long], &[], &[]).is_err());
        assert!(recipe(&[], &[2], &[]).is_err());
        assert!(recipe(&[], &[], &[vec![]]).is_err());
    }
    #[test]
    fn concat_conversion_types_and_result_are_explicit() {
        assert_eq!(
            arguments("(IJZCLjava/lang/String;BS)Ljava/lang/String;").unwrap(),
            vec![
                Argument::Int,
                Argument::Long,
                Argument::Boolean,
                Argument::Char,
                Argument::String,
                Argument::Int,
                Argument::Int
            ]
        );
        for descriptor in [
            "(F)Ljava/lang/String;",
            "(D)Ljava/lang/String;",
            "(Ljava/lang/Object;)Ljava/lang/String;",
            "(I)Ljava/lang/Object;",
            "(I)",
            "([I)Ljava/lang/String;",
        ] {
            assert!(arguments(descriptor).is_err());
        }
    }
    #[test]
    fn expanded_constant_recipe_is_bounded_before_assembly() {
        assert!(recipe(&[], &[2, 2], &[vec![65; 32768], vec![65; 32768]]).is_err());
    }
}
