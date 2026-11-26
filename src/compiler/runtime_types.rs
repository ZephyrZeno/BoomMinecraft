//! Immutable bridge between heap header tags and loader-aware TypeDesc identities.
use super::{classfile::ClassFile, types};
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Debug, Serialize, Deserialize)]
pub struct Binding {
    pub tag: String,
    pub type_id: usize,
    pub kind: u32,
    pub payload_bytes: usize,
    pub references: usize,
    pub element_shift: u32,
}
pub(super) fn prepare(
    registry: &mut types::Registry<'_>,
    classes: &[ClassFile],
    owners: &BTreeSet<usize>,
    layouts: &[super::program::ProgramObjectLayout],
    modules: bool,
    layers: bool,
    loaders: &[&str],
) -> Result<Vec<Binding>> {
    ensure!(
        loaders.len() == classes.len(),
        "Missing defining loaders for runtime bindings"
    );
    let mut rows = Vec::new();
    for (tag, descriptor, shift) in [
        (260, "[Z", 0),
        (261, "[C", 1),
        (262, "[F", 2),
        (263, "[D", 3),
        (264, "[B", 0),
        (265, "[S", 1),
        (266, "[I", 2),
        (267, "[J", 3),
    ] {
        rows.push(Binding {
            tag: tag.to_string(),
            type_id: registry.field("bootstrap", descriptor)?,
            kind: 1,
            payload_bytes: 0,
            references: 0,
            element_shift: shift,
        });
    }
    for &owner in owners {
        let class = &classes[owner];
        let loader = loaders[owner];
        let layout = &layouts
            .iter()
            .find(|layout| layout.class_id == owner)
            .ok_or_else(|| anyhow::anyhow!("Missing actual object layout"))?
            .layout;
        rows.push(Binding {
            tag: format!("OFFSET boom_layout{owner}"),
            type_id: registry.class(loader, &class.name)?,
            kind: 0,
            payload_bytes: layout.payload_bytes,
            references: layout.reference_prefix_fields,
            element_shift: 0,
        });
        rows.push(Binding {
            tag: format!("OFFSET boom_ref_layout{owner}"),
            type_id: registry.field(loader, &format!("[L{};", class.name))?,
            kind: 2,
            payload_bytes: 0,
            references: 0,
            element_shift: 3,
        });
    }
    for (name, tag, payload, refs) in [
        ("java/lang/String", "boom_string", 16, 1),
        ("java/lang/Class", "boom_mirror", 8, 0),
    ] {
        rows.push(Binding {
            tag: format!("OFFSET {tag}_layout"),
            type_id: registry.class("bootstrap", name)?,
            kind: 0,
            payload_bytes: payload,
            references: refs,
            element_shift: 0,
        });
        rows.push(Binding {
            tag: format!("OFFSET {tag}_array_layout"),
            type_id: registry.field("bootstrap", &format!("[L{name};"))?,
            kind: 2,
            payload_bytes: 0,
            references: 0,
            element_shift: 3,
        });
    }
    if modules {
        rows.push(Binding {
            tag: "OFFSET boom_module_layout".into(),
            type_id: registry.class("bootstrap", "java/lang/Module")?,
            kind: 0,
            payload_bytes: 8,
            references: 0,
            element_shift: 0,
        });
    }
    if layers {
        rows.push(Binding {
            tag: "OFFSET boom_layer_layout".into(),
            type_id: registry.class("bootstrap", "java/lang/ModuleLayer")?,
            kind: 0,
            payload_bytes: 8,
            references: 0,
            element_shift: 0,
        });
    }
    ensure!(rows.len() <= 65536, "Runtime tag map exceeds budget");
    Ok(rows)
}
pub(super) fn emit(assembly: &mut String, rows: &[Binding], type_count: usize) -> Result<()> {
    use std::fmt::Write;
    assembly.push_str("\nEXTERN boom_runtime_cast:PROC\nEXTERN boom_runtime_instanceof:PROC\nEXTERN boom_runtime_getclass:PROC\n.const\nALIGN 8\nboom_runtime_type_rows LABEL BYTE\n");
    for row in rows {
        ensure!(
            row.type_id < type_count,
            "Runtime type binding is out of bounds"
        );
        writeln!(
            assembly,
            "    QWORD {}, OFFSET boom_t{}\n    DWORD {}, {}\n    QWORD {}\n    DWORD {}, {}",
            row.tag,
            row.type_id,
            row.type_id,
            row.kind,
            row.payload_bytes,
            row.references,
            row.element_shift
        )?;
    }
    writeln!(
        assembly,
        "ALIGN 8\nboom_runtime_type_map DWORD 052545950h, 1, {}, {type_count}\n    QWORD OFFSET boom_runtime_type_rows, OFFSET boom_mirror_pool\n.code",
        rows.len()
    )?;
    Ok(())
}
