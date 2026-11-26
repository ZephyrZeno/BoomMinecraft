//! Per-actual-class field addresses for reference-prefix object layouts.
//! Field identity is the declaring class and field index, never just its name.
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::fmt::Write;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Row {
    pub receiver_class: usize,
    pub receiver_type: usize,
    pub offset: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Map {
    pub id: usize,
    pub declaring_class: usize,
    pub field_index: usize,
    pub receiver_constraint: usize,
    pub rows: Vec<Row>,
}
pub(super) fn emit(assembly: &mut String, maps: &[Map]) -> Result<()> {
    if maps.is_empty() {
        return Ok(());
    }
    if !assembly.contains("EXTERN boom_runtime_type:PROC") {
        assembly.push_str("\nEXTERN boom_runtime_type:PROC\n");
    }
    assembly.push_str(".code\n");
    for map in maps {
        let id = map.id;
        writeln!(
            assembly,
            "boom_field_map{id} PROC FRAME\n    sub rsp, 72\n    .allocstack 72\n    .endprolog\n    mov QWORD PTR [rsp+48], rcx\n    mov QWORD PTR [rsp+56], rdx\n    mov r8, rdx\n    lea rdx, boom_runtime_type_map\n    call boom_runtime_type\n    test rax, rax\n    jz boom_field_map{id}_done"
        )?;
        for (index, row) in map.rows.iter().enumerate() {
            writeln!(
                assembly,
                "    lea r11, boom_t{}\n    cmp rax, r11\n    je boom_field_map{id}_row{index}",
                row.receiver_type
            )?;
        }
        writeln!(
            assembly,
            "    mov r10, QWORD PTR [rsp+56]\n    mov DWORD PTR [r10], 7\n    xor eax, eax\n    jmp boom_field_map{id}_done"
        )?;
        for (index, row) in map.rows.iter().enumerate() {
            writeln!(
                assembly,
                "boom_field_map{id}_row{index}:\n    mov rax, QWORD PTR [rsp+48]\n    add rax, {}\n    jmp boom_field_map{id}_done",
                row.offset
            )?;
        }
        writeln!(
            assembly,
            "boom_field_map{id}_done:\n    add rsp, 72\n    ret\nboom_field_map{id} ENDP"
        )?;
    }
    Ok(())
}
