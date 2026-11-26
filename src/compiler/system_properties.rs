//! Original SystemProps.Raw platform contract and assembly Windows snapshot.
use super::{
    classfile::{ClassFile, NumericConstant},
    numeric, types,
};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "jdk/internal/util/SystemProps$Raw";
pub const DESCRIPTOR: &str = "()[Ljava/lang/String;";
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum Operation {
    Platform,
    Vm,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, descriptor: &str) -> Option<Self> {
        if owner != OWNER || descriptor != DESCRIPTOR {
            return None;
        }
        match name {
            "platformProperties" => Some(Self::Platform),
            "vmProperties" => Some(Self::Vm),
            _ => None,
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub constant: u16,
    pub caller: ClassOrigin,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Row {
    pub name: String,
    pub index: usize,
    pub query: u32,
    pub argument: u32,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub class_id: usize,
    pub origin: ClassOrigin,
    pub rows: Vec<Row>,
    pub fallbacks: Vec<usize>,
    pub bindings: Vec<Binding>,
    pub native_source_sha256: String,
}
pub const FALLBACKS: &[&str] = &[
    "",
    "unknown",
    "C:\\",
    "en",
    "US",
    "no",
    "NO",
    "NY",
    "UTF-8",
    "GBK",
    "GB18030",
    "MS950_HKSCS_XP",
    "Windows NT (unknown)",
    "Windows 8",
    "Windows 8.1",
    "Windows 10",
    "Windows 11",
    "Windows Server 2012",
    "Windows Server 2012 R2",
    "Windows Server 2016",
    "Windows Server 2019",
    "Windows Server 2022",
    "Windows Server 2025",
];
// query: 0=null,1=literal,2=cwd,3=temp,4=username,5=home,6=os name,
// 7=os version,8=locale(country/lang/script/variant),9=ACP,10=stdout/stderr,11=OS patch,12=ISA.
pub(super) fn query(name: &str) -> Result<(u32, u32, Option<&'static str>)> {
    Ok(match name {
        "_file_separator_NDX" => (1, 0, Some("\\")),
        "_line_separator_NDX" => (1, 0, Some("\r\n")),
        "_path_separator_NDX" => (1, 0, Some(";")),
        "_os_arch_NDX" => (1, 0, Some("amd64")),
        "_sun_cpu_endian_NDX" => (1, 0, Some("little")),
        "_sun_cpu_isalist_NDX" => (12, 0, Some("amd64")),
        "_sun_io_unicode_encoding_NDX" => (1, 0, Some("UnicodeLittle")),
        "_sun_arch_data_model_NDX" => (1, 0, Some("64")),
        "_java_io_tmpdir_NDX" => (3, 0, None),
        "_user_dir_NDX" => (2, 0, None),
        "_user_name_NDX" => (4, 0, None),
        "_user_home_NDX" => (5, 0, None),
        "_os_name_NDX" => (6, 0, None),
        "_os_version_NDX" => (7, 0, None),
        "_sun_os_patch_level_NDX" => (11, 0, None),
        "_file_encoding_NDX" | "_sun_jnu_encoding_NDX" => (9, 0, None),
        "_stdout_encoding_NDX" => (10, 0, None),
        "_stderr_encoding_NDX" => (10, 1, None),
        "_display_country_NDX" => (8, 0, None),
        "_display_language_NDX" => (8, 1, None),
        "_display_script_NDX" => (8, 2, None),
        "_display_variant_NDX" => (8, 3, None),
        "_format_country_NDX" => (8, 4, None),
        "_format_language_NDX" => (8, 5, None),
        "_format_script_NDX" => (8, 6, None),
        "_format_variant_NDX" => (8, 7, None),
        "_ftp_nonProxyHosts_NDX"
        | "_ftp_proxyHost_NDX"
        | "_ftp_proxyPort_NDX"
        | "_http_nonProxyHosts_NDX"
        | "_http_proxyHost_NDX"
        | "_http_proxyPort_NDX"
        | "_https_proxyHost_NDX"
        | "_https_proxyPort_NDX"
        | "_socksNonProxyHosts_NDX"
        | "_socksProxyHost_NDX"
        | "_socksProxyPort_NDX"
        | "_sun_arch_abi_NDX" => (0, 0, None),
        _ => anyhow::bail!("Unknown SystemProps.Raw native field {name}"),
    })
}

impl Plan {
    pub(super) fn prepare(
        registry: &mut types::Registry<'_>,
        class_id: usize,
        mut literal: impl FnMut(&str) -> Result<usize>,
    ) -> Result<Self> {
        let id = registry.class("bootstrap", OWNER)?;
        let types::Type::Class { key, origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "SystemProps native needs its original bootstrap class"
        );
        let origin = origin.as_ref().clone();
        let class = registry
            .definition(id)
            .context("Missing original Raw definition")?;
        let member = class.method("platformProperties", Some(DESCRIPTOR))?;
        ensure!(
            member.access == 0x10a && member.code.is_none(),
            "Raw.platformProperties native contract changed"
        );
        let mut rows = Vec::new();
        let mut fixed = None;
        for field in &class.field_info {
            if field.name == "FIXED_LENGTH" || field.name.ends_with("_NDX") {
                ensure!(
                    field.access == 0x1a && field.descriptor == "I",
                    "Raw native constant contract changed"
                );
                let NumericConstant::Int(index) = class.numeric(
                    field
                        .constant_value
                        .context("Raw index lacks ConstantValue")?,
                )?
                else {
                    anyhow::bail!("Non-integer Raw native index")
                };
                let index = usize::try_from(index).context("Negative Raw native index")?;
                if field.name == "FIXED_LENGTH" {
                    fixed = Some(index);
                    continue;
                }
                let (kind, arg, value) = query(&field.name)?;
                rows.push(Row {
                    name: field.name.clone(),
                    index,
                    query: kind,
                    argument: if let Some(value) = value {
                        u32::try_from(literal(value)?)?
                    } else {
                        arg
                    },
                });
            }
        }
        rows.sort_by_key(|r| r.index);
        ensure!(
            fixed == Some(39)
                && rows.len() == 39
                && rows.iter().enumerate().all(|(i, r)| i == r.index),
            "Raw native indexed schema changed"
        );
        let fallbacks = FALLBACKS
            .iter()
            .map(|s| literal(s))
            .collect::<Result<Vec<_>>>()?;
        Ok(Self {
            abi: 1,
            class_id,
            origin,
            rows,
            fallbacks,
            bindings: Vec::new(),
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/system_properties.asm"
            ))
            .sha256,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        origin: &ClassOrigin,
        constant: u16,
    ) -> Result<()> {
        let (owner, name, descriptor, interface) = caller.static_method_reference(constant)?;
        ensure!(
            !interface
                && matches!(
                    Operation::resolve(&owner, &name, &descriptor),
                    Some(Operation::Platform)
                )
                && caller.name == OWNER
                && origin == &self.origin,
            "Raw private native requires its original declaring caller"
        );
        if !self.bindings.iter().any(|b| b.constant == constant) {
            self.bindings.push(Binding {
                constant,
                caller: origin.clone(),
            });
            self.bindings.sort_by_key(|b| b.constant);
        }
        Ok(())
    }
    pub(super) fn signature() -> numeric::Signature {
        numeric::Signature {
            arguments: Vec::new(),
            result: numeric::Type::BootstrapStringArray,
        }
    }
    pub(super) fn emit(&self, out: &mut String) {
        out.push_str("EXTERN boom_platform_properties:PROC\n.const\nALIGN 8\nboom_property_rows LABEL DWORD\n");
        for r in &self.rows {
            out.push_str(&format!(
                "    DWORD {}, {}, {}, 0\n",
                r.index, r.query, r.argument
            ));
        }
        out.push_str("boom_property_fallbacks LABEL DWORD\n");
        for id in &self.fallbacks {
            out.push_str(&format!("    DWORD {id}\n"));
        }
        out.push_str(&format!(".data\nALIGN 8\nboom_property_pool DWORD 050524F50h, 1, 0, 0\n    QWORD OFFSET boom_heap_ptr, OFFSET boom_string_pool, OFFSET boom_string_array_layout, OFFSET boom_property_root\n    QWORD OFFSET boom_property_rows\n    DWORD {}, 0\n    QWORD OFFSET boom_property_fallbacks\n    QWORD 0\n.code\nPUBLIC boom_get_property_pool\nboom_get_property_pool PROC\n    lea rax, boom_property_pool\n    ret\nboom_get_property_pool ENDP\n",self.rows.len()));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn windows_raw_schema_keeps_null_optional_slots_and_actual_architecture_contracts() {
        assert_eq!(
            query("_sun_arch_data_model_NDX").unwrap(),
            (1, 0, Some("64"))
        );
        assert_eq!(
            query("_sun_cpu_isalist_NDX").unwrap(),
            (12, 0, Some("amd64"))
        );
        for name in [
            "_http_proxyHost_NDX",
            "_ftp_proxyPort_NDX",
            "_sun_arch_abi_NDX",
        ] {
            assert_eq!(query(name).unwrap(), (0, 0, None));
        }
        assert!(query("_unrecognized_future_property_NDX").is_err());
    }
}
