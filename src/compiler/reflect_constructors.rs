//! Frozen-image reflective Constructor objects and invocation, executed in MASM.
use super::{
    classfile::ClassFile, constructor_entries, hierarchy, nests, numeric, reflect_new, types,
};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fmt::Write as _};
pub const OWNER: &str = "java/lang/reflect/Constructor";
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Operation {
    Declared = 0,
    Public = 1,
    Invoke = 2,
    DeclaringClass = 3,
    Parameters = 4,
    Exceptions = 5,
    Modifiers = 6,
    ParameterCount = 7,
    VarArgs = 8,
    Synthetic = 9,
    Name = 10,
    Equals = 11,
    Hash = 12,
    ToString = 13,
}
impl Operation {
    pub(super) fn resolve(o: &str, n: &str, d: &str) -> Option<Self> {
        if o == "java/lang/Class" {
            return match (n, d) {
                (
                    "getDeclaredConstructor",
                    "([Ljava/lang/Class;)Ljava/lang/reflect/Constructor;",
                ) => Some(Self::Declared),
                ("getConstructor", "([Ljava/lang/Class;)Ljava/lang/reflect/Constructor;") => {
                    Some(Self::Public)
                }
                _ => None,
            };
        }
        if o != OWNER {
            return None;
        }
        match (n, d) {
            ("newInstance", "([Ljava/lang/Object;)Ljava/lang/Object;") => Some(Self::Invoke),
            ("getDeclaringClass", "()Ljava/lang/Class;") => Some(Self::DeclaringClass),
            ("getParameterTypes", "()[Ljava/lang/Class;") => Some(Self::Parameters),
            ("getExceptionTypes", "()[Ljava/lang/Class;") => Some(Self::Exceptions),
            ("getModifiers", "()I") => Some(Self::Modifiers),
            ("getParameterCount", "()I") => Some(Self::ParameterCount),
            ("isVarArgs", "()Z") => Some(Self::VarArgs),
            ("isSynthetic", "()Z") => Some(Self::Synthetic),
            ("getName", "()Ljava/lang/String;") => Some(Self::Name),
            ("equals", "(Ljava/lang/Object;)Z") => Some(Self::Equals),
            ("hashCode", "()I") => Some(Self::Hash),
            ("toString", "()Ljava/lang/String;") => Some(Self::ToString),
            _ => None,
        }
    }
    pub(super) fn lookup(self) -> bool {
        matches!(self, Self::Declared | Self::Public)
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub access_caller: ClassOrigin,
    pub caller_type: usize,
    pub constant: u16,
    pub site: usize,
    pub operation: Operation,
    pub declaration: ClassOrigin,
    pub code_sha256: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Record {
    pub type_id: usize,
    pub slot: usize,
    pub modifiers: u16,
    pub descriptor: String,
    pub parameters: Vec<usize>,
    pub exceptions: Vec<usize>,
    pub flags: u32,
    pub signature: Option<String>,
    pub attributes: super::classfile::ReflectionMetadata,
    pub source: ClassOrigin,
    pub code_sha256: Option<String>,
    pub helper: Option<usize>,
    pub class_state: Option<usize>,
    pub name_literal: usize,
    pub name_hash: u32,
    pub display_literal: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Catalog {
    pub constructor_type: usize,
    pub class_array_type: usize,
    pub object_array_type: usize,
    pub object_type: usize,
    pub class_type: usize,
    pub records: Vec<Record>,
    pub indexed_types: usize,
    pub boxes: Vec<BoxLayout>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BoxLayout {
    pub type_id: usize,
    pub kind: usize,
    pub value_offset: usize,
    pub value_width: usize,
    pub layout: numeric::ObjectLayout,
    pub source: ClassOrigin,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Site {
    pub binding: Binding,
    pub access: Vec<u8>,
    pub nest_proofs: Vec<nests::Proof>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub catalog: Catalog,
    pub sites: Vec<Site>,
    pub constructors: Vec<constructor_entries::Plan>,
    pub type_names: Vec<Vec<u16>>,
    pub non_class_types: Vec<bool>,
    pub message_offset: usize,
    pub target_offset: usize,
    pub native_source_sha256: String,
    pub module_descriptor_sha256: String,
    pub module_snapshot_fingerprint: String,
    pub original_java_class_methods_executed: bool,
    pub original_java_constructor_methods_executed: bool,
    pub vm_owned_constructor_layout: bool,
    pub security_manager_supported: bool,
    pub set_accessible_supported: bool,
    pub generic_reflection_complete: bool,
    pub reflective_stack_frames_complete: bool,
    pub automatic_gc: bool,
}
fn origin(registry: &types::Registry<'_>, id: usize) -> Result<ClassOrigin> {
    let types::Type::Class { origin, .. } = &registry.types[id] else {
        anyhow::bail!("Expected reflection class")
    };
    Ok(origin.as_ref().clone())
}
pub(super) fn register(registry: &mut types::Registry<'_>) -> Result<(usize, usize, usize)> {
    let c = registry.class("bootstrap", OWNER)?;
    let o = origin(registry, c)?;
    ensure!(
        o.source_id == "jdk:java.base" && o.generated.is_none(),
        "Constructor representation requires original java.base"
    );
    ensure!(
        registry.definition(c).unwrap().access & 0x611 == 0x11,
        "Constructor must remain final"
    );
    let a = registry.field("bootstrap", "[Ljava/lang/Class;")?;
    let b = registry.field("bootstrap", "[Ljava/lang/Object;")?;
    for n in [
        "Boolean",
        "Byte",
        "Character",
        "Short",
        "Integer",
        "Long",
        "Float",
        "Double",
    ] {
        registry.class("bootstrap", &format!("java/lang/{n}"))?;
    }
    Ok((c, a, b))
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    access_context: (ClassOrigin, usize),
    constant: u16,
    operation: Operation,
    site: usize,
) -> Result<Binding> {
    let (access_caller, caller_type) = access_context;
    let (o, n, d) = caller.method_reference(constant)?;
    ensure!(
        Operation::resolve(&o, &n, &d) == Some(operation),
        "Constructor operation reference changed"
    );
    let mut id = registry.class("bootstrap", &o)?;
    let declaration;
    let code_sha256;
    loop {
        let class = registry
            .definition(id)
            .context("Missing reflection declaration")?;
        if let Some(m) = class
            .methods
            .iter()
            .find(|m| m.name == n && m.descriptor == d)
        {
            ensure!(
                m.access & 0x109 == 1 && m.code.is_some(),
                "Reflection declaration must be original public Java Code"
            );
            if operation.lookup() || operation == Operation::Invoke {
                ensure!(
                    m.runtime_visible_annotations
                        .iter()
                        .any(|a| a == "Ljdk/internal/reflect/CallerSensitive;"),
                    "Reflection caller-sensitive contract changed"
                );
            }
            declaration = origin(registry, id)?;
            code_sha256 = files::digest_bytes(&m.code.as_ref().unwrap().bytes).sha256;
            break;
        }
        let parent = class.super_name.clone();
        ensure!(!parent.is_empty(), "Missing reflection member");
        id = registry.class("bootstrap", &parent)?;
    }
    ensure!(
        declaration.source_id == "jdk:java.base" && declaration.generated.is_none(),
        "Reflection declaration provenance changed"
    );
    Ok(Binding {
        caller: source.clone(),
        access_caller,
        caller_type,
        constant,
        site,
        operation,
        declaration,
        code_sha256,
    })
}
fn box_layout(registry: &types::Registry<'_>, id: usize, kind: usize) -> Result<BoxLayout> {
    let layout = hierarchy::compact_layout(registry, id)?;
    let fields = layout
        .fields
        .iter()
        .map(|f| {
            let types::Type::Class { key, .. } = &registry.types[f.member.owner] else {
                unreachable!()
            };
            numeric::FieldLayout {
                name: f.member.name.clone(),
                descriptor: f.member.descriptor.clone(),
                offset: f.offset,
                declaring_class: Some(key.name.clone()),
                declaring_field: Some(f.member.index),
                storage_bytes: Some(f.storage_bytes),
            }
        })
        .collect::<Vec<_>>();
    let value = fields
        .iter()
        .find(|f| f.name == "value")
        .context("Missing boxed primitive value")?;
    let value_offset = value.offset;
    let value_width = value.storage_bytes.unwrap();
    ensure!(
        layout.reference_prefix == 0
            && value_width
                == if kind == 5 || kind == 7 {
                    8
                } else if kind == 4 || kind == 6 {
                    4
                } else if kind == 2 || kind == 3 {
                    2
                } else {
                    1
                },
        "Boxed primitive layout changed"
    );
    Ok(BoxLayout {
        type_id: id,
        kind,
        value_offset,
        value_width,
        layout: numeric::ObjectLayout {
            abi: 2,
            payload_bytes: layout.payload_bytes,
            reference_prefix_fields: layout.reference_prefix,
            fields,
        },
        source: origin(registry, id)?,
    })
}
impl Catalog {
    pub(super) fn prepare(registry: &mut types::Registry<'_>) -> Result<Self> {
        let (c, a, b) = register(registry)?;
        let mut boxes = Vec::new();
        for (kind, n) in [
            "Boolean",
            "Byte",
            "Character",
            "Short",
            "Integer",
            "Long",
            "Float",
            "Double",
        ]
        .iter()
        .enumerate()
        {
            let id = registry.class("bootstrap", &format!("java/lang/{n}"))?;
            boxes.push(box_layout(registry, id, kind)?);
        }
        let indexed_types = registry.types.len();
        let mut declarations = Vec::new();
        for id in 0..indexed_types {
            if let types::Type::Class {
                key,
                access,
                origin,
                ..
            } = &registry.types[id]
            {
                let class = registry.definition(id).unwrap();
                for (slot, m) in class
                    .methods
                    .iter()
                    .enumerate()
                    .filter(|(_, m)| m.name == "<init>")
                {
                    declarations.push((
                        id,
                        key.loader.clone(),
                        *access,
                        origin.as_ref().clone(),
                        slot,
                        m.access,
                        m.descriptor.clone(),
                        class.reflection_metadata(slot)?.clone(),
                        m.code
                            .as_ref()
                            .map(|c| files::digest_bytes(&c.bytes).sha256),
                    ));
                }
            }
        }
        let mut records = Vec::new();
        for (
            type_id,
            loader,
            class_access,
            source,
            slot,
            modifiers,
            descriptor,
            attributes,
            code_sha256,
        ) in declarations
        {
            let sig = registry.method(&loader, &descriptor)?;
            ensure!(sig.result.is_none(), "Constructor result changed");
            let exceptions = attributes
                .exceptions
                .iter()
                .map(|n| registry.class(&loader, n))
                .collect::<Result<Vec<_>>>()?;
            let flags =
                u32::from(class_access & 0x400 != 0) | (u32::from(class_access & 0x4000 != 0) << 1);
            records.push(Record {
                type_id,
                slot,
                modifiers,
                descriptor,
                parameters: sig.arguments,
                exceptions,
                flags,
                signature: attributes.signature.clone(),
                attributes,
                source,
                code_sha256,
                helper: None,
                class_state: None,
                name_literal: 0,
                name_hash: 0,
                display_literal: 0,
            });
        }
        ensure!(
            records.len() <= 262144,
            "Constructor metadata exceeds image budget"
        );
        Ok(Self {
            constructor_type: c,
            class_array_type: a,
            object_array_type: b,
            object_type: registry.class("bootstrap", "java/lang/Object")?,
            class_type: registry.class("bootstrap", "java/lang/Class")?,
            records,
            indexed_types,
            boxes,
        })
    }
    pub(super) fn extend_rows(&self, rows: &mut Vec<super::runtime_types::Binding>) {
        rows.push(super::runtime_types::Binding {
            tag: "OFFSET boom_ctor_argument_array_layout".into(),
            type_id: self.object_array_type,
            kind: 2,
            payload_bytes: 0,
            references: 0,
            element_shift: 3,
        });
        rows.push(super::runtime_types::Binding {
            tag: "OFFSET boom_constructor_vm_layout".into(),
            type_id: self.constructor_type,
            kind: 0,
            payload_bytes: 32,
            references: 1,
            element_shift: 0,
        });
        for b in &self.boxes {
            rows.push(super::runtime_types::Binding {
                tag: format!("OFFSET boom_ctor_box_layout{}", b.kind),
                type_id: b.type_id,
                kind: 0,
                payload_bytes: b.layout.payload_bytes,
                references: 0,
                element_shift: 0,
            });
        }
    }
}
impl Plan {
    #[allow(clippy::too_many_arguments)]
    pub(super) fn prepare(
        registry: &mut types::Registry<'_>,
        mut catalog: Catalog,
        bindings: Vec<Binding>,
        constructors: Vec<constructor_entries::Plan>,
        message_offset: usize,
        target_offset: usize,
        module_identity: (&str, &str),
        mut intern: impl FnMut(Vec<u16>) -> Result<usize>,
        exported: &dyn Fn(&ClassOrigin, &ClassOrigin, &str) -> Result<bool>,
    ) -> Result<Self> {
        for r in &mut catalog.records {
            let name = super::mirrors::name(&registry.types, r.type_id);
            r.name_literal = intern(name.encode_utf16().collect())?;
            r.name_hash = name
                .encode_utf16()
                .fold(0u32, |h, c| h.wrapping_mul(31).wrapping_add(c as u32));
            let modifiers = super::dispatch::modifier_text(r.modifiers & 7);
            let parameters = r
                .parameters
                .iter()
                .map(|id| super::dispatch::type_name(&registry.types, *id))
                .collect::<Vec<_>>()
                .join(",");
            let exceptions = r
                .exceptions
                .iter()
                .map(|id| super::dispatch::type_name(&registry.types, *id))
                .collect::<Vec<_>>()
                .join(",");
            let display = format!(
                "{}{name}({parameters}){}",
                if modifiers.is_empty() {
                    String::new()
                } else {
                    format!("{modifiers} ")
                },
                if exceptions.is_empty() {
                    String::new()
                } else {
                    format!(" throws {exceptions}")
                }
            );
            r.display_literal = intern(display.encode_utf16().collect())?;
        }
        let mut sites = Vec::new();
        for binding in bindings {
            let mut access = Vec::new();
            let mut nest_proofs = Vec::new();
            for r in &catalog.records {
                if binding.operation != Operation::Invoke {
                    access.push(0);
                    continue;
                }
                let types::Type::Class { key, .. } = &registry.types[r.type_id] else {
                    unreachable!()
                };
                let package = key.name.rsplit_once('/').map_or("", |v| v.0).to_string();
                let allowed = exported(&binding.access_caller, &r.source, &package)?;
                let (yes, proof) = reflect_new::accessible(
                    registry,
                    binding.caller_type,
                    r.type_id,
                    r.modifiers,
                    allowed,
                )?;
                access.push(u8::from(!yes));
                if let Some(p) = proof {
                    nest_proofs.push(p);
                }
            }
            sites.push(Site {
                binding,
                access,
                nest_proofs,
            });
        }
        let type_names = (0..registry.types.len())
            .map(|id| {
                super::mirrors::name(&registry.types, id)
                    .encode_utf16()
                    .collect()
            })
            .collect();
        Ok(Self {
            abi: 2,
            catalog,
            sites,
            constructors,
            type_names,
            non_class_types: Vec::new(),
            message_offset,
            target_offset,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/reflect_constructors.asm"
            ))
            .sha256,
            module_descriptor_sha256: module_identity.0.into(),
            module_snapshot_fingerprint: module_identity.1.into(),
            original_java_class_methods_executed: false,
            original_java_constructor_methods_executed: false,
            vm_owned_constructor_layout: true,
            security_manager_supported: false,
            set_accessible_supported: false,
            generic_reflection_complete: false,
            reflective_stack_frames_complete: false,
            automatic_gc: false,
        })
    }
    pub(super) fn finish_names(&mut self, registry: &types::Registry<'_>) {
        self.type_names = (0..registry.types.len())
            .map(|id| {
                super::mirrors::name(&registry.types, id)
                    .encode_utf16()
                    .collect()
            })
            .collect();
        self.non_class_types = registry
            .types
            .iter()
            .map(|t| !matches!(t, types::Type::Class { .. }))
            .collect();
    }
    pub(super) fn assign_helpers(
        &mut self,
        slots: &BTreeMap<(String, String, usize), (usize, usize)>,
    ) {
        for r in &mut self.catalog.records {
            if let Some(&(helper, state)) = slots.get(&(
                r.source.loader.clone(),
                r.source.binary_name.clone(),
                r.slot,
            )) {
                r.helper = Some(helper);
                r.class_state = Some(state);
            }
        }
    }
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        out.push_str("EXTERN boom_constructor_service:PROC\n.const\nALIGN 8\nboom_constructor_vm_layout DWORD 04F424A43h,1\n    QWORD 32\n    DWORD 1,4\nboom_ctor_argument_object_layout DWORD 04F424A43h,1\n    QWORD 0\n    DWORD 0,0\nboom_ctor_argument_array_layout DWORD 052454641h,1\n    QWORD OFFSET boom_ctor_argument_object_layout\n");
        for b in &self.catalog.boxes {
            writeln!(
                out,
                "ALIGN 8\nboom_ctor_box_layout{} DWORD 04F424A43h,{}\n    QWORD {}\n    DWORD 0,{}",
                b.kind,
                b.layout.abi,
                b.layout.payload_bytes,
                b.layout.fields.len()
            )?;
        }
        writeln!(out, "ALIGN 8\nboom_ctor_boxes LABEL BYTE")?;
        for b in &self.catalog.boxes {
            writeln!(
                out,
                "    QWORD OFFSET boom_t{}\n    DWORD {},{},{},0\n    QWORD {}",
                b.type_id, b.value_offset, b.value_width, b.kind, b.layout.payload_bytes
            )?;
        }
        for (i, r) in self.catalog.records.iter().enumerate() {
            for (label, values) in [("parameters", &r.parameters), ("exceptions", &r.exceptions)] {
                writeln!(out, "ALIGN 4\nboom_ctor_{label}{i} LABEL DWORD")?;
                if values.is_empty() {
                    out.push_str("    DWORD 0\n");
                } else {
                    for chunk in values.chunks(16) {
                        writeln!(
                            out,
                            "    DWORD {}",
                            chunk
                                .iter()
                                .map(|v| v.to_string())
                                .collect::<Vec<_>>()
                                .join(",")
                        )?;
                    }
                }
            }
        }
        out.push_str("ALIGN 8\nboom_ctor_records LABEL BYTE\n");
        for (i, r) in self.catalog.records.iter().enumerate() {
            let helper = r
                .helper
                .map_or("0".into(), |id| format!("OFFSET boom_m{id}"));
            let state = r
                .class_state
                .map_or("0".into(), |id| format!("OFFSET boom_class{id}"));
            writeln!(
                out,
                "    DWORD {},{},{},{}\n    QWORD OFFSET boom_ctor_parameters{i},OFFSET boom_ctor_exceptions{i}\n    DWORD {},{}\n    DWORD {},0\n    QWORD 0,0,0\n    QWORD {helper},{state}\n    DWORD {},{}",
                r.type_id,
                r.slot,
                r.modifiers,
                r.parameters.len(),
                r.exceptions.len(),
                r.flags,
                r.display_literal,
                r.name_literal,
                r.name_hash
            )?;
        }
        out.push_str("ALIGN 4\nboom_ctor_type_ranges LABEL DWORD\n");
        for id in 0..self.type_names.len() {
            let start = self
                .catalog
                .records
                .iter()
                .position(|r| r.type_id == id)
                .unwrap_or(0);
            let count = self
                .catalog
                .records
                .iter()
                .filter(|r| r.type_id == id)
                .count();
            writeln!(
                out,
                "    DWORD {},{count}",
                if id >= self.catalog.indexed_types && !self.non_class_types[id] {
                    u32::MAX as usize
                } else {
                    start
                }
            )?;
        }
        for (i, name) in self.type_names.iter().enumerate() {
            writeln!(out, "ALIGN 2\nboom_ctor_type_name{i} LABEL WORD")?;
            if name.is_empty() {
                out.push_str("    WORD 0\n");
            } else {
                for chunk in name.chunks(16) {
                    writeln!(
                        out,
                        "    WORD {}",
                        chunk
                            .iter()
                            .map(|u| format!("0{u:04x}h"))
                            .collect::<Vec<_>>()
                            .join(",")
                    )?;
                }
            }
        }
        out.push_str("ALIGN 8\nboom_ctor_type_names LABEL BYTE\n");
        for (i, name) in self.type_names.iter().enumerate() {
            writeln!(
                out,
                "    QWORD OFFSET boom_ctor_type_name{i}\n    DWORD {},0",
                name.len()
            )?;
        }
        writeln!(
            out,
            "ALIGN 8\nboom_constructor_pool DWORD 052544343h,2\n    QWORD OFFSET boom_heap_ptr,OFFSET boom_mirror_pool,OFFSET boom_string_pool,OFFSET boom_runtime_type_map,OFFSET boom_constructor_vm_layout,OFFSET boom_ctor_records\n    DWORD {},{}\n    QWORD OFFSET boom_ctor_type_ranges,OFFSET boom_ctor_type_names,OFFSET boom_type_table,OFFSET boom_mirror_array_layout,OFFSET boom_t{},OFFSET boom_t{},OFFSET boom_ctor_boxes\n    DWORD {},{}\n    QWORD 0,0,0,0\n.code",
            self.catalog.records.len(),
            self.type_names.len(),
            self.catalog.constructor_type,
            self.catalog.class_type,
            self.message_offset,
            self.target_offset
        )?;
        for site in &self.sites {
            let id = site.binding.site;
            writeln!(out, ".const\nALIGN 8\nboom_ctor_access{id} LABEL BYTE")?;
            if site.access.is_empty() {
                out.push_str("    BYTE 0\n");
            } else {
                for c in site.access.chunks(32) {
                    writeln!(
                        out,
                        "    BYTE {}",
                        c.iter()
                            .map(|v| v.to_string())
                            .collect::<Vec<_>>()
                            .join(",")
                    )?;
                }
            }
            writeln!(
                out,
                "ALIGN 8\nboom_ctor_site{id} DWORD 050534343h,1\n    QWORD OFFSET boom_constructor_pool,OFFSET boom_ctor_access{id}\n    DWORD {},{}",
                site.binding.caller_type, site.binding.operation as u32
            )?;
        }
        out.push_str(
            ".code\nPUBLIC boom_get_constructor_box_layout\nboom_get_constructor_box_layout PROC\n",
        );
        for b in &self.catalog.boxes {
            writeln!(
                out,
                "    cmp ecx,{}\n    jne boom_ctor_box_next{}\n    lea rax,boom_ctor_box_layout{}\n    ret\nboom_ctor_box_next{}:",
                b.kind, b.kind, b.kind, b.kind
            )?;
        }
        out.push_str("    xor eax,eax\n    ret\nboom_get_constructor_box_layout ENDP\nPUBLIC boom_get_constructor_argument_layout\nboom_get_constructor_argument_layout PROC\n    lea rax,boom_ctor_argument_array_layout\n    ret\nboom_get_constructor_argument_layout ENDP\n");
        for c in &self.constructors {
            c.emit(out, true);
        }
        out.push_str(".code\nPUBLIC boom_get_constructor_pool\nboom_get_constructor_pool PROC\n    lea rax,boom_constructor_pool\n    ret\nboom_get_constructor_pool ENDP\nPUBLIC boom_get_constructor_vm_layout\nboom_get_constructor_vm_layout PROC\n    lea rax,boom_constructor_vm_layout\n    ret\nboom_get_constructor_vm_layout ENDP\n");
        Ok(())
    }
}
