//! Whole-input inventory and dependency batches. This stage emits no game code.
use super::{classfile::ClassFile, exceptions, numeric};
use crate::{
    bytecode::{BytecodeProvider, ClassArchives, ClassOrigin, VanillaBytecodeProvider},
    files,
    jdk_classes::{self, ClassInputs, Packages},
    lock::InputLock,
};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet, VecDeque},
    fs,
    io::{BufWriter, Write},
    path::Path,
    sync::atomic::{AtomicUsize, Ordering},
};

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Symbol {
    pub loader: String,
    pub owner: String,
    pub name: String,
    pub descriptor: String,
}
#[derive(Debug, Clone, Serialize)]
pub struct Call {
    pub pc: usize,
    pub opcode: u8,
    pub owner: String,
    pub name: String,
    pub descriptor: String,
}
#[derive(Debug, Serialize)]
pub struct FieldUse {
    pub pc: usize,
    pub opcode: u8,
    pub owner: String,
    pub name: String,
    pub descriptor: String,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct FieldDeclaration {
    pub name: String,
    pub descriptor: String,
    pub access: u16,
}
#[derive(Debug, Clone, Serialize)]
pub struct Problem {
    pub category: String,
    pub target: String,
    pub detail: String,
}
#[derive(Debug, Serialize)]
pub struct MethodTask {
    pub id: usize,
    pub class_id: usize,
    pub symbol: Symbol,
    pub class_sha256: String,
    pub access: u16,
    pub kind: String,
    pub code_sha256: Option<String>,
    pub code_bytes: usize,
    pub max_stack: u16,
    pub max_locals: u16,
    pub exception_handlers: usize,
    pub calls: Vec<Call>,
    pub fields: Vec<FieldUse>,
    pub referenced_classes: Vec<String>,
    pub initialize_classes: Vec<String>,
    pub problems: Vec<Problem>,
    pub structural_scan_complete: bool,
    pub type_layout_and_link_verified: bool,
    pub assembly_emitted: bool,
    pub conservative_startup_reachable: bool,
    pub conservative_main_reachable: bool,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct ClassTask {
    pub id: usize,
    pub origin: ClassOrigin,
    pub name: String,
    pub access: u16,
    pub superclass: String,
    pub interfaces: Vec<String>,
    pub fields: Vec<FieldDeclaration>,
    pub method_ids: Vec<usize>,
    pub parse_error: Option<String>,
}
struct Scanned {
    class: ClassTask,
    methods: Vec<MethodTask>,
    opcodes: BTreeMap<u8, u64>,
}
#[derive(Debug, Serialize)]
pub struct Group {
    pub category: String,
    pub target: String,
    pub occurrences: usize,
    pub affected_methods: Vec<usize>,
    pub startup_methods: usize,
    pub main_methods: usize,
    pub examples: Vec<String>,
}
#[derive(Debug, Serialize)]
pub struct Batch {
    pub id: usize,
    pub method_ids: Vec<usize>,
    pub dependency_batches: Vec<usize>,
    pub stage: String,
    pub startup_priority: bool,
    pub main_priority: bool,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Artifact {
    pub path: String,
    pub digest: files::FileDigest,
}
#[derive(Debug, Serialize)]
pub struct Summary {
    pub schema: u32,
    pub mode: &'static str,
    pub input_fingerprint: String,
    pub jdk_fingerprint: String,
    pub planner_fingerprint: String,
    pub game_version: String,
    pub side: String,
    pub workers: usize,
    pub application_classes: usize,
    pub java_base_classes: usize,
    pub additional_system_classes: usize,
    pub system_classes: usize,
    pub shadowed_application_classes: usize,
    pub classes: usize,
    pub class_parse_failures: usize,
    pub methods: usize,
    pub java_methods: usize,
    pub native_methods: usize,
    pub native_binding_candidates: usize,
    pub native_without_catalog_entry: usize,
    pub abstract_methods: usize,
    pub structurally_scanned_java_methods: usize,
    pub compatibility_groups: usize,
    pub conservative_startup_methods: usize,
    pub conservative_main_methods: usize,
    pub batches: usize,
    pub unresolved_symbolic_calls: usize,
    pub dependency_edges: usize,
    pub startup_seed_methods: Vec<usize>,
    pub main_seed_methods: Vec<usize>,
    pub virtual_dispatch_overapproximated: bool,
    pub reflection_and_other_jdk_modules_require_further_resolution: bool,
    pub native_catalog_is_complete: bool,
    pub type_layout_and_link_verified: bool,
    pub compiled_methods: usize,
    pub game_started: bool,
    pub world_created: bool,
    pub full_game_ready: bool,
    pub roots: Vec<Symbol>,
    pub missing_roots: Vec<Symbol>,
    pub artifacts: BTreeMap<String, Artifact>,
}
fn problem(category: &str, target: impl Into<String>, detail: impl Into<String>) -> Problem {
    Problem {
        category: category.into(),
        target: target.into(),
        detail: detail.into(),
    }
}
fn native_candidate(owner: &str, name: &str, desc: &str) -> bool {
    macro_rules! known { ($($module:ident),*) => { false $(||super::$module::Operation::resolve(owner,name,desc).is_some())* }; }
    if known!(
        vm,
        vm_registration,
        thread_natives,
        unsafe_bootstrap,
        file_descriptors,
        system_streams,
        cds,
        access_context,
        signal_natives,
        shutdown,
        reflection_arrays
    ) {
        return true;
    }
    matches!(
        (owner, name, desc),
        (
            "java/lang/Class",
            "getPrimitiveClass",
            "(Ljava/lang/String;)Ljava/lang/Class;"
        ) | (
            "java/lang/Class",
            "forName0",
            "(Ljava/lang/String;ZLjava/lang/ClassLoader;Ljava/lang/Class;)Ljava/lang/Class;"
        ) | (
            "java/lang/ClassLoader",
            "findBootstrapClass",
            "(Ljava/lang/String;)Ljava/lang/Class;"
        ) | ("java/lang/ClassLoader", "registerNatives", "()V")
            | (
                "java/lang/ClassLoader",
                "retrieveDirectives",
                "()Ljava/lang/AssertionStatusDirectives;"
            )
            | (
                "java/io/FileInputStream" | "java/io/FileOutputStream" | "java/io/WinNTFileSystem",
                "initIDs",
                "()V"
            )
            | ("java/lang/Object", "getClass", "()Ljava/lang/Class;")
            | ("java/lang/Object", "hashCode", "()I")
            | ("java/lang/Object", "notify" | "notifyAll", "()V")
    ) || (owner == "java/lang/Class" && numeric::ClassIntrinsic::resolve(name, desc).is_ok())
}
fn opaque(owner: &str) -> bool {
    matches!(
        owner,
        "java/lang/String"
            | "java/lang/Class"
            | "java/lang/ModuleLayer"
            | "java/lang/reflect/Field"
            | "java/lang/reflect/Constructor"
    )
}
fn runtime_adapter_candidate(owner: &str, name: &str, desc: &str) -> bool {
    (owner == "java/lang/String" && numeric::StringIntrinsic::resolve(name, desc).is_ok())
        || (owner == "java/lang/Class" && numeric::ClassIntrinsic::resolve(name, desc).is_ok())
        || super::modules::Operation::resolve(owner, name, desc)
            .ok()
            .flatten()
            .is_some()
}
fn read_u16(bytes: &[u8], pc: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(
        bytes
            .get(pc..pc + 2)
            .context("Truncated constant operand")?
            .try_into()?,
    ))
}
fn descriptor_classes(descriptor: &str) -> Vec<String> {
    let mut types = vec![];
    let mut remaining = descriptor;
    while let Some(start) = remaining.find('L') {
        let rest = &remaining[start + 1..];
        let Some(end) = rest.find(';') else { break };
        types.push(rest[..end].into());
        remaining = &rest[end + 1..];
    }
    types
}
fn scan_method(
    class: &ClassFile,
    origin: &ClassOrigin,
    class_id: usize,
    index: usize,
) -> MethodTask {
    let method = &class.methods[index];
    let native = method.access & 0x100 != 0;
    let abstract_method = method.access & 0x400 != 0;
    let candidate = origin.loader == "bootstrap"
        && native_candidate(&class.name, &method.name, &method.descriptor);
    let mut task = MethodTask {
        id: 0,
        class_id,
        symbol: Symbol {
            loader: origin.loader.clone(),
            owner: class.name.clone(),
            name: method.name.clone(),
            descriptor: method.descriptor.clone(),
        },
        class_sha256: origin.sha256.clone(),
        access: method.access,
        kind: if native {
            if candidate {
                "native_binding_candidate"
            } else {
                "native_compatibility"
            }
        } else if abstract_method {
            "metadata_only"
        } else {
            "java_pending_lowering"
        }
        .into(),
        code_sha256: method
            .code
            .as_ref()
            .map(|c| files::digest_bytes(&c.bytes).sha256),
        code_bytes: method.code.as_ref().map_or(0, |c| c.bytes.len()),
        max_stack: method.code.as_ref().map_or(0, |c| c.max_stack),
        max_locals: method.code.as_ref().map_or(0, |c| c.max_locals),
        exception_handlers: method.code.as_ref().map_or(0, |c| c.handlers.len()),
        calls: vec![],
        fields: vec![],
        referenced_classes: descriptor_classes(&method.descriptor),
        initialize_classes: vec![],
        problems: vec![],
        structural_scan_complete: false,
        type_layout_and_link_verified: false,
        assembly_emitted: false,
        conservative_startup_reachable: false,
        conservative_main_reachable: false,
    };
    if native && !candidate {
        task.problems.push(problem("native_without_catalog_entry",format!("{}.{}{}",class.name,method.name,method.descriptor),"Needs binding audit; this inventory is not proof that every uncatalogued native is unimplemented"));
    }
    if origin.loader == "bootstrap" && opaque(&class.name) && !native && !abstract_method {
        if runtime_adapter_candidate(&class.name, &method.name, &method.descriptor) {
            task.kind = "runtime_adapter_candidate".into();
        } else {
            task.problems.push(problem("vm_owned_layout",class.name.clone(),"Original Java body uses a VM-owned class layout; requires generic layout adaptation or a verified adapter"));
        }
    }
    let Some(code) = &method.code else {
        return task;
    };
    let scan = (|| -> Result<()> {
        let starts = exceptions::boundaries(&code.bytes)?;
        for &pc in &starts {
            let op = code.bytes[pc];
            if matches!(op, 0xa8 | 0xa9 | 0xc9)
                || (op == 0xc4 && code.bytes.get(pc + 1) == Some(&0xa9))
            {
                task.problems.push(problem(
                    "legacy_subroutine",
                    "jsr/ret",
                    "No executable backend lowering for legacy subroutines",
                ));
            }
            match op {
                0xb6..=0xb9 => {
                    let constant = read_u16(&code.bytes, pc + 1)?;
                    let (owner, name, descriptor) = if op == 0xb6 {
                        class.method_reference(constant)?
                    } else if op == 0xb9 {
                        class.interface_method_reference(constant)?
                    } else {
                        let (o, n, d, _) = class.special_method_reference(constant)?;
                        (o, n, d)
                    };
                    if op == 0xb8 {
                        task.initialize_classes.push(owner.clone());
                    }
                    if (owner == "java/lang/Class"
                        && matches!(
                            name.as_str(),
                            "forName" | "getDeclaredMethod" | "getDeclaredMethods"
                        ))
                        || (owner == "java/lang/ClassLoader"
                            && matches!(name.as_str(), "loadClass" | "defineClass"))
                        || owner.starts_with("java/lang/invoke/MethodHandle")
                        || owner == "java/lang/reflect/Method"
                    {
                        task.problems.push(problem(
                            "dynamic_resolution_review",
                            format!("{owner}.{name}{descriptor}"),
                            "Static call graph is not sufficient evidence for this dynamic API",
                        ));
                    }
                    task.calls.push(Call {
                        pc,
                        opcode: op,
                        owner,
                        name,
                        descriptor,
                    });
                }
                0xba => {
                    let site = class.dynamic_site(read_u16(&code.bytes, pc + 1)?)?;
                    let b = &site.bootstrap;
                    let known = matches!(
                        (b.owner.as_str(), b.name.as_str()),
                        (
                            "java/lang/invoke/StringConcatFactory",
                            "makeConcat" | "makeConcatWithConstants"
                        ) | (
                            "java/lang/invoke/LambdaMetafactory",
                            "metafactory" | "altMetafactory"
                        )
                    ) || (b.owner == "java/lang/runtime/ObjectMethods"
                        && site.name == "toString");
                    task.problems.push(problem(if known {"bootstrap_family_review"}else{"bootstrap_compatibility"},format!("{}.{}:{}",b.owner,b.name,site.name),if known {"Known frontend family; call-site arguments, access and lowering still require validation"}else{"No catalogued lowering for this bootstrap operation"}));
                    for arg in site.arguments {
                        if let Ok(handle) = class.method_handle(arg)
                            && handle.reference_kind >= 5
                        {
                            task.calls.push(Call {
                                pc,
                                opcode: if handle.reference_kind == 6 {
                                    0xb8
                                } else if handle.reference_kind == 8 {
                                    0xb7
                                } else {
                                    0xb6
                                },
                                owner: handle.owner,
                                name: handle.name,
                                descriptor: handle.descriptor,
                            });
                        }
                    }
                }
                0xb2..=0xb5 => {
                    let (owner, name, desc) =
                        class.field_reference(read_u16(&code.bytes, pc + 1)?)?;
                    if op <= 0xb3 {
                        task.initialize_classes.push(owner.clone());
                    }
                    if opaque(&owner) {
                        let known = super::class_loaders::field(&owner, &name, &desc)
                            || super::class_queries::component_field(&owner, &name, &desc)
                            || super::class_queries::class_value_field(&owner, &name, &desc);
                        if !known {
                            task.problems.push(problem("opaque_field_layout",format!("{owner}.{name}:{desc}"),"Resolve through the VM layout adapter; ordinary Java offsets cannot be assumed"));
                        }
                    }
                    task.fields.push(FieldUse {
                        pc,
                        opcode: op,
                        owner,
                        name,
                        descriptor: desc,
                    });
                }
                0xbb | 0xbd | 0xc0 | 0xc1 | 0xc5 => {
                    let name = class.constant_class(read_u16(&code.bytes, pc + 1)?)?;
                    if op == 0xbb {
                        task.initialize_classes.push(name.clone());
                    }
                    task.referenced_classes.push(name);
                }
                0x12..=0x14 => {
                    let index = if op == 0x12 {
                        u16::from(code.bytes[pc + 1])
                    } else {
                        read_u16(&code.bytes, pc + 1)?
                    };
                    let tag = class.constant_tag(index)?;
                    if tag == 7 {
                        task.referenced_classes.push(class.constant_class(index)?);
                    }
                    if matches!(tag, 15..=17) {
                        task.problems.push(problem(
                            "runtime_constant_review",
                            format!("constant_tag_{}", class.constant_tag(index)?),
                            "Method handle/type or dynamic constant requires source-bound lowering",
                        ));
                    }
                }
                _ => {}
            }
        }
        for h in &code.handlers {
            ensure!(
                starts.contains(&(h.start_pc as usize))
                    && starts.contains(&(h.handler_pc as usize))
                    && (h.end_pc as usize == code.bytes.len()
                        || starts.contains(&(h.end_pc as usize))),
                "Exception handler is not on instruction boundaries"
            );
        }
        Ok(())
    })();
    match scan {
        Ok(()) => task.structural_scan_complete = true,
        Err(e) => task.problems.push(problem(
            "bytecode_structure",
            format!("{}.{}{}", class.name, method.name, method.descriptor),
            format!("{e:#}"),
        )),
    }
    task.initialize_classes.sort();
    task.initialize_classes.dedup();
    for call in &task.calls {
        task.referenced_classes.push(call.owner.clone());
        task.referenced_classes
            .extend(descriptor_classes(&call.descriptor));
    }
    for field in &task.fields {
        task.referenced_classes.push(field.owner.clone());
        task.referenced_classes
            .extend(descriptor_classes(&field.descriptor));
    }
    task.referenced_classes
        .extend(code.handlers.iter().filter_map(|h| h.catch_type.clone()));
    task.referenced_classes.sort();
    task.referenced_classes.dedup();
    task
}
fn scan_class(bytes: &[u8], origin: ClassOrigin, id: usize) -> Scanned {
    let mut out = Scanned {
        class: ClassTask {
            id,
            name: origin.binary_name.replace('.', "/"),
            access: 0,
            origin,
            superclass: String::new(),
            interfaces: vec![],
            fields: vec![],
            method_ids: vec![],
            parse_error: None,
        },
        methods: vec![],
        opcodes: BTreeMap::new(),
    };
    let class = match ClassFile::parse(bytes) {
        Ok(c) => c,
        Err(e) => {
            out.class.parse_error = Some(format!("{e:#}"));
            return out;
        }
    };
    if class.name != out.class.name {
        out.class.parse_error =
            Some("Class declaration differs from its selected archive name".into());
        return out;
    }
    out.class.superclass = class.super_name.clone();
    out.class.access = class.access;
    out.class.interfaces = class.interface_names.clone();
    out.class.fields = class
        .field_info
        .iter()
        .map(|f| FieldDeclaration {
            name: f.name.clone(),
            descriptor: f.descriptor.clone(),
            access: f.access,
        })
        .collect();
    for (index, method) in class.methods.iter().enumerate() {
        if let Some(code) = &method.code
            && let Ok(starts) = exceptions::boundaries(&code.bytes)
        {
            for pc in starts {
                *out.opcodes.entry(code.bytes[pc]).or_default() += 1;
            }
        }
        out.methods
            .push(scan_method(&class, &out.class.origin, id, index));
    }
    out
}

fn class_lookup(
    index: &BTreeMap<(String, String), usize>,
    packages: &Packages,
    loader: &str,
    name: &str,
) -> Option<usize> {
    jdk_classes::lookup(packages, loader, name, |loader, name| {
        index.get(&(loader.into(), name.into())).copied()
    })
}
fn resolve_method(
    owner: usize,
    name: &str,
    desc: &str,
    parents: &[Vec<usize>],
    members: &BTreeMap<(usize, String, String), usize>,
) -> Option<usize> {
    if matches!(name, "<init>" | "<clinit>") {
        return members.get(&(owner, name.into(), desc.into())).copied();
    }
    let mut queue = VecDeque::from([owner]);
    let mut seen = BTreeSet::new();
    while let Some(id) = queue.pop_front() {
        if !seen.insert(id) {
            continue;
        }
        if let Some(&method) = members.get(&(id, name.into(), desc.into())) {
            return Some(method);
        }
        queue.extend(parents[id].iter().copied());
    }
    None
}
fn ancestors(parents: &[Vec<usize>], id: usize) -> BTreeSet<usize> {
    let mut seen = BTreeSet::new();
    let mut todo = vec![id];
    while let Some(id) = todo.pop() {
        if seen.insert(id) {
            todo.extend(parents[id].iter().copied());
        }
    }
    seen
}
fn reachable(graph: &[Vec<usize>], roots: &[usize]) -> Vec<bool> {
    let mut seen = vec![false; graph.len()];
    let mut todo = roots.to_vec();
    while let Some(id) = todo.pop() {
        if !seen[id] {
            seen[id] = true;
            todo.extend(graph[id].iter().copied());
        }
    }
    seen
}
fn components(graph: &[Vec<usize>]) -> Vec<Vec<usize>> {
    let mut seen = vec![false; graph.len()];
    let mut order = Vec::with_capacity(graph.len());
    for start in 0..graph.len() {
        if seen[start] {
            continue;
        }
        seen[start] = true;
        let mut stack = vec![(start, 0)];
        while let Some((id, next)) = stack.last_mut() {
            if *next < graph[*id].len() {
                let dest = graph[*id][*next];
                *next += 1;
                if !seen[dest] {
                    seen[dest] = true;
                    stack.push((dest, 0));
                }
            } else {
                order.push(*id);
                stack.pop();
            }
        }
    }
    let mut reverse = vec![Vec::new(); graph.len()];
    for (source, edges) in graph.iter().enumerate() {
        for &target in edges {
            reverse[target].push(source);
        }
    }
    seen.fill(false);
    let mut result = Vec::new();
    for start in order.into_iter().rev() {
        if seen[start] {
            continue;
        }
        let mut members = vec![];
        let mut stack = vec![start];
        while let Some(id) = stack.pop() {
            if !seen[id] {
                seen[id] = true;
                members.push(id);
                stack.extend(reverse[id].iter().copied());
            }
        }
        members.sort_unstable();
        result.push(members);
    }
    result.reverse();
    result
}
fn write_jsonl<T: Serialize>(path: &Path, rows: impl IntoIterator<Item = T>) -> Result<Artifact> {
    let temp =
        tempfile::NamedTempFile::new_in(path.parent().context("Missing artifact directory")?)?;
    {
        let mut writer = BufWriter::new(temp.as_file());
        for row in rows {
            serde_json::to_writer(&mut writer, &row)?;
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

/// Build a conservative inventory, not a statement of executable coverage.
pub fn plan(
    inputs: &InputLock,
    jdk_path: &Path,
    output: &Path,
    requested_workers: usize,
) -> Result<Summary> {
    ensure!(
        (1..=64).contains(&requested_workers),
        "Planner workers must be in 1..=64"
    );
    let application = VanillaBytecodeProvider { inputs }.snapshot()?;
    let base = ClassInputs::read(jdk_path, inputs)?;
    let packages = base.packages()?;
    let mut jobs = base
        .classes()
        .values()
        .cloned()
        .map(|o| (true, o))
        .collect::<Vec<_>>();
    let mut shadowed = application.shadowed.len();
    for origin in application.classes.values() {
        let package = origin
            .binary_name
            .rsplit_once('.')
            .map(|(p, _)| p.replace('.', "/"));
        if base.classes().contains_key(&origin.binary_name)
            || package.is_some_and(|p| packages.contains_key(&p))
        {
            shadowed += 1;
        } else {
            jobs.push((false, origin.clone()));
        }
    }
    jobs.sort_by(|a, b| (&a.1.loader, &a.1.binary_name).cmp(&(&b.1.loader, &b.1.binary_name)));
    ensure!(jobs.len() <= 100_000, "Whole-input class budget exceeded");
    let next = AtomicUsize::new(0);
    let workers = requested_workers.min(jobs.len().max(1));
    eprintln!(
        "Inventorying {} selected classes with {workers} workers",
        jobs.len()
    );
    let scanned = std::thread::scope(|scope| -> Result<Vec<Scanned>> {
        let mut handles = vec![];
        for _ in 0..workers {
            let jobs = &jobs;
            let next = &next;
            let base = &base;
            handles.push(scope.spawn(move || -> Result<Vec<Scanned>> {
                let archives = ClassArchives::default();
                let mut rows = vec![];
                loop {
                    let id = next.fetch_add(1, Ordering::Relaxed);
                    let Some((jdk, origin)) = jobs.get(id) else {
                        break;
                    };
                    let bytes = if *jdk {
                        base.read_class(jdk_path, &origin.binary_name)?.0
                    } else {
                        archives.read(&inputs.file(&origin.source_id)?.path, origin)?
                    };
                    rows.push(scan_class(&bytes, origin.clone(), id));
                }
                Ok(rows)
            }));
        }
        let mut all = vec![];
        for handle in handles {
            all.extend(
                handle
                    .join()
                    .map_err(|_| anyhow::anyhow!("Planner worker panicked"))??,
            );
        }
        Ok(all)
    })?;
    let mut scanned = scanned;
    scanned.sort_by_key(|c| c.class.id);
    let mut classes = vec![];
    let mut methods = vec![];
    let mut opcodes = BTreeMap::<u8, u64>::new();
    for mut c in scanned {
        for mut m in c.methods {
            m.id = methods.len();
            c.class.method_ids.push(m.id);
            methods.push(m);
        }
        for (op, n) in c.opcodes {
            *opcodes.entry(op).or_default() += n;
        }
        classes.push(c.class);
    }
    ensure!(
        methods.len() <= 1_000_000,
        "Whole-input method budget exceeded"
    );
    eprintln!(
        "Indexed {} methods; building conservative dependency graph",
        methods.len()
    );
    let index = classes
        .iter()
        .map(|c| ((c.origin.loader.clone(), c.name.clone()), c.id))
        .collect::<BTreeMap<_, _>>();
    let parents = classes
        .iter()
        .map(|c| {
            std::iter::once(&c.superclass)
                .chain(c.interfaces.iter())
                .filter_map(|name| class_lookup(&index, &packages, &c.origin.loader, name))
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();
    let ancestry = (0..classes.len())
        .map(|id| ancestors(&parents, id))
        .collect::<Vec<_>>();
    let members = methods
        .iter()
        .map(|m| {
            (
                (
                    m.class_id,
                    m.symbol.name.clone(),
                    m.symbol.descriptor.clone(),
                ),
                m.id,
            )
        })
        .collect::<BTreeMap<_, _>>();
    let mut signatures = BTreeMap::<(String, String), Vec<usize>>::new();
    for m in &methods {
        if m.access & 8 == 0 {
            signatures
                .entry((m.symbol.name.clone(), m.symbol.descriptor.clone()))
                .or_default()
                .push(m.id);
        }
    }
    let mut dispatch = BTreeMap::<(usize, String, String), Vec<usize>>::new();
    let mut graph = vec![Vec::new(); methods.len()];
    let mut resolution_problems = vec![Vec::new(); methods.len()];
    let mut unresolved = 0;
    for m in &methods {
        let mut edges = BTreeSet::new();
        for call in &m.calls {
            let Some(owner) = class_lookup(&index, &packages, &m.symbol.loader, &call.owner) else {
                unresolved += 1;
                resolution_problems[m.id].push(problem(
                    if call.owner.starts_with('[') { "array_vm_call_review" } else { "class_definition_required" },
                    &call.owner,
                    format!("Call at pc {} needs a VM array operation or a definition outside the indexed input; not proof of an unimplemented method", call.pc),
                ));
                continue;
            };
            if matches!(call.opcode, 0xb6 | 0xb9) {
                let key = (owner, call.name.clone(), call.descriptor.clone());
                let found = dispatch.entry(key).or_insert_with(|| {
                    let mut found = signatures
                        .get(&(call.name.clone(), call.descriptor.clone()))
                        .into_iter()
                        .flatten()
                        .copied()
                        .filter(|id| ancestry[methods[*id].class_id].contains(&owner))
                        .collect::<BTreeSet<_>>();
                    // An implementation inherited from a superclass need not
                    // itself declare the interface implemented by its subclass.
                    if classes[owner].access & 0x200 != 0 {
                        for (id, ancestors) in ancestry.iter().enumerate() {
                            if ancestors.contains(&owner)
                                && let Some(target) = resolve_method(
                                    id,
                                    &call.name,
                                    &call.descriptor,
                                    &parents,
                                    &members,
                                )
                            {
                                found.insert(target);
                            }
                        }
                    }
                    found.into_iter().collect()
                });
                edges.extend(found.iter().copied());
            }
            if let Some(target) =
                resolve_method(owner, &call.name, &call.descriptor, &parents, &members)
            {
                edges.insert(target);
            } else {
                unresolved += 1;
                resolution_problems[m.id].push(problem(
                    if call.owner.starts_with("java/lang/invoke/MethodHandle")
                        || call.owner == "java/lang/invoke/VarHandle" {
                        "signature_polymorphic_resolution_review"
                    } else { "member_resolution_review" },
                    format!("{}.{}{}", call.owner, call.name, call.descriptor),
                    format!("No exact indexed declaration at pc {}; symbolic linking and dynamic API rules still need verification", call.pc),
                ));
            }
        }
        for name in &m.initialize_classes {
            if let Some(owner) = class_lookup(&index, &packages, &m.symbol.loader, name) {
                for &id in &ancestry[owner] {
                    if let Some(&init) = members.get(&(id, "<clinit>".into(), "()V".into())) {
                        edges.insert(init);
                    }
                }
            }
        }
        graph[m.id] = edges.into_iter().collect();
    }
    for (m, problems) in methods.iter_mut().zip(resolution_problems) {
        m.problems.extend(problems);
    }
    let roots = vec![
        Symbol {
            loader: "bootstrap".into(),
            owner: "java/lang/System".into(),
            name: "initPhase1".into(),
            descriptor: "()V".into(),
        },
        Symbol {
            loader: "bootstrap".into(),
            owner: "java/lang/System".into(),
            name: "initPhase2".into(),
            descriptor: "(ZZ)I".into(),
        },
        Symbol {
            loader: "bootstrap".into(),
            owner: "java/lang/System".into(),
            name: "initPhase3".into(),
            descriptor: "()V".into(),
        },
        Symbol {
            loader: "vanilla-application".into(),
            owner: inputs.main_class.replace('.', "/"),
            name: "main".into(),
            descriptor: "([Ljava/lang/String;)V".into(),
        },
    ];
    let mut missing_roots = vec![];
    let mut startup = vec![];
    let mut main = vec![];
    for (i, root) in roots.iter().enumerate() {
        let owner = class_lookup(&index, &packages, &root.loader, &root.owner);
        let id = owner.and_then(|owner| {
            members
                .get(&(owner, root.name.clone(), root.descriptor.clone()))
                .copied()
        });
        if let Some(id) = id {
            let seeds = if i < 3 { &mut startup } else { &mut main };
            seeds.push(id);
            for &class in &ancestry[owner.expect("Resolved method has an owner")] {
                if let Some(&init) = members.get(&(class, "<clinit>".into(), "()V".into())) {
                    seeds.push(init);
                }
            }
        } else {
            missing_roots.push(root.clone());
        }
    }
    let startup_seeds = startup;
    let main_seeds = main;
    let startup = reachable(&graph, &startup_seeds);
    let main = reachable(&graph, &main_seeds);
    for m in &mut methods {
        m.conservative_startup_reachable = startup[m.id];
        m.conservative_main_reachable = main[m.id];
    }
    let mut groups = BTreeMap::<(String, String), Group>::new();
    for m in &methods {
        for p in &m.problems {
            let group = groups
                .entry((p.category.clone(), p.target.clone()))
                .or_insert_with(|| Group {
                    category: p.category.clone(),
                    target: p.target.clone(),
                    occurrences: 0,
                    affected_methods: vec![],
                    startup_methods: 0,
                    main_methods: 0,
                    examples: vec![],
                });
            group.occurrences += 1;
            if group.affected_methods.last() != Some(&m.id) {
                group.affected_methods.push(m.id);
                group.startup_methods += usize::from(startup[m.id]);
                group.main_methods += usize::from(main[m.id]);
                if group.examples.len() < 6 {
                    group.examples.push(format!(
                        "{}.{}{}",
                        m.symbol.owner, m.symbol.name, m.symbol.descriptor
                    ));
                }
            }
        }
    }
    let groups = groups.into_values().collect::<Vec<_>>();
    let parts = components(&graph);
    let mut batch_ids = vec![0; methods.len()];
    for (id, part) in parts.iter().enumerate() {
        for &method in part {
            batch_ids[method] = id;
        }
    }
    let batches = parts
        .into_iter()
        .enumerate()
        .map(|(id, part)| {
            let dependencies = part
                .iter()
                .flat_map(|m| graph[*m].iter().map(|target| batch_ids[*target]))
                .filter(|target| *target != id)
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect();
            let blocked = part.iter().any(|m| {
                methods[*m].kind == "native_compatibility"
                    || methods[*m].problems.iter().any(|p| {
                        matches!(
                            p.category.as_str(),
                            "bytecode_structure"
                                | "legacy_subroutine"
                                | "vm_owned_layout"
                                | "opaque_field_layout"
                                | "bootstrap_compatibility"
                        )
                    })
            });
            Batch {
                id,
                dependency_batches: dependencies,
                stage: if blocked {
                    "compatibility_required"
                } else {
                    "pending_type_layout_and_codegen"
                }
                .into(),
                startup_priority: part.iter().any(|m| startup[*m]),
                main_priority: part.iter().any(|m| main[*m]),
                method_ids: part,
            }
        })
        .collect::<Vec<_>>();
    eprintln!(
        "Planned {} dependency batches and {} compatibility groups; emitting no assembly",
        batches.len(),
        groups.len()
    );
    fs::create_dir_all(output)?;
    let identity = files::digest_bytes(&serde_json::to_vec(&(
        1,
        &inputs.fingerprint,
        &base.fingerprint(),
        files::digest(&std::env::current_exe()?)?,
    ))?)
    .sha256;
    let mut artifacts = BTreeMap::new();
    artifacts.insert(
        "classes".into(),
        write_jsonl(&output.join("classes.jsonl"), &classes)?,
    );
    artifacts.insert(
        "methods".into(),
        write_jsonl(&output.join("methods.jsonl"), &methods)?,
    );
    artifacts.insert(
        "compatibility".into(),
        write_jsonl(&output.join("compatibility.jsonl"), &groups)?,
    );
    artifacts.insert(
        "batches".into(),
        write_jsonl(&output.join("batches.jsonl"), &batches)?,
    );
    artifacts.insert(
        "dependencies".into(),
        write_jsonl(&output.join("dependencies.jsonl"), graph.iter().enumerate().map(|(id, dependencies)|
            serde_json::json!({"method_id":id,"dependencies":dependencies})
        ))?,
    );
    artifacts.insert(
        "opcodes".into(),
        write_jsonl(
            &output.join("opcodes.jsonl"),
            opcodes
                .iter()
                .map(|(opcode, count)| serde_json::json!({"opcode":opcode,"instructions":count})),
        )?,
    );
    let summary = Summary {
        schema: 1,
        mode: "inventory_and_plan_only",
        input_fingerprint: inputs.fingerprint.clone(),
        jdk_fingerprint: base.fingerprint().into(),
        planner_fingerprint: identity,
        game_version: inputs.game_version.clone(),
        side: inputs.side.name().into(),
        workers,
        application_classes: jobs.iter().filter(|(jdk, _)| !*jdk).count(),
        java_base_classes: jobs
            .iter()
            .filter(|(_, origin)| origin.source_id == "jdk:java.base")
            .count(),
        additional_system_classes: jobs
            .iter()
            .filter(|(jdk, origin)| *jdk && origin.source_id != "jdk:java.base")
            .count(),
        system_classes: jobs.iter().filter(|(jdk, _)| *jdk).count(),
        shadowed_application_classes: shadowed,
        classes: classes.len(),
        class_parse_failures: classes.iter().filter(|c| c.parse_error.is_some()).count(),
        methods: methods.len(),
        java_methods: methods.iter().filter(|m| m.code_sha256.is_some()).count(),
        native_methods: methods.iter().filter(|m| m.access & 0x100 != 0).count(),
        native_binding_candidates: methods
            .iter()
            .filter(|m| m.kind == "native_binding_candidate")
            .count(),
        native_without_catalog_entry: methods
            .iter()
            .filter(|m| m.kind == "native_compatibility")
            .count(),
        abstract_methods: methods.iter().filter(|m| m.access & 0x400 != 0).count(),
        structurally_scanned_java_methods: methods
            .iter()
            .filter(|m| m.structural_scan_complete)
            .count(),
        compatibility_groups: groups.len(),
        conservative_startup_methods: startup.iter().filter(|v| **v).count(),
        conservative_main_methods: main.iter().filter(|v| **v).count(),
        batches: batches.len(),
        unresolved_symbolic_calls: unresolved,
        dependency_edges: graph.iter().map(Vec::len).sum(),
        startup_seed_methods: startup_seeds,
        main_seed_methods: main_seeds,
        virtual_dispatch_overapproximated: true,
        reflection_and_other_jdk_modules_require_further_resolution: true,
        native_catalog_is_complete: false,
        type_layout_and_link_verified: false,
        compiled_methods: 0,
        game_started: false,
        world_created: false,
        full_game_ready: false,
        roots,
        missing_roots,
        artifacts,
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
    fn inventory_continues_after_native_and_malformed_method() {
        fn utf(bytes: &mut Vec<u8>, value: &str) {
            bytes.push(1);
            bytes.extend((value.len() as u16).to_be_bytes());
            bytes.extend(value.as_bytes());
        }
        let mut bytes = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 10];
        utf(&mut bytes, "p/Plan");
        bytes.extend([7, 0, 1]);
        utf(&mut bytes, "java/lang/Object");
        bytes.extend([7, 0, 3]);
        for name in ["first", "()V", "Code", "broken", "last"] {
            utf(&mut bytes, name);
        }
        for value in [0x21u16, 2, 4, 0, 0, 3, 0x109, 5, 6, 0] {
            bytes.extend(value.to_be_bytes());
        }
        for (name, opcode) in [(8u16, 0xcau8), (9, 0xb1)] {
            for value in [9u16, name, 6, 1, 7] {
                bytes.extend(value.to_be_bytes());
            }
            bytes.extend(13u32.to_be_bytes());
            bytes.extend([0, 0, 0, 0, 0, 0, 0, 1, opcode, 0, 0, 0, 0]);
        }
        bytes.extend([0, 0]);
        let scanned = scan_class(
            &bytes,
            ClassOrigin {
                loader: "vanilla-application".into(),
                binary_name: "p.Plan".into(),
                source_id: "fixture".into(),
                jar_entry: "p/Plan.class".into(),
                java_class_major: 65,
                sha256: files::digest_bytes(&bytes).sha256,
                generated: None,
            },
            0,
        );
        assert!(scanned.class.parse_error.is_none());
        assert_eq!(scanned.methods.len(), 3);
        assert_eq!(
            scanned.methods[0].problems[0].category,
            "native_without_catalog_entry"
        );
        assert_eq!(
            scanned.methods[1].problems[0].category,
            "bytecode_structure"
        );
        assert!(scanned.methods[2].structural_scan_complete);
        assert!(
            scanned
                .methods
                .iter()
                .all(|m| !m.assembly_emitted && !m.type_layout_and_link_verified)
        );
    }
    #[test]
    fn constructors_are_not_inherited_during_inventory_resolution() {
        let parents = vec![vec![], vec![0]];
        let members = BTreeMap::from([((0, "<init>".into(), "()V".into()), 0)]);
        assert_eq!(resolve_method(1, "<init>", "()V", &parents, &members), None);
    }
    #[test]
    fn cycles_form_one_dependency_batch_and_dependencies_come_first() {
        let graph = vec![vec![1], vec![2], vec![1, 3], vec![]];
        let parts = components(&graph);
        assert_eq!(parts, vec![vec![3], vec![1, 2], vec![0]]);
        assert_eq!(reachable(&graph, &[0]), vec![true; 4]);
    }
    #[test]
    fn native_inventory_does_not_claim_unknown_bindings() {
        assert!(native_candidate(
            "jdk/internal/misc/Unsafe",
            "fullFence",
            "()V"
        ));
        assert!(!native_candidate(
            "jdk/internal/misc/Unsafe",
            "getReferenceVolatile",
            "(Ljava/lang/Object;J)Ljava/lang/Object;"
        ));
    }
    #[test]
    fn parent_first_identity_does_not_merge_application_definitions() {
        let index = BTreeMap::from([
            (("bootstrap".into(), "java/lang/Object".into()), 0),
            (("a".into(), "p/C".into()), 1),
            (("b".into(), "p/C".into()), 2),
        ]);
        let packages = Packages::new();
        assert_eq!(class_lookup(&index, &packages, "a", "p/C"), Some(1));
        assert_eq!(class_lookup(&index, &packages, "b", "p/C"), Some(2));
        assert_eq!(
            class_lookup(&index, &packages, "b", "java/lang/Object"),
            Some(0)
        );
    }
}
