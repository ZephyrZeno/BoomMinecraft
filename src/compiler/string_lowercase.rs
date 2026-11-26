//! Source-bound case conversion over real Locale/BaseLocale field storage.
use super::{classfile::ClassFile, numeric, types, word_break};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::fmt::Write as _;
pub const LOCALE: &str = "java/util/Locale";
pub const BASE: &str = "sun/util/locale/BaseLocale";
pub const DESCRIPTOR: &str = "(Ljava/util/Locale;)Ljava/lang/String;";
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub string_origin: ClassOrigin,
    pub locale_origin: ClassOrigin,
    pub base_origin: ClassOrigin,
    pub locale_type: usize,
    pub base_type: usize,
    pub locale_layout: numeric::ObjectLayout,
    pub base_layout: numeric::ObjectLayout,
    pub base_offset: usize,
    pub language_offset: usize,
    pub words: Option<word_break::Tables>,
    pub native_source_sha256: String,
    pub bindings: Vec<Binding>,
    pub original_java_string_method_executed: bool,
    pub dictionary_sigma_implemented: bool,
    pub dynamic_locale_providers: bool,
    pub automatic_gc: bool,
}
pub(super) fn is_call(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == "java/lang/String" && name == "toLowerCase" && descriptor == DESCRIPTOR
}
fn original(registry: &mut types::Registry<'_>, name: &str) -> Result<(usize, ClassOrigin)> {
    let id = registry.class("bootstrap", name)?;
    let types::Type::Class { origin, key, .. } = &registry.types[id] else {
        unreachable!()
    };
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none(),
        "Case conversion requires original java.base definitions"
    );
    Ok((id, origin.as_ref().clone()))
}
fn field(
    layout: &numeric::ObjectLayout,
    owner: &str,
    name: &str,
    descriptor: &str,
) -> Result<usize> {
    ensure!(
        layout.abi == 2,
        "Locale case fields require compact layout ABI2"
    );
    let field = layout
        .fields
        .iter()
        .find(|f| {
            f.name == name
                && f.descriptor == descriptor
                && f.declaring_class.as_deref() == Some(owner)
        })
        .context("Missing Locale case field")?;
    ensure!(
        field.storage_bytes == Some(8)
            && field.offset % 8 == 0
            && field.offset < layout.reference_prefix_fields * 8
            && field.offset + 8 <= layout.payload_bytes,
        "Locale field is outside reference prefix"
    );
    Ok(field.offset)
}
impl Plan {
    pub(super) fn new(
        registry: &mut types::Registry<'_>,
        locale_layout: numeric::ObjectLayout,
        base_layout: numeric::ObjectLayout,
    ) -> Result<Self> {
        let (locale_type, locale_origin) = original(registry, LOCALE)?;
        let (base_type, base_origin) = original(registry, BASE)?;
        let (string_type, string_origin) = original(registry, "java/lang/String")?;
        let string = registry
            .definition(string_type)
            .context("Missing String case source")?;
        let method = string.method("toLowerCase", Some(DESCRIPTOR))?;
        let code = method
            .code
            .as_ref()
            .context("Missing String case Java Code")?;
        let b = &code.bytes;
        ensure!(
            method.access == 1 && code.handlers.is_empty() && b.len() == 29,
            "String case dispatch changed"
        );
        for (i, byte) in [
            (0, 0x2a),
            (1, 0xb6),
            (4, 0x99),
            (5, 0),
            (6, 15),
            (7, 0x2a),
            (8, 0x2a),
            (9, 0xb4),
            (12, 0x2b),
            (13, 0xb8),
            (16, 0xa7),
            (17, 0),
            (18, 12),
            (19, 0x2a),
            (20, 0x2a),
            (21, 0xb4),
            (24, 0x2b),
            (25, 0xb8),
            (28, 0xb0),
        ] {
            ensure!(b[i] == byte, "String encoding/case dispatch body changed");
        }
        let cp = |i| u16::from_be_bytes([b[i], b[i + 1]]);
        ensure!(
            string.method_reference(cp(2))?
                == ("java/lang/String".into(), "isLatin1".into(), "()Z".into()),
            "String encoding predicate changed"
        );
        for i in [10, 22] {
            ensure!(
                string.field_reference(cp(i))?
                    == ("java/lang/String".into(), "value".into(), "[B".into()),
                "String backing delegation changed"
            );
        }
        for (i, owner) in [
            (14, "java/lang/StringLatin1"),
            (26, "java/lang/StringUTF16"),
        ] {
            ensure!(
                string.static_method_reference(cp(i))?
                    == (
                        owner.into(),
                        "toLowerCase".into(),
                        "(Ljava/lang/String;[BLjava/util/Locale;)Ljava/lang/String;".into(),
                        false
                    ),
                "String lower helper changed"
            );
        }
        let locale = registry
            .definition(locale_type)
            .context("Missing Locale source")?;
        let base = registry
            .definition(base_type)
            .context("Missing BaseLocale source")?;
        for class in [locale, base] {
            ensure!(
                class.access & 0x611 == 0x11,
                "Locale case receiver must be its original concrete final class"
            );
        }
        let getter = locale.method("getLanguage", Some("()Ljava/lang/String;"))?;
        let b = &getter
            .code
            .as_ref()
            .context("Missing Locale language getter")?
            .bytes;
        ensure!(
            getter.access == 1
                && b.len() == 8
                && b[0] == 0x2a
                && b[1] == 0xb4
                && b[4] == 0xb6
                && b[7] == 0xb0,
            "Locale language getter changed"
        );
        let cp = |i| u16::from_be_bytes([b[i], b[i + 1]]);
        ensure!(
            locale.field_reference(cp(2))?
                == (
                    LOCALE.into(),
                    "baseLocale".into(),
                    "Lsun/util/locale/BaseLocale;".into()
                )
                && locale.method_reference(cp(5))?
                    == (
                        BASE.into(),
                        "getLanguage".into(),
                        "()Ljava/lang/String;".into()
                    ),
            "Locale language delegation changed"
        );
        let getter = base.method("getLanguage", Some("()Ljava/lang/String;"))?;
        let b = &getter
            .code
            .as_ref()
            .context("Missing BaseLocale getter")?
            .bytes;
        ensure!(
            getter.access == 1
                && b.len() == 5
                && b[0] == 0x2a
                && b[1] == 0xb4
                && b[4] == 0xb0
                && base.field_reference(u16::from_be_bytes([b[2], b[3]]))?
                    == (BASE.into(), "language".into(), "Ljava/lang/String;".into()),
            "BaseLocale language read changed"
        );
        Ok(Self {
            abi: 1,
            string_origin,
            locale_origin,
            base_origin,
            locale_type,
            base_type,
            base_offset: field(
                &locale_layout,
                LOCALE,
                "baseLocale",
                "Lsun/util/locale/BaseLocale;",
            )?,
            language_offset: field(&base_layout, BASE, "language", "Ljava/lang/String;")?,
            locale_layout,
            base_layout,
            words: None,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/string_lowercase.asm"
            ))
            .sha256,
            bindings: Vec::new(),
            original_java_string_method_executed: false,
            dictionary_sigma_implemented: false,
            dynamic_locale_providers: false,
            automatic_gc: false,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
    ) -> Result<()> {
        let (o, n, d) = caller.method_reference(constant)?;
        ensure!(
            is_call(&o, &n, &d) && source.binary_name == caller.name.replace('/', "."),
            "Invalid case conversion caller"
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
                (&a.caller.loader, &a.caller.binary_name, a.constant).cmp(&(
                    &b.caller.loader,
                    &b.caller.binary_name,
                    b.constant,
                ))
            });
        }
        Ok(())
    }
    pub(super) fn extend_rows(&self, rows: &mut Vec<super::runtime_types::Binding>) {
        for (tag, id, layout) in [
            (
                "boom_lower_locale_layout",
                self.locale_type,
                &self.locale_layout,
            ),
            ("boom_lower_base_layout", self.base_type, &self.base_layout),
        ] {
            rows.push(super::runtime_types::Binding {
                tag: format!("OFFSET {tag}"),
                type_id: id,
                kind: 0,
                payload_bytes: layout.payload_bytes,
                references: layout.reference_prefix_fields,
                element_shift: 0,
            });
        }
    }
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        self.words
            .as_ref()
            .context("Unprepared case word boundaries")?
            .emit(out)?;
        out.push_str("EXTERN boom_string_lowercase:PROC\n.const\n");
        for (name, layout) in [
            ("boom_lower_locale_layout", &self.locale_layout),
            ("boom_lower_base_layout", &self.base_layout),
        ] {
            writeln!(
                out,
                "ALIGN 8\n{name} DWORD 04F424A43h,{}\n    QWORD {}\n    DWORD {},{}",
                layout.abi,
                layout.payload_bytes,
                layout.reference_prefix_fields,
                layout.fields.len()
            )?;
        }
        writeln!(
            out,
            "ALIGN 8\nboom_lowercase_pool DWORD 05341434Ch,1\n    QWORD OFFSET boom_string_pool,OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_t{},OFFSET boom_t{},OFFSET boom_word_plan\n    DWORD {},{}\n    QWORD {},{}\n    DWORD {},{},0,0\n.code\nPUBLIC boom_get_lowercase_pool\nboom_get_lowercase_pool PROC\n    lea rax,boom_lowercase_pool\n    ret\nboom_get_lowercase_pool ENDP",
            self.locale_type,
            self.base_type,
            self.base_offset,
            self.language_offset,
            self.locale_layout.payload_bytes,
            self.base_layout.payload_bytes,
            self.locale_layout.reference_prefix_fields,
            self.base_layout.reference_prefix_fields
        )?;
        Ok(())
    }
}
