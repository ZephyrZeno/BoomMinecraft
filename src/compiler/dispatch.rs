//! Closed-module dispatch tables. Rust selects source members offline; all
//! receiver validation and invocation below execute as generated x86-64 MASM.
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::fmt::Write;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Row {
    pub receiver_class: Option<usize>,
    pub receiver_type: usize,
    pub target: Option<usize>,
    pub error: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_string: Option<super::numeric::StringIntrinsic>,
    #[serde(default, skip_serializing_if = "is_false")]
    pub runtime_identity_hash: bool,
    #[serde(default, skip_serializing_if = "is_false")]
    pub runtime_builder_snapshot: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_reflection: Option<ReflectionTarget>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflectionTarget {
    pub field: bool,
    pub operation: u32,
    pub declaration: crate::bytecode::ClassOrigin,
    pub code_sha256: String,
}
pub(super) fn reflection_target(
    registry: &super::types::Registry<'_>,
    member: &super::hierarchy::Member,
) -> Result<Option<ReflectionTarget>> {
    use super::{reflect_constructors as constructors, reflect_fields as fields, types::Type};
    let Type::Class { key, origin, .. } = &registry.types[member.owner] else {
        unreachable!()
    };
    if key.loader != "bootstrap" {
        return Ok(None);
    }
    let (field, operation) = if let Some(op) =
        constructors::Operation::resolve(&key.name, &member.name, &member.descriptor)
    {
        if op.lookup() || op == constructors::Operation::Invoke {
            return Ok(None);
        }
        (false, op as u32)
    } else if let Some(op) = fields::Operation::resolve(&key.name, &member.name, &member.descriptor)
    {
        if op == fields::Operation::Declared {
            return Ok(None);
        }
        (true, op as u32)
    } else {
        return Ok(None);
    };
    ensure!(
        origin.source_id == "jdk:java.base" && origin.generated.is_none(),
        "Reflection dispatch requires original bootstrap source"
    );
    let method = &registry
        .definition(member.owner)
        .context("Missing reflection dispatch declaration")?
        .methods[member.index];
    ensure!(
        method.access & 0x109 == 1,
        "Reflection dispatch requires public instance Java Code"
    );
    let code = method
        .code
        .as_ref()
        .context("Missing original reflection dispatch Code")?;
    Ok(Some(ReflectionTarget {
        field,
        operation,
        declaration: origin.as_ref().clone(),
        code_sha256: crate::files::digest_bytes(&code.bytes).sha256,
    }))
}
fn is_false(value: &bool) -> bool {
    !value
}
pub(super) fn type_name(types: &[super::types::Type], id: usize) -> String {
    if let super::types::Type::Array { component } = &types[id] {
        format!("{}[]", type_name(types, *component))
    } else {
        super::mirrors::name(types, id)
    }
}
pub(super) fn modifier_text(flags: u16) -> String {
    [
        (1, "public"),
        (4, "protected"),
        (2, "private"),
        (0x400, "abstract"),
        (8, "static"),
        (0x10, "final"),
        (0x80, "transient"),
        (0x40, "volatile"),
        (0x20, "synchronized"),
        (0x100, "native"),
        (0x800, "strictfp"),
        (0x200, "interface"),
    ]
    .into_iter()
    .filter_map(|(bit, name)| (flags & bit != 0).then_some(name))
    .collect::<Vec<_>>()
    .join(" ")
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Site {
    pub id: usize,
    pub caller: String,
    pub constant: u16,
    pub owner: String,
    pub name: String,
    pub descriptor: String,
    pub interface: bool,
    #[serde(default)]
    pub invocation: String,
    pub rows: Vec<Row>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub array_identity_hash: Option<usize>,
}
pub(super) fn emit(assembly: &mut String, sites: &[Site]) -> Result<()> {
    if sites.is_empty() {
        return Ok(());
    }
    assembly.push_str("\nEXTERN boom_runtime_type:PROC\n.code\n");
    if sites
        .iter()
        .flat_map(|s| &s.rows)
        .any(|r| r.runtime_reflection.as_ref().is_some_and(|r| r.field))
    {
        assembly.push_str("EXTERN boom_field_virtual:PROC\n");
    }
    if sites
        .iter()
        .flat_map(|s| &s.rows)
        .any(|r| r.runtime_reflection.as_ref().is_some_and(|r| !r.field))
    {
        assembly.push_str("EXTERN boom_constructor_virtual:PROC\n");
    }
    if sites.iter().any(|s| s.array_identity_hash.is_some()) {
        assembly.push_str("EXTERN boom_type_assignable:PROC\n");
    }
    for site in sites {
        let id = site.id;
        writeln!(
            assembly,
            "; {} {}.{}{}\nboom_dispatch{id} PROC FRAME\n    sub rsp, 72\n    .allocstack 72\n    .endprolog\n    mov QWORD PTR [rsp+48], rcx\n    mov QWORD PTR [rsp+56], rdx\n    mov DWORD PTR [rsp+32], 0\n    mov r8, rcx\n    mov rcx, QWORD PTR [rdx]\n    lea rdx, boom_runtime_type_map\n    call boom_runtime_type\n    test rax, rax\n    jz boom_dispatch{id}_done",
            site.invocation, site.owner, site.name, site.descriptor
        )?;
        for (index, row) in site.rows.iter().enumerate() {
            writeln!(
                assembly,
                "    lea r11, boom_t{}\n    cmp rax, r11\n    je boom_dispatch{id}_row{index}",
                row.receiver_type
            )?;
        }
        // A valid object outside this site's receiver closure is incompatible.
        if let Some(constraint) = site.array_identity_hash {
            writeln!(
                assembly,
                "    cmp DWORD PTR [rax+8], 3\n    jne boom_dispatch{id}_incompatible\n    mov rcx, rax\n    lea rdx, boom_t{constraint}\n    call boom_type_assignable\n    test eax, eax\n    jz boom_dispatch{id}_incompatible\n    mov rcx, QWORD PTR [rsp+48]\n    mov rdx, QWORD PTR [rsp+56]\n    mov rdx, QWORD PTR [rdx]\n    call boom_identity_hash\n    jmp boom_dispatch{id}_done\nboom_dispatch{id}_incompatible:"
            )?;
        }
        writeln!(
            assembly,
            "    mov r10, QWORD PTR [rsp+48]\n    mov DWORD PTR [r10], 13\n    xor eax, eax\n    jmp boom_dispatch{id}_done"
        )?;
        for (index, row) in site.rows.iter().enumerate() {
            writeln!(assembly, "boom_dispatch{id}_row{index}:")?;
            if let Some(operation) = row.runtime_string {
                writeln!(
                    assembly,
                    "    mov rcx, QWORD PTR [rsp+48]\n    mov rdx, QWORD PTR [rsp+56]\n    lea r8, boom_string_pool\n    mov r9d, {}\n    call boom_string_intrinsic",
                    operation as u32
                )?;
            } else if let Some(target) = &row.runtime_reflection {
                let symbol = if target.field {
                    "boom_field_virtual"
                } else {
                    "boom_constructor_virtual"
                };
                writeln!(
                    assembly,
                    "    mov rcx, QWORD PTR [rsp+48]\n    mov rdx, QWORD PTR [rsp+56]\n    mov r9d, {}\n    call {symbol}",
                    target.operation
                )?;
            } else if row.runtime_builder_snapshot {
                writeln!(
                    assembly,
                    "    mov rcx, QWORD PTR [rsp+48]\n    mov rdx, QWORD PTR [rsp+56]\n    lea r8, boom_builder_snapshot_pool\n    call boom_builder_snapshot"
                )?;
            } else if row.runtime_identity_hash {
                writeln!(
                    assembly,
                    "    mov rcx, QWORD PTR [rsp+48]\n    mov rdx, QWORD PTR [rsp+56]\n    mov rdx, QWORD PTR [rdx]\n    call boom_identity_hash"
                )?;
            } else if let Some(target) = row.target {
                // Instance envelopes do not initialize the declaring interface.
                // They do acquire the selected method's monitor when synchronized.
                writeln!(
                    assembly,
                    "    mov rcx, QWORD PTR [rsp+48]\n    mov rdx, QWORD PTR [rsp+56]\n    call boom_m{target}\n    mov DWORD PTR [rsp+32], 1"
                )?;
            } else {
                writeln!(
                    assembly,
                    "    mov r10, QWORD PTR [rsp+48]\n    mov DWORD PTR [r10], {}\n    xor eax, eax",
                    row.error
                )?;
            }
            writeln!(assembly, "    jmp boom_dispatch{id}_done")?;
        }
        writeln!(
            assembly,
            "boom_dispatch{id}_done:\n    mov edx, DWORD PTR [rsp+32]\n    add rsp, 72\n    ret\nboom_dispatch{id} ENDP"
        )?;
    }
    Ok(())
}
