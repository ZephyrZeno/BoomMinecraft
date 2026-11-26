//! Build and diagnostic execution of the uniform primitive/context ABI.
use super::{
    classfile::ClassFile,
    numeric::{self, Signature, Type},
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::{Path, PathBuf},
};

pub const BACKEND: &str = "boom-numeric-v1-masm-x64";
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Compilation {
    pub schema: u32,
    pub backend: String,
    pub abi: String,
    pub class_name: String,
    pub method: String,
    pub descriptor: String,
    pub signature: Signature,
    pub instructions: usize,
    pub linked_methods: usize,
    #[serde(default)]
    pub requires_heap: bool,
    #[serde(default)]
    pub object_layout: Option<numeric::ObjectLayout>,
    pub source: PathBuf,
    pub source_digest: files::FileDigest,
    pub assembly: PathBuf,
    pub assembly_digest: files::FileDigest,
    pub dll: Option<PathBuf>,
    pub dll_digest: Option<files::FileDigest>,
}
pub fn compile(
    source: &Path,
    method: &str,
    descriptor: Option<&str>,
    output: &Path,
    assemble: bool,
) -> Result<Compilation> {
    let source = files::absolute(source)?;
    let bytes = fs::read(&source)?;
    let class = ClassFile::parse(&bytes)?;
    let method = class.method(method, descriptor)?;
    let compiled = numeric::compile(&class, method)?;
    fs::create_dir_all(output)?;
    let output = files::absolute(output)?;
    let assembly = output.join("method.asm");
    files::write_atomic(&assembly, compiled.assembly.as_bytes())?;
    let mut result = Compilation {
        schema: 1,
        backend: BACKEND.into(),
        abi: "context16-argv64-rax64-v1".into(),
        class_name: class.name.clone(),
        method: method.name.clone(),
        descriptor: method.descriptor.clone(),
        signature: compiled.signature,
        instructions: compiled.instructions,
        linked_methods: compiled.linked_methods,
        requires_heap: compiled.requires_heap,
        object_layout: compiled.object_layout,
        source: source.clone(),
        source_digest: files::digest(&source)?,
        assembly: assembly.clone(),
        assembly_digest: files::digest(&assembly)?,
        dll: None,
        dll_digest: None,
    };
    if assemble {
        let dll = super::assemble_module_with_heap(&output, &assembly, compiled.requires_heap)?;
        result.dll_digest = Some(files::digest(&dll)?);
        result.dll = Some(dll);
    }
    files::write_atomic(
        &output.join("compilation.json"),
        &serde_json::to_vec_pretty(&result)?,
    )?;
    Ok(result)
}

pub fn compile_class(
    source: &Path,
    methods: &[String],
    output: &Path,
    jobs: usize,
    assemble: bool,
) -> Result<Vec<Compilation>> {
    ensure!(!methods.is_empty(), "Select at least one static method");
    let unique: std::collections::BTreeSet<_> = methods.iter().collect();
    ensure!(
        unique.len() == methods.len(),
        "Duplicate method selections would overwrite outputs"
    );
    let work = crate::parallel::ordered_map(methods, jobs, |_, method| -> Result<Compilation> {
        let path = files::safe_join(output, method)?;
        compile(source, method, None, &path, assemble)
    })?;
    work.results.into_iter().collect()
}

#[repr(C)]
#[derive(Debug, Default, Serialize)]
pub struct ThreadContext {
    pub exception_kind: u32,
    pub bytecode_pc: u32,
    pub method_id: u32,
    pub reserved: u32,
}
#[derive(Debug, Serialize)]
pub struct Outcome {
    pub raw_bits: String,
    pub normalized_bits: String,
    pub exception: Option<&'static str>,
    pub context: ThreadContext,
}
pub fn normalize_bits(ty: Type, bits: u64) -> u64 {
    match ty {
        Type::Array(_)
        | Type::Null
        | Type::AnyRef
        | Type::Object
        | Type::ObjectArray
        | Type::LinkedObject(_)
        | Type::LinkedObjectArray(_)
        | Type::BootstrapString
        | Type::BootstrapStringArray
        | Type::BootstrapClass
        | Type::BootstrapClassArray
        | Type::MetadataReference(_)
        | Type::ReferenceJoin(_) => bits,
        Type::Uninitialized(_)
        | Type::UninitializedString(_)
        | Type::UninitializedThis
        | Type::UninitializedLinked(_, _)
        | Type::UninitializedLinkedThis(_) => {
            unreachable!("Uninitialized values cannot cross the entry ABI")
        }
        Type::Void => 0,
        Type::I32 => bits & 0xffff_ffff,
        Type::I64 => bits,
        Type::F32 => {
            let bits = bits as u32;
            if f32::from_bits(bits).is_nan() {
                0x7fc00000
            } else {
                bits as u64
            }
        }
        Type::F64 => {
            if f64::from_bits(bits).is_nan() {
                0x7ff8000000000000
            } else {
                bits
            }
        }
    }
}
pub fn execute(manifest: &Path, arguments: &[u64]) -> Result<Outcome> {
    let compilation: Compilation = serde_json::from_slice(&fs::read(manifest)?)?;
    ensure!(
        compilation.schema == 1
            && compilation.backend == BACKEND
            && compilation.abi == "context16-argv64-rax64-v1",
        "Unknown numeric manifest or ABI"
    );
    let signature = Signature::parse(&compilation.descriptor)?;
    ensure!(
        signature == compilation.signature && signature.arguments.len() == arguments.len(),
        "Argument/signature mismatch"
    );
    ensure!(
        !compilation.requires_heap && !signature.arguments.iter().any(|ty| ty.is_reference()),
        "Reference modules require an assembly heap host and initialized references; raw-pointer diagnostic invocation is disabled"
    );
    for (ty, bits) in signature.arguments.iter().zip(arguments) {
        if matches!(ty, Type::I32 | Type::F32) {
            ensure!(
                *bits <= u32::MAX as u64,
                "32-bit argument has nonzero upper bits"
            );
        }
    }
    ensure!(
        files::digest(&compilation.assembly)? == compilation.assembly_digest,
        "Assembly changed after compilation"
    );
    let dll = compilation
        .dll
        .context("Numeric method has not been assembled")?;
    let expected = compilation.dll_digest.context("Missing DLL digest")?;
    ensure!(
        files::digest(&dll)? == expected,
        "Numeric DLL changed after compilation"
    );
    let (bits, context) = invoke(&dll, arguments)?;
    let exception = match context.exception_kind {
        0 => None,
        1 => Some("java.lang.ArithmeticException"),
        2 => Some("java.lang.NegativeArraySizeException"),
        3 => Some("java.lang.OutOfMemoryError"),
        4 => Some("java.lang.NullPointerException"),
        5 => Some("java.lang.ArrayIndexOutOfBoundsException"),
        6 => Some("java.lang.ArrayStoreException"),
        7 => Some("java.lang.VerifyError"),
        8 => Some("java.lang.ExceptionInInitializerError"),
        9 => Some("java.lang.NoClassDefFoundError"),
        10 => Some("java.lang.StackOverflowError"),
        11 => Some("java.lang.StringIndexOutOfBoundsException"),
        12 => Some("java.lang.ClassCastException"),
        17 => Some("java.lang.IllegalMonitorStateException"),
        18 => Some("java.lang.IllegalArgumentException"),
        19 => Some("java.lang.ClassNotFoundException"),
        20 => Some("java.lang.UnsatisfiedLinkError"),
        21 => Some("java.io.IOException"),
        22 => Some("java.io.SyncFailedException"),
        _ => anyhow::bail!("Unknown generated-code exception kind"),
    };
    Ok(Outcome {
        raw_bits: format!("{bits:016x}"),
        normalized_bits: format!("{:016x}", normalize_bits(signature.result, bits)),
        exception,
        context,
    })
}

#[cfg(windows)]
fn invoke(path: &Path, arguments: &[u64]) -> Result<(u64, ThreadContext)> {
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
    let wide: Vec<_> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    // Diagnostic host only. The generated DLL executes all numeric operations,
    // conversions, calls, and exception propagation in its assembly procedures.
    unsafe {
        let module = LoadLibraryExW(wide.as_ptr(), std::ptr::null_mut(), 0x1100);
        ensure!(
            !module.is_null(),
            "Cannot load numeric DLL: {}",
            std::io::Error::last_os_error()
        );
        let module = Library(module);
        let symbol = GetProcAddress(module.0, c"boom_entry".as_ptr().cast());
        ensure!(!symbol.is_null(), "Missing numeric entry point");
        let entry = std::mem::transmute::<
            *mut c_void,
            unsafe extern "C" fn(*mut ThreadContext, *const u64) -> u64,
        >(symbol);
        let mut context = ThreadContext::default();
        let bits = entry(&mut context, arguments.as_ptr());
        Ok((bits, context))
    }
}
#[cfg(not(windows))]
fn invoke(_path: &Path, _arguments: &[u64]) -> Result<(u64, ThreadContext)> {
    anyhow::bail!("Numeric execution requires Windows x86-64")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nan_payloads_normalize_but_signed_zero_is_preserved() {
        assert_eq!(normalize_bits(Type::F32, 0xffc12345), 0x7fc00000);
        assert_eq!(
            normalize_bits(Type::F64, 0xfff123456789abcd),
            0x7ff8000000000000
        );
        assert_eq!(normalize_bits(Type::F32, 0x80000000), 0x80000000);
        assert_eq!(
            normalize_bits(Type::F64, 0x8000000000000000),
            0x8000000000000000
        );
    }
    #[test]
    fn context_layout_matches_generated_assembly() {
        assert_eq!(std::mem::size_of::<ThreadContext>(), 16);
        assert_eq!(std::mem::offset_of!(ThreadContext, method_id), 8);
    }
}
