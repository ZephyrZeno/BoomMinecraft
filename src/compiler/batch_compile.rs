//! Persistent IR -> nominal operands -> existing MASM emitter, without JVM fallback.
//! Object code remains unlinked until runtime/layout/module contracts are satisfied.
use super::{
    batch_array_clone, batch_bitcasts,
    batch_catalog::{Catalog, Header, Layout},
    batch_class_bootstrap, batch_class_lookup, batch_class_state, batch_classes, batch_concat,
    batch_dispatch, batch_frames, batch_literals, batch_metadata, batch_properties,
    batch_runtime_resources, batch_string_intern, batch_system,
    batch_types::{Binding, Environment, Universe},
    batch_unsafe, batch_unsafe_fields, batch_unsafe_memory, batch_vm,
    classfile::ClassFile,
    numeric,
    translation_ir::{self, Store},
    translation_plan::Artifact,
};
use crate::{
    bytecode::ClassArchives,
    files,
    jdk_classes::{self, ClassInputs},
    lock::InputLock,
    parallel,
};
use anyhow::{Context, Result, ensure};
use regex::Regex;
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{BufWriter, Write},
    path::Path,
    sync::atomic::{AtomicUsize, Ordering},
    time::Instant,
};
use zip::{ZipWriter, write::SimpleFileOptions};

#[derive(Default, Debug, Serialize)]
pub struct Counts {
    pub declarations: usize,
    pub java_methods: usize,
    pub operand_verified: usize,
    pub assembly_emitted: usize,
    pub failed_methods: usize,
    pub instructions: usize,
    pub reference_maps: usize,
}
#[derive(Serialize)]
pub struct MethodResult {
    pub id: usize,
    pub name: String,
    pub descriptor: String,
    pub code_sha256: Option<String>,
    pub stage: String,
    pub operand_verified: bool,
    pub assembly_emitted: bool,
    pub assembly_unit: Option<usize>,
    pub diagnostic: Option<String>,
    pub references: Vec<numeric::ReferenceMap>,
    pub bindings: Vec<Binding>,
}
#[derive(Serialize)]
pub struct ClassResult {
    pub class_id: usize,
    pub source_sha256: String,
    pub name: String,
    pub methods: Vec<MethodResult>,
}
#[derive(Serialize)]
pub struct ShardResult {
    pub id: usize,
    pub zip: Artifact,
    pub counts: Counts,
    pub units: Vec<AssemblyUnit>,
}
#[derive(Serialize)]
pub struct AssemblyUnit {
    pub id: usize,
    pub body_bytes: usize,
    pub assembly: Artifact,
    pub object: Option<Artifact>,
    pub assembler_diagnostic: Option<String>,
    pub external_procedures: usize,
    pub external_data: usize,
    pub assembler_cache: Option<crate::assembly_cache::CacheRecord>,
}
#[derive(Serialize)]
pub struct Group {
    pub stage: String,
    pub reason: String,
    pub methods: usize,
    pub examples: Vec<String>,
}
#[derive(Serialize)]
pub struct Summary {
    pub schema: u32,
    pub mode: &'static str,
    pub input_fingerprint: String,
    pub ir_identity: String,
    pub compiler_sha256: String,
    pub workers: usize,
    pub elapsed_ms: u128,
    pub classes: usize,
    pub counts: Counts,
    pub candidate_layouts: usize,
    pub hierarchy_failures: usize,
    pub arrays: usize,
    pub assembled_shards: usize,
    pub assembler_failures: usize,
    pub assembly_units: usize,
    pub assembled_units: usize,
    pub assembly_body_budget_bytes: usize,
    pub layouts: Artifact,
    pub array_types: Artifact,
    pub numeric_kernel: Artifact,
    pub numeric_kernel_object: Option<Artifact>,
    pub numeric_kernel_assembler_diagnostic: Option<String>,
    pub numeric_kernel_assembler_cache: Option<crate::assembly_cache::CacheRecord>,
    pub string_literals: batch_literals::Summary,
    pub runtime_metadata: batch_metadata::Summary,
    pub class_state: batch_class_state::Summary,
    pub dispatch: batch_dispatch::Summary,
    pub array_clone: batch_array_clone::Summary,
    pub system_natives: batch_system::Summary,
    pub class_literals: batch_classes::Summary,
    pub string_intern: batch_string_intern::Summary,
    pub properties: batch_properties::Summary,
    pub string_concat: batch_concat::Summary,
    pub class_bootstrap: batch_class_bootstrap::Summary,
    pub unsafe_bootstrap: batch_unsafe::Summary,
    pub vm_registration: batch_vm::Summary,
    pub runtime_resources: batch_runtime_resources::Summary,
    pub bitcasts: batch_bitcasts::Summary,
    pub unsafe_fields: batch_unsafe_fields::Summary,
    pub unsafe_memory: batch_unsafe_memory::Summary,
    pub class_lookup: batch_class_lookup::Summary,
    pub frames: batch_frames::Summary,
    pub shards: Vec<ShardResult>,
    pub diagnostics: Vec<Group>,
    pub runtime_layout_abi: &'static str,
    pub runtime_abi_verified: bool,
    pub module_access_verified: bool,
    pub linked: bool,
    pub automatic_memory_reclamation: bool,
    pub game_started: bool,
    pub world_created: bool,
    pub full_game_ready: bool,
}
fn write_rows<T: Serialize>(path: &Path, rows: &[T]) -> Result<Artifact> {
    let temp = tempfile::NamedTempFile::new_in(path.parent().context("Missing output directory")?)?;
    {
        let mut writer = BufWriter::new(temp.as_file());
        for row in rows {
            serde_json::to_writer(&mut writer, row)?;
            writer.write_all(b"\n")?;
        }
        writer.flush()?;
    }
    temp.persist(path).map_err(|e| e.error)?;
    Ok(Artifact {
        path: path.display().to_string(),
        digest: files::digest(path)?,
    })
}
fn context32_initialization_calls(body: &str) -> String {
    body.replace("call boom_class_ensure\n", "call boom_class_ensure32\n")
}

pub(super) struct Symbols {
    references: Regex,
    definitions: Regex,
    procedures: Regex,
    calls: Regex,
}
impl Symbols {
    pub(super) fn new() -> Result<Self> {
        Ok(Self {
            references: Regex::new(r"\bboom_[A-Za-z0-9_]+\b")?,
            definitions: Regex::new(
                r"(?m)^\s*(boom_[A-Za-z0-9_]+)(?::|\s+(?:PROC|LABEL|QWORD|DWORD|WORD|BYTE)\b)",
            )?,
            procedures: Regex::new(r"(?m)^\s*(boom_[A-Za-z0-9_]+)\s+PROC\b")?,
            calls: Regex::new(r"(?m)^\s*(?:call|jmp)\s+(boom_[A-Za-z0-9_]+)\b")?,
        })
    }
    pub(super) fn module(&self, body: &str) -> (String, usize, usize) {
        let definitions = self
            .definitions
            .captures_iter(body)
            .map(|c| c[1].to_string())
            .collect::<BTreeSet<_>>();
        let procedures = self
            .procedures
            .captures_iter(body)
            .map(|c| c[1].to_string())
            .collect::<BTreeSet<_>>();
        let calls = self
            .calls
            .captures_iter(body)
            .map(|c| c[1].to_string())
            .collect::<BTreeSet<_>>();
        let references = self
            .references
            .find_iter(body)
            .map(|m| m.as_str().to_string())
            .filter(|s| !definitions.contains(s))
            .collect::<BTreeSet<_>>();
        let mut module = String::from(
            "; Self-authored candidate MASM; unresolved contracts are externals, not implementations.\noption casemap:none\n",
        );
        let mut external_procedures = 0;
        let mut external_data = 0;
        for symbol in references {
            if calls.contains(&symbol) {
                module.push_str(&format!("EXTERN {symbol}:PROC\n"));
                external_procedures += 1;
            } else {
                module.push_str(&format!("EXTERN {symbol}:BYTE\n"));
                external_data += 1;
            }
        }
        for symbol in procedures {
            module.push_str(&format!("PUBLIC {symbol}\n"));
        }
        module.push_str(".code\n");
        module.push_str(body);
        module.push_str("\nEND\n");
        (module, external_procedures, external_data)
    }
}
struct Work<'a> {
    inputs: &'a InputLock,
    base: &'a ClassInputs,
    jdk_path: &'a Path,
    store: &'a Store,
    catalog: &'a Catalog,
    universe: &'a Universe,
    layouts: &'a [Layout],
    output: &'a Path,
    assemble: bool,
}
struct Completed {
    shard: ShardResult,
    groups: BTreeMap<(String, String), Group>,
    literals: Vec<batch_literals::Request>,
    class_states: Vec<batch_class_state::ClassState>,
    contracts: batch_dispatch::Requests,
    frames: Vec<batch_frames::FrameMethod>,
}
pub(super) const ASSEMBLY_BODY_BUDGET: usize = 8 * 1024 * 1024;
/// Retain whole generated functions while bounding assembler symbol-table work.
/// Relocations cross units through the same source-bound method symbols.
pub(super) struct AssemblyBodies {
    budget: usize,
    pub(super) parts: Vec<String>,
}
impl AssemblyBodies {
    pub(super) fn new(budget: usize) -> Self {
        Self {
            budget,
            parts: vec![],
        }
    }
    pub(super) fn push(&mut self, body: &str) -> usize {
        if self.parts.last().is_none_or(|part| {
            !part.is_empty()
                && part.len().saturating_add(body.len()).saturating_add(1) > self.budget
        }) {
            self.parts.push(String::new());
        }
        let id = self.parts.len() - 1;
        self.parts[id].push_str(body);
        self.parts[id].push('\n');
        id
    }
}
fn compile_shard(
    work: &Work<'_>,
    id: usize,
    archives: &ClassArchives,
    symbols: &Symbols,
) -> Result<Completed> {
    let classes = work.store.read_shard::<translation_ir::Class>(id)?;
    let directory = work.output.join("shards");
    let zip_path = directory.join(format!("{id:05}.zip"));
    let mut temporary = tempfile::NamedTempFile::new_in(&directory)?;
    let mut counts = Counts::default();
    let mut groups = BTreeMap::<(String, String), Group>::new();
    let mut assembly = AssemblyBodies::new(ASSEMBLY_BODY_BUDGET);
    let mut literals = vec![];
    let mut class_states = vec![];
    let mut contracts = batch_dispatch::Requests::default();
    let mut frames = vec![];
    {
        let mut zip = ZipWriter::new(temporary.as_file_mut());
        let options = SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .compression_level(Some(1));
        for class in classes {
            let node = work
                .catalog
                .nodes
                .get(class.class_id)
                .context("Invalid IR class identity")?;
            ensure!(
                node.origin == class.origin,
                "IR class source differs from nominal catalog"
            );
            let bytes = if jdk_classes::is_system(&class.origin) {
                let (bytes, origin) = work
                    .base
                    .read_class(work.jdk_path, &class.origin.binary_name)?;
                ensure!(origin == class.origin, "IR JDK source changed");
                bytes
            } else {
                archives.read(
                    &work.inputs.file(&class.origin.source_id)?.path,
                    &class.origin,
                )?
            };
            let source = ClassFile::parse(&bytes)?;
            ensure!(
                source.name == class.name
                    && source.access == class.access
                    && source.super_name == class.superclass
                    && source.interface_names == class.interfaces
                    && source.nest_host == class.nest_host
                    && source.nest_members == class.nest_members
                    && source.field_info.len() == class.fields.len()
                    && source
                        .field_info
                        .iter()
                        .zip(&class.fields)
                        .all(|(a, b)| a.name == b.name
                            && a.descriptor == b.descriptor
                            && a.access == b.access
                            && a.constant_value == b.constant_value)
                    && source.methods.len() == class.methods.len()
                    && source
                        .methods
                        .iter()
                        .zip(&class.methods)
                        .all(|(a, b)| a.name == b.name
                            && a.descriptor == b.descriptor
                            && a.access == b.access
                            && a.code
                                .as_ref()
                                .map(|code| files::digest_bytes(&code.bytes).sha256)
                                == b.code_sha256),
                "IR/source class differs"
            );
            for (index, value) in &class.constants {
                ensure!(
                    super::symbolic::constant(&source, *index)? == *value,
                    "IR symbolic constant differs from original source"
                );
                if let super::symbolic::Constant::StringUtf16(utf16) = value {
                    literals.push(batch_literals::Request {
                        class_id: class.class_id,
                        constant: *index,
                        utf16: utf16.clone(),
                    });
                }
            }
            let mut methods = vec![];
            for (index, method) in class.methods.iter().enumerate() {
                let mut row = MethodResult {
                    id: method.id,
                    name: method.name.clone(),
                    descriptor: method.descriptor.clone(),
                    code_sha256: method.code_sha256.clone(),
                    stage: "declaration".into(),
                    operand_verified: false,
                    assembly_emitted: false,
                    assembly_unit: None,
                    diagnostic: None,
                    references: vec![],
                    bindings: vec![],
                };
                if method.code_sha256.is_none() {
                    counts.declarations += 1;
                    methods.push(row);
                    continue;
                }
                counts.java_methods += 1;
                let env = Environment::new(
                    work.catalog,
                    work.universe,
                    work.layouts,
                    class.class_id,
                    index,
                );
                row.stage = "operand_verification".into();
                let result = (|| -> Result<()> {
                    ensure!(
                        method.id == node.method_ids[index],
                        "IR method identity differs from nominal catalog"
                    );
                    let prepared = numeric::prepare_symbolic_method(&source, index, &class, &env)?;
                    row.operand_verified = true;
                    counts.operand_verified += 1;
                    counts.instructions += prepared.instruction_count();
                    row.references = prepared.reference_maps();
                    counts.reference_maps += row.references.len();
                    row.stage = "assembly_generation".into();
                    let (body, _) = numeric::emit_prepared_linked_function(
                        &source, index, method.id, &env, &prepared,
                    )?;
                    // This environment always uses Context32 and descriptor ABI2.
                    // The legacy Context16 state machine must never receive it.
                    let body = context32_initialization_calls(&body);
                    row.assembly_unit = Some(assembly.push(&body));
                    row.assembly_emitted = true;
                    counts.assembly_emitted += 1;
                    row.stage = "assembly_emitted_unlinked".into();
                    Ok(())
                })();
                row.bindings = env.bindings.into_inner();
                if row.assembly_emitted {
                    contracts.record(
                        row.id,
                        &class.origin.sha256,
                        &row.bindings,
                        &class.constants,
                    )?;
                }
                if let Err(error) = result {
                    counts.failed_methods += 1;
                    let reason = format!("{error:#}");
                    row.diagnostic = Some(reason.clone());
                    let key = (row.stage.clone(), reason.clone());
                    let group = groups.entry(key).or_insert_with(|| Group {
                        stage: row.stage.clone(),
                        reason,
                        methods: 0,
                        examples: vec![],
                    });
                    group.methods += 1;
                    if group.examples.len() < 6 {
                        group.examples.push(format!(
                            "{}.{}{}",
                            class.name, method.name, method.descriptor
                        ));
                    }
                }
                methods.push(row);
            }
            frames.extend(batch_frames::capture(
                work.catalog,
                &source,
                class.class_id,
                &class.origin,
                &methods,
            ));
            class_states.push(batch_class_state::ClassState::from_source(&class, &methods));
            zip.start_file(format!("classes/{:06}.json", class.class_id), options)?;
            serde_json::to_writer(
                &mut zip,
                &ClassResult {
                    class_id: class.class_id,
                    source_sha256: class.origin.sha256,
                    name: class.name,
                    methods,
                },
            )?;
        }
        zip.finish()?;
    }
    temporary.persist(&zip_path).map_err(|e| e.error)?;
    let mut result = ShardResult {
        id,
        zip: Artifact {
            path: zip_path.display().to_string(),
            digest: files::digest(&zip_path)?,
        },
        counts,
        units: vec![],
    };
    for (unit_id, body) in assembly.parts.into_iter().enumerate() {
        let path = directory.join(format!("{id:05}-{unit_id:04}.asm"));
        result
            .units
            .push(write_unit(symbols, &path, unit_id, &body, work.assemble)?);
    }
    Ok(Completed {
        shard: result,
        groups,
        literals,
        class_states,
        contracts,
        frames,
    })
}

pub(super) fn write_unit(
    symbols: &Symbols,
    path: &Path,
    id: usize,
    body: &str,
    assemble: bool,
) -> Result<AssemblyUnit> {
    let (module, external_procedures, external_data) = symbols.module(body);
    files::write_atomic(path, module.as_bytes())?;
    let mut unit = AssemblyUnit {
        id,
        body_bytes: body.len(),
        assembly: Artifact {
            path: path.display().to_string(),
            digest: files::digest(path)?,
        },
        object: None,
        assembler_diagnostic: None,
        external_procedures,
        external_data,
        assembler_cache: None,
    };
    if assemble {
        let object = path.with_extension("obj");
        let run = crate::assembly_cache::assemble(
            path,
            &object,
            &path.with_extension("assembler.log"),
            Some(Path::new(".boom/assembly-object-cache/v1")),
        )?;
        unit.assembler_cache = Some(run.cache);
        if run.success {
            unit.object = Some(Artifact {
                path: object.display().to_string(),
                digest: files::digest(&object)?,
            });
        } else {
            unit.assembler_diagnostic = Some(format!(
                "Assembler failed: {}",
                path.with_extension("assembler.log").display()
            ));
        }
    }
    Ok(unit)
}

pub fn compile(
    inputs: &InputLock,
    jdk_path: &Path,
    ir_path: &Path,
    output: &Path,
    workers: usize,
    assemble: bool,
) -> Result<Summary> {
    let started = Instant::now();
    ensure!(
        (1..=64).contains(&workers),
        "Batch worker budget must be 1..=64"
    );
    inputs.verify()?;
    let base = ClassInputs::read(jdk_path, inputs)?;
    let store = Store::open(ir_path, &inputs.fingerprint)?;
    ensure!(
        store.jdk_fingerprint == base.fingerprint(),
        "IR JDK image differs from locked inputs"
    );
    eprintln!(
        "Reading {} nominal class headers from source-bound IR",
        store.classes
    );
    let work = parallel::ordered_map(&store.shards, workers, |index, _| {
        store.read_shard::<Header>(index)
    })?;
    let headers = work
        .results
        .into_iter()
        .collect::<Result<Vec<_>>>()?
        .into_iter()
        .flatten()
        .collect();
    let catalog = Catalog::with_packages(headers, base.packages()?)?;
    // Validate new VM contracts before paying for whole-input Java codegen.
    batch_class_bootstrap::source_methods(&catalog)?;
    batch_unsafe::source_methods(&catalog)?;
    batch_vm::source_methods(&catalog)?;
    batch_runtime_resources::source_methods(&catalog)?;
    batch_bitcasts::source_methods(&catalog)?;
    batch_unsafe_fields::source_methods(&catalog)?;
    batch_unsafe_memory::source_methods(&catalog)?;
    batch_class_lookup::source_methods(&catalog)?;
    batch_frames::source_methods(&catalog)?;
    ensure!(
        catalog.methods == store.methods,
        "Nominal method coverage differs from IR"
    );
    let universe = Universe::new(&catalog)?;
    let layouts = catalog.layouts();
    fs::create_dir_all(output.join("shards"))?;
    let output = files::absolute(output)?;
    let layout_artifact = write_rows(&output.join("layouts.jsonl"), &layouts)?;
    let array_types = write_rows(&output.join("arrays.jsonl"), &universe.arrays)?;
    let symbols = Symbols::new()?;
    let (kernel, _, _) = symbols.module(&numeric::shared_numeric_module());
    let kernel_path = output.join("numeric-kernel.asm");
    files::write_atomic(&kernel_path, kernel.as_bytes())?;
    let numeric_kernel = Artifact {
        path: kernel_path.display().to_string(),
        digest: files::digest(&kernel_path)?,
    };
    let mut numeric_kernel_object = None;
    let mut numeric_kernel_assembler_diagnostic = None;
    let mut numeric_kernel_assembler_cache = None;
    if assemble {
        let object = output.join("numeric-kernel.obj");
        let run = crate::assembly_cache::assemble(
            &kernel_path,
            &object,
            &output.join("numeric-kernel-assembler.log"),
            Some(Path::new(".boom/assembly-object-cache/v1")),
        )?;
        numeric_kernel_assembler_cache = Some(run.cache);
        if run.success {
            numeric_kernel_object = Some(Artifact {
                path: object.display().to_string(),
                digest: files::digest(&object)?,
            });
        } else {
            numeric_kernel_assembler_diagnostic =
                Some("Shared numeric kernel assembler failed".into());
        }
    }
    let work = Work {
        inputs,
        base: &base,
        jdk_path,
        store: &store,
        catalog: &catalog,
        universe: &universe,
        layouts: &layouts,
        output: &output,
        assemble,
    };
    let next = AtomicUsize::new(0);
    let done = AtomicUsize::new(0);
    eprintln!(
        "Generating typed MASM candidates for {} methods; native/runtime contracts remain unlinked",
        store.methods
    );
    let mut completed = std::thread::scope(|scope| -> Result<Vec<Completed>> {
        let mut handles = vec![];
        for _ in 0..workers.min(store.shards.len().max(1)) {
            let work = &work;
            let next = &next;
            let done = &done;
            handles.push(scope.spawn(move || -> Result<Vec<Completed>> {
                let archives = ClassArchives::default();
                let symbols = Symbols::new()?;
                let mut rows = vec![];
                loop {
                    let id = next.fetch_add(1, Ordering::Relaxed);
                    if id >= work.store.shards.len() {
                        break;
                    }
                    rows.push(compile_shard(work, id, &archives, &symbols)?);
                    let count = done.fetch_add(1, Ordering::Relaxed) + 1;
                    if count.is_multiple_of(16) || count == work.store.shards.len() {
                        eprintln!(
                            "Typed/codegen shards complete: {count}/{}",
                            work.store.shards.len()
                        );
                    }
                }
                Ok(rows)
            }));
        }
        let mut rows = vec![];
        for handle in handles {
            rows.extend(
                handle
                    .join()
                    .map_err(|_| anyhow::anyhow!("Batch codegen worker panicked"))??,
            );
        }
        Ok(rows)
    })?;
    completed.sort_by_key(|r| r.shard.id);
    let requests = completed
        .iter_mut()
        .flat_map(|r| std::mem::take(&mut r.literals))
        .collect();
    let string_literals =
        batch_literals::generate(&catalog, &layouts, &universe, requests, &output, assemble)?;
    let runtime_metadata =
        batch_metadata::generate(&catalog, &layouts, &universe, &output, assemble)?;
    let frame_methods = completed
        .iter_mut()
        .flat_map(|r| std::mem::take(&mut r.frames))
        .collect();
    let (frames, frame_natives) = batch_frames::generate(
        &catalog,
        &runtime_metadata,
        frame_methods,
        inputs,
        jdk_path,
        &output,
        assemble,
    )?;
    let class_states = completed
        .iter_mut()
        .flat_map(|r| std::mem::take(&mut r.class_states))
        .collect();
    let class_state = batch_class_state::generate(&catalog, class_states, &output, assemble)?;
    let mut contracts = batch_dispatch::Requests::default();
    for result in &mut completed {
        contracts.merge(std::mem::take(&mut result.contracts))?;
    }
    let array_clone = batch_array_clone::generate(
        &catalog,
        &universe,
        std::mem::take(&mut contracts.array_clones),
        &output,
        assemble,
    )?;
    let (system_natives, mut provided_natives) =
        batch_system::generate(&catalog, &output, assemble)?;
    provided_natives.extend(frame_natives);
    let (class_literals, class_natives) = batch_classes::generate(
        &catalog,
        &layouts,
        &runtime_metadata,
        &string_literals,
        std::mem::take(&mut contracts.class_literals),
        &output,
        assemble,
    )?;
    provided_natives.extend(class_natives);
    let (class_bootstrap, bootstrap_natives) =
        batch_class_bootstrap::generate(&catalog, &runtime_metadata, &output, assemble)?;
    provided_natives.extend(bootstrap_natives);
    let (unsafe_bootstrap, unsafe_natives) =
        batch_unsafe::generate(&catalog, &runtime_metadata, &class_state, &output, assemble)?;
    provided_natives.extend(unsafe_natives);
    let (vm_registration, vm_natives) = batch_vm::generate(&catalog, &output, assemble)?;
    provided_natives.extend(vm_natives);
    let (runtime_resources, resource_natives) =
        batch_runtime_resources::generate(&catalog, &output, assemble)?;
    provided_natives.extend(resource_natives);
    let (bitcasts, bitcast_natives) = batch_bitcasts::generate(&catalog, &output, assemble)?;
    let (unsafe_fields, unsafe_field_natives) = batch_unsafe_fields::generate(
        &catalog,
        &universe,
        &runtime_metadata,
        &string_literals.source_layout,
        &output,
        assemble,
    )?;
    provided_natives.extend(bitcast_natives);
    provided_natives.extend(unsafe_field_natives);
    let (unsafe_memory, memory_natives) =
        batch_unsafe_memory::generate(&catalog, &output, assemble)?;
    provided_natives.extend(memory_natives);
    let (class_lookup, lookup_natives) = batch_class_lookup::generate(
        &catalog,
        &runtime_metadata,
        &class_state,
        &string_literals,
        &output,
        assemble,
    )?;
    provided_natives.extend(lookup_natives);
    let (string_intern, intern_natives) =
        batch_string_intern::generate(&catalog, &string_literals.source_layout, &output, assemble)?;
    provided_natives.extend(intern_natives);
    let (properties, property_natives) = batch_properties::generate(
        inputs,
        &catalog,
        &string_literals.source_layout,
        &runtime_metadata,
        &class_state,
        &output,
        assemble,
    )?;
    provided_natives.extend(property_natives);
    contracts.resolve_native_methods(&provided_natives);
    let (string_concat, rejected_concat) = batch_concat::generate(
        &catalog,
        &string_literals.source_layout,
        std::mem::take(&mut contracts.concat_sites),
        &output,
        assemble,
    )?;
    contracts.reject_concat(rejected_concat)?;
    let dispatch = batch_dispatch::generate(
        &catalog, &universe, &layouts, contracts, &output, assemble, workers,
    )?;
    let mut counts = Counts::default();
    let mut groups = BTreeMap::<(String, String), Group>::new();
    for result in &completed {
        let c = &result.shard.counts;
        counts.declarations += c.declarations;
        counts.java_methods += c.java_methods;
        counts.operand_verified += c.operand_verified;
        counts.assembly_emitted += c.assembly_emitted;
        counts.failed_methods += c.failed_methods;
        counts.instructions += c.instructions;
        counts.reference_maps += c.reference_maps;
        for (key, value) in &result.groups {
            let group = groups.entry(key.clone()).or_insert_with(|| Group {
                stage: value.stage.clone(),
                reason: value.reason.clone(),
                methods: 0,
                examples: vec![],
            });
            group.methods += value.methods;
            for example in &value.examples {
                if group.examples.len() < 6 {
                    group.examples.push(example.clone());
                }
            }
        }
    }
    ensure!(
        counts.java_methods + counts.declarations == store.methods,
        "Batch method coverage differs from IR"
    );
    let summary = Summary {
        schema: 23,
        mode: "typed_assembly_candidates_unlinked",
        input_fingerprint: inputs.fingerprint.clone(),
        ir_identity: store.identity,
        compiler_sha256: files::digest(&std::env::current_exe()?)?.sha256,
        workers,
        elapsed_ms: started.elapsed().as_millis(),
        classes: store.classes,
        counts,
        candidate_layouts: layouts.iter().filter(|l| l.candidate.is_some()).count(),
        hierarchy_failures: catalog
            .nodes
            .iter()
            .filter(|n| n.hierarchy_error.is_some())
            .count(),
        arrays: universe.arrays.len(),
        assembled_shards: completed
            .iter()
            .filter(|r| {
                !r.shard.units.is_empty() && r.shard.units.iter().all(|unit| unit.object.is_some())
            })
            .count(),
        assembler_failures: completed
            .iter()
            .filter(|r| {
                r.shard
                    .units
                    .iter()
                    .any(|unit| unit.assembler_diagnostic.is_some())
            })
            .count(),
        assembly_units: completed.iter().map(|r| r.shard.units.len()).sum(),
        assembled_units: completed
            .iter()
            .flat_map(|r| &r.shard.units)
            .filter(|unit| unit.object.is_some())
            .count(),
        assembly_body_budget_bytes: ASSEMBLY_BODY_BUDGET,
        layouts: layout_artifact,
        array_types,
        numeric_kernel,
        numeric_kernel_object,
        numeric_kernel_assembler_diagnostic,
        numeric_kernel_assembler_cache,
        string_literals,
        runtime_metadata,
        class_state,
        dispatch,
        array_clone,
        system_natives,
        class_literals,
        string_intern,
        properties,
        string_concat,
        class_bootstrap,
        unsafe_bootstrap,
        vm_registration,
        runtime_resources,
        bitcasts,
        unsafe_fields,
        unsafe_memory,
        class_lookup,
        frames,
        shards: completed.into_iter().map(|r| r.shard).collect(),
        diagnostics: groups.into_values().collect(),
        runtime_layout_abi: "batch-original-java-layout-candidate-v1",
        runtime_abi_verified: false,
        module_access_verified: false,
        linked: false,
        automatic_memory_reclamation: false,
        game_started: false,
        world_created: false,
        full_game_ready: false,
    };
    files::write_atomic(
        &output.join("summary.json"),
        &serde_json::to_vec_pretty(&summary)?,
    )?;
    Ok(summary)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn initialization_lowering_preserves_already_normal_monitor_calls() {
        let normal = super::super::monitors::wrapper(7, 8, Some(8), true, true);
        assert_eq!(context32_initialization_calls(&normal), normal);
        let legacy = super::super::monitors::wrapper(7, 8, Some(8), true, false);
        let lowered = context32_initialization_calls(&legacy);
        assert!(lowered.contains("call boom_class_ensure32\n"));
        assert!(!lowered.contains("boom_class_ensure3232"));
    }

    #[test]
    fn assembly_units_preserve_whole_methods_and_cross_unit_relocations() {
        let first = "boom_m0 PROC\n call boom_m1\n ret\nboom_m0 ENDP\nboom_m0_body PROC\n ret\nboom_m0_body ENDP\n";
        let second =
            "boom_m1 PROC\n ret\nboom_m1 ENDP\nboom_m1_body PROC\n ret\nboom_m1_body ENDP\n";
        let mut bodies = AssemblyBodies::new(first.len() + 1);
        assert_eq!(bodies.push(first), 0);
        assert_eq!(bodies.push(second), 1);
        assert_eq!(bodies.parts.concat(), format!("{first}\n{second}\n"));
        let symbols = Symbols::new().unwrap();
        let (a, _, _) = symbols.module(&bodies.parts[0]);
        let (b, _, _) = symbols.module(&bodies.parts[1]);
        assert!(a.contains("EXTERN boom_m1:PROC"));
        assert!(!a.contains("PUBLIC boom_m1\n"));
        assert!(b.contains("PUBLIC boom_m1\n"));
        assert!(!b.contains("EXTERN boom_m1:"));
    }
    #[test]
    fn one_oversized_method_stays_atomic_and_empty_shards_have_no_units() {
        let mut bodies = AssemblyBodies::new(3);
        assert!(bodies.parts.is_empty());
        assert_eq!(bodies.push("whole function"), 0);
        assert_eq!(bodies.push("next function"), 1);
        assert_eq!(bodies.parts, vec!["whole function\n", "next function\n"]);
    }
    #[test]
    fn external_contracts_are_declarations_and_local_labels_are_not_external() {
        let symbols = Symbols::new().unwrap();
        let (module,procedures,data)=symbols.module("boom_m0 PROC\n call boom_native\n lea rax,boom_global\n jmp boom_m0_done\nboom_m0_done:\n ret\nboom_m0 ENDP\n");
        assert_eq!((procedures, data), (1, 1));
        assert!(
            module.contains("EXTERN boom_native:PROC")
                && module.contains("EXTERN boom_global:BYTE")
        );
        assert!(!module.contains("EXTERN boom_m0_done"));
        assert!(!module.contains("boom_native PROC"));
    }
    #[test]
    fn persistent_ir_and_original_frontend_emit_identical_scalar_and_array_functions() {
        for (descriptor, code) in [
            (6, &[0x1a, 0x04, 0x60, 0xac][..]),
            (6, &[0x1a, 0x99, 0, 5, 0x04, 0xac, 0x03, 0xac][..]),
            (24, &[0x05, 0xbc, 0x0a, 0xbe, 0xac][..]),
            (24, &[0x0c, 0x8b, 0xac][..]),
            (24, &[0x0f, 0x8e, 0xac][..]),
        ] {
            let (source, unit, catalog, universe, layouts) = fixture(descriptor, code);
            let env = Environment::new(&catalog, &universe, &layouts, 1, 0);
            let prepared = numeric::prepare_symbolic_method(&source, 0, &unit, &env).unwrap();
            let actual =
                numeric::emit_prepared_linked_function(&source, 0, 0, &env, &prepared).unwrap();
            let expected = numeric::emit_linked_function(&source, 0, 0, &env).unwrap();
            assert_eq!(actual, expected);
        }
    }
    fn fixture(
        descriptor: u16,
        code: &[u8],
    ) -> (
        ClassFile,
        translation_ir::Class,
        Catalog,
        Universe,
        Vec<Layout>,
    ) {
        use super::super::symbolic;
        let bytes = symbolic::fixture(&[(5, descriptor, code)]);
        let source = ClassFile::parse(&bytes).unwrap();
        let mut decoder = symbolic::Decoder::new(&source);
        let body = decoder.method(&source.methods[0]).unwrap();
        let origin = crate::bytecode::ClassOrigin {
            loader: "vanilla-application".into(),
            binary_name: "p.IR".into(),
            source_id: "fixture".into(),
            jar_entry: "p/IR.class".into(),
            java_class_major: 65,
            sha256: files::digest_bytes(&bytes).sha256,
            generated: None,
        };
        let method = &source.methods[0];
        let unit = translation_ir::Class {
            schema: 1,
            class_id: 1,
            origin,
            name: source.name.clone(),
            access: source.access,
            superclass: source.super_name.clone(),
            interfaces: vec![],
            fields: vec![],
            nest_host: None,
            nest_members: None,
            record_components: None,
            source_file: None,
            constants: decoder.constants,
            methods: vec![translation_ir::Method {
                id: 0,
                name: method.name.clone(),
                descriptor: method.descriptor.clone(),
                access: method.access,
                signature: Some(symbolic::MethodType::parse(&method.descriptor).unwrap()),
                code_sha256: Some(files::digest_bytes(&method.code.as_ref().unwrap().bytes).sha256),
                body_kind: "java".into(),
                body: Some(body),
                line_numbers: vec![],
                diagnostic: None,
            }],
            diagnostic: None,
            type_layout_and_link_verified: false,
            assembly_emitted: false,
        };
        let mut root = serde_json::to_value(&unit).unwrap();
        root["class_id"] = serde_json::json!(0);
        root["name"] = serde_json::json!("java/lang/Object");
        root["superclass"] = serde_json::json!("");
        root["methods"] = serde_json::json!([]);
        root["constants"] = serde_json::json!({});
        root["origin"]["loader"] = serde_json::json!("bootstrap");
        root["origin"]["binary_name"] = serde_json::json!("java.lang.Object");
        let catalog = Catalog::new(vec![
            serde_json::from_value(root).unwrap(),
            serde_json::from_value(serde_json::to_value(&unit).unwrap()).unwrap(),
        ])
        .unwrap();
        let universe = Universe::new(&catalog).unwrap();
        let layouts = catalog.layouts();
        (source, unit, catalog, universe, layouts)
    }
    #[test]
    fn primitive_aaload_is_rejected_and_float_remainder_uses_assembly_kernel() {
        let (source, unit, catalog, universe, layouts) =
            fixture(24, &[0x04, 0xbc, 0x0a, 0x03, 0x32, 0xac]);
        let env = Environment::new(&catalog, &universe, &layouts, 1, 0);
        assert!(numeric::prepare_symbolic_method(&source, 0, &unit, &env).is_err());
        let (source, unit, catalog, universe, layouts) =
            fixture(24, &[0x0d, 0x0c, 0x72, 0x8b, 0xac]);
        let env = Environment::new(&catalog, &universe, &layouts, 1, 0);
        let prepared = numeric::prepare_symbolic_method(&source, 0, &unit, &env).unwrap();
        let (assembly, _) =
            numeric::emit_prepared_linked_function(&source, 0, 0, &env, &prepared).unwrap();
        assert!(assembly.contains("call boom_frem32"));
    }
}
