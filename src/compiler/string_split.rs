//! Original public split wrappers with a source-bound assembly literal fast path.
use super::{classfile::ClassFile, jdk_bridges, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::fmt::Write as _;
pub const DESCRIPTOR: &str = "(Ljava/lang/String;IZ)[Ljava/lang/String;";
pub(super) fn is_call(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == "java/lang/String" && name == "split" && descriptor == DESCRIPTOR
}
pub(super) fn signature() -> numeric::Signature {
    numeric::Signature {
        arguments: vec![
            numeric::Type::BootstrapString,
            numeric::Type::BootstrapString,
            numeric::Type::I32,
            numeric::Type::I32,
        ],
        result: numeric::Type::BootstrapStringArray,
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub string_origin: ClassOrigin,
    pub dispatch_code_sha256: String,
    pub char_helper_code_sha256: String,
    pub native_source_sha256: String,
    pub empty_literal: usize,
    pub bindings: Vec<Binding>,
    pub original_public_wrapper_code_retained: bool,
    pub original_private_java_methods_executed: bool,
    pub literal_delimiter_fast_path: bool,
    pub regex_engine_complete: bool,
    pub automatic_gc: bool,
}
impl Plan {
    pub(super) fn new(registry: &mut types::Registry<'_>, empty_literal: usize) -> Result<Self> {
        let id = registry.class("bootstrap", "java/lang/String")?;
        let types::Type::Class { origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            origin.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "Split requires original java.base String"
        );
        let string_origin = origin.as_ref().clone();
        let string = registry
            .definition(id)
            .context("Missing String split source")?;
        let dispatch = string.method("split", Some(DESCRIPTOR))?;
        let helper = string.method("split", Some("(CIZ)[Ljava/lang/String;"))?;
        let dispatch = dispatch
            .code
            .as_ref()
            .filter(|c| dispatch.access == 2 && c.bytes.len() == 148 && c.handlers.is_empty())
            .context("String split dispatch changed")?;
        let helper = helper
            .code
            .as_ref()
            .filter(|c| helper.access == 2 && c.bytes.len() == 242 && c.handlers.is_empty())
            .context("String split char helper changed")?;
        let b = &dispatch.bytes;
        ensure!(
            b[0..4] == [3, 0x36, 4, 0x2b]
                && b[11] == 0x13
                && b[116] == 0xb6
                && b[121] == 0xb8
                && b[147] == 0xb0,
            "String split fast-path shape changed"
        );
        let cp = |i| u16::from_be_bytes([b[i], b[i + 1]]);
        ensure!(
            string.method_reference(cp(117))?
                == (
                    "java/lang/String".into(),
                    "split".into(),
                    "(CIZ)[Ljava/lang/String;".into()
                ),
            "String literal split target changed"
        );
        ensure!(
            string.static_method_reference(cp(122))?
                == (
                    "java/util/regex/Pattern".into(),
                    "compile".into(),
                    "(Ljava/lang/String;)Ljava/util/regex/Pattern;".into(),
                    false
                ),
            "String regex fallback changed"
        );
        Ok(Self {
            abi: 1,
            string_origin,
            dispatch_code_sha256: files::digest_bytes(&dispatch.bytes).sha256,
            char_helper_code_sha256: files::digest_bytes(&helper.bytes).sha256,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/string_split.asm"
            ))
            .sha256,
            empty_literal,
            bindings: Vec::new(),
            original_public_wrapper_code_retained: true,
            original_private_java_methods_executed: false,
            literal_delimiter_fast_path: true,
            regex_engine_complete: false,
            automatic_gc: false,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
    ) -> Result<()> {
        jdk_bridges::validate(caller, source)?;
        let g = source
            .generated
            .as_ref()
            .context("Missing split bridge proof")?;
        let (o, n, d) = caller.method_reference(constant)?;
        ensure!(
            is_call(&o, &n, &d)
                && matches!(g.site, 17..=19)
                && g.host_sha256 == self.string_origin.sha256
                && source.binary_name == caller.name.replace('/', "."),
            "Private String split is restricted to retained original public wrappers"
        );
        if !self
            .bindings
            .iter()
            .any(|b| b.caller == *source && b.constant == constant)
        {
            self.bindings.push(Binding {
                caller: source.clone(),
                constant,
            });
            self.bindings.sort_by(|a, b| {
                (&a.caller.binary_name, a.constant).cmp(&(&b.caller.binary_name, b.constant))
            });
        }
        Ok(())
    }
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        writeln!(
            out,
            "EXTERN boom_string_split:PROC\n.const\nALIGN 8\nboom_split_pool DWORD 0544C5053h,1\n    QWORD OFFSET boom_string_pool,OFFSET boom_heap_ptr,OFFSET boom_string_array_layout\n    DWORD {},0\n    QWORD 0\n.code\nPUBLIC boom_get_split_pool\nboom_get_split_pool PROC\n    lea rax,boom_split_pool\n    ret\nboom_get_split_pool ENDP",
            self.empty_literal
        )?;
        Ok(())
    }
}
