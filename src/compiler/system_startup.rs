//! Explicit VM invocation of the original System phase-one Java body.
//! This capability never marks a phase complete or enables an application entry.
use super::{
    classfile::{ClassFile, Method},
    types,
};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub entry_method: String,
    pub entry_descriptor: String,
    pub code_sha256: String,
    pub expected_completion_level: u32,
    pub invocation_only: bool,
    pub application_entry: bool,
}
impl Plan {
    pub(super) fn prepare(
        registry: Option<&mut types::Registry<'_>>,
        owner: &str,
        name: &str,
        descriptor: Option<&str>,
    ) -> Result<Option<Self>> {
        if owner != "java/lang/System" || name != "initPhase1" {
            return Ok(None);
        }
        ensure!(
            descriptor.is_none() || descriptor == Some("()V"),
            "System phase-one VM invocation requires ()V"
        );
        let registry =
            registry.context("System phase-one invocation requires verified java.base")?;
        let id = registry.class("bootstrap", owner)?;
        let types::Type::Class { key, origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "System phase-one invocation requires its original bootstrap definition"
        );
        let origin = origin.as_ref().clone();
        let class = registry
            .definition(id)
            .context("Missing original System definition")?;
        let method = class.method("initPhase1", Some("()V"))?;
        ensure!(
            class.access & 0x611 == 0x11 && method.access == 0xa,
            "System phase-one VM invocation access changed"
        );
        let code = method
            .code
            .as_ref()
            .context("System phase one must execute original Java Code")?;
        Ok(Some(Self {
            abi: 1,
            origin,
            entry_method: name.into(),
            entry_descriptor: "()V".into(),
            code_sha256: files::digest_bytes(&code.bytes).sha256,
            expected_completion_level: 1,
            invocation_only: true,
            application_entry: false,
        }))
    }
}
pub(super) fn java_method_allowed(
    class: &ClassFile,
    method: &Method,
    phase_one_invocation: bool,
) -> bool {
    class.name != "java/lang/System"
        || matches!(
            method.name.as_str(),
            "<clinit>" | "getSecurityManager" | "allowSecurityManager"
        )
        || (phase_one_invocation && !matches!(method.name.as_str(), "initPhase2" | "initPhase3"))
}
