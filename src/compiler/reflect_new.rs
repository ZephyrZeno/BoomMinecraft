//! Frozen-image Class.newInstance dispatch; all allocation/invocation stays ASM.
use super::{constructor_entries, nests, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fmt::Write as _};
pub const DESCRIPTOR: &str = "()Ljava/lang/Object;";
pub(super) fn is_call(o: &str, n: &str, d: &str) -> bool {
    o == "java/lang/Class" && n == "newInstance" && d == DESCRIPTOR
}
pub(super) fn signature() -> numeric::Signature {
    numeric::Signature {
        arguments: vec![numeric::Type::BootstrapClass],
        result: numeric::Type::AnyRef,
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub access_caller: ClassOrigin,
    pub constant: u16,
    pub caller_type: usize,
    pub site: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Row {
    pub type_id: usize,
    pub action: u32,
    pub name_literal: usize,
    pub no_such_message: usize,
    pub constructor_helper: Option<usize>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Site {
    pub binding: Binding,
    pub rows: Vec<Row>,
    pub nest_proofs: Vec<nests::Proof>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub class_origin: ClassOrigin,
    pub module_descriptor_sha256: String,
    pub module_snapshot_fingerprint: String,
    pub original_code_sha256: String,
    pub original_java_class_method_executed: bool,
    pub native_source_sha256: String,
    pub class_type: usize,
    pub message_offset: usize,
    pub constructors: Vec<constructor_entries::Plan>,
    pub sites: Vec<Site>,
    pub reflective_stack_frames_complete: bool,
    pub security_manager_supported: bool,
    pub dynamic_class_loading_complete: bool,
    pub automatic_gc: bool,
}
pub(super) fn verify(registry: &mut types::Registry<'_>) -> Result<(usize, ClassOrigin, String)> {
    let id = registry.class("bootstrap", "java/lang/Class")?;
    let types::Type::Class { origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    ensure!(
        origin.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "Reflection requires original bootstrap Class"
    );
    let origin = origin.as_ref().clone();
    let m = registry
        .definition(id)
        .context("Missing reflection source")?
        .method("newInstance", Some(DESCRIPTOR))?;
    ensure!(
        m.access == 1
            && m.runtime_visible_annotations
                .iter()
                .any(|s| s == "Ljdk/internal/reflect/CallerSensitive;"),
        "Class.newInstance access/caller contract changed"
    );
    let code = m
        .code
        .as_ref()
        .context("Missing original Class.newInstance Code")?;
    Ok((id, origin, files::digest_bytes(&code.bytes).sha256))
}
fn package(name: &str) -> &str {
    name.rsplit_once('/').map_or("", |v| v.0)
}
/// Constructor reflection checks use targetClass == declaringClass. Therefore a
/// protected constructor in another runtime package is not accessible to a subclass.
pub(super) fn accessible(
    registry: &mut types::Registry<'_>,
    caller: usize,
    target: usize,
    ctor: u16,
    module_access: bool,
) -> Result<(bool, Option<nests::Proof>)> {
    if caller == target {
        return Ok((true, None));
    }
    if !module_access {
        return Ok((false, None));
    }
    let types::Type::Class { key: c, .. } = &registry.types[caller] else {
        unreachable!()
    };
    let types::Type::Class { key: t, access, .. } = &registry.types[target] else {
        unreachable!()
    };
    let same = c.loader == t.loader && package(&c.name) == package(&t.name);
    if access & 1 == 0 && !same {
        return Ok((false, None));
    }
    if ctor & 1 != 0 {
        return Ok((true, None));
    }
    if ctor & 2 != 0 {
        let c = c.clone();
        let t = t.clone();
        let proof = nests::prove(registry, &c.loader, &c.name, &t.loader, &t.name)?;
        return Ok((proof.is_some(), proof));
    }
    Ok((same, None))
}
impl Plan {
    #[allow(clippy::too_many_arguments)]
    pub(super) fn prepare(
        registry: &mut types::Registry<'_>,
        module_identity: (&str, &str),
        bindings: Vec<Binding>,
        constructors: Vec<constructor_entries::Plan>,
        message_offset: usize,
        mut intern: impl FnMut(Vec<u16>) -> Result<usize>,
        exported: &impl Fn(&ClassOrigin, &ClassOrigin, &str) -> Result<bool>,
    ) -> Result<Self> {
        let (class_type, class_origin, original_code_sha256) = verify(registry)?;
        let mut helpers = BTreeMap::new();
        for c in &constructors {
            ensure!(
                c.signature.arguments.is_empty(),
                "Reflective constructor must have no arguments"
            );
            let source = c
                .source
                .as_ref()
                .context("Unproven reflected constructor")?;
            let id = registry.class(&source.loader, &source.binary_name.replace('.', "/"))?;
            helpers.insert(id, c.helper_id);
        }
        // Resolve reciprocal nest hosts before freezing the per-site row width.
        let mut candidate = 0;
        while candidate < registry.types.len() {
            if registry.definition(candidate).is_some_and(|c| {
                c.methods
                    .iter()
                    .any(|m| m.name == "<init>" && m.descriptor == "()V" && m.access & 2 != 0)
            }) {
                for binding in &bindings {
                    accessible(registry, binding.caller_type, candidate, 2, true)?;
                }
            }
            candidate += 1;
        }
        let type_count = registry.types.len();
        let mut sites = Vec::new();
        for binding in bindings {
            let mut rows = Vec::new();
            let mut nest_proofs = Vec::new();
            let mut id = 0;
            while id < registry.types.len() {
                let name = super::mirrors::name(&registry.types, id);
                let name_literal = intern(name.encode_utf16().collect())?;
                let no_such_message = intern(format!("{name}.<init>()").encode_utf16().collect())?;
                let mut row = Row {
                    type_id: id,
                    action: 1,
                    name_literal,
                    no_such_message,
                    constructor_helper: None,
                };
                if let types::Type::Class {
                    origin,
                    key,
                    access,
                    ..
                } = &registry.types[id]
                {
                    let origin = origin.as_ref().clone();
                    let key = key.clone();
                    let access = *access;
                    if id == class_type {
                        row.action = 2;
                    } else {
                        let ctor = registry
                            .definition(id)
                            .context("Missing reflected class definition")?
                            .methods
                            .iter()
                            .find(|m| m.name == "<init>" && m.descriptor == "()V")
                            .map(|m| m.access);
                        if let Some(ctor) = ctor {
                            let module_access =
                                exported(&binding.access_caller, &origin, package(&key.name))?;
                            let (yes, proof) =
                                accessible(registry, binding.caller_type, id, ctor, module_access)?;
                            if let Some(p) = proof {
                                nest_proofs.push(p);
                            }
                            row.action = if !yes {
                                2
                            } else if access & 0x400 != 0 {
                                3
                            } else {
                                4
                            };
                            if row.action == 4
                                && let Some(&helper) = helpers.get(&id)
                            {
                                row.action = 0;
                                row.constructor_helper = Some(helper);
                            }
                        }
                    }
                }
                rows.push(row);
                id += 1;
            }
            sites.push(Site {
                binding,
                rows,
                nest_proofs,
            });
        }
        ensure!(
            registry.types.len() == type_count,
            "Reflection type identities changed after nest preloading"
        );
        Ok(Self {
            abi: 1,
            class_origin,
            original_code_sha256,
            module_descriptor_sha256: module_identity.0.into(),
            module_snapshot_fingerprint: module_identity.1.into(),
            original_java_class_method_executed: false,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/reflect_new.asm"
            ))
            .sha256,
            class_type,
            message_offset,
            constructors,
            sites,
            reflective_stack_frames_complete: false,
            security_manager_supported: false,
            dynamic_class_loading_complete: false,
            automatic_gc: false,
        })
    }
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        out.push_str("EXTERN boom_reflect_new:PROC\n");
        for ctor in &self.constructors {
            ctor.emit(out, true);
        }
        for site in &self.sites {
            let id = site.binding.site;
            writeln!(out, ".const\nALIGN 8\nboom_reflect_rows{id} LABEL BYTE")?;
            for row in &site.rows {
                let target = row
                    .constructor_helper
                    .map_or("0".into(), |m| format!("OFFSET boom_m{m}"));
                writeln!(
                    out,
                    "    DWORD {},{}\n    QWORD {target}\n    DWORD {},0",
                    row.action, row.name_literal, row.no_such_message
                )?;
            }
            writeln!(
                out,
                "ALIGN 8\nboom_reflect_pool{id} DWORD 057454E52h,1\n    QWORD OFFSET boom_mirror_pool,OFFSET boom_heap_ptr,OFFSET boom_reflect_rows{id}\n    DWORD {},{}, {},0\n    QWORD OFFSET boom_runtime_type_map,OFFSET boom_t{},0,0\n.code",
                site.rows.len(),
                site.binding.caller_type,
                self.message_offset,
                self.class_type
            )?;
        }
        if !self.sites.is_empty() {
            out.push_str("PUBLIC boom_get_reflect_pool\nboom_get_reflect_pool PROC\n    lea rax,boom_reflect_pool0\n    ret\nboom_get_reflect_pool ENDP\n");
        }
        Ok(())
    }
}
