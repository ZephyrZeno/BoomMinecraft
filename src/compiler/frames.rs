//! Immutable Java method identities for assembly shadow frames and backtraces.
use super::{classfile::ClassFile, types};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Method {
    pub id: usize,
    pub class_name: String,
    pub name: String,
    pub descriptor: String,
    pub source: ClassOrigin,
    pub source_file: Option<String>,
    pub type_id: usize,
    pub flags: u32,
    pub code_length: usize,
    pub lines: Vec<super::classfile::LineNumber>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub node_bytes: usize,
    pub maximum_depth: usize,
    pub methods: Vec<Method>,
}
impl Plan {
    pub(super) fn new(methods: Vec<Method>) -> Result<Self> {
        ensure!(
            !methods.is_empty() && methods.len() <= 262144,
            "Invalid Java shadow-frame method count"
        );
        for (i, m) in methods.iter().enumerate() {
            ensure!(
                i == 0 || methods[i - 1].id < m.id,
                "Shadow-frame identities must be unique and ordered"
            );
            ensure!(
                m.code_length > 0 && m.code_length <= 65535 && m.flags & !7 == 0,
                "Invalid Java frame metadata"
            );
        }
        Ok(Self {
            abi: 2,
            node_bytes: 48,
            maximum_depth: 128,
            methods,
        })
    }
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        ensure!(
            self.abi == 2 && self.node_bytes == 48 && self.maximum_depth == 128,
            "Unsupported frame protocol"
        );
        out.push_str("EXTERN boom_trace_enter:PROC\nEXTERN boom_trace_leave:PROC\nEXTERN boom_trace_release:PROC\n.const\n");
        for m in &self.methods {
            if !m.lines.is_empty() {
                out.push_str(&format!("ALIGN 4\nboom_trace_lines{} LABEL DWORD\n", m.id));
                for line in &m.lines {
                    out.push_str(&format!("    DWORD {}, {}\n", line.pc, line.line));
                }
            }
        }
        out.push_str("ALIGN 8\nboom_trace_methods LABEL BYTE\n");
        for m in &self.methods {
            let lines = if m.lines.is_empty() {
                "0".into()
            } else {
                format!("OFFSET boom_trace_lines{}", m.id)
            };
            out.push_str(&format!("boom_trace_method{} DWORD {}, {}\n    QWORD OFFSET boom_t{}\n    DWORD {}, {}\n    QWORD {}\n",m.id,m.id,m.flags,m.type_id,m.code_length,m.lines.len(),lines));
        }
        out.push_str(&format!(".data\nALIGN 8\nboom_trace_pool DWORD 05452504Ch, 2, 0, 0FFFFFFFFh\n    DWORD {}, 0\n    QWORD OFFSET boom_trace_methods, 0, 0\n.code\nPUBLIC boom_get_trace_pool\nboom_get_trace_pool PROC\n    lea rax, boom_trace_pool\n    ret\nboom_get_trace_pool ENDP\nPUBLIC boom_release_trace_pool\nboom_release_trace_pool PROC\n    lea rcx, boom_trace_pool\n    jmp boom_trace_release\nboom_release_trace_pool ENDP\n",self.methods.len()));
        Ok(())
    }
}
pub(super) fn method(
    registry: &mut types::Registry<'_>,
    class: &ClassFile,
    member: usize,
    id: usize,
    source: &ClassOrigin,
) -> Result<Method> {
    let m = &class.methods[member];
    let code = m
        .code
        .as_ref()
        .context("Java shadow frame requires original Code")?;
    let type_id = registry.class(&source.loader, &class.name)?;
    Ok(Method {
        id,
        class_name: class.name.clone(),
        name: m.name.clone(),
        descriptor: m.descriptor.clone(),
        source: source.clone(),
        source_file: class.source_file.clone(),
        type_id,
        flags: u32::from(m.name == "<init>")
            | (u32::from(m.name == "fillInStackTrace") << 1)
            | (u32::from(source.generated.is_some()) << 2),
        code_length: code.bytes.len(),
        lines: m.line_numbers.clone(),
    })
}
