//! Closed-input linking, named objects and interface dispatch. Execution is MASM.
//! Source-verified application/java.base hierarchies use complete physical layouts
//! and per-type field maps. Unsupported JDK/native/runtime operations stay gated.
use super::{
    assertions, cds, class_initialization,
    classfile::{ClassFile, Method, NumericConstant},
    concat, dispatch, field_maps, file_descriptors, file_streams, frames, hierarchy, lambdas,
    managed, mirrors, modules, monitors, nests, numeric, resources, runtime_types, string_join,
    string_values, throwables, types, unwind, vm,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    path::{Path, PathBuf},
};

// Closed vanilla graphs exceed the early subset's 1024-method budget. Runtime
// method IDs are DWORDs; shadow-frame tables allow 262144 rows independently.
const MAX_LINKED_CLASSES: usize = 8192;
const MAX_LINKED_METHODS: usize = 65536;

#[derive(Debug, Serialize, Deserialize)]
pub struct Source {
    pub class_name: String,
    pub path: PathBuf,
    pub digest: files::FileDigest,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub origin: Option<crate::bytecode::ClassOrigin>,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Symbol {
    pub id: usize,
    pub class_name: String,
    pub method: String,
    pub descriptor: String,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct Program {
    pub schema: u32,
    pub backend: String,
    pub entry_id: usize,
    pub input_fingerprint: String,
    pub sources: Vec<Source>,
    pub symbols: Vec<Symbol>,
    pub classes: Vec<ClassState>,
    pub object_layouts: Vec<ProgramObjectLayout>,
    pub string_literals: Vec<StringLiteral>,
    pub bootstrap_string_runtime: bool,
    pub bootstrap_string_abi: Option<u32>,
    pub concat_plans: Vec<concat::Plan>,
    #[serde(default)]
    pub lambda_sites: Vec<lambdas::Plan>,
    pub record_sites: Vec<super::records::Binding>,
    #[serde(default)]
    pub null_guards: bool,
    #[serde(default)]
    pub monitor_methods: Vec<monitors::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub monitor_notifications: Vec<monitors::Notification>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_resources: Option<super::runtime_resources::Plan>,
    #[serde(default)]
    pub resources: Option<resources::Plan>,
    #[serde(default)]
    pub string_join_plans: Vec<string_join::Plan>,
    #[serde(default)]
    pub string_value_bindings: Vec<string_values::Binding>,
    #[serde(default)]
    pub primitive_class_bindings: Vec<mirrors::PrimitiveBinding>,
    pub dynamic_string_runtime: bool,
    pub runtime_type_bindings: Vec<runtime_types::Binding>,
    pub runtime_type_map_abi: Option<u32>,
    #[serde(default)]
    pub covariant_reference_arrays: bool,
    pub reference_joins: Vec<Vec<usize>>,
    #[serde(default)]
    pub interface_dispatch: Vec<dispatch::Site>,
    #[serde(default)]
    pub interface_dispatch_abi: Option<u32>,
    #[serde(default)]
    pub field_maps: Vec<field_maps::Map>,
    pub mirror_types: Vec<types::Type>,
    pub mirror_name_literals: Vec<usize>,
    pub bootstrap_mirror_abi: Option<u32>,
    #[serde(default)]
    pub assertion_policy: Option<assertions::Policy>,
    #[serde(default)]
    pub vm_bindings: Vec<vm::Binding>,
    #[serde(default)]
    pub cds_profile: Option<cds::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub file_descriptors: Option<file_descriptors::Plan>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub nest_access: Vec<nests::Proof>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub constant_class_initialization: Vec<class_initialization::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub file_streams: Vec<file_streams::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub initializer_source_abi: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub java_frames: Option<frames::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub throwables: Option<throwables::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub exception_runtime: Option<unwind::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub string_case: Option<super::string_case::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub constructor_entry: Option<super::constructor_entries::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub thread_bootstrap: Option<super::thread_bootstrap::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub access_context: Option<super::access_context::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub platform_properties: Option<super::system_properties::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub vm_properties: Option<super::vm_properties::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub class_queries: Option<super::class_queries::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub shutdown: Option<super::shutdown::Plan>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub string_concat_api: Vec<super::string_concat_api::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub string_replace: Vec<super::string_replace::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub literal_regex_replacements: Vec<super::literal_regex::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub string_chars: Vec<super::string_chars::Binding>,
    pub string_getchars: Vec<super::string_getchars::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub string_construction: Vec<super::string_construction::Binding>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub string_lowercase: Option<super::string_lowercase::Plan>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub string_split: Option<super::string_split::Plan>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reflect_new: Option<super::reflect_new::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reflected_constructors: Option<super::reflect_constructors::Plan>,
    pub reflected_fields: Option<super::reflect_fields::Plan>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub class_for_name: Option<super::class_for_name::Plan>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub string_prefix: Vec<super::string_prefix::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub array_clones: Vec<super::array_clone::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub protected_constructors: Vec<super::protected_constructors::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub vm_registration: Vec<super::vm_registration::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub signal_lookup_bindings: Vec<super::signals::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub signal_natives: Vec<super::signal_natives::Binding>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub windows_startup: Option<super::windows_startup::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub class_loaders: Option<super::class_loaders::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reflection_arrays: Option<super::reflection_arrays::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scoped_memory: Option<super::scoped_memory::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub winnt_file_system: Option<super::winnt_file_system::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub thread_natives: Option<super::thread_natives::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub unsafe_bootstrap: Option<super::unsafe_bootstrap::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub typed_arrays: Option<super::typed_arrays::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub system_startup: Option<super::system_startup::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub system_streams: Option<super::system_streams::Plan>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub identity_hashes: Vec<super::identity_hash::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub hex_strings: Vec<super::hex_strings::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub string_storage: Vec<super::string_storage::Binding>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub builder_snapshot: Option<super::builder_snapshot::Plan>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub bitcasts: Vec<super::bitcasts::Binding>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub jdk_bridges: Vec<super::jdk_bridges::Binding>,
    #[serde(default)]
    pub module_plan: Option<modules::Plan>,
    pub metadata_input_fingerprint: Option<String>,
    pub edges: Vec<(usize, usize)>,
    pub compilation: managed::Compilation,
    #[serde(default)]
    pub volatile_accesses: bool,
    pub full_game_ready: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ProgramObjectLayout {
    pub class_id: usize,
    pub class_name: String,
    pub layout: numeric::ObjectLayout,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct StringLiteral {
    pub id: usize,
    pub utf16: Vec<u16>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ClassState {
    pub id: usize,
    pub name: String,
    pub initializer: Option<usize>,
    pub fields: Vec<StaticField>,
    #[serde(default)]
    pub initialization_dependencies: Vec<usize>,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct StaticField {
    pub index: usize,
    pub name: String,
    pub descriptor: String,
    pub initial_bits: String,
    pub reference: bool,
    pub initial_string: Option<usize>,
}

#[derive(Debug, Serialize)]
pub struct LockedProgram {
    pub schema: u32,
    pub input_fingerprint: String,
    pub origins: Vec<crate::bytecode::ClassOrigin>,
    pub program: Program,
}

pub fn compile_locked(
    inputs: &crate::lock::InputLock,
    entry_class: &str,
    method: &str,
    descriptor: Option<&str>,
    output: &Path,
    assemble: bool,
) -> Result<LockedProgram> {
    compile_locked_with_metadata(
        inputs,
        entry_class,
        method,
        descriptor,
        output,
        assemble,
        None,
    )
}
pub fn compile_locked_with_metadata(
    inputs: &crate::lock::InputLock,
    entry_class: &str,
    method: &str,
    descriptor: Option<&str>,
    output: &Path,
    assemble: bool,
    jdk_base: Option<&Path>,
) -> Result<LockedProgram> {
    compile_locked_with_assertions(
        inputs,
        entry_class,
        method,
        descriptor,
        output,
        assemble,
        jdk_base,
        assertions::Policy::default(),
    )
}
#[allow(clippy::too_many_arguments)]
pub fn compile_locked_with_assertions(
    inputs: &crate::lock::InputLock,
    entry_class: &str,
    method: &str,
    descriptor: Option<&str>,
    output: &Path,
    assemble: bool,
    jdk_base: Option<&Path>,
    assertion_policy: assertions::Policy,
) -> Result<LockedProgram> {
    compile_locked_with_runtime_metadata(
        inputs,
        entry_class,
        method,
        descriptor,
        output,
        assemble,
        jdk_base,
        assertion_policy,
        None,
    )
}
#[allow(clippy::too_many_arguments)]
pub fn compile_locked_with_runtime_metadata(
    inputs: &crate::lock::InputLock,
    entry_class: &str,
    method: &str,
    descriptor: Option<&str>,
    output: &Path,
    assemble: bool,
    jdk_base: Option<&Path>,
    assertion_policy: assertions::Policy,
    jdk_modules: Option<&Path>,
) -> Result<LockedProgram> {
    compile_locked_with_vm_profile(
        inputs,
        entry_class,
        method,
        descriptor,
        output,
        assemble,
        jdk_base,
        assertion_policy,
        jdk_modules,
        None,
        false,
        false,
    )
}
#[allow(clippy::too_many_arguments)]
pub fn compile_locked_with_vm_profile(
    inputs: &crate::lock::InputLock,
    entry_class: &str,
    method: &str,
    descriptor: Option<&str>,
    output: &Path,
    assemble: bool,
    jdk_base: Option<&Path>,
    assertion_policy: assertions::Policy,
    jdk_modules: Option<&Path>,
    vm_profile: Option<&super::vm_properties::Profile>,
    primordial: bool,
    module_bootstrap: bool,
) -> Result<LockedProgram> {
    ensure!(
        !module_bootstrap
            || (jdk_base.is_some()
                && !primordial
                && super::module_objects::bootstrap_entry(entry_class, method, descriptor)),
        "Module VM bootstrap requires the exact original unnamed constructor and java.base metadata"
    );
    ensure!(
        !primordial
            || (jdk_base.is_some()
                && super::thread_bootstrap::entry(entry_class, method, descriptor)),
        "Primordial VM entry requires the exact original Thread attaching constructor and java.base metadata"
    );
    ensure!(
        vm_profile.is_none() || jdk_base.is_some(),
        "VM profile requires verified java.base metadata"
    );
    ensure!(
        jdk_modules.is_none() || jdk_base.is_some(),
        "Boot module metadata requires java.base inputs"
    );
    if let Some(manifest) = jdk_modules {
        crate::boot_modules::Snapshot::read(manifest, inputs)?;
    }
    ensure!(
        jdk_base.is_some() || assertion_policy == assertions::Policy::default(),
        "Assertion configuration requires verified java.base metadata"
    );
    use crate::bytecode::{BytecodeProvider, VanillaBytecodeProvider};
    let snapshot = if jdk_base.is_none() {
        Some(VanillaBytecodeProvider { inputs }.snapshot()?)
    } else {
        None
    };
    let entry_class = entry_class.replace('.', "/");
    let metadata_provider = jdk_base
        .map(|manifest| types::VanillaTypes::new(inputs, manifest))
        .transpose()?
        .map(|base| lambdas::Provider { base });
    let mut registry = metadata_provider
        .as_ref()
        .map(|provider| types::Registry::new(provider));
    let loaded = discover_static_profiled(
        |loader, name| {
            if let Some(provider) = &metadata_provider {
                return types::TypeProvider::resolve(provider, loader, name);
            }
            let origin=snapshot.as_ref().unwrap().classes.get(&name.replace('/',"."))
            .with_context(|| format!("Class {name} is absent from the locked application classpath; bootstrap/JDK or other providers may be required"))?;
            Ok((origin.read(inputs)?, origin.clone()))
        },
        &entry_class,
        method,
        descriptor,
        registry.as_mut(),
        primordial,
        module_bootstrap,
    )?;
    // Cache only the verified closure, never the entire client/JDK set. No game starts.
    let source_dir = output.join("classes");
    fs::create_dir_all(&source_dir)?;
    let mut paths = Vec::new();
    let mut origins = Vec::new();
    for (index, (_, bytes, origin)) in loaded.into_iter().enumerate() {
        let path = source_dir.join(format!("{index:04}.class"));
        files::write_atomic(&path, &bytes)?;
        paths.push(path);
        origins.push(origin);
    }
    let program = compile_with_metadata(
        &paths,
        &entry_class,
        method,
        descriptor,
        output,
        assemble,
        jdk_base.map(|manifest| MetadataContext {
            inputs,
            manifest,
            explicit_sources: false,
            assertions: assertion_policy,
            module_manifest: jdk_modules,
            resource_jars: &[],
            vm_profile,
            primordial,
            module_bootstrap,
            class_lookup_fixture: false,
        }),
    )?;
    for source in &program.sources {
        let origin = origins
            .iter()
            .find(|origin| origin.binary_name == source.class_name.replace('/', "."))
            .context("Compiled class lost its locked origin")?;
        ensure!(
            source.digest.sha256 == origin.sha256,
            "Extracted class changed between discovery and compilation"
        );
    }
    let result = LockedProgram {
        schema: 1,
        input_fingerprint: inputs.fingerprint.clone(),
        origins,
        program,
    };
    files::write_atomic(
        &output.join("locked-program.json"),
        &serde_json::to_vec_pretty(&result)?,
    )?;
    Ok(result)
}

type LoadedClass = (ClassFile, Vec<u8>, crate::bytecode::ClassOrigin);
#[cfg(test)]
fn discover_static(
    load: impl FnMut(&str, &str) -> Result<(Vec<u8>, crate::bytecode::ClassOrigin)>,
    entry_class: &str,
    method: &str,
    descriptor: Option<&str>,
    registry: Option<&mut types::Registry<'_>>,
) -> Result<Vec<LoadedClass>> {
    discover_static_profiled(
        load,
        entry_class,
        method,
        descriptor,
        registry,
        false,
        false,
    )
}
fn discover_static_profiled(
    load: impl FnMut(&str, &str) -> Result<(Vec<u8>, crate::bytecode::ClassOrigin)>,
    entry_class: &str,
    method: &str,
    descriptor: Option<&str>,
    registry: Option<&mut types::Registry<'_>>,
    primordial: bool,
    module_bootstrap: bool,
) -> Result<Vec<LoadedClass>> {
    discover_with_definitions(
        load,
        entry_class,
        method,
        descriptor,
        registry,
        "vanilla-application",
        &[],
        primordial,
        module_bootstrap,
        false,
    )
}
#[allow(clippy::too_many_arguments)]
fn discover_with_definitions(
    mut load: impl FnMut(&str, &str) -> Result<(Vec<u8>, crate::bytecode::ClassOrigin)>,
    entry_class: &str,
    method: &str,
    descriptor: Option<&str>,
    mut registry: Option<&mut types::Registry<'_>>,
    entry_loader: &str,
    definitions: &[(String, String)],
    primordial: bool,
    module_bootstrap: bool,
    lookup_fixture: bool,
) -> Result<Vec<LoadedClass>> {
    let metadata = registry.is_some();
    let system_startup = super::system_startup::Plan::prepare(
        registry.as_deref_mut(),
        entry_class,
        method,
        descriptor,
    )?;
    use std::{cell::RefCell, collections::VecDeque};
    struct Request {
        loader: String,
        owner: String,
        method: String,
        descriptor: Option<String>,
        requested_by: String,
    }
    #[derive(Default)]
    struct Recorder(
        RefCell<Vec<(String, String, String)>>,
        bool,
        RefCell<Vec<(String, String, String, bool)>>,
        Option<(String, String, u16)>,
        bool,
        RefCell<Vec<String>>,
    );
    impl Recorder {
        fn exception_bootstrap(&self) -> Result<()> {
            ensure!(self.1, "Context32 exceptions require verified java.base");
            let mut pending = self.0.borrow_mut();
            for (_, name) in unwind::KINDS {
                pending.push(((*name).into(), String::new(), "()V".into()));
            }
            pending.push(("java/lang/Error".into(), "@definition".into(), "()V".into()));
            pending.push((
                "java/lang/Throwable".into(),
                "fillInStackTrace".into(),
                "()Ljava/lang/Throwable;".into(),
            ));
            Ok(())
        }
        fn descriptor(&self, descriptor: &str) -> Result<numeric::Signature> {
            numeric::Signature::parse_with(descriptor, &mut |name, array| {
                if name == "java/lang/String" {
                    return Ok(if array {
                        numeric::Type::BootstrapStringArray
                    } else {
                        numeric::Type::BootstrapString
                    });
                }
                if name == "java/lang/Class" {
                    return Ok(if array {
                        numeric::Type::BootstrapClassArray
                    } else {
                        numeric::Type::BootstrapClass
                    });
                }
                if self.1 {
                    return Ok(numeric::Type::MetadataReference(0));
                }
                self.0
                    .borrow_mut()
                    .push((name.into(), String::new(), "()V".into()));
                Ok(if array {
                    numeric::Type::LinkedObjectArray(0)
                } else {
                    numeric::Type::LinkedObject(0)
                })
            })
        }
    }
    impl numeric::StaticLinker for Recorder {
        fn winfs_init(&self, caller: &ClassFile, _: u16) -> Result<(usize, usize)> {
            ensure!(
                self.1 && caller.name == super::winnt_file_system::OWNER,
                "WinNTFileSystem.initIDs is private to original WinNTFileSystem source"
            );
            for name in [
                super::winnt_file_system::OWNER,
                super::winnt_file_system::FILE,
            ] {
                self.0
                    .borrow_mut()
                    .push((name.into(), String::new(), "()V".into()));
            }
            self.exception_bootstrap()?;
            Ok((0, 0))
        }
        fn scoped_register(&self, caller: &ClassFile, _: u16) -> Result<usize> {
            ensure!(
                self.1 && caller.name == super::scoped_memory::OWNER,
                "ScopedMemoryAccess.registerNatives is private to its original source"
            );
            self.0.borrow_mut().push((
                super::scoped_memory::OWNER.into(),
                String::new(),
                "()V".into(),
            ));
            self.exception_bootstrap()?;
            Ok(0)
        }
        fn reflect_array(
            &self,
            caller: &ClassFile,
            _: u16,
            op: super::reflection_arrays::Operation,
        ) -> Result<(numeric::Signature, usize)> {
            ensure!(
                self.1 && caller.name == super::reflection_arrays::OWNER,
                "Reflection array allocation native is private to original Array source"
            );
            self.0.borrow_mut().push((
                super::reflection_arrays::OWNER.into(),
                String::new(),
                "()V".into(),
            ));
            self.exception_bootstrap()?;
            Ok((self.descriptor(op.descriptor())?, 0))
        }
        fn class_loader_register(&self, caller: &ClassFile, _: u16) -> Result<usize> {
            ensure!(
                self.1 && caller.name == super::class_loaders::LOADER,
                "ClassLoader.registerNatives is private to original ClassLoader source"
            );
            self.0.borrow_mut().push((
                super::class_loaders::LOADER.into(),
                String::new(),
                "()V".into(),
            ));
            self.exception_bootstrap()?;
            Ok(0)
        }
        fn class_loader_field(&self, caller: &ClassFile, _: u16) -> Result<numeric::Signature> {
            ensure!(
                self.1
                    && (caller.name == super::class_loaders::OWNER
                        || self
                            .3
                            .as_ref()
                            .is_some_and(|(host, _, _)| host == super::class_loaders::OWNER)),
                "Class.classLoader is private to original Class code"
            );
            self.0.borrow_mut().push((
                super::class_loaders::LOADER.into(),
                "@definition".into(),
                "()V".into(),
            ));
            self.exception_bootstrap()?;
            let mut sig = self.descriptor("()Ljava/lang/ClassLoader;")?;
            sig.arguments.push(numeric::Type::BootstrapClass);
            Ok(sig)
        }
        fn windows_error_mode(&self, caller: &ClassFile, _: u16) -> Result<usize> {
            ensure!(
                self.1 && caller.name == super::windows_startup::OWNER,
                "Win32ErrorMode native is private to its original caller"
            );
            self.0.borrow_mut().push((
                super::windows_startup::OWNER.into(),
                String::new(),
                "()V".into(),
            ));
            Ok(0)
        }
        fn signal_control(
            &self,
            caller: &ClassFile,
            _: u16,
            _: super::signal_natives::Operation,
        ) -> Result<usize> {
            ensure!(
                self.1 && caller.name == super::signals::OWNER,
                "Signal control native is private to its original Signal caller"
            );
            self.0
                .borrow_mut()
                .push((super::signals::OWNER.into(), String::new(), "()V".into()));
            self.exception_bootstrap()?;
            Ok(0)
        }
        fn access_context(
            &self,
            caller: &ClassFile,
            _: u16,
            op: super::access_context::Operation,
        ) -> Result<(numeric::Signature, usize)> {
            ensure!(self.1, "Access contexts require java.base");
            if matches!(
                op,
                super::access_context::Operation::Stack
                    | super::access_context::Operation::Materialize
            ) {
                ensure!(
                    caller.name == super::access_context::OWNER,
                    "Private AccessController native requires its original caller"
                );
            }
            for owner in [
                super::access_context::OWNER,
                super::access_context::CONTEXT,
                "java/lang/Thread",
            ] {
                self.0
                    .borrow_mut()
                    .push((owner.into(), String::new(), "()V".into()));
            }
            self.0.borrow_mut().push((
                super::access_context::DOMAIN.into(),
                "@definition".into(),
                "()V".into(),
            ));
            if op == super::access_context::Operation::CallerClass {
                self.0.borrow_mut().push((
                    super::access_context::REFLECTION.into(),
                    String::new(),
                    "()V".into(),
                ));
            }
            self.exception_bootstrap()?;
            Ok((self.descriptor(op.descriptor())?, 0))
        }
        fn primordial_body(&self, class: &ClassFile, code: &super::classfile::Code) -> bool {
            self.4 && super::thread_bootstrap::applies(class, code)
        }
        fn unsafe_native(
            &self,
            caller: &ClassFile,
            _: u16,
            op: super::unsafe_bootstrap::Operation,
        ) -> Result<(numeric::Signature, usize)> {
            ensure!(self.1, "Unsafe natives require verified java.base");
            if op.private() {
                ensure!(
                    caller.name == super::unsafe_bootstrap::OWNER,
                    "Unsafe private native requires its original caller"
                );
            }
            self.0.borrow_mut().push((
                super::unsafe_bootstrap::OWNER.into(),
                String::new(),
                "()V".into(),
            ));
            if op.field_metadata() {
                self.exception_bootstrap()?;
                self.0.borrow_mut().push((
                    super::reflect_fields::OWNER.into(),
                    "@definition".into(),
                    "()V".into(),
                ));
            }
            let mut sig = self.descriptor(op.descriptor())?;
            if op != super::unsafe_bootstrap::Operation::Register {
                sig.arguments.insert(0, numeric::Type::LinkedObject(0));
            }
            Ok((sig, 0))
        }
        fn thread_native(
            &self,
            caller: &ClassFile,
            _: u16,
            op: super::thread_natives::Operation,
        ) -> Result<usize> {
            ensure!(
                self.1,
                "Thread native discovery requires verified java.base"
            );
            if matches!(
                op,
                super::thread_natives::Operation::Register
                    | super::thread_natives::Operation::Yield
                    | super::thread_natives::Operation::Materialize
            ) {
                ensure!(
                    caller.name == super::thread_natives::OWNER,
                    "Thread private native is restricted to its original Thread caller"
                );
            }
            self.0.borrow_mut().push((
                super::thread_natives::OWNER.into(),
                String::new(),
                "()V".into(),
            ));
            Ok(0)
        }
        fn signal_lookup(&self, caller: &ClassFile, _: u16) -> Result<usize> {
            ensure!(
                self.1 && caller.name == super::signals::OWNER,
                "Signal.findSignal0 is private to the original Signal caller"
            );
            self.0
                .borrow_mut()
                .push((super::signals::OWNER.into(), String::new(), "()V".into()));
            Ok(0)
        }
        fn string_prefix(&self, _: &ClassFile, _: u16) -> Result<numeric::Signature> {
            ensure!(
                self.1,
                "String prefix discovery requires verified java.base"
            );
            Ok(super::string_prefix::signature())
        }
        fn system_stream(
            &self,
            caller: &ClassFile,
            _: u16,
            op: super::system_streams::Operation,
        ) -> Result<(numeric::Signature, usize)> {
            ensure!(
                self.1 && caller.name == "java/lang/System",
                "System stream setters are private to the original System caller"
            );
            self.0
                .borrow_mut()
                .push(("java/lang/System".into(), String::new(), "()V".into()));
            Ok((self.descriptor(op.descriptor())?, 0))
        }
        fn typed_array(
            &self,
            _: &ClassFile,
            descriptor: &str,
            dimensions: u8,
        ) -> Result<(usize, numeric::Type)> {
            ensure!(self.1, "Typed array discovery requires metadata");
            super::typed_arrays::rank(descriptor, dimensions)?;
            Ok((0, numeric::Type::MetadataReference(0)))
        }
        fn vm_registration(
            &self,
            _: &ClassFile,
            _: u16,
            op: super::vm_registration::Operation,
        ) -> Result<usize> {
            ensure!(
                self.1,
                "VM registration discovery requires verified java.base"
            );
            self.0
                .borrow_mut()
                .push((op.owner().into(), String::new(), "()V".into()));
            Ok(0)
        }
        fn array_clone(&self, _: &ClassFile, _: u16) -> Result<(numeric::Signature, usize)> {
            ensure!(self.1, "Array clone discovery requires verified java.base");
            self.0.borrow_mut().push((
                "java/lang/Object".into(),
                "@definition".into(),
                "()V".into(),
            ));
            Ok((
                numeric::Signature {
                    arguments: vec![numeric::Type::MetadataReference(0)],
                    result: numeric::Type::MetadataReference(0),
                },
                0,
            ))
        }
        fn literal_regex_replace(
            &self,
            _: &ClassFile,
            _: u16,
            _: super::literal_regex::Proof,
        ) -> Result<numeric::Signature> {
            self.exception_bootstrap()?;
            Ok(super::literal_regex::signature())
        }
        fn string_replace(&self, _: &ClassFile, _: u16) -> Result<numeric::Signature> {
            ensure!(
                self.1,
                "String replacement discovery requires verified java.base"
            );
            Ok(super::string_replace::signature())
        }
        fn string_construction(&self, _: &ClassFile, _: u16, _: bool) -> Result<()> {
            self.exception_bootstrap()
        }
        fn class_for_name(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
            use super::jdk_bridges::Kind;
            let (o, n, d) = caller.method_reference(constant)?;
            let bootstrap_lookup = super::class_for_name::is_bootstrap_call(&o, &n, &d);
            ensure!(
                (bootstrap_lookup && caller.name == "java/lang/ClassLoader")
                    || caller.name == "java/lang/Class"
                    || [Kind::ClassForNameCaller, Kind::ClassForNameChecked]
                        .iter()
                        .any(|k| caller.name == k.class_name()),
                "Class.forName0 is private to its original Class caller"
            );
            self.exception_bootstrap()?;
            self.0.borrow_mut().push((
                super::class_loaders::LOADER.into(),
                "@definition".into(),
                "()V".into(),
            ));
            self.0.borrow_mut().push((
                caller.name.clone(),
                if bootstrap_lookup {
                    "@bootstrap-lookup"
                } else {
                    "@for-name"
                }
                .into(),
                "()V".into(),
            ));
            self.descriptor(if bootstrap_lookup {
                super::class_for_name::BOOTSTRAP_DESCRIPTOR
            } else {
                super::class_for_name::DESCRIPTOR
            })
        }
        fn reflected_field_filter(
            &self,
            _: &ClassFile,
            _: u16,
            _: super::field_filters::Proof,
        ) -> Result<numeric::Signature> {
            self.exception_bootstrap()?;
            for name in [super::reflect_fields::OWNER, super::field_filters::SET12] {
                self.0
                    .borrow_mut()
                    .push((name.into(), "@definition".into(), "()V".into()));
            }
            self.descriptor(super::field_filters::DESCRIPTOR)
        }
        fn reflected_field(
            &self,
            caller: &ClassFile,
            constant: u16,
            _: super::reflect_fields::Operation,
        ) -> Result<numeric::Signature> {
            self.exception_bootstrap()?;
            self.0.borrow_mut().push((
                super::reflect_fields::OWNER.into(),
                "@definition".into(),
                "()V".into(),
            ));
            let (o, _, d) = caller.method_reference(constant)?;
            self.descriptor(&format!("(L{o};{}", &d[1..]))
        }

        fn reflected_constructor(
            &self,
            caller: &ClassFile,
            constant: u16,
            op: super::reflect_constructors::Operation,
        ) -> Result<(usize, numeric::Signature)> {
            self.exception_bootstrap()?;
            self.0.borrow_mut().push((
                super::reflect_constructors::OWNER.into(),
                "@definition".into(),
                "()V".into(),
            ));
            self.0.borrow_mut().push((
                caller.name.clone(),
                "@reflect-constructors".into(),
                "()V".into(),
            ));
            let (o, _, d) = caller.method_reference(constant)?;
            let d = format!("(L{o};{}", &d[1..]);
            let _ = op;
            Ok((0, self.descriptor(&d)?))
        }
        fn reflect_new(&self, caller: &ClassFile, _: u16) -> Result<(usize, numeric::Signature)> {
            self.exception_bootstrap()?;
            self.0
                .borrow_mut()
                .push((caller.name.clone(), "@reflect-new".into(), "()V".into()));
            Ok((0, super::reflect_new::signature()))
        }
        fn string_split(&self, _: &ClassFile, _: u16) -> Result<numeric::Signature> {
            self.exception_bootstrap()?;
            ensure!(self.1, "String split discovery requires verified java.base");
            Ok(super::string_split::signature())
        }
        fn string_lowercase(&self, _: &ClassFile, _: u16) -> Result<numeric::Signature> {
            self.exception_bootstrap()?;
            for name in [
                super::string_lowercase::LOCALE,
                super::string_lowercase::BASE,
            ] {
                self.0
                    .borrow_mut()
                    .push((name.into(), "@definition".into(), "()V".into()));
            }
            let mut sig = self.descriptor(super::string_lowercase::DESCRIPTOR)?;
            sig.arguments.insert(0, numeric::Type::BootstrapString);
            Ok(sig)
        }
        fn string_chars(&self, _: &ClassFile, _: u16) -> Result<numeric::Signature> {
            ensure!(
                self.1,
                "String character copy discovery requires verified java.base"
            );
            Ok(super::string_chars::signature())
        }
        fn string_get_chars(&self, _: &ClassFile, _: u16) -> Result<()> {
            ensure!(self.1, "String.getChars requires verified java.base");
            self.exception_bootstrap()?;
            Ok(())
        }
        fn class_query(&self, _: &ClassFile, _: u16, _: super::class_queries::Kind) -> Result<()> {
            ensure!(self.1, "Class query discovery requires java.base");
            Ok(())
        }
        fn class_value_field(
            &self,
            caller: &ClassFile,
            constant: u16,
            write: bool,
        ) -> Result<numeric::Signature> {
            ensure!(
                caller.name == "java/lang/ClassValue",
                "ClassValue field requires original package caller"
            );
            self.exception_bootstrap()?;
            self.0.borrow_mut().push((
                super::class_queries::CLASS_VALUE_TYPE.into(),
                "@definition".into(),
                "()V".into(),
            ));
            self.class_query(
                caller,
                constant,
                if write {
                    super::class_queries::Kind::ClassValueStore
                } else {
                    super::class_queries::Kind::ClassValueLoad
                },
            )?;
            self.descriptor(super::class_queries::class_value_descriptor(write))
        }
        fn shutdown_native(
            &self,
            caller: &ClassFile,
            _: u16,
            op: super::shutdown::Operation,
        ) -> Result<(numeric::Signature, usize)> {
            ensure!(
                self.1
                    && caller
                        .name
                        .rsplit_once('/')
                        .is_some_and(|p| p.0 == "java/lang"),
                "Shutdown native requires original java.lang package caller"
            );
            self.exception_bootstrap()?;
            self.0
                .borrow_mut()
                .push((super::shutdown::OWNER.into(), String::new(), "()V".into()));
            Ok((op.signature(), 0))
        }
        fn jdk_bridge(
            &self,
            caller: &ClassFile,
            _: u16,
            kind: super::jdk_bridges::Kind,
        ) -> Result<(usize, numeric::Signature)> {
            ensure!(self.1, "JDK bridge discovery requires java.base");
            if kind.private_api() {
                use super::jdk_bridges::Kind;
                ensure!(
                    caller.name == kind.owner()
                        || [
                            Kind::ClassForName,
                            Kind::ClassForNameLoader,
                            Kind::ClassForNameCaller,
                            Kind::ClassForNameChecked
                        ]
                        .iter()
                        .any(|k| caller.name == k.class_name()),
                    "Private Class.forName helper requires its verified original Class caller"
                );
            }
            self.0.borrow_mut().push((
                kind.class_name(),
                kind.name().into(),
                kind.descriptor().into(),
            ));
            Ok((0, self.descriptor(kind.descriptor())?))
        }
        fn bitcast(
            &self,
            _: &ClassFile,
            _: u16,
            kind: super::bitcasts::Kind,
        ) -> Result<(numeric::Signature, usize)> {
            ensure!(self.1, "Bitcast discovery requires java.base");
            self.0
                .borrow_mut()
                .push((kind.owner().into(), String::new(), "()V".into()));
            Ok((kind.signature(), 0))
        }
        fn builder_snapshot(&self, _: &ClassFile, _: u16) -> Result<(numeric::Signature, usize)> {
            ensure!(self.1, "Builder snapshot discovery requires java.base");
            self.0.borrow_mut().push((
                super::builder_snapshot::OWNER.into(),
                String::new(),
                "()V".into(),
            ));
            Ok((
                numeric::Signature {
                    arguments: vec![numeric::Type::LinkedObject(0)],
                    result: numeric::Type::BootstrapString,
                },
                0,
            ))
        }
        fn string_storage(
            &self,
            caller: &ClassFile,
            _: u16,
            _: super::string_storage::Property,
        ) -> Result<u32> {
            ensure!(
                self.1 && caller.name.rsplit_once('/').map(|p| p.0) == Some("java/lang"),
                "String storage discovery requires original java.lang access"
            );
            Ok(0)
        }
        fn hex_string(
            &self,
            _: &ClassFile,
            _: u16,
            kind: super::hex_strings::Kind,
        ) -> Result<(numeric::Signature, usize)> {
            ensure!(self.1, "Hex string discovery requires java.base");
            self.0
                .borrow_mut()
                .push((kind.owner().into(), String::new(), "()V".into()));
            Ok((kind.signature(), 0))
        }
        fn identity_hash(&self, _: &ClassFile, _: u16) -> Result<numeric::Signature> {
            ensure!(
                self.1,
                "Identity hash discovery requires verified java.base"
            );
            self.descriptor("(Ljava/lang/Object;)I")
        }
        fn fixed_identity_hash(
            &self,
            caller: &ClassFile,
            constant: u16,
        ) -> Result<numeric::Signature> {
            ensure!(self.1, "Array hash discovery requires java.base");
            self.0.borrow_mut().push((
                "java/lang/Object".into(),
                "@definition".into(),
                "()V".into(),
            ));
            let (owner, _, _) = caller.method_reference(constant)?;
            let receiver = if owner.starts_with('[') {
                owner
            } else {
                format!("L{owner};")
            };
            self.descriptor(&format!("({receiver})I"))
        }
        fn string_concat_api(&self, _: &ClassFile, _: u16) -> Result<numeric::Signature> {
            ensure!(
                self.1,
                "String.concat discovery requires verified java.base"
            );
            Ok(super::string_concat_api::signature())
        }
        fn raw_properties(
            &self,
            _: &ClassFile,
            _: u16,
            _: super::system_properties::Operation,
        ) -> Result<(numeric::Signature, usize)> {
            ensure!(
                self.1,
                "Raw properties discovery requires verified java.base"
            );
            self.0.borrow_mut().push((
                super::system_properties::OWNER.into(),
                String::new(),
                "()V".into(),
            ));
            Ok((super::system_properties::Plan::signature(), 0))
        }
        fn string_case(&self, _: &ClassFile, _: u16) -> Result<()> {
            ensure!(
                self.1,
                "Unicode String comparison requires verified java.base"
            );
            Ok(())
        }
        fn exception_method(&self, _: &ClassFile, method: &Method) -> Result<()> {
            if unwind::required(method)? {
                self.exception_bootstrap()?;
            }
            Ok(())
        }
        fn runtime_resources(
            &self,
            _: &ClassFile,
            _: u16,
            op: super::runtime_resources::Operation,
        ) -> Result<numeric::Signature> {
            self.exception_bootstrap()?;
            self.0.borrow_mut().push((
                super::runtime_resources::OWNER.into(),
                "@definition".into(),
                "()V".into(),
            ));
            self.descriptor(&format!(
                "(Ljava/lang/Runtime;){}",
                if op == super::runtime_resources::Operation::AvailableProcessors {
                    "I"
                } else {
                    "J"
                }
            ))
        }
        fn monitor_notify(
            &self,
            caller: &ClassFile,
            constant: u16,
            _: bool,
        ) -> Result<numeric::Signature> {
            self.exception_bootstrap()?;
            let (owner, _, _) = caller.method_reference(constant)?;
            self.descriptor(&format!(
                "({})V",
                if owner.starts_with('[') {
                    owner
                } else {
                    format!("L{owner};")
                }
            ))
        }
        fn monitor_opcode(&self, _: &ClassFile) -> Result<()> {
            self.exception_bootstrap()
        }
        fn npe_message(&self, _: &ClassFile, _: u16) -> Result<numeric::Signature> {
            self.exception_bootstrap()?;
            self.descriptor("(Ljava/lang/NullPointerException;)Ljava/lang/String;")
        }
        fn throwable_fill(&self, _: &ClassFile, _: u16) -> Result<numeric::Signature> {
            ensure!(
                self.1,
                "Throwable native discovery requires original java.base"
            );
            self.0
                .borrow_mut()
                .push((throwables::OWNER.into(), String::new(), "()V".into()));
            self.descriptor("(Ljava/lang/Throwable;I)Ljava/lang/Throwable;")
        }
        fn stream_init(&self, caller: &ClassFile, constant: u16) -> Result<usize> {
            ensure!(
                self.1,
                "Stream native discovery requires verified java.base"
            );
            let (owner, _, _, _) = caller.static_method_reference(constant)?;
            self.0
                .borrow_mut()
                .push((owner, String::new(), "()V".into()));
            Ok(0)
        }
        fn constant_class_initialization(
            &self,
            _: &ClassFile,
            site: class_initialization::Site,
        ) -> Result<usize> {
            ensure!(
                self.1,
                "Constant Class initialization discovery requires verified java.base"
            );
            self.0
                .borrow_mut()
                .push((site.target, String::new(), "()V".into()));
            Ok(0)
        }
        fn file_descriptor(
            &self,
            _: &ClassFile,
            _: u16,
            _: file_descriptors::Operation,
        ) -> Result<usize> {
            ensure!(
                self.1,
                "Descriptor native discovery requires verified java.base"
            );
            self.0
                .borrow_mut()
                .push((file_descriptors::OWNER.into(), String::new(), "()V".into()));
            Ok(0)
        }
        fn cds(&self, _: &ClassFile, _: u16, _: cds::Operation) -> Result<usize> {
            ensure!(self.1, "CDS discovery requires verified java.base metadata");
            self.0
                .borrow_mut()
                .push((cds::OWNER.into(), String::new(), "()V".into()));
            Ok(0)
        }
        fn resource_stream(&self, _: &ClassFile) -> Result<resources::Link> {
            ensure!(self.1, "Class resources require verified metadata");
            self.0.borrow_mut().push((
                "java/io/ByteArrayInputStream".into(),
                "<init>".into(),
                "([B)V".into(),
            ));
            Ok(resources::Link {
                signature: numeric::Signature {
                    arguments: vec![
                        numeric::Type::BootstrapClass,
                        numeric::Type::BootstrapString,
                    ],
                    result: numeric::Type::MetadataReference(0),
                },
                class_id: 0,
                constructor: 0,
                caller: 0,
            })
        }
        fn method_monitor(&self, _: &ClassFile, method: &Method) -> Result<Option<usize>> {
            if method.access & 0x20 == 0 {
                return Ok(None);
            }
            ensure!(
                self.1 && !method.name.starts_with('<'),
                "Synchronized methods require verified metadata and ordinary methods"
            );
            Ok((method.access & 8 != 0).then_some(0))
        }
        fn interface_call(
            &self,
            caller: &ClassFile,
            constant: u16,
        ) -> Result<numeric::InterfaceLink> {
            ensure!(
                self.1,
                "Interface discovery requires verified hierarchy metadata"
            );
            let (owner, name, descriptor) = caller.interface_method_reference(constant)?;
            let mut signature = self.descriptor(&descriptor)?;
            signature
                .arguments
                .insert(0, numeric::Type::MetadataReference(0));
            signature.check_arguments()?;
            self.2.borrow_mut().push((owner, name, descriptor, true));
            Ok((0, signature, Vec::new(), Vec::new()))
        }
        fn string_join(
            &self,
            _: &ClassFile,
            _: u16,
            kind: string_join::Kind,
        ) -> Result<string_join::Link> {
            ensure!(
                self.1,
                "String.join discovery needs verified java.base metadata"
            );
            if kind == string_join::Kind::Replace {
                self.exception_bootstrap()?;
            }
            for (owner, name, descriptor) in kind.callbacks() {
                self.2
                    .borrow_mut()
                    .push((owner.into(), name.into(), descriptor.into(), true));
            }
            Ok(string_join::Link {
                id: 0,
                signature: self.descriptor(kind.invocation_descriptor())?,
                targets: vec![],
                owners: vec![],
            })
        }
        fn string_value(
            &self,
            caller: &ClassFile,
            constant: u16,
            kind: string_values::Kind,
        ) -> Result<string_values::Link> {
            ensure!(
                self.1,
                "Primitive String.valueOf discovery needs verified java.base metadata"
            );
            if let Some(owner) = kind.initialization_owner() {
                self.0
                    .borrow_mut()
                    .push((owner.into(), String::new(), "()V".into()));
            }
            if let Some(plan) = kind.concat() {
                Ok(string_values::Link::Concat(
                    self.concat(caller, constant, plan)?,
                    kind.signature(),
                    kind.initialization_owner().map(|_| 0),
                ))
            } else {
                Ok(string_values::Link::Boolean([0, 0]))
            }
        }
        fn inherited_virtual(
            &self,
            caller: &ClassFile,
            constant: u16,
        ) -> Result<Option<numeric::InterfaceLink>> {
            if !self.1 {
                return Ok(None);
            }
            let (owner, name, descriptor) = caller.method_reference(constant)?;
            let mut signature = self.descriptor(&descriptor)?;
            signature
                .arguments
                .insert(0, numeric::Type::MetadataReference(0));
            signature.check_arguments()?;
            self.2.borrow_mut().push((owner, name, descriptor, false));
            Ok(Some((0, signature, Vec::new(), Vec::new())))
        }
        fn special_call(
            &self,
            caller: &ClassFile,
            constant: u16,
        ) -> Result<Option<numeric::InterfaceLink>> {
            if !self.1 {
                return Ok(None);
            }
            let (owner, name, descriptor, interface) = caller.special_method_reference(constant)?;
            let (lookup_name, lookup_super, lookup_access) = self.3.as_ref().map_or(
                (&caller.name, &caller.super_name, caller.access),
                |(name, parent, access)| (name, parent, *access),
            );
            let lookup = if !interface && owner != *lookup_name && lookup_access & 0x20 != 0 {
                lookup_super.clone()
            } else {
                owner
            };
            let mut sig = self.descriptor(&descriptor)?;
            sig.arguments.insert(0, numeric::Type::MetadataReference(0));
            self.0.borrow_mut().push((lookup, name, descriptor));
            Ok(Some((0, sig, Vec::new(), Vec::new())))
        }
        fn resolve(
            &self,
            caller: &ClassFile,
            constant: u16,
        ) -> Result<(usize, numeric::Signature)> {
            let (owner, name, descriptor, _) = caller.static_method_reference(constant)?;
            let signature = self.descriptor(&descriptor)?;
            self.0.borrow_mut().push((owner, name, descriptor));
            Ok((0, signature)) // Discovery only; real symbol IDs are assigned later.
        }
        fn class_id(&self, _class: &ClassFile) -> Result<usize> {
            Ok(0)
        }
        fn field(&self, caller: &ClassFile, constant: u16) -> Result<numeric::LinkedField> {
            let (owner, _, descriptor) = caller.field_reference(constant)?;
            self.0
                .borrow_mut()
                .push((owner, String::new(), "()V".into()));
            Ok(numeric::LinkedField {
                owner: 0,
                index: 0,
                ty: self.descriptor(&format!("(){descriptor}"))?.result,
                access: 0,
                narrow: descriptor.as_bytes()[0],
            })
        }
        fn signature(&self, _: &ClassFile, method: &Method) -> Result<numeric::Signature> {
            let mut signature = self.descriptor(&method.descriptor)?;
            if method.access & 8 == 0 {
                signature
                    .arguments
                    .insert(0, numeric::Type::LinkedObject(0));
            }
            Ok(signature)
        }
        fn object_class(&self, _: &ClassFile, name: &str) -> Result<usize> {
            self.0
                .borrow_mut()
                .push((name.into(), String::new(), "()V".into()));
            Ok(0)
        }
        fn instance(
            &self,
            caller: &ClassFile,
            constant: u16,
            _: bool,
        ) -> Result<(usize, numeric::Signature)> {
            let (owner, name, descriptor) = caller.method_reference(constant)?;
            let mut signature = self.descriptor(&descriptor)?;
            signature
                .arguments
                .insert(0, numeric::Type::LinkedObject(0));
            self.0.borrow_mut().push((owner, name, descriptor));
            Ok((0, signature))
        }
        fn instance_field(
            &self,
            caller: &ClassFile,
            constant: u16,
        ) -> Result<numeric::LinkedInstanceField> {
            let (owner, _, descriptor) = caller.field_reference(constant)?;
            self.0
                .borrow_mut()
                .push((owner, String::new(), "()V".into()));
            Ok(numeric::LinkedInstanceField {
                owner: 0,
                index: 0,
                offset: 0,
                receiver: numeric::Type::LinkedObject(0),
                mapping: None,
                storage_bytes: 8,
                ty: self.descriptor(&format!("(){descriptor}"))?.result,
                access: 0,
                narrow: descriptor.as_bytes()[0],
            })
        }
        fn string_literal(&self, class: &ClassFile, index: u16) -> Result<usize> {
            let units = class
                .string_literal(index)?
                .context("Expected string constant")?;
            let _ = units;
            Ok(0)
        }
        fn lambda_capture(
            &self,
            class: &ClassFile,
            index: u16,
        ) -> Result<(usize, numeric::Signature)> {
            if class.dynamic_site(index)?.bootstrap.owner == super::records::BOOTSTRAP_OWNER {
                ensure!(self.1, "Record discovery requires verified metadata");
                let plan = super::records::Plan::parse(class, index)?;
                let signature = self.descriptor(&plan.descriptor)?;
                self.0.borrow_mut().push((
                    plan.class_name,
                    super::records::METHOD.into(),
                    plan.descriptor,
                ));
                return Ok((0, signature));
            }
            ensure!(self.1, "Lambda discovery requires verified metadata");
            let plan = lambdas::Plan::parse(class, index)?;
            let sig = self.descriptor(&plan.factory_descriptor)?;
            self.0.borrow_mut().push((
                plan.class_name,
                lambdas::FACTORY.into(),
                plan.factory_descriptor,
            ));
            Ok((0, sig))
        }
        fn require_non_null(&self) -> Result<()> {
            ensure!(self.1, "Objects.requireNonNull requires verified metadata");
            Ok(())
        }
        fn vm_intrinsic(&self, _: &ClassFile, _: vm::Operation) -> Result<()> {
            ensure!(
                self.1,
                "VM native discovery requires verified java.base metadata"
            );
            Ok(())
        }
        fn primitive_class(&self, _: &ClassFile) -> Result<()> {
            ensure!(
                self.1,
                "Primitive class discovery requires verified java.base metadata"
            );
            Ok(())
        }
        fn assertion_status(&self) -> Result<()> {
            Ok(())
        }
        fn class_constant(&self, caller: &ClassFile, name: &str) -> Result<usize> {
            if !name.starts_with('[') {
                self.5.borrow_mut().push(name.into());
            }
            self.class_literal(caller, name)
        }
        fn class_literal(&self, _: &ClassFile, _: &str) -> Result<usize> {
            Ok(0)
        }
        fn object_constructor(&self, class: &ClassFile) -> Result<()> {
            ensure!(
                self.1 || class.super_name == "java/lang/Object",
                "Object constructor discovery needs verified hierarchy metadata"
            );
            Ok(())
        }
        fn type_target(&self, _: &ClassFile, _: &str) -> Result<(usize, numeric::Type)> {
            Ok((0, numeric::Type::MetadataReference(0)))
        }
        fn module_intrinsic(
            &self,
            _: &ClassFile,
            op: modules::Operation,
        ) -> Result<(numeric::Signature, Option<usize>)> {
            ensure!(
                self.1,
                "Module operations require verified java.base metadata"
            );
            let factory = if op == modules::Operation::LayerFindModule {
                self.0.borrow_mut().push((
                    "java/util/Optional".into(),
                    "ofNullable".into(),
                    "(Ljava/lang/Object;)Ljava/util/Optional;".into(),
                ));
                Some(0)
            } else {
                None
            };
            Ok((
                op.signature(
                    numeric::Type::MetadataReference(0),
                    numeric::Type::MetadataReference(0),
                    numeric::Type::LinkedObject(0),
                ),
                factory,
            ))
        }
        fn get_class(&self, _: &ClassFile, _: &str, _: bool) -> Result<()> {
            Ok(())
        }
        fn concat(&self, _: &ClassFile, _: u16, _: concat::Plan) -> Result<usize> {
            Ok(0)
        }
    }
    let entry_class = entry_class.to_owned();
    let mut pending = VecDeque::from([Request {
        loader: entry_loader.into(),
        owner: entry_class.clone(),
        method: method.into(),
        descriptor: descriptor.map(str::to_owned),
        requested_by: "entry point".into(),
    }]);
    ensure!(
        !primordial
            || (metadata && super::thread_bootstrap::entry(&entry_class, method, descriptor)),
        "Invalid primordial discovery profile"
    );
    if primordial {
        for (owner, desc) in super::thread_bootstrap::EXTRA {
            pending.push_back(Request {
                loader: "bootstrap".into(),
                owner: owner.into(),
                method: "<init>".into(),
                descriptor: Some(desc.into()),
                requested_by: "VM primordial dependency".into(),
            });
        }
    }
    pending.extend(definitions.iter().map(|(owner, loader)| Request {
        loader: loader.clone(),
        owner: owner.clone(),
        method: "@definition".into(),
        descriptor: None,
        requested_by: "provided definition".into(),
    }));
    if lookup_fixture {
        ensure!(
            metadata && !primordial && !module_bootstrap,
            "VM lookup fixture requires an isolated metadata compilation"
        );
        for (_, owner) in unwind::KINDS {
            pending.push_back(Request {
                loader: "bootstrap".into(),
                owner: (*owner).into(),
                method: String::new(),
                descriptor: None,
                requested_by: "VM name-lookup error metadata".into(),
            });
        }
        for (owner, method) in [
            (super::class_loaders::LOADER, "@definition"),
            ("java/lang/Throwable", "fillInStackTrace"),
        ] {
            pending.push_back(Request {
                loader: "bootstrap".into(),
                owner: owner.into(),
                method: method.into(),
                descriptor: if method == "@definition" {
                    None
                } else {
                    Some("()Ljava/lang/Throwable;".into())
                },
                requested_by: "VM name-lookup fixture".into(),
            });
        }
    }
    let mut loaded: BTreeMap<String, LoadedClass> = BTreeMap::new();
    let mut seen = BTreeSet::new();
    let mut enqueued = BTreeSet::new();
    let mut bytes_total = 0usize;
    let mut application_loader: Option<String> = None;
    let mut dispatches = BTreeSet::new();
    let mut receiver_order = Vec::new();
    let mut receiver_types = Vec::new();
    let mut receiver_cursors = BTreeMap::new();
    let mut receiver_probes = 0usize;
    let mut active_classes = BTreeSet::new();
    let mut reflective = false;
    let mut constructor_reflection = false;
    let mut constructor_targets = BTreeSet::new();
    let mut lookup = lookup_fixture;
    let mut lookup_targets = BTreeSet::new();
    let mut resolved_lookup_roots = BTreeSet::new();
    let mut reflect_roots: BTreeSet<String> =
        definitions.iter().map(|(name, _)| name.clone()).collect();
    let mut constructor_roots = reflect_roots.clone();
    let mut reflection_targets = BTreeSet::new();
    let trace_discovery = std::env::var_os("BOOM_TRACE_DISCOVERY").is_some();
    loop {
        while let Some(request) = pending.pop_front() {
            if trace_discovery {
                eprintln!(
                    "discovery {}.{}{} <- {}",
                    request.owner,
                    request.method,
                    request.descriptor.as_deref().unwrap_or(""),
                    request.requested_by
                );
            }
            if !loaded.contains_key(&request.owner) {
                ensure!(
                    loaded.len() < MAX_LINKED_CLASSES,
                    "Locked graph exceeds {MAX_LINKED_CLASSES} classes"
                );
                let (bytes, origin) = load(&request.loader, &request.owner)?;
                ensure!(
                    files::digest_bytes(&bytes).sha256 == origin.sha256
                        && origin.binary_name == request.owner.replace('/', "."),
                    "Provider bytes/name disagree with class origin"
                );
                if origin.loader != "bootstrap" {
                    if let Some(loader) = &application_loader {
                        ensure!(
                            loader == &origin.loader,
                            "Multiple application defining loaders require a loader-aware multi-domain linker: {} was {}, {} is {} (requested by {})",
                            request.owner,
                            loader,
                            origin.binary_name,
                            origin.loader,
                            request.requested_by
                        );
                    } else {
                        application_loader = Some(origin.loader.clone());
                    }
                }
                if let Some((_, _, first_origin)) = loaded.values().next() {
                    ensure!(
                        first_origin.loader == origin.loader
                            || (metadata
                                && matches!(
                                    first_origin.loader.as_str(),
                                    "bootstrap" | "vanilla-application" | "explicit-application"
                                )
                                && matches!(
                                    origin.loader.as_str(),
                                    "bootstrap" | "vanilla-application" | "explicit-application"
                                )),
                        "Only the verified bootstrap/application pair may share an executable module"
                    );
                }
                bytes_total = bytes_total
                    .checked_add(bytes.len())
                    .context("Locked byte count overflow")?;
                ensure!(
                    bytes_total <= 256 * 1024 * 1024,
                    "Locked graph exceeds 256 MiB of class bytes"
                );
                let class = ClassFile::parse(&bytes)?;
                ensure!(
                    class.name == request.owner,
                    "Locked class name disagrees with classpath origin"
                );
                receiver_order.push(request.owner.clone());
                loaded.insert(request.owner.clone(), (class, bytes, origin));
            }
            if request.owner == super::module_objects::OWNER
                && !loaded.contains_key(super::class_loaders::LOADER)
            {
                // Physical Module services use the same Context32 error factories
                // as loader services, even when the constructor itself cannot throw.
                for (_, name) in unwind::KINDS {
                    pending.push_back(Request {
                        loader: "bootstrap".into(),
                        owner: (*name).into(),
                        method: String::new(),
                        descriptor: Some("()V".into()),
                        requested_by: "physical Module runtime errors".into(),
                    });
                }
                pending.push_back(Request {
                    loader: "bootstrap".into(),
                    owner: "java/lang/Throwable".into(),
                    method: "fillInStackTrace".into(),
                    descriptor: Some("()Ljava/lang/Throwable;".into()),
                    requested_by: "physical Module error capture".into(),
                });
                pending.push_back(Request {
                    loader: "bootstrap".into(),
                    owner: super::class_loaders::LOADER.into(),
                    method: "@definition".into(),
                    descriptor: Some("()V".into()),
                    requested_by: "physical Module loader metadata".into(),
                });
            }
            let (class, _, origin) = &loaded[&request.owner];
            ensure!(
                request.loader != "bootstrap" || origin.loader == "bootstrap",
                "Bootstrap bytecode cannot resolve an application definition"
            );
            if request.method == "@for-name" {
                lookup = true;
                continue;
            }
            if request.method == "@bootstrap-lookup" {
                continue;
            }
            if request.method == "@lookup-target" {
                pending.push_back(Request {
                    loader: origin.loader.clone(),
                    owner: class.name.clone(),
                    method: String::new(),
                    descriptor: None,
                    requested_by: "Class.forName initialization root".into(),
                });
                continue;
            }
            if request.method == "@reflect-constructors" {
                constructor_reflection = true;
                continue;
            }
            if request.method == "@constructor-target" {
                if class.access & 0x600 == 0
                    && !matches!(
                        class.name.as_str(),
                        "java/lang/Class"
                            | "java/lang/String"
                            | "java/lang/Module"
                            | "java/lang/ModuleLayer"
                            | super::reflect_constructors::OWNER
                            | super::reflect_fields::OWNER
                    )
                {
                    for ctor in class.methods.iter().filter(|m| m.name == "<init>") {
                        pending.push_back(Request {
                            loader: origin.loader.clone(),
                            owner: class.name.clone(),
                            method: ctor.name.clone(),
                            descriptor: Some(ctor.descriptor.clone()),
                            requested_by: "reflective Constructor body".into(),
                        });
                    }
                }
                continue;
            }
            if request.method == "@reflect-new" {
                reflective = true;
                continue;
            }
            if request.method == "@reflect-target" {
                if let Some(ctor) = class
                    .methods
                    .iter()
                    .find(|m| m.name == "<init>" && m.descriptor == "()V")
                    && class.access & 0x600 == 0
                    && !matches!(class.name.as_str(), "java/lang/Class" | "java/lang/String")
                {
                    pending.push_back(Request {
                        loader: origin.loader.clone(),
                        owner: class.name.clone(),
                        method: ctor.name.clone(),
                        descriptor: Some(ctor.descriptor.clone()),
                        requested_by: "reflective constructor root".into(),
                    });
                }
                continue;
            }
            if request.method == "@definition" {
                continue;
            }
            if module_bootstrap
                && super::module_objects::original(class, Some(origin))
                && (request.method.is_empty() || request.method == "<clinit>")
            {
                continue;
            }
            if super::builder_snapshot::is_snapshot(
                &class.name,
                &request.method,
                request.descriptor.as_deref().unwrap_or(""),
            ) {
                ensure!(
                    origin.loader == "bootstrap"
                        && origin.source_id == "jdk:java.base"
                        && origin.generated.is_none(),
                    "Builder native endpoint requires original source"
                );
                active_classes.insert(class.name.clone());
                continue;
            }
            if super::identity_hash::object_member(
                &class.name,
                &request.method,
                request.descriptor.as_deref().unwrap_or(""),
            ) {
                super::identity_hash::verify_object(class, origin)?;
                continue;
            }
            active_classes.insert(class.name.clone());
            validate_provided_class(class, Some(origin)).with_context(|| {
                format!(
                    "Preparing linked class {}.{}{} requested by {}",
                    class.name,
                    request.method,
                    request.descriptor.as_deref().unwrap_or(""),
                    request.requested_by,
                )
            })?;
            let member = if request.method.is_empty() {
                let Some(member) = class.methods.iter().find(|m| m.name == "<clinit>") else {
                    continue;
                };
                member
            } else {
                if let Some(member) = class.methods.iter().find(|m| {
                    m.name == request.method
                        && request
                            .descriptor
                            .as_ref()
                            .is_none_or(|descriptor| &m.descriptor == descriptor)
                }) {
                    member
                } else {
                    let registry = registry
                        .as_deref_mut()
                        .context("Inherited method discovery requires metadata")?;
                    let descriptor = request
                        .descriptor
                        .as_ref()
                        .context("Inherited method discovery requires a descriptor")?;
                    let id = registry.class(&origin.loader, &class.name)?;
                    let member = hierarchy::resolve_method(
                        registry,
                        id,
                        &request.method,
                        descriptor,
                        class.access & 0x200 != 0,
                    )?;
                    let types::Type::Class { key, .. } = &registry.types[member.owner] else {
                        unreachable!()
                    };
                    let next = (
                        key.name.clone(),
                        member.name,
                        member.descriptor,
                        key.loader.clone(),
                    );
                    if enqueued.insert(next.clone()) {
                        pending.push_back(Request {
                            loader: next.3,
                            owner: next.0,
                            method: next.1,
                            descriptor: Some(next.2),
                            requested_by: format!("inherited {}.{}", class.name, request.method),
                        });
                    }
                    continue;
                }
            };
            let key = (
                class.name.clone(),
                member.name.clone(),
                member.descriptor.clone(),
                origin.loader.clone(),
            );
            if !seen.insert(key) {
                continue;
            }
            ensure!(
                seen.len() <= MAX_LINKED_METHODS,
                "Locked graph exceeds {MAX_LINKED_METHODS} methods"
            );
            if request.requested_by == "entry point"
                && super::windows_startup::is_native(&class.name, &member.name, &member.descriptor)
            {
                let plan = super::windows_startup::Plan::new(
                    registry
                        .as_deref_mut()
                        .context("Windows native entry requires java.base metadata")?,
                    0,
                )?;
                ensure!(
                    origin == &plan.origin,
                    "Windows native entry source mismatch"
                );
                continue;
            }
            if request.requested_by == "entry point"
                && super::vm_properties::is_native(&class.name, &member.name, &member.descriptor)
            {
                super::vm_properties::verify(class, origin)?;
                ensure!(
                    !class.methods.iter().any(|m| m.name == "<clinit>"),
                    "VM property entry needs initializer discovery"
                );
                continue;
            }
            let stream_entry = request.requested_by == "entry point"
                && super::system_streams::Operation::resolve(
                    &class.name,
                    &member.name,
                    &member.descriptor,
                )
                .is_some();
            let access_entry = request.requested_by == "entry point"
                && super::access_context::Operation::resolve(
                    &class.name,
                    &member.name,
                    &member.descriptor,
                )
                .is_some();
            if access_entry {
                ensure!(
                    super::access_context::Operation::resolve(
                        &class.name,
                        &member.name,
                        &member.descriptor
                    ) != Some(super::access_context::Operation::CallerClass),
                    "Reflection.getCallerClass requires a verified Java call site and caller-sensitive frame"
                );
                for owner in [
                    super::access_context::CONTEXT,
                    "java/lang/Thread",
                    super::access_context::DOMAIN,
                ] {
                    pending.push_back(Request {
                        loader: "bootstrap".into(),
                        owner: owner.into(),
                        method: if owner == super::access_context::DOMAIN {
                            "@definition".into()
                        } else {
                            String::new()
                        },
                        descriptor: None,
                        requested_by: "VM access context dependency".into(),
                    });
                }
                for (_, owner) in unwind::KINDS {
                    pending.push_back(Request {
                        loader: "bootstrap".into(),
                        owner: (*owner).into(),
                        method: String::new(),
                        descriptor: None,
                        requested_by: "VM access context exception".into(),
                    });
                }
                pending.push_back(Request {
                    loader: "bootstrap".into(),
                    owner: "java/lang/Throwable".into(),
                    method: "fillInStackTrace".into(),
                    descriptor: Some("()Ljava/lang/Throwable;".into()),
                    requested_by: "VM access context trace".into(),
                });
            } else if stream_entry {
                super::system_streams::verify(class, origin)?;
            } else {
                validate_member(class, member, system_startup.is_some()).with_context(|| {
                    format!(
                        "Linking locked {}.{}{} (required by {})",
                        class.name, member.name, member.descriptor, request.requested_by
                    )
                })?;
            }
            let initializer = class.methods.iter().find(|m| m.name == "<clinit>");
            if let Some(init) = initializer {
                let init_key = (
                    class.name.clone(),
                    init.name.clone(),
                    init.descriptor.clone(),
                    origin.loader.clone(),
                );
                if !seen.contains(&init_key) && enqueued.insert(init_key) {
                    pending.push_back(Request {
                        loader: origin.loader.clone(),
                        owner: class.name.clone(),
                        method: init.name.clone(),
                        descriptor: Some(init.descriptor.clone()),
                        requested_by: format!("initialization of {}", class.name),
                    });
                }
            }
            if stream_entry || access_entry {
                continue;
            }
            let lookup_host = if let Some(generated) = &origin.generated {
                let registry = registry
                    .as_deref_mut()
                    .context("Generated lambda lookup needs metadata")?;
                let id = registry.class(&generated.host_loader, &generated.host_class)?;
                let host = registry
                    .definition(id)
                    .context("Missing lambda lookup creator")?;
                Some((host.name.clone(), host.super_name.clone(), host.access))
            } else {
                None
            };
            let recorder = Recorder(
                RefCell::new(Vec::new()),
                metadata,
                RefCell::new(Vec::new()),
                lookup_host,
                primordial,
                RefCell::new(Vec::new()),
            );
            numeric::linked_dependencies(class, member, &recorder).with_context(|| {
                format!(
                    "Discovering locked {}.{}{}",
                    class.name, member.name, member.descriptor
                )
            })?;
            let literal_roots = recorder.5.into_inner();
            if origin.loader != "bootstrap" {
                constructor_roots.extend(literal_roots.iter().cloned());
            }
            reflect_roots.extend(literal_roots);
            dispatches.extend(recorder.2.into_inner().into_iter().map(
                |(owner, name, descriptor, interface)| {
                    (owner, name, descriptor, interface, origin.loader.clone())
                },
            ));
            ensure!(
                dispatches.len() <= 4096,
                "Interface discovery exceeds call-site budget"
            );
            for (owner, name, descriptor) in recorder.0.into_inner() {
                let key = (
                    owner.clone(),
                    name.clone(),
                    descriptor.clone(),
                    origin.loader.clone(),
                );
                if !seen.contains(&key) && enqueued.insert(key) {
                    ensure!(
                        pending.len() < 4096,
                        "Pending locked graph exceeds linking limit"
                    );
                    pending.push_back(Request {
                        loader: origin.loader.clone(),
                        owner,
                        method: name,
                        descriptor: Some(descriptor),
                        requested_by: format!(
                            "{}.{}{}",
                            class.name, member.name, member.descriptor
                        ),
                    });
                }
            }
        }
        let Some(registry) = registry.as_deref_mut() else {
            break;
        };
        // Loaded bytecode already has a verified defining origin. Resolve each
        // receiver once; re-reading and hashing the class for every dispatch
        // made large bootstrap graphs spend most of their time in file IO.
        for receiver_name in &receiver_order[receiver_types.len()..] {
            receiver_types.push(registry.class(&loaded[receiver_name].2.loader, receiver_name)?);
        }
        let mut additions = Vec::new();
        for (owner, name, descriptor, interface, loader) in &dispatches {
            let symbolic = registry.class(loader, owner)?;
            let resolved =
                hierarchy::resolve_method(registry, symbolic, name, descriptor, *interface)?;
            additions.push((
                owner.clone(),
                "@definition".into(),
                "()V".into(),
                loader.clone(),
            ));
            let types::Type::Class { key, .. } = &registry.types[resolved.owner] else {
                unreachable!()
            };
            additions.push((
                key.name.clone(),
                "@definition".into(),
                "()V".into(),
                key.loader.clone(),
            ));
            // Resolve each symbolic-method/receiver pair once, using loader-aware
            // type identities. The previous Cartesian String set retained every
            // rejected receiver and hit its subset budget in the JDK regex graph.
            let dispatch_key = (symbolic, resolved.owner, resolved.index, *interface);
            let start = *receiver_cursors.get(&dispatch_key).unwrap_or(&0);
            for &receiver in &receiver_types[start..] {
                receiver_probes += 1;
                ensure!(
                    receiver_probes <= 1048576,
                    "Interface discovery exceeds 1048576 receiver probes"
                );
                let types::Type::Class { access, .. } = &registry.types[receiver] else {
                    unreachable!()
                };
                if access & 0x600 != 0 || !registry.assignable(receiver, symbolic) {
                    continue;
                }
                if let hierarchy::Selection::Method { member } =
                    hierarchy::select_method(registry, receiver, symbolic, &resolved, *interface)?
                {
                    if dispatch::reflection_target(registry, &member)?.is_some() {
                        continue;
                    }
                    let types::Type::Class { key, .. } = &registry.types[member.owner] else {
                        unreachable!()
                    };
                    additions.push((
                        key.name.clone(),
                        member.name,
                        member.descriptor,
                        key.loader.clone(),
                    ));
                }
            }
            receiver_cursors.insert(dispatch_key, receiver_order.len());
        }
        for (class, _, origin) in loaded.values() {
            if !active_classes.contains(&class.name) {
                continue;
            }
            if class.interfaces == 0 && class.super_name == "java/lang/Object" {
                continue;
            }
            let id = registry.class(&origin.loader, &class.name)?;
            for dependency in hierarchy::initialization_dependencies(registry, id)? {
                let types::Type::Class { key, .. } = &registry.types[dependency] else {
                    unreachable!()
                };
                if key.loader == "bootstrap" && key.name == "java/lang/Object" {
                    continue;
                }
                additions.push((
                    key.name.clone(),
                    String::new(),
                    "()V".into(),
                    key.loader.clone(),
                ));
            }
        }
        for (owner, method, descriptor, loader) in additions {
            if enqueued.insert((
                owner.clone(),
                method.clone(),
                descriptor.clone(),
                loader.clone(),
            )) {
                ensure!(
                    pending.len() < 4096,
                    "Pending hierarchy discovery exceeds linking budget"
                );
                pending.push_back(Request {
                    loader,
                    owner,
                    method,
                    descriptor: Some(descriptor),
                    requested_by: "hierarchy or dispatch dependency".into(),
                });
            }
        }
        if lookup {
            resolved_lookup_roots.extend(reflect_roots.iter().cloned());
            for name in &resolved_lookup_roots {
                if !matches!(
                    name.as_str(),
                    "java/lang/Class"
                        | "java/lang/String"
                        | "java/lang/ModuleLayer"
                        | super::reflect_constructors::OWNER
                        | super::reflect_fields::OWNER
                ) && lookup_targets.insert(name.clone())
                {
                    pending.push_back(Request {
                        loader: entry_loader.into(),
                        owner: name.clone(),
                        method: "@lookup-target".into(),
                        descriptor: None,
                        requested_by: "frozen class-name initialization root".into(),
                    });
                }
            }
        }
        if constructor_reflection {
            // Internal JDK assertion literals describe metadata, not requests to
            // compile every overload of that class. Reachable JDK constructors
            // still receive factories below; unlinked bodies fail explicitly.
            for name in &constructor_roots {
                if constructor_targets.insert(name.clone())
                    && !matches!(
                        name.as_str(),
                        "java/lang/Class"
                            | "java/lang/String"
                            | "java/lang/Module"
                            | "java/lang/ModuleLayer"
                            | super::reflect_constructors::OWNER
                            | super::reflect_fields::OWNER
                    )
                {
                    pending.push_back(Request {
                        loader: entry_loader.into(),
                        owner: name.clone(),
                        method: "@constructor-target".into(),
                        descriptor: None,
                        requested_by: "Constructor reflection root".into(),
                    });
                }
            }
        }
        if reflective {
            for name in reflect_roots.union(&resolved_lookup_roots) {
                if reflection_targets.insert(name.clone())
                    && !matches!(
                        name.as_str(),
                        "java/lang/Class" | "java/lang/String" | "java/lang/ModuleLayer"
                    )
                {
                    pending.push_back(Request {
                        loader: entry_loader.into(),
                        owner: name.clone(),
                        method: "@reflect-target".into(),
                        descriptor: None,
                        requested_by: "Class literal reflection registration".into(),
                    });
                }
            }
        }
        if pending.is_empty() {
            break;
        }
    }
    Ok(loaded.into_values().collect())
}

struct Linker<'a> {
    shutdown: std::cell::RefCell<Option<super::shutdown::Plan>>,
    classes: &'a [ClassFile],
    names: BTreeMap<&'a str, usize>,
    ids: Vec<Vec<usize>>,
    locations: Vec<(usize, usize)>,
    strings: std::cell::RefCell<LiteralPool>,
    metadata: Option<std::cell::RefCell<types::Registry<'a>>>,
    metadata_loader: &'static str,
    source_origins: Vec<Option<crate::bytecode::ClassOrigin>>,
    concats: std::cell::RefCell<BTreeMap<(String, u16), (usize, concat::Plan)>>,
    lambda_sites: std::cell::RefCell<BTreeMap<(String, u16), lambdas::Plan>>,
    record_sites: std::cell::RefCell<BTreeMap<(String, u16), super::records::Binding>>,
    null_guards: std::cell::Cell<bool>,
    monitor_methods: std::cell::RefCell<BTreeMap<(String, String, String), monitors::Binding>>,
    monitor_notifications: std::cell::RefCell<BTreeMap<(String, u16), monitors::Notification>>,
    runtime_resources: std::cell::RefCell<Option<super::runtime_resources::Plan>>,
    resource_bindings: std::cell::RefCell<BTreeMap<String, resources::Binding>>,
    string_joins: std::cell::RefCell<BTreeMap<(String, u16), string_join::Plan>>,
    string_values: std::cell::RefCell<BTreeMap<(String, u16), string_values::Binding>>,
    primitive_bindings: std::cell::RefCell<BTreeMap<String, mirrors::PrimitiveBinding>>,
    type_checks: std::cell::Cell<bool>,
    assertion_queries: std::cell::Cell<bool>,
    vm_bindings: std::cell::RefCell<BTreeMap<vm::Operation, vm::Binding>>,
    cds_bindings: std::cell::RefCell<BTreeMap<(String, u16), cds::Binding>>,
    fd_plan: std::cell::RefCell<Option<file_descriptors::Plan>>,
    stream_plans: std::cell::RefCell<BTreeMap<usize, file_streams::Plan>>,
    throwable_binding: std::cell::RefCell<Option<throwables::Binding>>,
    exception_enabled: std::cell::Cell<bool>,
    npe_bindings: std::cell::RefCell<BTreeMap<u16, crate::bytecode::ClassOrigin>>,
    case_plan: std::cell::RefCell<Option<super::string_case::Plan>>,
    property_plan: std::cell::RefCell<Option<super::system_properties::Plan>>,
    vm_property_plan: std::cell::RefCell<Option<super::vm_properties::Plan>>,
    vm_profile: Option<super::vm_properties::Profile>,
    concat_api: std::cell::RefCell<BTreeMap<(String, u16), super::string_concat_api::Binding>>,
    string_replace: std::cell::RefCell<BTreeMap<(String, u16), super::string_replace::Binding>>,
    literal_regex_replacements: std::cell::RefCell<
        BTreeMap<(String, String, String, usize), super::literal_regex::Binding>,
    >,
    string_chars: std::cell::RefCell<BTreeMap<(String, u16), super::string_chars::Binding>>,
    string_getchars: std::cell::RefCell<BTreeMap<(String, u16), super::string_getchars::Binding>>,
    string_construction:
        std::cell::RefCell<BTreeMap<(String, u16, bool), super::string_construction::Binding>>,
    string_lowercase: std::cell::RefCell<Option<super::string_lowercase::Plan>>,
    string_split: std::cell::RefCell<Option<super::string_split::Plan>>,
    field_bindings: std::cell::RefCell<BTreeMap<(String, u16), super::reflect_fields::Binding>>,
    field_filter_bindings: std::cell::RefCell<
        BTreeMap<(String, String, String, usize), super::field_filters::Binding>,
    >,
    constructor_bindings:
        std::cell::RefCell<BTreeMap<(String, u16), super::reflect_constructors::Binding>>,
    reflect_bindings: std::cell::RefCell<BTreeMap<(String, u16), super::reflect_new::Binding>>,
    reflect_literals: std::cell::RefCell<BTreeSet<usize>>,
    constructor_literals: std::cell::RefCell<BTreeSet<usize>>,
    lookup_bindings: std::cell::RefCell<BTreeMap<(String, u16), super::class_for_name::Binding>>,
    lookup_vm_fixture: bool,
    lookup_literals: std::cell::RefCell<BTreeSet<(String, String)>>,
    string_prefix: std::cell::RefCell<BTreeMap<(String, u16), super::string_prefix::Binding>>,
    array_clones: std::cell::RefCell<BTreeMap<(String, u16), super::array_clone::Binding>>,
    protected_constructors:
        std::cell::RefCell<BTreeMap<(String, u16), super::protected_constructors::Binding>>,
    vm_registration: std::cell::RefCell<BTreeMap<(String, u16), super::vm_registration::Binding>>,
    signal_lookup_bindings: std::cell::RefCell<BTreeMap<(String, u16), super::signals::Binding>>,
    signal_natives: std::cell::RefCell<BTreeMap<(String, u16), super::signal_natives::Binding>>,
    windows_startup: std::cell::RefCell<Option<super::windows_startup::Plan>>,
    class_loaders: std::cell::RefCell<Option<super::class_loaders::Plan>>,
    reflection_arrays: std::cell::RefCell<Option<super::reflection_arrays::Plan>>,
    scoped_memory: std::cell::RefCell<Option<super::scoped_memory::Plan>>,
    winnt_file_system: std::cell::RefCell<Option<super::winnt_file_system::Plan>>,
    thread_natives: std::cell::RefCell<Option<super::thread_natives::Plan>>,
    unsafe_bootstrap: std::cell::RefCell<Option<super::unsafe_bootstrap::Plan>>,
    typed_array_sites:
        std::cell::RefCell<BTreeMap<(String, String, u8), super::typed_arrays::Site>>,
    typed_array_roots: std::cell::RefCell<BTreeSet<usize>>,
    system_startup: Option<super::system_startup::Plan>,
    primordial: bool,
    access_context: std::cell::RefCell<Option<super::access_context::Plan>>,
    system_streams: std::cell::RefCell<Option<super::system_streams::Plan>>,
    identity_hashes: std::cell::RefCell<
        BTreeMap<(String, u16, super::identity_hash::Kind), super::identity_hash::Binding>,
    >,
    hex_strings: std::cell::RefCell<BTreeMap<(String, u16), super::hex_strings::Binding>>,
    string_storage: std::cell::RefCell<
        BTreeMap<(String, u16, super::string_storage::Property), super::string_storage::Binding>,
    >,
    builder_snapshot: std::cell::RefCell<Option<super::builder_snapshot::Plan>>,
    bitcasts: std::cell::RefCell<BTreeMap<(String, u16), super::bitcasts::Binding>>,
    jdk_bridges: std::cell::RefCell<BTreeMap<(String, u16), super::jdk_bridges::Binding>>,
    class_queries: std::cell::RefCell<
        BTreeMap<(String, u16, super::class_queries::Kind), super::class_queries::Binding>,
    >,
    nest_access: std::cell::RefCell<BTreeMap<(String, String), nests::Proof>>,
    constant_initialization:
        std::cell::RefCell<BTreeMap<(String, String, usize), class_initialization::Binding>>,
    module_bindings: std::cell::RefCell<BTreeMap<modules::Operation, modules::Binding>>,
    boot_snapshot: Option<crate::boot_modules::Snapshot>,
    joins: std::cell::RefCell<BTreeMap<Vec<usize>, usize>>,
    dispatch: std::cell::RefCell<BTreeMap<(String, u16, u8), dispatch::Site>>,
    hierarchy: bool,
    covariant_arrays: std::cell::Cell<bool>,
    layouts: std::cell::RefCell<BTreeMap<usize, numeric::ObjectLayout>>,
    field_maps: std::cell::RefCell<BTreeMap<(usize, usize, usize), field_maps::Map>>,
}
#[derive(Default)]
struct LiteralPool {
    values: BTreeMap<Vec<u16>, usize>,
    units: usize,
}
impl LiteralPool {
    fn intern(&mut self, value: Vec<u16>) -> Result<usize> {
        if let Some(&id) = self.values.get(&value) {
            return Ok(id);
        }
        ensure!(
            self.values.len() < 65536 && self.units + value.len() <= 8 * 1024 * 1024,
            "String pool exceeds compiler budget"
        );
        let id = self.values.len();
        self.units += value.len();
        self.values.insert(value, id);
        Ok(id)
    }
}
fn package(name: &str) -> &str {
    name.rsplit_once('/').map_or("", |(parent, _)| parent)
}
fn validate_provided_class(
    class: &ClassFile,
    origin: Option<&crate::bytecode::ClassOrigin>,
) -> Result<()> {
    validate_class_definition(class, origin, false)
}
fn validate_class_definition(
    class: &ClassFile,
    origin: Option<&crate::bytecode::ClassOrigin>,
    metadata_only: bool,
) -> Result<()> {
    let bootstrap = origin
        .is_some_and(|origin| origin.loader == "bootstrap" && origin.source_id == "jdk:java.base");
    let generated = origin.and_then(|origin| origin.generated.as_ref());
    if let Some(proof) = generated {
        let origin = origin.unwrap();
        if proof.generator == "boom-jdk-bridge" {
            super::jdk_bridges::validate(class, origin)?;
        } else if proof.generator == "boom-record" {
            super::records::validate(class, origin)?;
        } else {
            ensure!(
                proof.generator == "boom-lambda"
                    && proof.abi == 1
                    && origin.source_id == "boom:lambda-v1"
                    && origin.loader == proof.host_loader
                    && class.name
                        == format!("{}{}{:04x}", proof.host_class, lambdas::MARKER, proof.site)
                    && package(&class.name) == package(&proof.host_class),
                "Invalid generated lambda origin"
            );
        }
    }
    ensure!(
        bootstrap || generated.is_some() || !class.name.starts_with("java/"),
        "Explicit classes cannot redefine the bootstrap java.* namespace"
    );
    ensure!(
        metadata_only
            || !bootstrap
            || super::module_objects::original(class, origin)
            || !matches!(
                class.name.as_str(),
                "java/lang/String"
                    | "java/lang/Class"
                    | "java/lang/Module"
                    | "java/lang/ModuleLayer"
                    | "java/lang/reflect/Constructor"
                    | "java/lang/reflect/Field"
            ),
        "Bootstrap {} Java bodies need integration with their runtime-owned opaque layout",
        class.name
    );
    ensure!(
        class.field_info.len() <= 4096,
        "Class exceeds static field limit"
    );
    ensure!(
        class.access & 0x2000 == 0
            && (class.access & 0x200 == 0 || class.super_name == "java/lang/Object"),
        "Annotation execution and non-Object interface superclass are unsupported"
    );
    ensure!(
        class
            .name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_$/".contains(&b)),
        "Unsafe class identifier"
    );
    for field in &class.field_info {
        ensure!(
            class.access & 0x200 == 0 || field.access & 0x19 == 0x19,
            "Interface fields must be public static final"
        );
        ensure!(
            field.access & 0x50 != 0x50,
            "A field cannot be both final and volatile"
        );
        numeric::field_type(&field.descriptor)?;
        if field.access & 8 != 0 {
            constant_bits(class, field)?;
        }
    }
    Ok(())
}
fn constant_bits(class: &ClassFile, field: &super::classfile::Field) -> Result<u64> {
    let Some(index) = field.constant_value else {
        return Ok(0);
    };
    if field.descriptor == "Ljava/lang/String;" && class.string_literal(index)?.is_some() {
        return Ok(0);
    }
    let ty = numeric::field_type(&field.descriptor)?;
    let mut bits = match (ty, class.numeric(index)?) {
        (numeric::Type::I32, NumericConstant::Int(v)) => v as u32 as u64,
        (numeric::Type::I64, NumericConstant::Long(v)) => v as u64,
        (numeric::Type::F32, NumericConstant::Float(v)) => v as u64,
        (numeric::Type::F64, NumericConstant::Double(v)) => v,
        _ => anyhow::bail!("ConstantValue type does not match static field descriptor"),
    };
    bits = match field.descriptor.as_str() {
        "Z" => bits & 1,
        "B" => bits as i8 as i32 as u32 as u64,
        "S" => bits as i16 as i32 as u32 as u64,
        "C" => bits as u16 as u64,
        _ => bits,
    };
    Ok(bits)
}
fn validate_member(class: &ClassFile, method: &Method, phase_one_invocation: bool) -> Result<()> {
    ensure!(
        super::signal_natives::Operation::resolve(&class.name, &method.name, &method.descriptor)
            .is_none(),
        "Signal control native requires an original Java call site and initialized Signal owner"
    );
    ensure!(
        super::unsafe_bootstrap::Operation::resolve(&class.name, &method.name, &method.descriptor)
            .is_none(),
        "Unsafe native entry cannot bypass original class initialization; use verified Java call sites"
    );
    ensure!(
        super::thread_natives::Operation::resolve(&class.name, &method.name, &method.descriptor)
            .is_none(),
        "Thread native entry cannot bypass original class initialization and VM attachment; use verified Java call sites"
    );
    ensure!(
        !super::signals::is_lookup(&class.name, &method.name, &method.descriptor),
        "Signal lookup accepts verified Java call sites; a direct native entry cannot bypass original Signal class initialization"
    );
    ensure!(
        super::system_startup::java_method_allowed(class, method, phase_one_invocation),
        "System Java startup phases 1/2/3 are required before executing {}{}",
        method.name,
        method.descriptor
    );
    ensure!(
        method.access & 0x100 == 0,
        "Native method {}.{}{} requires its own assembly runtime binding",
        class.name,
        method.name,
        method.descriptor
    );

    ensure!(
        ((method.name == "<clinit>" && method.descriptor == "()V" && method.access & 8 != 0)
            || (method.name == "<init>"
                && method.access & 8 == 0
                && method.descriptor.ends_with(")V"))
            || (!method.name.starts_with('<')
                && method
                    .name
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"_$".contains(&b)))),
        "Invalid linked member name/access/descriptor"
    );
    Ok(())
}
impl numeric::StaticLinker for Linker<'_> {
    fn access_context(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::access_context::Operation,
    ) -> Result<(numeric::Signature, usize)> {
        self.prepare_access_context()?;
        let ci = self.class_id(caller)?;
        let mut plan = self.access_context.borrow_mut();
        let plan = plan.as_mut().unwrap();
        let owner = if op == super::access_context::Operation::CallerClass {
            plan.prepare_reflection(&mut self.metadata.as_ref().unwrap().borrow_mut())?;
            *self
                .names
                .get(super::access_context::REFLECTION)
                .context("Missing executable Reflection initializer")?
        } else {
            plan.owner
        };
        plan.bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing access context caller source")?,
            constant,
            op,
        )?;
        Ok((
            self.descriptor(self.loader(caller), op.descriptor())?,
            owner,
        ))
    }
    fn primordial_body(&self, class: &ClassFile, code: &super::classfile::Code) -> bool {
        self.primordial && super::thread_bootstrap::applies(class, code)
    }
    fn unsafe_native(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::unsafe_bootstrap::Operation,
    ) -> Result<(numeric::Signature, usize)> {
        let ci = self.class_id(caller)?;
        let owner = *self
            .names
            .get(super::unsafe_bootstrap::OWNER)
            .context("Missing original Unsafe class")?;
        let constants = *self
            .names
            .get(super::unsafe_bootstrap::CONSTANTS)
            .context("Missing original Unsafe constants class")?;
        {
            let mut registry = self
                .metadata
                .as_ref()
                .context("Unsafe requires java.base")?
                .borrow_mut();
            let mut plan = self.unsafe_bootstrap.borrow_mut();
            if plan.is_none() {
                *plan = Some(super::unsafe_bootstrap::Plan::new(
                    &mut registry,
                    owner,
                    constants,
                )?);
            }
            let p = plan.as_mut().unwrap();
            ensure!(
                self.source_origins[owner].as_ref() == Some(&p.origin)
                    && self.source_origins[constants].as_ref() == Some(&p.constants_origin),
                "Unsafe executable providers differ from metadata"
            );
            p.bind(
                caller,
                self.source_origins[ci]
                    .as_ref()
                    .context("Missing Unsafe caller source")?,
                constant,
                op,
            )?;
        }
        if op.field_metadata() {
            super::reflect_fields::register(&mut self.metadata.as_ref().unwrap().borrow_mut())?;
            self.exception_enabled.set(true);
        }
        self.type_checks.set(true);
        let mut sig = self.descriptor(self.loader(caller), op.descriptor())?;
        if op != super::unsafe_bootstrap::Operation::Register {
            sig.arguments.insert(0, numeric::Type::LinkedObject(owner));
        }
        Ok((sig, owner))
    }
    fn thread_native(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::thread_natives::Operation,
    ) -> Result<usize> {
        let ci = self.class_id(caller)?;
        let owner = *self
            .names
            .get(super::thread_natives::OWNER)
            .context("Missing original Thread class")?;
        let mut registry = self
            .metadata
            .as_ref()
            .context("Thread natives require java.base")?
            .borrow_mut();
        let mut plan = self.thread_natives.borrow_mut();
        if plan.is_none() {
            *plan = Some(super::thread_natives::Plan::new(&mut registry, owner)?);
        }
        let p = plan.as_mut().unwrap();
        ensure!(
            self.source_origins[owner].as_ref() == Some(&p.origin),
            "Thread provider source mismatch"
        );
        p.bind(
            &mut registry,
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing native Thread caller origin")?,
            constant,
            op,
        )?;
        self.type_checks.set(true);
        Ok(owner)
    }
    fn signal_lookup(&self, caller: &ClassFile, constant: u16) -> Result<usize> {
        let ci = self.class_id(caller)?;
        let owner = *self
            .names
            .get(super::signals::OWNER)
            .context("Missing original Signal class")?;
        let b = super::signals::binding(
            &mut self
                .metadata
                .as_ref()
                .context("Signal lookup requires java.base")?
                .borrow_mut(),
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing Signal caller source")?,
            constant,
            owner,
        )?;
        ensure!(
            self.source_origins[owner].as_ref() == Some(&b.contract.origin),
            "Signal provider source mismatch"
        );
        self.signal_lookup_bindings
            .borrow_mut()
            .insert((caller.name.clone(), constant), b);
        Ok(owner)
    }
    fn windows_error_mode(&self, caller: &ClassFile, constant: u16) -> Result<usize> {
        self.prepare_windows_startup()?;
        let ci = self.class_id(caller)?;
        let mut plan = self.windows_startup.borrow_mut();
        let plan = plan.as_mut().unwrap();
        plan.bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing Windows native caller source")?,
            constant,
        )?;
        Ok(plan.class_id)
    }
    fn class_loader_field(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        self.prepare_class_loaders()?;
        let ci = self.class_id(caller)?;
        self.class_loaders.borrow_mut().as_mut().unwrap().bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing Class loader field source")?,
            constant,
        )
    }
    fn winfs_init(&self, caller: &ClassFile, constant: u16) -> Result<(usize, usize)> {
        let owner = self.names[super::winnt_file_system::OWNER];
        let file = self.names[super::winnt_file_system::FILE];
        let ci = self.class_id(caller)?;
        let layout = self.layout(file)?;
        let mut registry = self
            .metadata
            .as_ref()
            .context("WinNTFileSystem needs java.base")?
            .borrow_mut();
        let mut plan = self.winnt_file_system.borrow_mut();
        if plan.is_none() {
            *plan = Some(super::winnt_file_system::Plan::new(
                &mut registry,
                owner,
                file,
                layout,
            )?);
        }
        let p = plan.as_mut().unwrap();
        ensure!(
            self.source_origins[owner].as_ref() == Some(&p.origin)
                && self.source_origins[file].as_ref() == Some(&p.file_origin),
            "Windows file system provider identity mismatch"
        );
        p.bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing WinNTFileSystem caller source")?,
            constant,
        )?;
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok((owner, file))
    }
    fn scoped_register(&self, caller: &ClassFile, constant: u16) -> Result<usize> {
        let owner = self.names[super::scoped_memory::OWNER];
        let ci = self.class_id(caller)?;
        let mut registry = self
            .metadata
            .as_ref()
            .context("ScopedMemoryAccess requires java.base")?
            .borrow_mut();
        let mut plan = self.scoped_memory.borrow_mut();
        if plan.is_none() {
            *plan = Some(super::scoped_memory::Plan::new(&mut registry, owner)?);
        }
        let p = plan.as_mut().unwrap();
        ensure!(
            self.source_origins[owner].as_ref() == Some(&p.origin),
            "ScopedMemoryAccess provider mismatch"
        );
        p.bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing ScopedMemoryAccess source")?,
            constant,
        )?;
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok(owner)
    }
    fn class_loader_register(&self, caller: &ClassFile, constant: u16) -> Result<usize> {
        self.prepare_class_loaders()?;
        let ci = self.class_id(caller)?;
        self.class_loaders
            .borrow_mut()
            .as_mut()
            .unwrap()
            .bind_registration(
                caller,
                self.source_origins[ci]
                    .as_ref()
                    .context("Missing ClassLoader registration source")?,
                constant,
            )?;
        Ok(*self.names.get(super::class_loaders::LOADER).unwrap())
    }
    fn reflect_array(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::reflection_arrays::Operation,
    ) -> Result<(numeric::Signature, usize)> {
        let owner = self.names[super::reflection_arrays::OWNER];
        let ci = self.class_id(caller)?;
        let mut registry = self
            .metadata
            .as_ref()
            .context("Reflection arrays require java.base")?
            .borrow_mut();
        let mut plan = self.reflection_arrays.borrow_mut();
        if plan.is_none() {
            for class in self.classes {
                registry.class(self.loader(class), &class.name)?;
            }
            for primitive in [
                types::Primitive::Boolean,
                types::Primitive::Byte,
                types::Primitive::Char,
                types::Primitive::Short,
                types::Primitive::Int,
                types::Primitive::Long,
                types::Primitive::Float,
                types::Primitive::Double,
                types::Primitive::Void,
            ] {
                registry.primitive(primitive)?;
            }
            *plan = Some(super::reflection_arrays::Plan::new(&mut registry, owner)?);
        }
        let p = plan.as_mut().unwrap();
        ensure!(
            self.source_origins[owner].as_ref() == Some(&p.origin),
            "Reflection Array provider mismatch"
        );
        p.bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing reflection array caller source")?,
            constant,
            op,
        )?;
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        drop(plan);
        drop(registry);
        Ok((
            self.descriptor(self.loader(caller), op.descriptor())?,
            owner,
        ))
    }
    fn signal_control(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::signal_natives::Operation,
    ) -> Result<usize> {
        let ci = self.class_id(caller)?;
        let owner = *self
            .names
            .get(super::signals::OWNER)
            .context("Missing original Signal class")?;
        let binding = super::signal_natives::binding(
            &mut self
                .metadata
                .as_ref()
                .context("Signal control requires java.base")?
                .borrow_mut(),
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing Signal caller source")?,
            constant,
            op,
            owner,
        )?;
        ensure!(
            self.source_origins[owner].as_ref() == Some(&binding.origin),
            "Signal control provider source mismatch"
        );
        self.signal_natives
            .borrow_mut()
            .insert((caller.name.clone(), constant), binding);
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok(owner)
    }
    fn string_prefix(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing String prefix caller")?;
        let b = super::string_prefix::binding(
            &mut self
                .metadata
                .as_ref()
                .context("String prefix requires java.base")?
                .borrow_mut(),
            caller,
            source,
            constant,
        )?;
        self.string_prefix
            .borrow_mut()
            .insert((caller.name.clone(), constant), b);
        Ok(super::string_prefix::signature())
    }
    fn system_stream(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::system_streams::Operation,
    ) -> Result<(numeric::Signature, usize)> {
        let ci = self.names["java/lang/System"];
        self.prepare_system_streams(ci)?;
        let caller_id = self.class_id(caller)?;
        self.system_streams.borrow_mut().as_mut().unwrap().bind(
            caller,
            self.source_origins[caller_id]
                .as_ref()
                .context("Missing System stream caller")?,
            constant,
            op,
        )?;
        Ok((self.descriptor("bootstrap", op.descriptor())?, ci))
    }
    fn string_construction(
        &self,
        caller: &ClassFile,
        constant: u16,
        allocation: bool,
    ) -> Result<()> {
        let ci = self.class_id(caller)?;
        let binding = super::string_construction::binding(
            &mut self
                .metadata
                .as_ref()
                .context("String construction needs verified metadata")?
                .borrow_mut(),
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing String construction caller source")?,
            constant,
            allocation,
        )?;
        self.string_construction
            .borrow_mut()
            .insert((caller.name.clone(), constant, allocation), binding);
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok(())
    }
    fn class_for_name(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        self.prepare_class_loaders()?;
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing lookup caller")?;
        let binding = super::class_for_name::binding(
            &mut self.metadata.as_ref().unwrap().borrow_mut(),
            caller,
            source,
            constant,
        )?;
        let descriptor = if binding.bootstrap_lookup {
            super::class_for_name::BOOTSTRAP_DESCRIPTOR
        } else {
            super::class_for_name::DESCRIPTOR
        };
        self.lookup_bindings
            .borrow_mut()
            .insert((caller.name.clone(), constant), binding);
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        self.descriptor(self.loader(caller), descriptor)
    }
    fn reflected_field_filter(
        &self,
        caller: &ClassFile,
        constant: u16,
        proof: super::field_filters::Proof,
    ) -> Result<numeric::Signature> {
        let ci = self.class_id(caller)?;
        let mi = caller
            .methods
            .iter()
            .position(|m| m.name == proof.method && m.descriptor == proof.descriptor)
            .context("Missing Field filter caller method")?;
        let target = self.class_literal(caller, &proof.containing_class)?;
        let set_ci = *self
            .names
            .get(super::field_filters::SET12)
            .context("Missing original Set12 constructor class")?;
        let layout = self.layout(set_ci)?;
        let key = (
            caller.name.clone(),
            proof.method.clone(),
            proof.descriptor.clone(),
            proof.pc,
        );
        let binding = super::field_filters::bind(
            &mut self.metadata.as_ref().unwrap().borrow_mut(),
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing Field filter caller source")?,
            constant,
            (self.ids[ci][mi], target, set_ci),
            &layout,
            proof,
        )?;
        self.field_filter_bindings.borrow_mut().insert(key, binding);
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        self.descriptor(self.loader(caller), super::field_filters::DESCRIPTOR)
    }

    fn reflected_field(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::reflect_fields::Operation,
    ) -> Result<numeric::Signature> {
        let ci = self.class_id(caller)?;
        let mut registry = self
            .metadata
            .as_ref()
            .context("Field reflection requires java.base")?
            .borrow_mut();
        super::reflect_fields::register(&mut registry)?;
        let binding = super::reflect_fields::binding(
            &mut registry,
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing Field caller source")?,
            constant,
            op,
        )?;
        self.field_bindings
            .borrow_mut()
            .insert((caller.name.clone(), constant), binding);
        drop(registry);
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        let (o, _, d) = caller.method_reference(constant)?;
        self.descriptor(self.loader(caller), &format!("(L{o};{}", &d[1..]))
    }

    fn reflected_constructor(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::reflect_constructors::Operation,
    ) -> Result<(usize, numeric::Signature)> {
        let ci = self.class_id(caller)?;
        let source = self.source_origins[ci]
            .as_ref()
            .context("Missing Constructor caller")?;
        let mut registry = self
            .metadata
            .as_ref()
            .context("Constructor reflection needs metadata")?
            .borrow_mut();
        super::reflect_constructors::register(&mut registry)?;
        let mut access_caller = source.clone();
        let mut caller_type = registry.class(&source.loader, &caller.name)?;
        if let Some(g) = source
            .generated
            .as_ref()
            .filter(|g| matches!(g.generator.as_str(), "boom-jdk-bridge" | "boom-lambda"))
        {
            if g.generator == "boom-jdk-bridge" {
                super::jdk_bridges::validate(caller, source)?;
            }
            caller_type = registry.class(&g.host_loader, &g.host_class)?;
            let types::Type::Class { origin, .. } = &registry.types[caller_type] else {
                unreachable!()
            };
            ensure!(
                origin.sha256 == g.host_sha256
                    && origin.source_id == g.host_source_id
                    && origin.generated.is_none(),
                "Constructor creator context changed"
            );
            access_caller = origin.as_ref().clone();
        }
        let key = (caller.name.clone(), constant);
        let mut bindings = self.constructor_bindings.borrow_mut();
        if !bindings.contains_key(&key) {
            let b = super::reflect_constructors::binding(
                &mut registry,
                caller,
                source,
                (access_caller, caller_type),
                constant,
                op,
                bindings.len(),
            )?;
            bindings.insert(key.clone(), b);
        }
        let site = bindings[&key].site;
        drop(bindings);
        drop(registry);
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        self.covariant_arrays.set(true);
        let (o, _, d) = caller.method_reference(constant)?;
        let sig = self.descriptor(self.loader(caller), &format!("(L{o};{}", &d[1..]))?;
        Ok((site, sig))
    }
    fn reflect_new(
        &self,
        caller: &ClassFile,
        constant: u16,
    ) -> Result<(usize, numeric::Signature)> {
        let ci = self.class_id(caller)?;
        let mut caller_type = self.class_literal(caller, &caller.name)?;
        let source = self.source_origins[ci]
            .as_ref()
            .context("Unproven reflection caller")?;
        let mut access_caller = source.clone();
        if let Some(g) = source
            .generated
            .as_ref()
            .filter(|g| matches!(g.generator.as_str(), "boom-jdk-bridge" | "boom-lambda"))
        {
            if g.generator == "boom-jdk-bridge" {
                super::jdk_bridges::validate(caller, source)?;
            }
            let mut registry = self.metadata.as_ref().unwrap().borrow_mut();
            caller_type = registry.class(&g.host_loader, &g.host_class)?;
            let types::Type::Class { origin, .. } = &registry.types[caller_type] else {
                unreachable!()
            };
            ensure!(
                origin.source_id == g.host_source_id
                    && origin.sha256 == g.host_sha256
                    && origin.generated.is_none(),
                "Reflection creator identity changed"
            );
            access_caller = origin.as_ref().clone();
        }
        super::reflect_new::verify(
            &mut self
                .metadata
                .as_ref()
                .context("Reflection needs original metadata")?
                .borrow_mut(),
        )?;
        let key = (caller.name.clone(), constant);
        let mut bindings = self.reflect_bindings.borrow_mut();
        if !bindings.contains_key(&key) {
            let site = bindings.len();
            bindings.insert(
                key.clone(),
                super::reflect_new::Binding {
                    caller: self.source_origins[ci]
                        .as_ref()
                        .context("Unproven reflection caller")?
                        .clone(),
                    constant,
                    access_caller,
                    caller_type,
                    site,
                },
            );
        }
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        let mut sig = self.descriptor(self.loader(caller), super::reflect_new::DESCRIPTOR)?;
        sig.arguments.insert(0, numeric::Type::BootstrapClass);
        Ok((bindings[&key].site, sig))
    }
    fn string_split(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        if self.string_split.borrow().is_none() {
            let empty = self.strings.borrow_mut().intern(Vec::new())?;
            *self.string_split.borrow_mut() = Some(super::string_split::Plan::new(
                &mut self
                    .metadata
                    .as_ref()
                    .context("String split needs verified metadata")?
                    .borrow_mut(),
                empty,
            )?);
        }
        let ci = self.class_id(caller)?;
        self.string_split.borrow_mut().as_mut().unwrap().bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing split caller origin")?,
            constant,
        )?;
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok(super::string_split::signature())
    }
    fn string_lowercase(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        if self.string_lowercase.borrow().is_none() {
            let locale = *self
                .names
                .get(super::string_lowercase::LOCALE)
                .context("Missing Locale case metadata")?;
            let base = *self
                .names
                .get(super::string_lowercase::BASE)
                .context("Missing BaseLocale case metadata")?;
            let locale_layout = self.layout(locale)?;
            let base_layout = self.layout(base)?;
            *self.string_lowercase.borrow_mut() = Some(super::string_lowercase::Plan::new(
                &mut self
                    .metadata
                    .as_ref()
                    .context("Case conversion needs verified metadata")?
                    .borrow_mut(),
                locale_layout,
                base_layout,
            )?);
        }
        self.string_case(caller, constant)?;
        let ci = self.class_id(caller)?;
        self.string_lowercase.borrow_mut().as_mut().unwrap().bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing lowercase caller origin")?,
            constant,
        )?;
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        let mut sig = self.descriptor(self.loader(caller), super::string_lowercase::DESCRIPTOR)?;
        sig.arguments.insert(0, numeric::Type::BootstrapString);
        Ok(sig)
    }
    fn string_chars(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing String character copy caller")?;
        let b = super::string_chars::binding(
            &mut self
                .metadata
                .as_ref()
                .context("String character copy requires java.base")?
                .borrow_mut(),
            caller,
            source,
            constant,
        )?;
        self.string_chars
            .borrow_mut()
            .insert((caller.name.clone(), constant), b);
        Ok(super::string_chars::signature())
    }
    fn string_get_chars(&self, caller: &ClassFile, constant: u16) -> Result<()> {
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing String.getChars caller source")?;
        let binding = super::string_getchars::bind(
            &mut self.metadata.as_ref().unwrap().borrow_mut(),
            caller,
            source,
            constant,
        )?;
        self.string_getchars
            .borrow_mut()
            .insert((caller.name.clone(), constant), binding);
        self.exception_enabled.set(true);
        Ok(())
    }
    fn literal_regex_replace(
        &self,
        caller: &ClassFile,
        constant: u16,
        proof: super::literal_regex::Proof,
    ) -> Result<numeric::Signature> {
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing literal regex caller source")?;
        let binding = super::literal_regex::bind(
            &mut self
                .metadata
                .as_ref()
                .context("Literal regex requires java.base metadata")?
                .borrow_mut(),
            caller,
            source,
            constant,
            proof,
        )?;
        self.literal_regex_replacements.borrow_mut().insert(
            (
                caller.name.clone(),
                binding.proof.method.clone(),
                binding.proof.descriptor.clone(),
                binding.proof.pc,
            ),
            binding,
        );
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok(super::literal_regex::signature())
    }
    fn string_replace(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing String replacement caller")?;
        let b = super::string_replace::binding(
            &mut self
                .metadata
                .as_ref()
                .context("String replacement requires java.base")?
                .borrow_mut(),
            caller,
            source,
            constant,
        )?;
        self.string_replace
            .borrow_mut()
            .insert((caller.name.clone(), constant), b);
        Ok(super::string_replace::signature())
    }
    fn class_query(
        &self,
        caller: &ClassFile,
        constant: u16,
        kind: super::class_queries::Kind,
    ) -> Result<()> {
        if kind == super::class_queries::Kind::IsInstance {
            self.type_checks.set(true);
        }
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing Class query caller")?;
        let b = super::class_queries::binding(
            &mut self
                .metadata
                .as_ref()
                .context("Class query requires java.base")?
                .borrow_mut(),
            caller,
            source,
            constant,
            kind,
        )?;
        self.class_queries
            .borrow_mut()
            .insert((caller.name.clone(), constant, kind), b);
        Ok(())
    }
    fn class_value_field(
        &self,
        caller: &ClassFile,
        constant: u16,
        write: bool,
    ) -> Result<numeric::Signature> {
        self.class_query(
            caller,
            constant,
            if write {
                super::class_queries::Kind::ClassValueStore
            } else {
                super::class_queries::Kind::ClassValueLoad
            },
        )?;
        self.type_checks.set(true);
        self.exception_enabled.set(true);
        self.descriptor(
            self.loader(caller),
            super::class_queries::class_value_descriptor(write),
        )
    }
    fn shutdown_native(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::shutdown::Operation,
    ) -> Result<(numeric::Signature, usize)> {
        let owner = *self
            .names
            .get(super::shutdown::OWNER)
            .context("Missing Shutdown executable definition")?;
        if self.shutdown.borrow().is_none() {
            *self.shutdown.borrow_mut() = Some(super::shutdown::Plan::new(
                &mut self
                    .metadata
                    .as_ref()
                    .context("Shutdown needs java.base")?
                    .borrow_mut(),
                owner,
            )?);
        }
        self.shutdown.borrow_mut().as_mut().unwrap().bind(
            &mut self.metadata.as_ref().unwrap().borrow_mut(),
            caller,
            self.source_origins[self.class_id(caller)?]
                .as_ref()
                .context("Missing Shutdown caller provenance")?,
            constant,
            op,
        )?;
        self.exception_enabled.set(true);
        Ok((op.signature(), owner))
    }

    fn jdk_bridge(
        &self,
        caller: &ClassFile,
        constant: u16,
        kind: super::jdk_bridges::Kind,
    ) -> Result<(usize, numeric::Signature)> {
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing bridge caller")?;
        self.metadata
            .as_ref()
            .context("JDK bridge requires java.base metadata")?
            .borrow_mut()
            .class("bootstrap", kind.owner())?;
        if kind.private_api() {
            let mut registry = self.metadata.as_ref().unwrap().borrow_mut();
            let id = registry.class("bootstrap", kind.owner())?;
            let types::Type::Class { origin: host, .. } = &registry.types[id] else {
                unreachable!()
            };
            let direct = source == host.as_ref() && caller.name == kind.owner();
            let copied = if source
                .generated
                .as_ref()
                .is_some_and(|g| g.generator == "boom-jdk-bridge")
            {
                super::jdk_bridges::validate(caller, source)?;
                source
                    .generated
                    .as_ref()
                    .is_some_and(|g| g.host_class == kind.owner() && g.host_sha256 == host.sha256)
            } else {
                false
            };
            ensure!(
                direct || copied,
                "Private Class.forName helper requires its verified original Class caller"
            );
        } else if !kind.public_api() {
            ensure!(
                source.loader == "bootstrap" && package(&caller.name) == "java/lang",
                "String bounds bridges require java.lang package access"
            );
        }
        let (o, n, d, _) = caller.special_method_reference(constant)?;
        ensure!(
            super::jdk_bridges::Kind::resolve(&o, &n, &d, !kind.instance()) == Some(kind),
            "JDK bridge call changed"
        );
        let name = kind.class_name();
        let ci = *self
            .names
            .get(name.as_str())
            .context("Missing JDK bridge holder")?;
        let origin = self.source_origins[ci]
            .as_ref()
            .context("Missing JDK bridge origin")?;
        super::jdk_bridges::validate(&self.classes[ci], origin)?;
        let mi = self.classes[ci]
            .methods
            .iter()
            .position(|m| m.name == kind.name() && m.descriptor == kind.descriptor())
            .context("Missing bridge method")?;
        self.jdk_bridges.borrow_mut().insert(
            (caller.name.clone(), constant),
            super::jdk_bridges::Binding {
                kind,
                caller: source.clone(),
                constant,
                target: origin.clone(),
            },
        );
        Ok((
            self.ids[ci][mi],
            self.descriptor(self.loader(caller), kind.descriptor())?,
        ))
    }
    fn bitcast(
        &self,
        caller: &ClassFile,
        constant: u16,
        kind: super::bitcasts::Kind,
    ) -> Result<(numeric::Signature, usize)> {
        let owner = *self
            .names
            .get(kind.owner())
            .context("Missing numeric initializer")?;
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing bitcast caller")?;
        let b = super::bitcasts::binding(
            &mut self
                .metadata
                .as_ref()
                .context("Bitcasts require java.base")?
                .borrow_mut(),
            caller,
            source,
            constant,
            kind,
            owner,
        )?;
        ensure!(
            self.source_origins[owner].as_ref() == Some(&b.origin),
            "Bitcast initializer origin differs from metadata"
        );
        self.bitcasts
            .borrow_mut()
            .insert((caller.name.clone(), constant), b);
        Ok((kind.signature(), owner))
    }
    fn builder_snapshot(
        &self,
        caller: &ClassFile,
        constant: u16,
    ) -> Result<(numeric::Signature, usize)> {
        self.bind_builder_snapshot_in(
            &mut self
                .metadata
                .as_ref()
                .context("Builder snapshot needs java.base")?
                .borrow_mut(),
            caller,
            constant,
        )
    }
    fn string_storage(
        &self,
        caller: &ClassFile,
        constant: u16,
        property: super::string_storage::Property,
    ) -> Result<u32> {
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing string storage caller")?;
        let b = super::string_storage::binding(
            &mut self
                .metadata
                .as_ref()
                .context("String storage requires java.base")?
                .borrow_mut(),
            caller,
            source,
            constant,
            property,
        )?;
        let value = b.value;
        self.string_storage
            .borrow_mut()
            .insert((caller.name.clone(), constant, property), b);
        Ok(value)
    }
    fn hex_string(
        &self,
        caller: &ClassFile,
        constant: u16,
        kind: super::hex_strings::Kind,
    ) -> Result<(numeric::Signature, usize)> {
        let owner = *self
            .names
            .get(kind.owner())
            .context("Missing original hex class initializer")?;
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing hex caller source")?;
        let b = super::hex_strings::binding(
            &mut self
                .metadata
                .as_ref()
                .context("Hex strings require java.base")?
                .borrow_mut(),
            caller,
            source,
            constant,
            kind,
            owner,
        )?;
        ensure!(
            self.source_origins[owner].as_ref() == Some(&b.origin),
            "Hex executable class initializer differs from metadata"
        );
        self.hex_strings
            .borrow_mut()
            .insert((caller.name.clone(), constant), b);
        Ok((kind.signature(), owner))
    }
    fn array_clone(
        &self,
        caller: &ClassFile,
        constant: u16,
    ) -> Result<(numeric::Signature, usize)> {
        let (owner, _, _) = caller.method_reference(constant)?;
        let owner_type = self.class_literal(caller, &owner)?;
        let ci = self.class_id(caller)?;
        let b = super::array_clone::binding(
            &mut self
                .metadata
                .as_ref()
                .context("Array clone requires java.base")?
                .borrow_mut(),
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing clone caller source")?,
            constant,
            owner_type,
        )?;
        let object = *self
            .names
            .get("java/lang/Object")
            .context("Missing Object clone definition")?;
        ensure!(
            self.source_origins[object].as_ref() == Some(&b.origin),
            "Clone Object source differs from executable definition"
        );
        self.array_clones
            .borrow_mut()
            .insert((caller.name.clone(), constant), b);
        self.type_checks.set(true);
        let result = self
            .descriptor(self.loader(caller), "()Ljava/lang/Object;")?
            .result;
        Ok((
            numeric::Signature {
                arguments: vec![numeric::Type::MetadataReference(owner_type)],
                result,
            },
            owner_type,
        ))
    }
    fn fixed_identity_hash(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        let (owner, _, _) = caller.method_reference(constant)?;
        self.record_identity_hash(
            &mut self
                .metadata
                .as_ref()
                .context("Array hashes require java.base")?
                .borrow_mut(),
            caller,
            constant,
            if owner.starts_with('[') {
                super::identity_hash::Kind::ArrayDefault
            } else {
                super::identity_hash::Kind::OpaqueDefault
            },
        )?;
        self.type_checks.set(true);
        let receiver = if owner.starts_with('[') {
            owner
        } else {
            format!("L{owner};")
        };
        self.descriptor(self.loader(caller), &format!("({receiver})I"))
    }
    fn identity_hash(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        self.record_identity_hash(
            &mut self
                .metadata
                .as_ref()
                .context("Identity hash requires java.base")?
                .borrow_mut(),
            caller,
            constant,
            super::identity_hash::Kind::SystemIdentity,
        )?;
        self.type_checks.set(true);
        self.descriptor(self.loader(caller), "(Ljava/lang/Object;)I")
    }
    fn raw_properties(
        &self,
        caller: &ClassFile,
        constant: u16,
        operation: super::system_properties::Operation,
    ) -> Result<(numeric::Signature, usize)> {
        let ci = self.class_id(caller)?;
        if matches!(operation, super::system_properties::Operation::Vm) {
            self.prepare_vm_properties(ci)?;
            self.vm_property_plan.borrow_mut().as_mut().unwrap().bind(
                caller,
                self.source_origins[ci]
                    .as_ref()
                    .context("Missing Raw caller origin")?,
                constant,
            )?;
            self.type_checks.set(true);
            return Ok((super::vm_properties::Plan::signature(), ci));
        }
        let mut plan = self.property_plan.borrow_mut();
        if plan.is_none() {
            *plan = Some(super::system_properties::Plan::prepare(
                &mut self
                    .metadata
                    .as_ref()
                    .context("Raw native properties require java.base")?
                    .borrow_mut(),
                ci,
                |s| self.strings.borrow_mut().intern(s.encode_utf16().collect()),
            )?);
        }
        plan.as_mut().unwrap().bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing Raw caller origin")?,
            constant,
        )?;
        self.type_checks.set(true);
        Ok((super::system_properties::Plan::signature(), ci))
    }
    fn string_concat_api(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        let ci = self.class_id(caller)?;
        let binding = super::string_concat_api::binding(
            &mut self
                .metadata
                .as_ref()
                .context("String.concat requires java.base")?
                .borrow_mut(),
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing String.concat caller origin")?,
            constant,
        )?;
        self.concat_api
            .borrow_mut()
            .insert((caller.name.clone(), constant), binding);
        Ok(super::string_concat_api::signature())
    }
    fn string_case(&self, caller: &ClassFile, constant: u16) -> Result<()> {
        let ci = self.class_id(caller)?;
        let (_, name, _) = caller.method_reference(constant)?;
        if name == "substring" || name == "trim" {
            self.strings.borrow_mut().intern(Vec::new())?;
        }
        let mut plan = self.case_plan.borrow_mut();
        if plan.is_none() {
            *plan = Some(super::string_case::Plan::prepare(
                &mut self
                    .metadata
                    .as_ref()
                    .context("Unicode String comparison requires verified java.base")?
                    .borrow_mut(),
            )?);
        }
        plan.as_mut().unwrap().bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing String case caller provenance")?,
            constant,
        )
    }
    fn exception_method(&self, _: &ClassFile, method: &Method) -> Result<()> {
        if unwind::required(method)? {
            ensure!(
                self.metadata.is_some(),
                "Context32 requires verified java.base"
            );
            self.exception_enabled.set(true);
            self.type_checks.set(true);
        }
        Ok(())
    }
    fn context_bytes(&self) -> usize {
        if self.exception_enabled.get() { 32 } else { 16 }
    }
    fn runtime_resources(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::runtime_resources::Operation,
    ) -> Result<numeric::Signature> {
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing processor query caller")?;
        let mut plan = self.runtime_resources.borrow_mut();
        if plan.is_none() {
            *plan = Some(super::runtime_resources::Plan::new(
                &mut self
                    .metadata
                    .as_ref()
                    .context("Processor query requires metadata")?
                    .borrow_mut(),
            )?);
        }
        let result = plan.as_mut().unwrap().bind(caller, source, constant, op)?;
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok(result)
    }
    fn monitor_notify(
        &self,
        caller: &ClassFile,
        constant: u16,
        all: bool,
    ) -> Result<numeric::Signature> {
        let source = self.source_origins[self.class_id(caller)?]
            .as_ref()
            .context("Missing notification caller")?;
        let binding = monitors::Notification::bind(
            &mut self
                .metadata
                .as_ref()
                .context("Notification requires metadata")?
                .borrow_mut(),
            self.loader(caller),
            caller,
            source,
            constant,
            all,
        )?;
        let receiver = binding.receiver_type;
        self.monitor_notifications
            .borrow_mut()
            .insert((caller.name.clone(), constant), binding);
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok(numeric::Signature {
            arguments: vec![numeric::Type::MetadataReference(receiver)],
            result: numeric::Type::Void,
        })
    }
    fn monitor_opcode(&self, _: &ClassFile) -> Result<()> {
        ensure!(
            self.metadata.is_some(),
            "Monitor opcodes require verified java.base"
        );
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok(())
    }
    fn npe_message(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        let ci = self.class_id(caller)?;
        let mut registry = self
            .metadata
            .as_ref()
            .context("NPE diagnostics require java.base")?
            .borrow_mut();
        let id = registry.class("bootstrap", "java/lang/NullPointerException")?;
        let types::Type::Class { key, origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none()
                && caller.name == key.name
                && self.source_origins[ci].as_ref() == Some(origin.as_ref()),
            "NPE private native requires its original caller"
        );
        let native = caller.method("getExtendedNPEMessage", Some("()Ljava/lang/String;"))?;
        ensure!(
            native.access == 0x102 && native.code.is_none(),
            "NPE diagnostic native contract changed"
        );
        self.npe_bindings
            .borrow_mut()
            .insert(constant, origin.as_ref().clone());
        drop(registry);
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        self.descriptor(
            self.loader(caller),
            "(Ljava/lang/NullPointerException;)Ljava/lang/String;",
        )
    }
    fn runtime_frames(&self) -> bool {
        self.exception_enabled.get() || self.throwable_binding.borrow().is_some()
    }
    fn throwable_fill(&self, caller: &ClassFile, constant: u16) -> Result<numeric::Signature> {
        let ci = self.class_id(caller)?;
        let binding = throwables::binding(
            &mut self
                .metadata
                .as_ref()
                .context("Throwable native requires java.base")?
                .borrow_mut(),
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing Throwable caller origin")?,
            constant,
        )?;
        *self.throwable_binding.borrow_mut() = Some(binding);
        self.type_checks.set(true);
        self.descriptor(
            self.loader(caller),
            "(Ljava/lang/Throwable;I)Ljava/lang/Throwable;",
        )
    }
    fn initializer_source_abi(&self) -> u32 {
        // v28 has a separate identity and enables this contract for ordinary
        // static wrappers in its image. Earlier profiles retain ABI1 bytes.
        if self.stream_plans.borrow().is_empty() && self.throwable_binding.borrow().is_none() {
            1
        } else {
            2
        }
    }
    fn stream_init(&self, caller: &ClassFile, constant: u16) -> Result<usize> {
        let (name, _, _, _) = caller.static_method_reference(constant)?;
        let &owner = self
            .names
            .get(name.as_str())
            .context("Missing original stream executable class")?;
        ensure!(
            caller.name == name,
            "Stream initIDs requires its own original caller"
        );
        let origin = self.source_origins[owner]
            .as_ref()
            .context("Missing stream caller origin")?;
        let fd_origin = file_streams::source(
            &mut self
                .metadata
                .as_ref()
                .context("Stream initIDs requires java.base")?
                .borrow_mut(),
            caller,
            origin,
        )?;
        let mut plan = if let Some(p) = self.stream_plans.borrow().get(&owner) {
            p.clone()
        } else {
            file_streams::Plan::new(owner, origin.clone(), fd_origin, self.layout(owner)?)?
        };
        if !plan
            .bindings
            .iter()
            .any(|b| b.constant == constant && &b.caller == origin)
        {
            plan.bindings.push(file_streams::Binding {
                caller: origin.clone(),
                constant,
            });
            plan.bindings.sort_by_key(|b| b.constant);
        }
        self.stream_plans.borrow_mut().insert(owner, plan);
        self.type_checks.set(true);
        Ok(owner)
    }
    fn constant_class_initialization(
        &self,
        caller: &ClassFile,
        site: class_initialization::Site,
    ) -> Result<usize> {
        let &owner = self
            .names
            .get(site.target.as_str())
            .context("Missing executable constant Class initializer")?;
        let caller_id = self.class_id(caller)?;
        let binding = class_initialization::binding(
            &mut self
                .metadata
                .as_ref()
                .context("Constant Class initialization needs verified java.base")?
                .borrow_mut(),
            caller,
            self.source_origins[caller_id]
                .as_ref()
                .context("Missing initialization caller origin")?,
            site,
            owner,
        )?;
        ensure!(
            self.source_origins[owner].as_ref() == Some(&binding.target),
            "Constant Class executable initializer differs from resolved metadata origin"
        );
        self.constant_initialization.borrow_mut().insert(
            (
                binding.site.method.clone(),
                binding.site.descriptor.clone(),
                binding.site.pc,
            ),
            binding,
        );
        Ok(owner)
    }
    fn file_descriptor(
        &self,
        caller: &ClassFile,
        constant: u16,
        operation: file_descriptors::Operation,
    ) -> Result<usize> {
        let &owner = self
            .names
            .get(file_descriptors::OWNER)
            .context("Missing FileDescriptor executable initializer")?;
        let origin = file_descriptors::source(
            &mut self
                .metadata
                .as_ref()
                .context("Descriptor services require java.base")?
                .borrow_mut(),
            operation,
            caller,
            self.source_origins[self.class_id(caller)?]
                .as_ref()
                .context("Missing descriptor caller source")?,
        )?;
        ensure!(
            self.source_origins[owner].as_ref() == Some(&origin),
            "Descriptor initializer origin differs from native binding"
        );
        let previous = self.fd_plan.borrow().clone();
        let mut plan = if let Some(p) = previous {
            p
        } else {
            file_descriptors::Plan::new(owner, origin.clone(), self.layout(owner)?)?
        };
        if !plan
            .bindings
            .iter()
            .any(|b| b.constant == constant && b.caller == origin)
        {
            plan.bindings.push(file_descriptors::Binding {
                operation,
                caller: origin,
                constant,
            });
            plan.bindings.sort_by_key(|b| b.constant);
        }
        *self.fd_plan.borrow_mut() = Some(plan);
        self.type_checks.set(true);
        Ok(owner)
    }
    fn cds(&self, caller: &ClassFile, constant: u16, operation: cds::Operation) -> Result<usize> {
        let &owner = self
            .names
            .get(cds::OWNER)
            .context("Missing executable CDS initializer")?;
        let ci = self.class_id(caller)?;
        let source = self.source_origins[ci]
            .as_ref()
            .context("Missing CDS caller source")?;
        let binding = cds::binding(
            &mut self
                .metadata
                .as_ref()
                .context("CDS requires pinned java.base")?
                .borrow_mut(),
            operation,
            caller,
            source,
            constant,
            owner,
        )?;
        ensure!(
            self.source_origins[owner].as_ref() == Some(&binding.origin),
            "Executable CDS initializer differs from its native binding origin"
        );
        self.cds_bindings
            .borrow_mut()
            .insert((caller.name.clone(), constant), binding);
        self.type_checks.set(true);
        Ok(owner)
    }
    fn string_value(
        &self,
        caller: &ClassFile,
        constant: u16,
        kind: string_values::Kind,
    ) -> Result<string_values::Link> {
        let key = (caller.name.clone(), constant);
        let previous = self.string_values.borrow().get(&key).cloned();
        let binding = if let Some(binding) = previous {
            binding
        } else {
            let source = string_values::source(
                &mut self
                    .metadata
                    .as_ref()
                    .context("String.valueOf needs verified metadata")?
                    .borrow_mut(),
                kind,
            )?;
            let initializer = source
                .initializer
                .map(|origin| {
                    let &class_id = self
                        .names
                        .get(kind.initialization_owner().unwrap())
                        .context("Missing decimal conversion initializer")?;
                    ensure!(
                        self.source_origins[class_id].as_ref() == Some(&origin),
                        "Decimal conversion initializer source changed"
                    );
                    Ok(string_values::Initialization { class_id, origin })
                })
                .transpose()?;
            let caller_origin = self.source_origins[self.class_id(caller)?]
                .as_ref()
                .context("Missing primitive String.valueOf caller source")?
                .clone();
            let concat_plan = kind
                .concat()
                .map(|p| self.concat(caller, constant, p))
                .transpose()?;
            let boolean_literals = if kind == string_values::Kind::Boolean {
                let mut literals = self.strings.borrow_mut();
                Some([
                    literals.intern("false".encode_utf16().collect())?,
                    literals.intern("true".encode_utf16().collect())?,
                ])
            } else {
                None
            };
            let binding = string_values::Binding {
                kind,
                caller: caller_origin,
                constant,
                origin: source.origin,
                concat_plan,
                boolean_literals,
                initializer,
            };
            self.string_values.borrow_mut().insert(key, binding.clone());
            binding
        };
        ensure!(
            binding.kind == kind,
            "Primitive String.valueOf call-site type changed"
        );
        if let Some(plan) = binding.concat_plan {
            Ok(string_values::Link::Concat(
                plan,
                kind.signature(),
                binding.initializer.as_ref().map(|i| i.class_id),
            ))
        } else {
            Ok(string_values::Link::Boolean(
                binding
                    .boolean_literals
                    .context("Missing boolean literal bindings")?,
            ))
        }
    }
    fn string_join(
        &self,
        caller: &ClassFile,
        constant: u16,
        kind: string_join::Kind,
    ) -> Result<string_join::Link> {
        let key = (caller.name.clone(), constant);
        let existing = self.string_joins.borrow().get(&key).cloned();
        let plan = if let Some(plan) = existing {
            plan
        } else {
            let (origin, cs, code_sha256) = string_join::binding(
                &mut self
                    .metadata
                    .as_ref()
                    .context("String.join needs verified metadata")?
                    .borrow_mut(),
                kind,
            )?;
            let caller_origin = self.source_origins[self.class_id(caller)?]
                .as_ref()
                .context("Missing String.join caller source")?
                .clone();
            let mut sites = Vec::new();
            for (i, (owner, name, descriptor)) in kind.callbacks().into_iter().enumerate() {
                sites.push(
                    self.dispatch_symbolic(
                        caller,
                        constant,
                        0xe0 + i as u8,
                        owner.into(),
                        name.into(),
                        descriptor.into(),
                        true,
                    )?
                    .0,
                );
            }
            let id = self.string_joins.borrow().len();
            let plan = string_join::Plan {
                id,
                kind,
                caller: caller_origin,
                constant,
                origin,
                char_sequence_type: cs,
                dispatch_sites: sites,
                source_method: kind.member_name().into(),
                code_sha256,
                native_source_sha256: files::digest_bytes(
                    &[
                        include_bytes!("../../native/runtime/string_join.asm").as_slice(),
                        include_bytes!("../../native/runtime/string_sequence_replace.asm")
                            .as_slice(),
                    ]
                    .concat(),
                )
                .sha256,
                literal_role: if kind == string_join::Kind::Replace {
                    "empty"
                } else {
                    "null"
                }
                .into(),
                original_java_api_body_executed: false,
                null_literal: self.strings.borrow_mut().intern(
                    (if kind == string_join::Kind::Replace {
                        ""
                    } else {
                        "null"
                    })
                    .encode_utf16()
                    .collect(),
                )?,
            };
            self.string_joins.borrow_mut().insert(key, plan.clone());
            plan
        };
        ensure!(plan.kind == kind, "String.join call-site kind changed");
        if kind == string_join::Kind::Replace {
            self.exception_enabled.set(true);
        }
        self.type_checks.set(true);
        let dispatch = self.dispatch.borrow();
        let mut targets = Vec::new();
        let mut owners = Vec::new();
        for site in &plan.dispatch_sites {
            let site = dispatch
                .values()
                .find(|s| s.id == *site)
                .context("Missing String.join callback site")?;
            targets.extend(site.rows.iter().filter_map(|r| r.target));
            owners.extend(site.rows.iter().filter_map(|r| r.receiver_class));
        }
        Ok(string_join::Link {
            id: plan.id,
            signature: self.descriptor(self.loader(caller), kind.invocation_descriptor())?,
            targets,
            owners,
        })
    }
    fn vm_registration(
        &self,
        caller: &ClassFile,
        constant: u16,
        op: super::vm_registration::Operation,
    ) -> Result<usize> {
        let ci = self.class_id(caller)?;
        let owner = *self
            .names
            .get(op.owner())
            .context("Missing original VM class")?;
        let b = super::vm_registration::binding(
            &mut self
                .metadata
                .as_ref()
                .context("VM registration requires metadata")?
                .borrow_mut(),
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing VM caller source")?,
            constant,
            op,
            owner,
        )?;
        ensure!(
            self.source_origins[owner].as_ref() == Some(&b.origin),
            "VM native provider differs from original metadata"
        );
        self.vm_registration
            .borrow_mut()
            .insert((caller.name.clone(), constant), b);
        Ok(owner)
    }
    fn system_registration(&self) -> bool {
        self.vm_bindings
            .borrow()
            .contains_key(&vm::Operation::RegisterNatives)
    }
    fn root_object_constructor(&self, class: &ClassFile) -> Result<bool> {
        let ci = self.class_id(class)?;
        Ok(class.name == "java/lang/Object"
            && class.super_name.is_empty()
            && self.source_origins[ci].as_ref().is_some_and(|o| {
                o.loader == "bootstrap" && o.source_id == "jdk:java.base" && o.generated.is_none()
            })
            && class
                .method("<init>", Some("()V"))?
                .code
                .as_ref()
                .is_some_and(|c| c.bytes == [0xb1] && c.handlers.is_empty()))
    }
    fn object_constructor(&self, caller: &ClassFile) -> Result<()> {
        if let Some(registry) = &self.metadata {
            let mut registry = registry.borrow_mut();
            let id = registry.class("bootstrap", "java/lang/Object")?;
            let types::Type::Class { key, origin, .. } = &registry.types[id] else {
                unreachable!()
            };
            ensure!(
                key.loader == "bootstrap" && origin.source_id == "jdk:java.base",
                "Object constructor needs its verified bootstrap origin"
            );
            let method = registry
                .definition(id)
                .unwrap()
                .method("<init>", Some("()V"))?;
            ensure!(
                method.access == 1
                    && method
                        .code
                        .as_ref()
                        .is_some_and(|c| c.bytes == [0xb1] && c.handlers.is_empty()),
                "Object constructor erasure needs its original empty Java body"
            );
        } else {
            ensure!(
                caller.super_name == "java/lang/Object",
                "Object constructor requires a direct Object subclass"
            );
        }
        Ok(())
    }
    fn direct_object_parent(&self, owner: usize) -> Result<bool> {
        Ok(self
            .classes
            .get(owner)
            .is_some_and(|c| c.super_name == "java/lang/Object"))
    }
    fn root_object_allocation(&self, owner: usize) -> Result<bool> {
        Ok(self
            .classes
            .get(owner)
            .is_some_and(|c| c.name == "java/lang/Object")
            && self
                .source_origins
                .get(owner)
                .and_then(Option::as_ref)
                .is_some_and(|o| o.loader == "bootstrap" && o.source_id == "jdk:java.base"))
    }
    fn primitive_class(&self, caller: &ClassFile) -> Result<()> {
        let mut registry = self
            .metadata
            .as_ref()
            .context("Primitive class lookup requires verified java.base metadata")?
            .borrow_mut();
        let ci = self.class_id(caller)?;
        let origin = self.source_origins[ci]
            .as_ref()
            .context("Missing primitive lookup caller origin")?;
        let binding = mirrors::primitive_binding(&mut registry, caller, origin)?;
        self.primitive_bindings
            .borrow_mut()
            .insert(caller.name.clone(), binding);
        Ok(())
    }
    fn resource_stream(&self, caller: &ClassFile) -> Result<resources::Link> {
        ensure!(
            self.boot_snapshot.is_some(),
            "Class resources require verified --jdk-modules metadata"
        );
        self.type_checks.set(true);
        let id = if let Some(b) = self.resource_bindings.borrow().get(&caller.name) {
            b.id
        } else {
            usize::MAX
        };
        let id = if id != usize::MAX {
            id
        } else {
            let next = self.resource_bindings.borrow().len();
            ensure!(next < 1024, "Resource caller budget exceeded");
            let binding = resources::binding(
                &mut self
                    .metadata
                    .as_ref()
                    .context("Resources require metadata")?
                    .borrow_mut(),
                caller,
                self.loader(caller),
                next,
            )?;
            self.resource_bindings
                .borrow_mut()
                .insert(caller.name.clone(), binding);
            next
        };
        let &owner = self
            .names
            .get("java/io/ByteArrayInputStream")
            .context("Missing JDK byte-array stream constructor dependency")?;
        let class = &self.classes[owner];
        let origin = self.source_origins[owner]
            .as_ref()
            .context("JDK byte-array stream source missing")?;
        ensure!(
            origin.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "Untrusted resource stream implementation"
        );
        let ctor = class.method("<init>", Some("([B)V"))?;
        ensure!(
            ctor.access & (1 | 8 | 0x20 | 0x100 | 0x400) == 1 && ctor.code.is_some(),
            "Resource stream constructor contract changed"
        );
        let mi = class
            .methods
            .iter()
            .position(|m| std::ptr::eq(m, ctor))
            .unwrap();
        self.allocate_class(caller, &class.name)?;
        let mut signature = self.descriptor("bootstrap", resources::DESCRIPTOR)?;
        signature.arguments.insert(0, numeric::Type::BootstrapClass);
        Ok(resources::Link {
            signature,
            class_id: owner,
            constructor: self.ids[owner][mi],
            caller: id,
        })
    }
    fn method_monitor(&self, class: &ClassFile, method: &Method) -> Result<Option<usize>> {
        if method.access & 0x20 == 0 {
            return Ok(None);
        }
        ensure!(
            self.metadata.is_some()
                && !method.name.starts_with('<')
                && method.access & (0x100 | 0x400) == 0,
            "Synchronized execution requires verified metadata and an ordinary Java body"
        );
        let key = (
            class.name.clone(),
            method.name.clone(),
            method.descriptor.clone(),
        );
        if let Some(binding) = self.monitor_methods.borrow().get(&key) {
            return Ok(binding.mirror_type);
        }
        let ci = *self
            .names
            .get(class.name.as_str())
            .context("Missing synchronized owner")?;
        let source = self.source_origins[ci]
            .as_ref()
            .context("Synchronized method source proof missing")?;
        self.type_checks.set(true);
        let mirror_type = if method.access & 8 != 0 {
            Some(self.class_literal(class, &class.name)?)
        } else {
            None
        };
        self.monitor_methods.borrow_mut().insert(
            key,
            monitors::Binding {
                class_name: class.name.clone(),
                loader: self.loader(class).into(),
                method: method.name.clone(),
                descriptor: method.descriptor.clone(),
                static_method: method.access & 8 != 0,
                mirror_type,
                source_sha256: source.sha256.clone(),
            },
        );
        Ok(mirror_type)
    }
    fn type_target(&self, caller: &ClassFile, name: &str) -> Result<(usize, numeric::Type)> {
        self.type_checks.set(true);
        let id = self.class_literal(caller, name)?;
        if name.starts_with("[[") {
            self.typed_array_roots.borrow_mut().insert(id);
        }
        Ok((id, self.static_reference(name, id)?))
    }
    fn get_class(&self, caller: &ClassFile, owner: &str, interface: bool) -> Result<()> {
        self.type_checks.set(true);
        let id = self.class_literal(caller, owner)?;
        let registry = self.metadata.as_ref().unwrap().borrow();
        match &registry.types[id] {
            types::Type::Class { access, .. } => ensure!(
                (access & 0x200 != 0) == interface,
                "Invocation opcode disagrees with defining class/interface kind"
            ),
            types::Type::Array { .. } => ensure!(!interface, "Array owner is not an interface"),
            _ => anyhow::bail!("getClass owner is not a reference type"),
        }
        let mut current = Some(id);
        while let Some(id) = current {
            let types::Type::Class {
                key, superclass, ..
            } = &registry.types[id]
            else {
                break;
            };
            if let Some(method) = registry.definition(id).and_then(|class| {
                class
                    .methods
                    .iter()
                    .find(|m| m.name == "getClass" && m.descriptor == "()Ljava/lang/Class;")
            }) {
                ensure!(
                    key.loader == "bootstrap"
                        && key.name == "java/lang/Object"
                        && method.access & 0x119 == 0x111,
                    "Cannot override or replace final Object.getClass"
                );
            }
            current = *superclass;
        }
        Ok(())
    }
    fn assignable(&self, from: numeric::Type, to: numeric::Type) -> Result<bool> {
        if !from.is_reference() || !to.is_reference() || self.metadata.is_none() {
            return Ok(false);
        }
        let mut registry = self.metadata.as_ref().unwrap().borrow_mut();
        let source = self.metadata_ids(&mut registry, from)?;
        let target = self.metadata_ids(&mut registry, to)?;
        Ok(!source.is_empty()
            && !target.is_empty()
            && source.iter().all(|&source| {
                target
                    .iter()
                    .any(|&target| registry.assignable(source, target))
            }))
    }
    fn reference_join(
        &self,
        left: numeric::Type,
        right: numeric::Type,
    ) -> Result<Option<numeric::Type>> {
        if !left.is_reference() || !right.is_reference() || self.metadata.is_none() {
            return Ok(None);
        }
        if self.assignable(left, right)? {
            return Ok(Some(right));
        }
        if self.assignable(right, left)? {
            return Ok(Some(left));
        }
        self.type_checks.set(true);
        let mut registry = self.metadata.as_ref().unwrap().borrow_mut();
        let mut members = self.metadata_ids(&mut registry, left)?;
        members.extend(self.metadata_ids(&mut registry, right)?);
        members.sort_unstable();
        members.dedup();
        ensure!(
            members.len() <= 64,
            "Reference join exceeds alternative budget"
        );
        let mut joins = self.joins.borrow_mut();
        let next = joins.len();
        ensure!(next < 4096, "Reference join table exceeds budget");
        let id = *joins.entry(members).or_insert(next);
        Ok(Some(numeric::Type::ReferenceJoin(id)))
    }
    fn concat(&self, class: &ClassFile, index: u16, plan: concat::Plan) -> Result<usize> {
        let mut plans = self.concats.borrow_mut();
        let key = (class.name.clone(), index);
        if let Some((id, previous)) = plans.get(&key) {
            ensure!(*previous == plan, "Concat site changed within compilation");
            return Ok(*id);
        }
        ensure!(plans.len() < 65536, "Concat plan count exceeds budget");
        let id = plans.len();
        plans.insert(key, (id, plan));
        Ok(id)
    }
    fn string_literal(&self, class: &ClassFile, index: u16) -> Result<usize> {
        let value = class
            .string_literal(index)?
            .context("Expected string constant")?;
        if let Some(name) = super::class_for_name::candidate(&value) {
            self.lookup_literals
                .borrow_mut()
                .insert((self.loader(class).into(), name));
        }
        self.strings.borrow_mut().intern(value)
    }
    fn lambda_capture(
        &self,
        caller: &ClassFile,
        index: u16,
    ) -> Result<(usize, numeric::Signature)> {
        if caller.dynamic_site(index)?.bootstrap.owner == super::records::BOOTSTRAP_OWNER {
            let plan = super::records::Plan::parse(caller, index)?;
            let source = self.source_origins[self.class_id(caller)?]
                .as_ref()
                .context("Missing record source proof")?;
            let binding = plan.binding(
                &mut self
                    .metadata
                    .as_ref()
                    .context("Record lowering requires verified metadata")?
                    .borrow_mut(),
                source,
            )?;
            let &ci = self
                .names
                .get(plan.class_name.as_str())
                .context("Missing generated record dependency")?;
            ensure!(
                self.source_origins[ci].as_ref() == Some(&binding.generated),
                "Generated record definition conflicts with its source proof"
            );
            let mi = self.classes[ci]
                .methods
                .iter()
                .position(|m| m.name == super::records::METHOD && m.descriptor == plan.descriptor)
                .context("Missing record helper method")?;
            self.record_sites
                .borrow_mut()
                .insert((caller.name.clone(), index), binding);
            self.type_checks.set(true);
            return Ok((
                self.ids[ci][mi],
                self.descriptor(self.loader(caller), &plan.descriptor)?,
            ));
        }
        let plan = lambdas::Plan::parse(caller, index)?;
        plan.validate(
            &mut self
                .metadata
                .as_ref()
                .context("Lambda needs verified metadata")?
                .borrow_mut(),
            self.loader(caller),
        )?;
        let &host_ci = self
            .names
            .get(caller.name.as_str())
            .context("Missing lambda creator")?;
        let host = self.source_origins[host_ci]
            .as_ref()
            .context("Lambda creator has no source proof")?;
        ensure!(
            host.generated.is_none(),
            "Lambda creator must be original bytecode"
        );
        let &ci = self
            .names
            .get(plan.class_name.as_str())
            .context("Missing generated capture dependency")?;
        let (_, expected_origin) = plan.definition(host)?;
        ensure!(
            self.source_origins[ci].as_ref() == Some(&expected_origin),
            "Lambda definition conflicts with its compiler-owned source proof"
        );
        let method = self.classes[ci].method(lambdas::FACTORY, Some(&plan.factory_descriptor))?;
        let mi = self.classes[ci]
            .methods
            .iter()
            .position(|m| std::ptr::eq(m, method))
            .unwrap();
        self.lambda_sites
            .borrow_mut()
            .insert((caller.name.clone(), index), plan.clone());
        self.type_checks.set(true);
        Ok((
            self.ids[ci][mi],
            self.descriptor(self.loader(caller), &plan.factory_descriptor)?,
        ))
    }
    fn require_non_null(&self) -> Result<()> {
        let mut registry = self
            .metadata
            .as_ref()
            .context("Null guard requires pinned java.base")?
            .borrow_mut();
        let id = registry.class("bootstrap", "java/util/Objects")?;
        let types::Type::Class { key, origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "Null guard does not name the pinned java.base Objects"
        );
        let member = registry.definition(id).unwrap().method(
            "requireNonNull",
            Some("(Ljava/lang/Object;)Ljava/lang/Object;"),
        )?;
        ensure!(
            member.access & (1 | 8 | 0x100 | 0x400) == 9 && member.code.is_some(),
            "Null guard member contract changed"
        );
        self.null_guards.set(true);
        Ok(())
    }
    fn vm_intrinsic(&self, caller: &ClassFile, operation: vm::Operation) -> Result<()> {
        if operation == vm::Operation::RegisterNatives {
            ensure!(
                caller.name == "java/lang/System" && self.loader(caller) == "bootstrap",
                "System.registerNatives is private to its verified bootstrap System caller"
            );
            let ci = self.class_id(caller)?;
            let source = self.source_origins[ci]
                .as_ref()
                .context("Missing System registration caller origin")?;
            let mut registry = self
                .metadata
                .as_ref()
                .context("System registration needs verified java.base")?
                .borrow_mut();
            let binding = vm::binding(&mut registry, "bootstrap", operation)?;
            vm::registration_caller(caller, source, &binding)?;
            let mut bindings = self.vm_bindings.borrow_mut();
            for op in [
                vm::Operation::CurrentTimeMillis,
                vm::Operation::NanoTime,
                vm::Operation::ArrayCopy,
            ] {
                bindings.insert(op, vm::binding(&mut registry, "bootstrap", op)?);
            }
            bindings.insert(operation, binding);
        }
        if matches!(
            operation,
            vm::Operation::ArrayCopy | vm::Operation::RegisterNatives
        ) {
            self.type_checks.set(true);
        }
        if !self.vm_bindings.borrow().contains_key(&operation) {
            let binding = vm::binding(
                &mut self
                    .metadata
                    .as_ref()
                    .context("VM native bindings require verified java.base metadata")?
                    .borrow_mut(),
                self.loader(caller),
                operation,
            )?;
            self.vm_bindings.borrow_mut().insert(operation, binding);
        }
        Ok(())
    }
    fn module_intrinsic(
        &self,
        _: &ClassFile,
        op: modules::Operation,
    ) -> Result<(numeric::Signature, Option<usize>)> {
        ensure!(
            !op.uses_layer() || self.boot_snapshot.is_some(),
            "Module layers require verified --jdk-modules inputs"
        );
        let mut registry = self
            .metadata
            .as_ref()
            .context("Module operations require verified java.base metadata")?
            .borrow_mut();
        let (binding, mut signature) = modules::binding(&mut registry, op)?;
        self.module_bindings.borrow_mut().insert(op, binding);
        self.type_checks.set(true);
        let factory = if op == modules::Operation::LayerFindModule {
            let &owner = self
                .names
                .get("java/util/Optional")
                .context("Missing pinned Optional factory dependency")?;
            let method = self.classes[owner].method(
                "ofNullable",
                Some("(Ljava/lang/Object;)Ljava/util/Optional;"),
            )?;
            ensure!(
                self.loader(&self.classes[owner]) == "bootstrap"
                    && method.access & (1 | 8 | 0x100 | 0x400) == 9,
                "Untrusted Optional factory"
            );
            let mi = self.classes[owner]
                .methods
                .iter()
                .position(|m| std::ptr::eq(m, method))
                .unwrap();
            signature.result = numeric::Type::LinkedObject(owner);
            Some(self.ids[owner][mi])
        } else {
            None
        };
        Ok((signature, factory))
    }
    fn assertion_status(&self) -> Result<()> {
        ensure!(
            self.metadata.is_some(),
            "Assertion queries require verified metadata"
        );
        self.assertion_queries.set(true);
        Ok(())
    }
    fn class_constant(&self, caller: &ClassFile, name: &str) -> Result<usize> {
        let id = self.class_literal(caller, name)?;
        self.reflect_literals.borrow_mut().insert(id);
        if self.loader(caller) != "bootstrap" {
            self.constructor_literals.borrow_mut().insert(id);
        }
        Ok(id)
    }
    fn class_literal(&self, caller: &ClassFile, name: &str) -> Result<usize> {
        let mut registry = self
            .metadata
            .as_ref()
            .context("Class mirrors require verified --metadata-lock and --jdk-base inputs")?
            .borrow_mut();
        registry.class("bootstrap", "java/lang/Class")?;
        registry.class("bootstrap", "java/lang/String")?;
        let id = registry.literal(self.loader(caller), name)?;
        let mut element = id;
        while let types::Type::Array { component } = registry.types[element] {
            element = component;
        }
        if let types::Type::Class { key, access, .. } = &registry.types[element] {
            ensure!(
                access & 1 != 0
                    || (key.loader == self.loader(caller)
                        && package(&key.name) == package(&caller.name)),
                "Class literal access denied: {name}"
            );
        }
        Ok(id)
    }
    fn resolve(&self, caller: &ClassFile, constant: u16) -> Result<(usize, numeric::Signature)> {
        let (ci, mi) = self.method_identity(caller, constant)?;
        let class = &self.classes[ci];
        let method = &class.methods[mi];
        ensure!(
            method.access & 8 != 0 && !method.name.starts_with('<'),
            "invokestatic must select an ordinary static method"
        );
        self.check_member_access(caller, class, method.access)?;
        Ok((self.ids[ci][mi], self.signature(class, method)?))
    }
    fn class_id(&self, class: &ClassFile) -> Result<usize> {
        self.names
            .get(class.name.as_str())
            .copied()
            .context("Missing program class identity")
    }
    fn field(&self, caller: &ClassFile, constant: u16) -> Result<numeric::LinkedField> {
        let (ci, index) = self.field_identity(caller, constant)?;
        let class = &self.classes[ci];
        let field = &class.field_info[index];
        ensure!(
            class.name != "java/lang/System"
                || caller.name == "java/lang/System"
                || self.system_startup.is_some(),
            "System public/static field access needs completed Java startup phases; field {}",
            field.name
        );
        let descriptor = &field.descriptor;
        ensure!(field.access & 8 != 0, "Expected static field");
        self.check_member_access(caller, class, field.access)?;
        Ok(numeric::LinkedField {
            owner: ci,
            index,
            ty: self
                .descriptor(self.loader(class), &format!("(){descriptor}"))?
                .result,
            access: field.access,
            narrow: descriptor.as_bytes()[0],
        })
    }
    fn signature(&self, class: &ClassFile, method: &Method) -> Result<numeric::Signature> {
        let mut signature = self.descriptor(self.loader(class), &method.descriptor)?;
        if method.access & 8 == 0 {
            signature
                .arguments
                .insert(0, numeric::Type::LinkedObject(self.class_id(class)?));
        }
        signature.check_arguments()?;
        Ok(signature)
    }
    fn object_class(&self, caller: &ClassFile, name: &str) -> Result<usize> {
        let &owner = self
            .names
            .get(name)
            .with_context(|| format!("Missing linked object class {name}"))?;
        self.validate_executable(owner)?;
        if self.classes[owner].access & 0x200 != 0 {
            self.covariant_arrays.set(true);
            self.type_checks.set(true);
        }
        ensure!(
            self.classes[owner].interfaces == 0 || self.metadata.is_some(),
            "Interface hierarchies require verified metadata"
        );
        self.check_access(caller, &self.classes[owner], 1)?;
        Ok(owner)
    }
    fn allocate_class(&self, caller: &ClassFile, name: &str) -> Result<usize> {
        let owner = self.object_class(caller, name)?;
        ensure!(
            self.classes[owner].access & (0x200 | 0x400) == 0,
            "new requires a concrete class, not an interface or abstract class"
        );
        Ok(owner)
    }
    fn interface_call(&self, caller: &ClassFile, constant: u16) -> Result<numeric::InterfaceLink> {
        self.dispatch_call(caller, constant, true)
    }
    fn inherited_virtual(
        &self,
        caller: &ClassFile,
        constant: u16,
    ) -> Result<Option<numeric::InterfaceLink>> {
        let (owner, name, descriptor) = caller.method_reference(constant)?;
        let &ci = self
            .names
            .get(owner.as_str())
            .context("Missing virtual owner")?;
        if !self.hierarchy
            && self.classes[ci]
                .methods
                .iter()
                .any(|m| m.name == name && m.descriptor == descriptor)
        {
            return Ok(None);
        }
        self.dispatch_call(caller, constant, false).map(Some)
    }
    fn special_call(
        &self,
        caller: &ClassFile,
        constant: u16,
    ) -> Result<Option<numeric::InterfaceLink>> {
        if self.metadata.is_none() {
            return Ok(None);
        }
        self.special_dispatch(caller, constant).map(Some)
    }
    fn instance(
        &self,
        caller: &ClassFile,
        constant: u16,
        constructor: bool,
    ) -> Result<(usize, numeric::Signature)> {
        let (owner, name, descriptor) = caller.method_reference(constant)?;
        ensure!(
            !self.primordial || !super::thread_bootstrap::entry(&owner, &name, Some(&descriptor)),
            "Primordial constructor specialization cannot serve a Java allocation call site"
        );
        let ci = self.object_class(caller, &owner)?;
        let class = &self.classes[ci];
        let method = class.method(&name, Some(&descriptor))?;
        ensure!(
            method.access & 8 == 0 && constructor == (name == "<init>"),
            "Wrong instance invocation kind"
        );
        if constructor
            && method.access & 4 != 0
            && (self.loader(caller) != self.loader(class)
                || package(&caller.name) != package(&class.name))
        {
            self.check_class_access(caller, class)?;
            let b = super::protected_constructors::prove(
                &mut self
                    .metadata
                    .as_ref()
                    .context("Protected constructor needs loader-aware source metadata")?
                    .borrow_mut(),
                caller,
                self.loader(caller),
                class,
                self.loader(class),
                constant,
            )?;
            let caller_ci = self.class_id(caller)?;
            ensure!(
                self.source_origins[caller_ci].as_ref() == Some(&b.caller)
                    && self.source_origins[ci].as_ref() == Some(&b.owner),
                "Protected constructor source differs from executable provider"
            );
            self.protected_constructors
                .borrow_mut()
                .insert((caller.name.clone(), constant), b);
        } else {
            self.check_access(caller, class, method.access)?;
        }
        let mi = class
            .methods
            .iter()
            .position(|m| std::ptr::eq(m, method))
            .context("Missing instance method identity")?;
        Ok((self.ids[ci][mi], self.signature(class, method)?))
    }
    fn instance_field(
        &self,
        caller: &ClassFile,
        constant: u16,
    ) -> Result<numeric::LinkedInstanceField> {
        let (ci, index) = self.field_identity(caller, constant)?;
        let class = &self.classes[ci];
        let field = &class.field_info[index];
        ensure!(field.access & 8 == 0, "Expected instance field");
        self.check_member_access(caller, class, field.access)?;
        let mapping = if self.hierarchy {
            Some(self.field_map(ci, index, ci)?)
        } else {
            None
        };
        Ok(numeric::LinkedInstanceField {
            owner: ci,
            index,
            offset: numeric::field_offset(class, index)?,
            ty: self
                .descriptor(self.loader(class), &format!("(){}", field.descriptor))?
                .result,
            access: field.access,
            narrow: field.descriptor.as_bytes()[0],
            receiver: numeric::Type::LinkedObject(ci),
            mapping,
            storage_bytes: if self.hierarchy {
                hierarchy::storage_bytes(&field.descriptor)?
            } else {
                8
            },
        })
    }
    fn field_receivers(&self, field: &numeric::LinkedInstanceField) -> Result<Vec<usize>> {
        if let Some(id) = field.mapping {
            return Ok(self
                .field_maps
                .borrow()
                .values()
                .find(|m| m.id == id)
                .context("Missing field map")?
                .rows
                .iter()
                .map(|row| row.receiver_class)
                .collect());
        }
        Ok(vec![field.owner])
    }
    fn typed_array(
        &self,
        caller: &ClassFile,
        descriptor: &str,
        dimensions: u8,
    ) -> Result<(usize, numeric::Type)> {
        super::typed_arrays::rank(descriptor, dimensions)?;
        let id = self.class_literal(caller, descriptor)?;
        self.type_checks.set(true);
        self.covariant_arrays.set(true);
        self.typed_array_roots.borrow_mut().insert(id);
        let ci = self.class_id(caller)?;
        self.typed_array_sites.borrow_mut().insert(
            (caller.name.clone(), descriptor.into(), dimensions),
            super::typed_arrays::Site {
                caller: self.source_origins[ci]
                    .as_ref()
                    .context("Missing typed array caller source")?
                    .clone(),
                descriptor: descriptor.into(),
                dimensions,
                type_id: id,
            },
        );
        Ok((id, self.static_reference(descriptor, id)?))
    }
    fn is_array(&self, ty: numeric::Type) -> Result<bool> {
        let mut registry = self
            .metadata
            .as_ref()
            .context("Array identity needs metadata")?
            .borrow_mut();
        let ids = self.metadata_ids(&mut registry, ty)?;
        let yes = !ids.is_empty()
            && ids
                .iter()
                .all(|&id| matches!(registry.types[id], types::Type::Array { .. }));
        if yes {
            self.typed_array_roots.borrow_mut().extend(ids);
            self.type_checks.set(true);
        }
        Ok(yes)
    }
    fn primitive_array(&self, ty: numeric::Type, kind: numeric::ArrayKind) -> Result<bool> {
        let mut registry = self
            .metadata
            .as_ref()
            .context("Array identity needs metadata")?
            .borrow_mut();
        let ids = self.metadata_ids(&mut registry, ty)?;
        let target = registry.field("bootstrap", kind.descriptor())?;
        let boolean = registry.field("bootstrap", "[Z")?;
        Ok(!ids.is_empty()
            && ids
                .into_iter()
                .all(|id| id == target || (kind == numeric::ArrayKind::Byte && id == boolean)))
    }
    fn array_component(&self, ty: numeric::Type) -> Result<Option<numeric::Type>> {
        let values = {
            let mut registry = self
                .metadata
                .as_ref()
                .context("Array components need metadata")?
                .borrow_mut();
            let ids = self.metadata_ids(&mut registry, ty)?;
            if ids.is_empty() {
                return Ok(None);
            }
            let mut values = Vec::new();
            for id in ids {
                let types::Type::Array { component } = registry.types[id] else {
                    return Ok(None);
                };
                if matches!(registry.types[component], types::Type::Primitive { .. }) {
                    return Ok(None);
                }
                self.typed_array_roots.borrow_mut().insert(id);
                let name = match &registry.types[component] {
                    types::Type::Class { key, .. } => key.name.clone(),
                    _ => super::typed_arrays::descriptor(&registry, component),
                };
                values.push(self.static_reference(&name, component)?);
            }
            values
        };
        let mut result = values[0];
        for other in values.into_iter().skip(1) {
            if result != other {
                result = self
                    .reference_join(result, other)?
                    .context("Incompatible array component join")?;
            }
        }
        Ok(Some(result))
    }
    fn covariant_arrays(&self) -> bool {
        let enabled = self.covariant_arrays.get();
        if enabled {
            self.type_checks.set(true);
        }
        enabled
    }
    fn constructor_parent(&self, owner: usize, expected: usize) -> Result<bool> {
        Ok(self
            .classes
            .get(owner)
            .zip(self.classes.get(expected))
            .is_some_and(|(class, parent)| class.super_name == parent.name))
    }
    fn protected_constructor_receiver(
        &self,
        caller: &ClassFile,
        constant: u16,
    ) -> Result<Option<usize>> {
        self.protected_constructors
            .borrow()
            .contains_key(&(caller.name.clone(), constant))
            .then(|| self.class_id(caller))
            .transpose()
    }
}
impl<'a> Linker<'a> {
    fn needs_class_lookup(&self) -> bool {
        self.lookup_vm_fixture || !self.lookup_bindings.borrow().is_empty()
    }
    fn needs_lookup_initializers(&self) -> bool {
        self.lookup_vm_fixture
            || self
                .lookup_bindings
                .borrow()
                .values()
                .any(|b| !b.bootstrap_lookup)
    }
    fn prepare_class_loaders(&self) -> Result<()> {
        if self.class_loaders.borrow().is_some() {
            return Ok(());
        }
        let loader = *self
            .names
            .get(super::class_loaders::LOADER)
            .context("Missing ClassLoader definition")?;
        let layout = self.layout(loader)?;
        let mut registry = self
            .metadata
            .as_ref()
            .context("Class loader field requires java.base")?
            .borrow_mut();
        for class in self.classes {
            registry.class(self.loader(class), &class.name)?;
        }
        let plan = super::class_loaders::Plan::new(&mut registry, layout)?;
        ensure!(
            self.source_origins[loader].as_ref() == Some(&plan.loader_origin),
            "ClassLoader executable definition mismatch"
        );
        *self.class_loaders.borrow_mut() = Some(plan);
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok(())
    }
    fn prepare_windows_startup(&self) -> Result<()> {
        if self.windows_startup.borrow().is_some() {
            return Ok(());
        }
        let owner = *self
            .names
            .get(super::windows_startup::OWNER)
            .context("Missing Win32ErrorMode definition")?;
        let plan = super::windows_startup::Plan::new(
            &mut self
                .metadata
                .as_ref()
                .context("Windows startup requires java.base")?
                .borrow_mut(),
            owner,
        )?;
        ensure!(
            self.source_origins[owner].as_ref() == Some(&plan.origin),
            "Windows native executable source mismatch"
        );
        *self.windows_startup.borrow_mut() = Some(plan);
        Ok(())
    }
    fn prepare_access_context(&self) -> Result<()> {
        if self.access_context.borrow().is_some() {
            return Ok(());
        }
        let mut ids = Vec::new();
        for name in [
            super::access_context::OWNER,
            super::access_context::CONTEXT,
            "java/lang/Thread",
            super::access_context::DOMAIN,
        ] {
            ids.push(
                *self
                    .names
                    .get(name)
                    .context("Missing access context VM dependency")?,
            );
        }
        let domain_layout = self.layout(ids[3])?;
        let mut registry = self
            .metadata
            .as_ref()
            .context("Access contexts require java.base")?
            .borrow_mut();
        // VM domain assignment precedes execution. Include every loaded
        // definition, even if its methods are not part of this entry closure.
        for class in self.classes {
            registry.class(self.loader(class), &class.name)?;
        }
        let plan = super::access_context::Plan::new(
            &mut registry,
            [ids[0], ids[1], ids[2], ids[3]],
            domain_layout,
        )?;
        self.typed_array_roots
            .borrow_mut()
            .insert(plan.domain_array);
        if self.thread_natives.borrow().is_none() {
            *self.thread_natives.borrow_mut() =
                Some(super::thread_natives::Plan::new(&mut registry, ids[2])?);
        }
        *self.access_context.borrow_mut() = Some(plan);
        self.exception_enabled.set(true);
        self.type_checks.set(true);
        Ok(())
    }
    fn prepare_vm_properties(&self, ci: usize) -> Result<()> {
        let mut plan = self.vm_property_plan.borrow_mut();
        if plan.is_none() {
            *plan = Some(super::vm_properties::Plan::prepare(
                &mut self
                    .metadata
                    .as_ref()
                    .context("VM properties require java.base")?
                    .borrow_mut(),
                ci,
                self.vm_profile
                    .clone()
                    .context("VM properties require a frozen image profile")?,
                |s| self.strings.borrow_mut().intern(s.encode_utf16().collect()),
            )?);
        }
        ensure!(
            plan.as_ref().unwrap().class_id == ci,
            "Raw VM caller identity changed"
        );
        Ok(())
    }
    fn bind_builder_snapshot_in(
        &self,
        registry: &mut types::Registry<'_>,
        caller: &ClassFile,
        constant: u16,
    ) -> Result<(numeric::Signature, usize)> {
        let owner = *self
            .names
            .get(super::builder_snapshot::OWNER)
            .context("Missing builder definition")?;
        registry.class("bootstrap", super::builder_snapshot::OWNER)?;
        let layout = self.layout_in(registry, owner)?;
        let mut plan = self.builder_snapshot.borrow_mut();
        if plan.is_none() {
            *plan = Some(super::builder_snapshot::Plan::prepare(
                registry, owner, &layout,
            )?);
        }
        let p = plan.as_mut().unwrap();
        ensure!(
            self.source_origins[owner].as_ref() == Some(&p.origin),
            "Builder layout differs from source proof"
        );
        let ci = numeric::StaticLinker::class_id(self, caller)?;
        p.bind(
            caller,
            self.source_origins[ci]
                .as_ref()
                .context("Missing builder caller")?,
            constant,
        )?;
        self.type_checks.set(true);
        Ok((p.signature(), owner))
    }
    fn record_identity_hash(
        &self,
        registry: &mut types::Registry<'_>,
        caller: &ClassFile,
        constant: u16,
        kind: super::identity_hash::Kind,
    ) -> Result<()> {
        let ci = numeric::StaticLinker::class_id(self, caller)?;
        let source = self.source_origins[ci]
            .as_ref()
            .context("Missing identity hash caller source")?;
        let binding = super::identity_hash::binding(registry, caller, source, constant, kind)?;
        if kind != super::identity_hash::Kind::SystemIdentity {
            let object = self
                .names
                .get("java/lang/Object")
                .context("Missing executable Object provider")?;
            ensure!(
                self.source_origins[*object].as_ref() == Some(&binding.origin),
                "Native Object hash provider differs from metadata source"
            );
        }
        self.identity_hashes
            .borrow_mut()
            .insert((caller.name.clone(), constant, kind), binding);
        Ok(())
    }
    fn loader(&self, class: &ClassFile) -> &str {
        self.names
            .get(class.name.as_str())
            .and_then(|ci| self.source_origins[*ci].as_ref())
            .map_or(self.metadata_loader, |origin| origin.loader.as_str())
    }
    fn bootstrap_execution(&self) -> bool {
        self.source_origins
            .iter()
            .flatten()
            .any(|origin| origin.loader == "bootstrap")
    }
    fn check_access(&self, caller: &ClassFile, owner: &ClassFile, access: u16) -> Result<()> {
        self.check_class_access(caller, owner)?;
        self.check_member_access(caller, owner, access)
    }
    fn check_class_access(&self, caller: &ClassFile, owner: &ClassFile) -> Result<()> {
        if let Some(metadata) = &self.metadata {
            let mut registry = metadata.borrow_mut();
            let id = registry.class(self.loader(caller), &owner.name)?;
            let types::Type::Class { key, .. } = &registry.types[id] else {
                unreachable!()
            };
            ensure!(
                key.loader == self.loader(owner),
                "Executable class resolved through another defining loader"
            );
        }
        if caller.name != owner.name {
            let same_package = self.loader(caller) == self.loader(owner)
                && package(&caller.name) == package(&owner.name);
            ensure!(
                owner.access & 1 != 0 || same_package,
                "Cross-package access to a nonpublic class"
            );
        }
        Ok(())
    }
    fn check_member_access(
        &self,
        caller: &ClassFile,
        owner: &ClassFile,
        access: u16,
    ) -> Result<()> {
        let same_package = self.loader(caller) == self.loader(owner)
            && package(&caller.name) == package(&owner.name);
        let lookup = self.lambda_lookup_host(caller).unwrap_or(caller);
        let record_super_constructor = access == 4
            && owner.name == "java/lang/Record"
            && self.loader(owner) == "bootstrap"
            && caller.super_name == owner.name
            && caller.record_components.is_some()
            && owner
                .methods
                .iter()
                .filter(|m| m.access == 4)
                .all(|m| m.name == "<init>" && m.descriptor == "()V");
        let mut nestmate = false;
        if access & 2 != 0
            && lookup.name != owner.name
            && same_package
            && let Some(registry) = &self.metadata
            && let Some(proof) = nests::prove(
                &mut registry.borrow_mut(),
                self.loader(lookup),
                &lookup.name,
                self.loader(owner),
                &owner.name,
            )?
        {
            self.nest_access
                .borrow_mut()
                .insert((caller.name.clone(), owner.name.clone()), proof);
            nestmate = true;
        }
        ensure!(
            caller.name == owner.name
                || record_super_constructor
                || nestmate
                || self.lambda_lookup_host(caller).is_some_and(
                    |host| host.name == owner.name && self.loader(host) == self.loader(owner)
                )
                || (access & 2 == 0 && (access & 1 != 0 || same_package)),
            "Member access denied (private access needs reciprocal nest membership; cross-package protected access is not implemented)"
        );
        Ok(())
    }
    fn lambda_lookup_host(&self, caller: &ClassFile) -> Option<&ClassFile> {
        let origin = self.source_origins[*self.names.get(caller.name.as_str())?].as_ref()?;
        let proof = origin.generated.as_ref()?;
        let ci = *self.names.get(proof.host_class.as_str())?;
        let host_origin = self.source_origins[ci].as_ref()?;
        ((proof.generator == "boom-lambda" && origin.source_id == "boom:lambda-v1"
            || proof.generator == "boom-record" && origin.source_id == "boom:record-v1")
            && proof.abi == 1
            && origin.loader == proof.host_loader
            && host_origin.loader == proof.host_loader
            && host_origin.source_id == proof.host_source_id
            && host_origin.sha256 == proof.host_sha256
            && host_origin.generated.is_none())
        .then_some(&self.classes[ci])
    }
    fn special_dispatch(
        &self,
        caller: &ClassFile,
        constant: u16,
    ) -> Result<numeric::InterfaceLink> {
        let key = (caller.name.clone(), constant, 0xb7);
        let (owner, name, descriptor, interface) = caller.special_method_reference(constant)?;
        let lookup_caller = self.lambda_lookup_host(caller).unwrap_or(caller);
        ensure!(
            !name.starts_with('<'),
            "Special dispatch does not replace constructor verification"
        );
        let &caller_ci = self
            .names
            .get(lookup_caller.name.as_str())
            .context("Missing special caller")?;
        if !self.dispatch.borrow().contains_key(&key) {
            let &symbolic_ci = self
                .names
                .get(owner.as_str())
                .context("Special owner requires executable definition")?;
            self.check_access(caller, &self.classes[symbolic_ci], 1)?;
            let mut registry = self.metadata.as_ref().unwrap().borrow_mut();
            let symbolic = registry.class(self.loader(caller), &owner)?;
            let current = registry.class(self.loader(caller), &lookup_caller.name)?;
            if interface {
                ensure!(
                    owner == lookup_caller.name || lookup_caller.interface_names.contains(&owner),
                    "Special interface invocation must name the current or a direct superinterface"
                );
            } else {
                ensure!(
                    registry.assignable(current, symbolic),
                    "Special class invocation must name the current class or an ancestor"
                );
            }
            let resolved =
                hierarchy::resolve_method(&registry, symbolic, &name, &descriptor, interface)?;
            ensure!(
                resolved.access & 8 == 0,
                "invokespecial cannot select static methods"
            );
            let types::Type::Class { key: declared, .. } = &registry.types[resolved.owner] else {
                unreachable!()
            };
            let &declared_ci = self
                .names
                .get(declared.name.as_str())
                .context("Special resolved member requires executable provider")?;
            self.check_member_access(caller, &self.classes[declared_ci], resolved.access)?;
            let lookup = if !interface && current != symbolic && lookup_caller.access & 0x20 != 0 {
                registry.class(self.loader(caller), &lookup_caller.super_name)?
            } else {
                symbolic
            };
            let selection = hierarchy::select_special(&registry, lookup, &name, &descriptor)?;
            let (target, error, native_identity) = match selection {
                hierarchy::Selection::Method { member } => {
                    let types::Type::Class { key, .. } = &registry.types[member.owner] else {
                        unreachable!()
                    };
                    let &ci = self
                        .names
                        .get(key.name.as_str())
                        .context("Selected special member requires executable provider")?;
                    if super::identity_hash::object_member(
                        &key.name,
                        &member.name,
                        &member.descriptor,
                    ) {
                        self.record_identity_hash(
                            &mut registry,
                            caller,
                            constant,
                            super::identity_hash::Kind::ObjectDefault,
                        )?;
                        (None, 0, true)
                    } else {
                        (Some(self.ids[ci][member.index]), 0, false)
                    }
                }
                hierarchy::Selection::IncompatibleClassChange => (None, 13, false),
                hierarchy::Selection::AbstractMethod => (None, 14, false),
                hierarchy::Selection::IllegalAccess => (None, 15, false),
            };
            let mut rows = Vec::new();
            for (ci, class) in self.classes.iter().enumerate() {
                if class.access & 0x600 != 0 {
                    continue;
                }
                let receiver = registry.class(self.loader(class), &class.name)?;
                if registry.assignable(receiver, current) {
                    rows.push(dispatch::Row {
                        receiver_class: Some(ci),
                        receiver_type: receiver,
                        target,
                        error,
                        runtime_string: None,
                        runtime_identity_hash: native_identity,
                        runtime_builder_snapshot: false,
                        runtime_reflection: None,
                    });
                }
            }
            ensure!(
                rows.len() <= 4096 && self.dispatch.borrow().len() < 4096,
                "Special dispatch exceeds budget"
            );
            let id = self.dispatch.borrow().len();
            self.dispatch.borrow_mut().insert(
                key.clone(),
                dispatch::Site {
                    id,
                    caller: caller.name.clone(),
                    constant,
                    owner,
                    name,
                    descriptor: descriptor.clone(),
                    interface,
                    invocation: "invokespecial".into(),
                    rows,
                    array_identity_hash: None,
                },
            );
            self.type_checks.set(true);
        }
        let sites = self.dispatch.borrow();
        let site = &sites[&key];
        let mut sig = self.descriptor(self.loader(caller), &descriptor)?;
        sig.arguments
            .insert(0, numeric::Type::LinkedObject(caller_ci));
        sig.check_arguments()?;
        Ok((
            site.id,
            sig,
            site.rows.iter().filter_map(|row| row.target).collect(),
            site.rows
                .iter()
                .filter_map(|row| row.receiver_class)
                .collect(),
        ))
    }
    fn method_identity(&self, caller: &ClassFile, constant: u16) -> Result<(usize, usize)> {
        let (owner, name, descriptor, interface) = caller.static_method_reference(constant)?;
        let &symbolic = self
            .names
            .get(owner.as_str())
            .context("Missing symbolic method owner")?;
        ensure!(
            (self.classes[symbolic].access & 0x200 != 0) == interface,
            "Static method reference class/interface kind mismatch"
        );
        self.check_access(caller, &self.classes[symbolic], 1)?;
        if let Some(metadata) = &self.metadata {
            let mut registry = metadata.borrow_mut();
            let id = registry.class(self.loader(caller), &owner)?;
            let member = hierarchy::resolve_method(&registry, id, &name, &descriptor, interface)?;
            let types::Type::Class { key, .. } = &registry.types[member.owner] else {
                unreachable!()
            };
            let &ci = self
                .names
                .get(key.name.as_str())
                .context("Resolved method requires executable declaring class")?;
            ensure!(
                key.loader == self.loader(&self.classes[ci]),
                "Resolved method has unsupported defining loader"
            );
            return Ok((ci, member.index));
        }
        let mi = self.classes[symbolic]
            .methods
            .iter()
            .position(|m| m.name == name && m.descriptor == descriptor)
            .context("Missing declared method; inherited methods require metadata")?;
        Ok((symbolic, mi))
    }
    fn validate_executable(&self, ci: usize) -> Result<()> {
        let class = &self.classes[ci];
        validate_provided_class(class, self.source_origins[ci].as_ref())?;
        if class.super_name == "java/lang/Object" {
            return Ok(());
        }
        let mut registry = self
            .metadata
            .as_ref()
            .context("Superclass execution requires verified metadata")?
            .borrow_mut();
        let mut id = registry.class(self.loader(class), &class.name)?;
        let mut depth = 0;
        loop {
            ensure!(depth < 128, "Executable hierarchy exceeds depth budget");
            depth += 1;
            let types::Type::Class {
                key, superclass, ..
            } = &registry.types[id]
            else {
                unreachable!()
            };
            if key.loader == "bootstrap" && key.name == "java/lang/Object" {
                break;
            }
            ensure!(
                self.names
                    .get(key.name.as_str())
                    .is_some_and(|&ci| key.loader == self.loader(&self.classes[ci])),
                "Superclass {} requires its own executable provider",
                key.name
            );
            let ci = self.names[key.name.as_str()];
            validate_provided_class(&self.classes[ci], self.source_origins[ci].as_ref())?;
            id = superclass.context("Missing executable superclass")?;
        }
        Ok(())
    }
    fn layout_in(
        &self,
        registry: &types::Registry<'_>,
        ci: usize,
    ) -> Result<numeric::ObjectLayout> {
        if let Some(layout) = self.layouts.borrow().get(&ci) {
            return Ok(layout.clone());
        }
        let class = &self.classes[ci];
        let result = if class.access & 0x200 != 0 {
            numeric::ObjectLayout {
                abi: 2,
                payload_bytes: 0,
                reference_prefix_fields: 0,
                fields: Vec::new(),
            }
        } else {
            let id=registry.types.iter().position(|ty|matches!(ty,types::Type::Class{key,..} if key.loader==self.loader(class) && key.name==class.name)).context("Missing physical type identity")?;
            let layout = hierarchy::compact_layout(registry, id)?;
            let fields = layout
                .fields
                .iter()
                .map(|field| {
                    let types::Type::Class { key, .. } = &registry.types[field.member.owner] else {
                        unreachable!()
                    };
                    ensure!(
                        self.names
                            .get(key.name.as_str())
                            .is_some_and(|&ci| key.loader == self.loader(&self.classes[ci])),
                        "Inherited field owner {} requires executable provider/layout",
                        key.name
                    );
                    Ok(numeric::FieldLayout {
                        name: field.member.name.clone(),
                        descriptor: field.member.descriptor.clone(),
                        offset: field.offset,
                        declaring_class: Some(key.name.clone()),
                        declaring_field: Some(field.member.index),
                        storage_bytes: Some(field.storage_bytes),
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            numeric::ObjectLayout {
                abi: 2,
                payload_bytes: layout.payload_bytes,
                reference_prefix_fields: layout.reference_prefix,
                fields,
            }
        };
        self.layouts.borrow_mut().insert(ci, result.clone());
        Ok(result)
    }
    fn layout(&self, ci: usize) -> Result<numeric::ObjectLayout> {
        if let Some(layout) = self.layouts.borrow().get(&ci) {
            return Ok(layout.clone());
        }
        if self.hierarchy {
            let mut registry = self
                .metadata
                .as_ref()
                .context("Inherited layouts require verified metadata")?
                .borrow_mut();
            registry.class(self.loader(&self.classes[ci]), &self.classes[ci].name)?;
            return self.layout_in(&registry, ci);
        }
        let class = &self.classes[ci];
        let fields = class
            .field_info
            .iter()
            .enumerate()
            .filter(|(_, f)| f.access & 8 == 0)
            .map(|(index, f)| {
                Ok(numeric::FieldLayout {
                    name: f.name.clone(),
                    descriptor: f.descriptor.clone(),
                    offset: numeric::field_offset(class, index)?,
                    declaring_class: None,
                    declaring_field: None,
                    storage_bytes: None,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        let refs = fields
            .iter()
            .filter(|f| numeric::field_type(&f.descriptor).is_ok_and(|ty| ty.is_reference()))
            .count();
        let layout = numeric::ObjectLayout {
            abi: 1,
            payload_bytes: fields.len() * 8,
            reference_prefix_fields: refs,
            fields,
        };
        self.layouts.borrow_mut().insert(ci, layout.clone());
        Ok(layout)
    }
    fn field_identity(&self, caller: &ClassFile, constant: u16) -> Result<(usize, usize)> {
        let (owner, name, descriptor) = caller.field_reference(constant)?;
        let &symbolic = self
            .names
            .get(owner.as_str())
            .context("Missing symbolic field owner")?;
        self.check_access(caller, &self.classes[symbolic], 1)?;
        if let Some(metadata) = &self.metadata {
            let mut registry = metadata.borrow_mut();
            let id = registry.class(self.loader(caller), &owner)?;
            let field = hierarchy::resolve_field(&registry, id, &name, &descriptor)?;
            let types::Type::Class { key, .. } = &registry.types[field.owner] else {
                unreachable!()
            };
            let &ci = self
                .names
                .get(key.name.as_str())
                .context("Resolved field requires executable declaring class")?;
            ensure!(
                key.loader == self.loader(&self.classes[ci]),
                "Resolved field has unsupported defining loader"
            );
            return Ok((ci, field.index));
        }
        let index = self.classes[symbolic]
            .field_info
            .iter()
            .position(|f| f.name == name && f.descriptor == descriptor)
            .context("Missing declared field; inherited fields require metadata")?;
        Ok((symbolic, index))
    }
    fn field_map(&self, owner: usize, index: usize, constraint: usize) -> Result<usize> {
        let key = (owner, index, constraint);
        if let Some(map) = self.field_maps.borrow().get(&key) {
            return Ok(map.id);
        }
        let mut registry = self
            .metadata
            .as_ref()
            .context("Inherited fields require verified metadata")?
            .borrow_mut();
        let target = registry.class(
            self.loader(&self.classes[constraint]),
            &self.classes[constraint].name,
        )?;
        let mut rows = Vec::new();
        for (ci, class) in self.classes.iter().enumerate() {
            if class.access & 0x200 != 0 {
                continue;
            }
            let receiver = registry.class(self.loader(class), &class.name)?;
            if !registry.assignable(receiver, target) {
                continue;
            }
            let layout = self.layout_in(&registry, ci)?;
            let field = layout
                .fields
                .iter()
                .find(|f| {
                    f.declaring_class.as_deref() == Some(&self.classes[owner].name)
                        && f.declaring_field == Some(index)
                })
                .context("Resolved field is absent from actual object layout")?;
            if self.classes[owner].field_info[index].access & 0x40 != 0 {
                let width = field
                    .storage_bytes
                    .context("Volatile field is missing its physical width")?;
                ensure!(
                    matches!(width, 1 | 2 | 4 | 8) && field.offset % width == 0,
                    "Volatile field is not naturally aligned in an actual receiver layout"
                );
            }
            rows.push(field_maps::Row {
                receiver_class: ci,
                receiver_type: receiver,
                offset: field.offset,
            });
        }
        ensure!(
            rows.len() <= 4096 && self.field_maps.borrow().len() < 65536,
            "Field maps exceed compiler budget"
        );
        let id = self.field_maps.borrow().len();
        self.field_maps.borrow_mut().insert(
            key,
            field_maps::Map {
                id,
                declaring_class: owner,
                field_index: index,
                receiver_constraint: constraint,
                rows,
            },
        );
        self.type_checks.set(true);
        Ok(id)
    }
    fn dispatch_call(
        &self,
        caller: &ClassFile,
        constant: u16,
        interface: bool,
    ) -> Result<numeric::InterfaceLink> {
        let (owner, name, descriptor) = if interface {
            caller.interface_method_reference(constant)?
        } else {
            caller.method_reference(constant)?
        };
        self.dispatch_symbolic(
            caller,
            constant,
            if interface { 0xb9 } else { 0xb6 },
            owner,
            name,
            descriptor,
            interface,
        )
    }
    #[allow(clippy::too_many_arguments)]
    fn dispatch_symbolic(
        &self,
        caller: &ClassFile,
        constant: u16,
        kind: u8,
        owner: String,
        name: String,
        descriptor: String,
        interface: bool,
    ) -> Result<numeric::InterfaceLink> {
        let key = (caller.name.clone(), constant, kind);
        if !self.dispatch.borrow().contains_key(&key) {
            ensure!(
                !name.starts_with('<'),
                "Invalid interface invocation target"
            );
            let symbolic_ci = self
                .names
                .get(owner.as_str())
                .copied()
                .context("Missing executable symbolic owner")?;
            self.check_access(caller, &self.classes[symbolic_ci], 1)?;
            let mut registry = self
                .metadata
                .as_ref()
                .context("Interface dispatch requires verified metadata")?
                .borrow_mut();
            let symbolic = registry.class(self.loader(caller), &owner)?;
            let resolved =
                hierarchy::resolve_method(&registry, symbolic, &name, &descriptor, interface)?;
            ensure!(
                resolved.access & 8 == 0,
                "Instance invocation cannot select static methods"
            );
            let types::Type::Class { key: declared, .. } = &registry.types[resolved.owner] else {
                unreachable!()
            };
            let declared_name = declared.name.clone();
            let &declared_ci = self.names.get(declared_name.as_str()).with_context(|| {
                format!("Interface member requires executable declaring class {declared_name}")
            })?;
            self.check_member_access(caller, &self.classes[declared_ci], resolved.access)?;
            let mut rows = Vec::new();
            for (ci, class) in self.classes.iter().enumerate() {
                if class.access & 0x600 != 0
                    || (self.loader(class) == "bootstrap"
                        && matches!(
                            class.name.as_str(),
                            super::reflect_constructors::OWNER | super::reflect_fields::OWNER
                        ))
                {
                    continue;
                }
                let receiver = registry.class(self.loader(class), &class.name)?;
                if !registry.assignable(receiver, symbolic) {
                    continue;
                }
                validate_provided_class(class, self.source_origins[ci].as_ref())?;
                let selection =
                    hierarchy::select_method(&registry, receiver, symbolic, &resolved, interface)?;
                let (target, error, native_identity, native_builder) = match selection {
                    hierarchy::Selection::Method { member } => {
                        let types::Type::Class { key, .. } = &registry.types[member.owner] else {
                            unreachable!()
                        };
                        let &target_ci = self.names.get(key.name.as_str()).with_context(|| {
                            format!(
                                "Selected interface method requires executable class {}",
                                key.name
                            )
                        })?;
                        ensure!(
                            member.index < self.classes[target_ci].methods.len(),
                            "Selected method index is out of bounds"
                        );
                        let method = &self.classes[target_ci].methods[member.index];
                        ensure!(
                            method.name == name
                                && method.descriptor == descriptor
                                && method.access & (8 | 0x400) == 0,
                            "Selected method identity changed"
                        );
                        if super::builder_snapshot::is_snapshot(
                            &key.name,
                            &member.name,
                            &member.descriptor,
                        ) {
                            self.bind_builder_snapshot_in(&mut registry, caller, constant)?;
                            (None, 0, false, true)
                        } else if super::identity_hash::object_member(
                            &key.name,
                            &member.name,
                            &member.descriptor,
                        ) {
                            self.record_identity_hash(
                                &mut registry,
                                caller,
                                constant,
                                super::identity_hash::Kind::ObjectDefault,
                            )?;
                            (None, 0, true, false)
                        } else {
                            (Some(self.ids[target_ci][member.index]), 0, false, false)
                        }
                    }
                    hierarchy::Selection::IncompatibleClassChange => (None, 13, false, false),
                    hierarchy::Selection::AbstractMethod => (None, 14, false, false),
                    hierarchy::Selection::IllegalAccess => (None, 15, false, false),
                };
                rows.push(dispatch::Row {
                    receiver_class: Some(ci),
                    receiver_type: receiver,
                    target,
                    error,
                    runtime_string: None,
                    runtime_identity_hash: native_identity,
                    runtime_builder_snapshot: native_builder,
                    runtime_reflection: None,
                });
            }
            ensure!(
                rows.len() <= 4096 && self.dispatch.borrow().len() < 4096,
                "Interface dispatch exceeds table budget"
            );
            for opaque in [
                super::reflect_constructors::OWNER,
                super::reflect_fields::OWNER,
            ] {
                if !self.names.contains_key(opaque) {
                    continue;
                }
                let receiver = registry.class("bootstrap", opaque)?;
                if !registry.assignable(receiver, symbolic) {
                    continue;
                }
                if let hierarchy::Selection::Method { member } =
                    hierarchy::select_method(&registry, receiver, symbolic, &resolved, interface)?
                    && let Some(target) = dispatch::reflection_target(&registry, &member)?
                {
                    rows.push(dispatch::Row {
                        receiver_class: None,
                        receiver_type: receiver,
                        target: None,
                        error: 0,
                        runtime_string: None,
                        runtime_identity_hash: false,
                        runtime_builder_snapshot: false,
                        runtime_reflection: Some(target),
                    });
                }
            }
            let string_id = registry.class("bootstrap", "java/lang/String")?;
            if registry.assignable(string_id, symbolic) {
                let selection =
                    hierarchy::select_method(&registry, string_id, symbolic, &resolved, interface)?;
                if let hierarchy::Selection::Method { member } = selection {
                    let types::Type::Class {
                        key,
                        origin,
                        access,
                        ..
                    } = &registry.types[member.owner]
                    else {
                        unreachable!()
                    };
                    ensure!(
                        key.loader == "bootstrap"
                            && key.name == "java/lang/String"
                            && origin.source_id == "jdk:java.base"
                            && access & 0x211 == 0x11,
                        "Opaque String dispatch requires the pinned final String receiver"
                    );
                    let (op, _) =
                        numeric::StringIntrinsic::resolve(&member.name, &member.descriptor)?;
                    let method = registry
                        .definition(member.owner)
                        .unwrap()
                        .method(&member.name, Some(&member.descriptor))?;
                    ensure!(
                        method.access & (1 | 8 | 0x20 | 0x100 | 0x400) == 1
                            && method.code.is_some(),
                        "Opaque String dispatch member changed"
                    );
                    rows.push(dispatch::Row {
                        receiver_class: None,
                        receiver_type: string_id,
                        target: None,
                        error: 0,
                        runtime_string: Some(op),
                        runtime_identity_hash: false,
                        runtime_builder_snapshot: false,
                        runtime_reflection: None,
                    });
                } else {
                    anyhow::bail!("Opaque String method selection requires another runtime bridge");
                }
            }
            if name == "hashCode"
                && descriptor == "()I"
                && (declared_name == "java/lang/Object"
                    || rows.iter().any(|r| r.runtime_identity_hash))
            {
                for opaque in [
                    "java/lang/Class",
                    "java/lang/Module",
                    "java/lang/ModuleLayer",
                ] {
                    let receiver = registry.class("bootstrap", opaque)?;
                    if registry.assignable(receiver, symbolic) {
                        let selected = hierarchy::select_method(
                            &registry, receiver, symbolic, &resolved, interface,
                        )?;
                        let hierarchy::Selection::Method { member } = selected else {
                            anyhow::bail!("Opaque hash selection is unsupported")
                        };
                        let types::Type::Class { key, .. } = &registry.types[member.owner] else {
                            unreachable!()
                        };
                        ensure!(
                            super::identity_hash::object_member(
                                &key.name,
                                &member.name,
                                &member.descriptor
                            ),
                            "Opaque hash override requires its own runtime binding"
                        );
                        rows.push(dispatch::Row {
                            receiver_class: None,
                            receiver_type: receiver,
                            target: None,
                            error: 0,
                            runtime_string: None,
                            runtime_identity_hash: true,
                            runtime_builder_snapshot: false,
                            runtime_reflection: None,
                        });
                    }
                }
                if rows.iter().any(|r| r.runtime_identity_hash) {
                    self.record_identity_hash(
                        &mut registry,
                        caller,
                        constant,
                        super::identity_hash::Kind::ObjectDefault,
                    )?;
                }
            }
            let array_identity_hash = if name == "hashCode"
                && descriptor == "()I"
                && matches!(&registry.types[symbolic],types::Type::Class{key,..} if key.loader=="bootstrap"&&matches!(key.name.as_str(),"java/lang/Object"|"java/lang/Cloneable"|"java/io/Serializable"))
            {
                self.record_identity_hash(
                    &mut registry,
                    caller,
                    constant,
                    super::identity_hash::Kind::ObjectDefault,
                )?;
                Some(symbolic)
            } else {
                None
            };
            let id = self.dispatch.borrow().len();
            self.dispatch.borrow_mut().insert(
                key.clone(),
                dispatch::Site {
                    id,
                    caller: caller.name.clone(),
                    constant,
                    owner,
                    name,
                    descriptor,
                    interface,
                    invocation: if kind >= 0xe0 {
                        format!("String.join callback {}", kind - 0xe0)
                    } else if interface {
                        "invokeinterface".into()
                    } else {
                        "invokevirtual".into()
                    },
                    rows,
                    array_identity_hash,
                },
            );
            self.type_checks.set(true);
        }
        let sites = self.dispatch.borrow();
        let site = &sites[&key];
        let mut signature = self.descriptor(self.loader(caller), &site.descriptor)?;
        let owner = self
            .metadata
            .as_ref()
            .unwrap()
            .borrow_mut()
            .class(self.loader(caller), &site.owner)?;
        signature
            .arguments
            .insert(0, numeric::Type::MetadataReference(owner));
        signature.check_arguments()?;
        Ok((
            site.id,
            signature,
            site.rows.iter().filter_map(|row| row.target).collect(),
            site.rows
                .iter()
                .filter_map(|row| row.receiver_class)
                .collect(),
        ))
    }
    fn metadata_ids(
        &self,
        registry: &mut types::Registry<'_>,
        ty: numeric::Type,
    ) -> Result<Vec<usize>> {
        use numeric::Type as T;
        let name = match ty {
            T::MetadataReference(id) => {
                ensure!(id < registry.types.len(), "Unknown reference type identity");
                return Ok(vec![id]);
            }
            T::ReferenceJoin(id) => {
                return self
                    .joins
                    .borrow()
                    .iter()
                    .find(|(_, value)| **value == id)
                    .map(|(key, _)| key.clone())
                    .context("Missing reference join identity");
            }
            T::LinkedObject(owner) => self
                .classes
                .get(owner)
                .context("Invalid object class identity")?
                .name
                .clone(),
            T::LinkedObjectArray(owner) => format!(
                "[L{};",
                self.classes
                    .get(owner)
                    .context("Invalid array class identity")?
                    .name
            ),
            T::BootstrapString => "java/lang/String".into(),
            T::BootstrapStringArray => "[Ljava/lang/String;".into(),
            T::BootstrapClass => "java/lang/Class".into(),
            T::BootstrapClassArray => "[Ljava/lang/Class;".into(),
            T::Array(kind) => kind.descriptor().into(),
            _ => return Ok(Vec::new()),
        };
        let loader = match ty {
            T::LinkedObject(owner) | T::LinkedObjectArray(owner) => {
                self.loader(&self.classes[owner])
            }
            _ => "bootstrap",
        };
        Ok(vec![registry.literal(loader, &name)?])
    }
    fn static_reference(&self, name: &str, id: usize) -> Result<numeric::Type> {
        use numeric::{ArrayKind as A, Type as T};
        Ok(match name {
            "java/lang/String" => T::BootstrapString,
            "java/lang/Class" => T::BootstrapClass,
            "[Ljava/lang/String;" => T::BootstrapStringArray,
            "[Ljava/lang/Class;" => T::BootstrapClassArray,
            "[Z" => T::Array(A::Boolean),
            "[B" => T::Array(A::Byte),
            "[C" => T::Array(A::Char),
            "[S" => T::Array(A::Short),
            "[I" => T::Array(A::Int),
            "[J" => T::Array(A::Long),
            "[F" => T::Array(A::Float),
            "[D" => T::Array(A::Double),
            _ => {
                if let Some(component) = name.strip_prefix("[L").and_then(|s| s.strip_suffix(';'))
                    && let Some(&owner) = self.names.get(component)
                {
                    T::LinkedObjectArray(owner)
                } else if let Some(&owner) = self.names.get(name) {
                    T::LinkedObject(owner)
                } else {
                    T::MetadataReference(id)
                }
            }
        })
    }
    fn descriptor(&self, loader: &str, descriptor: &str) -> Result<numeric::Signature> {
        numeric::Signature::parse_with(descriptor, &mut |name, array| {
            if name == "java/lang/String" {
                return Ok(if array {
                    numeric::Type::BootstrapStringArray
                } else {
                    numeric::Type::BootstrapString
                });
            }
            if name == "java/lang/Class" {
                return Ok(if array {
                    numeric::Type::BootstrapClassArray
                } else {
                    numeric::Type::BootstrapClass
                });
            }
            let Some(owner) = self.names.get(name).copied() else {
                self.type_checks.set(true);
                let mut registry=self.metadata.as_ref().context("General reference descriptors require verified --metadata-lock and --jdk-base inputs")?.borrow_mut();
                let name = if array {
                    format!("[L{name};")
                } else {
                    name.into()
                };
                return Ok(numeric::Type::MetadataReference({
                    let id = registry.literal(loader, &name)?;
                    if name.starts_with("[[") {
                        self.typed_array_roots.borrow_mut().insert(id);
                    }
                    id
                }));
            };
            if let Some(metadata) = &self.metadata {
                let mut registry = metadata.borrow_mut();
                let id = registry.class(loader, name)?;
                let types::Type::Class { key, .. } = &registry.types[id] else {
                    unreachable!()
                };
                ensure!(
                    key.loader == self.loader(&self.classes[owner]),
                    "Descriptor type has another defining loader"
                );
            }
            Ok(if array {
                numeric::Type::LinkedObjectArray(owner)
            } else {
                numeric::Type::LinkedObject(owner)
            })
        })
    }
    fn new(classes: &'a [ClassFile]) -> Result<Self> {
        Self::with_metadata(classes, None, "explicit-application", None)
    }
    fn with_metadata(
        classes: &'a [ClassFile],
        provider: Option<&'a dyn types::TypeProvider>,
        metadata_loader: &'static str,
        sources: Option<&[Source]>,
    ) -> Result<Self> {
        let names = classes
            .iter()
            .enumerate()
            .map(|(i, c)| (c.name.as_str(), i))
            .collect();
        let mut ids = Vec::new();
        let mut locations = Vec::new();
        for (class_index, class) in classes.iter().enumerate() {
            let mut class_ids = Vec::new();
            for method_index in 0..class.methods.len() {
                class_ids.push(locations.len());
                locations.push((class_index, method_index));
                ensure!(
                    locations.len() <= 262144,
                    "Input method table exceeds linking limit"
                );
            }
            ids.push(class_ids);
        }
        Ok(Self {
            classes,
            names,
            ids,
            locations,
            strings: Default::default(),
            metadata: provider
                .map(|provider| std::cell::RefCell::new(types::Registry::new(provider))),
            metadata_loader,
            source_origins: sources
                .map(|sources| sources.iter().map(|source| source.origin.clone()).collect())
                .unwrap_or_else(|| classes.iter().map(|_| None).collect()),
            concats: Default::default(),
            lambda_sites: Default::default(),
            record_sites: Default::default(),
            null_guards: Default::default(),
            monitor_methods: Default::default(),
            monitor_notifications: Default::default(),
            runtime_resources: Default::default(),
            resource_bindings: Default::default(),
            string_joins: Default::default(),
            string_values: Default::default(),
            primitive_bindings: Default::default(),
            type_checks: Default::default(),
            assertion_queries: Default::default(),
            vm_bindings: Default::default(),
            cds_bindings: Default::default(),
            fd_plan: Default::default(),
            stream_plans: Default::default(),
            throwable_binding: Default::default(),
            exception_enabled: Default::default(),
            npe_bindings: Default::default(),
            case_plan: Default::default(),
            property_plan: Default::default(),
            vm_property_plan: Default::default(),
            vm_profile: None,
            concat_api: Default::default(),
            string_replace: Default::default(),
            literal_regex_replacements: Default::default(),
            string_chars: Default::default(),
            string_getchars: Default::default(),
            string_construction: Default::default(),
            string_lowercase: Default::default(),
            string_split: Default::default(),
            reflect_bindings: Default::default(),
            constructor_bindings: Default::default(),
            field_bindings: Default::default(),
            field_filter_bindings: Default::default(),
            reflect_literals: Default::default(),
            constructor_literals: Default::default(),
            lookup_bindings: Default::default(),
            lookup_vm_fixture: false,
            lookup_literals: Default::default(),
            string_prefix: Default::default(),
            array_clones: Default::default(),
            protected_constructors: Default::default(),
            vm_registration: Default::default(),
            signal_lookup_bindings: Default::default(),
            signal_natives: Default::default(),
            windows_startup: Default::default(),
            class_loaders: Default::default(),
            reflection_arrays: Default::default(),
            scoped_memory: Default::default(),
            winnt_file_system: Default::default(),
            thread_natives: Default::default(),
            unsafe_bootstrap: Default::default(),
            typed_array_sites: Default::default(),
            typed_array_roots: Default::default(),
            system_startup: None,
            primordial: false,
            access_context: Default::default(),
            system_streams: Default::default(),
            identity_hashes: Default::default(),
            hex_strings: Default::default(),
            string_storage: Default::default(),
            builder_snapshot: Default::default(),
            bitcasts: Default::default(),
            jdk_bridges: Default::default(),
            class_queries: Default::default(),
            shutdown: Default::default(),
            nest_access: Default::default(),
            constant_initialization: Default::default(),
            module_bindings: Default::default(),
            boot_snapshot: None,
            joins: Default::default(),
            dispatch: Default::default(),
            hierarchy: classes
                .iter()
                .any(|class| class.super_name != "java/lang/Object"),
            covariant_arrays: std::cell::Cell::new(
                classes
                    .iter()
                    .any(|class| class.super_name != "java/lang/Object"),
            ),
            layouts: Default::default(),
            field_maps: Default::default(),
        })
    }
    fn initialization_dependencies(&self, ci: usize) -> Result<Vec<usize>> {
        if self.classes[ci].interfaces == 0 && self.classes[ci].super_name == "java/lang/Object" {
            return Ok(Vec::new());
        }
        let mut registry = self
            .metadata
            .as_ref()
            .context("Initialization hierarchy requires verified metadata")?
            .borrow_mut();
        let id = registry.class(self.loader(&self.classes[ci]), &self.classes[ci].name)?;
        hierarchy::initialization_dependencies(&registry, id)?
            .into_iter()
            .filter_map(|id| {
                let types::Type::Class { key, .. } = &registry.types[id] else {
                    unreachable!()
                };
                if key.loader == "bootstrap" && key.name == "java/lang/Object" {
                    return None;
                }
                Some(self.names.get(key.name.as_str()).copied().with_context(|| {
                    format!("Missing executable initialization dependency {}", key.name)
                }))
            })
            .collect()
    }
    fn initializer(&self, ci: usize) -> Option<usize> {
        self.classes[ci]
            .methods
            .iter()
            .position(|m| m.name == "<clinit>")
            .map(|mi| self.ids[ci][mi])
    }
    fn prepare_system_streams(&self, ci: usize) -> Result<()> {
        let mut plan = self.system_streams.borrow_mut();
        if plan.is_none() {
            *plan = Some(super::system_streams::Plan::prepare(
                &mut self
                    .metadata
                    .as_ref()
                    .context("System native streams require java.base")?
                    .borrow_mut(),
                ci,
            )?);
        }
        ensure!(
            self.source_origins[ci].as_ref() == Some(&plan.as_ref().unwrap().origin),
            "System stream owner source mismatch"
        );
        self.type_checks.set(true);
        Ok(())
    }
    fn visit(&self, id: usize, graph: &mut Graph) -> Result<()> {
        if graph.done.contains(&id) || graph.active.contains(&id) {
            return Ok(());
        }
        ensure!(
            graph.active.len() < 128 && graph.order.len() < MAX_LINKED_METHODS,
            "Linked graph exceeds depth/method limit"
        );
        let (ci, mi) = self.locations[id];
        let class = &self.classes[ci];
        let method = &class.methods[mi];
        self.validate_executable(ci)?;
        validate_member(class, method, self.system_startup.is_some())?;
        graph.active.insert(id);
        graph.order.push(id);
        let deps = numeric::linked_dependencies(class, method, self).with_context(|| {
            format!(
                "Linking {}.{}{}",
                class.name, method.name, method.descriptor
            )
        })?;
        numeric::validate_linked(class, method, self).with_context(|| {
            format!(
                "Verifying linked {}.{}{}",
                class.name, method.name, method.descriptor
            )
        })?;
        graph.heap |= deps.heap;
        graph.strings |= deps.strings;
        graph.dynamic_strings |= deps.dynamic_strings;
        graph.volatile_accesses |= deps.volatile_accesses;
        for ci in deps.classes {
            self.validate_executable(ci)?;
            graph.classes.insert(ci);
        }
        for target in deps.calls {
            graph.edges.insert((id, target));
            self.visit(target, graph)?;
        }
        graph.active.remove(&id);
        graph.done.insert(id);
        Ok(())
    }
}

#[derive(Default)]
struct Graph {
    active: BTreeSet<usize>,
    done: BTreeSet<usize>,
    order: Vec<usize>,
    edges: BTreeSet<(usize, usize)>,
    classes: BTreeSet<usize>,
    heap: bool,
    strings: bool,
    dynamic_strings: bool,
    volatile_accesses: bool,
}

pub fn compile(
    inputs: &[PathBuf],
    entry_class: &str,
    entry_method: &str,
    descriptor: Option<&str>,
    output: &Path,
    assemble: bool,
) -> Result<Program> {
    compile_with_metadata(
        inputs,
        entry_class,
        entry_method,
        descriptor,
        output,
        assemble,
        None,
    )
}
pub struct MetadataContext<'a> {
    pub inputs: &'a crate::lock::InputLock,
    pub manifest: &'a Path,
    pub explicit_sources: bool,
    pub assertions: assertions::Policy,
    pub module_manifest: Option<&'a Path>,
    pub resource_jars: &'a [PathBuf],
    pub vm_profile: Option<&'a super::vm_properties::Profile>,
    pub primordial: bool,
    pub module_bootstrap: bool,
    pub class_lookup_fixture: bool,
}
pub fn compile_with_metadata(
    inputs: &[PathBuf],
    entry_class: &str,
    entry_method: &str,
    descriptor: Option<&str>,
    output: &Path,
    assemble: bool,
    metadata: Option<MetadataContext<'_>>,
) -> Result<Program> {
    ensure!(
        !inputs.is_empty() && inputs.len() <= MAX_LINKED_CLASSES,
        "Supply 1..{MAX_LINKED_CLASSES} explicit class files"
    );
    let base = metadata
        .as_ref()
        .map(|context| types::VanillaTypes::new(context.inputs, context.manifest))
        .transpose()?;
    let boot_snapshot = metadata
        .as_ref()
        .and_then(|c| c.module_manifest.map(|p| (p, c.inputs)))
        .map(|(p, i)| crate::boot_modules::Snapshot::read(p, i))
        .transpose()?;
    let verify_sources = metadata
        .as_ref()
        .is_some_and(|context| !context.explicit_sources);
    let mut loaded = BTreeMap::new();
    let mut total = 0u64;
    let mut explicit = BTreeMap::new();
    for path in inputs {
        let path = files::absolute(path)?;
        let size = fs::metadata(&path)?.len();
        ensure!(size <= 16 * 1024 * 1024, "Class exceeds size limit");
        let mut bytes = Vec::new();
        fs::File::open(&path)?
            .take(16 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)?;
        ensure!(
            bytes.len() <= 16 * 1024 * 1024,
            "Class grew beyond size limit"
        );
        total = total
            .checked_add(bytes.len() as u64)
            .context("Class input size overflow")?;
        ensure!(total <= 256 * 1024 * 1024, "Linked inputs exceed 256 MiB");
        let class = ClassFile::parse(&bytes)?;
        let name = class.name.clone();
        let mut origin = if verify_sources {
            let (original, origin) = types::TypeProvider::resolve(
                &lambdas::Provider {
                    base: base.as_ref().unwrap(),
                },
                "vanilla-application",
                &name,
            )?;
            ensure!(
                original == bytes && origin.sha256 == files::digest_bytes(&bytes).sha256,
                "Executable source does not match its verified bootstrap/application origin: {name}"
            );
            Some(origin)
        } else {
            None
        };
        validate_class_definition(&class, origin.as_ref(), true)?;
        if metadata
            .as_ref()
            .is_some_and(|context| context.explicit_sources)
        {
            let explicit_origin = mirrors::explicit_origin(&class, &bytes)?;
            origin = Some(explicit_origin.clone());
            explicit.insert(name.clone(), (bytes.clone(), explicit_origin));
        }
        ensure!(
            !loaded.contains_key(&name),
            "Duplicate class definition: {name}"
        );
        // Digest exactly the parsed bytes, without re-reading a potentially changed file.
        let digest = files::digest_bytes(&bytes);
        loaded.insert(
            name.clone(),
            (
                class,
                Source {
                    class_name: name,
                    path,
                    digest,
                    origin,
                },
            ),
        );
    }
    let provider = base.map(|base| lambdas::Provider {
        base: mirrors::Inputs { explicit, base },
    });
    let mut extra_sources = Vec::new();
    if metadata
        .as_ref()
        .is_some_and(|context| context.explicit_sources)
    {
        let provider = provider.as_ref().unwrap();
        let definitions: Vec<_> = loaded
            .keys()
            .map(|name| (name.clone(), "explicit-application".into()))
            .collect();
        let mut registry = types::Registry::new(provider);
        let discovered = discover_with_definitions(
            |loader, name| types::TypeProvider::resolve(provider, loader, name),
            entry_class,
            entry_method,
            descriptor,
            Some(&mut registry),
            "explicit-application",
            &definitions,
            false,
            metadata
                .as_ref()
                .is_some_and(|context| context.module_bootstrap),
            metadata
                .as_ref()
                .is_some_and(|context| context.class_lookup_fixture),
        )?;
        for (class, bytes, origin) in discovered {
            if loaded.contains_key(&class.name) {
                continue;
            }
            ensure!(
                (origin.loader == "bootstrap" && origin.source_id == "jdk:java.base")
                    || origin.generated.is_some(),
                "Automatic additions require verified java.base or compiler-generated origins"
            );
            validate_class_definition(&class, Some(&origin), true)?;
            let path = std::path::absolute(output)?
                .join(if origin.generated.is_some() {
                    "lambda-classes"
                } else {
                    "bootstrap-classes"
                })
                .join(format!("{:04}.class", extra_sources.len()));
            let name = class.name.clone();
            let source = Source {
                class_name: name.clone(),
                path: path.clone(),
                digest: files::digest_bytes(&bytes),
                origin: Some(origin),
            };
            extra_sources.push((path, bytes));
            loaded.insert(name, (class, source));
        }
    }
    let (classes, sources): (Vec<_>, Vec<_>) = loaded.into_values().unzip();
    let mut linker = if let Some(provider) = &provider {
        Linker::with_metadata(
            &classes,
            Some(provider),
            if metadata.as_ref().unwrap().explicit_sources {
                "explicit-application"
            } else {
                "vanilla-application"
            },
            Some(&sources),
        )?
    } else {
        Linker::new(&classes)?
    };
    linker.boot_snapshot = boot_snapshot;
    linker.lookup_vm_fixture = metadata.as_ref().is_some_and(|c| c.class_lookup_fixture);
    if linker.lookup_vm_fixture {
        linker.prepare_class_loaders()?;
        linker.exception_enabled.set(true);
        linker.type_checks.set(true);
    }
    linker.primordial = metadata.as_ref().is_some_and(|m| m.primordial);
    ensure!(
        !linker.primordial || super::thread_bootstrap::entry(entry_class, entry_method, descriptor),
        "Invalid primordial compilation profile"
    );
    linker.vm_profile = metadata
        .as_ref()
        .map(|c| {
            c.vm_profile
                .cloned()
                .map(Ok)
                .unwrap_or_else(|| super::vm_properties::Profile::for_image(c.inputs, output))
        })
        .transpose()?;
    linker.system_startup = super::system_startup::Plan::prepare(
        linker
            .metadata
            .as_ref()
            .map(|r| r.borrow_mut())
            .as_deref_mut(),
        entry_class,
        entry_method,
        descriptor,
    )?;
    if linker.bootstrap_execution() {
        linker.hierarchy = true;
        linker.covariant_arrays.set(true);
    }
    let &ci = linker
        .names
        .get(entry_class)
        .context("Entry class is not in linked inputs (use JVM slash names)")?;
    let method = classes[ci].method(entry_method, descriptor)?;
    let mi = classes[ci]
        .methods
        .iter()
        .position(|m| std::ptr::eq(m, method))
        .context("Entry method identity missing")?;
    let entry_id = linker.ids[ci][mi];
    let constructor = method.name == "<init>" && method.access & 8 == 0;
    ensure!(
        constructor || (!method.name.starts_with('<') && method.access & 8 != 0),
        "Program entry must be an ordinary static method or a constructor VM invoker"
    );
    ensure!(
        !constructor || classes[ci].access & 0x600 == 0,
        "Constructor entry cannot allocate an abstract class/interface"
    );
    let mut constructor_entry = if constructor {
        Some(super::constructor_entries::Plan::new(
            ci,
            entry_id,
            linker.locations.len(),
            sources[ci].origin.clone(),
            numeric::StaticLinker::signature(&linker, &classes[ci], method)?,
        )?)
    } else {
        None
    };
    let module_bootstrap = metadata.as_ref().is_some_and(|m| m.module_bootstrap);
    ensure!(
        !module_bootstrap
            || super::module_objects::bootstrap_entry(entry_class, entry_method, descriptor),
        "Invalid Module VM bootstrap entry"
    );
    if let Some(entry) = &mut constructor_entry {
        entry.module_bootstrap = module_bootstrap;
    }
    let module_objects = if let Some(&owner) = linker.names.get(super::module_objects::OWNER) {
        if super::module_objects::original(&classes[owner], sources[owner].origin.as_ref()) {
            linker.prepare_class_loaders()?;
            let layout = linker.layout(owner)?;
            let loader_layout = linker.layout(linker.names[super::class_loaders::LOADER])?;
            let mut plan = super::module_objects::Plan::new(
                &mut linker.metadata.as_ref().unwrap().borrow_mut(),
                owner,
                layout,
                &loader_layout,
            )?;
            plan.bootstrap_entry = module_bootstrap;
            Some(plan)
        } else {
            None
        }
    } else {
        None
    };
    let mut graph = Graph::default();
    if linker.lookup_vm_fixture {
        graph.heap = true;
        graph.strings = true;
        graph.dynamic_strings = true;
    }
    let native_windows_entry =
        super::windows_startup::is_native(&classes[ci].name, &method.name, &method.descriptor);
    let native_vm_entry = method.access & 0x100 != 0
        && super::vm_properties::is_native(&classes[ci].name, &method.name, &method.descriptor);
    let native_stream_entry = super::system_streams::Operation::resolve(
        &classes[ci].name,
        &method.name,
        &method.descriptor,
    );
    let native_access_entry = super::access_context::Operation::resolve(
        &classes[ci].name,
        &method.name,
        &method.descriptor,
    );
    if native_windows_entry {
        linker.prepare_windows_startup()?;
        linker.windows_startup.borrow_mut().as_mut().unwrap().entry = Some(entry_id);
        graph.classes.insert(ci);
        graph.heap = true;
        graph.strings = true;
    } else if let Some(op) = native_access_entry {
        linker.prepare_access_context()?;
        linker.access_context.borrow_mut().as_mut().unwrap().entry = Some((entry_id, op));
        graph.classes.insert(ci);
        graph.heap = true;
        graph.strings = true;
    } else if let Some(op) = native_stream_entry {
        super::system_streams::verify(
            &classes[ci],
            sources[ci]
                .origin
                .as_ref()
                .context("Missing System native entry source")?,
        )?;
        linker.prepare_system_streams(ci)?;
        linker.system_streams.borrow_mut().as_mut().unwrap().entry = Some((entry_id, op));
        graph.classes.insert(ci);
        graph.heap = true;
    } else if native_vm_entry {
        super::vm_properties::verify(
            &classes[ci],
            sources[ci]
                .origin
                .as_ref()
                .context("Native VM entry requires source provenance")?,
        )?;
        linker.prepare_vm_properties(ci)?;
        linker
            .vm_property_plan
            .borrow_mut()
            .as_mut()
            .unwrap()
            .entry_method_id = Some(entry_id);
        graph.classes.insert(ci);
        graph.heap = true;
        graph.strings = true;
        graph.dynamic_strings = true;
    } else {
        linker.visit(entry_id, &mut graph)?;
    }
    if constructor {
        graph.classes.insert(ci);
        graph.heap = true;
    }
    let thread_bootstrap = if linker.primordial {
        let mut helpers = Vec::new();
        for (index, (name, desc)) in super::thread_bootstrap::EXTRA.iter().enumerate() {
            let owner = *linker
                .names
                .get(*name)
                .context("Missing primordial constructor dependency")?;
            let mi = classes[owner]
                .methods
                .iter()
                .position(|m| m.name == "<init>" && m.descriptor == *desc)
                .context("Missing primordial dependency constructor")?;
            let id = linker.ids[owner][mi];
            linker.visit(id, &mut graph)?;
            graph.classes.insert(owner);
            helpers.push(super::constructor_entries::Plan::new(
                owner,
                id,
                linker.locations.len() + 1 + index,
                sources[owner].origin.clone(),
                numeric::StaticLinker::signature(
                    &linker,
                    &classes[owner],
                    &classes[owner].methods[mi],
                )?,
            )?);
        }
        let name = linker
            .strings
            .borrow_mut()
            .intern("main".encode_utf16().collect())?;
        graph.strings = true;
        Some(super::thread_bootstrap::Plan::new(
            sources[ci]
                .origin
                .clone()
                .context("Primordial entry requires source provenance")?,
            &classes[ci],
            method.code.as_ref().unwrap(),
            constructor_entry.as_ref().unwrap(),
            helpers.remove(0),
            helpers.remove(0),
            name,
        )?)
    } else {
        None
    };
    if linker.needs_class_lookup() {
        super::class_for_name::register_literals(
            &mut linker.metadata.as_ref().unwrap().borrow_mut(),
            &linker.lookup_literals.borrow(),
        )?;
    }
    let mut initialized = BTreeSet::new();
    let mut reflection_registered = BTreeSet::new();
    let mut vm_added = false;
    loop {
        if let Some(plan) = linker.access_context.borrow().as_ref() {
            graph
                .classes
                .extend([plan.owner, plan.context, plan.thread]);
            graph.heap = true;
            graph.strings = true;
        }
        if linker.exception_enabled.get() && !vm_added {
            vm_added = true;
            for (_, name) in unwind::KINDS {
                graph.classes.insert(
                    *linker
                        .names
                        .get(name)
                        .with_context(|| format!("Missing VM exception class {name}"))?,
                );
            }
            for name in ["java/lang/Throwable", "java/lang/Error"] {
                graph.classes.insert(
                    *linker
                        .names
                        .get(name)
                        .context("Missing VM exception base")?,
                );
            }
            let tc = linker.names["java/lang/Throwable"];
            let tm = classes[tc]
                .methods
                .iter()
                .position(|m| {
                    m.name == "fillInStackTrace" && m.descriptor == "()Ljava/lang/Throwable;"
                })
                .context("Missing original Throwable capture wrapper")?;
            linker.visit(linker.ids[tc][tm], &mut graph)?;
            if linker.throwable_binding.borrow().is_none() {
                *linker.throwable_binding.borrow_mut() = Some(throwables::runtime_binding(
                    &mut linker.metadata.as_ref().unwrap().borrow_mut(),
                )?);
            }
        }
        if linker.needs_lookup_initializers() {
            let mut lookup_targets = sources
                .iter()
                .enumerate()
                .filter(|(_, s)| {
                    s.origin.as_ref().is_some_and(|o| {
                        o.loader == "explicit-application" && o.generated.is_none()
                    })
                })
                .map(|(ci, _)| ci)
                .collect::<BTreeSet<_>>();
            for &id in linker.reflect_literals.borrow().iter() {
                let registry = linker.metadata.as_ref().unwrap().borrow();
                if let types::Type::Class { key, .. } = &registry.types[id]
                    && let Some(&ci) = linker.names.get(key.name.as_str())
                {
                    lookup_targets.insert(ci);
                }
            }
            for (_, name) in linker.lookup_literals.borrow().iter() {
                if let Some(&ci) = linker.names.get(name.replace('.', "/").as_str()) {
                    lookup_targets.insert(ci);
                }
            }
            for ci in lookup_targets {
                if !matches!(
                    classes[ci].name.as_str(),
                    "java/lang/Class" | "java/lang/String" | "java/lang/ModuleLayer"
                ) {
                    graph.classes.insert(ci);
                }
            }
        }
        if !linker.constructor_bindings.borrow().is_empty() {
            let targets = linker
                .constructor_literals
                .borrow()
                .iter()
                .filter_map(|&id| {
                    let registry = linker.metadata.as_ref().unwrap().borrow();
                    let types::Type::Class { key, .. } = &registry.types[id] else {
                        return None;
                    };
                    linker.names.get(key.name.as_str()).copied()
                })
                .chain(sources.iter().enumerate().filter_map(|(ci, s)| {
                    s.origin
                        .as_ref()
                        .filter(|o| o.loader == "explicit-application" && o.generated.is_none())
                        .map(|_| ci)
                }))
                .collect::<BTreeSet<_>>();
            for target in targets {
                let class = &classes[target];
                if class.access & 0x600 != 0
                    || matches!(
                        class.name.as_str(),
                        "java/lang/Class"
                            | "java/lang/String"
                            | "java/lang/Module"
                            | "java/lang/ModuleLayer"
                            | super::reflect_constructors::OWNER
                            | super::reflect_fields::OWNER
                    )
                {
                    continue;
                }
                for (mi, _) in class
                    .methods
                    .iter()
                    .enumerate()
                    .filter(|(_, m)| m.name == "<init>")
                {
                    linker.visit(linker.ids[target][mi], &mut graph)?;
                    graph.classes.insert(target);
                }
            }
        }
        if !linker.reflect_bindings.borrow().is_empty() {
            let targets = linker
                .reflect_literals
                .borrow()
                .iter()
                .filter_map(|&id| {
                    let registry = linker.metadata.as_ref().unwrap().borrow();
                    let types::Type::Class { key, .. } = &registry.types[id] else {
                        return None;
                    };
                    linker.names.get(key.name.as_str()).copied()
                })
                .chain(sources.iter().enumerate().filter_map(|(ci, s)| {
                    s.origin
                        .as_ref()
                        .filter(|o| o.loader == "explicit-application" && o.generated.is_none())
                        .map(|_| ci)
                }))
                .collect::<BTreeSet<_>>();
            for target in targets {
                let class = &classes[target];
                if class.access & 0x600 != 0
                    || matches!(class.name.as_str(), "java/lang/Class" | "java/lang/String")
                {
                    continue;
                }
                if let Some(mi) = class
                    .methods
                    .iter()
                    .position(|m| m.name == "<init>" && m.descriptor == "()V")
                    && reflection_registered.insert(target)
                {
                    linker.visit(linker.ids[target][mi], &mut graph)?;
                    graph.classes.insert(target);
                }
            }
        }
        let Some(ci) = graph
            .classes
            .iter()
            .find(|ci| !initialized.contains(*ci))
            .copied()
        else {
            break;
        };
        initialized.insert(ci);
        graph
            .classes
            .extend(linker.initialization_dependencies(ci)?);
        if let Some(id) = linker
            .initializer(ci)
            .filter(|_| !module_bootstrap || classes[ci].name != super::module_objects::OWNER)
        {
            linker.visit(id, &mut graph)?;
        }
    }
    if !linker.reflect_bindings.borrow().is_empty() {
        for &id in &graph.order {
            let (ci, mi) = linker.locations[id];
            let class = &classes[ci];
            let method = &class.methods[mi];
            if method.name == "<init>"
                && method.descriptor == "()V"
                && class.access & 0x600 == 0
                && !matches!(class.name.as_str(), "java/lang/Class" | "java/lang/String")
            {
                reflection_registered.insert(ci);
            }
        }
    }
    let reflection_constructors = reflection_registered
        .iter()
        .enumerate()
        .map(|(index, &ci)| {
            let mi = classes[ci]
                .methods
                .iter()
                .position(|m| m.name == "<init>" && m.descriptor == "()V")
                .unwrap();
            let mut plan = super::constructor_entries::Plan::new(
                ci,
                linker.ids[ci][mi],
                linker.locations.len() + 256 + index,
                sources[ci].origin.clone(),
                numeric::StaticLinker::signature(&linker, &classes[ci], &classes[ci].methods[mi])?,
            )?;
            plan.preserve_call_site = true;
            Ok(plan)
        })
        .collect::<Result<Vec<_>>>()?;
    let mut constructor_helpers = Vec::new();
    let mut constructor_slots = BTreeMap::new();
    let constructor_catalog = if linker.constructor_bindings.borrow().is_empty() {
        None
    } else {
        for &id in &graph.order {
            let (ci, mi) = linker.locations[id];
            let class = &classes[ci];
            if class.methods[mi].name != "<init>"
                || class.access & 0x600 != 0
                || matches!(
                    class.name.as_str(),
                    "java/lang/Class"
                        | "java/lang/String"
                        | "java/lang/Module"
                        | "java/lang/ModuleLayer"
                        | super::reflect_constructors::OWNER
                        | super::reflect_fields::OWNER
                )
            {
                continue;
            }
            let helper = linker.locations.len()
                + 256
                + reflection_constructors.len()
                + constructor_helpers.len();
            let mut plan = super::constructor_entries::Plan::new(
                ci,
                id,
                helper,
                sources[ci].origin.clone(),
                numeric::StaticLinker::signature(&linker, class, &class.methods[mi])?,
            )?;
            plan.preserve_call_site = true;
            plan.report_constructor_phase = true;
            constructor_helpers.push(plan);
            let source = sources[ci].origin.as_ref().unwrap();
            constructor_slots.insert(
                (source.loader.clone(), source.binary_name.clone(), mi),
                (helper, ci),
            );
        }
        Some(super::reflect_constructors::Catalog::prepare(
            &mut linker.metadata.as_ref().unwrap().borrow_mut(),
        )?)
    };
    let mut reflected_fields = if linker.field_bindings.borrow().is_empty()
        && linker.field_filter_bindings.borrow().is_empty()
        && !linker
            .unsafe_bootstrap
            .borrow()
            .as_ref()
            .is_some_and(|p| p.static_field_access || p.object_field_access)
    {
        None
    } else {
        let owners = sources
            .iter()
            .enumerate()
            .filter(|(ci, _)| graph.classes.contains(ci))
            .filter_map(|(ci, s)| {
                s.origin.as_ref().map(|o| {
                    (
                        (o.loader.clone(), s.class_name.clone(), o.sha256.clone()),
                        ci,
                    )
                })
            })
            .collect();
        Some(super::reflect_fields::Plan::prepare(
            &mut linker.metadata.as_ref().unwrap().borrow_mut(),
            &owners,
            linker.field_bindings.borrow().values().cloned().collect(),
            linker
                .field_filter_bindings
                .borrow()
                .values()
                .cloned()
                .collect(),
            |name| linker.strings.borrow_mut().intern(name),
        )?)
    };
    let states = graph
        .classes
        .iter()
        .map(|&id| {
            let class = &classes[id];
            let fields = class
                .field_info
                .iter()
                .enumerate()
                .filter(|(_, field)| field.access & 8 != 0)
                .map(|(index, field)| {
                    Ok(StaticField {
                        index,
                        name: field.name.clone(),
                        descriptor: field.descriptor.clone(),
                        initial_bits: format!("{:016x}", constant_bits(class, field)?),
                        reference: numeric::field_type(&field.descriptor)?.is_reference(),
                        initial_string: if field.descriptor == "Ljava/lang/String;" {
                            field
                                .constant_value
                                .map(|index| {
                                    numeric::StaticLinker::string_literal(&linker, class, index)
                                })
                                .transpose()?
                        } else {
                            None
                        },
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            Ok(ClassState {
                id,
                name: class.name.clone(),
                initializer: linker
                    .initializer(id)
                    .filter(|_| !module_bootstrap || class.name != super::module_objects::OWNER),
                fields,
                initialization_dependencies: linker.initialization_dependencies(id)?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    ensure!(
        states.iter().map(|s| s.fields.len()).sum::<usize>() <= 65536,
        "Program exceeds static field limit"
    );
    let prepared_layouts = graph
        .classes
        .iter()
        .map(|&id| {
            Ok(ProgramObjectLayout {
                class_id: id,
                class_name: classes[id].name.clone(),
                layout: linker.layout(id)?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let (throwable_plan, java_frames) =
        if let Some(binding) = linker.throwable_binding.borrow().clone() {
            let mut registry = linker
                .metadata
                .as_ref()
                .context("Throwable capture requires metadata")?
                .borrow_mut();
            let throwable_plan = throwables::plan(
                &mut registry,
                binding,
                &classes,
                &linker.source_origins,
                &prepared_layouts,
            )?;
            let mut methods = Vec::new();
            for &id in &graph.order {
                let (ci, mi) = linker.locations[id];
                methods.push(frames::method(
                    &mut registry,
                    &classes[ci],
                    mi,
                    id,
                    linker.source_origins[ci]
                        .as_ref()
                        .context("Missing Java frame source")?,
                )?);
            }
            methods.sort_by_key(|m| m.id);
            (Some(throwable_plan), Some(frames::Plan::new(methods)?))
        } else {
            (None, None)
        };
    let throwable_frames = throwable_plan.is_some();
    let string_case = linker.case_plan.borrow().clone();
    let platform_properties = linker.property_plan.borrow().clone();
    let vm_properties = linker.vm_property_plan.borrow().clone();
    let string_concat_api: Vec<_> = linker.concat_api.borrow().values().cloned().collect();
    let string_replace: Vec<_> = linker.string_replace.borrow().values().cloned().collect();
    let literal_regex_replacements: Vec<_> = linker
        .literal_regex_replacements
        .borrow()
        .values()
        .cloned()
        .collect();
    let string_chars: Vec<_> = linker.string_chars.borrow().values().cloned().collect();
    let string_getchars: Vec<_> = linker.string_getchars.borrow().values().cloned().collect();
    let shutdown = linker.shutdown.borrow().clone();
    let string_construction: Vec<_> = linker
        .string_construction
        .borrow()
        .values()
        .cloned()
        .collect();
    let string_split = linker.string_split.borrow().clone();
    let mut string_lowercase = linker.string_lowercase.borrow().clone();
    if let Some(plan) = &mut string_lowercase {
        let context = metadata
            .as_ref()
            .context("Case word data needs locked metadata")?;
        plan.words = Some(super::word_break::Tables::prepare(
            context.inputs,
            context.manifest,
        )?);
    }
    let string_prefix: Vec<_> = linker.string_prefix.borrow().values().cloned().collect();
    let system_streams = linker.system_streams.borrow().clone();
    let array_clones: Vec<_> = linker.array_clones.borrow().values().cloned().collect();
    let protected_constructors: Vec<_> = linker
        .protected_constructors
        .borrow()
        .values()
        .cloned()
        .collect();
    let vm_registration: Vec<_> = linker.vm_registration.borrow().values().cloned().collect();
    let signal_lookup_bindings: Vec<_> = linker
        .signal_lookup_bindings
        .borrow()
        .values()
        .cloned()
        .collect();
    let thread_natives = linker.thread_natives.borrow().clone();
    let signal_natives: Vec<_> = linker.signal_natives.borrow().values().cloned().collect();
    let windows_startup = linker.windows_startup.borrow().clone();
    let mut class_loaders = linker.class_loaders.borrow().clone();
    let mut reflection_arrays = linker.reflection_arrays.borrow().clone();
    let scoped_memory = linker.scoped_memory.borrow().clone();
    let winnt_file_system = linker.winnt_file_system.borrow().clone();
    let unsafe_bootstrap = linker.unsafe_bootstrap.borrow().clone();
    let mut access_context = linker.access_context.borrow().clone();
    if let Some(plan) = &mut access_context {
        plan.finish(
            java_frames
                .as_ref()
                .context("Access contexts require Java frames")?,
            &classes,
            &linker.metadata.as_ref().unwrap().borrow(),
        )?;
    }
    ensure!(
        unsafe_bootstrap.is_some()
            || !graph
                .classes
                .iter()
                .any(|&id| classes[id].name == super::unsafe_bootstrap::CONSTANTS),
        "UnsafeConstants execution requires its VM injection through the original Unsafe bootstrap"
    );
    let mut typed_arrays = if let Some(registry) = &linker.metadata {
        super::typed_arrays::Plan::new(
            linker
                .typed_array_sites
                .borrow()
                .values()
                .cloned()
                .collect(),
            linker.typed_array_roots.borrow().iter().copied().collect(),
            &registry.borrow(),
        )?
    } else {
        None
    };
    let identity_hashes: Vec<_> = linker.identity_hashes.borrow().values().cloned().collect();
    let hex_strings: Vec<_> = linker.hex_strings.borrow().values().cloned().collect();
    let string_storage: Vec<_> = linker.string_storage.borrow().values().cloned().collect();
    let builder_snapshot = linker.builder_snapshot.borrow().clone();
    let bitcasts: Vec<_> = linker.bitcasts.borrow().values().cloned().collect();
    let jdk_bridges: Vec<_> = linker.jdk_bridges.borrow().values().cloned().collect();
    let exception_runtime = if linker.exception_enabled.get() {
        let mut registry = linker.metadata.as_ref().unwrap().borrow_mut();
        let throwable_class = linker.names["java/lang/Throwable"];
        let field = |name: &str| {
            classes[throwable_class]
                .field_info
                .iter()
                .position(|f| f.name == name && f.access & 8 != 0)
                .context("Missing original Throwable sentinel")
        };
        let mut factories = Vec::new();
        for &(kind, name) in unwind::KINDS {
            let ci = linker.names[name];
            let message = if kind == 1 {
                Some(
                    linker
                        .strings
                        .borrow_mut()
                        .intern("/ by zero".encode_utf16().collect())?,
                )
            } else {
                None
            };
            let name_literal = linker
                .strings
                .borrow_mut()
                .intern(name.replace('/', ".").encode_utf16().collect())?;
            let layout = prepared_layouts
                .iter()
                .find(|l| l.class_id == ci)
                .context("Missing VM exception layout")?;
            factories.push(unwind::factory(
                &mut registry,
                kind,
                ci,
                &classes[ci],
                linker.source_origins[ci].as_ref().unwrap(),
                layout,
                (message, name_literal),
            )?);
        }
        let mut diagnostics = Vec::new();
        for &id in &graph.order {
            let (ci, mi) = linker.locations[id];
            let code = classes[ci].methods[mi].code.as_ref().unwrap();
            for pc in super::exceptions::boundaries(&code.bytes)? {
                if let Some(text) = unwind::diagnostic(&classes[ci], &code.bytes, pc)? {
                    let literal = linker
                        .strings
                        .borrow_mut()
                        .intern(text.encode_utf16().collect())?;
                    diagnostics.push(unwind::Diagnostic {
                        method: id,
                        pc,
                        literal,
                    });
                }
            }
        }
        diagnostics.sort_by_key(|d| (d.method, d.pc));
        Some(unwind::Plan {
            abi: 1,
            context_bytes: 32,
            external_bridge_bytes: 16,
            class_state_abi: 2,
            throwable_type: registry.class("bootstrap", "java/lang/Throwable")?,
            error_type: registry.class("bootstrap", "java/lang/Error")?,
            throwable_class,
            suppressed_field: field("SUPPRESSED_SENTINEL")?,
            stack_field: field("UNASSIGNED_STACK")?,
            factories,
            diagnostics,
            npe_bindings: linker.npe_bindings.borrow().clone(),
        })
    } else {
        None
    };
    let inheritance_runtime = linker.hierarchy || linker.covariant_arrays.get();
    let mut field_maps = linker
        .field_maps
        .borrow()
        .values()
        .cloned()
        .collect::<Vec<_>>();
    field_maps.sort_by_key(|m| m.id);
    let ordinary_field_map_count = field_maps.len();
    if linker
        .unsafe_bootstrap
        .borrow()
        .as_ref()
        .is_some_and(|p| p.object_field_access)
    {
        let maps = reflected_fields
            .as_mut()
            .context("Object Unsafe requires frozen Field metadata")?
            .prepare_instance_maps(
                &mut linker.metadata.as_ref().unwrap().borrow_mut(),
                &classes,
                &classes
                    .iter()
                    .map(|class| linker.loader(class).to_owned())
                    .collect::<Vec<_>>(),
                &prepared_layouts,
                ordinary_field_map_count,
            )?;
        field_maps.extend(maps);
    }

    let vm_bindings: Vec<_> = linker.vm_bindings.borrow().values().cloned().collect();
    let cds_profile =
        cds::Plan::no_archive(linker.cds_bindings.borrow().values().cloned().collect());
    let fd_plan = linker.fd_plan.borrow().clone();
    let nest_access: Vec<_> = linker.nest_access.borrow().values().cloned().collect();
    let runtime_access = fd_plan.is_some() || !nest_access.is_empty();
    let file_streams: Vec<_> = linker.stream_plans.borrow().values().cloned().collect();
    let stream_fields = !file_streams.is_empty();
    let constant_class_initialization: Vec<_> = linker
        .constant_initialization
        .borrow()
        .values()
        .cloned()
        .collect();
    let constant_initialization = !constant_class_initialization.is_empty();
    let system_services = vm_bindings
        .iter()
        .any(|b| b.operation == vm::Operation::ArrayCopy);
    let primitive_class_bindings: Vec<_> = linker
        .primitive_bindings
        .borrow()
        .values()
        .cloned()
        .collect();
    let module_bindings: Vec<_> = linker.module_bindings.borrow().values().cloned().collect();
    let layers = module_bindings.iter().any(|b| b.operation.uses_layer())
        || (module_objects.is_some() && linker.boot_snapshot.is_some());
    let lambda_sites: Vec<_> = linker.lambda_sites.borrow().values().cloned().collect();
    let record_sites: Vec<_> = linker.record_sites.borrow().values().cloned().collect();
    let null_guards = linker.null_guards.get();
    let lambdas = !lambda_sites.is_empty() || null_guards;
    let monitor_methods: Vec<_> = linker.monitor_methods.borrow().values().cloned().collect();
    let monitor_notifications: Vec<_> = linker
        .monitor_notifications
        .borrow()
        .values()
        .cloned()
        .collect();
    let runtime_resources = linker.runtime_resources.borrow().clone();
    let checked_types = linker.type_checks.get();
    let mut string_join_plans: Vec<_> = linker.string_joins.borrow().values().cloned().collect();
    string_join_plans.sort_by_key(|p| p.id);
    let string_value_bindings: Vec<_> = linker.string_values.borrow().values().cloned().collect();
    let initialized_string_values = string_value_bindings
        .iter()
        .any(|b| b.initializer.is_some());
    let mut interface_dispatch = linker
        .dispatch
        .borrow()
        .values()
        .cloned()
        .collect::<Vec<_>>();
    interface_dispatch.sort_by_key(|site| site.id);
    let reflection_dispatch = interface_dispatch
        .iter()
        .flat_map(|s| &s.rows)
        .any(|r| r.runtime_reflection.is_some());
    let dispatch_abi = if reflection_dispatch {
        4
    } else if interface_dispatch.iter().any(|s| {
        s.array_identity_hash.is_some()
            || s.rows
                .iter()
                .any(|r| r.runtime_identity_hash || r.runtime_builder_snapshot)
    }) {
        3
    } else {
        2
    };
    let string_services = !string_join_plans.is_empty()
        || interface_dispatch
            .iter()
            .any(|s| s.rows.iter().any(|r| r.runtime_string.is_some()));
    let hierarchy_runtime = !interface_dispatch.is_empty()
        || states
            .iter()
            .any(|state| !state.initialization_dependencies.is_empty());
    let mut runtime_type_bindings = if checked_types {
        runtime_types::prepare(
            &mut linker
                .metadata
                .as_ref()
                .context("Runtime types require verified metadata")?
                .borrow_mut(),
            &classes,
            &graph.classes,
            &prepared_layouts,
            !module_bindings.is_empty() && module_objects.is_none(),
            layers,
            &classes
                .iter()
                .map(|class| linker.loader(class))
                .collect::<Vec<_>>(),
        )?
    } else {
        Vec::new()
    };
    if let Some(plan) = &mut reflection_arrays {
        let mut registry = linker.metadata.as_ref().unwrap().borrow_mut();
        linker
            .typed_array_roots
            .borrow_mut()
            .extend(plan.prepare(&mut registry)?);
        typed_arrays = super::typed_arrays::Plan::new(
            linker
                .typed_array_sites
                .borrow()
                .values()
                .cloned()
                .collect(),
            linker.typed_array_roots.borrow().iter().copied().collect(),
            &registry,
        )?;
    }
    if let Some(plan) = &typed_arrays {
        plan.extend_rows(&mut runtime_type_bindings);
    }
    if let Some(plan) = &system_streams {
        plan.extend_rows(&mut runtime_type_bindings);
    }
    if let Some(plan) = &access_context {
        runtime_type_bindings.push(runtime_types::Binding {
            tag: "OFFSET boom_access_pd_layout".into(),
            type_id: plan.domain_type,
            kind: 0,
            payload_bytes: plan.domain_layout.payload_bytes,
            references: plan.domain_layout.reference_prefix_fields,
            element_shift: 0,
        });
    }
    if let Some(plan) = &class_loaders {
        runtime_type_bindings.push(runtime_types::Binding {
            tag: "OFFSET boom_loader_vm_layout".into(),
            type_id: plan.loader_type,
            kind: 0,
            payload_bytes: plan.loader_vm_layout.payload_bytes,
            references: plan.loader_vm_layout.reference_prefix_fields,
            element_shift: 0,
        });
    }
    if let Some(plan) = &string_lowercase {
        plan.extend_rows(&mut runtime_type_bindings);
    }
    if let Some(plan) = &reflected_fields {
        runtime_type_bindings.push(plan.runtime_binding());
    }
    if let Some(catalog) = &constructor_catalog {
        catalog.extend_rows(&mut runtime_type_bindings);
    }
    let mut reference_joins = linker
        .joins
        .borrow()
        .iter()
        .map(|(values, &id)| (id, values.clone()))
        .collect::<Vec<_>>();
    reference_joins.sort_by_key(|(id, _)| *id);
    let reference_joins = reference_joins
        .into_iter()
        .map(|(_, values)| values)
        .collect::<Vec<_>>();
    let mut module_plan = if module_bindings.is_empty() && module_objects.is_none() {
        None
    } else {
        let name = linker
            .strings
            .borrow_mut()
            .intern("java.base".encode_utf16().collect())?;
        let mut plan = modules::Plan::prepare(
            &linker.metadata.as_ref().unwrap().borrow().types,
            module_bindings,
            name,
        )?;
        if layers {
            plan.attach_boot(
                linker.boot_snapshot.as_ref().unwrap(),
                linker.metadata_loader,
                &mut |name| {
                    linker
                        .strings
                        .borrow_mut()
                        .intern(name.encode_utf16().collect())
                },
            )?;
        }
        if let Some(objects) = &module_objects {
            plan.objects = Some(objects.clone());
            plan.abi = 3;
        }
        Some(plan)
    };
    if vm_registration
        .iter()
        .any(|b| b.bootstrap_unnamed_field.is_some())
    {
        let plan = module_plan
            .as_mut()
            .context("BootLoader publication requires a Module plan")?;
        ensure!(
            plan.abi == 3 && plan.objects.is_some(),
            "BootLoader publication requires physical modules"
        );
        let identity = modules::Identity {
            defining_loader: "bootstrap".into(),
            name: None,
        };
        if !plan.identities.contains(&identity) {
            plan.identities.push(identity);
            if let Some(boot) = &mut plan.boot {
                boot.name_literals.push(None);
            }
        }
    }
    let module_count = module_plan.as_ref().map_or(0, |p| p.identities.len());
    let mut reflected_constructors = if let Some(catalog) = constructor_catalog {
        let context = metadata
            .as_ref()
            .context("Constructor reflection needs metadata")?;
        let snapshot = linker
            .boot_snapshot
            .as_ref()
            .context("Constructor access needs locked module metadata")?;
        let module = snapshot
            .modules
            .get("java.base")
            .context("Missing java.base module")?;
        let factory = exception_runtime
            .as_ref()
            .unwrap()
            .factories
            .iter()
            .find(|f| f.kind == 27)
            .unwrap();
        let layout = &prepared_layouts
            .iter()
            .find(|l| l.class_id == factory.class_id)
            .unwrap()
            .layout;
        let target = layout
            .fields
            .iter()
            .find(|f| {
                f.name == "target"
                    && f.declaring_class.as_deref()
                        == Some("java/lang/reflect/InvocationTargetException")
            })
            .context("Missing InvocationTargetException target")?
            .offset;
        let message = factory
            .fields
            .iter()
            .find(|f| f.name == "detailMessage")
            .unwrap()
            .offset;
        let mut bindings = linker
            .constructor_bindings
            .borrow()
            .values()
            .cloned()
            .collect::<Vec<_>>();
        bindings.sort_by_key(|b| b.site);
        let mut registry = linker.metadata.as_ref().unwrap().borrow_mut();
        let _ = context;
        let mut plan = super::reflect_constructors::Plan::prepare(
            &mut registry,
            catalog,
            bindings,
            constructor_helpers,
            message,
            target,
            (&module.sha256, &snapshot.fingerprint),
            |s| linker.strings.borrow_mut().intern(s),
            &|caller, target, package| {
                if target.source_id != "jdk:java.base" || caller.source_id == "jdk:java.base" {
                    return Ok(true);
                }
                Ok(module
                    .descriptor
                    .exports
                    .iter()
                    .any(|e| e.package == package && e.targets.is_empty()))
            },
        )?;
        plan.assign_helpers(&constructor_slots);
        Some(plan)
    } else {
        None
    };
    let reflect_new = if linker.reflect_bindings.borrow().is_empty() {
        None
    } else {
        let mut registry = linker.metadata.as_ref().unwrap().borrow_mut();
        let snapshot = linker
            .boot_snapshot
            .as_ref()
            .context("Reflective access requires locked module descriptors (--jdk-modules)")?;
        let module = snapshot
            .modules
            .get("java.base")
            .context("Missing reflection java.base module descriptor")?;
        let message_offset = exception_runtime
            .as_ref()
            .unwrap()
            .factories
            .iter()
            .find(|f| f.kind == 24)
            .unwrap()
            .fields
            .iter()
            .find(|f| f.name == "detailMessage")
            .unwrap()
            .offset;
        let mut bindings = linker
            .reflect_bindings
            .borrow()
            .values()
            .cloned()
            .collect::<Vec<_>>();
        bindings.sort_by_key(|b| b.site);
        let plan = super::reflect_new::Plan::prepare(
            &mut registry,
            (&module.sha256, &snapshot.fingerprint),
            bindings,
            reflection_constructors,
            message_offset,
            |s| linker.strings.borrow_mut().intern(s),
            &|caller, target, package| {
                if target.source_id != "jdk:java.base" || caller.source_id == "jdk:java.base" {
                    return Ok(true);
                }
                ensure!(
                    target.loader == "bootstrap" && target.generated.is_none(),
                    "Unproven reflective module target"
                );
                Ok(module
                    .descriptor
                    .exports
                    .iter()
                    .any(|e| e.package == package && e.targets.is_empty()))
            },
        )?;
        Some(plan)
    };
    if let Some(plan) = &mut reflected_fields {
        plan.message_offset = exception_runtime
            .as_ref()
            .context("Field reflection requires Context32 exceptions")?
            .factories
            .iter()
            .find(|f| f.kind == 28)
            .context("Missing NoSuchFieldException factory")?
            .fields
            .iter()
            .find(|f| f.name == "detailMessage")
            .context("Missing Field error message slot")?
            .offset;
    }
    if let Some(plan) = &mut reflected_constructors {
        plan.finish_names(&linker.metadata.as_ref().unwrap().borrow());
    }
    let class_name_metadata = if linker.class_queries.borrow().values().any(|b| {
        matches!(
            b.kind,
            super::class_queries::Kind::CanonicalName | super::class_queries::Kind::SimpleName
        )
    }) {
        Some(super::class_queries::prepare_names(
            &mut linker.metadata.as_ref().unwrap().borrow_mut(),
            |s| linker.strings.borrow_mut().intern(s),
        )?)
    } else {
        None
    };
    let mirror_names = if let Some(registry) = &linker.metadata {
        let registry = registry.borrow();
        (0..registry.types.len())
            .map(|id| {
                linker
                    .strings
                    .borrow_mut()
                    .intern(mirrors::name(&registry.types, id).encode_utf16().collect())
            })
            .collect::<Result<Vec<_>>>()?
    } else {
        Vec::new()
    };
    let assertion_policy = if linker.assertion_queries.get() {
        Some(
            metadata
                .as_ref()
                .context("Assertion policy requires verified metadata")?
                .assertions,
        )
    } else {
        None
    };
    let mirror_count = mirror_names.len();
    if let Some(plan) = &mut class_loaders {
        if module_objects.is_some() {
            let modules = module_plan.as_mut().unwrap();
            let mut extra = modules
                .identities
                .iter()
                .map(|i| i.defining_loader.clone())
                .collect::<Vec<_>>();
            if linker.needs_class_lookup() {
                extra.extend(["platform".into(), "vanilla-application".into()]);
            }
            plan.finish_with_keys(&linker.metadata.as_ref().unwrap().borrow().types, &extra)?;
            modules.object_loader_keys = modules
                .identities
                .iter()
                .map(|i| {
                    plan.keys
                        .iter()
                        .position(|key| key == &i.defining_loader)
                        .context("Missing physical module loader key")
                })
                .collect::<Result<_>>()?;
        } else {
            if !linker.needs_class_lookup() {
                plan.finish(&linker.metadata.as_ref().unwrap().borrow().types)?;
            } else {
                plan.finish_with_keys(
                    &linker.metadata.as_ref().unwrap().borrow().types,
                    &["platform".into(), "vanilla-application".into()],
                )?;
            }
        }
    }
    let class_for_name = if !linker.needs_class_lookup() {
        None
    } else {
        let context = metadata.as_ref().unwrap();
        let message_offset = exception_runtime
            .as_ref()
            .unwrap()
            .factories
            .iter()
            .find(|f| f.kind == 19)
            .unwrap()
            .fields
            .iter()
            .find(|f| f.name == "detailMessage")
            .unwrap()
            .offset;
        Some(super::class_for_name::Plan::prepare(
            &mut linker.metadata.as_ref().unwrap().borrow_mut(),
            context.inputs,
            context.manifest,
            linker
                .boot_snapshot
                .as_ref()
                .context("Class lookup requires locked JDK module metadata (--jdk-modules)")?,
            class_loaders.as_ref().unwrap(),
            &states,
            &sources,
            linker.lookup_bindings.borrow().values().cloned().collect(),
            message_offset,
        )?)
    };
    let class_queries = if linker.class_queries.borrow().is_empty() {
        None
    } else {
        let mut plan = super::class_queries::Plan::new(
            linker.class_queries.borrow().values().cloned().collect(),
            &linker
                .metadata
                .as_ref()
                .context("Class queries require mirror metadata")?
                .borrow()
                .types,
        )?;
        plan.names = class_name_metadata;
        Some(plan)
    };
    let mut resource_callers: Vec<_> = linker
        .resource_bindings
        .borrow()
        .values()
        .cloned()
        .collect();
    resource_callers.sort_by_key(|b| b.id);
    let (resource_plan, resource_source) = if resource_callers.is_empty() {
        (None, None)
    } else {
        let context = metadata.as_ref().unwrap();
        let (pack, source) = resources::prepare(
            context.inputs,
            context.manifest,
            linker.boot_snapshot.as_ref().unwrap(),
            context.resource_jars,
            context.explicit_sources,
        )?;
        let plan = resources::Plan::new(
            pack,
            std::path::absolute(output)?.join("resources.pack"),
            &linker.metadata.as_ref().unwrap().borrow().types,
            resource_callers,
        )?;
        plan.verify_definitions(&sources)?;
        (Some(plan), Some(source))
    };
    let mut literals = linker
        .strings
        .borrow()
        .values
        .iter()
        .map(|(value, &id)| StringLiteral {
            id,
            utf16: value.clone(),
        })
        .collect::<Vec<_>>();
    literals.sort_by_key(|literal| literal.id);
    let strings = graph.strings || !literals.is_empty();
    let dynamic_strings = graph.dynamic_strings;
    let mut concat_plans = linker
        .concats
        .borrow()
        .values()
        .cloned()
        .collect::<Vec<_>>();
    concat_plans.sort_by_key(|(id, _)| *id);
    let concat_plans = concat_plans
        .into_iter()
        .map(|(_, plan)| plan)
        .collect::<Vec<_>>();
    ensure!(
        states
            .iter()
            .flat_map(|state| &state.fields)
            .filter(|field| field.reference)
            .count()
            + class_for_name.as_ref().map_or(0, |p| p.synthetic_roots)
            + literals.len()
            + mirror_count
            + if class_queries
                .as_ref()
                .is_some_and(|p| p.class_value_map.is_some())
            {
                mirror_count
            } else {
                0
            }
            + if class_queries.as_ref().is_some_and(|p| p.names.is_some()) {
                mirror_count * 2
            } else {
                0
            }
            + class_loaders.as_ref().map_or(0, |p| p.keys.len())
            + if access_context.is_some() {
                mirror_count
            } else {
                0
            }
            + module_count
            + if layers { 2 } else { 0 }
            + usize::from(dynamic_strings)
            + usize::from(platform_properties.is_some())
            + if exception_runtime.is_some() {
                states.len() + 2
            } else {
                0
            }
            <= 65536,
        "Combined static/literal roots exceed ABI budget"
    );
    let heap = strings
        || graph.heap
        || states
            .iter()
            .any(|state| state.fields.iter().any(|field| field.reference));
    let object_layouts = if heap { prepared_layouts } else { Vec::new() };
    let order = &graph.order;
    let entry_target = constructor_entry.as_ref().map_or(entry_id, |p| p.helper_id);
    let mut assembly = if exception_runtime.is_some() {
        numeric::module_header32(entry_target)
    } else {
        numeric::module_header(entry_target)
    };
    if let Some(p) = &thread_bootstrap {
        p.emit(&mut assembly, &object_layouts, exception_runtime.is_some())?;
    } else if let Some(p) = &constructor_entry {
        p.emit(&mut assembly, exception_runtime.is_some());
    }
    if let Some(p) = &system_streams {
        p.emit(&mut assembly);
    }
    if !string_prefix.is_empty() {
        assembly.push_str("EXTERN boom_string_starts_with:PROC\nPUBLIC boom_get_prefix_string_pool\nboom_get_prefix_string_pool PROC\n    lea rax,boom_string_pool\n    ret\nboom_get_prefix_string_pool ENDP\n");
    }
    if string_storage.iter().any(|binding| {
        matches!(
            binding.property,
            super::string_storage::Property::GetBytes
                | super::string_storage::Property::GetBytesRange
        )
    }) {
        assembly.push_str("PUBLIC boom_get_storage_string_pool\nboom_get_storage_string_pool PROC\n    lea rax,boom_string_pool\n    ret\nboom_get_storage_string_pool ENDP\n");
    }
    if let Some(p) = &platform_properties {
        p.emit(&mut assembly);
    }
    if let Some(p) = &vm_properties {
        p.emit(&mut assembly);
    }
    if let Some(p) = &class_queries {
        p.emit(&mut assembly);
    }
    if let Some(p) = &shutdown {
        p.emit(&mut assembly);
    }
    if !string_concat_api.is_empty() {
        assembly.push_str("EXTERN boom_string_concat_api:PROC\nPUBLIC boom_get_concat_string_pool\nboom_get_concat_string_pool PROC\n    lea rax, boom_string_pool\n    ret\nboom_get_concat_string_pool ENDP\n");
    }
    if !string_replace.is_empty() || !literal_regex_replacements.is_empty() {
        assembly.push_str("EXTERN boom_string_replace:PROC\nPUBLIC boom_get_replace_string_pool\nboom_get_replace_string_pool PROC\n    lea rax, boom_string_pool\n    ret\nboom_get_replace_string_pool ENDP\n");
    }
    if !array_clones.is_empty() {
        super::array_clone::emit(&mut assembly);
    }
    if !literal_regex_replacements.is_empty() {
        assembly.push_str("EXTERN boom_string_replace_literal_chars:PROC\n");
    }
    if !string_chars.is_empty() {
        assembly.push_str("EXTERN boom_string_to_chars:PROC\nPUBLIC boom_get_chars_string_pool\nboom_get_chars_string_pool PROC\n    lea rax, boom_string_pool\n    ret\nboom_get_chars_string_pool ENDP\n");
    }
    if !string_construction.is_empty() {
        assembly.push_str("EXTERN boom_string_new:PROC\nEXTERN boom_string_construct_chars:PROC\nEXTERN boom_string_construct_chars_all:PROC\nPUBLIC boom_get_constructor_string_pool\nboom_get_constructor_string_pool PROC\n    lea rax,boom_string_pool\n    ret\nboom_get_constructor_string_pool ENDP\n");
    }
    if let Some(plan) = &string_lowercase {
        plan.emit(&mut assembly)?;
    }
    if let Some(plan) = &string_split {
        plan.emit(&mut assembly)?;
    }
    if let Some(plan) = &reflected_fields {
        plan.emit(
            &mut assembly,
            linker.metadata.as_ref().unwrap().borrow().types.len(),
        )?;
    }
    if let Some(plan) = &reflected_constructors {
        plan.emit(&mut assembly)?;
    }
    if let Some(plan) = &reflect_new {
        plan.emit(&mut assembly)?;
    }
    if let Some(plan) = &class_for_name {
        plan.emit(&mut assembly)?;
    }
    if !vm_registration.is_empty() {
        super::vm_registration::emit(&mut assembly, &vm_registration, module_plan.as_ref())?;
    }
    if !signal_lookup_bindings.is_empty() {
        assembly.push_str("EXTERN boom_signal_find:PROC\n");
    }
    if !signal_natives.is_empty() {
        super::signal_natives::emit(&mut assembly);
    }
    if let Some(plan) = &windows_startup {
        plan.emit(&mut assembly);
    }
    if let Some(plan) = &class_loaders {
        plan.emit(&mut assembly)?;
    }
    if let Some(plan) = &reflection_arrays {
        plan.emit(&mut assembly)?;
    }
    if let Some(plan) = &scoped_memory {
        plan.emit(&mut assembly);
    }
    if let Some(plan) = &winnt_file_system {
        plan.emit(&mut assembly);
    }
    if let Some(plan) = &thread_natives {
        plan.emit(&mut assembly);
    }
    if let Some(plan) = &access_context {
        plan.emit(
            &mut assembly,
            &object_layouts,
            &linker.metadata.as_ref().unwrap().borrow().types,
        )?;
    }
    if let Some(plan) = &unsafe_bootstrap {
        plan.emit(
            &mut assembly,
            &states,
            &linker.metadata.as_ref().unwrap().borrow().types,
            thread_natives.is_some(),
            reflected_fields.is_some(),
        )?;
    }
    if let Some(plan) = &typed_arrays {
        plan.emit(&mut assembly);
    }
    if !identity_hashes.is_empty() {
        assembly.push_str("EXTERN boom_identity_hash:PROC\n");
    }
    if !hex_strings.is_empty() {
        assembly.push_str("EXTERN boom_hex_string:PROC\nPUBLIC boom_get_hex_string_pool\nboom_get_hex_string_pool PROC\n    lea rax, boom_string_pool\n    ret\nboom_get_hex_string_pool ENDP\n");
    }
    if let Some(p) = &builder_snapshot {
        p.emit(&mut assembly);
    }
    if let Some(p) = &fd_plan {
        p.emit(&mut assembly)?;
    }
    file_streams::emit(&file_streams, &mut assembly)?;
    if let Some(p) = &java_frames {
        p.emit(&mut assembly)?;
    }
    if let Some(p) = &throwable_plan {
        p.emit(&mut assembly)?;
    }
    if let Some(p) = &exception_runtime {
        p.emit(&mut assembly)?;
    }
    if !string_getchars.is_empty() {
        let offset = exception_runtime
            .as_ref()
            .context("getChars needs Context32")?
            .factories
            .iter()
            .find(|f| f.kind == 11)
            .context("Missing String bounds factory")?
            .fields
            .iter()
            .find(|f| f.name == "detailMessage")
            .context("Missing bounds message field")?
            .offset;
        assembly.push_str(&format!("EXTERN boom_string_get_chars:PROC\nEXTERN boom_exception_create:PROC\n.const\nALIGN 8\nboom_getchars_plan DWORD 047434852h,1,{offset},0\n    QWORD OFFSET boom_exception_create\n.code\n"));
    }
    if let Some(plan) = &cds_profile {
        plan.emit(&mut assembly)?;
    }
    string_join::emit(&mut assembly, &string_join_plans)?;
    mirrors::emit_primitives(&mut assembly, &primitive_class_bindings)?;
    if let Some(plan) = &resource_plan {
        plan.emit(&mut assembly, linker.boot_snapshot.as_ref().unwrap())?;
    }
    if let Some(plan) = &runtime_resources {
        plan.emit(&mut assembly);
    }
    if !monitor_notifications.is_empty() {
        assembly.push_str("EXTERN boom_monitor_notify:PROC\nEXTERN boom_monitor_notify_all:PROC\n");
    }
    if !monitor_methods.is_empty() {
        assembly.push_str("EXTERN boom_monitor_enter:PROC\nEXTERN boom_monitor_exit:PROC\n");
    }
    for binding in &vm_bindings {
        assembly.push_str(&format!("EXTERN {}:PROC\n", binding.assembly_symbol));
    }
    vm::emit_registration(&mut assembly, &vm_bindings)?;

    if heap {
        numeric::append_program_heap(&mut assembly, &object_layouts, ci)?;
    }
    if strings {
        append_string_pool(&mut assembly, &literals, dynamic_strings)?;
    }
    if dynamic_strings {
        concat::emit(&mut assembly, &concat_plans)?;
    }
    if mirror_count != 0 {
        mirrors::emit(
            &mut assembly,
            &linker.metadata.as_ref().unwrap().borrow().types,
            &mirror_names,
            assertion_policy,
        )?;
    }
    if let Some(plan) = &module_plan {
        plan.emit(&mut assembly)?;
    }
    if checked_types {
        runtime_types::emit(&mut assembly, &runtime_type_bindings, mirror_count)?;
    }
    dispatch::emit(&mut assembly, &interface_dispatch)?;
    field_maps::emit(&mut assembly, &field_maps)?;
    if linker.covariant_arrays.get() {
        assembly.push_str("EXTERN boom_covariant_array:PROC\n");
    }
    append_class_state(
        &mut assembly,
        &states,
        heap,
        if strings { Some(literals.len()) } else { None },
        mirror_count,
        module_count,
        layers,
        dynamic_strings,
        exception_runtime.is_some(),
        platform_properties.is_some(),
        unsafe_bootstrap.as_ref().map(|p| p.constants_class_id),
        if access_context.is_some() {
            mirror_count
        } else {
            0
        },
        class_loaders.as_ref().map_or(0, |p| p.keys.len()),
        class_for_name.as_ref().map_or(0, |p| p.synthetic_roots),
        if class_queries.as_ref().is_some_and(|p| p.names.is_some()) {
            mirror_count * 2
        } else {
            0
        },
        if class_queries
            .as_ref()
            .is_some_and(|p| p.class_value_map.is_some())
        {
            mirror_count
        } else {
            0
        },
    );
    let mut instructions = 0;
    let mut symbols = Vec::new();
    if native_vm_entry
        || native_stream_entry.is_some()
        || native_access_entry.is_some()
        || native_windows_entry
    {
        symbols.push(Symbol {
            id: entry_id,
            class_name: classes[ci].name.clone(),
            method: method.name.clone(),
            descriptor: method.descriptor.clone(),
        });
    }
    for &id in order {
        let (c, m) = linker.locations[id];
        let (code, count) = numeric::emit_linked_function(&classes[c], m, id, &linker)?;
        assembly.push_str(&code);
        instructions += count;
        ensure!(
            assembly.len() <= 256 * 1024 * 1024,
            "Assembly exceeds program size limit"
        );
        symbols.push(Symbol {
            id,
            class_name: classes[c].name.clone(),
            method: classes[c].methods[m].name.clone(),
            descriptor: classes[c].methods[m].descriptor.clone(),
        });
    }
    ensure!(
        linker.strings.borrow().values.len() == literals.len(),
        "String pool changed after assembly layout"
    );
    ensure!(
        linker.string_getchars.borrow().len() == string_getchars.len(),
        "String.getChars bindings changed after layout"
    );
    ensure!(
        linker.concats.borrow().len() == concat_plans.len(),
        "Concat plans changed after assembly layout"
    );
    ensure!(
        linker.joins.borrow().len() == reference_joins.len(),
        "Reference joins changed after metadata layout"
    );
    ensure!(
        linker.dispatch.borrow().len() == interface_dispatch.len(),
        "Interface dispatch changed after assembly layout"
    );
    ensure!(
        linker.field_maps.borrow().len() == ordinary_field_map_count,
        "Field maps changed after assembly layout"
    );
    ensure!(
        linker
            .runtime_resources
            .borrow()
            .as_ref()
            .map_or(0, |p| p.bindings.len())
            == runtime_resources.as_ref().map_or(0, |p| p.bindings.len())
            && linker.constructor_bindings.borrow().len()
                == reflected_constructors.as_ref().map_or(0, |p| p.sites.len())
            && linker.monitor_notifications.borrow().len() == monitor_notifications.len()
            && linker.lookup_bindings.borrow().len()
                == class_for_name.as_ref().map_or(0, |p| p.bindings.len())
            && linker.reflect_bindings.borrow().len()
                == reflect_new.as_ref().map_or(0, |p| p.sites.len())
            && linker.vm_bindings.borrow().len() == vm_bindings.len()
            && linker.concat_api.borrow().len() == string_concat_api.len()
            && linker.string_replace.borrow().len() == string_replace.len()
            && linker.literal_regex_replacements.borrow().len() == literal_regex_replacements.len()
            && linker.string_chars.borrow().len() == string_chars.len()
            && linker.string_construction.borrow().len() == string_construction.len()
            && linker
                .string_lowercase
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == string_lowercase.as_ref().map(|p| p.bindings.len())
            && linker
                .string_split
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == string_split.as_ref().map(|p| p.bindings.len())
            && linker.string_prefix.borrow().len() == string_prefix.len()
            && linker
                .system_streams
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == system_streams.as_ref().map(|p| p.bindings.len())
            && linker
                .unsafe_bootstrap
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == unsafe_bootstrap.as_ref().map(|p| p.bindings.len())
            && linker.array_clones.borrow().len() == array_clones.len()
            && linker.protected_constructors.borrow().len() == protected_constructors.len()
            && linker.vm_registration.borrow().len() == vm_registration.len()
            && linker.signal_lookup_bindings.borrow().len() == signal_lookup_bindings.len()
            && linker.signal_natives.borrow().len() == signal_natives.len()
            && linker
                .winnt_file_system
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == winnt_file_system.as_ref().map(|p| p.bindings.len())
            && linker
                .scoped_memory
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == scoped_memory.as_ref().map(|p| p.bindings.len())
            && linker
                .reflection_arrays
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == reflection_arrays.as_ref().map(|p| p.bindings.len())
            && linker
                .class_loaders
                .borrow()
                .as_ref()
                .map(|p| (p.bindings.len(), p.registration_bindings.len()))
                == class_loaders
                    .as_ref()
                    .map(|p| (p.bindings.len(), p.registration_bindings.len()))
            && linker
                .windows_startup
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == windows_startup.as_ref().map(|p| p.bindings.len())
            && linker
                .thread_natives
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == thread_natives.as_ref().map(|p| p.bindings.len())
            && linker
                .access_context
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == access_context.as_ref().map(|p| p.bindings.len())
            && linker.typed_array_sites.borrow().len()
                == typed_arrays.as_ref().map_or(0, |p| p.sites.len())
            && linker.typed_array_roots.borrow().len()
                == typed_arrays.as_ref().map_or(0, |p| p.root_types.len())
            && linker.identity_hashes.borrow().len() == identity_hashes.len()
            && linker.hex_strings.borrow().len() == hex_strings.len()
            && linker.string_storage.borrow().len() == string_storage.len()
            && linker
                .builder_snapshot
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == builder_snapshot.as_ref().map(|p| p.bindings.len())
            && linker.bitcasts.borrow().len() == bitcasts.len()
            && linker.jdk_bridges.borrow().len() == jdk_bridges.len()
            && linker.class_queries.borrow().len()
                == class_queries.as_ref().map_or(0, |p| p.bindings.len())
            && linker.exception_enabled.get() == exception_runtime.is_some()
            && linker
                .property_plan
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == platform_properties.as_ref().map(|p| p.bindings.len())
            && linker
                .vm_property_plan
                .borrow()
                .as_ref()
                .map(|p| p.bindings.len())
                == vm_properties.as_ref().map(|p| p.bindings.len())
            && linker.case_plan.borrow().as_ref().map(|p| p.bindings.len())
                == string_case.as_ref().map(|p| p.bindings.len())
            && exception_runtime
                .as_ref()
                .is_none_or(|p| *linker.npe_bindings.borrow() == p.npe_bindings)
            && linker.throwable_binding.borrow().is_some() == throwable_plan.is_some()
            && linker
                .stream_plans
                .borrow()
                .values()
                .map(|p| p.bindings.len())
                .sum::<usize>()
                == file_streams.iter().map(|p| p.bindings.len()).sum::<usize>()
            && linker.constant_initialization.borrow().len() == constant_class_initialization.len()
            && linker.nest_access.borrow().len() == nest_access.len()
            && linker
                .fd_plan
                .borrow()
                .as_ref()
                .map_or(0, |p| p.bindings.len())
                == fd_plan.as_ref().map_or(0, |p| p.bindings.len())
            && linker.cds_bindings.borrow().len()
                == cds_profile.as_ref().map_or(0, |p| p.bindings.len())
            && linker.string_values.borrow().len() == string_value_bindings.len()
            && linker.string_joins.borrow().len() == string_join_plans.len()
            && linker.primitive_bindings.borrow().len() == primitive_class_bindings.len()
            && linker.lambda_sites.borrow().len() == lambda_sites.len()
            && linker.record_sites.borrow().len() == record_sites.len()
            && linker.null_guards.get() == null_guards
            && linker.monitor_methods.borrow().len() == monitor_methods.len()
            && linker.resource_bindings.borrow().len()
                == resource_plan.as_ref().map_or(0, |p| p.callers.len())
            && linker.module_bindings.borrow().len()
                == module_plan.as_ref().map_or(0, |p| p.bindings.len())
            && linker.assertion_queries.get() == assertion_policy.is_some()
            && linker
                .metadata
                .as_ref()
                .is_none_or(|registry| registry.borrow().types.len() == mirror_count),
        "Runtime policy/native/type metadata changed after immutable layout"
    );
    if exception_runtime.is_some() {
        assembly = assembly
            .replace("boom_class_ensure", "boom_class_ensure32")
            .replace("boom_class_ensure3232", "boom_class_ensure32");
    }
    numeric::append_shared_kernels(&mut assembly);
    assembly.push_str("END\n");
    fs::create_dir_all(output)?;
    for (path, bytes) in &extra_sources {
        files::write_atomic(path, bytes)?;
    }
    let output = files::absolute(output)?;
    if let Some(plan) = &resource_plan {
        plan.publish(resource_source.as_ref().unwrap())?;
    }
    let asm = output.join("method.asm");
    files::write_atomic(&asm, assembly.as_bytes())?;
    let mut compilation = managed::Compilation {
        schema: 1,
        backend: managed::BACKEND.into(),
        abi: if exception_runtime.is_some() {
            "context16-bridge32-pending-in-rax-v1"
        } else {
            "context16-argv64-rax64-v1"
        }
        .into(),
        class_name: entry_class.into(),
        method: method.name.clone(),
        descriptor: method.descriptor.clone(),
        signature: if let Some(p) = &thread_bootstrap {
            p.signature()
        } else if let Some(p) = &constructor_entry {
            p.signature.clone()
        } else {
            numeric::StaticLinker::signature(&linker, &classes[ci], method)?
        },
        instructions,
        linked_methods: order.len()
            + usize::from(
                native_vm_entry
                    || native_stream_entry.is_some()
                    || native_access_entry.is_some()
                    || native_windows_entry,
            ),
        requires_heap: heap,
        object_layout: None,
        source: sources[ci].path.clone(),
        source_digest: sources[ci].digest.clone(),
        assembly: asm.clone(),
        assembly_digest: files::digest(&asm)?,
        dll: None,
        dll_digest: None,
    };
    if assemble {
        let dll = super::assemble_module_with_mirrors(
            &output,
            &asm,
            heap,
            true,
            strings,
            mirror_count != 0,
        )?;
        compilation.dll_digest = Some(files::digest(&dll)?);
        compilation.dll = Some(dll);
    }
    files::write_atomic(
        &output.join("compilation.json"),
        &serde_json::to_vec_pretty(&compilation)?,
    )?;
    #[derive(Serialize)]
    #[serde(untagged)]
    enum MonitorIdentity<'a> {
        Previous(&'a [monitors::Binding]),
        Primitive((&'a [monitors::Binding], &'a [mirrors::PrimitiveBinding])),
    }
    type ResourceView<'a> = Option<(
        &'a resources::Pack,
        &'a Vec<resources::Anchor>,
        &'a Vec<resources::Binding>,
    )>;
    type AccessView<'a> = (
        ResourceView<'a>,
        &'a [string_join::Plan],
        &'a [string_values::Binding],
        Option<&'a cds::Plan>,
        &'a [nests::Proof],
        Option<&'a file_descriptors::Plan>,
    );
    type ThrowableView<'a> = (
        u32,
        AccessView<'a>,
        &'a [class_initialization::Binding],
        &'a [file_streams::Plan],
        &'a throwables::Plan,
        &'a frames::Plan,
    );
    #[derive(Serialize)]
    #[serde(untagged)]
    enum ResourceIdentity<'a> {
        Exceptions((&'a unwind::Plan, ThrowableView<'a>)),
        Throwable(ThrowableView<'a>),
        Streams(
            (
                u32,
                AccessView<'a>,
                &'a [class_initialization::Binding],
                &'a [file_streams::Plan],
            ),
        ),
        Initialization((AccessView<'a>, &'a [class_initialization::Binding])),
        Access(AccessView<'a>),
        Cds(
            (
                ResourceView<'a>,
                &'a [string_join::Plan],
                &'a [string_values::Binding],
                &'a cds::Plan,
            ),
        ),
        Previous(ResourceView<'a>),
        Join((ResourceView<'a>, &'a [string_join::Plan])),
        Values(
            (
                ResourceView<'a>,
                &'a [string_join::Plan],
                &'a [string_values::Binding],
            ),
        ),
    }
    #[derive(Serialize)]
    #[serde(untagged)]
    enum DispatchIdentity<'a> {
        Empty(&'a [dispatch::Site]),
        Versioned((u32, &'a [dispatch::Site])),
    }
    let identity = serde_json::to_vec(&(
        if exception_runtime.is_some() {
            "boom-context32-program-v30"
        } else if throwable_frames {
            "boom-throwable-frames-program-v29"
        } else if stream_fields {
            "boom-stream-fields-program-v28"
        } else if constant_initialization {
            "boom-class-initialization-program-v27"
        } else if runtime_access {
            "boom-runtime-access-program-v26"
        } else if initialized_string_values {
            "boom-decimal-program-v25"
        } else if cds_profile.is_some() {
            "boom-cds-program-v24"
        } else if !string_value_bindings.is_empty() {
            "boom-string-values-program-v23"
        } else if string_services {
            "boom-string-join-program-v22"
        } else if system_services {
            "boom-system-program-v21"
        } else if !primitive_class_bindings.is_empty() {
            "boom-primitive-class-program-v20"
        } else if resource_plan.is_some() {
            "boom-resources-program-v19"
        } else if !monitor_methods.is_empty() {
            "boom-monitors-program-v18"
        } else if lambdas {
            "boom-lambda-program-v17"
        } else if layers {
            "boom-layers-program-v16"
        } else if module_plan.is_some() {
            "boom-modules-program-v15"
        } else if !vm_bindings.is_empty() {
            "boom-vm-program-v14"
        } else if assertion_policy.is_some() {
            "boom-assertions-program-v13"
        } else if graph.volatile_accesses {
            "boom-volatile-program-v12"
        } else if linker.bootstrap_execution() {
            "boom-bootstrap-program-v11"
        } else if linker.hierarchy {
            "boom-compact-program-v10"
        } else if inheritance_runtime {
            "boom-inheritance-program-v9"
        } else if hierarchy_runtime {
            "boom-interface-program-v8"
        } else if checked_types {
            "boom-runtime-types-program-v7"
        } else if dynamic_strings {
            "boom-concat-program-v6"
        } else if mirror_count != 0 {
            "boom-mirror-program-v5"
        } else if strings {
            "boom-string-program-v4"
        } else {
            "boom-object-program-v3"
        },
        entry_class,
        &method.name,
        &method.descriptor,
        &object_layouts,
        &field_maps,
        if interface_dispatch.is_empty() {
            DispatchIdentity::Empty(&interface_dispatch)
        } else {
            DispatchIdentity::Versioned((dispatch_abi, &interface_dispatch))
        },
        &assertion_policy,
        &vm_bindings,
        &module_plan,
        (&lambda_sites, &record_sites, null_guards),
        if primitive_class_bindings.is_empty() {
            MonitorIdentity::Previous(&monitor_methods)
        } else {
            MonitorIdentity::Primitive((&monitor_methods, &primitive_class_bindings))
        },
        if let Some(e) = &exception_runtime {
            ResourceIdentity::Exceptions((
                e,
                (
                    2,
                    (
                        resource_plan
                            .as_ref()
                            .map(|p| (&p.pack, &p.anchors, &p.callers)),
                        &string_join_plans,
                        &string_value_bindings,
                        cds_profile.as_ref(),
                        &nest_access,
                        fd_plan.as_ref(),
                    ),
                    &constant_class_initialization,
                    &file_streams,
                    throwable_plan.as_ref().unwrap(),
                    java_frames.as_ref().unwrap(),
                ),
            ))
        } else if let Some(p) = &throwable_plan {
            ResourceIdentity::Throwable((
                2,
                (
                    resource_plan
                        .as_ref()
                        .map(|p| (&p.pack, &p.anchors, &p.callers)),
                    &string_join_plans,
                    &string_value_bindings,
                    cds_profile.as_ref(),
                    &nest_access,
                    fd_plan.as_ref(),
                ),
                &constant_class_initialization,
                &file_streams,
                p,
                java_frames.as_ref().unwrap(),
            ))
        } else if stream_fields {
            ResourceIdentity::Streams((
                2,
                (
                    resource_plan
                        .as_ref()
                        .map(|p| (&p.pack, &p.anchors, &p.callers)),
                    &string_join_plans,
                    &string_value_bindings,
                    cds_profile.as_ref(),
                    &nest_access,
                    fd_plan.as_ref(),
                ),
                &constant_class_initialization,
                &file_streams,
            ))
        } else if constant_initialization {
            ResourceIdentity::Initialization((
                (
                    resource_plan
                        .as_ref()
                        .map(|p| (&p.pack, &p.anchors, &p.callers)),
                    &string_join_plans,
                    &string_value_bindings,
                    cds_profile.as_ref(),
                    &nest_access,
                    fd_plan.as_ref(),
                ),
                &constant_class_initialization,
            ))
        } else if runtime_access {
            ResourceIdentity::Access((
                resource_plan
                    .as_ref()
                    .map(|p| (&p.pack, &p.anchors, &p.callers)),
                &string_join_plans,
                &string_value_bindings,
                cds_profile.as_ref(),
                &nest_access,
                fd_plan.as_ref(),
            ))
        } else if let Some(cds) = &cds_profile {
            ResourceIdentity::Cds((
                resource_plan
                    .as_ref()
                    .map(|p| (&p.pack, &p.anchors, &p.callers)),
                &string_join_plans,
                &string_value_bindings,
                cds,
            ))
        } else if !string_value_bindings.is_empty() {
            ResourceIdentity::Values((
                resource_plan
                    .as_ref()
                    .map(|p| (&p.pack, &p.anchors, &p.callers)),
                &string_join_plans,
                &string_value_bindings,
            ))
        } else if string_join_plans.is_empty() {
            ResourceIdentity::Previous(
                resource_plan
                    .as_ref()
                    .map(|p| (&p.pack, &p.anchors, &p.callers)),
            )
        } else {
            ResourceIdentity::Join((
                resource_plan
                    .as_ref()
                    .map(|p| (&p.pack, &p.anchors, &p.callers)),
                &string_join_plans,
            ))
        },
        sources
            .iter()
            .map(|s| (&s.class_name, &s.digest, &s.origin))
            .collect::<Vec<_>>(),
        &metadata.as_ref().map(|context| &context.inputs.fingerprint),
        &linker
            .metadata
            .as_ref()
            .map(|registry| serde_json::to_value(&registry.borrow().types))
            .transpose()?,
    ))?;
    let identity = if let Some(case) = &string_case {
        serde_json::to_vec(&(31, case, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(ctor) = &constructor_entry {
        serde_json::to_vec(&(32, ctor, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(props) = &platform_properties {
        serde_json::to_vec(&(33, props, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if string_concat_api.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(34, &string_concat_api, files::digest_bytes(&identity)))?
    };
    let identity = if identity_hashes.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(35, &identity_hashes, files::digest_bytes(&identity)))?
    };
    let identity = if hex_strings.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(36, &hex_strings, files::digest_bytes(&identity)))?
    };
    let identity = if string_storage.is_empty()
        && builder_snapshot.is_none()
        && bitcasts.is_empty()
        && jdk_bridges.is_empty()
    {
        identity
    } else {
        serde_json::to_vec(&(
            37,
            &string_storage,
            &builder_snapshot,
            &bitcasts,
            &jdk_bridges,
            files::digest_bytes(&identity),
        ))?
    };
    let identity = if let Some(p) = &vm_properties {
        serde_json::to_vec(&(38, p, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(p) = &class_queries {
        serde_json::to_vec(&(39, p, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if string_replace.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(40, &string_replace, files::digest_bytes(&identity)))?
    };
    let identity = if array_clones.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(41, &array_clones, files::digest_bytes(&identity)))?
    };
    let identity = if protected_constructors.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(42, &protected_constructors, files::digest_bytes(&identity)))?
    };
    let identity = if vm_registration.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(43, &vm_registration, files::digest_bytes(&identity)))?
    };
    let identity = if let Some(plan) = &typed_arrays {
        serde_json::to_vec(&(44, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if string_chars.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(45, &string_chars, files::digest_bytes(&identity)))?
    };
    let identity = if string_construction.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(61, &string_construction, files::digest_bytes(&identity)))?
    };
    let identity = if let Some(plan) = &class_for_name {
        serde_json::to_vec(&(65, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &reflect_new {
        serde_json::to_vec(&(64, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &string_split {
        serde_json::to_vec(&(63, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &string_lowercase {
        serde_json::to_vec(&(62, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &system_streams {
        serde_json::to_vec(&(46, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &linker.system_startup {
        serde_json::to_vec(&(46, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if string_prefix.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(47, &string_prefix, files::digest_bytes(&identity)))?
    };
    let identity = if signal_lookup_bindings.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(48, &signal_lookup_bindings, files::digest_bytes(&identity)))?
    };
    let identity = if let Some(plan) = &thread_natives {
        serde_json::to_vec(&(53, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &unsafe_bootstrap {
        serde_json::to_vec(&(52, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &thread_bootstrap {
        serde_json::to_vec(&(54, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &access_context {
        serde_json::to_vec(&(55, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if signal_natives.is_empty() && windows_startup.is_none() {
        identity
    } else {
        serde_json::to_vec(&(
            56,
            &signal_natives,
            &windows_startup,
            files::digest_bytes(&identity),
        ))?
    };
    let identity = if let Some(plan) = &class_loaders {
        serde_json::to_vec(&(57, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &reflection_arrays {
        serde_json::to_vec(&(58, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &scoped_memory {
        serde_json::to_vec(&(59, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &winnt_file_system {
        serde_json::to_vec(&(59, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if monitor_notifications.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(66, &monitor_notifications, files::digest_bytes(&identity)))?
    };
    let identity = if let Some(plan) = &runtime_resources {
        serde_json::to_vec(&(67, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &reflected_fields {
        serde_json::to_vec(&(&identity, plan))?
    } else if let Some(plan) = &reflected_constructors {
        serde_json::to_vec(&(68, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if literal_regex_replacements.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(
            69,
            &literal_regex_replacements,
            files::digest_bytes(&identity),
        ))?
    };
    let identity = if string_getchars.is_empty() {
        identity
    } else {
        serde_json::to_vec(&(77, &string_getchars, files::digest_bytes(&identity)))?
    };
    let identity = if class_queries.as_ref().is_some_and(|p| p.names.is_some()) {
        serde_json::to_vec(&(78, &class_queries, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let identity = if let Some(plan) = &shutdown {
        serde_json::to_vec(&(81, plan, files::digest_bytes(&identity)))?
    } else {
        identity
    };
    let program = Program {
        shutdown,
        schema: if linker.shutdown.borrow().is_some() {
            81
        } else if class_queries
            .as_ref()
            .is_some_and(|p| p.class_value_map.is_some())
        {
            80
        } else if class_for_name
            .as_ref()
            .is_some_and(|p| p.bindings.iter().any(|b| b.bootstrap_lookup))
        {
            79
        } else if class_queries.as_ref().is_some_and(|p| p.names.is_some()) {
            78
        } else if !string_getchars.is_empty() {
            77
        } else if unsafe_bootstrap
            .as_ref()
            .is_some_and(|p| p.object_field_access)
        {
            76
        } else if !record_sites.is_empty() {
            74
        } else if reflection_dispatch {
            73
        } else if reflected_fields.is_some() {
            72
        } else if vm_registration.iter().any(|b| {
            b.field_cache.is_some()
                || b.finalization_policy.is_some()
                || b.bootstrap_unnamed_field.is_some()
        }) {
            71
        } else if string_join_plans
            .iter()
            .any(|p| p.kind == string_join::Kind::Replace)
        {
            70
        } else if !literal_regex_replacements.is_empty() {
            69
        } else if reflected_constructors.is_some() {
            68
        } else if runtime_resources.is_some() {
            67
        } else if !monitor_notifications.is_empty() {
            66
        } else if class_for_name.is_some() {
            65
        } else if reflect_new.is_some() {
            64
        } else if string_split.is_some() {
            63
        } else if string_lowercase.is_some() {
            62
        } else if !string_construction.is_empty() {
            61
        } else if module_objects.is_some() {
            60
        } else if winnt_file_system.is_some() || scoped_memory.is_some() {
            59
        } else if reflection_arrays.is_some() {
            58
        } else if class_loaders.is_some() {
            57
        } else if !signal_natives.is_empty() || windows_startup.is_some() {
            56
        } else if access_context.is_some() {
            55
        } else if thread_bootstrap.is_some() {
            54
        } else if thread_natives.is_some() {
            53
        } else if unsafe_bootstrap.is_some() {
            52
        } else if !signal_lookup_bindings.is_empty() {
            48
        } else if !string_prefix.is_empty() {
            47
        } else if linker.system_startup.is_some() || system_streams.is_some() {
            46
        } else if !string_chars.is_empty() {
            45
        } else if typed_arrays.is_some() {
            44
        } else if !vm_registration.is_empty() {
            43
        } else if !protected_constructors.is_empty() {
            42
        } else if !array_clones.is_empty() {
            41
        } else if !string_replace.is_empty() {
            40
        } else if class_queries.is_some() {
            39
        } else if vm_properties.is_some() {
            38
        } else if !string_storage.is_empty()
            || builder_snapshot.is_some()
            || !bitcasts.is_empty()
            || !jdk_bridges.is_empty()
        {
            37
        } else if !hex_strings.is_empty() {
            36
        } else if !identity_hashes.is_empty() {
            35
        } else if !string_concat_api.is_empty() {
            34
        } else if platform_properties.is_some() {
            33
        } else if constructor_entry.is_some() {
            32
        } else if string_case.is_some() {
            31
        } else if exception_runtime.is_some() {
            30
        } else if throwable_frames {
            29
        } else if stream_fields {
            28
        } else if constant_initialization {
            27
        } else if runtime_access {
            26
        } else if initialized_string_values {
            25
        } else if cds_profile.is_some() {
            24
        } else if !string_value_bindings.is_empty() {
            23
        } else if string_services {
            22
        } else if system_services {
            21
        } else if !primitive_class_bindings.is_empty() {
            20
        } else if resource_plan.is_some() {
            19
        } else if !monitor_methods.is_empty() {
            18
        } else if lambdas {
            17
        } else if layers {
            16
        } else if module_plan.is_some() {
            15
        } else if !vm_bindings.is_empty() {
            14
        } else if assertion_policy.is_some() {
            13
        } else if graph.volatile_accesses {
            12
        } else if linker.bootstrap_execution() {
            11
        } else if linker.hierarchy {
            10
        } else if inheritance_runtime {
            9
        } else if hierarchy_runtime {
            8
        } else if checked_types {
            7
        } else if dynamic_strings {
            6
        } else if mirror_count != 0 {
            5
        } else if strings {
            4
        } else {
            3
        },
        backend: if linker.shutdown.borrow().is_some() {
            "boom-shutdown-program-v81-masm-x64"
        } else if class_queries
            .as_ref()
            .is_some_and(|p| p.class_value_map.is_some())
        {
            "boom-class-value-fields-program-v80-masm-x64"
        } else if class_for_name
            .as_ref()
            .is_some_and(|p| p.bindings.iter().any(|b| b.bootstrap_lookup))
        {
            "boom-bootstrap-class-lookup-program-v79-masm-x64"
        } else if class_queries.as_ref().is_some_and(|p| p.names.is_some()) {
            "boom-class-names-program-v78-masm-x64"
        } else if !string_getchars.is_empty() {
            "boom-string-getchars-program-v77-masm-x64"
        } else if unsafe_bootstrap
            .as_ref()
            .is_some_and(|p| p.object_field_access)
        {
            "boom-unsafe-instance-fields-program-v76-masm-x64"
        } else if !record_sites.is_empty() {
            "boom-record-bootstrap-program-v74-masm-x64"
        } else if reflection_dispatch {
            "boom-reflection-dispatch-program-v73-masm-x64"
        } else if reflected_fields.is_some() {
            "boom-reflected-fields-program-v72-masm-x64"
        } else if vm_registration.iter().any(|b| {
            b.field_cache.is_some()
                || b.finalization_policy.is_some()
                || b.bootstrap_unnamed_field.is_some()
        }) {
            "boom-bootstrap-services-program-v71-masm-x64"
        } else if string_join_plans
            .iter()
            .any(|p| p.kind == string_join::Kind::Replace)
        {
            "boom-char-sequence-replace-program-v70-masm-x64"
        } else if !literal_regex_replacements.is_empty() {
            "boom-literal-regex-fold-program-v69-masm-x64"
        } else if reflected_constructors.is_some() {
            "boom-reflected-constructors-program-v68-masm-x64"
        } else if runtime_resources.is_some() {
            "boom-runtime-resources-program-v67-masm-x64"
        } else if !monitor_notifications.is_empty() {
            "boom-empty-wait-set-notifications-v66-masm-x64"
        } else if class_for_name.is_some() {
            "boom-class-name-lookup-program-v65-masm-x64"
        } else if reflect_new.is_some() {
            "boom-reflective-construction-program-v64-masm-x64"
        } else if string_split.is_some() {
            "boom-literal-split-program-v63-masm-x64"
        } else if string_lowercase.is_some() {
            "boom-locale-lowercase-program-v62-masm-x64"
        } else if !string_construction.is_empty() {
            "boom-string-construction-program-v61-masm-x64"
        } else if module_objects.is_some() {
            "boom-physical-module-program-v60-masm-x64"
        } else if winnt_file_system.is_some() {
            "boom-windows-file-system-program-v59-masm-x64"
        } else if scoped_memory.is_some() {
            "boom-scoped-memory-bootstrap-program-v59-masm-x64"
        } else if reflection_arrays.is_some() {
            "boom-reflection-array-program-v58-masm-x64"
        } else if class_loaders.is_some() {
            "boom-class-loader-field-program-v57-masm-x64"
        } else if !signal_natives.is_empty() {
            "boom-signal-control-program-v56-masm-x64"
        } else if windows_startup.is_some() {
            "boom-windows-startup-program-v56-masm-x64"
        } else if access_context.is_some() {
            "boom-access-context-program-v55-masm-x64"
        } else if thread_bootstrap.is_some() {
            "boom-primordial-thread-program-v54-masm-x64"
        } else if thread_natives.is_some() {
            "boom-thread-native-program-v53-masm-x64"
        } else if unsafe_bootstrap.is_some() {
            "boom-unsafe-bootstrap-program-v52-masm-x64"
        } else if !signal_lookup_bindings.is_empty() {
            "boom-signal-lookup-program-v48-masm-x64"
        } else if !string_prefix.is_empty() {
            "boom-string-prefix-program-v47-masm-x64"
        } else if system_streams.is_some() {
            "boom-system-streams-program-v46-masm-x64"
        } else if linker.system_startup.is_some() {
            "boom-system-startup-program-v46-masm-x64"
        } else if !string_chars.is_empty() {
            "boom-string-chars-program-v45-masm-x64"
        } else if typed_arrays.is_some() {
            "boom-typed-arrays-program-v44-masm-x64"
        } else if !vm_registration.is_empty() {
            "boom-vm-registration-program-v43-masm-x64"
        } else if !protected_constructors.is_empty() {
            "boom-protected-constructor-program-v42-masm-x64"
        } else if !array_clones.is_empty() {
            "boom-array-clone-program-v41-masm-x64"
        } else if !string_replace.is_empty() {
            "boom-string-replace-program-v40-masm-x64"
        } else if class_queries.is_some() {
            "boom-class-query-program-v39-masm-x64"
        } else if vm_properties.is_some() {
            "boom-vm-properties-program-v38-masm-x64"
        } else if !string_storage.is_empty()
            || builder_snapshot.is_some()
            || !bitcasts.is_empty()
            || !jdk_bridges.is_empty()
        {
            "boom-string-storage-program-v37-masm-x64"
        } else if !hex_strings.is_empty() {
            "boom-hex-string-program-v36-masm-x64"
        } else if !identity_hashes.is_empty() {
            "boom-identity-hash-program-v35-masm-x64"
        } else if !string_concat_api.is_empty() {
            "boom-string-concat-api-program-v34-masm-x64"
        } else if platform_properties.is_some() {
            "boom-platform-properties-program-v33-masm-x64"
        } else if constructor_entry.is_some() {
            "boom-constructor-entry-program-v32-masm-x64"
        } else if string_case.is_some() {
            "boom-unicode-comparison-program-v31-masm-x64"
        } else if exception_runtime.is_some() {
            "boom-context32-program-v30-masm-x64"
        } else if throwable_frames {
            "boom-throwable-frames-program-v29-masm-x64"
        } else if stream_fields {
            "boom-stream-fields-program-v28-masm-x64"
        } else if constant_initialization {
            "boom-class-initialization-program-v27-masm-x64"
        } else if runtime_access {
            "boom-runtime-access-program-v26-masm-x64"
        } else if initialized_string_values {
            "boom-decimal-program-v25-masm-x64"
        } else if cds_profile.is_some() {
            "boom-cds-program-v24-masm-x64"
        } else if !string_value_bindings.is_empty() {
            "boom-string-values-program-v23-masm-x64"
        } else if string_services {
            "boom-string-join-program-v22-masm-x64"
        } else if system_services {
            "boom-system-program-v21-masm-x64"
        } else if !primitive_class_bindings.is_empty() {
            "boom-primitive-class-program-v20-masm-x64"
        } else if resource_plan.is_some() {
            "boom-resources-program-v19-masm-x64"
        } else if !monitor_methods.is_empty() {
            "boom-monitors-program-v18-masm-x64"
        } else if lambdas {
            "boom-lambda-program-v17-masm-x64"
        } else if layers {
            "boom-layers-program-v16-masm-x64"
        } else if module_plan.is_some() {
            "boom-modules-program-v15-masm-x64"
        } else if !vm_bindings.is_empty() {
            "boom-vm-program-v14-masm-x64"
        } else if assertion_policy.is_some() {
            "boom-assertions-program-v13-masm-x64"
        } else if graph.volatile_accesses {
            "boom-volatile-program-v12-masm-x64"
        } else if linker.bootstrap_execution() {
            "boom-bootstrap-program-v11-masm-x64"
        } else if linker.hierarchy {
            "boom-compact-program-v10-masm-x64"
        } else if inheritance_runtime {
            "boom-inheritance-program-v9-masm-x64"
        } else if hierarchy_runtime {
            "boom-interface-program-v8-masm-x64"
        } else if checked_types {
            "boom-runtime-types-program-v7-masm-x64"
        } else if dynamic_strings {
            "boom-concat-program-v6-masm-x64"
        } else if mirror_count != 0 {
            "boom-mirror-program-v5-masm-x64"
        } else if strings {
            "boom-string-program-v4-masm-x64"
        } else {
            "boom-object-program-v3-masm-x64"
        }
        .into(),
        entry_id,
        input_fingerprint: files::digest_bytes(&identity).sha256,
        sources,
        symbols,
        classes: states,
        object_layouts,
        string_literals: literals,
        bootstrap_string_runtime: strings,
        bootstrap_string_abi: if dynamic_strings {
            Some(3)
        } else if strings {
            Some(2)
        } else {
            None
        },
        concat_plans,
        lambda_sites,
        record_sites,
        null_guards,
        monitor_methods,
        monitor_notifications,
        runtime_resources,
        resources: resource_plan,
        string_join_plans,
        string_value_bindings,
        primitive_class_bindings,
        dynamic_string_runtime: dynamic_strings,
        runtime_type_bindings,
        runtime_type_map_abi: if checked_types { Some(1) } else { None },
        covariant_reference_arrays: linker.covariant_arrays.get(),
        reference_joins,
        interface_dispatch_abi: (!interface_dispatch.is_empty()).then_some(dispatch_abi),
        interface_dispatch,
        field_maps,
        mirror_types: linker
            .metadata
            .map(|registry| registry.into_inner().types)
            .unwrap_or_default(),
        mirror_name_literals: mirror_names,
        bootstrap_mirror_abi: if mirror_count != 0 {
            Some(if assertion_policy.is_some() { 2 } else { 1 })
        } else {
            None
        },
        assertion_policy,
        vm_bindings,
        cds_profile,
        file_descriptors: fd_plan,
        nest_access,
        constant_class_initialization,
        file_streams,
        initializer_source_abi: (stream_fields || throwable_frames).then_some(2),
        java_frames,
        throwables: throwable_plan,
        exception_runtime,
        string_case,
        constructor_entry,
        thread_bootstrap,
        access_context,
        platform_properties,
        vm_properties,
        class_queries,
        string_concat_api,
        string_replace,
        literal_regex_replacements,
        string_chars,
        string_getchars,
        string_construction,
        string_lowercase,
        string_split,
        reflect_new,
        reflected_constructors,
        reflected_fields,
        class_for_name,
        string_prefix,
        array_clones,
        protected_constructors,
        vm_registration,
        signal_lookup_bindings,
        signal_natives,
        windows_startup,
        class_loaders,
        reflection_arrays,
        scoped_memory,
        winnt_file_system,
        thread_natives,
        unsafe_bootstrap,
        typed_arrays,
        system_startup: linker.system_startup.clone(),
        system_streams,
        identity_hashes,
        hex_strings,
        string_storage,
        builder_snapshot,
        bitcasts,
        jdk_bridges,
        module_plan,
        metadata_input_fingerprint: metadata.map(|context| context.inputs.fingerprint.clone()),
        edges: graph.edges.into_iter().collect(),
        compilation,
        volatile_accesses: graph.volatile_accesses,
        full_game_ready: false,
    };
    files::write_atomic(
        &output.join("program.json"),
        &serde_json::to_vec_pretty(&program)?,
    )?;
    Ok(program)
}

#[allow(clippy::too_many_arguments)]
fn append_class_state(
    assembly: &mut String,
    states: &[ClassState],
    heap: bool,
    literals: Option<usize>,
    mirrors: usize,
    modules: usize,
    layers: bool,
    dynamic_strings: bool,
    context32: bool,
    platform_properties: bool,
    unsafe_constants: Option<usize>,
    access_domains: usize,
    loader_roots: usize,
    lookup_roots: usize,
    class_name_roots: usize,
    class_value_roots: usize,
) {
    assembly.push_str("EXTERN boom_class_ensure:PROC\n.data\nALIGN 8\n");
    for state in states {
        let initializer = if unsafe_constants == Some(state.id) {
            "OFFSET boom_unsafe_constants_initialize".into()
        } else if !state.initialization_dependencies.is_empty()
            || state
                .fields
                .iter()
                .any(|field| field.initial_string.is_some())
        {
            format!("OFFSET boom_prepare_strings{}", state.id)
        } else {
            state
                .initializer
                .map_or("0".into(), |id| format!("OFFSET boom_m{id}_body"))
        };
        if context32 {
            assembly.push_str(&format!("boom_class{} DWORD 0434C4153h, 2, 0, 0\n    QWORD {initializer}\n    DWORD {}, 0\n    QWORD 0, 0, 0, OFFSET boom_class_failure_root{}\n",state.id,state.id,state.id));
        } else {
            assembly.push_str(&format!("boom_class{} DWORD 0434C4153h, 1, 0, 0\n    QWORD {initializer}\n    DWORD {}, 0\n    QWORD 0, 0, 0, 0\n",state.id,state.id));
        }
    }
    assembly.push_str("ALIGN 8\nboom_static_roots LABEL QWORD\n");
    let mut root_count = 0;
    for reference in [true, false] {
        for state in states {
            for field in &state.fields {
                if field.reference == reference {
                    assembly.push_str(&format!(
                        "boom_s{}_{} QWORD 0{}h\n",
                        state.id, field.index, field.initial_bits
                    ));
                    if reference {
                        root_count += 1;
                    }
                }
            }
        }
        if reference && let Some(count) = literals {
            assembly.push_str("boom_literal_roots LABEL QWORD\n");
            for _ in 0..count {
                assembly.push_str("    QWORD 0\n");
            }
            root_count += count;
        }
        if reference && mirrors != 0 {
            assembly.push_str("boom_mirror_roots LABEL QWORD\n");
            for _ in 0..mirrors {
                assembly.push_str("    QWORD 0\n");
            }
            root_count += mirrors;
        }
        if reference && class_name_roots != 0 {
            assembly.push_str("boom_class_name_roots LABEL QWORD\n");
            for _ in 0..class_name_roots {
                assembly.push_str("    QWORD 0\n");
            }
            root_count += class_name_roots;
        }
        if reference && class_value_roots != 0 {
            assembly.push_str("boom_class_value_roots LABEL QWORD\n");
            for _ in 0..class_value_roots {
                assembly.push_str("    QWORD 0\n");
            }
            root_count += class_value_roots;
        }
        if reference && modules != 0 {
            assembly.push_str("boom_module_roots LABEL QWORD\n");
            for _ in 0..modules {
                assembly.push_str("    QWORD 0\n");
            }
            root_count += modules;
        }
        if reference && layers {
            assembly.push_str("boom_layer_roots QWORD 0, 0\n");
            root_count += 2;
        }
        if reference && dynamic_strings {
            assembly.push_str("boom_intern_root QWORD 0\n");
            root_count += 1;
        }
        if reference && context32 {
            for state in states {
                assembly.push_str(&format!("boom_class_failure_root{} QWORD 0\n", state.id));
                root_count += 1;
            }
            assembly
                .push_str("boom_emergency_oom_root QWORD 0\nboom_emergency_stack_root QWORD 0\n");
            root_count += 2;
        }
        if reference && platform_properties {
            assembly.push_str("boom_property_root QWORD 0\n");
            root_count += 1;
        }
        if reference && access_domains != 0 {
            assembly.push_str("boom_access_domain_roots LABEL QWORD\n");
            for _ in 0..access_domains {
                assembly.push_str("    QWORD 0\n");
            }
            root_count += access_domains;
        }
        if reference && loader_roots != 0 {
            assembly.push_str("boom_loader_roots LABEL QWORD\n");
            for _ in 0..loader_roots {
                assembly.push_str("    QWORD 0\n");
            }
            root_count += loader_roots;
        }
        if reference && lookup_roots != 0 {
            assembly.push_str("boom_lookup_failure_roots LABEL QWORD\n");
            for _ in 0..lookup_roots {
                assembly.push_str("    QWORD 0\n");
            }
            root_count += lookup_roots;
        }
        if reference && root_count == 0 {
            assembly.push_str("    QWORD 0\n");
        }
    }
    assembly.push_str(&format!(".code\nPUBLIC boom_get_static_roots\nboom_get_static_roots PROC\n    xor eax, eax\n    test rcx, rcx\n    jz boom_static_roots_done\n    mov DWORD PTR [rcx], {root_count}\n    lea rax, boom_static_roots\nboom_static_roots_done:\n    ret\nboom_get_static_roots ENDP\nPUBLIC boom_get_class_descriptor\nboom_get_class_descriptor PROC\n"));
    for state in states {
        assembly.push_str(&format!(
            "    cmp ecx, {}\n    je boom_descriptor_{}\n",
            state.id, state.id
        ));
    }
    assembly.push_str("    xor eax, eax\n    ret\n");
    for state in states {
        assembly.push_str(&format!(
            "boom_descriptor_{}:\n    lea rax, boom_class{}\n    ret\n",
            state.id, state.id
        ));
    }
    assembly.push_str("boom_get_class_descriptor ENDP\n");
    assembly.push_str("PUBLIC boom_get_static_field\nboom_get_static_field PROC\n");
    for state in states {
        for field in &state.fields {
            assembly.push_str(&format!("    cmp ecx, {}\n    jne boom_field_next_{}_{}\n    cmp edx, {}\n    jne boom_field_next_{}_{}\n    lea rax, boom_s{}_{}\n    ret\nboom_field_next_{}_{}:\n",state.id,state.id,field.index,field.index,state.id,field.index,state.id,field.index,state.id,field.index));
        }
    }
    assembly.push_str("    xor eax, eax\n    ret\nboom_get_static_field ENDP\n");
    assembly.push_str("PUBLIC boom_get_object_layout\nboom_get_object_layout PROC\n");
    if heap {
        for state in states {
            assembly.push_str(&format!("    cmp ecx, {}\n    jne boom_object_layout_next{}\n    lea rax, boom_layout{}\n    ret\nboom_object_layout_next{}:\n",state.id,state.id,state.id,state.id));
        }
    }
    assembly.push_str("    xor eax, eax\n    ret\nboom_get_object_layout ENDP\n");
    for state in states.iter().filter(|state| {
        !state.initialization_dependencies.is_empty()
            || state
                .fields
                .iter()
                .any(|field| field.initial_string.is_some())
    }) {
        assembly.push_str(&format!("boom_prepare_strings{} PROC FRAME\n    sub rsp, 72\n    .allocstack 72\n    .endprolog\n    mov QWORD PTR [rsp+48], rcx\n    mov QWORD PTR [rsp+56], rdx\n",state.id));
        for field in &state.fields {
            if let Some(literal) = field.initial_string {
                assembly.push_str(&format!("    mov rcx, QWORD PTR [boom_heap_ptr]\n    lea rdx, boom_string_pool\n    mov r8d, {literal}\n    mov r9, QWORD PTR [rsp+48]\n    call boom_string_load\n    mov r10, QWORD PTR [rsp+48]\n    cmp DWORD PTR [r10], 0\n    jne boom_prepare_strings{}_done\n    mov QWORD PTR [boom_s{}_{}], rax\n",state.id,state.id,field.index));
            }
        }
        for dependency in &state.initialization_dependencies {
            assembly.push_str(&format!("    lea rcx, boom_class{dependency}\n    mov rdx, QWORD PTR [rsp+48]\n    call boom_class_ensure\n    test eax, eax\n    jnz boom_prepare_strings{}_done\n",state.id));
        }
        if let Some(initializer) = state.initializer {
            assembly.push_str(&format!("    mov rcx, QWORD PTR [rsp+48]\n    mov rdx, QWORD PTR [rsp+56]\n    call boom_m{initializer}_body\n"));
        } else {
            assembly.push_str("    xor eax, eax\n");
        }
        assembly.push_str(&format!(
            "boom_prepare_strings{}_done:\n    add rsp, 72\n    ret\nboom_prepare_strings{} ENDP\n",
            state.id, state.id
        ));
    }
}

fn append_string_pool(
    assembly: &mut String,
    literals: &[StringLiteral],
    dynamic: bool,
) -> Result<()> {
    use std::fmt::Write;
    assembly.push_str("EXTERN boom_string_load:PROC\nEXTERN boom_string_intrinsic:PROC\n.const\nALIGN 8\nboom_string_layout DWORD 04F424A43h, 1\n    QWORD 16\n    DWORD 1, 2\nALIGN 8\nboom_string_array_layout DWORD 052454641h, 1\n    QWORD OFFSET boom_string_layout\n");
    for literal in literals {
        writeln!(
            assembly,
            "ALIGN 2\nboom_string_utf16_{} LABEL WORD",
            literal.id
        )?;
        if literal.utf16.is_empty() {
            assembly.push_str("    WORD 0\n");
        }
        for chunk in literal.utf16.chunks(16) {
            writeln!(
                assembly,
                "    WORD {}",
                chunk
                    .iter()
                    .map(|unit| format!("0{unit:04X}h"))
                    .collect::<Vec<_>>()
                    .join(", ")
            )?;
        }
    }
    assembly.push_str("ALIGN 8\nboom_string_entries LABEL BYTE\n");
    if literals.is_empty() {
        assembly.push_str("    QWORD 0, 0\n");
    }
    for literal in literals {
        writeln!(
            assembly,
            "    QWORD OFFSET boom_string_utf16_{}\n    DWORD {}, 0",
            literal.id,
            literal.utf16.len()
        )?;
    }
    writeln!(
        assembly,
        ".data\nALIGN 8\nboom_string_pool DWORD 053545250h, {}, 0, 0\n    DWORD {}, 0\n    QWORD OFFSET boom_literal_roots, OFFSET boom_string_entries, OFFSET boom_string_layout, 0",
        if dynamic { 3 } else { 2 },
        literals.len()
    )?;
    if dynamic {
        assembly.push_str("    QWORD 0, OFFSET boom_intern_root, 0\n");
    }
    assembly.push_str(".code\n");
    Ok(())
}

#[cfg(test)]
#[path = "discovery_tests.rs"]
mod discovery_tests;
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn explicit_input_cannot_shadow_bootstrap_string_identity() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("String.class");
        fs::write(&path, fixture("java/lang/String", None, 1, 9)).unwrap();
        let output = dir.path().join("output");
        assert!(compile(&[path], "java/lang/String", "run", None, &output, false).is_err());
        assert!(!output.exists());
    }
    #[test]
    fn final_statics_are_only_writable_from_their_own_initializer() {
        struct Fields {
            owner: usize,
        }
        impl numeric::StaticLinker for Fields {
            fn resolve(&self, _: &ClassFile, _: u16) -> Result<(usize, numeric::Signature)> {
                anyhow::bail!("Not a call test")
            }
            fn class_id(&self, _: &ClassFile) -> Result<usize> {
                Ok(0)
            }
            fn field(&self, _: &ClassFile, _: u16) -> Result<numeric::LinkedField> {
                Ok(numeric::LinkedField {
                    owner: self.owner,
                    index: 0,
                    ty: numeric::Type::I32,
                    access: 0x18,
                    narrow: b'I',
                })
            }
        }
        let mut class = ClassFile::parse(&fixture("p/A", None, 1, 9)).unwrap();
        class.methods[0].code.as_mut().unwrap().bytes = vec![0x03, 0xb3, 0, 0, 0x03, 0xac];
        assert!(
            numeric::linked_dependencies(&class, &class.methods[0], &Fields { owner: 0 }).is_err()
        );
        class.methods[0].name = "<clinit>".into();
        class.methods[0].descriptor = "()V".into();
        class.methods[0].code.as_mut().unwrap().bytes = vec![0x03, 0xb3, 0, 0, 0xb1];
        assert!(
            numeric::linked_dependencies(&class, &class.methods[0], &Fields { owner: 0 }).is_ok()
        );
        assert!(
            numeric::linked_dependencies(&class, &class.methods[0], &Fields { owner: 1 }).is_err()
        );
    }
    fn origin(name: &str, bytes: &[u8]) -> crate::bytecode::ClassOrigin {
        crate::bytecode::ClassOrigin {
            generated: None,
            loader: "fixture".into(),
            binary_name: name.replace('/', "."),
            source_id: "fixture.jar".into(),
            jar_entry: format!("{name}.class"),
            java_class_major: 65,
            sha256: files::digest_bytes(bytes).sha256,
        }
    }
    #[test]
    fn bootstrap_discovery_never_resolves_through_an_application_child() {
        struct NoTypes;
        impl types::TypeProvider for NoTypes {
            fn resolve(&self, _: &str, _: &str) -> Result<(Vec<u8>, crate::bytecode::ClassOrigin)> {
                anyhow::bail!("No metadata lookup is required before the loader boundary check")
            }
        }
        let mut calls = Vec::new();
        let mut registry = types::Registry::new(&NoTypes);
        let error = discover_static(
            |loader, name| {
                calls.push((loader.to_owned(), name.to_owned()));
                let bytes = fixture(
                    name,
                    if name == "java/util/BootstrapFixture" {
                        Some("p/Child")
                    } else {
                        None
                    },
                    1,
                    9,
                );
                let mut proof = origin(name, &bytes);
                proof.loader = if name.starts_with("java/") {
                    "bootstrap"
                } else {
                    "vanilla-application"
                }
                .into();
                if proof.loader == "bootstrap" {
                    proof.source_id = "jdk:java.base".into();
                }
                Ok((bytes, proof))
            },
            "java/util/BootstrapFixture",
            "run",
            None,
            Some(&mut registry),
        )
        .unwrap_err();
        assert!(
            format!("{error:#}")
                .contains("Bootstrap bytecode cannot resolve an application definition")
        );
        assert_eq!(calls[1], ("bootstrap".into(), "p/Child".into()));
    }
    #[test]
    fn package_access_includes_the_defining_loader() {
        let classes = [
            ClassFile::parse(&fixture("p/A", None, 1, 9)).unwrap(),
            ClassFile::parse(&fixture("p/B", None, 0, 8)).unwrap(),
        ];
        let sources: Vec<_> = classes
            .iter()
            .enumerate()
            .map(|(index, class)| {
                let mut proof = origin(&class.name, &[]);
                proof.loader = if index == 0 {
                    "bootstrap"
                } else {
                    "explicit-application"
                }
                .into();
                Source {
                    class_name: class.name.clone(),
                    path: PathBuf::from("unused.class"),
                    digest: files::digest_bytes(&[]),
                    origin: Some(proof),
                }
            })
            .collect();
        let linker =
            Linker::with_metadata(&classes, None, "explicit-application", Some(&sources)).unwrap();
        assert!(linker.check_access(&classes[0], &classes[1], 9).is_err());
        assert!(
            linker
                .check_member_access(&classes[0], &classes[1], 8)
                .is_err()
        );
        assert!(
            linker
                .check_member_access(&classes[0], &classes[1], 9)
                .is_ok()
        );
        let mut same_sources = sources;
        same_sources[1].origin.as_mut().unwrap().loader = "bootstrap".into();
        let linker =
            Linker::with_metadata(&classes, None, "explicit-application", Some(&same_sources))
                .unwrap();
        assert!(linker.check_access(&classes[0], &classes[1], 8).is_ok());
    }
    #[test]
    fn lambda_private_lookup_requires_original_creator_proof() {
        let names = ["p/Creator", "p/Other", "p/Creator$$BoomLambda$0025"];
        let classes: Vec<_> = names
            .iter()
            .map(|n| ClassFile::parse(&fixture(n, None, 1, 9)).unwrap())
            .collect();
        let mut sources: Vec<_> = names
            .iter()
            .map(|name| {
                let bytes = fixture(name, None, 1, 9);
                let mut proof = origin(name, &bytes);
                proof.loader = "explicit-application".into();
                Source {
                    class_name: (*name).into(),
                    path: "unused.class".into(),
                    digest: files::digest_bytes(&bytes),
                    origin: Some(proof),
                }
            })
            .collect();
        let check = |sources: &[Source]| {
            let linker =
                Linker::with_metadata(&classes, None, "explicit-application", Some(sources))
                    .unwrap();
            assert!(
                linker
                    .check_member_access(&classes[2], &classes[1], 2)
                    .is_err()
            );
            linker
                .check_member_access(&classes[2], &classes[0], 2)
                .is_ok()
        };
        assert!(!check(&sources)); // A user class with the prefix has no extra privilege.
        let host = sources[0].origin.as_ref().unwrap().clone();
        let generated = sources[2].origin.as_mut().unwrap();
        generated.source_id = "boom:lambda-v1".into();
        generated.generated = Some(Box::new(crate::bytecode::GeneratedOrigin {
            generator: "boom-lambda".into(),
            abi: 1,
            host_loader: host.loader.clone(),
            host_class: names[0].into(),
            host_source_id: host.source_id.clone(),
            host_sha256: host.sha256.clone(),
            site: 37,
        }));
        assert!(check(&sources));
        sources[2]
            .origin
            .as_mut()
            .unwrap()
            .generated
            .as_mut()
            .unwrap()
            .host_sha256 = "00".repeat(32);
        assert!(!check(&sources));
        sources[2]
            .origin
            .as_mut()
            .unwrap()
            .generated
            .as_mut()
            .unwrap()
            .host_sha256 = host.sha256;
        sources[2]
            .origin
            .as_mut()
            .unwrap()
            .generated
            .as_mut()
            .unwrap()
            .host_loader = "bootstrap".into();
        assert!(!check(&sources));
    }
    #[test]
    fn discovery_loads_only_the_transitive_closure_and_checks_provenance() {
        let mut requests = Vec::new();
        let classes = discover_static(
            |_, name| {
                requests.push(name.to_owned());
                let bytes = fixture(name, if name == "p/A" { Some("p/B") } else { None }, 1, 9);
                Ok((bytes.clone(), origin(name, &bytes)))
            },
            "p/A",
            "run",
            None,
            None,
        )
        .unwrap();
        assert_eq!(requests, vec!["p/A", "p/B"]);
        assert_eq!(classes.len(), 2);
        let corrupt = discover_static(
            |_, name| {
                let bytes = fixture(name, None, 1, 9);
                let mut source = origin(name, &bytes);
                source.sha256 = "0".repeat(64);
                Ok((bytes, source))
            },
            "p/A",
            "run",
            None,
            None,
        );
        assert!(corrupt.is_err());
        let mixed = discover_static(
            |_, name| {
                let bytes = fixture(name, if name == "p/A" { Some("p/B") } else { None }, 1, 9);
                let mut source = origin(name, &bytes);
                source.loader = name.into();
                Ok((bytes, source))
            },
            "p/A",
            "run",
            None,
            None,
        );
        assert!(mixed.is_err());
    }
    // Tiny valid class files keep linker/access tests independent of javac.
    fn fixture(name: &str, target: Option<&str>, class_access: u16, access: u16) -> Vec<u8> {
        fn u16v(out: &mut Vec<u8>, value: u16) {
            out.extend_from_slice(&value.to_be_bytes());
        }
        fn utf(out: &mut Vec<u8>, value: &str) {
            out.push(1);
            u16v(out, value.len() as u16);
            out.extend_from_slice(value.as_bytes());
        }
        let mut out = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65];
        u16v(&mut out, 12);
        utf(&mut out, name);
        out.push(7);
        u16v(&mut out, 1);
        utf(&mut out, "java/lang/Object");
        out.push(7);
        u16v(&mut out, 3);
        utf(&mut out, "run");
        utf(&mut out, "(I)I");
        utf(&mut out, "Code");
        utf(&mut out, target.unwrap_or(name));
        out.push(7);
        u16v(&mut out, 8);
        out.push(12);
        u16v(&mut out, 5);
        u16v(&mut out, 6);
        out.push(10);
        u16v(&mut out, 9);
        u16v(&mut out, 10);
        for value in [class_access | 0x20, 2, 4, 0, 0, 1, access, 5, 6, 1, 7] {
            u16v(&mut out, value);
        }
        let code: &[u8] = if target.is_some() {
            &[0x1a, 0xb8, 0, 11, 0xac]
        } else {
            &[0x1a, 0xac]
        };
        out.extend_from_slice(&(12u32 + code.len() as u32).to_be_bytes());
        u16v(&mut out, 1);
        u16v(&mut out, 1);
        out.extend_from_slice(&(code.len() as u32).to_be_bytes());
        out.extend_from_slice(code);
        for _ in 0..3 {
            u16v(&mut out, 0);
        }
        out
    }
    fn run_access(target_class: u16, target_method: u16, target_name: &str) -> Result<()> {
        let dir = tempfile::tempdir()?;
        let a = dir.path().join("A.class");
        let b = dir.path().join("B.class");
        fs::write(&a, fixture("p/A", Some(target_name), 1, 9))?;
        fs::write(&b, fixture(target_name, None, target_class, target_method))?;
        let output = dir.path().join("output");
        let result = compile(&[a, b], "p/A", "run", None, &output, false);
        if result.is_err() {
            assert!(!output.exists());
        }
        result.map(|_| ())
    }
    #[test]
    fn volatile_field_flags_preserve_the_final_field_prohibition() {
        let mut class = ClassFile::parse(&fixture("p/Volatile", None, 1, 9)).unwrap();
        class.fields = 1;
        class.field_info.push(super::super::classfile::Field {
            name: "value".into(),
            descriptor: "J".into(),
            access: 0x40,
            constant_value: None,
        });
        assert!(validate_provided_class(&class, None).is_ok());
        class.field_info[0].access = 0x48;
        assert!(validate_provided_class(&class, None).is_ok());
        class.field_info[0].access = 0x50;
        assert!(validate_provided_class(&class, None).is_err());
        class.field_info[0].access = 0x58;
        assert!(validate_provided_class(&class, None).is_err());
    }
    #[test]
    fn access_control_distinguishes_private_package_and_public() {
        assert!(run_access(1, 9, "q/B").is_ok());
        assert!(run_access(0, 8, "p/B").is_ok());
        assert!(run_access(1, 10, "p/B").is_err()); // private, another class
        assert!(run_access(1, 8, "q/B").is_err()); // package access, other package
        assert!(run_access(0, 9, "q/B").is_err()); // inaccessible declaring class
        assert!(run_access(1, 12, "q/B").is_err()); // protected without inheritance
        assert!(run_access(1, 1, "p/B").is_err()); // wrong invocation kind
    }
    #[test]
    fn input_order_does_not_change_symbols_or_generated_assembly() {
        let dir = tempfile::tempdir().unwrap();
        let a = dir.path().join("A.class");
        let b = dir.path().join("B.class");
        fs::write(&a, fixture("p/A", Some("p/B"), 1, 9)).unwrap();
        fs::write(&b, fixture("p/B", None, 1, 9)).unwrap();
        let first = compile(
            &[a.clone(), b.clone()],
            "p/A",
            "run",
            None,
            &dir.path().join("first"),
            false,
        )
        .unwrap();
        let second = compile(
            &[b, a],
            "p/A",
            "run",
            None,
            &dir.path().join("second"),
            false,
        )
        .unwrap();
        assert_eq!(
            first.compilation.assembly_digest,
            second.compilation.assembly_digest
        );
        assert_eq!(first.entry_id, second.entry_id);
        assert_eq!(first.input_fingerprint, second.input_fingerprint);
        assert_eq!(first.symbols.len(), 2);
        assert_eq!(first.edges, vec![(0, 1)]);
    }
    #[test]
    fn recursive_call_graph_links_to_guarded_methods() {
        let dir = tempfile::tempdir().unwrap();
        let a = dir.path().join("A.class");
        let b = dir.path().join("B.class");
        fs::write(&a, fixture("p/A", Some("p/B"), 1, 9)).unwrap();
        fs::write(&b, fixture("p/B", Some("p/A"), 1, 9)).unwrap();
        let program = compile(
            &[a, b],
            "p/A",
            "run",
            None,
            &dir.path().join("recursive"),
            false,
        )
        .unwrap();
        assert_eq!(program.symbols.len(), 2);
        assert_eq!(program.edges, vec![(0, 1), (1, 0)]);
    }
    #[test]
    fn missing_and_duplicate_definitions_fail_before_writing_outputs() {
        let dir = tempfile::tempdir().unwrap();
        let a = dir.path().join("A.class");
        let b = dir.path().join("B.class");
        fs::write(&a, fixture("p/A", Some("p/B"), 1, 9)).unwrap();
        fs::write(&b, fixture("p/B", Some("p/A"), 1, 9)).unwrap();
        for (name, inputs) in [
            ("missing", vec![a.clone()]),
            ("duplicate", vec![a.clone(), a.clone()]),
        ] {
            let output = dir.path().join(name);
            assert!(compile(&inputs, "p/A", "run", None, &output, false).is_err());
            assert!(!output.exists());
        }
    }
}
