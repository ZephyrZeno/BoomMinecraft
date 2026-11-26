use std::path::PathBuf;

use anyhow::Result;
use boom_minecraft::{
    bytecode::{BytecodeProvider, VanillaBytecodeProvider},
    launch,
    lock::{InputLock, Side},
    prepare::{self, PrepareOptions},
    tools,
};
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(
    name = "boom",
    version,
    about = "Java bytecode to x86-64 assembly compiler and Minecraft 1.21.1 inputs"
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Assemble one MASM unit with byte-identity COFF reuse; development tool.
    AssembleUnit {
        #[arg(long)]
        source: PathBuf,
        #[arg(long)]
        output: PathBuf,
        #[arg(long, default_value = ".boom/assembly-object-cache/v1")]
        cache: PathBuf,
        #[arg(long)]
        no_cache: bool,
    },
    /// Verify nominal operands and emit unlinked MASM candidates from persisted IR.
    CompileTranslation {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long)]
        ir: PathBuf,
        #[arg(long)]
        output: PathBuf,
        #[arg(long, default_value_t = 8)]
        workers: usize,
        #[arg(long)]
        assemble: bool,
    },
    /// Lower every method in a verified plan into link-independent symbolic IR.
    LowerTranslation {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long)]
        plan: PathBuf,
        #[arg(long, default_value_t = 8)]
        workers: usize,
        #[arg(long)]
        output: PathBuf,
    },
    /// Inventory all locked methods and group compatibility work; emits no game code.
    PlanTranslation {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long, default_value_t = 8)]
        workers: usize,
        #[arg(long)]
        output: PathBuf,
    },
    /// Inspect the original Windows File.path cache; no Java initializer execution.
    InspectWindowsFileSystem {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Prepare source-verified word boundary tables for the assembly case runtime.
    InspectWordBreak {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Inspect the source-verified Windows signal lookup VM contract; no game execution.
    InspectSignalRuntime {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Export source-verified original JDK method bridges for development inspection.
    InspectJdkBridges {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long = "bridge-id", required = true)]
        ids: Vec<u16>,
        #[arg(long)]
        output: PathBuf,
    },
    /// Inspect constant Field filter registration operands; does not run Java.
    InspectFieldFilters {
        #[arg(long)]
        class_file: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Validate locked exception tables and emit ordered rows; no game execution.
    PlanExceptions {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long = "class")]
        class_name: String,
        #[arg(long)]
        output: PathBuf,
    },
    /// Prepare locked InetAddress JNI field metadata; does not initialize Java or sockets.
    PlanInetAddress {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long)]
        output: PathBuf,
        #[arg(long, default_value = "java/net/InetAddress")]
        owner: String,
    },
    /// Inspect source-verified member resolution, field layouts and initialization dependencies.
    PlanHierarchy {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long = "class-file")]
        class_files: Vec<PathBuf>,
        #[arg(long = "class", required = true)]
        classes: Vec<String>,
        #[arg(long)]
        requests: Option<PathBuf>,
        #[arg(long)]
        output: PathBuf,
    },
    /// Verify a system module snapshot and emit its resolved graph; no execution.
    PlanBootModules {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_modules: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Extract and resolve system module metadata from the locked image; no JVM execution.
    PrepareJdkModules {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Extract classes of the original default resolved system modules for batch compilation.
    PrepareJdkClasses {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_modules: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Extract java.base compiler inputs from the verified, locked JDK image.
    PrepareJdkBase {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Build loader-aware descriptor/hierarchy metadata; does not compile or start a game.
    PlanTypes {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: PathBuf,
        #[arg(long = "class", required = true)]
        classes: Vec<String>,
        #[arg(long = "type")]
        descriptors: Vec<String>,
        #[arg(long)]
        output: PathBuf,
    },
    /// Discover the supported method/object closure directly from verified vanilla inputs.
    CompileLockedProgram {
        /// VM bootstrap only: construct and attach the primordial platform Thread.
        #[arg(long, requires = "jdk_base")]
        vm_primordial_thread: bool,
        /// VM only: initialize physical Module fields before Java class initialization.
        #[arg(long, requires = "jdk_base", conflicts_with = "vm_primordial_thread")]
        vm_module_bootstrap: bool,
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        jdk_base: Option<PathBuf>,
        #[arg(long, requires = "jdk_base")]
        enable_assertions: bool,
        #[arg(long, requires = "jdk_base")]
        jdk_modules: Option<PathBuf>,
        #[arg(long, requires = "jdk_base")]
        enable_system_assertions: bool,
        /// Frozen native-image paths and -D properties (development CLI).
        #[arg(long, requires = "jdk_base")]
        vm_profile: Option<PathBuf>,
        #[arg(long)]
        entry_class: String,
        #[arg(long)]
        method: String,
        #[arg(long)]
        descriptor: Option<String>,
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        assemble: bool,
    },
    /// Link explicit classes, exact named objects and initialization into one assembly module.
    CompileProgram {
        /// Development-only: emit the VM lookup catalog without skipping Java startup guards.
        #[arg(long, requires = "jdk_modules")]
        vm_class_lookup: bool,
        /// VM only: initialize the original unnamed Module before Java initialization.
        #[arg(long, requires = "jdk_base")]
        vm_module_bootstrap: bool,
        #[arg(long = "class-file", required = true)]
        class_files: Vec<PathBuf>,
        #[arg(long, requires = "jdk_base")]
        metadata_lock: Option<PathBuf>,
        /// Leading frozen resource JARs for explicit development class inputs.
        #[arg(long = "resource-jar", requires = "metadata_lock")]
        resource_jars: Vec<PathBuf>,
        #[arg(long, requires = "metadata_lock")]
        jdk_base: Option<PathBuf>,
        #[arg(long, requires = "jdk_base")]
        enable_assertions: bool,
        #[arg(long, requires = "jdk_base")]
        jdk_modules: Option<PathBuf>,
        #[arg(long, requires = "jdk_base")]
        enable_system_assertions: bool,
        #[arg(long, requires = "jdk_base")]
        vm_profile: Option<PathBuf>,
        #[arg(long)]
        entry_class: String,
        #[arg(long)]
        method: String,
        #[arg(long)]
        descriptor: Option<String>,
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        assemble: bool,
    },
    /// Offline batch of uniquely named methods; the assembler environment is shared.
    CompileManagedClass {
        #[arg(long)]
        class_file: PathBuf,
        #[arg(long = "method", required = true)]
        methods: Vec<String>,
        #[arg(long)]
        output: PathBuf,
        #[arg(long,default_value_t=8,value_parser=clap::value_parser!(u16).range(1..=64))]
        jobs: u16,
        #[arg(long)]
        assemble: bool,
    },
    /// Compile typed primitive bytecode using the context/argument-vector assembly ABI.
    CompileManaged {
        #[arg(long)]
        class_file: PathBuf,
        #[arg(long)]
        method: String,
        #[arg(long)]
        descriptor: Option<String>,
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        assemble: bool,
    },
    /// Diagnostic host for a numeric DLL; arguments are hexadecimal raw value bits.
    ExecuteManaged {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long = "arg-bits")]
        arguments: Vec<String>,
    },
    /// Player launch entry; translation/build work belongs inside this flow.
    Play {
        #[arg(long, default_value = ".boom/runs/native-client")]
        game_dir: PathBuf,
        #[arg(long, default_value_t=4096, value_parser=clap::value_parser!(u32).range(512..=32768))]
        memory_mib: u32,
        #[arg(long)]
        auth_file: Option<PathBuf>,
        #[arg(long)]
        dry_run: bool,
    },
    /// Compile eligible static int methods across the locked class set using bounded workers.
    CompileSet {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        output: PathBuf,
        #[arg(long, default_value_t=boom_minecraft::parallel::recommended_jobs() as u16, value_parser=clap::value_parser!(u16).range(1..=64))]
        jobs: u16,
        #[arg(long)]
        assemble: bool,
        /// Use the typed I/J/F/D primitive backend and context ABI.
        #[arg(long)]
        numeric: bool,
    },
    /// Compile a static Java int method directly into readable x86-64 MASM.
    CompileAsm {
        #[arg(long)]
        class_file: PathBuf,
        #[arg(long)]
        method: String,
        #[arg(long)]
        descriptor: Option<String>,
        #[arg(long)]
        output: PathBuf,
        /// Assemble and link the generated assembly with MSVC, without a JVM.
        #[arg(long)]
        assemble: bool,
    },
    /// Execute a hash-verified compiler-produced integer method in this process.
    ExecuteAsm {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long = "arg", allow_hyphen_values = true)]
        arguments: Vec<i32>,
    },
    /// Collect dynamic Java metadata from a real vanilla server --help startup.
    CollectMetadata {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        native_image: Option<PathBuf>,
        #[arg(long, default_value = ".boom/metadata/server-startup")]
        output: PathBuf,
        /// Exercise vanilla settings initialization without accepting the EULA.
        #[arg(long)]
        init_settings: bool,
    },
    /// Inspect class origins, Java versions and classpath shadowing for AOT input.
    Inspect {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    /// Report Java and Native Image availability without changing the machine.
    Doctor {
        #[arg(long)]
        java: Option<PathBuf>,
        #[arg(long)]
        native_image: Option<PathBuf>,
    },
    /// Verify vanilla inputs, unpack server dependencies, and publish an input lock.
    Prepare {
        #[arg(long, value_enum)]
        side: Side,
        #[arg(long, default_value = ".boom/cache")]
        cache: PathBuf,
        #[arg(long)]
        minecraft_dir: Option<PathBuf>,
        #[arg(long)]
        metadata: Option<PathBuf>,
        #[arg(long)]
        server_jar: Option<PathBuf>,
        #[arg(long)]
        java: Option<PathBuf>,
        /// Download missing official game files; never accepts the server EULA.
        #[arg(long)]
        download: bool,
        /// Maximum workers for verified asset preparation.
        #[arg(long, default_value_t=8, value_parser=clap::value_parser!(u16).range(1..=64))]
        jobs: u16,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    /// Verify all locked files and Java runtime inputs offline.
    Verify {
        #[arg(long)]
        lock: PathBuf,
    },
    /// Launch the original JVM reference, or print a redacted argument-vector plan.
    Reference {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        game_dir: Option<PathBuf>,
        /// Caller-provided authenticated client session; not stored in input locks.
        #[arg(long)]
        auth_file: Option<PathBuf>,
        #[arg(long, allow_hyphen_values = true)]
        jvm_arg: Vec<String>,
        #[arg(long)]
        dry_run: bool,
    },
    /// Invoke Java 21 Native Image, or inspect the exact build plan.
    BuildNative {
        #[arg(long)]
        lock: PathBuf,
        #[arg(long)]
        native_image: Option<PathBuf>,
        #[arg(long)]
        metadata_dir: Option<PathBuf>,
        /// Maximum compiler worker threads.
        #[arg(long, default_value_t=8, value_parser=clap::value_parser!(u16).range(1..=256))]
        jobs: u16,
        /// Maximum Java heap for the compiler, in GiB.
        #[arg(long, default_value_t=16, value_parser=clap::value_parser!(u16).range(1..=512))]
        build_heap_gib: u16,
        #[arg(long)]
        output: Option<PathBuf>,
        #[arg(long)]
        dry_run: bool,
    },
}

fn execute() -> Result<i32> {
    match Cli::parse().command {
        Commands::AssembleUnit {
            source,
            output,
            cache,
            no_cache,
        } => {
            let log = output.with_extension("assembler.log");
            let result = boom_minecraft::assembly_cache::assemble(
                &source,
                &output,
                &log,
                (!no_cache).then_some(cache.as_path()),
            )?;
            println!("{}", serde_json::to_string_pretty(&result)?);
            if !result.success {
                return Ok(result.exit_code.filter(|c| *c != 0).unwrap_or(1));
            }
        }
        Commands::CompileTranslation {
            lock,
            jdk_base,
            ir,
            output,
            workers,
            assemble,
        } => {
            let inputs = InputLock::read(&lock)?;
            let summary = boom_minecraft::compiler::batch_compile::compile(
                &inputs, &jdk_base, &ir, &output, workers, assemble,
            )?;
            println!("{}", serde_json::to_string_pretty(&summary)?);
        }
        Commands::LowerTranslation {
            lock,
            jdk_base,
            plan,
            workers,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let summary = boom_minecraft::compiler::translation_ir::lower(
                &inputs, &jdk_base, &plan, &output, workers,
            )?;
            println!("{}", serde_json::to_string_pretty(&summary)?);
        }
        Commands::PlanTranslation {
            lock,
            jdk_base,
            workers,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let plan = boom_minecraft::compiler::translation_plan::plan(
                &inputs, &jdk_base, &output, workers,
            )?;
            println!("{}", serde_json::to_string_pretty(&plan)?);
        }
        Commands::InspectFieldFilters { class_file, output } => {
            let result = boom_minecraft::compiler::field_filters::inspect(&class_file, &output)?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Commands::PlanInetAddress {
            lock,
            jdk_base,
            output,
            owner,
        } => {
            let inputs = InputLock::read(&lock)?;
            let plan = boom_minecraft::compiler::inet_address::inspect(
                &inputs, &jdk_base, &output, &owner,
            )?;
            println!("{}", serde_json::to_string_pretty(&plan)?);
        }
        Commands::PlanHierarchy {
            lock,
            jdk_base,
            class_files,
            classes,
            requests,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let requests: Vec<boom_minecraft::compiler::hierarchy::Request> = requests
                .map(|path| -> Result<_> {
                    use std::io::Read;
                    let mut bytes = Vec::new();
                    std::fs::File::open(path)?
                        .take(4 * 1024 * 1024 + 1)
                        .read_to_end(&mut bytes)?;
                    anyhow::ensure!(
                        bytes.len() <= 4 * 1024 * 1024,
                        "Hierarchy requests exceed byte budget"
                    );
                    Ok(serde_json::from_slice(&bytes)?)
                })
                .transpose()?
                .unwrap_or_default();
            let result = boom_minecraft::compiler::hierarchy::plan(
                &inputs,
                &jdk_base,
                &class_files,
                &classes,
                &requests,
                &output,
            )?;
            println!(
                "{}",
                serde_json::json!({"types":result.types.len(),"roots":result.roots.len(),"calls":result.calls.len(),"execution_wired":result.execution_wired,"full_game_ready":false,"output":output})
            );
        }
        Commands::PlanExceptions {
            lock,
            jdk_base,
            class_name,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let result = boom_minecraft::compiler::exceptions::plan(
                &inputs,
                &jdk_base,
                &class_name,
                &output,
            )?;
            println!(
                "{}",
                serde_json::json!({"methods":result.methods.len(), "types":result.types.len(),
                "execution_wired":false, "full_game_ready":false, "output":output})
            );
        }
        Commands::PlanBootModules {
            lock,
            jdk_modules,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let snapshot = boom_minecraft::boot_modules::plan(&inputs, &jdk_modules, &output)?;
            println!(
                "{}",
                serde_json::json!({"snapshot_fingerprint":snapshot.fingerprint,"available":snapshot.modules.len(),"resolved":snapshot.graph.resolved.len(),"module_layer_execution":false,"full_game_ready":false,"output":output.join("boot-modules.json")})
            );
        }
        Commands::PrepareJdkModules { lock, output } => {
            let inputs = InputLock::read(&lock)?;
            let snapshot = boom_minecraft::boot_modules::prepare(&inputs, &output)?;
            println!(
                "{}",
                serde_json::json!({"available":snapshot.modules.len(),"roots":snapshot.graph.roots.len(),"resolved":snapshot.graph.resolved.len(),"fingerprint":snapshot.fingerprint,"manifest":output.join("jdk-modules.json"),"game_started":false})
            );
        }
        Commands::PrepareJdkBase { lock, output } => {
            let inputs = InputLock::read(&lock)?;
            let base = boom_minecraft::jdk::prepare(&inputs, &output)?;
            println!(
                "{}",
                serde_json::json!({"classes":base.classes.len(),"fingerprint":base.fingerprint,"manifest":output.join("jdk-base.json"),"game_started":false})
            );
        }
        Commands::PrepareJdkClasses {
            lock,
            jdk_modules,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let catalog = boom_minecraft::jdk_classes::prepare(&inputs, &jdk_modules, &output)?;
            println!(
                "{}",
                serde_json::json!({"classes":catalog.classes.len(),
                "packages":catalog.packages.len(), "fingerprint":catalog.fingerprint,
                "manifest":output.join("jdk-classes.json"),"game_started":false})
            );
        }
        Commands::InspectSignalRuntime {
            lock,
            jdk_base,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let result = boom_minecraft::compiler::signals::inspect(&inputs, &jdk_base, &output)?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Commands::InspectWordBreak {
            lock,
            jdk_base,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let tables =
                boom_minecraft::compiler::word_break::inspect(&inputs, &jdk_base, &output)?;
            println!("{}", serde_json::to_string_pretty(&tables)?);
        }
        Commands::InspectWindowsFileSystem {
            lock,
            jdk_base,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let result =
                boom_minecraft::compiler::winnt_file_system::inspect(&inputs, &jdk_base, &output)?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Commands::InspectJdkBridges {
            lock,
            jdk_base,
            ids,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let result =
                boom_minecraft::compiler::jdk_bridges::inspect(&inputs, &jdk_base, &ids, &output)?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Commands::PlanTypes {
            lock,
            jdk_base,
            classes,
            descriptors,
            output,
        } => {
            let inputs = InputLock::read(&lock)?;
            let result = boom_minecraft::compiler::types::plan(
                &inputs,
                &jdk_base,
                &classes,
                &descriptors,
                &output,
            )?;
            println!(
                "{}",
                serde_json::json!({"types":result.types.len(),"roots":result.roots.len(),"output":output,"assembly_emitted":false,"full_game_ready":result.full_game_ready})
            );
        }
        Commands::CompileLockedProgram {
            vm_primordial_thread,
            vm_module_bootstrap,
            lock,
            jdk_base,
            enable_assertions,
            jdk_modules,
            enable_system_assertions,
            vm_profile,
            entry_class,
            method,
            descriptor,
            output,
            assemble,
        } => {
            let inputs = InputLock::read(&lock)?;
            let profile = vm_profile
                .as_deref()
                .map(boom_minecraft::compiler::vm_properties::Profile::read)
                .transpose()?;
            let result = boom_minecraft::compiler::program::compile_locked_with_vm_profile(
                &inputs,
                &entry_class,
                &method,
                descriptor.as_deref(),
                &output,
                assemble,
                jdk_base.as_deref(),
                boom_minecraft::compiler::assertions::Policy {
                    application_enabled: enable_assertions,
                    system_enabled: enable_system_assertions,
                },
                jdk_modules.as_deref(),
                profile.as_ref(),
                vm_primordial_thread,
                vm_module_bootstrap,
            )?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Commands::CompileProgram {
            vm_class_lookup,
            vm_module_bootstrap,
            class_files,
            metadata_lock,
            resource_jars,
            jdk_base,
            enable_assertions,
            jdk_modules,
            enable_system_assertions,
            vm_profile,
            entry_class,
            method,
            descriptor,
            output,
            assemble,
        } => {
            let metadata_inputs = metadata_lock.as_deref().map(InputLock::read).transpose()?;
            let profile = vm_profile
                .as_deref()
                .map(boom_minecraft::compiler::vm_properties::Profile::read)
                .transpose()?;
            let result = boom_minecraft::compiler::program::compile_with_metadata(
                &class_files,
                &entry_class,
                &method,
                descriptor.as_deref(),
                &output,
                assemble,
                metadata_inputs
                    .as_ref()
                    .zip(jdk_base.as_deref())
                    .map(
                        |(inputs, manifest)| boom_minecraft::compiler::program::MetadataContext {
                            primordial: false,
                            module_bootstrap: vm_module_bootstrap,
                            class_lookup_fixture: vm_class_lookup,
                            inputs,
                            manifest,
                            explicit_sources: true,
                            module_manifest: jdk_modules.as_deref(),
                            resource_jars: &resource_jars,
                            vm_profile: profile.as_ref(),
                            assertions: boom_minecraft::compiler::assertions::Policy {
                                application_enabled: enable_assertions,
                                system_enabled: enable_system_assertions,
                            },
                        },
                    ),
            )?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Commands::CompileManagedClass {
            class_file,
            methods,
            output,
            jobs,
            assemble,
        } => {
            let results = boom_minecraft::compiler::managed::compile_class(
                &class_file,
                &methods,
                &output,
                jobs as usize,
                assemble,
            )?;
            println!("{}", serde_json::to_string_pretty(&results)?);
        }
        Commands::CompileManaged {
            class_file,
            method,
            descriptor,
            output,
            assemble,
        } => {
            let result = boom_minecraft::compiler::managed::compile(
                &class_file,
                &method,
                descriptor.as_deref(),
                &output,
                assemble,
            )?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Commands::ExecuteManaged {
            manifest,
            arguments,
        } => {
            let arguments: Vec<_> = arguments
                .iter()
                .map(|s| u64::from_str_radix(s.strip_prefix("0x").unwrap_or(s), 16))
                .collect::<std::result::Result<_, _>>()?;
            let result = boom_minecraft::compiler::managed::execute(&manifest, &arguments)?;
            println!("{}", serde_json::to_string(&result)?);
        }
        Commands::Play {
            game_dir,
            memory_mib,
            auth_file,
            dry_run,
        } => {
            if dry_run {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&boom_minecraft::startup::plan(
                        &game_dir, memory_mib
                    )?)?
                );
            } else {
                boom_minecraft::startup::play(&game_dir, memory_mib, auth_file.as_deref())?;
            }
        }
        Commands::CompileSet {
            lock,
            output,
            jobs,
            assemble,
            numeric,
        } => {
            let inputs = InputLock::read(&lock)?;
            let report = boom_minecraft::compiler::batch::compile_set(
                &inputs,
                &output,
                jobs as usize,
                assemble,
                numeric,
            )?;
            println!(
                "{}",
                serde_json::json!({"classes":report.classes,"candidates":report.candidate_methods,"supported":report.supported_methods,"workers":report.workers,"elapsed_ms":report.elapsed_ms,"full_game_ready":report.full_game_ready,"report":output.join("report.json")})
            );
        }
        Commands::CompileAsm {
            class_file,
            method,
            descriptor,
            output,
            assemble,
        } => {
            let result = boom_minecraft::compiler::compile(
                &class_file,
                &method,
                descriptor.as_deref(),
                &output,
                assemble,
            )?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Commands::ExecuteAsm {
            manifest,
            arguments,
        } => {
            let value = boom_minecraft::compiler::execute(&manifest, &arguments)?;
            println!("{}", serde_json::json!({"result":value}));
        }
        Commands::CollectMetadata {
            lock,
            native_image,
            output,
            init_settings,
        } => {
            let inputs = InputLock::read(&lock)?;
            anyhow::ensure!(
                inputs.side == Side::Server,
                "Startup metadata collection currently supports the vanilla server only"
            );
            let native = tools::native_image(native_image.as_deref())?;
            let graal_home = native
                .parent()
                .and_then(|path| path.parent())
                .ok_or_else(|| anyhow::anyhow!("Cannot determine GraalVM home"))?;
            let agent = graal_home.join("bin/native-image-agent.dll");
            anyhow::ensure!(
                agent.is_file(),
                "Native Image tracing agent is missing: {}",
                agent.display()
            );
            std::fs::create_dir_all(&output)?;
            let output = boom_minecraft::files::absolute(&output)?;
            anyhow::ensure!(
                !output.to_string_lossy().contains([',', '=', '\r', '\n']),
                "Unsupported character in tracing output path"
            );
            let agent_argument = format!(
                "-agentpath:{}=config-merge-dir={}",
                agent.display(),
                output.display()
            );
            let mut plan = launch::reference_plan(
                &inputs,
                &PathBuf::from(".boom/runs/metadata-server"),
                None,
                &[agent_argument],
            )?;
            plan.kind = "metadata-training-jvm".into();
            plan.arguments.push(
                if init_settings {
                    "--initSettings"
                } else {
                    "--help"
                }
                .into(),
            );
            let code = plan.run_reference()?;
            anyhow::ensure!(code == 0, "Metadata training failed with exit code {code}");
            anyhow::ensure!(
                output.join("reflect-config.json").is_file(),
                "Tracing agent did not produce reflection metadata"
            );
            let scope = if init_settings {
                "server --help and --initSettings startup only"
            } else {
                "server --help startup only"
            };
            let report = serde_json::json!({"input_fingerprint":inputs.fingerprint,"scope":scope,"complete_game_coverage":false,"agent":agent,"agent_digest":boom_minecraft::files::digest(&agent)?});
            boom_minecraft::files::write_atomic(
                &output.join("collection.json"),
                &serde_json::to_vec_pretty(&report)?,
            )?;
            println!("{}", serde_json::json!({"metadata":output,"scope":scope}));
        }
        Commands::Inspect { lock, output } => {
            let inputs = InputLock::read(&lock)?;
            let set = VanillaBytecodeProvider { inputs: &inputs }.snapshot()?;
            if let Some(output) = output {
                boom_minecraft::files::write_atomic(&output, &serde_json::to_vec_pretty(&set)?)?;
            }
            println!(
                "{}",
                serde_json::json!({"classes":set.classes.len(),"shadowed":set.shadowed.len(),"fingerprint":set.input_fingerprint})
            );
        }
        Commands::Doctor { java, native_image } => println!(
            "{}",
            serde_json::to_string_pretty(&tools::doctor(java.as_deref(), native_image.as_deref()))?
        ),
        Commands::Prepare {
            side,
            cache,
            minecraft_dir,
            metadata,
            server_jar,
            java,
            download,
            jobs,
            output,
        } => {
            let options = PrepareOptions {
                side,
                cache,
                minecraft_dir,
                metadata,
                server_jar,
                java,
                download,
                jobs: jobs as usize,
            };
            let mut lock = prepare::prepare(&options)?;
            let output = output
                .unwrap_or_else(|| PathBuf::from(format!(".boom/locks/{}.json", side.name())));
            lock.save(&output)?;
            println!(
                "{}",
                serde_json::json!({"lock":output,"game_version":lock.game_version,"side":side,"files":lock.files.len(),"classpath_entries":lock.classpath.len(),"fingerprint":lock.fingerprint})
            );
        }
        Commands::Verify { lock } => {
            let lock = InputLock::read(&lock)?;
            lock.verify()?;
            println!(
                "{}",
                serde_json::json!({"verified":true,"files":lock.files.len(),"fingerprint":lock.fingerprint})
            );
        }
        Commands::Reference {
            lock,
            game_dir,
            auth_file,
            jvm_arg,
            dry_run,
        } => {
            let lock = InputLock::read(&lock)?;
            let game_dir = game_dir.unwrap_or_else(|| {
                PathBuf::from(format!(".boom/runs/reference-{}", lock.side.name()))
            });
            let plan = launch::reference_plan(&lock, &game_dir, auth_file.as_deref(), &jvm_arg)?;
            if dry_run {
                println!("{}", serde_json::to_string_pretty(&plan.redacted())?);
            } else {
                return plan.run_reference();
            }
        }
        Commands::BuildNative {
            lock,
            native_image,
            metadata_dir,
            jobs,
            build_heap_gib,
            output,
            dry_run,
        } => {
            let lock = InputLock::read(&lock)?;
            let executable = if dry_run && native_image.is_none() {
                tools::native_image(None).unwrap_or_else(|_| PathBuf::from("native-image"))
            } else {
                tools::native_image(native_image.as_deref())?
            };
            let output = output.unwrap_or_else(|| {
                PathBuf::from(format!(
                    ".boom/native/{}/minecraft-{}.exe",
                    lock.fingerprint,
                    lock.side.name()
                ))
            });
            let plan = launch::native_plan(
                &lock,
                &executable,
                &output,
                metadata_dir.as_deref(),
                jobs,
                build_heap_gib,
            )?;
            if dry_run {
                println!("{}", serde_json::to_string_pretty(&plan)?);
            } else {
                launch::build_native(&plan, &lock)?;
            }
        }
    }
    Ok(0)
}

fn main() {
    // The debug linker and metadata walk exceed Windows' 1 MiB main stack for
    // mixed JDK/application graphs. Reserve a bounded compiler stack; this
    // process is a build tool and is never the delivered game runtime.
    let result = std::thread::Builder::new()
        .name("boom-compiler".into())
        .stack_size(16 * 1024 * 1024)
        .spawn(execute)
        .map_err(anyhow::Error::from)
        .and_then(|worker| {
            worker
                .join()
                .map_err(|_| anyhow::anyhow!("Compiler worker panicked"))?
        });
    match result {
        Ok(code) => std::process::exit(code),
        Err(error) => {
            eprintln!("error: {error:#}");
            std::process::exit(1);
        }
    }
}
