//! Frozen Field identities. All lookup, token allocation and memory access run in MASM.
use super::{classfile::ClassFile, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, fmt::Write as _};
pub const OWNER: &str = "java/lang/reflect/Field";
pub const REFLECTION: &str = "jdk/internal/reflect/Reflection";
const FILTER_CLASS_SHA: &str = "367e5447826f325e7952543ecb11983c3314217126a6a46238421e241eed2f34";
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum Operation {
    Declared,
    Name,
    Type,
    Modifiers,
    DeclaringClass,
    UnsafeOffset,
    UnsafeBase,
    Equals,
    Hash,
    Synthetic,
    EnumConstant,
    RegisterFilter,
    ToString,
}
impl Operation {
    pub(super) fn resolve(o: &str, n: &str, d: &str) -> Option<Self> {
        if o == "java/lang/Class"
            && n == "getDeclaredField"
            && d == "(Ljava/lang/String;)Ljava/lang/reflect/Field;"
        {
            return Some(Self::Declared);
        }
        if o != OWNER {
            return None;
        }
        Some(match (n, d) {
            ("getName", "()Ljava/lang/String;") => Self::Name,
            ("getType", "()Ljava/lang/Class;") => Self::Type,
            ("getModifiers", "()I") => Self::Modifiers,
            ("getDeclaringClass", "()Ljava/lang/Class;") => Self::DeclaringClass,
            ("equals", "(Ljava/lang/Object;)Z") => Self::Equals,
            ("hashCode", "()I") => Self::Hash,
            ("toString", "()Ljava/lang/String;") => Self::ToString,
            ("isSynthetic", "()Z") => Self::Synthetic,
            ("isEnumConstant", "()Z") => Self::EnumConstant,
            _ => return None,
        })
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub operation: Operation,
    pub declaration: ClassOrigin,
    pub code_sha256: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Record {
    pub owner: usize,
    pub slot: usize,
    pub modifiers: u16,
    pub name: String,
    pub descriptor: String,
    pub field_type: usize,
    pub width: usize,
    pub class_state: Option<usize>,
    pub filtered: bool,
    pub name_literal: usize,
    pub owner_name_hash: u32,
    pub display_literal: usize,
    pub instance_map: Option<usize>,
    pub source: ClassOrigin,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub field_type: usize,
    pub indexed_types: usize,
    pub records: Vec<Record>,
    pub bindings: Vec<Binding>,
    pub registrations: Vec<super::field_filters::Binding>,
    pub bootstrap_registered_types: Vec<usize>,
    pub message_offset: usize,
    pub field_origin: ClassOrigin,
    pub filter_origin: ClassOrigin,
    pub native_source_sha256: String,
    pub vm_owned_field_layout: bool,
    pub original_class_and_field_api_bodies_executed: bool,
    pub class_initialization_triggered_by_lookup: bool,
    pub dynamic_filter_registration_supported: bool,
    pub constant_set_filter_registration_supported: bool,
    pub first_lookup_filter_snapshot: bool,
    pub soft_reference_cache_clearing_implemented: bool,
    pub value_access_complete: bool,
    pub generic_reflection_complete: bool,
}
fn origin(registry: &types::Registry<'_>, id: usize) -> Result<ClassOrigin> {
    let types::Type::Class { origin, .. } = &registry.types[id] else {
        anyhow::bail!("Field metadata requires a class")
    };
    Ok(origin.as_ref().clone())
}
pub(super) fn register(registry: &mut types::Registry<'_>) -> Result<usize> {
    let id = registry.class("bootstrap", OWNER)?;
    let o = origin(registry, id)?;
    ensure!(
        o.source_id == "jdk:java.base"
            && o.generated.is_none()
            && registry.definition(id).unwrap().access & 0x611 == 0x11,
        "Field must be the original final java.base class"
    );
    let r = registry.class("bootstrap", REFLECTION)?;
    let o = origin(registry, r)?;
    ensure!(
        o.source_id == "jdk:java.base" && o.generated.is_none() && o.sha256 == FILTER_CLASS_SHA,
        "JDK Field filter policy needs review for this Reflection source"
    );
    Ok(id)
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    constant: u16,
    operation: Operation,
) -> Result<Binding> {
    let (o, n, d) = caller.method_reference(constant)?;
    ensure!(
        Operation::resolve(&o, &n, &d) == Some(operation),
        "Reflected Field callsite changed"
    );
    let id = registry.class("bootstrap", &o)?;
    let declaration = origin(registry, id)?;
    ensure!(
        declaration.source_id == "jdk:java.base" && declaration.generated.is_none(),
        "Field API requires original bootstrap source"
    );
    let m = registry.definition(id).unwrap().method(&n, Some(&d))?;
    let code = m
        .code
        .as_ref()
        .context("Field API must retain original Java Code")?;
    ensure!(
        m.access & 0x109 == 1,
        "Field API must remain public instance Java Code"
    );
    Ok(Binding {
        caller: source.clone(),
        constant,
        operation,
        declaration,
        code_sha256: files::digest_bytes(&code.bytes).sha256,
    })
}
fn filtered(owner: &str, name: &str) -> bool {
    match owner {
        REFLECTION
        | "java/lang/reflect/AccessibleObject"
        | "java/lang/ClassLoader"
        | "java/lang/reflect/Constructor"
        | OWNER
        | "java/lang/reflect/Method"
        | "java/lang/Module" => true,
        "java/lang/Class" => matches!(name, "classLoader" | "classData"),
        "java/lang/System" => name == "security",
        _ => false,
    }
}
fn hash(s: &str) -> u32 {
    s.encode_utf16()
        .fold(0u32, |a, b| a.wrapping_mul(31).wrapping_add(u32::from(b)))
}
impl Plan {
    pub(super) fn prepare_instance_maps(
        &mut self,
        registry: &mut types::Registry<'_>,
        classes: &[ClassFile],
        loaders: &[String],
        layouts: &[super::program::ProgramObjectLayout],
        first_id: usize,
    ) -> Result<Vec<super::field_maps::Map>> {
        self.abi = 5;
        let mut class_ids = BTreeMap::new();
        let mut type_ids = Vec::new();
        for (ci, class) in classes.iter().enumerate() {
            let id = registry.class(&loaders[ci], &class.name)?;
            type_ids.push(id);
            class_ids.insert(id, ci);
        }
        let indexes: BTreeMap<_, _> = self
            .records
            .iter()
            .enumerate()
            .filter(|(_, r)| r.modifiers & 8 == 0 && r.descriptor.len() == 1)
            .map(|(index, r)| ((r.owner, r.slot), index))
            .collect();
        let mut rows: BTreeMap<usize, Vec<super::field_maps::Row>> = BTreeMap::new();
        let mut declaring_ids = BTreeMap::new();
        for layout in layouts {
            if matches!(
                layout.class_name.as_str(),
                "java/lang/String"
                    | "java/lang/Class"
                    | "java/lang/ModuleLayer"
                    | OWNER
                    | super::reflect_constructors::OWNER
            ) {
                continue;
            }
            let receiver = type_ids[layout.class_id];
            for field in &layout.layout.fields {
                let (Some(owner), Some(slot)) = (&field.declaring_class, field.declaring_field)
                else {
                    continue;
                };
                let key = (loaders[layout.class_id].clone(), owner.clone());
                let declaring = if let Some(&id) = declaring_ids.get(&key) {
                    id
                } else {
                    let id = registry.class(&key.0, &key.1)?;
                    declaring_ids.insert(key, id);
                    id
                };
                let Some(&index) = indexes.get(&(declaring, slot)) else {
                    continue;
                };
                let record = &self.records[index];
                ensure!(
                    field.descriptor == record.descriptor
                        && field.storage_bytes == Some(record.width)
                        && field.offset >= layout.layout.reference_prefix_fields * 8
                        && field
                            .offset
                            .checked_add(record.width)
                            .is_some_and(|end| end <= layout.layout.payload_bytes),
                    "Unsafe instance field disagrees with its compact physical layout"
                );
                rows.entry(index).or_default().push(super::field_maps::Row {
                    receiver_class: layout.class_id,
                    receiver_type: receiver,
                    offset: field.offset,
                });
            }
        }
        ensure!(
            rows.values().map(Vec::len).sum::<usize>() <= 262144,
            "Unsafe field receiver maps exceed their metadata budget"
        );
        let mut maps = Vec::new();
        for (index, mut receivers) in rows {
            receivers.sort_by_key(|row| row.receiver_type);
            receivers.dedup_by_key(|row| row.receiver_type);
            let record = &mut self.records[index];
            let id = first_id + maps.len();
            ensure!(
                id < 65536,
                "Unsafe field map count exceeds the module budget"
            );
            record.instance_map = Some(id);
            maps.push(super::field_maps::Map {
                id,
                declaring_class: *class_ids
                    .get(&record.owner)
                    .context("Missing executable declaring class for Unsafe field map")?,
                field_index: record.slot,
                receiver_constraint: record.owner,
                rows: receivers,
            });
        }
        Ok(maps)
    }
    pub(super) fn prepare(
        registry: &mut types::Registry<'_>,
        names: &BTreeMap<(String, String, String), usize>,
        bindings: Vec<Binding>,
        registrations: Vec<super::field_filters::Binding>,
        mut literal: impl FnMut(Vec<u16>) -> Result<usize>,
    ) -> Result<Self> {
        let field_type = register(registry)?;
        let field_origin = origin(registry, field_type)?;
        let reflection = registry.class("bootstrap", REFLECTION)?;
        let filter_origin = origin(registry, reflection)?;
        let indexed_types = registry.types.len();
        let mut records = vec![];
        for id in 0..indexed_types {
            let types::Type::Class { key, origin, .. } = &registry.types[id] else {
                continue;
            };
            let key = key.clone();
            let source = origin.as_ref().clone();
            let fs = registry
                .definition(id)
                .context("Missing reflected class definition")?
                .field_info
                .clone();
            for (slot, f) in fs.into_iter().enumerate() {
                let field_type = registry.field(&key.loader, &f.descriptor)?;
                let width = match f.descriptor.as_bytes()[0] {
                    b'B' | b'Z' => 1,
                    b'C' | b'S' => 2,
                    b'I' | b'F' => 4,
                    _ => 8,
                };
                let name_literal = literal(f.name.encode_utf16().collect())?;
                let modifiers = super::dispatch::modifier_text(f.access);
                let display = format!(
                    "{}{} {}.{}",
                    if f.access == 0 {
                        String::new()
                    } else {
                        format!("{modifiers} ")
                    },
                    super::dispatch::type_name(&registry.types, field_type),
                    key.name.replace('/', "."),
                    f.name
                );
                let display_literal = literal(display.encode_utf16().collect())?;
                records.push(Record {
                    owner: id,
                    slot,
                    modifiers: f.access,
                    field_type,
                    width,
                    class_state: names
                        .get(&(key.loader.clone(), key.name.clone(), source.sha256.clone()))
                        .copied()
                        .filter(|_| f.access & 8 != 0),
                    filtered: filtered(&key.name, &f.name),
                    name_literal,
                    owner_name_hash: hash(&key.name.replace('/', ".")),
                    display_literal,
                    instance_map: None,
                    name: f.name,
                    descriptor: f.descriptor,
                    source: source.clone(),
                });
            }
        }
        ensure!(
            records.len() <= 262144,
            "Field metadata exceeds runtime row budget"
        );
        let bootstrap_registered_types = registry
            .types
            .iter()
            .enumerate()
            .filter_map(|(id, t)| match t {
                types::Type::Class { key, .. }
                    if key.loader == "bootstrap"
                        && matches!(
                            key.name.as_str(),
                            REFLECTION
                                | "java/lang/reflect/AccessibleObject"
                                | "java/lang/Class"
                                | "java/lang/ClassLoader"
                                | "java/lang/reflect/Constructor"
                                | OWNER
                                | "java/lang/reflect/Method"
                                | "java/lang/Module"
                                | "java/lang/System"
                        ) =>
                {
                    Some(id)
                }
                _ => None,
            })
            .collect();
        ensure!(
            registrations
                .iter()
                .all(|r| r.containing_type < indexed_types),
            "Field filter target metadata was not indexed"
        );
        Ok(Self {
            abi: 4,
            field_type,
            indexed_types,
            records,
            bindings,
            registrations,
            bootstrap_registered_types,
            message_offset: 0,
            field_origin,
            filter_origin,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/reflect_fields.asm"
            ))
            .sha256,
            vm_owned_field_layout: true,
            original_class_and_field_api_bodies_executed: false,
            class_initialization_triggered_by_lookup: false,
            dynamic_filter_registration_supported: false,
            constant_set_filter_registration_supported: true,
            first_lookup_filter_snapshot: true,
            soft_reference_cache_clearing_implemented: false,
            value_access_complete: false,
            generic_reflection_complete: false,
        })
    }
    pub(super) fn emit(&self, out: &mut String, type_count: usize) -> Result<()> {
        out.push_str("EXTERN boom_field_service:PROC\nEXTERN boom_field_static_address:PROC\nEXTERN boom_field_instance_address:PROC\n.const\nALIGN 8\nboom_field_layout DWORD 04F424A43h,1\n    QWORD 32\n    DWORD 1,4\n");
        for (i, r) in self.records.iter().enumerate() {
            write!(out, "boom_field_name{i} WORD ")?;
            let units = r.name.encode_utf16().collect::<Vec<_>>();
            writeln!(
                out,
                "{}",
                if units.is_empty() {
                    "0".into()
                } else {
                    units
                        .iter()
                        .map(u16::to_string)
                        .collect::<Vec<_>>()
                        .join(",")
                }
            )?;
        }
        out.push_str("ALIGN 8\nboom_field_rows LABEL BYTE\n");
        for (i, r) in self.records.iter().enumerate() {
            let cell = if r.modifiers & 8 != 0 {
                r.class_state
                    .map_or("0".into(), |c| format!("OFFSET boom_s{c}_{}", r.slot))
            } else {
                r.instance_map
                    .map_or("0".into(), |id| format!("OFFSET boom_field_map{id}"))
            };
            writeln!(
                out,
                "    DWORD {},{},{},{}\n    DWORD {},{}\n    DWORD {},0\n    QWORD {cell},OFFSET boom_field_name{i}\n    DWORD {},{}, {},{}",
                r.owner,
                r.slot,
                r.modifiers,
                r.width,
                r.field_type,
                r.name_literal,
                r.display_literal,
                r.name.encode_utf16().count(),
                hash(&r.name),
                u32::from(r.filtered),
                r.owner_name_hash
            )?;
        }
        out.push_str("boom_field_ranges LABEL DWORD\n");
        for id in 0..type_count {
            let start = self.records.iter().position(|r| r.owner == id).unwrap_or(0);
            let count = self.records.iter().filter(|r| r.owner == id).count();
            writeln!(
                out,
                "    DWORD {},{count}",
                if id < self.indexed_types {
                    start
                } else {
                    u32::MAX as usize
                }
            )?;
        }
        for (i, r) in self.registrations.iter().enumerate() {
            for (k, name) in r.proof.names.iter().enumerate() {
                writeln!(
                    out,
                    "boom_field_filter_name{i}_{k} WORD {}",
                    if name.is_empty() {
                        "0".into()
                    } else {
                        name.iter()
                            .map(u16::to_string)
                            .collect::<Vec<_>>()
                            .join(",")
                    }
                )?;
            }
            writeln!(out, "ALIGN 8\nboom_field_filter_names{i} LABEL BYTE")?;
            for (k, name) in r.proof.names.iter().enumerate() {
                writeln!(
                    out,
                    "    QWORD OFFSET boom_field_filter_name{i}_{k}\n    DWORD {},0",
                    name.len()
                )?;
            }
            writeln!(out, "boom_field_filter_rows{i} LABEL DWORD")?;
            let wildcard = r.proof.names.iter().any(|n| n == &vec![42]);
            let rows = self
                .records
                .iter()
                .enumerate()
                .filter(|(_, f)| {
                    f.owner == r.containing_type
                        && (wildcard
                            || r.proof
                                .names
                                .iter()
                                .any(|n| f.name.encode_utf16().eq(n.iter().copied())))
                })
                .map(|(j, _)| j)
                .collect::<Vec<_>>();
            if rows.is_empty() {
                out.push_str("    DWORD 0\n");
            } else {
                for row in rows {
                    writeln!(out, "    DWORD {row}")?;
                }
            }
        }
        out.push_str("ALIGN 8\nboom_field_registrations LABEL BYTE\n");
        for (i, r) in self.registrations.iter().enumerate() {
            let wildcard = r.proof.names.iter().any(|n| n == &vec![42]);
            let rows = self
                .records
                .iter()
                .filter(|f| {
                    f.owner == r.containing_type
                        && (wildcard
                            || r.proof
                                .names
                                .iter()
                                .any(|n| f.name.encode_utf16().eq(n.iter().copied())))
                })
                .count();
            writeln!(
                out,
                "    DWORD {},{},{},2\n    QWORD OFFSET boom_layout{}\n    DWORD {},{}\n    QWORD OFFSET boom_field_filter_names{i},OFFSET boom_field_filter_rows{i}\n    DWORD {rows},0\n    QWORD OFFSET boom_t{}",
                r.method_id,
                r.proof.pc,
                r.containing_type,
                r.set_class_id,
                r.offsets[0],
                r.offsets[1],
                r.set_type
            )?;
        }
        out.push_str(".data\nALIGN 8\nboom_field_filter_cells LABEL DWORD\n");
        for r in &self.records {
            writeln!(out, "    DWORD {}", u32::from(r.filtered))?;
        }
        out.push_str("boom_field_registered_types LABEL DWORD\n");
        for id in 0..type_count {
            writeln!(
                out,
                "    DWORD {}",
                u32::from(self.bootstrap_registered_types.contains(&id))
            )?;
        }
        out.push_str("boom_field_cached_filters LABEL DWORD\n");
        for _ in &self.records {
            out.push_str("    DWORD 0\n");
        }
        out.push_str("boom_field_cache_states LABEL DWORD\n");
        for _ in 0..type_count {
            out.push_str("    DWORD 0\n");
        }
        writeln!(
            out,
            ".data\nALIGN 8\nboom_field_pool DWORD 053444C46h,{}\n    QWORD OFFSET boom_heap_ptr,OFFSET boom_mirror_pool,OFFSET boom_string_pool,OFFSET boom_runtime_type_map,OFFSET boom_field_layout,OFFSET boom_field_rows\n    DWORD {},{}\n    QWORD OFFSET boom_type_table,OFFSET boom_field_ranges,OFFSET boom_t{}\n    DWORD {},0\n    QWORD OFFSET boom_field_filter_cells,OFFSET boom_field_registered_types,OFFSET boom_field_registrations\n    DWORD {},0\n    QWORD OFFSET boom_field_cached_filters,OFFSET boom_field_cache_states\n.code\nPUBLIC boom_get_field_pool\nboom_get_field_pool PROC\n    lea rax,boom_field_pool\n    ret\nboom_get_field_pool ENDP",
            self.abi,
            self.records.len(),
            type_count,
            self.field_type,
            self.message_offset,
            self.registrations.len()
        )?;
        Ok(())
    }
    pub(super) fn runtime_binding(&self) -> super::runtime_types::Binding {
        super::runtime_types::Binding {
            tag: "OFFSET boom_field_layout".into(),
            type_id: self.field_type,
            kind: 0,
            payload_bytes: 32,
            references: 1,
            element_shift: 0,
        }
    }
}
