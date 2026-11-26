//! Original java.lang.reflect.Array allocation bindings and frozen array types.
//! Runtime allocation, validation and multidimensional recursion execute MASM.
use super::{classfile::ClassFile, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/lang/reflect/Array";
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum Operation {
    New = 0,
    Multi = 1,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, desc: &str) -> Option<Self> {
        if owner != OWNER {
            return None;
        }
        match (name, desc) {
            ("newArray", "(Ljava/lang/Class;I)Ljava/lang/Object;") => Some(Self::New),
            ("multiNewArray", "(Ljava/lang/Class;[I)Ljava/lang/Object;") => Some(Self::Multi),
            _ => None,
        }
    }
    pub(super) fn descriptor(self) -> &'static str {
        match self {
            Self::New => "(Ljava/lang/Class;I)Ljava/lang/Object;",
            Self::Multi => "(Ljava/lang/Class;[I)Ljava/lang/Object;",
        }
    }
    fn name(self) -> &'static str {
        match self {
            Self::New => "newArray",
            Self::Multi => "multiNewArray",
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub operation: Operation,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Row {
    pub array_type: Option<usize>,
    pub component_rank: u32,
    pub void_component: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub class_id: usize,
    pub bindings: Vec<Binding>,
    pub prepared_component_types: usize,
    pub rows: Vec<Row>,
    pub native_source_sha256: String,
    pub allocator_source_sha256: String,
    pub dynamic_type_creation: bool,
    pub missing_array_metadata_is_an_error: bool,
    pub automatic_gc: bool,
}
fn rank(types: &[types::Type], mut id: usize) -> Result<u32> {
    let mut rank = 0;
    while let types::Type::Array { component } = types
        .get(id)
        .ok_or_else(|| anyhow::anyhow!("Missing reflection component type"))?
    {
        rank += 1;
        ensure!(rank <= 255, "Cyclic or excessive reflection array rank");
        id = *component;
    }
    Ok(rank)
}
impl Plan {
    pub(super) fn new(registry: &mut types::Registry<'_>, class_id: usize) -> Result<Self> {
        let id = registry.class("bootstrap", OWNER)?;
        let types::Type::Class { key, origin, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "Reflection arrays require original java.base Array"
        );
        let source = registry.definition(id).unwrap();
        for op in [Operation::New, Operation::Multi] {
            let m = source.method(op.name(), Some(op.descriptor()))?;
            ensure!(
                m.access == 0x10a && m.code.is_none(),
                "Reflection array native declaration changed"
            );
        }
        Ok(Self {
            abi: 1,
            origin: origin.as_ref().clone(),
            class_id,
            bindings: Vec::new(),
            prepared_component_types: 0,
            rows: Vec::new(),
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/reflection_arrays.asm"
            ))
            .sha256,
            allocator_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/typed_arrays.asm"
            ))
            .sha256,
            dynamic_type_creation: false,
            missing_array_metadata_is_an_error: true,
            automatic_gc: false,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
        op: Operation,
    ) -> Result<()> {
        let (o, n, d, i) = caller.static_method_reference(constant)?;
        ensure!(
            !i && Operation::resolve(&o, &n, &d) == Some(op)
                && caller.name == OWNER
                && source == &self.origin,
            "Reflection array allocation native is private to original Array source"
        );
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
            self.bindings.sort_by_key(|b| b.constant);
        }
        Ok(())
    }
    /// Prepare the next array type of each component in the linked graph. The
    /// existing frozen metadata ABI cannot create additional types at runtime.
    /// Never substitute Object[] when an exact array descriptor is unavailable.
    pub(super) fn prepare(&mut self, registry: &mut types::Registry<'_>) -> Result<Vec<usize>> {
        self.prepared_component_types = registry.types.len();
        let mut arrays = Vec::new();
        for id in 0..self.prepared_component_types {
            if matches!(
                registry.types[id],
                types::Type::Primitive {
                    value: types::Primitive::Void
                }
            ) || rank(&registry.types, id)? == 255
            {
                continue;
            }
            arrays.push(registry.array(id)?);
        }
        let mut next = vec![None; registry.types.len()];
        for (id, ty) in registry.types.iter().enumerate() {
            if let types::Type::Array { component } = ty {
                ensure!(
                    next[*component].replace(id).is_none(),
                    "Duplicate reflection array identity"
                );
            }
        }
        self.rows = registry
            .types
            .iter()
            .enumerate()
            .map(|(id, ty)| {
                Ok(Row {
                    array_type: next[id],
                    component_rank: rank(&registry.types, id)?,
                    void_component: matches!(
                        ty,
                        types::Type::Primitive {
                            value: types::Primitive::Void
                        }
                    ),
                })
            })
            .collect::<Result<_>>()?;
        ensure!(
            self.rows.len() <= 16384,
            "Reflection type table exceeds current metadata ABI"
        );
        Ok(arrays)
    }
    pub(super) fn emit(&self, out: &mut String) -> Result<()> {
        ensure!(
            !self.rows.is_empty(),
            "Reflection array table must be frozen"
        );
        out.push_str("EXTERN boom_reflect_array_allocate:PROC\n.const\nALIGN 8\nboom_reflect_array_rows LABEL BYTE\n");
        for row in &self.rows {
            let (ptr, id) = row.array_type.map_or(("0".into(), u32::MAX), |id| {
                (format!("OFFSET boom_t{id}"), id as u32)
            });
            out.push_str(&format!(
                "    QWORD {ptr}\n    DWORD {id},{}\n",
                if row.void_component {
                    u32::MAX
                } else {
                    row.component_rank
                }
            ));
        }
        out.push_str(&format!(".data\nALIGN 8\nboom_reflect_array_pool DWORD 050524152h,1\n    QWORD OFFSET boom_heap_ptr,OFFSET boom_mirror_pool,OFFSET boom_reflect_array_rows,OFFSET boom_runtime_type_map\n    DWORD {},0\n.code\nPUBLIC boom_get_reflect_array_pool\nboom_get_reflect_array_pool PROC\n    lea rax,boom_reflect_array_pool\n    ret\nboom_get_reflect_array_pool ENDP\n",self.rows.len()));
        Ok(())
    }
}
