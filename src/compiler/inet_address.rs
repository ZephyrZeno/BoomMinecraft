//! Offline JNI field-ID preparation for InetAddress.init; runtime publication is ASM.
//! Original init caches two bootstrap classes and five fields, not network sockets.
use super::{hierarchy, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::fmt::Write as _;
pub const OWNER: &str = "java/net/InetAddress";
pub const HOLDER: &str = "java/net/InetAddress$InetAddressHolder";
pub const IPV4: &str = "java/net/Inet4Address";
pub const IPV6: &str = "java/net/Inet6Address";
pub const IPV6_HOLDER: &str = "java/net/Inet6Address$Inet6AddressHolder";
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Constructor {
    pub index: usize,
    pub access: u16,
    pub code_sha256: String,
    pub invoked_by_cache_initialization: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Layout {
    pub payload_bytes: usize,
    pub reference_prefix: usize,
    pub fields: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Field {
    pub owner: usize,
    pub index: usize,
    pub name: String,
    pub descriptor: String,
    pub offset: usize,
    pub width: usize,
    pub reference: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub class_id: usize,
    pub cache_family: u32,
    pub type_ids: Vec<usize>,
    pub origins: Vec<ClassOrigin>,
    pub layouts: Vec<Layout>,
    pub fields: Vec<Field>,
    pub prefer_ipv4_stack_field: Option<usize>,
    pub constructor: Option<Constructor>,
    pub native_source_sha256: String,
    pub bootstrap_class_metadata_pinned: bool,
    pub runtime_jni_lookup_used: bool,
    pub network_backend_complete: bool,
}
impl Plan {
    pub(super) fn prepare(registry: &mut types::Registry<'_>, class_id: usize) -> Result<Self> {
        Self::prepare_for(registry, class_id, OWNER)
    }
    pub(super) fn prepare_for(
        registry: &mut types::Registry<'_>,
        class_id: usize,
        owner: &str,
    ) -> Result<Self> {
        let (cache_family, names) = match owner {
            OWNER => (0, [OWNER, HOLDER]),
            IPV4 => (4, [IPV4, IPV4]),
            IPV6 => (6, [IPV6, IPV6_HOLDER]),
            _ => anyhow::bail!("Unsupported InetAddress native cache owner"),
        };
        let mut type_ids = Vec::new();
        let mut origins = Vec::new();
        let mut layouts = Vec::new();
        let mut physical = Vec::new();
        for (position, name) in names.into_iter().enumerate() {
            let id = registry.class("bootstrap", name)?;
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
                    && access & 0x600 == 0,
                "InetAddress metadata requires original concrete bootstrap classes"
            );
            origins.push(origin.as_ref().clone());
            type_ids.push(id);
            let class = registry
                .definition(id)
                .context("Missing InetAddress metadata")?;
            if position == 0 {
                let mut natives = vec![("init", "()V")];
                if cache_family == 0 {
                    natives.extend([("isIPv4Available", "()Z"), ("isIPv6Supported", "()Z")]);
                }
                for (name, desc) in natives {
                    let m = class.method(name, Some(desc))?;
                    ensure!(
                        m.access == 0x10a && m.code.is_none(),
                        "InetAddress native declaration changed: {name}"
                    );
                }
            } else if name != owner {
                ensure!(
                    class.super_name == "java/lang/Object"
                        && !class.methods.iter().any(|m| m.name == "<clinit>"),
                    "InetAddress holder initialization now needs Java execution"
                );
            }
            let layout = hierarchy::compact_layout(registry, id)?;
            layouts.push(Layout {
                payload_bytes: layout.payload_bytes,
                reference_prefix: layout.reference_prefix,
                fields: layout.fields.len(),
            });
            physical.push(layout);
        }
        let class = registry
            .definition(type_ids[0])
            .context("Missing InetAddress source")?;
        let prefer_ipv4_stack_field = if cache_family == 0 {
            Some(
                class
                    .field_info
                    .iter()
                    .position(|f| {
                        f.name == "PREFER_IPV4_STACK_VALUE"
                            && f.descriptor == "Ljava/lang/String;"
                            && f.access == 0x1a
                    })
                    .context("InetAddress IPv4 preference snapshot field changed")?,
            )
        } else {
            None
        };
        let constructor = if cache_family != 0 {
            let index = class
                .methods
                .iter()
                .position(|m| m.name == "<init>" && m.descriptor == "()V")
                .context("InetAddress cached zero-argument constructor changed")?;
            let m = &class.methods[index];
            ensure!(
                m.access == 0,
                "InetAddress cached constructor access changed"
            );
            let code = m
                .code
                .as_ref()
                .context("InetAddress cached constructor requires original Java Code")?;
            Some(Constructor {
                index,
                access: m.access,
                code_sha256: files::digest_bytes(&code.bytes).sha256,
                invoked_by_cache_initialization: false,
            })
        } else {
            None
        };
        let mut fields = Vec::new();
        let cached_fields = if cache_family == 0 {
            vec![
                (0, "holder", "Ljava/net/InetAddress$InetAddressHolder;"),
                (1, "address", "I"),
                (1, "family", "I"),
                (1, "hostName", "Ljava/lang/String;"),
                (1, "originalHostName", "Ljava/lang/String;"),
            ]
        } else if cache_family == 6 {
            vec![
                (0, "holder6", "Ljava/net/Inet6Address$Inet6AddressHolder;"),
                (1, "ipaddress", "[B"),
                (1, "scope_id", "I"),
                (1, "scope_id_set", "Z"),
                (1, "scope_ifname", "Ljava/net/NetworkInterface;"),
            ]
        } else {
            vec![]
        };
        for (owner, name, descriptor) in cached_fields {
            let field = physical[owner]
                .fields
                .iter()
                .find(|f| {
                    f.member.owner == type_ids[owner]
                        && f.member.name == name
                        && f.member.descriptor == descriptor
                })
                .with_context(|| {
                    format!("Missing JNI cached InetAddress field {name}:{descriptor}")
                })?;
            ensure!(
                field.member.access & 8 == 0
                    && field.storage_bytes
                        == if descriptor == "I" {
                            4
                        } else if descriptor == "Z" {
                            1
                        } else {
                            8
                        },
                "InetAddress cached field shape changed"
            );
            fields.push(Field {
                owner,
                index: field.member.index,
                name: name.into(),
                descriptor: descriptor.into(),
                offset: field.offset,
                width: field.storage_bytes,
                reference: field.reference,
            });
        }
        Ok(Self {
            abi: if cache_family == 0 { 1 } else { 2 },
            class_id,
            cache_family,
            type_ids,
            origins,
            layouts,
            fields,
            prefer_ipv4_stack_field,
            constructor,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/inet_address.asm"
            ))
            .sha256,
            bootstrap_class_metadata_pinned: true,
            runtime_jni_lookup_used: false,
            network_backend_complete: false,
        })
    }
    pub(super) fn emit(&self, out: &mut String, availability: bool) -> Result<()> {
        ensure!(
            self.fields.len() == if self.cache_family == 4 { 0 } else { 5 }
                && self.type_ids.len() == 2
                && self.layouts.len() == 2,
            "InetAddress cache shape changed"
        );
        let suffix = if self.cache_family == 0 {
            String::new()
        } else {
            self.cache_family.to_string()
        };
        let prefix = format!("boom_inet{suffix}");
        out.push_str("EXTERN boom_inet_address_init:PROC\n.const\n");
        for (i, l) in self.layouts.iter().enumerate() {
            writeln!(
                out,
                "ALIGN 8\n{prefix}_layout{i} DWORD 04F424A43h,2\n    QWORD {}\n    DWORD {},{}",
                l.payload_bytes, l.reference_prefix, l.fields
            )?;
        }
        writeln!(out, "ALIGN 8\n{prefix}_field_rows LABEL BYTE")?;
        for f in &self.fields {
            writeln!(
                out,
                "    DWORD {},{}\n    QWORD {}\n    DWORD {},{}",
                f.owner,
                f.width,
                f.offset,
                f.index,
                u32::from(f.reference)
            )?;
        }
        let constructor = if let Some(c) = &self.constructor {
            writeln!(
                out,
                "ALIGN 8\n{prefix}_constructor DWORD 044494D4Ah,1\n    QWORD OFFSET boom_t{}\n    DWORD {},{}\n    QWORD 0",
                self.type_ids[0], c.index, c.access
            )?;
            format!("OFFSET {prefix}_constructor")
        } else {
            "0".into()
        };
        writeln!(
            out,
            ".data\nALIGN 8\n{prefix}_cache DWORD 052444149h,{},0,{}\n    QWORD OFFSET boom_class{},OFFSET boom_t{},OFFSET boom_t{},OFFSET {prefix}_layout0,OFFSET {prefix}_layout1,OFFSET {prefix}_field_rows,{constructor},{}\n.code\nPUBLIC boom_get_inet{suffix}_cache\nboom_get_inet{suffix}_cache PROC\n    lea rax,{prefix}_cache\n    ret\nboom_get_inet{suffix}_cache ENDP",
            self.abi,
            self.fields.len(),
            self.class_id,
            self.type_ids[0],
            self.type_ids[1],
            self.cache_family
        )?;
        if availability {
            ensure!(
                self.cache_family == 0,
                "Only base InetAddress owns network availability"
            );
            writeln!(
                out,
                "EXTERN boom_inet_address_available:PROC\n.data\nALIGN 8\nboom_inet_availability DWORD 056415049h,1,0,0\n    QWORD OFFSET boom_s{}_{},OFFSET boom_string_pool,OFFSET boom_inet_cache\n    DWORD 0,0,0,0,0,0\n.code\nPUBLIC boom_get_inet_availability\nboom_get_inet_availability PROC\n    lea rax,boom_inet_availability\n    ret\nboom_get_inet_availability ENDP",
                self.class_id,
                self.prefer_ipv4_stack_field
                    .context("Missing IPv4 property snapshot")?
            )?;
        }
        Ok(())
    }
}

/// Emit source-verified metadata and a deliberately uninitialized class descriptor
/// for isolated ABI tests. This neither executes InetAddress Java init nor sockets.
pub fn inspect(
    inputs: &crate::lock::InputLock,
    manifest: &std::path::Path,
    output: &std::path::Path,
    owner: &str,
) -> Result<Plan> {
    let provider = types::VanillaTypes::new(inputs, manifest)?;
    let mut registry = types::Registry::new(&provider);
    let plan = if owner == OWNER {
        Plan::prepare(&mut registry, 0)?
    } else {
        Plan::prepare_for(&mut registry, 0, owner)?
    };
    std::fs::create_dir_all(output)?;
    let mut asm = String::from(
        "; JNI-cache metadata ABI fixture only; no original Java initialization.\noption casemap:none\n.data\nALIGN 8\nboom_class0 DWORD 0434C4153h,2,0,0\n    QWORD 0\n    DWORD 0,0\n    QWORD 0,0,0,0\n.const\n",
    );
    for id in plan
        .type_ids
        .iter()
        .collect::<std::collections::BTreeSet<_>>()
    {
        writeln!(
            asm,
            "ALIGN 8\nboom_t{id} DWORD 054595045h,1,1,0\n    QWORD 0,0\n    DWORD 0,0"
        )?;
    }
    plan.emit(&mut asm, false)?;
    asm.push_str("END\n");
    files::write_atomic(&output.join("cache.asm"), asm.as_bytes())?;
    files::write_atomic(
        &output.join("cache.json"),
        &serde_json::to_vec_pretty(&plan)?,
    )?;
    Ok(plan)
}
