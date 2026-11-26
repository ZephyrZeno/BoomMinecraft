//! Loader-aware member resolution, method selection and physical field planning.
//! This module is an offline compiler component, never a game execution host.
use super::{
    classfile::{Field, Method},
    types::{ClassKey, Registry, Type},
};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

/// Shared nominal metadata for the original source linker and persisted IR.
/// Method/field slices are declarations, never an execution capability.
pub trait Metadata {
    fn class_view(&self, id: usize) -> Result<(&ClassKey, u16, Option<usize>, &[usize])>;
    fn methods(&self, id: usize) -> Result<&[Method]>;
    fn fields(&self, id: usize) -> Result<&[Field]>;
    fn assignable(&self, from: usize, to: usize) -> bool;
    fn root_object(&self) -> Result<usize>;
}
impl Metadata for Registry<'_> {
    fn class_view(&self, id: usize) -> Result<(&ClassKey, u16, Option<usize>, &[usize])> {
        let Some(Type::Class {
            key,
            access,
            superclass,
            interfaces,
            ..
        }) = self.types.get(id)
        else {
            bail!("Member owner is not a class or interface")
        };
        Ok((key, *access, *superclass, interfaces))
    }
    fn methods(&self, id: usize) -> Result<&[Method]> {
        Ok(&self
            .definition(id)
            .context("Missing class definition")?
            .methods)
    }
    fn fields(&self, id: usize) -> Result<&[Field]> {
        Ok(&self
            .definition(id)
            .context("Missing class definition")?
            .field_info)
    }
    fn assignable(&self, from: usize, to: usize) -> bool {
        Registry::assignable(self, from, to)
    }
    fn root_object(&self) -> Result<usize> {
        self.types.iter().position(|ty|matches!(ty,Type::Class{key,..} if key.loader=="bootstrap" && key.name=="java/lang/Object")).context("Missing bootstrap Object")
    }
}
macro_rules! borrowed_metadata {
    ($view:ident) => {
        impl<T: Metadata + ?Sized> Metadata for std::cell::$view<'_, T> {
            fn class_view(&self, id: usize) -> Result<(&ClassKey, u16, Option<usize>, &[usize])> {
                (**self).class_view(id)
            }
            fn methods(&self, id: usize) -> Result<&[Method]> {
                (**self).methods(id)
            }
            fn fields(&self, id: usize) -> Result<&[Field]> {
                (**self).fields(id)
            }
            fn assignable(&self, from: usize, to: usize) -> bool {
                (**self).assignable(from, to)
            }
            fn root_object(&self) -> Result<usize> {
                (**self).root_object()
            }
        }
    };
}
borrowed_metadata!(Ref);
borrowed_metadata!(RefMut);

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Member {
    pub owner: usize,
    pub index: usize,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FieldSlot {
    pub member: Member,
    pub offset: usize,
    pub reference: bool,
    #[serde(default = "legacy_slot_bytes")]
    pub storage_bytes: usize,
}
fn legacy_slot_bytes() -> usize {
    8
}
#[derive(Debug, Serialize)]
pub struct Layout {
    pub class: usize,
    pub payload_bytes: usize,
    pub reference_prefix: usize,
    pub fields: Vec<FieldSlot>,
}
#[derive(Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Selection {
    Method { member: Member },
    IncompatibleClassChange,
    AbstractMethod,
    IllegalAccess,
}
fn class(
    registry: &(impl Metadata + ?Sized),
    id: usize,
) -> Result<(&super::types::ClassKey, u16, Option<usize>, &[usize])> {
    registry.class_view(id)
}
fn method(
    registry: &(impl Metadata + ?Sized),
    owner: usize,
    name: &str,
    descriptor: &str,
) -> Option<Member> {
    registry
        .methods(owner)
        .ok()?
        .iter()
        .enumerate()
        .find(|(_, m)| m.name == name && m.descriptor == descriptor)
        .map(|(index, m)| Member {
            owner,
            index,
            name: m.name.clone(),
            descriptor: m.descriptor.clone(),
            access: m.access,
        })
}
fn methods(registry: &(impl Metadata + ?Sized), id: usize) -> Result<&[Method]> {
    registry.methods(id)
}
fn root_object(registry: &(impl Metadata + ?Sized)) -> Result<usize> {
    registry.root_object()
}
fn interfaces(registry: &(impl Metadata + ?Sized), id: usize) -> Result<BTreeSet<usize>> {
    let mut result = BTreeSet::new();
    let mut classes = vec![id];
    let mut seen = BTreeSet::new();
    while let Some(id) = classes.pop() {
        if !seen.insert(id) {
            continue;
        }
        ensure!(seen.len() <= 4096, "Hierarchy walk exceeds budget");
        let (_, access, parent, parents) = class(registry, id)?;
        for &parent in parents {
            result.insert(parent);
            classes.push(parent);
        }
        if access & 0x200 == 0 {
            classes.extend(parent);
        }
    }
    Ok(result)
}
fn maximal(
    registry: &(impl Metadata + ?Sized),
    id: usize,
    name: &str,
    descriptor: &str,
) -> Result<Vec<Member>> {
    let candidates = interfaces(registry, id)?
        .into_iter()
        .filter_map(|owner| method(registry, owner, name, descriptor))
        .filter(|m| m.access & (2 | 8) == 0)
        .collect::<Vec<_>>();
    Ok(candidates
        .iter()
        .filter(|candidate| {
            !candidates.iter().any(|other| {
                other.owner != candidate.owner && registry.assignable(other.owner, candidate.owner)
            })
        })
        .cloned()
        .collect())
}
pub fn resolve_method(
    registry: &(impl Metadata + ?Sized),
    owner: usize,
    name: &str,
    descriptor: &str,
    interface: bool,
) -> Result<Member> {
    let (_, access, _, _) = class(registry, owner)?;
    let owner_key = class(registry, owner)?.0;
    ensure!(
        !(owner_key.loader == "bootstrap"
            && matches!(
                owner_key.name.as_str(),
                "java/lang/invoke/MethodHandle" | "java/lang/invoke/VarHandle"
            )
            && methods(registry, owner)?
                .iter()
                .any(|m| m.name == name && m.access & (0x100 | 0x80) == 0x180)),
        "Signature-polymorphic methods require MethodHandle/VarHandle invocation support"
    );
    ensure!(
        (access & 0x200 != 0) == interface,
        "Method reference class/interface kind mismatch"
    );
    ensure!(
        name != "<clinit>",
        "Class initializer is not an invocation target"
    );
    if let Some(member) = method(registry, owner, name, descriptor) {
        return Ok(member);
    }
    ensure!(name != "<init>", "Constructors are not inherited");
    if interface {
        if let Some(member) = method(registry, root_object(registry)?, name, descriptor)
            && member.access & 9 == 1
        {
            return Ok(member);
        }
    } else {
        let mut parent = class(registry, owner)?.2;
        while let Some(id) = parent {
            if let Some(member) = method(registry, id, name, descriptor) {
                return Ok(member);
            }
            parent = class(registry, id)?.2;
        }
    }
    let candidates = maximal(registry, owner, name, descriptor)?;
    let concrete = candidates
        .iter()
        .filter(|m| m.access & 0x400 == 0)
        .collect::<Vec<_>>();
    if concrete.len() == 1 {
        return Ok(concrete[0].clone());
    }
    // Resolution may choose an abstract declaration. Selection detects conflicts.
    candidates
        .into_iter()
        .next()
        .context("NoSuchMethodError during hierarchy resolution")
}
fn same_package(registry: &(impl Metadata + ?Sized), left: usize, right: usize) -> Result<bool> {
    let (a, _, _, _) = class(registry, left)?;
    let (b, _, _, _) = class(registry, right)?;
    Ok(a.loader == b.loader
        && a.name.rsplit_once('/').map(|x| x.0) == b.name.rsplit_once('/').map(|x| x.0))
}
fn overrides(
    registry: &(impl Metadata + ?Sized),
    candidate: &Member,
    resolved: &Member,
    depth: usize,
) -> Result<bool> {
    ensure!(depth < 128, "Override search exceeds depth budget");
    if candidate.name != resolved.name
        || candidate.descriptor != resolved.descriptor
        || candidate.access & (2 | 8) != 0
        || resolved.access & 8 != 0
    {
        return Ok(false);
    }
    if resolved.access & 5 != 0 || same_package(registry, candidate.owner, resolved.owner)? {
        return Ok(resolved.access & 2 == 0);
    }
    if resolved.access & 2 != 0 {
        return Ok(false);
    }
    let mut parent = class(registry, candidate.owner)?.2;
    while let Some(id) = parent {
        if id == resolved.owner {
            break;
        }
        if let Some(middle) = method(registry, id, &candidate.name, &candidate.descriptor)
            && overrides(registry, candidate, &middle, depth + 1)?
            && overrides(registry, &middle, resolved, depth + 1)?
        {
            return Ok(true);
        }
        parent = class(registry, id)?.2;
    }
    Ok(false)
}
pub fn select_method(
    registry: &(impl Metadata + ?Sized),
    receiver: usize,
    symbolic_owner: usize,
    resolved: &Member,
    interface: bool,
) -> Result<Selection> {
    ensure!(
        !resolved.name.starts_with('<'),
        "Special methods cannot be virtually selected"
    );
    let (_, receiver_access, _, _) = class(registry, receiver)?;
    if receiver_access & 0x200 != 0 || !registry.assignable(receiver, symbolic_owner) {
        return Ok(Selection::IncompatibleClassChange);
    }
    if resolved.access & 8 != 0 {
        return Ok(Selection::IncompatibleClassChange);
    }
    let chosen = if resolved.access & 2 != 0 {
        Some(resolved.clone())
    } else {
        let mut current = Some(receiver);
        let mut chosen = None;
        while let Some(id) = current {
            if let Some(candidate) = method(registry, id, &resolved.name, &resolved.descriptor)
                && overrides(registry, &candidate, resolved, 0)?
            {
                chosen = Some(candidate);
                break;
            }
            current = class(registry, id)?.2;
        }
        if chosen.is_none() {
            let candidates = maximal(registry, receiver, &resolved.name, &resolved.descriptor)?;
            let concrete = candidates
                .into_iter()
                .filter(|m| m.access & 0x400 == 0)
                .collect::<Vec<_>>();
            if concrete.len() > 1 {
                return Ok(Selection::IncompatibleClassChange);
            }
            chosen = concrete.into_iter().next();
        }
        chosen
    };
    let Some(member) = chosen else {
        return Ok(Selection::AbstractMethod);
    };
    if member.access & 0x400 != 0 {
        return Ok(Selection::AbstractMethod);
    }
    // Private resolved methods are selected directly after caller access checks.
    if interface && member.access & 1 == 0 && resolved.access & 2 == 0 {
        return Ok(Selection::IllegalAccess);
    }
    Ok(Selection::Method { member })
}
pub fn resolve_field(
    registry: &(impl Metadata + ?Sized),
    owner: usize,
    name: &str,
    descriptor: &str,
) -> Result<Member> {
    fn search(
        registry: &(impl Metadata + ?Sized),
        owner: usize,
        name: &str,
        descriptor: &str,
        seen: &mut BTreeSet<usize>,
    ) -> Result<Option<Member>> {
        if !seen.insert(owner) {
            return Ok(None);
        }
        ensure!(seen.len() <= 4096, "Field lookup exceeds budget");
        if let Some((index, f)) = registry
            .fields(owner)?
            .iter()
            .enumerate()
            .find(|(_, f)| f.name == name && f.descriptor == descriptor)
        {
            return Ok(Some(Member {
                owner,
                index,
                name: f.name.clone(),
                descriptor: f.descriptor.clone(),
                access: f.access,
            }));
        }
        let (_, _, parent, parents) = class(registry, owner)?;
        for &parent in parents {
            if let Some(field) = search(registry, parent, name, descriptor, seen)? {
                return Ok(Some(field));
            }
        }
        if let Some(parent) = parent {
            return search(registry, parent, name, descriptor, seen);
        }
        Ok(None)
    }
    search(registry, owner, name, descriptor, &mut BTreeSet::new())?
        .context("NoSuchFieldError during hierarchy resolution")
}
/// JVMS invokespecial lookup after symbolic resolution and caller access checks.
pub fn select_special(
    registry: &(impl Metadata + ?Sized),
    lookup: usize,
    name: &str,
    descriptor: &str,
) -> Result<Selection> {
    let (_, access, parent, _) = class(registry, lookup)?;
    let mut selected = method(registry, lookup, name, descriptor);
    if selected.is_none() && access & 0x200 == 0 {
        let mut next = parent;
        while let Some(id) = next {
            selected = method(registry, id, name, descriptor);
            if selected.is_some() {
                break;
            }
            next = class(registry, id)?.2;
        }
    }
    if selected.is_none() && access & 0x200 != 0 {
        selected = method(registry, root_object(registry)?, name, descriptor)
            .filter(|m| m.access & 9 == 1);
    }
    if selected.is_none() {
        let concrete = maximal(registry, lookup, name, descriptor)?
            .into_iter()
            .filter(|m| m.access & 0x400 == 0)
            .collect::<Vec<_>>();
        if concrete.len() > 1 {
            return Ok(Selection::IncompatibleClassChange);
        }
        selected = concrete.into_iter().next();
    }
    Ok(match selected {
        Some(member) if member.access & 8 != 0 => Selection::IncompatibleClassChange,
        Some(member) if member.access & 0x400 == 0 => Selection::Method { member },
        _ => Selection::AbstractMethod,
    })
}
pub fn layout(registry: &(impl Metadata + ?Sized), owner: usize) -> Result<Layout> {
    ensure!(
        class(registry, owner)?.1 & 0x200 == 0,
        "Interfaces have no instance layout"
    );
    let mut chain = Vec::new();
    let mut current = Some(owner);
    while let Some(id) = current {
        ensure!(chain.len() < 128, "Layout inheritance exceeds depth budget");
        chain.push(id);
        current = class(registry, id)?.2;
    }
    chain.reverse();
    let mut fields = Vec::new();
    for owner in chain {
        for (index, f) in registry
            .fields(owner)?
            .iter()
            .enumerate()
            .filter(|(_, f)| f.access & 8 == 0)
        {
            fields.push(FieldSlot {
                member: Member {
                    owner,
                    index,
                    name: f.name.clone(),
                    descriptor: f.descriptor.clone(),
                    access: f.access,
                },
                offset: 0,
                reference: f.descriptor.starts_with(['L', '[']),
                storage_bytes: 8,
            });
        }
    }
    ensure!(
        fields.len() <= 65536,
        "Inherited object field count exceeds budget"
    );
    // Stable partition keeps declaration order within reference/scalar groups.
    fields.sort_by_key(|f| !f.reference);
    for (index, field) in fields.iter_mut().enumerate() {
        field.offset = index * 8;
    }
    Ok(Layout {
        class: owner,
        payload_bytes: fields.len() * 8,
        reference_prefix: fields.iter().filter(|f| f.reference).count(),
        fields,
    })
}
pub fn storage_bytes(descriptor: &str) -> Result<usize> {
    Ok(match descriptor {
        "Z" | "B" => 1,
        "C" | "S" => 2,
        "I" | "F" => 4,
        "J" | "D" => 8,
        value if value.starts_with('[') && value.len() > 1 => 8,
        value if value.starts_with('L') && value.ends_with(';') && value.len() > 2 => 8,
        _ => bail!("Invalid field storage descriptor"),
    })
}
/// Layout ABI2: eight-byte reference prefix, then naturally aligned scalar
/// groups. Distinct byte/boolean fields retain distinct byte addresses.
pub fn compact_layout(registry: &(impl Metadata + ?Sized), owner: usize) -> Result<Layout> {
    let mut result = layout(registry, owner)?;
    for field in &mut result.fields {
        field.storage_bytes = storage_bytes(&field.member.descriptor)?;
    }
    result
        .fields
        .sort_by_key(|field| (!field.reference, std::cmp::Reverse(field.storage_bytes)));
    let mut cursor = 0usize;
    for field in &mut result.fields {
        cursor = cursor
            .checked_add(field.storage_bytes - 1)
            .context("Field alignment overflow")?
            & !(field.storage_bytes - 1);
        field.offset = cursor;
        cursor = cursor
            .checked_add(field.storage_bytes)
            .context("Object size overflow")?;
    }
    result.payload_bytes = cursor;
    Ok(result)
}
pub fn initialization_dependencies(
    registry: &(impl Metadata + ?Sized),
    owner: usize,
) -> Result<Vec<usize>> {
    let (_, access, parent, parents) = class(registry, owner)?;
    if access & 0x200 != 0 {
        return Ok(Vec::new());
    }
    fn visit(
        registry: &(impl Metadata + ?Sized),
        id: usize,
        seen: &mut BTreeSet<usize>,
        output: &mut Vec<usize>,
    ) -> Result<()> {
        if !seen.insert(id) {
            return Ok(());
        }
        ensure!(
            seen.len() <= 4096,
            "Initialization interface walk exceeds budget"
        );
        for &parent in class(registry, id)?.3 {
            visit(registry, parent, seen, output)?;
        }
        if methods(registry, id)?
            .iter()
            .any(|m| m.access & (8 | 0x400) == 0 && !m.name.starts_with('<'))
        {
            output.push(id);
        }
        Ok(())
    }
    let mut output = parent.into_iter().collect::<Vec<_>>();
    let mut seen = BTreeSet::new();
    for &parent in parents {
        visit(registry, parent, &mut seen, &mut output)?;
    }
    Ok(output)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Request {
    pub owner: String,
    pub method: String,
    pub descriptor: String,
    pub receiver: String,
    pub interface: bool,
}
#[derive(Debug, Serialize)]
pub struct Call {
    pub request: Request,
    pub symbolic_owner: usize,
    pub receiver: usize,
    pub resolved: Member,
    pub selection: Selection,
}
#[derive(Debug, Serialize)]
pub struct Root {
    pub class: usize,
    pub layout: Option<Layout>,
    pub initialization_dependencies: Vec<usize>,
}
#[derive(Debug, Serialize)]
pub struct Plan {
    pub schema: u32,
    pub input_fingerprint: String,
    pub types: Vec<Type>,
    pub roots: Vec<Root>,
    pub calls: Vec<Call>,
    pub execution_wired: bool,
    pub full_game_ready: bool,
}
pub fn plan(
    inputs: &crate::lock::InputLock,
    manifest: &std::path::Path,
    class_files: &[std::path::PathBuf],
    names: &[String],
    requests: &[Request],
    output: &std::path::Path,
) -> Result<Plan> {
    use super::{classfile::ClassFile, mirrors};
    use std::{collections::BTreeMap, io::Read};
    ensure!(
        !names.is_empty()
            && names.len() <= 128
            && class_files.len() <= 1024
            && requests.len() <= 4096,
        "Hierarchy plan exceeds input budget"
    );
    let mut explicit = BTreeMap::new();
    let mut total = 0usize;
    for path in class_files {
        let mut bytes = Vec::new();
        std::fs::File::open(path)?
            .take(16 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)?;
        ensure!(
            bytes.len() <= 16 * 1024 * 1024,
            "Hierarchy class exceeds byte limit"
        );
        total += bytes.len();
        ensure!(
            total <= 256 * 1024 * 1024,
            "Hierarchy classes exceed byte budget"
        );
        let class = ClassFile::parse(&bytes)?;
        let origin = mirrors::explicit_origin(&class, &bytes)?;
        ensure!(
            explicit
                .insert(class.name.clone(), (bytes, origin))
                .is_none(),
            "Duplicate hierarchy class definition"
        );
    }
    let loader = if explicit.is_empty() {
        "vanilla-application"
    } else {
        "explicit-application"
    };
    let provider = mirrors::Inputs {
        explicit,
        base: super::types::VanillaTypes::new(inputs, manifest)?,
    };
    let mut registry = Registry::new(&provider);
    let mut roots = Vec::new();
    for name in names {
        let id = registry.root(loader, &name.replace('.', "/"))?.class;
        roots.push(Root {
            class: id,
            layout: if class(&registry, id)?.1 & 0x200 == 0 {
                Some(layout(&registry, id)?)
            } else {
                None
            },
            initialization_dependencies: initialization_dependencies(&registry, id)?,
        });
    }
    let mut calls = Vec::new();
    for request in requests {
        let owner = registry.class(loader, &request.owner.replace('.', "/"))?;
        let receiver = registry.class(loader, &request.receiver.replace('.', "/"))?;
        let resolved = resolve_method(
            &registry,
            owner,
            &request.method,
            &request.descriptor,
            request.interface,
        )?;
        let declared_loader = class(&registry, resolved.owner)?.0.loader.clone();
        let declared = registry.method(&declared_loader, &request.descriptor)?;
        let initiating = registry.method(loader, &request.descriptor)?;
        ensure!(
            declared.arguments == initiating.arguments && declared.result == initiating.result,
            "Method descriptor violates defining-loader constraints"
        );
        let selection = select_method(&registry, receiver, owner, &resolved, request.interface)?;
        calls.push(Call {
            request: request.clone(),
            symbolic_owner: owner,
            receiver,
            resolved,
            selection,
        });
    }
    let result = Plan {
        schema: 1,
        input_fingerprint: inputs.fingerprint.clone(),
        types: registry.types,
        roots,
        calls,
        execution_wired: false,
        full_game_ready: false,
    };
    crate::files::write_atomic(output, &serde_json::to_vec_pretty(&result)?)?;
    Ok(result)
}
