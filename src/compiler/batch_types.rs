//! Nominal operand types and binding contracts for persistent IR code generation.
use super::{
    batch_catalog::{Catalog, Layout},
    classfile::{ClassFile, Method},
    hierarchy::{self, Member, Metadata},
    numeric::{self, ArrayKind, Signature, StaticLinker, SymbolicReference, Type},
    symbolic::{Constant, JavaType, MethodType},
};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
};

fn descriptor(ty: &JavaType) -> String {
    match ty {
        JavaType::Boolean => "Z".into(),
        JavaType::Byte => "B".into(),
        JavaType::Char => "C".into(),
        JavaType::Short => "S".into(),
        JavaType::Int => "I".into(),
        JavaType::Long => "J".into(),
        JavaType::Float => "F".into(),
        JavaType::Double => "D".into(),
        JavaType::Void => "V".into(),
        JavaType::Object(name) => format!("L{name};"),
        JavaType::Array {
            dimensions,
            element,
        } => format!(
            "{}{}",
            "[".repeat(usize::from(*dimensions)),
            descriptor(element)
        ),
    }
}
fn primitive_array(ty: &JavaType) -> Option<ArrayKind> {
    Some(match ty {
        JavaType::Boolean => ArrayKind::Boolean,
        JavaType::Byte => ArrayKind::Byte,
        JavaType::Char => ArrayKind::Char,
        JavaType::Short => ArrayKind::Short,
        JavaType::Int => ArrayKind::Int,
        JavaType::Long => ArrayKind::Long,
        JavaType::Float => ArrayKind::Float,
        JavaType::Double => ArrayKind::Double,
        _ => return None,
    })
}
fn type_key(ty: Type) -> (u8, usize) {
    match ty {
        Type::LinkedObject(id) => (0, id),
        Type::MetadataReference(id) => (1, id),
        Type::Array(kind) => (2, kind as usize),
        Type::ReferenceJoin(id) => (3, id),
        Type::Null => (4, 0),
        _ => (255, 0),
    }
}
#[derive(Debug, Serialize)]
pub struct Array {
    pub id: usize,
    pub defining_loader: String,
    pub descriptor: String,
    pub stack_type: Type,
    pub component: Type,
}
pub struct Universe {
    pub arrays: Vec<Array>,
    pub field_ids: Vec<usize>,
    array_index: BTreeMap<(String, String), usize>,
    class_count: usize,
}
impl Universe {
    pub fn new(catalog: &Catalog) -> Result<Self> {
        let mut descriptors = BTreeSet::new();
        for ty in [
            JavaType::Boolean,
            JavaType::Byte,
            JavaType::Char,
            JavaType::Short,
            JavaType::Int,
            JavaType::Long,
            JavaType::Float,
            JavaType::Double,
        ] {
            descriptors.insert(("bootstrap".into(), format!("[{}", descriptor(&ty))));
        }
        for node in &catalog.nodes {
            if node.access & 0x8000 == 0 {
                descriptors.insert((node.key.loader.clone(), format!("[L{};", node.key.name)));
            }
        }
        fn collect(
            catalog: &Catalog,
            loader: &str,
            ty: &JavaType,
            out: &mut BTreeSet<(String, String)>,
        ) {
            if let JavaType::Array {
                dimensions,
                element,
            } = ty
            {
                let defining = if let JavaType::Object(name) = element.as_ref() {
                    let Some(id) = catalog.find(loader, name) else {
                        return;
                    };
                    catalog.nodes[id].key.loader.as_str()
                } else {
                    "bootstrap"
                };
                for n in 1..=usize::from(*dimensions).saturating_add(1).min(255) {
                    out.insert((
                        defining.into(),
                        format!("{}{}", "[".repeat(n), descriptor(element)),
                    ));
                }
            }
        }
        for (loader, text) in &catalog.type_mentions {
            if text.starts_with('(') {
                if let Ok(method) = MethodType::parse(text) {
                    for ty in method
                        .parameters
                        .iter()
                        .chain(std::iter::once(&method.result))
                    {
                        collect(catalog, loader, ty, &mut descriptors);
                    }
                }
            } else if let Ok(ty) = JavaType::field(text) {
                collect(catalog, loader, &ty, &mut descriptors);
            }
        }
        let class_count = catalog.nodes.len();
        let array_index = descriptors
            .iter()
            .enumerate()
            .map(|(i, key)| (key.clone(), class_count + i))
            .collect::<BTreeMap<_, _>>();
        let mut universe = Self {
            arrays: vec![],
            field_ids: vec![],
            array_index,
            class_count,
        };
        for (index, (loader, text)) in descriptors.into_iter().enumerate() {
            let JavaType::Array {
                dimensions,
                element,
            } = JavaType::field(&text)?
            else {
                unreachable!()
            };
            let component = if dimensions == 1 {
                universe.ty_unchecked(catalog, &loader, &element)?
            } else {
                universe.ty_unchecked(
                    catalog,
                    &loader,
                    &JavaType::Array {
                        dimensions: dimensions - 1,
                        element: element.clone(),
                    },
                )?
            };
            let stack_type = if dimensions == 1 {
                primitive_array(&element)
                    .map(Type::Array)
                    .unwrap_or(Type::MetadataReference(class_count + index))
            } else {
                Type::MetadataReference(class_count + index)
            };
            universe.arrays.push(Array {
                id: class_count + index,
                defining_loader: loader,
                descriptor: text,
                stack_type,
                component,
            });
        }
        let mut cursor = 0;
        for node in &catalog.nodes {
            universe.field_ids.push(cursor);
            cursor += node.fields.len();
        }
        Ok(universe)
    }
    fn canonical_array_key(
        &self,
        catalog: &Catalog,
        loader: &str,
        ty: &JavaType,
    ) -> Result<(String, String)> {
        let JavaType::Array { element, .. } = ty else {
            bail!("Expected array type")
        };
        let loader = if let JavaType::Object(name) = element.as_ref() {
            catalog.nodes[catalog
                .find(loader, name)
                .with_context(|| format!("Definition required: {name}"))?]
            .key
            .loader
            .as_str()
        } else {
            "bootstrap"
        };
        Ok((loader.into(), descriptor(ty)))
    }
    fn ty_unchecked(&self, catalog: &Catalog, loader: &str, ty: &JavaType) -> Result<Type> {
        Ok(match ty {
            JavaType::Boolean
            | JavaType::Byte
            | JavaType::Char
            | JavaType::Short
            | JavaType::Int => Type::I32,
            JavaType::Long => Type::I64,
            JavaType::Float => Type::F32,
            JavaType::Double => Type::F64,
            JavaType::Void => Type::Void,
            JavaType::Object(name) => Type::LinkedObject(
                catalog
                    .find(loader, name)
                    .with_context(|| format!("Definition required: {name}"))?,
            ),
            JavaType::Array {
                dimensions,
                element,
            } => {
                if *dimensions == 1
                    && let Some(kind) = primitive_array(element)
                {
                    return Ok(Type::Array(kind));
                }
                Type::MetadataReference(
                    *self
                        .array_index
                        .get(&self.canonical_array_key(catalog, loader, ty)?)
                        .context("Array metadata definition required")?,
                )
            }
        })
    }
    pub fn ty(&self, catalog: &Catalog, loader: &str, ty: &JavaType) -> Result<Type> {
        match ty {
            JavaType::Object(name) => {
                catalog.lookup(loader, name)?;
            }
            JavaType::Array { element, .. } => {
                if let JavaType::Object(name) = element.as_ref() {
                    catalog.lookup(loader, name)?;
                }
            }
            _ => {}
        }
        self.ty_unchecked(catalog, loader, ty)
    }
    pub fn method(&self, catalog: &Catalog, loader: &str, text: &str) -> Result<Signature> {
        let method = MethodType::parse(text)?;
        Ok(Signature {
            arguments: method
                .parameters
                .iter()
                .map(|ty| self.ty(catalog, loader, ty))
                .collect::<Result<_>>()?,
            result: self.ty(catalog, loader, &method.result)?,
        })
    }
    pub fn array(&self, id: usize) -> Result<&Array> {
        self.arrays
            .get(
                id.checked_sub(self.class_count)
                    .context("Class ID is not an array ID")?,
            )
            .context("Invalid array identity")
    }
    pub fn array_id(&self, catalog: &Catalog, loader: &str, ty: &JavaType) -> Result<usize> {
        self.array_index
            .get(&self.canonical_array_key(catalog, loader, ty)?)
            .copied()
            .context("Array metadata definition required")
    }
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VirtualCall {
    pub symbolic_owner: usize,
    pub receiver_constraint: usize,
    pub resolved_owner: usize,
    pub resolved_index: usize,
    pub interface: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub label: String,
    pub kind: String,
    pub caller_class: usize,
    pub caller_method: usize,
    pub constant: u16,
    pub opcode: u8,
    pub resolved_method: Option<usize>,
    pub descriptor: String,
    pub implemented: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub dispatch: Option<VirtualCall>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub protocol: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub array_type: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub literal_type: Option<usize>,
}
pub struct Environment<'a> {
    pub catalog: &'a Catalog,
    pub universe: &'a Universe,
    pub layouts: &'a [Layout],
    pub caller: usize,
    pub method_index: usize,
    pub bindings: RefCell<Vec<Binding>>,
    joins: RefCell<Vec<Vec<Type>>>,
}
impl<'a> Environment<'a> {
    pub fn new(
        catalog: &'a Catalog,
        universe: &'a Universe,
        layouts: &'a [Layout],
        caller: usize,
        method_index: usize,
    ) -> Self {
        Self {
            catalog,
            universe,
            layouts,
            caller,
            method_index,
            bindings: RefCell::new(vec![]),
            joins: RefCell::new(vec![]),
        }
    }
    fn loader(&self) -> &str {
        &self.catalog.nodes[self.caller].key.loader
    }
    fn ty(&self, text: &str) -> Result<Type> {
        self.universe
            .ty(self.catalog, self.loader(), &JavaType::field(text)?)
    }
    fn signature_of(&self, text: &str) -> Result<Signature> {
        self.universe.method(self.catalog, self.loader(), text)
    }
    fn binding(
        &self,
        cp: u16,
        opcode: u8,
        kind: &str,
        descriptor: &str,
        resolved_method: Option<usize>,
        label: String,
    ) -> String {
        self.bindings.borrow_mut().push(Binding {
            label: label.clone(),
            kind: kind.into(),
            caller_class: self.caller,
            caller_method: self.catalog.nodes[self.caller].method_ids[self.method_index],
            constant: cp,
            opcode,
            resolved_method,
            descriptor: descriptor.into(),
            implemented: false,
            dispatch: None,
            protocol: None,
            array_type: None,
            literal_type: None,
        });
        label
    }
    fn component(&self, ty: Type) -> Result<Option<Type>> {
        match ty {
            Type::MetadataReference(id) => Ok(Some(self.universe.array(id)?.component)),
            Type::Array(kind) => Ok(Some(match kind {
                ArrayKind::Long => Type::I64,
                ArrayKind::Float => Type::F32,
                ArrayKind::Double => Type::F64,
                _ => Type::I32,
            })),
            Type::ReferenceJoin(id) => {
                let values = self
                    .joins
                    .borrow()
                    .get(id)
                    .context("Invalid reference join")?
                    .clone();
                let mut result = None;
                for value in values {
                    let Some(component) = self.component(value)? else {
                        return Ok(None);
                    };
                    result = Some(if let Some(previous) = result {
                        self.join(previous, component)?
                            .context("Array components have no common type")?
                    } else {
                        component
                    });
                }
                Ok(result)
            }
            _ => Ok(None),
        }
    }
    fn assign(&self, from: Type, to: Type) -> Result<bool> {
        self.assignment(from, to, false)
    }
    fn verification_assign(&self, from: Type, to: Type) -> Result<bool> {
        self.assignment(from, to, true)
    }
    fn assignment(&self, from: Type, to: Type, interface_verification: bool) -> Result<bool> {
        if from == to {
            return Ok(true);
        }
        if from == Type::Null && to.is_reference() {
            return Ok(true);
        }
        if to == Type::AnyRef {
            return Ok(from.is_reference());
        }
        if let Type::ReferenceJoin(id) = from {
            let values = self
                .joins
                .borrow()
                .get(id)
                .context("Invalid reference join")?
                .clone();
            for value in values {
                if !self.assignment(value, to, interface_verification)? {
                    return Ok(false);
                }
            }
            return Ok(true);
        }
        if let Type::ReferenceJoin(id) = to {
            let values = self
                .joins
                .borrow()
                .get(id)
                .context("Invalid reference join")?
                .clone();
            for value in values {
                if self.assignment(from, value, interface_verification)? {
                    return Ok(true);
                }
            }
            return Ok(false);
        }
        match (from, to) {
            (Type::LinkedObject(a), Type::LinkedObject(b)) => {
                self.catalog.class_view(a)?;
                self.catalog.class_view(b)?;
                // Operand verification uses JVMS 4.10.1.2, which treats an
                // interface destination like Object (also recursively in arrays).
                // Runtime casts/dispatch must still use the nominal hierarchy.
                Ok(
                    (interface_verification && self.catalog.nodes[b].access & 0x200 != 0)
                        || Metadata::assignable(self.catalog, a, b),
                )
            }
            (Type::Array(_) | Type::MetadataReference(_), Type::LinkedObject(id)) => {
                let key = self.catalog.key(id)?;
                Ok(key.loader == "bootstrap"
                    && matches!(
                        key.name.as_str(),
                        "java/lang/Object" | "java/lang/Cloneable" | "java/io/Serializable"
                    ))
            }
            (Type::MetadataReference(_), Type::MetadataReference(_)) => {
                let a = self.component(from)?.unwrap();
                let b = self.component(to)?.unwrap();
                Ok(a.is_reference()
                    && b.is_reference()
                    && self.assignment(a, b, interface_verification)?)
            }
            _ => Ok(false),
        }
    }
    fn join(&self, left: Type, right: Type) -> Result<Option<Type>> {
        if left == right {
            return Ok(Some(left));
        }
        let left_to_right = self.assign(left, right)?;
        let right_to_left = self.assign(right, left)?;
        if left_to_right || right_to_left {
            // Equivalent unions must not oscillate between identities in loops.
            return Ok(Some(if left_to_right && right_to_left {
                if type_key(left) <= type_key(right) {
                    left
                } else {
                    right
                }
            } else if left_to_right {
                right
            } else {
                left
            }));
        }
        if !left.is_reference() || !right.is_reference() {
            return Ok(None);
        }
        let mut values = vec![];
        for ty in [left, right] {
            if let Type::ReferenceJoin(id) = ty {
                values.extend(
                    self.joins
                        .borrow()
                        .get(id)
                        .context("Invalid reference join")?
                        .iter()
                        .copied(),
                )
            } else {
                values.push(ty)
            }
        }
        values.sort_by_key(|ty| type_key(*ty));
        values.dedup();
        ensure!(values.len() <= 4096, "Reference join exceeds budget");
        let mut normalized = vec![];
        for &value in &values {
            let mut covered = false;
            for &other in &values {
                if value != other && self.assign(value, other)? {
                    covered = true;
                    break;
                }
            }
            if !covered {
                normalized.push(value);
            }
        }
        let values = normalized;
        let mut joins = self.joins.borrow_mut();
        let id = if let Some(id) = joins.iter().position(|v| *v == values) {
            id
        } else {
            let id = joins.len();
            joins.push(values);
            id
        };
        Ok(Some(Type::ReferenceJoin(id)))
    }
    fn field(
        &self,
        owner: &str,
        name: &str,
        descriptor: &str,
        opcode: u8,
    ) -> Result<SymbolicReference> {
        let symbolic_owner = self.catalog.lookup(self.loader(), owner)?;
        let member = hierarchy::resolve_field(self.catalog, symbolic_owner, name, descriptor)?;
        let protected = self
            .catalog
            .accessible(self.caller, symbolic_owner, &member)?;
        let is_static = opcode <= 0xb3;
        ensure!(
            (member.access & 8 != 0) == is_static,
            "Field static/instance kind mismatch"
        );
        if matches!(opcode, 0xb3 | 0xb5) && member.access & 0x10 != 0 {
            let method = &self.catalog.nodes[self.caller].methods[self.method_index];
            ensure!(
                member.owner == self.caller
                    && method.name == if is_static { "<clinit>" } else { "<init>" },
                "Final field store requires its declaring initializer"
            );
        }
        let ty = self.ty(descriptor)?;
        let narrow = match descriptor {
            "Z" => b'Z',
            "B" => b'B',
            "C" => b'C',
            "S" => b'S',
            _ => 0,
        };
        if is_static {
            Ok(SymbolicReference::StaticField(numeric::LinkedField {
                owner: member.owner,
                index: member.index,
                ty,
                access: member.access,
                narrow,
            }))
        } else {
            let layout = self.layouts[member.owner]
                .candidate
                .as_ref()
                .context("Physical field layout requires resolution")?;
            let slot = layout
                .fields
                .iter()
                .find(|f| f.member.owner == member.owner && f.member.index == member.index)
                .context("Missing declared physical field")?;
            Ok(SymbolicReference::InstanceField(
                numeric::LinkedInstanceField {
                    owner: member.owner,
                    index: member.index,
                    offset: slot.offset,
                    ty,
                    access: member.access,
                    narrow,
                    receiver: Type::LinkedObject(protected.unwrap_or(symbolic_owner)),
                    mapping: Some(self.universe.field_ids[member.owner] + member.index),
                    storage_bytes: slot.storage_bytes,
                },
            ))
        }
    }
    fn call(
        &self,
        owner: &str,
        name: &str,
        descriptor: &str,
        interface: bool,
        cp: u16,
        opcode: u8,
    ) -> Result<SymbolicReference> {
        let is_static = opcode == 0xb8;
        let array_owner = owner.starts_with('[');
        let symbolic_owner = if array_owner {
            self.catalog.root_object()?
        } else {
            self.catalog.lookup(self.loader(), owner)?
        };
        let mut signature = self.signature_of(descriptor)?;
        if array_owner && name == "clone" {
            ensure!(
                opcode == 0xb6 && descriptor == "()Ljava/lang/Object;",
                "Invalid array clone invocation"
            );
            signature.arguments.insert(0, self.ty(owner)?);
            let label = self.binding(
                cp,
                opcode,
                "array_clone",
                descriptor,
                None,
                format!("boom_batch_call_{}_{}_{}", self.caller, cp, opcode),
            );
            self.bindings.borrow_mut().last_mut().unwrap().array_type = Some(
                self.universe
                    .array_id(self.catalog, self.loader(), &JavaType::field(owner)?)?,
            );
            return Ok(SymbolicReference::ExternalCall(label, signature, true));
        }
        let polymorphic = self.catalog.nodes[symbolic_owner].key.loader == "bootstrap"
            && matches!(
                owner,
                "java/lang/invoke/MethodHandle" | "java/lang/invoke/VarHandle"
            );
        let member = if polymorphic {
            let found = self.catalog.nodes[symbolic_owner]
                .methods
                .iter()
                .enumerate()
                .find(|(_, m)| m.name == name && m.access & 0x180 == 0x180);
            if let Some((index, m)) = found {
                Member {
                    owner: symbolic_owner,
                    index,
                    name: name.into(),
                    descriptor: m.descriptor.clone(),
                    access: m.access,
                }
            } else {
                hierarchy::resolve_method(
                    self.catalog,
                    symbolic_owner,
                    name,
                    descriptor,
                    interface,
                )?
            }
        } else {
            hierarchy::resolve_method(self.catalog, symbolic_owner, name, descriptor, interface)?
        };
        let protected = self
            .catalog
            .accessible(self.caller, symbolic_owner, &member)?;
        ensure!(
            (member.access & 8 != 0) == is_static,
            "Method static/instance kind mismatch"
        );
        ensure!(
            !interface || !is_static || member.owner == symbolic_owner,
            "Interface static methods are not inherited"
        );
        if !is_static {
            signature.arguments.insert(
                0,
                if array_owner {
                    self.ty(owner)?
                } else {
                    Type::LinkedObject(if name == "<init>" {
                        member.owner
                    } else {
                        protected.unwrap_or(symbolic_owner)
                    })
                },
            );
        }
        let target = self.catalog.declared_method_id(&member)?;
        if polymorphic && member.access & 0x180 == 0x180 {
            let label = self.binding(
                cp,
                opcode,
                "signature_polymorphic_native",
                descriptor,
                Some(target),
                format!("boom_batch_call_{}_{}_{}", self.caller, cp, opcode),
            );
            return Ok(SymbolicReference::ExternalCall(
                label, signature, !is_static,
            ));
        }
        if name == "<init>" {
            ensure!(
                opcode == 0xb7 && member.owner == symbolic_owner,
                "Invalid constructor invocation"
            );
        }
        if opcode == 0xb7 && name != "<init>" {
            ensure!(
                !interface
                    || symbolic_owner == self.caller
                    || self.catalog.nodes[self.caller]
                        .interfaces
                        .contains(&symbolic_owner),
                "invokespecial requires a direct superinterface"
            );
            let mut lookup = symbolic_owner;
            if self.catalog.nodes[self.caller].access & 0x20 != 0
                && Metadata::assignable(self.catalog, self.caller, symbolic_owner)
                && self.caller != symbolic_owner
                && self.catalog.nodes[symbolic_owner].access & 0x200 == 0
            {
                lookup = self.catalog.nodes[self.caller]
                    .superclass
                    .context("Missing invokespecial superclass")?;
            }
            let selected = hierarchy::select_special(self.catalog, lookup, name, descriptor)?;
            if let hierarchy::Selection::Method { member: selected } = selected {
                let target = self.catalog.declared_method_id(&selected)?;
                if selected.access & 0x100 != 0 {
                    self.binding(
                        cp,
                        opcode,
                        "native_declaration",
                        descriptor,
                        Some(target),
                        format!("boom_m{target}"),
                    );
                }
                return Ok(SymbolicReference::DirectCall {
                    method: target,
                    signature,
                    is_static: false,
                    constructor: false,
                    protected_receiver: protected,
                });
            }
            let label = self.binding(
                cp,
                opcode,
                "special_selection_error",
                descriptor,
                Some(target),
                format!("boom_batch_call_{}_{}_{}", self.caller, cp, opcode),
            );
            return Ok(SymbolicReference::ExternalCall(label, signature, true));
        }
        let virtual_dispatch = !is_static
            && name != "<init>"
            && member.access & (2 | 0x10) == 0
            && self.catalog.nodes[symbolic_owner].access & 0x10 == 0;
        if virtual_dispatch {
            let label = self.binding(
                cp,
                opcode,
                "virtual_dispatch",
                descriptor,
                Some(target),
                format!("boom_batch_call_{}_{}_{}", self.caller, cp, opcode),
            );
            self.bindings.borrow_mut().last_mut().unwrap().dispatch = Some(VirtualCall {
                symbolic_owner,
                receiver_constraint: if array_owner {
                    self.universe
                        .array_id(self.catalog, self.loader(), &JavaType::field(owner)?)?
                } else {
                    protected.unwrap_or(symbolic_owner)
                },
                resolved_owner: member.owner,
                resolved_index: member.index,
                interface,
            });
            return Ok(SymbolicReference::ExternalCall(label, signature, true));
        }
        if member.access & 0x100 != 0 {
            self.binding(
                cp,
                opcode,
                "native_declaration",
                descriptor,
                Some(target),
                format!("boom_m{target}"),
            );
        }
        Ok(SymbolicReference::DirectCall {
            method: target,
            signature,
            is_static,
            constructor: name == "<init>",
            protected_receiver: protected,
        })
    }
}
impl StaticLinker for Environment<'_> {
    fn runtime_frames(&self) -> bool {
        true
    }
    fn runtime_stack_probe(&self) -> bool {
        true
    }
    fn symbolic_reference(
        &self,
        value: &Constant,
        cp: u16,
        opcode: u8,
    ) -> Result<SymbolicReference> {
        match value {
            Constant::Field {
                owner,
                name,
                descriptor,
            } => self.field(owner, name, descriptor, opcode),
            Constant::Method {
                owner,
                name,
                descriptor,
                interface,
            } => self.call(owner, name, descriptor, *interface, cp, opcode),
            Constant::InvokeDynamic(site) => {
                let signature = self.signature_of(&site.descriptor)?;
                let label = self.binding(
                    cp,
                    opcode,
                    "invokedynamic",
                    &site.descriptor,
                    None,
                    format!("boom_batch_call_{}_{}_{}", self.caller, cp, opcode),
                );
                self.bindings.borrow_mut().last_mut().unwrap().protocol = Some(format!(
                    "{}.{}{}",
                    site.bootstrap.owner, site.bootstrap.name, site.bootstrap.descriptor
                ));
                Ok(SymbolicReference::ExternalCall(label, signature, false))
            }
            Constant::Dynamic(site) => {
                let signature = Signature {
                    arguments: vec![],
                    result: self.ty(&site.descriptor)?,
                };
                let label = self.binding(
                    cp,
                    opcode,
                    "dynamic_constant",
                    &site.descriptor,
                    None,
                    format!("boom_batch_call_{}_{}_{}", self.caller, cp, opcode),
                );
                self.bindings.borrow_mut().last_mut().unwrap().protocol = Some(format!(
                    "{}.{}{}",
                    site.bootstrap.owner, site.bootstrap.name, site.bootstrap.descriptor
                ));
                Ok(SymbolicReference::ExternalCall(label, signature, false))
            }
            Constant::StringUtf16(_)
            | Constant::Class(_)
            | Constant::MethodType(_)
            | Constant::Handle(_) => {
                let descriptor = match value {
                    Constant::StringUtf16(_) => "Ljava/lang/String;",
                    Constant::Class(name) => {
                        if name.starts_with('[') {
                            let ty = JavaType::field(name)?;
                            self.universe.array_id(self.catalog, self.loader(), &ty)?;
                        } else {
                            self.catalog.lookup(self.loader(), name)?;
                        }
                        "Ljava/lang/Class;"
                    }
                    Constant::MethodType(_) => "Ljava/lang/invoke/MethodType;",
                    _ => "Ljava/lang/invoke/MethodHandle;",
                };
                let ty = self.ty(descriptor)?;
                let label = self.binding(
                    cp,
                    opcode,
                    if matches!(value, Constant::StringUtf16(_)) {
                        "string_literal_resolution"
                    } else {
                        "literal_resolution"
                    },
                    descriptor,
                    None,
                    format!("boom_batch_literal_load_{}_{}", self.caller, cp),
                );
                self.bindings.borrow_mut().last_mut().unwrap().protocol = Some(match value {
                    Constant::StringUtf16(_) => "java/lang/String".into(),
                    Constant::Class(_) => "java/lang/Class".into(),
                    Constant::MethodType(_) => "java/lang/invoke/MethodType".into(),
                    _ => "java/lang/invoke/MethodHandle".into(),
                });
                if let Constant::Class(name) = value {
                    self.bindings.borrow_mut().last_mut().unwrap().literal_type =
                        Some(if name.starts_with('[') {
                            self.universe.array_id(
                                self.catalog,
                                self.loader(),
                                &JavaType::field(name)?,
                            )?
                        } else {
                            self.catalog.lookup(self.loader(), name)?
                        });
                }
                Ok(SymbolicReference::ExternalCall(
                    label,
                    Signature {
                        arguments: vec![],
                        result: ty,
                    },
                    false,
                ))
            }
            _ => bail!("Unsupported symbolic reference constant"),
        }
    }
    fn context_bytes(&self) -> usize {
        32
    }
    fn normal_class_mirrors(&self) -> bool {
        true
    }
    fn initializer_source_abi(&self) -> u32 {
        2
    }
    fn resolve(&self, _: &ClassFile, _: u16) -> Result<(usize, Signature)> {
        bail!("Persistent IR environment requires symbolic reference binding")
    }
    fn class_id(&self, _: &ClassFile) -> Result<usize> {
        Ok(self.caller)
    }
    fn signature(&self, _: &ClassFile, method: &Method) -> Result<Signature> {
        let mut signature = self.signature_of(&method.descriptor)?;
        if method.access & 8 == 0 {
            signature
                .arguments
                .insert(0, Type::LinkedObject(self.caller));
        }
        Ok(signature)
    }
    fn object_class(&self, _: &ClassFile, name: &str) -> Result<usize> {
        self.catalog.lookup(self.loader(), name)
    }
    fn allocate_class(&self, class: &ClassFile, name: &str) -> Result<usize> {
        let id = self.object_class(class, name)?;
        ensure!(
            self.catalog.nodes[id].access & 0x600 == 0,
            "Allocation of abstract/interface type requires an instantiation-error binding"
        );
        Ok(id)
    }
    fn root_object_constructor(&self, _: &ClassFile) -> Result<bool> {
        Ok(self.caller == self.catalog.root_object()?)
    }
    fn constructor_parent(&self, child: usize, parent: usize) -> Result<bool> {
        Ok(self.catalog.nodes[child].superclass == Some(parent))
    }
    fn direct_object_parent(&self, id: usize) -> Result<bool> {
        Ok(self.catalog.nodes[id].superclass == Some(self.catalog.root_object()?))
    }
    fn root_object_allocation(&self, id: usize) -> Result<bool> {
        Ok(id == self.catalog.root_object()?)
    }
    fn assignable(&self, from: Type, to: Type) -> Result<bool> {
        self.verification_assign(from, to)
    }
    fn reference_join(&self, left: Type, right: Type) -> Result<Option<Type>> {
        self.join(left, right)
    }
    fn covariant_arrays(&self) -> bool {
        true
    }
    fn array_component(&self, ty: Type) -> Result<Option<Type>> {
        Ok(self.component(ty)?.filter(|ty| ty.is_reference()))
    }
    fn is_array(&self, ty: Type) -> Result<bool> {
        if let Type::ReferenceJoin(id) = ty {
            let values = self
                .joins
                .borrow()
                .get(id)
                .context("Invalid reference join")?
                .clone();
            for value in values {
                if !self.is_array(value)? {
                    return Ok(false);
                }
            }
            return Ok(true);
        }
        Ok(matches!(ty, Type::Array(_) | Type::MetadataReference(_)))
    }
    fn primitive_array(&self, ty: Type, kind: ArrayKind) -> Result<bool> {
        if let Type::ReferenceJoin(id) = ty {
            let values = self
                .joins
                .borrow()
                .get(id)
                .context("Invalid reference join")?
                .clone();
            for value in values {
                if !self.primitive_array(value, kind)? {
                    return Ok(false);
                }
            }
            return Ok(true);
        }
        Ok(
            matches!(ty,Type::Array(actual) if actual==kind || (actual==ArrayKind::Boolean&&kind==ArrayKind::Byte)),
        )
    }
    fn type_target(&self, _: &ClassFile, name: &str) -> Result<(usize, Type)> {
        if name.starts_with('[') {
            let ty = JavaType::field(name)?;
            Ok((
                self.universe.array_id(self.catalog, self.loader(), &ty)?,
                self.universe.ty(self.catalog, self.loader(), &ty)?,
            ))
        } else {
            let id = self.catalog.lookup(self.loader(), name)?;
            Ok((id, Type::LinkedObject(id)))
        }
    }
    fn typed_array(&self, _: &ClassFile, text: &str, dimensions: u8) -> Result<(usize, Type)> {
        let ty = JavaType::field(text)?;
        let JavaType::Array {
            dimensions: available,
            ..
        } = &ty
        else {
            bail!("Expected array descriptor")
        };
        ensure!(
            dimensions > 0 && dimensions <= *available,
            "Invalid array dimensions"
        );
        Ok((
            self.universe.array_id(self.catalog, self.loader(), &ty)?,
            self.universe.ty(self.catalog, self.loader(), &ty)?,
        ))
    }
    fn method_monitor(&self, _: &ClassFile, method: &Method) -> Result<Option<usize>> {
        Ok((method.access & 8 != 0).then_some(self.caller))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::compiler::batch_catalog::Header;

    fn header(id: usize, name: &str, access: u16) -> Header {
        serde_json::from_value(serde_json::json!({
            "schema": 1, "class_id": id, "name": name, "access": access,
            "superclass": if id == 0 { "" } else { "java/lang/Object" },
            "interfaces": [], "fields": [], "methods": [],
            "nest_host": null, "nest_members": null, "diagnostic": null,
            "origin": { "loader": "bootstrap", "binary_name": name.replace('/', "."),
                "source_id": "fixture", "jar_entry": format!("{name}.class"),
                "java_class_major": 65, "sha256": "a".repeat(64), "generated": null }
        }))
        .unwrap()
    }

    #[test]
    fn verifier_interface_arrays_do_not_relax_runtime_subtyping() {
        let catalog = Catalog::new(vec![
            header(0, "java/lang/Object", 1),
            header(1, "java/lang/Cloneable", 0x601),
            header(2, "java/io/Serializable", 0x601),
            header(3, "p/Interface", 0x601),
            header(4, "p/Concrete", 0x11),
            header(5, "p/Unrelated", 1),
            header(6, "p/OtherInterface", 0x601),
        ])
        .unwrap();
        let universe = Universe::new(&catalog).unwrap();
        let layouts = catalog.layouts();
        let env = Environment::new(&catalog, &universe, &layouts, 4, 0);
        let array = |descriptor: &str| {
            universe
                .ty(&catalog, "bootstrap", &JavaType::field(descriptor).unwrap())
                .unwrap()
        };
        assert!(
            env.verification_assign(Type::LinkedObject(4), Type::LinkedObject(3))
                .unwrap()
        );
        assert!(
            env.verification_assign(array("[Lp/Concrete;"), array("[Lp/Interface;"))
                .unwrap()
        );
        assert!(
            env.verification_assign(array("[Ljava/lang/Object;"), array("[Lp/Interface;"))
                .unwrap()
        );
        assert!(!Metadata::assignable(&catalog, 4, 3));
        assert!(
            !env.assign(Type::LinkedObject(4), Type::LinkedObject(5))
                .unwrap()
        );
        assert!(
            !env.assign(array("[Lp/Concrete;"), array("[Lp/Unrelated;"))
                .unwrap()
        );
        assert!(!env.assign(array("[I"), array("[Lp/Interface;")).unwrap());
        assert!(!env.assign(array("[I"), Type::LinkedObject(3)).unwrap());
        assert!(env.assign(array("[I"), Type::LinkedObject(1)).unwrap());
        assert!(env.assign(array("[I"), Type::LinkedObject(2)).unwrap());
        let left = Type::LinkedObject(3);
        let right = Type::LinkedObject(6);
        let merged = env.join(left, right).unwrap();
        assert_eq!(merged, env.join(right, left).unwrap());
        for _ in 0..32 {
            assert_eq!(env.join(merged.unwrap(), left).unwrap(), merged);
            assert_eq!(env.join(merged.unwrap(), right).unwrap(), merged);
        }
    }
}
