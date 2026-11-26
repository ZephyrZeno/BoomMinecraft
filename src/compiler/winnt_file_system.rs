//! WinNTFileSystem's VM field cache and optional Windows final-path function.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/io/WinNTFileSystem";
pub const FILE: &str = "java/io/File";
pub(super) fn initialization(o: &str, n: &str, d: &str) -> bool {
    o == OWNER && n == "initIDs" && d == "()V"
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub file_origin: ClassOrigin,
    pub class_id: usize,
    pub file_class_id: usize,
    pub file_layout: numeric::ObjectLayout,
    pub path_offset: usize,
    pub bindings: Vec<Binding>,
    pub native_source_sha256: String,
    pub file_initialization_required: bool,
    pub automatic_gc: bool,
}
impl Plan {
    pub(super) fn new(
        registry: &mut types::Registry<'_>,
        owner: usize,
        file: usize,
        layout: numeric::ObjectLayout,
    ) -> Result<Self> {
        let mut origins = Vec::new();
        for name in [OWNER, FILE] {
            let id = registry.class("bootstrap", name)?;
            let types::Type::Class { key, origin, .. } = &registry.types[id] else {
                unreachable!()
            };
            ensure!(
                key.loader == "bootstrap"
                    && origin.source_id == "jdk:java.base"
                    && origin.generated.is_none(),
                "Windows file system requires original java.base source"
            );
            origins.push(origin.as_ref().clone());
        }
        let id = registry.class("bootstrap", OWNER)?;
        let class = registry.definition(id).unwrap();
        let m = class.method("initIDs", Some("()V"))?;
        ensure!(
            m.access == 0x10a && m.code.is_none(),
            "WinNTFileSystem.initIDs declaration changed"
        );
        let id = registry.class("bootstrap", FILE)?;
        let class = registry.definition(id).unwrap();
        ensure!(
            class.field_info.iter().any(|f| f.name == "path"
                && f.descriptor == "Ljava/lang/String;"
                && f.access == 0x12),
            "Original File.path declaration changed"
        );
        let f = layout
            .fields
            .iter()
            .find(|f| {
                f.name == "path"
                    && f.descriptor == "Ljava/lang/String;"
                    && f.declaring_class.as_deref() == Some(FILE)
            })
            .context("Missing translated File.path slot")?;
        let offset = f.offset;
        ensure!(
            f.storage_bytes == Some(8)
                && offset % 8 == 0
                && offset < layout.reference_prefix_fields * 8
                && offset + 8 <= layout.payload_bytes,
            "File.path must be a complete reference slot"
        );
        Ok(Self {
            abi: 1,
            origin: origins.remove(0),
            file_origin: origins.remove(0),
            class_id: owner,
            file_class_id: file,
            file_layout: layout,
            path_offset: offset,
            bindings: Vec::new(),
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/winnt_file_system.asm"
            ))
            .sha256,
            file_initialization_required: true,
            automatic_gc: false,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
    ) -> Result<()> {
        let (o, n, d, i) = caller.static_method_reference(constant)?;
        ensure!(
            !i && initialization(&o, &n, &d) && caller.name == OWNER && source == &self.origin,
            "WinNTFileSystem.initIDs is private to original WinNTFileSystem source"
        );
        if !self
            .bindings
            .iter()
            .any(|b| b.caller == *source && b.constant == constant)
        {
            self.bindings.push(Binding {
                caller: source.clone(),
                constant,
            });
            self.bindings.sort_by_key(|b| b.constant);
        }
        Ok(())
    }
    pub(super) fn emit(&self, out: &mut String) {
        out.push_str(&format!("EXTERN boom_winfs_init:PROC\n.data\nALIGN 8\nboom_winfs_pool DWORD 049534657h,1\n    QWORD OFFSET boom_layout{},{}\n    QWORD 0,0\n    DWORD 0,0\n.code\nPUBLIC boom_get_winfs_pool\nboom_get_winfs_pool PROC\n    lea rax,boom_winfs_pool\n    ret\nboom_get_winfs_pool ENDP\n",self.file_class_id,self.path_offset));
    }
}

#[derive(Debug, Serialize)]
pub struct Inspection {
    pub plan: Plan,
    pub original_file: std::path::PathBuf,
    pub original_file_system: std::path::PathBuf,
    pub executable_class_ids_are_placeholders: bool,
    #[serde(rename = "original_Java_initializers_executed")]
    pub original_java_initializers_executed: bool,
    pub full_game_ready: bool,
}
pub fn inspect(
    inputs: &crate::lock::InputLock,
    manifest: &std::path::Path,
    output: &std::path::Path,
) -> Result<Inspection> {
    use super::{hierarchy, types::TypeProvider};
    let provider = types::VanillaTypes::new(inputs, manifest)?;
    let mut registry = types::Registry::new(&provider);
    let file = registry.class("bootstrap", FILE)?;
    let physical = hierarchy::compact_layout(&registry, file)?;
    let layout = numeric::ObjectLayout {
        abi: 2,
        payload_bytes: physical.payload_bytes,
        reference_prefix_fields: physical.reference_prefix,
        fields: physical
            .fields
            .iter()
            .map(|f| {
                let types::Type::Class { key, .. } = &registry.types[f.member.owner] else {
                    unreachable!()
                };
                numeric::FieldLayout {
                    name: f.member.name.clone(),
                    descriptor: f.member.descriptor.clone(),
                    offset: f.offset,
                    declaring_class: Some(key.name.clone()),
                    declaring_field: Some(f.member.index),
                    storage_bytes: Some(f.storage_bytes),
                }
            })
            .collect(),
    };
    let mut plan = Plan::new(&mut registry, 0, 1, layout)?;
    let (bytes, origin) = provider.resolve("bootstrap", OWNER)?;
    let class = ClassFile::parse(&bytes)?;
    let code = class
        .method("<clinit>", Some("()V"))?
        .code
        .as_ref()
        .context("Missing WinNTFileSystem initializer")?;
    ensure!(
        code.bytes.len() == 51 && code.bytes[47] == 0xb8 && code.bytes[50] == 0xb1,
        "WinNTFileSystem initializer callsite changed"
    );
    plan.bind(
        &class,
        &origin,
        u16::from_be_bytes([code.bytes[48], code.bytes[49]]),
    )?;
    let output = std::path::absolute(output)?;
    let original_file_system = output.join("WinNTFileSystem.class");
    let original_file = output.join("File.class");
    files::write_atomic(&original_file_system, &bytes)?;
    files::write_atomic(&original_file, &provider.resolve("bootstrap", FILE)?.0)?;
    let result = Inspection {
        plan,
        original_file,
        original_file_system,
        executable_class_ids_are_placeholders: true,
        original_java_initializers_executed: false,
        full_game_ready: false,
    };
    files::write_atomic(
        &output.join("inspection.json"),
        &serde_json::to_vec_pretty(&result)?,
    )?;
    Ok(result)
}
