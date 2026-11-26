//! Source-verified Windows signal-name lookup. Handler delivery remains gated.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::path::Path;
pub const OWNER: &str = "jdk/internal/misc/Signal";
pub const DESCRIPTOR: &str = "(Ljava/lang/String;)I";
const LABELS: [(&str, i32); 7] = [
    ("ABRT", 22),
    ("FPE", 8),
    ("SEGV", 11),
    ("INT", 2),
    ("TERM", 15),
    ("BREAK", 21),
    ("ILL", 4),
];
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Contract {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub native_access: u16,
    pub native_descriptor: String,
    pub class_initializer_code_sha256: String,
    pub platform: String,
    pub labels: Vec<(String, i32)>,
    pub storage_abi: u32,
    pub native_source_sha256: String,
    pub string_source_sha256: String,
    pub heap_source_sha256: String,
    pub unknown_result: i32,
    pub automatic_gc: bool,
    pub handler_registration_implemented: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub class_id: usize,
    pub requires_owner_initialized: bool,
    pub contract: Contract,
}
pub(super) fn is_lookup(o: &str, n: &str, d: &str) -> bool {
    o == OWNER && n == "findSignal0" && d == DESCRIPTOR
}
pub(super) fn signature() -> numeric::Signature {
    numeric::Signature {
        arguments: vec![numeric::Type::BootstrapString],
        result: numeric::Type::I32,
    }
}
pub(super) fn contract(registry: &mut types::Registry<'_>) -> Result<Contract> {
    ensure!(
        cfg!(target_os = "windows") && cfg!(target_arch = "x86_64"),
        "Signal lookup currently requires Windows x86-64"
    );
    let id = registry.class("bootstrap", OWNER)?;
    let types::Type::Class {
        key,
        origin,
        access,
        ..
    } = &registry.types[id]
    else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none()
            && access & 0x611 == 0x11,
        "Signal lookup requires its original final bootstrap definition"
    );
    let origin = origin.as_ref().clone();
    let class = registry.definition(id).context("Missing Signal source")?;
    for (name, desc) in [
        ("findSignal0", DESCRIPTOR),
        ("handle0", "(IJ)J"),
        ("raise0", "(I)V"),
    ] {
        let m = class.method(name, Some(desc))?;
        ensure!(
            m.access == 0x10a && m.code.is_none(),
            "Original private static native Signal declaration changed"
        );
    }
    let init = class
        .method("<clinit>", Some("()V"))?
        .code
        .as_ref()
        .context("Signal must retain original class initialization")?;
    Ok(Contract {
        abi: 1,
        origin,
        native_access: 0x10a,
        native_descriptor: DESCRIPTOR.into(),
        class_initializer_code_sha256: files::digest_bytes(&init.bytes).sha256,
        platform: "windows-x64".into(),
        labels: LABELS.into_iter().map(|(n, v)| (n.into(), v)).collect(),
        storage_abi: 3,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/signals.asm"
        ))
        .sha256,
        string_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/strings.asm"
        ))
        .sha256,
        heap_source_sha256: files::digest_bytes(include_bytes!("../../native/runtime/heap.asm"))
            .sha256,
        unknown_result: -1,
        automatic_gc: false,
        handler_registration_implemented: false,
    })
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    class_id: usize,
) -> Result<Binding> {
    let contract = contract(registry)?;
    verify_caller(caller, source, constant, &contract)?;
    Ok(Binding {
        caller: source.clone(),
        constant,
        class_id,
        requires_owner_initialized: true,
        contract,
    })
}
fn verify_caller(
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    contract: &Contract,
) -> Result<()> {
    let (o, n, d, interface) = caller.static_method_reference(constant)?;
    ensure!(
        !interface && is_lookup(&o, &n, &d) && caller.name == OWNER && source == &contract.origin,
        "Signal.findSignal0 is private to the original Signal caller"
    );
    Ok(())
}
#[derive(Debug, Serialize)]
pub struct Inspection {
    pub input_fingerprint: String,
    pub contract: Contract,
    pub original_class: std::path::PathBuf,
    pub constructor_lookup_pc: u32,
    pub constructor_lookup_constant: u16,
    pub original_private_callsite_verified: bool,
    pub control_callsite_bindings: Vec<super::signal_natives::Binding>,
    pub control_binding_class_id_is_inspection_placeholder: bool,
    pub inspection_only: bool,
    pub signal_class_initialization_executed: bool,
    pub handlers_installed: bool,
    pub full_game_ready: bool,
}
pub fn inspect(
    inputs: &crate::lock::InputLock,
    manifest: &Path,
    output: &Path,
) -> Result<Inspection> {
    use types::TypeProvider;
    let provider = types::VanillaTypes::new(inputs, manifest)?;
    let (bytes, origin) = provider.resolve("bootstrap", OWNER)?;
    let mut registry = types::Registry::new(&provider);
    let contract = contract(&mut registry)?;
    ensure!(
        origin == contract.origin && files::digest_bytes(&bytes).sha256 == origin.sha256,
        "Signal inspection source changed"
    );
    let class = ClassFile::parse(&bytes)?;
    let ctor = class.method("<init>", Some("(Ljava/lang/String;)V"))?;
    let code = ctor
        .code
        .as_ref()
        .context("Missing original Signal constructor Code")?;
    ensure!(
        ctor.access == 1 && code.bytes.len() == 95 && code.bytes[54] == 0xb8,
        "Signal constructor native callsite changed"
    );
    let constant = u16::from_be_bytes([code.bytes[55], code.bytes[56]]);
    verify_caller(&class, &origin, constant, &contract)?;
    let mut control_callsite_bindings = Vec::new();
    for (name, desc, pc, op) in [
        (
            "handle",
            "(Ljdk/internal/misc/Signal;Ljdk/internal/misc/Signal$Handler;)Ljdk/internal/misc/Signal$Handler;",
            40,
            super::signal_natives::Operation::Handle,
        ),
        (
            "raise",
            "(Ljdk/internal/misc/Signal;)V",
            48,
            super::signal_natives::Operation::Raise,
        ),
    ] {
        let body = class
            .method(name, Some(desc))?
            .code
            .as_ref()
            .context("Missing original Signal control Code")?;
        ensure!(
            body.bytes[pc] == 0xb8,
            "Signal native control callsite moved"
        );
        let constant = u16::from_be_bytes([body.bytes[pc + 1], body.bytes[pc + 2]]);
        control_callsite_bindings.push(super::signal_natives::binding(
            &mut registry,
            &class,
            &origin,
            constant,
            op,
            0,
        )?);
    }
    let output = std::path::absolute(output)?;
    let original_class = output.join("Signal.class");
    files::write_atomic(&original_class, &bytes)?;
    let inspection = Inspection {
        input_fingerprint: inputs.fingerprint.clone(),
        contract,
        original_class,
        constructor_lookup_pc: 54,
        constructor_lookup_constant: constant,
        original_private_callsite_verified: true,
        control_callsite_bindings,
        control_binding_class_id_is_inspection_placeholder: true,
        inspection_only: true,
        signal_class_initialization_executed: false,
        handlers_installed: false,
        full_game_ready: false,
    };
    files::write_atomic(
        &output.join("inspection.json"),
        &serde_json::to_vec_pretty(&inspection)?,
    )?;
    Ok(inspection)
}
