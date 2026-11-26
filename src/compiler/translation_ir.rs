//! Parallel, source-checked symbolic IR extraction from an existing whole-input plan.
//! Successful extraction is never a claim of type verification or executable code.
use super::{
    classfile::{ClassFile, LineNumber},
    symbolic,
    translation_plan::{Artifact, ClassTask, Symbol},
};
use crate::{
    bytecode::{ClassArchives, ClassOrigin},
    files,
    jdk_classes::{self, ClassInputs},
    lock::InputLock,
};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs::{self, File},
    io::{BufRead, BufReader, Read, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicUsize, Ordering},
    time::Instant,
};
use zip::{ZipWriter, write::SimpleFileOptions};

const CLASSES_PER_SHARD: usize = 256;
#[derive(Deserialize)]
struct InputPlan {
    schema: u32,
    mode: String,
    input_fingerprint: String,
    jdk_fingerprint: String,
    planner_fingerprint: String,
    classes: usize,
    methods: usize,
    artifacts: BTreeMap<String, Artifact>,
}
#[derive(Debug, Deserialize)]
struct MethodInput {
    id: usize,
    class_id: usize,
    symbol: Symbol,
    class_sha256: String,
    access: u16,
    code_sha256: Option<String>,
}
struct InputClass {
    class: ClassTask,
    methods: Vec<MethodInput>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Field {
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub constant_value: Option<u16>,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Method {
    pub id: usize,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub signature: Option<symbolic::MethodType>,
    pub code_sha256: Option<String>,
    pub body_kind: String,
    pub body: Option<symbolic::Body>,
    pub line_numbers: Vec<LineNumber>,
    pub diagnostic: Option<String>,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Class {
    pub schema: u32,
    pub class_id: usize,
    pub origin: ClassOrigin,
    pub name: String,
    pub access: u16,
    pub superclass: String,
    pub interfaces: Vec<String>,
    pub fields: Vec<Field>,
    pub nest_host: Option<String>,
    pub nest_members: Option<Vec<String>>,
    pub record_components: Option<Vec<(String, String)>>,
    pub source_file: Option<String>,
    pub constants: BTreeMap<u16, symbolic::Constant>,
    pub methods: Vec<Method>,
    pub diagnostic: Option<String>,
    pub type_layout_and_link_verified: bool,
    pub assembly_emitted: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Counts {
    pub methods: usize,
    pub java_methods: usize,
    pub symbolic_java_methods: usize,
    pub native_declarations: usize,
    pub abstract_declarations: usize,
    pub failed_methods: usize,
    pub legacy_subroutine_methods: usize,
    pub instructions: usize,
    pub blocks: usize,
    pub constants: usize,
}
impl Counts {
    fn empty() -> Self {
        Self {
            methods: 0,
            java_methods: 0,
            symbolic_java_methods: 0,
            native_declarations: 0,
            abstract_declarations: 0,
            failed_methods: 0,
            legacy_subroutine_methods: 0,
            instructions: 0,
            blocks: 0,
            constants: 0,
        }
    }
    fn add(&mut self, other: &Self) {
        self.methods += other.methods;
        self.java_methods += other.java_methods;
        self.symbolic_java_methods += other.symbolic_java_methods;
        self.native_declarations += other.native_declarations;
        self.abstract_declarations += other.abstract_declarations;
        self.failed_methods += other.failed_methods;
        self.legacy_subroutine_methods += other.legacy_subroutine_methods;
        self.instructions += other.instructions;
        self.blocks += other.blocks;
        self.constants += other.constants;
    }
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Entry {
    pub class_id: usize,
    pub class_sha256: String,
    pub path: String,
    pub digest: files::FileDigest,
    pub counts: Counts,
    pub class_diagnostic: Option<String>,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Shard {
    pub id: usize,
    pub cache_key: String,
    pub zip: Artifact,
    pub entries: Vec<Entry>,
}
#[derive(Debug, Serialize)]
pub struct Summary {
    pub schema: u32,
    pub mode: &'static str,
    pub input_fingerprint: String,
    pub jdk_fingerprint: String,
    pub source_plan_fingerprint: String,
    pub compiler_sha256: String,
    pub identity: String,
    pub workers: usize,
    pub elapsed_ms: u128,
    pub classes: usize,
    pub counts: Counts,
    pub class_failures: usize,
    pub shards: usize,
    pub reused_shards: usize,
    pub index: Artifact,
    pub type_layout_and_link_verified: bool,
    pub assembly_emitted_methods: usize,
    pub game_started: bool,
    pub world_created: bool,
    pub full_game_ready: bool,
}

/// Immutable reader for source-bound IR artifacts. Payloads are checked on each
/// read; a previous verifier report is never used as an execution permission.
pub struct Store {
    pub root: PathBuf,
    pub identity: String,
    pub input_fingerprint: String,
    pub jdk_fingerprint: String,
    pub classes: usize,
    pub methods: usize,
    pub shards: Vec<Shard>,
}
impl Store {
    pub fn open(root: &Path, expected_input: &str) -> Result<Self> {
        #[derive(Deserialize)]
        struct Index {
            schema: u32,
            mode: String,
            identity: String,
            input_fingerprint: String,
            jdk_fingerprint: String,
            classes: usize,
            counts: Counts,
            index: Artifact,
        }
        let root = files::absolute(root)?;
        let summary: Index = serde_json::from_slice(&fs::read(root.join("summary.json"))?)?;
        ensure!(
            summary.schema == symbolic::SCHEMA && summary.mode == "symbolic_ir_only",
            "Unsupported symbolic IR store"
        );
        ensure!(
            summary.input_fingerprint == expected_input,
            "IR store belongs to different locked inputs"
        );
        ensure!(
            summary.classes <= 100_000 && summary.counts.methods <= 1_000_000,
            "IR store budget exceeded"
        );
        let index = root.join("shards.jsonl");
        ensure!(
            files::digest(&index)? == summary.index.digest,
            "IR shard index digest changed"
        );
        let mut shards = vec![];
        let mut class_id = 0;
        for (id, line) in BufReader::new(File::open(index)?).lines().enumerate() {
            let shard: Shard = serde_json::from_str(&line?)?;
            ensure!(
                shard.id == id && !shard.entries.is_empty(),
                "Invalid IR shard sequence"
            );
            for entry in &shard.entries {
                ensure!(
                    entry.class_id == class_id,
                    "IR class coverage is not contiguous"
                );
                class_id += 1;
            }
            shards.push(shard);
        }
        ensure!(class_id == summary.classes, "IR class index is truncated");
        Ok(Self {
            root,
            identity: summary.identity,
            input_fingerprint: summary.input_fingerprint,
            jdk_fingerprint: summary.jdk_fingerprint,
            classes: summary.classes,
            methods: summary.counts.methods,
            shards,
        })
    }
    pub fn read_shard<T: serde::de::DeserializeOwned>(&self, index: usize) -> Result<Vec<T>> {
        let shard = self.shards.get(index).context("Invalid IR shard ID")?;
        let filename = Path::new(&shard.zip.path)
            .file_name()
            .context("Missing IR ZIP name")?;
        let path = self.root.join("shards").join(filename);
        ensure!(
            files::digest(&path)? == shard.zip.digest,
            "IR ZIP digest changed"
        );
        let mut zip = zip::ZipArchive::new(File::open(path)?)?;
        ensure!(
            zip.len() == shard.entries.len(),
            "IR ZIP entry coverage differs"
        );
        let mut rows = vec![];
        for entry in &shard.entries {
            ensure!(
                entry.digest.size <= 512 * 1024 * 1024,
                "IR class payload budget exceeded"
            );
            let mut member = zip.by_name(&entry.path)?;
            ensure!(
                member.size() == entry.digest.size,
                "IR class payload length changed"
            );
            let mut bytes = vec![];
            member.read_to_end(&mut bytes)?;
            ensure!(
                files::digest_bytes(&bytes) == entry.digest,
                "IR class payload digest changed"
            );
            rows.push(
                serde_json::from_slice(&bytes)
                    .with_context(|| format!("Reading IR class {}", entry.class_id))?,
            );
        }
        Ok(rows)
    }
}
fn artifact(root: &Path, plan: &InputPlan, name: &str) -> Result<PathBuf> {
    let artifact = plan.artifacts.get(name).context("Missing plan artifact")?;
    let path = root.join(format!("{name}.jsonl"));
    ensure!(
        files::digest(&path)? == artifact.digest,
        "Translation plan {name} artifact digest changed"
    );
    Ok(path)
}
fn read_inputs(
    inputs: &InputLock,
    base: &ClassInputs,
    root: &Path,
) -> Result<(InputPlan, Vec<InputClass>)> {
    let plan: InputPlan = serde_json::from_slice(&fs::read(root.join("summary.json"))?)?;
    ensure!(
        plan.schema == 1 && plan.mode == "inventory_and_plan_only",
        "Unsupported input plan schema/mode"
    );
    ensure!(
        plan.input_fingerprint == inputs.fingerprint && plan.jdk_fingerprint == base.fingerprint(),
        "Translation plan input identity differs"
    );
    ensure!(
        plan.classes <= 100_000 && plan.methods <= 1_000_000,
        "Translation plan budget exceeded"
    );
    let class_path = artifact(root, &plan, "classes")?;
    let method_path = artifact(root, &plan, "methods")?;
    let mut classes = vec![];
    for (id, line) in BufReader::new(File::open(class_path)?).lines().enumerate() {
        let class: ClassTask = serde_json::from_str(&line?)?;
        ensure!(class.id == id, "Noncontiguous class plan");
        classes.push(InputClass {
            class,
            methods: vec![],
        });
    }
    ensure!(classes.len() == plan.classes, "Class plan is truncated");
    let mut methods = 0;
    for (id, line) in BufReader::new(File::open(method_path)?).lines().enumerate() {
        let method: MethodInput = serde_json::from_str(&line?)?;
        ensure!(method.id == id, "Noncontiguous method plan");
        let class = classes
            .get_mut(method.class_id)
            .context("Invalid planned method class")?;
        ensure!(
            method.symbol.loader == class.class.origin.loader
                && method.symbol.owner == class.class.name
                && method.class_sha256 == class.class.origin.sha256,
            "Planned method source identity differs"
        );
        class.methods.push(method);
        methods += 1;
    }
    ensure!(methods == plan.methods, "Method plan is truncated");
    for class in &classes {
        ensure!(
            class.class.method_ids == class.methods.iter().map(|m| m.id).collect::<Vec<_>>(),
            "Planned class method membership differs"
        );
    }
    Ok((plan, classes))
}
fn lower_class(bytes: &[u8], input: &InputClass) -> Result<Class> {
    let parsed = ClassFile::parse(bytes)
        .with_context(|| format!("Parsing planned class {}", input.class.name))?;
    ensure!(
        parsed.name == input.class.name && parsed.methods.len() == input.methods.len(),
        "Class declaration changed from input plan"
    );
    let mut decoder = symbolic::Decoder::new(&parsed);
    let mut fields = vec![];
    for field in &parsed.field_info {
        symbolic::JavaType::field(&field.descriptor)?;
        if let Some(index) = field.constant_value {
            decoder.intern(index)?;
        }
        fields.push(Field {
            name: field.name.clone(),
            descriptor: field.descriptor.clone(),
            access: field.access,
            constant_value: field.constant_value,
        });
    }
    let mut methods = vec![];
    for (member, source) in parsed.methods.iter().zip(&input.methods) {
        ensure!(
            member.name == source.symbol.name
                && member.descriptor == source.symbol.descriptor
                && member.access == source.access,
            "Method declaration changed from plan"
        );
        let digest = member
            .code
            .as_ref()
            .map(|c| files::digest_bytes(&c.bytes).sha256);
        ensure!(digest == source.code_sha256, "Planned method Code changed");
        let signature = symbolic::MethodType::parse(&member.descriptor);
        let (body, diagnostic) = if let Err(error) = &signature {
            (None, Some(format!("{error:#}")))
        } else if member.code.is_some() {
            match decoder.method(member) {
                Ok(body) => (Some(body), None),
                Err(error) => (None, Some(format!("{error:#}"))),
            }
        } else if member.access & (0x100 | 0x400) == 0 {
            (None, Some("Concrete Java method has no Code".into()))
        } else {
            (None, None)
        };
        methods.push(Method {
            id: source.id,
            name: member.name.clone(),
            descriptor: member.descriptor.clone(),
            access: member.access,
            signature: signature.ok(),
            code_sha256: digest,
            body_kind: if member.code.is_some() {
                "java"
            } else if member.access & 0x100 != 0 {
                "native_declaration"
            } else {
                "abstract_declaration"
            }
            .into(),
            body,
            line_numbers: member.line_numbers.clone(),
            diagnostic,
        });
    }
    let constants = decoder.constants;
    Ok(Class {
        schema: symbolic::SCHEMA,
        class_id: input.class.id,
        origin: input.class.origin.clone(),
        name: parsed.name,
        access: parsed.access,
        superclass: parsed.super_name,
        interfaces: parsed.interface_names,
        fields,
        nest_host: parsed.nest_host,
        nest_members: parsed.nest_members,
        record_components: parsed.record_components,
        source_file: parsed.source_file,
        constants,
        methods,
        diagnostic: None,
        type_layout_and_link_verified: false,
        assembly_emitted: false,
    })
}
fn class_counts(class: &Class) -> Counts {
    let mut count = Counts::empty();
    count.constants = class.constants.len();
    for method in &class.methods {
        count.methods += 1;
        count.java_methods += usize::from(method.code_sha256.is_some());
        count.native_declarations += usize::from(method.access & 0x100 != 0);
        count.abstract_declarations += usize::from(method.access & 0x400 != 0);
        count.failed_methods += usize::from(method.diagnostic.is_some());
        if let Some(body) = &method.body {
            count.symbolic_java_methods += 1;
            count.instructions += body.instructions.len();
            count.blocks += body.blocks.len();
            count.legacy_subroutine_methods += usize::from(body.contains_legacy_subroutines);
        }
    }
    count
}
struct Build<'a> {
    inputs: &'a InputLock,
    base: &'a ClassInputs,
    jdk_path: &'a Path,
    output: &'a Path,
    identity: &'a str,
}
fn shard(
    build: &Build<'_>,
    id: usize,
    classes: &[InputClass],
    archives: &ClassArchives,
) -> Result<(Shard, bool)> {
    let cache_key = files::digest_bytes(&serde_json::to_vec(&(
        build.identity,
        id,
        classes
            .iter()
            .map(|c| (&c.class.origin, c.class.method_ids.as_slice()))
            .collect::<Vec<_>>(),
    ))?)
    .sha256;
    let directory = build.output.join("shards");
    let zip_path = directory.join(format!("{id:05}-{cache_key}.zip"));
    let manifest = zip_path.with_extension("json");
    if manifest.is_file() && zip_path.is_file() {
        let cached = (|| -> Result<Shard> {
            let cached: Shard = serde_json::from_slice(&fs::read(&manifest)?)?;
            ensure!(
                cached.id == id
                    && cached.cache_key == cache_key
                    && cached.entries.len() == classes.len(),
                "IR cache identity differs"
            );
            for (entry, input) in cached.entries.iter().zip(classes) {
                ensure!(
                    entry.class_id == input.class.id
                        && entry.class_sha256 == input.class.origin.sha256
                        && entry.counts.methods == input.methods.len(),
                    "IR cache entry identity differs"
                );
            }
            ensure!(
                files::digest(&zip_path)? == cached.zip.digest,
                "IR cache zip changed"
            );
            Ok(cached)
        })();
        if let Ok(mut cached) = cached {
            cached.zip.path = zip_path.display().to_string();
            return Ok((cached, true));
        }
    }
    let mut temporary = tempfile::NamedTempFile::new_in(&directory)?;
    let mut entries = vec![];
    {
        let mut zip = ZipWriter::new(temporary.as_file_mut());
        let options = SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .compression_level(Some(1));
        for input in classes {
            let origin = &input.class.origin;
            let bytes = if jdk_classes::is_system(origin) {
                let (bytes, found) = build.base.read_class(build.jdk_path, &origin.binary_name)?;
                ensure!(found == *origin, "Planned JDK source origin changed");
                bytes
            } else {
                archives.read(&build.inputs.file(&origin.source_id)?.path, origin)?
            };
            // Input integrity errors are fatal. A source-valid frontend error is
            // retained per class/method and never becomes executable success.
            let unit = match lower_class(&bytes, input) {
                Ok(unit) => unit,
                Err(error) => Class {
                    schema: symbolic::SCHEMA,
                    class_id: input.class.id,
                    origin: origin.clone(),
                    name: input.class.name.clone(),
                    access: input.class.access,
                    superclass: input.class.superclass.clone(),
                    interfaces: input.class.interfaces.clone(),
                    fields: vec![],
                    nest_host: None,
                    nest_members: None,
                    record_components: None,
                    source_file: None,
                    constants: BTreeMap::new(),
                    methods: input
                        .methods
                        .iter()
                        .map(|m| Method {
                            id: m.id,
                            name: m.symbol.name.clone(),
                            descriptor: m.symbol.descriptor.clone(),
                            access: m.access,
                            signature: None,
                            code_sha256: m.code_sha256.clone(),
                            body_kind: "class_frontend_error".into(),
                            body: None,
                            line_numbers: vec![],
                            diagnostic: Some(format!("Class frontend: {error:#}")),
                        })
                        .collect(),
                    diagnostic: Some(format!("{error:#}")),
                    type_layout_and_link_verified: false,
                    assembly_emitted: false,
                },
            };
            let counts = class_counts(&unit);
            let data = serde_json::to_vec(&unit)?;
            let path = format!("classes/{:06}.json", input.class.id);
            zip.start_file(&path, options)?;
            zip.write_all(&data)?;
            entries.push(Entry {
                class_id: input.class.id,
                class_sha256: origin.sha256.clone(),
                path,
                digest: files::digest_bytes(&data),
                counts,
                class_diagnostic: unit.diagnostic,
            });
        }
        zip.finish()?;
    }
    temporary.persist(&zip_path).map_err(|e| e.error)?;
    let result = Shard {
        id,
        cache_key,
        zip: Artifact {
            path: zip_path.display().to_string(),
            digest: files::digest(&zip_path)?,
        },
        entries,
    };
    files::write_atomic(&manifest, &serde_json::to_vec(&result)?)?;
    Ok((result, false))
}

/// Build every Java body into source-bound, unresolved IR. No JVM is launched.
pub fn lower(
    inputs: &InputLock,
    jdk_path: &Path,
    plan_path: &Path,
    output: &Path,
    workers: usize,
) -> Result<Summary> {
    let started = Instant::now();
    ensure!((1..=64).contains(&workers), "IR workers must be in 1..=64");
    inputs.verify()?;
    let base = ClassInputs::read(jdk_path, inputs)?;
    let (plan, classes) = read_inputs(inputs, &base, plan_path)?;
    fs::create_dir_all(output.join("shards"))?;
    let output = files::absolute(output)?;
    let compiler_sha256 = files::digest(&std::env::current_exe()?)?.sha256;
    let identity = files::digest_bytes(&serde_json::to_vec(&(
        symbolic::SCHEMA,
        &inputs.fingerprint,
        &base.fingerprint(),
        &plan.planner_fingerprint,
        &compiler_sha256,
        &plan.artifacts["classes"].digest,
        &plan.artifacts["methods"].digest,
    ))?)
    .sha256;
    let tasks = classes.chunks(CLASSES_PER_SHARD).collect::<Vec<_>>();
    let next = AtomicUsize::new(0);
    let done = AtomicUsize::new(0);
    let build = Build {
        inputs,
        base: &base,
        jdk_path,
        output: &output,
        identity: &identity,
    };
    let workers = workers.min(tasks.len().max(1));
    eprintln!(
        "Lowering {} planned methods in {} class shards with {workers} workers; emitting symbolic IR only",
        plan.methods,
        tasks.len()
    );
    let mut results = std::thread::scope(|scope| -> Result<Vec<(Shard, bool)>> {
        let mut handles = vec![];
        for _ in 0..workers {
            let tasks = &tasks;
            let next = &next;
            let done = &done;
            let build = &build;
            handles.push(scope.spawn(move || -> Result<Vec<(Shard, bool)>> {
                let archives = ClassArchives::default();
                let mut rows = vec![];
                loop {
                    let id = next.fetch_add(1, Ordering::Relaxed);
                    let Some(classes) = tasks.get(id) else { break };
                    rows.push(shard(build, id, classes, &archives)?);
                    let count = done.fetch_add(1, Ordering::Relaxed) + 1;
                    if count.is_multiple_of(32) || count == tasks.len() {
                        eprintln!("Symbolic IR shards complete: {count}/{}", tasks.len());
                    }
                }
                Ok(rows)
            }));
        }
        let mut all = vec![];
        for handle in handles {
            all.extend(
                handle
                    .join()
                    .map_err(|_| anyhow::anyhow!("IR worker panicked"))??,
            );
        }
        Ok(all)
    })?;
    results.sort_by_key(|r| r.0.id);
    let mut counts = Counts::empty();
    let mut class_failures = 0;
    for (shard, _) in &results {
        for entry in &shard.entries {
            counts.add(&entry.counts);
            class_failures += usize::from(entry.class_diagnostic.is_some());
        }
    }
    ensure!(
        counts.methods == plan.methods,
        "IR output method coverage differs from plan"
    );
    let index_path = output.join("shards.jsonl");
    let mut temporary = tempfile::NamedTempFile::new_in(&output)?;
    for (shard, _) in &results {
        serde_json::to_writer(temporary.as_file_mut(), shard)?;
        temporary.write_all(b"\n")?;
    }
    temporary.persist(&index_path).map_err(|e| e.error)?;
    let summary = Summary {
        schema: symbolic::SCHEMA,
        mode: "symbolic_ir_only",
        input_fingerprint: inputs.fingerprint.clone(),
        jdk_fingerprint: base.fingerprint().into(),
        source_plan_fingerprint: plan.planner_fingerprint,
        compiler_sha256,
        identity,
        workers,
        elapsed_ms: started.elapsed().as_millis(),
        classes: classes.len(),
        counts,
        class_failures,
        shards: results.len(),
        reused_shards: results.iter().filter(|r| r.1).count(),
        index: Artifact {
            path: index_path.display().to_string(),
            digest: files::digest(&index_path)?,
        },
        type_layout_and_link_verified: false,
        assembly_emitted_methods: 0,
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
    fn a_bad_method_does_not_prevent_other_bodies_from_becoming_symbolic_ir() {
        let bytes =
            symbolic::fixture(&[(5, 6, &[0xa7, 0, 1]), (23, 20, &[0xba, 0, 22, 0, 0, 0xb0])]);
        let parsed = ClassFile::parse(&bytes).unwrap();
        let digest = files::digest_bytes(&bytes).sha256;
        let origin = ClassOrigin {
            loader: "app".into(),
            binary_name: "p.IR".into(),
            source_id: "fixture".into(),
            jar_entry: "p/IR.class".into(),
            java_class_major: 65,
            sha256: digest.clone(),
            generated: None,
        };
        let methods = parsed
            .methods
            .iter()
            .enumerate()
            .map(|(id, m)| MethodInput {
                id,
                class_id: 0,
                symbol: Symbol {
                    loader: "app".into(),
                    owner: "p/IR".into(),
                    name: m.name.clone(),
                    descriptor: m.descriptor.clone(),
                },
                class_sha256: digest.clone(),
                access: m.access,
                code_sha256: m
                    .code
                    .as_ref()
                    .map(|c| files::digest_bytes(&c.bytes).sha256),
            })
            .collect();
        let input = InputClass {
            class: ClassTask {
                id: 0,
                origin,
                name: "p/IR".into(),
                access: 0x21,
                superclass: "java/lang/Object".into(),
                interfaces: vec![],
                fields: vec![],
                method_ids: vec![0, 1],
                parse_error: None,
            },
            methods,
        };
        let class = lower_class(&bytes, &input).unwrap();
        assert!(class.methods[0].diagnostic.is_some());
        assert!(class.methods[1].diagnostic.is_none() && class.methods[1].body.is_some());
        assert!(!class.type_layout_and_link_verified && !class.assembly_emitted);
        let counts = class_counts(&class);
        assert_eq!(
            (
                counts.methods,
                counts.failed_methods,
                counts.symbolic_java_methods
            ),
            (2, 1, 1)
        );
    }
}
