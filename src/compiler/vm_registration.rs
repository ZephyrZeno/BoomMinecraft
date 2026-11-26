//! java.base VM native registration and UTC adjustment, implemented in MASM.
use super::{classfile::ClassFile, numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::fmt::Write as _;
pub const OWNER: &str = "jdk/internal/misc/VM";
pub const FINALIZER_OWNER: &str = "java/lang/ref/Finalizer";
pub const BOOT_LOADER_OWNER: &str = "jdk/internal/loader/BootLoader";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum Operation {
    Initialize = 0,
    NanoAdjustment = 1,
    InetAddressInit = 2,
    InetAddressIPv4 = 3,
    InetAddressIPv6 = 4,
    FinalizationEnabled = 5,
    BootUnnamedModule = 6,
    Inet4Init = 7,
    Inet6Init = 8,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, desc: &str) -> Option<Self> {
        if name == "init" && desc == "()V" {
            if owner == super::inet_address::IPV4 {
                return Some(Self::Inet4Init);
            }
            if owner == super::inet_address::IPV6 {
                return Some(Self::Inet6Init);
            }
        }
        if owner == BOOT_LOADER_OWNER
            && name == "setBootLoaderUnnamedModule0"
            && desc == "(Ljava/lang/Module;)V"
        {
            return Some(Self::BootUnnamedModule);
        }
        if owner == FINALIZER_OWNER && name == "isFinalizationEnabled" && desc == "()Z" {
            return Some(Self::FinalizationEnabled);
        }
        if owner == super::inet_address::OWNER {
            return match (name, desc) {
                ("init", "()V") => Some(Self::InetAddressInit),
                ("isIPv4Available", "()Z") => Some(Self::InetAddressIPv4),
                ("isIPv6Supported", "()Z") => Some(Self::InetAddressIPv6),
                _ => None,
            };
        }
        if owner != OWNER {
            return None;
        }
        match (name, desc) {
            ("initialize", "()V") => Some(Self::Initialize),
            ("getNanoTimeAdjustment", "(J)J") => Some(Self::NanoAdjustment),
            _ => None,
        }
    }
    pub(super) fn owner(self) -> &'static str {
        if self == Self::Inet4Init {
            super::inet_address::IPV4
        } else if self == Self::Inet6Init {
            super::inet_address::IPV6
        } else if self == Self::BootUnnamedModule {
            BOOT_LOADER_OWNER
        } else if self == Self::FinalizationEnabled {
            FINALIZER_OWNER
        } else if self.is_inet() {
            super::inet_address::OWNER
        } else {
            OWNER
        }
    }
    pub(super) fn is_inet(self) -> bool {
        matches!(
            self,
            Self::InetAddressInit
                | Self::InetAddressIPv4
                | Self::InetAddressIPv6
                | Self::Inet4Init
                | Self::Inet6Init
        )
    }
    fn name(self) -> &'static str {
        match self {
            Self::Initialize => "initialize",
            Self::NanoAdjustment => "getNanoTimeAdjustment",
            Self::InetAddressInit | Self::Inet4Init | Self::Inet6Init => "init",
            Self::InetAddressIPv4 => "isIPv4Available",
            Self::InetAddressIPv6 => "isIPv6Supported",
            Self::FinalizationEnabled => "isFinalizationEnabled",
            Self::BootUnnamedModule => "setBootLoaderUnnamedModule0",
        }
    }
    fn descriptor(self) -> &'static str {
        match self {
            Self::Initialize | Self::InetAddressInit | Self::Inet4Init | Self::Inet6Init => "()V",
            Self::NanoAdjustment => "(J)J",
            Self::InetAddressIPv4 | Self::InetAddressIPv6 | Self::FinalizationEnabled => "()Z",
            Self::BootUnnamedModule => "(Ljava/lang/Module;)V",
        }
    }
    pub(super) fn signature(self) -> numeric::Signature {
        use numeric::{Signature, Type};
        match self {
            Self::BootUnnamedModule => Signature {
                arguments: vec![Type::AnyRef],
                result: Type::Void,
            },
            Self::Initialize | Self::InetAddressInit | Self::Inet4Init | Self::Inet6Init => {
                Signature {
                    arguments: vec![],
                    result: Type::Void,
                }
            }
            Self::NanoAdjustment => Signature {
                arguments: vec![Type::I64],
                result: Type::I64,
            },
            Self::InetAddressIPv4 | Self::InetAddressIPv6 | Self::FinalizationEnabled => {
                Signature {
                    arguments: vec![],
                    result: Type::I32,
                }
            }
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub operation: Operation,
    pub caller: ClassOrigin,
    pub origin: ClassOrigin,
    pub constant: u16,
    pub class_id: usize,
    pub native_source_sha256: String,
    pub registered_name: String,
    pub registered_descriptor: String,
    pub vm_boot_level_changed: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub field_cache: Option<super::inet_address::Plan>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub finalization_policy: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bootstrap_unnamed_field: Option<usize>,
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    operation: Operation,
    class_id: usize,
) -> Result<Binding> {
    let (o, n, d, i) = caller.static_method_reference(constant)?;
    ensure!(
        !i && Operation::resolve(&o, &n, &d) == Some(operation),
        "VM native call changed"
    );
    if operation.is_inet() {
        let plan = super::inet_address::Plan::prepare_for(registry, class_id, operation.owner())?;
        let origin = plan.origins[0].clone();
        ensure!(
            caller.name == operation.owner() && source == &origin,
            "InetAddress native methods are private to their original class"
        );
        return Ok(Binding {
            abi: 1,
            operation,
            caller: source.clone(),
            origin,
            constant,
            class_id,
            native_source_sha256: plan.native_source_sha256.clone(),
            registered_name: operation.name().into(),
            registered_descriptor: operation.descriptor().into(),
            vm_boot_level_changed: false,
            field_cache: Some(plan),
            finalization_policy: None,
            bootstrap_unnamed_field: None,
        });
    }
    if operation == Operation::FinalizationEnabled {
        let id = registry.class("bootstrap", FINALIZER_OWNER)?;
        let types::Type::Class { key, origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none()
                && caller.name == FINALIZER_OWNER
                && source == origin.as_ref(),
            "Finalizer policy requires its original private caller"
        );
        let origin = origin.as_ref().clone();
        let class = registry
            .definition(id)
            .context("Missing Finalizer source")?;
        let m = class.method(operation.name(), Some(operation.descriptor()))?;
        ensure!(
            m.access == 0x10a && m.code.is_none(),
            "Finalizer native declaration changed"
        );
        return Ok(Binding {
            abi: 1,
            operation,
            caller: source.clone(),
            origin,
            constant,
            class_id,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/vm_registration.asm"
            ))
            .sha256,
            registered_name: operation.name().into(),
            registered_descriptor: operation.descriptor().into(),
            vm_boot_level_changed: false,
            field_cache: None,
            finalization_policy: Some("disabled".into()),
            bootstrap_unnamed_field: None,
        });
    }
    if operation == Operation::BootUnnamedModule {
        let id = registry.class("bootstrap", BOOT_LOADER_OWNER)?;
        let types::Type::Class { key, origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none()
                && caller.name == BOOT_LOADER_OWNER
                && source == origin.as_ref(),
            "BootLoader module publication requires its original private caller"
        );
        let origin = origin.as_ref().clone();
        let class = registry
            .definition(id)
            .context("Missing BootLoader source")?;
        let m = class.method(operation.name(), Some(operation.descriptor()))?;
        ensure!(
            m.access == 0x10a && m.code.is_none(),
            "BootLoader native declaration changed"
        );
        let field = class
            .field_info
            .iter()
            .position(|f| {
                f.name == "UNNAMED_MODULE"
                    && f.descriptor == "Ljava/lang/Module;"
                    && f.access == 0x1a
            })
            .context("BootLoader unnamed module field changed")?;
        return Ok(Binding {
            abi: 1,
            operation,
            caller: source.clone(),
            origin,
            constant,
            class_id,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/module_objects.asm"
            ))
            .sha256,
            registered_name: operation.name().into(),
            registered_descriptor: operation.descriptor().into(),
            vm_boot_level_changed: false,
            field_cache: None,
            finalization_policy: None,
            bootstrap_unnamed_field: Some(field),
        });
    }
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
            && access & 0x601 == 1,
        "VM registration requires original public bootstrap source"
    );
    let origin = origin.as_ref().clone();
    let class = registry
        .definition(id)
        .context("Missing VM native source")?;
    for op in [Operation::Initialize, Operation::NanoAdjustment] {
        let m = class.method(op.name(), Some(op.descriptor()))?;
        ensure!(
            m.access
                == if op == Operation::Initialize {
                    0x10a
                } else {
                    0x109
                }
                && m.code.is_none(),
            "VM native declaration changed"
        );
    }
    if operation == Operation::Initialize {
        ensure!(
            caller.name == OWNER && source == &origin,
            "VM.initialize is private to original VM source"
        );
    }
    Ok(Binding {
        abi: 1,
        operation,
        caller: source.clone(),
        origin,
        constant,
        class_id,
        native_source_sha256: files::digest_bytes(include_bytes!(
            "../../native/runtime/vm_registration.asm"
        ))
        .sha256,
        registered_name: "getNanoTimeAdjustment".into(),
        registered_descriptor: "(J)J".into(),
        vm_boot_level_changed: false,
        field_cache: None,
        finalization_policy: None,
        bootstrap_unnamed_field: None,
    })
}
pub(super) fn emit(
    out: &mut String,
    bindings: &[Binding],
    modules: Option<&super::modules::Plan>,
) -> Result<()> {
    if let Some(b) = bindings
        .iter()
        .find(|b| b.operation == Operation::BootUnnamedModule)
    {
        let modules = modules.context("BootLoader module publication needs physical modules")?;
        ensure!(
            modules.abi == 3 && modules.objects.is_some(),
            "BootLoader module publication requires physical Module objects"
        );
        let slot = modules
            .identities
            .iter()
            .position(|m| m.defining_loader == "bootstrap" && m.name.is_none())
            .context("Missing bootstrap unnamed module GC root")?;
        writeln!(
            out,
            "EXTERN boom_boot_unnamed_publish:PROC\n.data\nALIGN 8\nboom_boot_unnamed_pool DWORD 0444D5542h,1,0,0\n    QWORD OFFSET boom_class{},OFFSET boom_s{}_{},OFFSET boom_module_pool,OFFSET boom_module_roots+{}\n.code\nPUBLIC boom_get_boot_unnamed_pool\nboom_get_boot_unnamed_pool PROC\n    lea rax,boom_boot_unnamed_pool\n    ret\nboom_get_boot_unnamed_pool ENDP",
            b.class_id,
            b.class_id,
            b.bootstrap_unnamed_field.unwrap(),
            slot * 8
        )?;
    }
    if bindings
        .iter()
        .any(|b| b.operation == Operation::FinalizationEnabled)
    {
        out.push_str("EXTERN boom_finalization_enabled:PROC\n");
    }
    out.push_str("EXTERN boom_vm_native:PROC\nEXTERN boom_vm_nano_adjustment:PROC\n.data\nALIGN 8\nboom_vm_native_pool DWORD 0564D5247h, 1, 0, 1\n    QWORD OFFSET boom_vm_nano_adjustment, 0\n.code\nPUBLIC boom_get_vm_native_pool\nboom_get_vm_native_pool PROC\n    lea rax, boom_vm_native_pool\n    ret\nboom_get_vm_native_pool ENDP\n");
    let mut emitted = std::collections::BTreeSet::new();
    for p in bindings.iter().filter_map(|b| b.field_cache.as_ref()) {
        if emitted.insert(p.class_id) {
            p.emit(
                out,
                p.cache_family == 0
                    && bindings.iter().any(|b| {
                        matches!(
                            b.operation,
                            Operation::InetAddressIPv4 | Operation::InetAddressIPv6
                        )
                    }),
            )?;
        }
    }
    Ok(())
}
