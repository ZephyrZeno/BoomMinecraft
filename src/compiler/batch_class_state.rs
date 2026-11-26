//! Source static storage and real initialization trampolines for the bulk backend.
//! ConstantValue assignment, dependency order and Java <clinit> remain executable
//! MASM, never host callbacks or a pre-initialized success flag.
use super::{
    batch_catalog::Catalog,
    batch_compile::{
        ASSEMBLY_BODY_BUDGET, AssemblyBodies, AssemblyUnit, MethodResult, Symbols, write_unit,
    },
    hierarchy,
    symbolic::Constant,
    translation_ir,
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, bail, ensure};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt::Write as _,
    fs,
    io::Write,
    path::Path,
};
use zip::{ZipWriter, write::SimpleFileOptions};

#[derive(Serialize)]
pub struct StaticField {
    pub index: usize,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub reference: bool,
    pub declared_storage_bytes: usize,
    pub constant: Option<u16>,
    pub initial_bits: u64,
    pub string_constant: Option<u16>,
}
#[derive(Serialize)]
pub struct Initializer {
    pub method: usize,
    pub code_sha256: String,
    pub assembly_emitted: bool,
}
#[derive(Serialize)]
pub struct ClassState {
    pub class_id: usize,
    pub source_sha256: String,
    pub name: String,
    pub access: u16,
    pub fields: Vec<StaticField>,
    pub initializer: Option<Initializer>,
    pub dependencies: Vec<usize>,
    pub diagnostic: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub vm_post_initializer: Option<&'static str>,
}
impl ClassState {
    pub(super) fn from_source(class: &translation_ir::Class, methods: &[MethodResult]) -> Self {
        let mut state = Self {
            class_id: class.class_id,
            source_sha256: class.origin.sha256.clone(),
            name: class.name.clone(),
            access: class.access,
            fields: vec![],
            initializer: None,
            dependencies: vec![],
            diagnostic: None,
            vm_post_initializer: (class.name == super::batch_unsafe::CONSTANTS
                && class.origin.loader == "bootstrap"
                && class.origin.source_id == "jdk:java.base"
                && class.origin.generated.is_none())
            .then_some("unsafe_constants"),
        };
        let result = (|| -> Result<()> {
            for (index, field) in class
                .fields
                .iter()
                .enumerate()
                .filter(|(_, f)| f.access & 8 != 0)
            {
                let reference = field.descriptor.starts_with(['L', '[']);
                let (initial_bits, string_constant) = if let Some(cp) = field.constant_value {
                    constant_value(
                        &field.descriptor,
                        class
                            .constants
                            .get(&cp)
                            .context("Missing source ConstantValue")?,
                        cp,
                    )?
                } else {
                    (0, None)
                };
                state.fields.push(StaticField {
                    index,
                    name: field.name.clone(),
                    descriptor: field.descriptor.clone(),
                    access: field.access,
                    reference,
                    declared_storage_bytes: hierarchy::storage_bytes(&field.descriptor)?,
                    constant: field.constant_value,
                    initial_bits,
                    string_constant,
                });
            }
            for (index, method) in class
                .methods
                .iter()
                .enumerate()
                .filter(|(_, m)| m.name == "<clinit>")
            {
                ensure!(
                    state.initializer.is_none()
                        && method.descriptor == "()V"
                        && method.access & 0x500 == 0
                        && (class.origin.java_class_major < 51 || method.access & 8 != 0),
                    "Invalid original class initialization method"
                );
                state.initializer = Some(Initializer {
                    method: method.id,
                    code_sha256: method
                        .code_sha256
                        .clone()
                        .context("Class initializer has no Java Code")?,
                    assembly_emitted: methods
                        .get(index)
                        .context("Missing initializer compilation result")?
                        .assembly_emitted,
                });
            }
            Ok(())
        })();
        if let Err(error) = result {
            state.diagnostic = Some(format!("{error:#}"));
        }
        state
    }
}
fn constant_value(descriptor: &str, value: &Constant, cp: u16) -> Result<(u64, Option<u16>)> {
    let bits = match (descriptor, value) {
        ("Ljava/lang/String;", Constant::StringUtf16(_)) => return Ok((0, Some(cp))),
        ("Z", Constant::Int(value)) => (*value as u32 & 1) as u64,
        ("B", Constant::Int(value)) => *value as i8 as i32 as u32 as u64,
        ("S", Constant::Int(value)) => *value as i16 as i32 as u32 as u64,
        ("C", Constant::Int(value)) => *value as u16 as u64,
        ("I", Constant::Int(value)) => *value as u32 as u64,
        ("J", Constant::Long(value)) => *value as u64,
        ("F", Constant::FloatBits(value)) => u64::from(*value),
        ("D", Constant::DoubleBits(value)) => *value,
        _ => bail!("ConstantValue does not match its original static field descriptor"),
    };
    Ok((bits, None))
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub class_capacity: usize,
    pub provided_classes: usize,
    pub omitted_classes: Vec<usize>,
    pub static_fields: usize,
    pub static_reference_fields: usize,
    pub constant_values: usize,
    pub string_constants: usize,
    pub java_initializers: usize,
    pub emitted_java_initializers: usize,
    pub initialization_dependencies: usize,
    pub root_cells: usize,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub descriptor_abi: u32,
    pub context_bytes: usize,
    pub initial_state: u32,
    pub initial_static_storage_zero: bool,
    pub complete_original_class_initialization_verified: bool,
    pub linked: bool,
    pub automatic_gc: bool,
}
#[derive(Serialize)]
struct IndexedClass<'a> {
    #[serde(flatten)]
    state: &'a ClassState,
    assembly_unit: Option<usize>,
}

pub(super) fn generate(
    catalog: &Catalog,
    mut requests: Vec<ClassState>,
    output: &Path,
    assemble: bool,
) -> Result<Summary> {
    requests.sort_by_key(|r| r.class_id);
    ensure!(
        requests.len() == catalog.nodes.len()
            && requests.iter().enumerate().all(|(i, r)| r.class_id == i),
        "Class-state source coverage differs"
    );
    let mut provided = BTreeSet::new();
    for state in &mut requests {
        let node = &catalog.nodes[state.class_id];
        ensure!(
            state.source_sha256 == node.origin.sha256 && state.name == node.key.name,
            "Class-state source identity changed"
        );
        if state.diagnostic.is_none() {
            if node.access & 0x8000 != 0 {
                state.diagnostic = Some("Module descriptor is not an initialized class".into());
            } else {
                match hierarchy::initialization_dependencies(catalog, state.class_id) {
                    Ok(deps) => {
                        state.dependencies = deps;
                        provided.insert(state.class_id);
                    }
                    Err(error) => state.diagnostic = Some(format!("{error:#}")),
                }
            }
        }
    }
    // A valid declaration may depend on a class whose static-field plan failed.
    // Do not fabricate a descriptor that makes this dependency appear ready.
    loop {
        let invalid: Vec<_> = requests
            .iter()
            .filter(|r| {
                provided.contains(&r.class_id)
                    && r.dependencies.iter().any(|d| !provided.contains(d))
            })
            .map(|r| r.class_id)
            .collect();
        if invalid.is_empty() {
            break;
        }
        for id in invalid {
            provided.remove(&id);
            requests[id].diagnostic =
                Some("Initialization dependency has no valid source state plan".into());
        }
    }
    let states: Vec<_> = requests
        .iter()
        .filter(|r| provided.contains(&r.class_id))
        .collect();
    let mut bodies = AssemblyBodies::new(ASSEMBLY_BODY_BUDGET);
    let mut roots = String::from(
        ".data?\nALIGN 8\nPUBLIC boom_batch_class_roots\nboom_batch_class_roots LABEL QWORD\n",
    );
    let mut root_cells = 0;
    let mut class_units = BTreeMap::new();
    for state in &states {
        for field in state.fields.iter().filter(|f| f.reference) {
            writeln!(
                roots,
                "PUBLIC boom_s{}_{}\nboom_s{}_{} QWORD ?",
                state.class_id, field.index, state.class_id, field.index
            )?;
            root_cells += 1;
        }
        writeln!(
            roots,
            "PUBLIC boom_batch_class_failure_root{0}\nboom_batch_class_failure_root{0} QWORD ?",
            state.class_id
        )?;
        root_cells += 1;
    }
    writeln!(
        roots,
        ".const\nPUBLIC boom_batch_class_root_count\nboom_batch_class_root_count QWORD {root_cells}\nPUBLIC boom_batch_class_descriptors\nboom_batch_class_descriptors LABEL QWORD"
    )?;
    for id in 0..catalog.nodes.len() {
        writeln!(
            roots,
            " QWORD {}",
            if provided.contains(&id) {
                format!("OFFSET boom_class{id}")
            } else {
                "0".into()
            }
        )?;
    }
    bodies.push(&roots);
    for state in &states {
        let id = state.class_id;
        let has_work = !state.dependencies.is_empty()
            || state.initializer.is_some()
            || state.fields.iter().any(|f| f.constant.is_some());
        let initialize = if has_work {
            format!("OFFSET boom_batch_initialize_{id}")
        } else {
            "0".into()
        };
        let mut body = format!(
            ".data\nALIGN 8\nPUBLIC boom_class{id}\nboom_class{id} DWORD 0434C4153h,2,0,0\n QWORD {initialize}\n DWORD {id},0\n QWORD 0,0,0,OFFSET boom_batch_class_failure_root{id}\n.data?\nALIGN 8\n"
        );
        for field in state.fields.iter().filter(|f| !f.reference) {
            writeln!(
                body,
                "PUBLIC boom_s{id}_{0}\nboom_s{id}_{0} QWORD ?",
                field.index
            )?;
        }
        if has_work {
            writeln!(
                body,
                ".code\nboom_batch_initialize_{id} PROC FRAME\n sub rsp,72\n .allocstack 72\n .endprolog\n mov QWORD PTR [rsp+48],rcx\n mov QWORD PTR [rsp+56],rdx"
            )?;
            // ConstantValue fields are zero in preparation, then assigned in
            // declaration order before superclass/interface initialization.
            for field in state.fields.iter().filter(|f| f.constant.is_some()) {
                if let Some(cp) = field.string_constant {
                    writeln!(
                        body,
                        " mov rcx,QWORD PTR [rsp+48]\n lea rdx,[rsp+64]\n call boom_batch_literal_load_{id}_{cp}\n mov r10,QWORD PTR [rsp+48]\n cmp DWORD PTR [r10],0\n jne boom_batch_initialize_{id}_done"
                    )?;
                } else {
                    writeln!(body, " mov rax,0{:016X}h", field.initial_bits)?;
                }
                writeln!(body, " mov QWORD PTR [boom_s{id}_{}],rax", field.index)?;
            }
            for dependency in &state.dependencies {
                writeln!(
                    body,
                    " lea rcx,boom_class{dependency}\n mov rdx,QWORD PTR [rsp+48]\n call boom_class_ensure32\n test eax,eax\n jnz boom_batch_initialize_{id}_done"
                )?;
            }
            if let Some(initializer) = &state.initializer {
                writeln!(
                    body,
                    " mov rcx,QWORD PTR [rsp+48]\n mov rdx,QWORD PTR [rsp+56]\n call boom_m{}_body",
                    initializer.method
                )?;
            }
            if state.vm_post_initializer == Some("unsafe_constants") {
                writeln!(
                    body,
                    " mov rcx,QWORD PTR [rsp+48]\n cmp DWORD PTR [rcx],0\n jne boom_batch_initialize_{id}_done\n lea rdx,boom_java_unsafe_pool\n call boom_java_unsafe_constants"
                )?;
            }
            writeln!(
                body,
                "boom_batch_initialize_{id}_done:\n mov r10,QWORD PTR [rsp+48]\n mov eax,DWORD PTR [r10]\n add rsp,72\n ret\nboom_batch_initialize_{id} ENDP"
            )?;
        }
        class_units.insert(id, bodies.push(&body));
    }
    let directory = output.join("class-state");
    fs::create_dir_all(&directory)?;
    let index_path = directory.join("index.zip");
    let mut temp = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut zip = ZipWriter::new(temp.as_file_mut());
        let options = SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .compression_level(Some(1));
        zip.start_file("classes.jsonl", options)?;
        for state in &requests {
            serde_json::to_writer(
                &mut zip,
                &IndexedClass {
                    state,
                    assembly_unit: class_units.get(&state.class_id).copied(),
                },
            )?;
            zip.write_all(b"\n")?;
        }
        zip.finish()?;
    }
    temp.persist(&index_path).map_err(|e| e.error)?;
    let symbols = Symbols::new()?;
    let mut units = vec![];
    for (id, body) in bodies.parts.into_iter().enumerate() {
        units.push(write_unit(
            &symbols,
            &directory.join(format!("{id:04}.asm")),
            id,
            &body,
            assemble,
        )?);
    }
    Ok(Summary {
        abi: 1,
        class_capacity: catalog.nodes.len(),
        provided_classes: provided.len(),
        omitted_classes: requests
            .iter()
            .filter(|r| !provided.contains(&r.class_id))
            .map(|r| r.class_id)
            .collect(),
        static_fields: states.iter().map(|s| s.fields.len()).sum(),
        static_reference_fields: states
            .iter()
            .flat_map(|s| &s.fields)
            .filter(|f| f.reference)
            .count(),
        constant_values: states
            .iter()
            .flat_map(|s| &s.fields)
            .filter(|f| f.constant.is_some())
            .count(),
        string_constants: states
            .iter()
            .flat_map(|s| &s.fields)
            .filter(|f| f.string_constant.is_some())
            .count(),
        java_initializers: states.iter().filter(|s| s.initializer.is_some()).count(),
        emitted_java_initializers: states
            .iter()
            .filter(|s| s.initializer.as_ref().is_some_and(|i| i.assembly_emitted))
            .count(),
        initialization_dependencies: states.iter().map(|s| s.dependencies.len()).sum(),
        root_cells,
        index: Artifact {
            path: index_path.display().to_string(),
            digest: files::digest(&index_path)?,
        },
        units,
        descriptor_abi: 2,
        context_bytes: 32,
        initial_state: 0,
        initial_static_storage_zero: true,
        complete_original_class_initialization_verified: false,
        linked: false,
        automatic_gc: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn constants_preserve_raw_bits_and_java_narrowing() {
        assert_eq!(
            constant_value("B", &Constant::Int(128), 1).unwrap(),
            (0xffffff80, None)
        );
        assert_eq!(
            constant_value("S", &Constant::Int(65535), 1).unwrap(),
            (0xffffffff, None)
        );
        assert_eq!(
            constant_value("C", &Constant::Int(-1), 1).unwrap(),
            (65535, None)
        );
        assert_eq!(
            constant_value("Z", &Constant::Int(2), 1).unwrap(),
            (0, None)
        );
        assert_eq!(
            constant_value("F", &Constant::FloatBits(0x80000000), 1).unwrap(),
            (0x80000000, None)
        );
        assert_eq!(
            constant_value("D", &Constant::DoubleBits(0x7ff8000000000001), 1).unwrap(),
            (0x7ff8000000000001, None)
        );
        assert!(constant_value("I", &Constant::Long(1), 1).is_err());
        assert!(constant_value("Ljava/lang/Object;", &Constant::StringUtf16(vec![]), 1).is_err());
    }
}
