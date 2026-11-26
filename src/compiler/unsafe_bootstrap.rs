//! Original Unsafe bootstrap and deliberately partial memory capabilities.
use super::{classfile::ClassFile, program::ClassState, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

pub const OWNER: &str = "jdk/internal/misc/Unsafe";
pub const CONSTANTS: &str = "jdk/internal/misc/UnsafeConstants";
const MEMBERS: [(&str, &str, u16); 13] = [
    ("registerNatives", "()V", 0x10a),
    ("arrayBaseOffset0", "(Ljava/lang/Class;)I", 0x102),
    ("arrayIndexScale0", "(Ljava/lang/Class;)I", 0x102),
    ("getLongVolatile", "(Ljava/lang/Object;J)J", 0x101),
    ("compareAndSetLong", "(Ljava/lang/Object;JJJ)Z", 0x111),
    ("getIntVolatile", "(Ljava/lang/Object;J)I", 0x101),
    ("compareAndSetInt", "(Ljava/lang/Object;JII)Z", 0x111),
    ("staticFieldOffset0", "(Ljava/lang/reflect/Field;)J", 0x102),
    (
        "staticFieldBase0",
        "(Ljava/lang/reflect/Field;)Ljava/lang/Object;",
        0x102,
    ),
    ("fullFence", "()V", 0x101),
    (
        "objectFieldOffset1",
        "(Ljava/lang/Class;Ljava/lang/String;)J",
        0x102,
    ),
    ("getBooleanVolatile", "(Ljava/lang/Object;J)Z", 0x101),
    ("compareAndExchangeByte", "(Ljava/lang/Object;JBB)B", 0x11),
];
pub const FIELDS: [(&str, &str); 5] = [
    ("ADDRESS_SIZE0", "I"),
    ("PAGE_SIZE", "I"),
    ("BIG_ENDIAN", "Z"),
    ("UNALIGNED_ACCESS", "Z"),
    ("DATA_CACHE_LINE_FLUSH_SIZE", "I"),
];
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum Operation {
    Register,
    ArrayBase,
    ArrayScale,
    ReadLong,
    CasLong,
    ReadInt,
    CasInt,
    StaticOffset,
    StaticBase,
    FullFence,
    ObjectOffset,
    ReadBoolean,
    ExchangeByte,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, desc: &str) -> Option<Self> {
        if owner != OWNER {
            return None;
        }
        MEMBERS
            .iter()
            .position(|m| m.0 == name && m.1 == desc)
            .map(|i| match i {
                0 => Self::Register,
                1 => Self::ArrayBase,
                2 => Self::ArrayScale,
                3 => Self::ReadLong,
                4 => Self::CasLong,
                5 => Self::ReadInt,
                6 => Self::CasInt,
                7 => Self::StaticOffset,
                8 => Self::StaticBase,
                9 => Self::FullFence,
                10 => Self::ObjectOffset,
                11 => Self::ReadBoolean,
                _ => Self::ExchangeByte,
            })
    }
    pub(super) fn descriptor(self) -> &'static str {
        MEMBERS[self as usize].1
    }
    pub(super) fn private(self) -> bool {
        (self as u32) < 3 || self.static_field() || self == Self::ObjectOffset
    }
    pub(super) fn static_field(self) -> bool {
        matches!(self, Self::StaticOffset | Self::StaticBase)
    }
    pub(super) fn object_field(self) -> bool {
        matches!(
            self,
            Self::ObjectOffset | Self::ReadBoolean | Self::ExchangeByte
        )
    }
    pub(super) fn field_metadata(self) -> bool {
        self.static_field() || self.object_field()
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub operation: Operation,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub constants_origin: ClassOrigin,
    pub class_id: usize,
    pub constants_class_id: usize,
    pub initializer_code_sha256: String,
    pub constants_initializer_code_sha256: String,
    pub native_declarations: usize,
    pub executable_native_declarations: usize,
    pub executable_operations: usize,
    pub java_intrinsic_code_sha256: Option<String>,
    pub bindings: Vec<Binding>,
    pub native_source_sha256: String,
    pub arrays_use_payload_offsets: bool,
    pub long_array_and_thread_counter_only: bool,
    pub int_array_operations: bool,
    pub static_field_access: bool,
    pub full_fence_supported: bool,
    pub object_field_access: bool,
    pub boolean_array_operations: bool,
    pub full_unsafe_coverage: bool,
}
impl Plan {
    pub(super) fn new(
        registry: &mut types::Registry<'_>,
        class_id: usize,
        constants_class_id: usize,
    ) -> Result<Self> {
        let mut origins = Vec::new();
        let mut hashes = Vec::new();
        let mut java_intrinsic_code_sha256 = None;
        for (owner, expected) in [(OWNER, 236), (CONSTANTS, 21)] {
            let id = registry.class("bootstrap", owner)?;
            let types::Type::Class { key, origin, .. } = &registry.types[id] else {
                unreachable!()
            };
            ensure!(
                key.loader == "bootstrap"
                    && origin.source_id == "jdk:java.base"
                    && origin.generated.is_none(),
                "Unsafe requires original bootstrap source"
            );
            origins.push(origin.as_ref().clone());
            let class = registry
                .definition(id)
                .context("Missing Unsafe definition")?;
            let init = class.method("<clinit>", Some("()V"))?;
            let code = init
                .code
                .as_ref()
                .context("Missing Unsafe original initializer")?;
            ensure!(
                code.bytes.len() == expected && init.access == 8,
                "Original Unsafe initializer shape changed: {owner}"
            );
            hashes.push(files::digest_bytes(&code.bytes).sha256);
            if owner == OWNER {
                for (name, desc, flags) in MEMBERS {
                    let m = class.method(name, Some(desc))?;
                    ensure!(
                        m.access == flags && m.code.is_none() == (flags & 0x100 != 0),
                        "Unsafe declaration changed: {name}{desc}"
                    );
                    if let Some(code) = &m.code {
                        ensure!(name == "compareAndExchangeByte" && m.runtime_visible_annotations.iter().any(|a| a == "Ljdk/internal/vm/annotation/IntrinsicCandidate;"), "Unreviewed Unsafe Java intrinsic");
                        java_intrinsic_code_sha256 = Some(files::digest_bytes(&code.bytes).sha256);
                    }
                }
            } else {
                for (name, desc) in FIELDS {
                    ensure!(
                        class
                            .field_info
                            .iter()
                            .any(|f| f.name == name && f.descriptor == desc && f.access == 0x18),
                        "Unsafe VM constant declaration changed: {name}"
                    );
                }
            }
        }
        let id = registry.class("bootstrap", OWNER)?;
        let native_declarations = registry
            .definition(id)
            .unwrap()
            .methods
            .iter()
            .filter(|m| m.access & 0x100 != 0)
            .count();
        Ok(Self {
            abi: 3,
            origin: origins.remove(0),
            constants_origin: origins.remove(0),
            class_id,
            constants_class_id,
            initializer_code_sha256: hashes.remove(0),
            constants_initializer_code_sha256: hashes.remove(0),
            native_declarations,
            executable_native_declarations: MEMBERS.iter().filter(|m| m.2 & 0x100 != 0).count(),
            executable_operations: MEMBERS.len(),
            java_intrinsic_code_sha256,
            bindings: Vec::new(),
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/unsafe_bootstrap.asm"
            ))
            .sha256,
            arrays_use_payload_offsets: true,
            long_array_and_thread_counter_only: false,
            int_array_operations: true,
            static_field_access: false,
            full_fence_supported: true,
            object_field_access: false,
            boolean_array_operations: true,
            full_unsafe_coverage: false,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
        op: Operation,
    ) -> Result<()> {
        self.static_field_access |= op.static_field();
        self.object_field_access |= op.object_field();
        let (owner, name, desc, interface) = caller.static_method_reference(constant)?;
        ensure!(
            !interface && Operation::resolve(&owner, &name, &desc) == Some(op),
            "Unsafe callsite changed"
        );
        if op.private() {
            ensure!(
                caller.name == OWNER && source == &self.origin,
                "Unsafe private native requires its original caller"
            );
        }
        if !self
            .bindings
            .iter()
            .any(|b| b.caller == *source && b.constant == constant)
        {
            self.bindings.push(Binding {
                caller: source.clone(),
                constant,
                operation: op,
            });
            self.bindings.sort_by(|a, b| {
                (&a.caller.binary_name, a.constant).cmp(&(&b.caller.binary_name, b.constant))
            });
        }
        Ok(())
    }
    pub(super) fn emit(
        &self,
        out: &mut String,
        states: &[ClassState],
        types: &[types::Type],
        threads: bool,
        fields: bool,
    ) -> Result<()> {
        let constants = states
            .iter()
            .find(|s| s.id == self.constants_class_id)
            .context("Missing Unsafe constants class state")?;
        let initializer = constants
            .initializer
            .context("Unsafe constants initializer was not compiled")?;
        out.push_str("EXTERN boom_unsafe_native:PROC\nEXTERN boom_unsafe_constants_fill:PROC\nPUBLIC boom_get_unsafe_pool\n.const\nALIGN 8\nboom_unsafe_constant_cells LABEL QWORD\n");
        for (name, desc) in FIELDS {
            let f = constants
                .fields
                .iter()
                .find(|f| f.name == name && f.descriptor == desc)
                .context("Missing Unsafe VM constant cell")?;
            out.push_str(&format!(
                "    QWORD OFFSET boom_s{}_{}\n",
                constants.id, f.index
            ));
        }
        out.push_str("boom_unsafe_array_scales LABEL DWORD\n");
        for t in types {
            let scale = if let types::Type::Array { component } = t {
                match types[*component] {
                    types::Type::Primitive {
                        value: types::Primitive::Boolean | types::Primitive::Byte,
                    } => 1,
                    types::Type::Primitive {
                        value: types::Primitive::Char | types::Primitive::Short,
                    } => 2,
                    types::Type::Primitive {
                        value: types::Primitive::Int | types::Primitive::Float,
                    } => 4,
                    _ => 8,
                }
            } else {
                0
            };
            out.push_str(&format!("    DWORD {scale}\n"));
        }
        let registry_cell = if threads {
            "OFFSET boom_thread_registry_ptr"
        } else {
            "0"
        };
        ensure!(
            !(self.static_field_access || self.object_field_access) || fields,
            "Field Unsafe requires Field metadata"
        );
        let field_callbacks = if fields {
            "OFFSET boom_field_pool,OFFSET boom_field_static_address,OFFSET boom_field_service,OFFSET boom_field_instance_address"
        } else {
            "0,0,0,0"
        };
        out.push_str(&format!(".data\nALIGN 8\nboom_unsafe_pool DWORD 0554E5346h,3,0,13\n    QWORD OFFSET boom_layout{},OFFSET boom_runtime_type_map,OFFSET boom_mirror_pool,OFFSET boom_heap_ptr\n    QWORD OFFSET boom_unsafe_array_scales,{},OFFSET boom_unsafe_constant_cells,{registry_cell},{field_callbacks}\n.code\nboom_get_unsafe_pool PROC\n    lea rax,boom_unsafe_pool\n    ret\nboom_get_unsafe_pool ENDP\nboom_unsafe_constants_initialize PROC FRAME\n    sub rsp,56\n    .allocstack 56\n    .endprolog\n    mov QWORD PTR [rsp+32],rcx\n    call boom_m{initializer}_body\n    mov rcx,QWORD PTR [rsp+32]\n    cmp DWORD PTR [rcx],0\n    jne boom_unsafe_constants_done\n    lea rdx,boom_unsafe_pool\n    call boom_unsafe_constants_fill\nboom_unsafe_constants_done:\n    xor eax,eax\n    add rsp,56\n    ret\nboom_unsafe_constants_initialize ENDP\n",self.class_id,types.len()));
        Ok(())
    }
}
