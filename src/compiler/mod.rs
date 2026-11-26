pub mod access_context;
pub mod array_clone;
pub mod assertions;
pub mod batch;
pub mod batch_array_clone;
mod batch_bitcasts;
pub mod batch_catalog;
mod batch_class_bootstrap;
mod batch_class_lookup;
mod batch_class_names;
pub mod batch_class_state;
pub mod batch_classes;
pub mod batch_compile;
mod batch_concat;
pub mod batch_dispatch;
mod batch_frames;
pub mod batch_literals;
pub mod batch_metadata;
mod batch_properties;
mod batch_runtime_resources;
mod batch_string_intern;
pub mod batch_system;
pub mod batch_types;
mod batch_unsafe;
mod batch_unsafe_fields;
mod batch_unsafe_memory;
mod batch_vm;
pub mod bitcasts;
pub mod builder_snapshot;
pub mod cds;
pub mod class_for_name;
pub mod class_initialization;
pub mod class_loaders;
pub mod class_queries;
pub mod classfile;
pub mod concat;
pub mod constructor_entries;
pub mod dispatch;
pub mod exceptions;
pub mod field_filters;
pub mod field_maps;
pub mod file_descriptors;
pub mod file_streams;
pub mod frames;
pub mod hex_strings;
pub mod hierarchy;
#[cfg(test)]
mod hierarchy_tests;
pub mod i32;
pub mod identity_hash;
pub mod inet_address;
pub mod jdk_bridges;
pub mod lambdas;
pub mod literal_regex;
pub mod managed;
mod mirrors;
pub mod module_objects;
pub mod modules;
pub mod monitors;
pub mod nests;
pub mod numeric;
pub mod program;
pub mod protected_constructors;
pub mod records;
pub mod reflect_constructors;
pub mod reflect_fields;
pub mod reflect_new;
pub mod reflection_arrays;
pub mod resources;
pub mod runtime_resources;
mod runtime_types;
pub mod scoped_memory;
pub mod shutdown;
pub mod signal_natives;
pub mod signals;
pub mod string_case;
pub mod string_chars;
pub mod string_concat_api;
pub mod string_construction;
pub mod string_getchars;
pub mod string_join;
pub mod string_lowercase;
pub mod string_prefix;
pub mod string_replace;
pub mod string_split;
pub mod string_storage;
pub mod string_values;
pub mod symbolic;
pub mod system_properties;
pub mod system_startup;
pub mod system_streams;
pub mod thread_bootstrap;
pub mod thread_natives;
pub mod throwables;
pub mod translation_ir;
pub mod translation_plan;
pub mod typed_arrays;
pub mod types;
pub mod unsafe_bootstrap;
pub mod unwind;
pub mod vm;
pub mod vm_properties;
pub mod vm_registration;
pub mod windows_startup;
pub mod winnt_file_system;
pub mod word_break;

use std::{
    fs,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

use crate::{files, tools};

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Compilation {
    pub schema: u32,
    pub backend: String,
    pub class_name: String,
    pub method: String,
    pub descriptor: String,
    pub argument_count: usize,
    pub instructions: usize,
    #[serde(default = "one")]
    pub linked_methods: usize,
    pub source: PathBuf,
    pub source_digest: files::FileDigest,
    pub assembly: PathBuf,
    pub assembly_digest: files::FileDigest,
    pub dll: Option<PathBuf>,
    pub dll_digest: Option<files::FileDigest>,
}

fn one() -> usize {
    1
}

pub fn compile(
    class_file: &Path,
    method_name: &str,
    descriptor: Option<&str>,
    output: &Path,
    assemble: bool,
) -> Result<Compilation> {
    let source = files::absolute(class_file)?;
    let bytes = fs::read(&source)?;
    let class = classfile::ClassFile::parse(&bytes)?;
    let method = class.method(method_name, descriptor)?;
    let compiled = i32::compile(&class, method)?;
    fs::create_dir_all(output)?;
    let output = files::absolute(output)?;
    let assembly = output.join("method.asm");
    files::write_atomic(&assembly, compiled.assembly.as_bytes())?;
    let mut result = Compilation {
        schema: 1,
        backend: "boom-i32-v2-masm-x64".into(),
        class_name: class.name.clone(),
        method: method.name.clone(),
        descriptor: method.descriptor.clone(),
        argument_count: compiled.argument_count,
        instructions: compiled.instruction_count,
        linked_methods: compiled.linked_methods,
        source,
        source_digest: files::digest(class_file)?,
        assembly: assembly.clone(),
        assembly_digest: files::digest(&assembly)?,
        dll: None,
        dll_digest: None,
    };
    if assemble {
        let dll = assemble_module(&output, &assembly)?;
        result.dll_digest = Some(files::digest(&dll)?);
        result.dll = Some(dll);
    }
    files::write_atomic(
        &output.join("compilation.json"),
        &serde_json::to_vec_pretty(&result)?,
    )?;
    Ok(result)
}

pub(crate) fn assemble_module(output: &Path, assembly: &Path) -> Result<PathBuf> {
    assemble_module_with_heap(output, assembly, false)
}

pub(crate) fn assemble_module_with_heap(
    output: &Path,
    assembly: &Path,
    heap: bool,
) -> Result<PathBuf> {
    assemble_module_with_runtime(output, assembly, heap, false)
}
pub(crate) fn assemble_module_with_runtime(
    output: &Path,
    assembly: &Path,
    heap: bool,
    classes: bool,
) -> Result<PathBuf> {
    assemble_module_with_strings(output, assembly, heap, classes, false)
}
pub(crate) fn assemble_module_with_strings(
    output: &Path,
    assembly: &Path,
    heap: bool,
    classes: bool,
    strings: bool,
) -> Result<PathBuf> {
    assemble_module_with_mirrors(output, assembly, heap, classes, strings, false)
}
pub(crate) fn assemble_module_with_mirrors(
    output: &Path,
    assembly: &Path,
    heap: bool,
    classes: bool,
    strings: bool,
    mirrors: bool,
) -> Result<PathBuf> {
    ensure!(
        cfg!(windows) && cfg!(target_arch = "x86_64"),
        "Assembly execution currently requires Windows x86-64"
    );
    let object = output.join("method.obj");
    let dll = output.join("method.dll");
    let assembler = tools::msvc_command("ml64.exe")?
        .arg("/nologo")
        .arg("/c")
        .arg(format!("/Fo{}", object.display()))
        .arg(assembly)
        .output()
        .context("Cannot execute MASM")?;
    files::write_atomic(
        &output.join("assemble.log"),
        &[assembler.stdout.as_slice(), assembler.stderr.as_slice()].concat(),
    )?;
    ensure!(
        assembler.status.success(),
        "Assembly failed; inspect {}",
        output.join("assemble.log").display()
    );
    let mut objects = vec![object];
    if heap {
        let runtime = output.join("runtime");
        fs::create_dir_all(&runtime)?;
        let mut modules = vec![
            (
                "heap",
                include_bytes!("../../native/runtime/heap.asm").as_slice(),
            ),
            (
                "monitors",
                include_bytes!("../../native/runtime/monitors.asm").as_slice(),
            ),
            (
                "object_wait",
                include_bytes!("../../native/runtime/object_wait.asm").as_slice(),
            ),
            (
                "thread_registry",
                include_bytes!("../../native/runtime/thread_registry.asm").as_slice(),
            ),
            (
                "arrays",
                include_bytes!("../../native/runtime/arrays.asm").as_slice(),
            ),
            (
                "objects",
                include_bytes!("../../native/runtime/objects.asm").as_slice(),
            ),
            (
                "references",
                include_bytes!("../../native/runtime/references.asm").as_slice(),
            ),
        ];
        if fs::read_to_string(assembly)?.contains("EXTERN boom_identity_hash:PROC\n") {
            modules.push((
                "identity_hash",
                include_bytes!("../../native/runtime/identity_hash.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_array_clone:PROC\n") {
            modules.push((
                "array_clone",
                include_bytes!("../../native/runtime/array_clone.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_typed_multi_new:PROC\n") {
            modules.push((
                "typed_arrays",
                include_bytes!("../../native/runtime/typed_arrays.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_inet_address_init:PROC\n") {
            modules.push((
                "inet_address",
                include_bytes!("../../native/runtime/inet_address.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_shutdown_native:PROC\n") {
            modules.push((
                "shutdown",
                include_bytes!("../../native/runtime/shutdown.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_field_service:PROC\n")
            || fs::read_to_string(assembly)?.contains("EXTERN boom_field_virtual:PROC\n")
        {
            modules.push((
                "reflect_fields",
                include_bytes!("../../native/runtime/reflect_fields.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_vm_native:PROC\n") {
            modules.push((
                "vm_registration",
                include_bytes!("../../native/runtime/vm_registration.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_hex_string:PROC\n") {
            modules.push((
                "hex_strings",
                include_bytes!("../../native/runtime/hex_strings.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_builder_snapshot:PROC\n") {
            modules.push((
                "builder_snapshot",
                include_bytes!("../../native/runtime/builder_snapshot.asm").as_slice(),
            ));
        }
        if strings {
            modules.push((
                "string_concat_api",
                include_bytes!("../../native/runtime/string_concat_api.asm").as_slice(),
            ));
            modules.push((
                "unicode_case",
                include_bytes!("../../native/runtime/unicode_case.asm").as_slice(),
            ));
            modules.push((
                "concat",
                include_bytes!("../../native/runtime/concat.asm").as_slice(),
            ));
            modules.push((
                "string_dynamic",
                include_bytes!("../../native/runtime/string_dynamic.asm").as_slice(),
            ));
            if fs::read_to_string(assembly)?.contains("EXTERN boom_string_new:PROC\n") {
                modules.push((
                    "string_construction",
                    include_bytes!("../../native/runtime/string_construction.asm").as_slice(),
                ));
            }
            if fs::read_to_string(assembly)?.contains("EXTERN boom_class_for_name:PROC\n") {
                modules.push((
                    "class_for_name",
                    include_bytes!("../../native/runtime/class_for_name.asm").as_slice(),
                ));
            }
            if fs::read_to_string(assembly)?.contains("EXTERN boom_reflect_new:PROC\n") {
                modules.push((
                    "reflect_new",
                    include_bytes!("../../native/runtime/reflect_new.asm").as_slice(),
                ));
            }
            if fs::read_to_string(assembly)?.contains("EXTERN boom_string_split:PROC\n") {
                modules.push((
                    "string_split",
                    include_bytes!("../../native/runtime/string_split.asm").as_slice(),
                ));
            }
            if fs::read_to_string(assembly)?.contains("EXTERN boom_string_lowercase:PROC\n") {
                modules.push((
                    "string_lowercase",
                    include_bytes!("../../native/runtime/string_lowercase.asm").as_slice(),
                ));
                modules.push((
                    "word_break",
                    include_bytes!("../../native/runtime/word_break.asm").as_slice(),
                ));
                modules.push((
                    "unicode_context",
                    include_bytes!("../../native/runtime/unicode_context.asm").as_slice(),
                ));
            }
            modules.push((
                "strings",
                include_bytes!("../../native/runtime/strings.asm").as_slice(),
            ));
        }
        if mirrors {
            modules.push((
                "classes32",
                include_bytes!("../../native/runtime/classes32.asm").as_slice(),
            ));
            modules.push((
                "unwind",
                include_bytes!("../../native/runtime/unwind.asm").as_slice(),
            ));
            modules.push((
                "frames",
                include_bytes!("../../native/runtime/frames.asm").as_slice(),
            ));
            modules.push((
                "throwables",
                include_bytes!("../../native/runtime/throwables.asm").as_slice(),
            ));
            modules.push((
                "file_streams",
                include_bytes!("../../native/runtime/file_streams.asm").as_slice(),
            ));
            modules.push((
                "file_descriptors",
                include_bytes!("../../native/runtime/file_descriptors.asm").as_slice(),
            ));
            modules.push((
                "cds",
                include_bytes!("../../native/runtime/cds.asm").as_slice(),
            ));
            modules.push((
                "string_join",
                include_bytes!("../../native/runtime/string_join.asm").as_slice(),
            ));
            modules.push((
                "string_sequence_replace",
                include_bytes!("../../native/runtime/string_sequence_replace.asm").as_slice(),
            ));
            modules.push((
                "system",
                include_bytes!("../../native/runtime/system.asm").as_slice(),
            ));
            modules.push((
                "resources",
                include_bytes!("../../native/runtime/resources.asm").as_slice(),
            ));
            modules.push((
                "layers",
                include_bytes!("../../native/runtime/layers.asm").as_slice(),
            ));
            modules.push((
                "modules",
                include_bytes!("../../native/runtime/modules.asm").as_slice(),
            ));
            modules.push((
                "module_objects",
                include_bytes!("../../native/runtime/module_objects.asm").as_slice(),
            ));
            modules.push((
                "vm_clock",
                include_bytes!("../../native/runtime/vm_clock.asm").as_slice(),
            ));
            modules.push((
                "exceptions",
                include_bytes!("../../native/runtime/exceptions.asm").as_slice(),
            ));
            modules.push((
                "covariant_arrays",
                include_bytes!("../../native/runtime/covariant_arrays.asm").as_slice(),
            ));
            modules.push((
                "runtime_types",
                include_bytes!("../../native/runtime/runtime_types.asm").as_slice(),
            ));
            modules.push((
                "runtime_type_index",
                include_bytes!("../../native/runtime/runtime_type_index.asm").as_slice(),
            ));
            modules.push((
                "mirrors",
                include_bytes!("../../native/runtime/mirrors.asm").as_slice(),
            ));
            modules.push((
                "types",
                include_bytes!("../../native/runtime/types.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("\nboom_get_property_pool PROC\n") {
            modules.push((
                "system_properties",
                include_bytes!("../../native/runtime/system_properties.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("\nboom_get_vm_property_pool PROC\n") {
            modules.push((
                "vm_properties",
                include_bytes!("../../native/runtime/vm_properties.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("\nboom_get_class_query_pool PROC\n") {
            modules.push((
                "class_queries",
                include_bytes!("../../native/runtime/class_queries.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_string_replace:PROC\n") {
            modules.push((
                "string_replace",
                include_bytes!("../../native/runtime/string_replace.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_string_to_chars:PROC\n") {
            modules.push((
                "string_chars",
                include_bytes!("../../native/runtime/string_chars.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_system_stream_set:PROC\n") {
            modules.push((
                "system_streams",
                include_bytes!("../../native/runtime/system_streams.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_string_starts_with:PROC\n") {
            modules.push((
                "string_prefix",
                include_bytes!("../../native/runtime/string_prefix.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_signal_find:PROC\n") {
            modules.push((
                "signals",
                include_bytes!("../../native/runtime/signals.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_thread_native_register:PROC\n") {
            modules.push((
                "thread_natives",
                include_bytes!("../../native/runtime/thread_natives.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_unsafe_native:PROC\n") {
            modules.push((
                "unsafe_bootstrap",
                include_bytes!("../../native/runtime/unsafe_bootstrap.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_signal_native_query:PROC\n") {
            modules.push((
                "signal_natives",
                include_bytes!("../../native/runtime/signal_natives.asm").as_slice(),
            ));
            modules.push((
                "signal_control",
                include_bytes!("../../native/runtime/signal_control.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_windows_error_mode:PROC\n") {
            modules.push((
                "windows_startup",
                include_bytes!("../../native/runtime/windows_startup.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_class_loader_field:PROC\n") {
            modules.push((
                "class_loaders",
                include_bytes!("../../native/runtime/class_loaders.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_reflect_array_allocate:PROC\n") {
            modules.push((
                "reflection_arrays",
                include_bytes!("../../native/runtime/reflection_arrays.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_scoped_native_register:PROC\n") {
            modules.push((
                "scoped_memory",
                include_bytes!("../../native/runtime/scoped_memory.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_winfs_init:PROC\n") {
            modules.push((
                "winnt_file_system",
                include_bytes!("../../native/runtime/winnt_file_system.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_access_context_query:PROC\n") {
            modules.push((
                "access_context",
                include_bytes!("../../native/runtime/access_context.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_runtime_resource:PROC\n") {
            modules.push((
                "runtime_resources",
                include_bytes!("../../native/runtime/runtime_resources.asm").as_slice(),
            ));
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_constructor_service:PROC\n")
            || fs::read_to_string(assembly)?.contains("EXTERN boom_constructor_virtual:PROC\n")
        {
            modules.push((
                "reflect_constructors",
                include_bytes!("../../native/runtime/reflect_constructors.asm").as_slice(),
            ));
        }
        for (name, source) in modules {
            let path = runtime.join(format!("{name}.asm"));
            files::write_atomic(&path, source)?;
            let object = runtime.join(format!("{name}.obj"));
            let result = tools::msvc_command("ml64.exe")?
                .args(["/nologo", "/c"])
                .arg(format!("/Fo{}", object.display()))
                .arg(&path)
                .output()?;
            files::write_atomic(
                &runtime.join(format!("{name}.log")),
                &[result.stdout.as_slice(), result.stderr.as_slice()].concat(),
            )?;
            ensure!(
                result.status.success(),
                "Assembly runtime module failed: {name}"
            );
            objects.push(object);
        }
    }
    if classes {
        let path = output.join("classes-runtime.asm");
        files::write_atomic(&path, include_bytes!("../../native/runtime/classes.asm"))?;
        let object = output.join("classes-runtime.obj");
        let result = tools::msvc_command("ml64.exe")?
            .args(["/nologo", "/c"])
            .arg(format!("/Fo{}", object.display()))
            .arg(&path)
            .output()?;
        files::write_atomic(
            &output.join("classes-runtime.log"),
            &[result.stdout.as_slice(), result.stderr.as_slice()].concat(),
        )?;
        ensure!(
            result.status.success(),
            "Class initialization assembly failed"
        );
        objects.push(object);
    }
    let mut linker_command = tools::msvc_command("link.exe")?;
    linker_command
        .args([
            "/NOLOGO",
            "/DLL",
            "/NOENTRY",
            "/MACHINE:X64",
            "/DYNAMICBASE",
            "/NXCOMPAT",
            "/EXPORT:boom_entry",
        ])
        .arg(format!("/OUT:{}", dll.display()))
        .args(&objects);
    if fs::read_to_string(assembly)?.contains("EXTERN boom_inet_address_init:PROC\n") {
        linker_command.args(["/EXPORT:boom_inet_address_init", "ws2_32.lib"]);
        let source = fs::read_to_string(assembly)?;
        for name in [
            "boom_get_inet_cache",
            "boom_get_inet4_cache",
            "boom_get_inet6_cache",
        ] {
            if source.contains(&format!("PUBLIC {name}\n")) {
                linker_command.arg(format!("/EXPORT:{name}"));
            }
        }
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_inet_address_available:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_inet_address_available",
            "/EXPORT:boom_get_inet_availability",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_boot_unnamed_publish:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_boot_unnamed_publish",
            "/EXPORT:boom_get_boot_unnamed_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_string_get_chars:PROC\n") {
        linker_command.arg("/EXPORT:boom_string_get_chars");
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_class_find_bootstrap:PROC\n") {
        linker_command.arg("/EXPORT:boom_class_find_bootstrap");
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_class_name:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_class_name",
            "/EXPORT:boom_get_class_name_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_class_value_field:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_class_value_field",
            "/EXPORT:boom_get_class_value_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_shutdown_native:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_shutdown_native",
            "/EXPORT:boom_get_shutdown_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_field_service:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_field_service",
            "/EXPORT:boom_field_static_address",
            "/EXPORT:boom_field_instance_address",
            "/EXPORT:boom_get_field_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_field_virtual:PROC\n") {
        linker_command.arg("/EXPORT:boom_field_virtual");
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_constructor_virtual:PROC\n") {
        linker_command.arg("/EXPORT:boom_constructor_virtual");
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_unsafe_native:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_get_unsafe_pool",
            "/EXPORT:boom_unsafe_native",
            "/EXPORT:boom_heap_alloc",
        ]);
    }
    if heap {
        linker_command.args([
            "kernel32.lib",
            "/EXPORT:boom_bind_heap",
            "synchronization.lib",
            "/EXPORT:boom_monitor_enter",
            "/EXPORT:boom_monitor_exit",
            "/EXPORT:boom_heap_create",
            "/EXPORT:boom_heap_collect",
            "/EXPORT:boom_heap_destroy",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_signal_native_query:PROC\n") {
        linker_command.args([
            "user32.lib",
            "/EXPORT:boom_get_signal_native_pool",
            "/EXPORT:boom_bind_signal_transport",
            "/EXPORT:boom_signal_native_query",
            "/EXPORT:boom_signal_native_bind",
            "/EXPORT:boom_signal_control_create",
            "/EXPORT:boom_signal_control_close",
            "/EXPORT:boom_signal_control_snapshot",
            "/EXPORT:boom_signal_control_register",
            "/EXPORT:boom_signal_control_raise",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_thread_native_register:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_get_thread_native_pool",
            "/EXPORT:boom_bind_thread_registry",
            "/EXPORT:boom_thread_native_register",
            "/EXPORT:boom_thread_native_dispatch",
            "/EXPORT:boom_threads_create",
            "/EXPORT:boom_threads_destroy",
            "/EXPORT:boom_threads_attach",
            "/EXPORT:boom_threads_detach",
            "/EXPORT:boom_threads_current",
            "/EXPORT:boom_threads_next_id",
            "/EXPORT:boom_threads_id_address",
            "/EXPORT:boom_object_new",
            "/EXPORT:boom_heap_alloc",
        ]);
    }
    if classes {
        linker_command.args([
            "kernel32.lib",
            "synchronization.lib",
            "/EXPORT:boom_get_static_roots",
            "/EXPORT:boom_get_class_descriptor",
            "/EXPORT:boom_get_static_field",
            "/EXPORT:boom_get_object_layout",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_constructor_service:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_constructor_service",
            "/EXPORT:boom_get_constructor_pool",
            "/EXPORT:boom_get_constructor_vm_layout",
            "/EXPORT:boom_get_constructor_box_layout",
            "/EXPORT:boom_get_constructor_argument_layout",
            "/EXPORT:boom_heap_alloc",
            "/EXPORT:boom_mirror_load",
            "/EXPORT:boom_string_allocate",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_runtime_resource:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_runtime_available_processors",
            "/EXPORT:boom_runtime_resource",
            "/EXPORT:boom_processor_count",
            "/EXPORT:boom_get_processor_pool",
            "/EXPORT:boom_heap_alloc",
            "ntdll.lib",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_monitor_notify:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_monitor_notify",
            "/EXPORT:boom_monitor_notify_all",
            "/EXPORT:boom_heap_alloc",
            "/EXPORT:boom_heap_contains",
        ]);
    }
    if mirrors {
        if fs::read_to_string(assembly)?.contains("EXTERN boom_class_for_name:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_get_for_name_pool",
                "/EXPORT:boom_class_for_name",
                "/EXPORT:boom_heap_contains",
                "/EXPORT:boom_class_loader_key",
                "/EXPORT:boom_string_load",
                "/EXPORT:boom_heap_alloc",
            ]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_reflect_new:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_get_reflect_pool",
                "/EXPORT:boom_reflect_new",
                "/EXPORT:boom_heap_alloc",
                "/EXPORT:boom_exception_create",
                "/EXPORT:boom_mirror_load",
            ]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_string_split:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_get_split_pool",
                "/EXPORT:boom_string_split",
                "/EXPORT:boom_string_load",
                "/EXPORT:boom_string_allocate",
                "/EXPORT:boom_heap_alloc",
            ]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_string_lowercase:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_get_lowercase_pool",
                "/EXPORT:boom_string_lowercase",
                "/EXPORT:boom_string_load",
                "/EXPORT:boom_string_intern",
                "/EXPORT:boom_string_allocate",
                "/EXPORT:boom_heap_alloc",
                "/EXPORT:boom_get_word_plan",
            ]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_string_new:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_string_new",
                "/EXPORT:boom_string_construct_chars",
                "/EXPORT:boom_string_construct_chars_all",
                "/EXPORT:boom_get_constructor_string_pool",
                "/EXPORT:boom_heap_alloc",
            ]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_module_objects_pool_valid:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_get_module_pool",
                "/EXPORT:boom_module_intrinsic",
                "/EXPORT:boom_module_index",
                "/EXPORT:boom_module_load",
                "/EXPORT:boom_module_objects_value",
                "/EXPORT:boom_layer_intrinsic",
            ]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_winfs_init:PROC\n") {
            linker_command.args(["/EXPORT:boom_winfs_init", "/EXPORT:boom_get_winfs_pool"]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_scoped_native_register:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_scoped_native_register",
                "/EXPORT:boom_scoped_close_unavailable",
                "/EXPORT:boom_get_scoped_native_pool",
            ]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_reflect_array_allocate:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_reflect_array_allocate",
                "/EXPORT:boom_get_reflect_array_pool",
                "/EXPORT:boom_heap_alloc",
                "/EXPORT:boom_mirror_load",
                "/EXPORT:boom_runtime_getclass",
            ]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_class_loader_register:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_get_class_loader_native_pool",
                "/EXPORT:boom_class_loader_register",
                "/EXPORT:boom_class_loader_retrieve",
            ]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_class_loader_field:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_get_class_loader_pool",
                "/EXPORT:boom_class_loader_field",
                "/EXPORT:boom_class_loader_bind",
                "/EXPORT:boom_heap_alloc",
                "/EXPORT:boom_mirror_load",
                "/EXPORT:boom_trace_enter",
                "/EXPORT:boom_trace_leave",
                "/EXPORT:boom_trace_release",
            ]);
        }
        if fs::read_to_string(assembly)?.contains("EXTERN boom_access_context_query:PROC\n") {
            linker_command.args([
                "/EXPORT:boom_get_access_context_pool",
                "/EXPORT:boom_access_context_query",
                "/EXPORT:boom_access_bind_domain",
                "/EXPORT:boom_trace_enter",
                "/EXPORT:boom_trace_leave",
                "/EXPORT:boom_trace_head",
                "/EXPORT:boom_trace_release",
                "/EXPORT:boom_mirror_load",
            ]);
        }
        linker_command.args([
            "bcrypt.lib",
            "/EXPORT:boom_get_type_count",
            "/EXPORT:boom_get_type_descriptor",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("\nboom_get_fd_pool PROC\n") {
        linker_command.arg("/EXPORT:boom_get_fd_pool");
    }
    if fs::read_to_string(assembly)?.contains("\nboom_get_property_pool PROC\n") {
        linker_command.args([
            "/EXPORT:boom_get_property_pool",
            "/EXPORT:boom_platform_properties",
            "advapi32.lib",
            "shell32.lib",
            "ole32.lib",
            "ntdll.lib",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("\nboom_get_vm_property_pool PROC\n") {
        linker_command.args([
            "/EXPORT:boom_get_vm_property_pool",
            "/EXPORT:boom_vm_properties",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("\nboom_get_class_query_pool PROC\n") {
        linker_command.args([
            "/EXPORT:boom_get_class_query_pool",
            "/EXPORT:boom_class_is_hidden",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_class_is_instance:PROC\n") {
        linker_command.arg("/EXPORT:boom_class_is_instance");
    }
    if fs::read_to_string(assembly)?.contains("PUBLIC boom_get_storage_string_pool\n") {
        linker_command.arg("/EXPORT:boom_get_storage_string_pool");
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_string_concat_api:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_string_concat_api",
            "/EXPORT:boom_string_allocate",
            "/EXPORT:boom_get_concat_string_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_string_replace:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_string_replace",
            "/EXPORT:boom_string_replace_literal_chars",
            "/EXPORT:boom_get_replace_string_pool",
            "/EXPORT:boom_string_allocate",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_string_join:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_string_join",
            "/EXPORT:boom_string_replace_sequence",
            "/EXPORT:boom_get_sequence_replace_plan",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_identity_hash:PROC\n") {
        linker_command.arg("/EXPORT:boom_identity_hash");
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_string_starts_with:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_string_starts_with",
            "/EXPORT:boom_get_prefix_string_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_system_stream_set:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_system_stream_set",
            "/EXPORT:boom_get_system_stream_pool",
            "/EXPORT:boom_get_stream_storage",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_string_to_chars:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_string_to_chars",
            "/EXPORT:boom_get_chars_string_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_array_clone:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_array_clone",
            "/EXPORT:boom_get_array_clone_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_typed_multi_new:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_typed_multi_new",
            "/EXPORT:boom_typed_array_length",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_vm_native:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_vm_native",
            "/EXPORT:boom_get_vm_native_pool",
            "/EXPORT:boom_vm_adjustment_from_filetime",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_hex_string:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_hex_string",
            "/EXPORT:boom_string_allocate",
            "/EXPORT:boom_get_hex_string_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("EXTERN boom_builder_snapshot:PROC\n") {
        linker_command.args([
            "/EXPORT:boom_builder_snapshot",
            "/EXPORT:boom_get_builder_snapshot_pool",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("\nboom_get_stream_pool PROC\n") {
        linker_command.arg("/EXPORT:boom_get_stream_pool");
    }
    if fs::read_to_string(assembly)?.contains("\nboom_get_trace_pool PROC\n") {
        linker_command.args([
            "/EXPORT:boom_get_trace_pool",
            "/EXPORT:boom_release_trace_pool",
            "/EXPORT:boom_get_throwable_plan",
        ]);
    }
    if fs::read_to_string(assembly)?.contains("\nboom_get_exception_vm PROC\n") {
        linker_command.args(["/EXPORT:boom_entry32", "/EXPORT:boom_get_exception_vm"]);
    }
    let linker = linker_command
        .output()
        .context("Cannot execute MSVC linker")?;
    files::write_atomic(
        &output.join("link.log"),
        &[linker.stdout.as_slice(), linker.stderr.as_slice()].concat(),
    )?;
    ensure!(
        linker.status.success() && dll.is_file(),
        "Linking failed; inspect {}",
        output.join("link.log").display()
    );
    Ok(dll)
}

pub fn execute(manifest: &Path, arguments: &[i32]) -> Result<i32> {
    let compilation: Compilation = serde_json::from_slice(&fs::read(manifest)?)?;
    ensure!(
        compilation.schema == 1
            && matches!(
                compilation.backend.as_str(),
                "boom-i32-v1-masm-x64" | "boom-i32-v2-masm-x64"
            ),
        "Unknown compiler manifest"
    );
    let count = i32::argument_count(&compilation.descriptor)?;
    ensure!(
        count == compilation.argument_count && count == arguments.len(),
        "Argument count does not match the compiled method"
    );
    ensure!(
        files::digest(&compilation.assembly)? == compilation.assembly_digest,
        "Assembly changed since compilation"
    );
    let dll = compilation
        .dll
        .context("Method has not been assembled and linked")?;
    let expected = compilation.dll_digest.context("Missing DLL identity")?;
    ensure!(files::digest(&dll)? == expected, "Compiled DLL changed");
    execute_dll(&dll, arguments)
}

#[cfg(windows)]
fn execute_dll(path: &Path, arguments: &[i32]) -> Result<i32> {
    use std::{ffi::c_void, os::windows::ffi::OsStrExt};
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn LoadLibraryExW(name: *const u16, file: *mut c_void, flags: u32) -> *mut c_void;
        fn GetProcAddress(module: *mut c_void, name: *const u8) -> *mut c_void;
        fn FreeLibrary(module: *mut c_void) -> i32;
    }
    struct Library(*mut c_void);
    impl Drop for Library {
        fn drop(&mut self) {
            unsafe {
                FreeLibrary(self.0);
            }
        }
    }
    let path = files::absolute(path)?;
    let wide: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    // Only compiler-produced, hash-verified code with a known integer ABI enters
    // here. The differential driver runs this command in a disposable process.
    unsafe {
        let module = LoadLibraryExW(wide.as_ptr(), std::ptr::null_mut(), 0x100 | 0x1000);
        ensure!(
            !module.is_null(),
            "Cannot load compiled DLL: {}",
            std::io::Error::last_os_error()
        );
        let module = Library(module);
        let symbol = GetProcAddress(module.0, c"boom_entry".as_ptr().cast());
        ensure!(!symbol.is_null(), "Compiled DLL has no boom_entry export");
        let result = match arguments {
            [] => std::mem::transmute::<*mut c_void, unsafe extern "C" fn() -> i32>(symbol)(),
            [a] => std::mem::transmute::<*mut c_void, unsafe extern "C" fn(i32) -> i32>(symbol)(*a),
            [a, b] => std::mem::transmute::<*mut c_void, unsafe extern "C" fn(i32, i32) -> i32>(
                symbol,
            )(*a, *b),
            [a, b, c] => std::mem::transmute::<
                *mut c_void,
                unsafe extern "C" fn(i32, i32, i32) -> i32,
            >(symbol)(*a, *b, *c),
            [a, b, c, d] => std::mem::transmute::<
                *mut c_void,
                unsafe extern "C" fn(i32, i32, i32, i32) -> i32,
            >(symbol)(*a, *b, *c, *d),
            _ => anyhow::bail!("Unsupported native method ABI"),
        };
        Ok(result)
    }
}

#[cfg(not(windows))]
fn execute_dll(_path: &Path, _arguments: &[i32]) -> Result<i32> {
    anyhow::bail!("Execution requires Windows x86-64")
}
