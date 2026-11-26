//! Source-verified metadata for Class literals; independent of executable class state.
use super::{
    classfile::ClassFile,
    types::{self, TypeProvider},
};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Result, ensure};
use std::collections::BTreeMap;

pub(super) const PRIMITIVE_DESCRIPTOR: &str = "(Ljava/lang/String;)Ljava/lang/Class;";
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PrimitiveBinding {
    pub caller: ClassOrigin,
    pub origin: ClassOrigin,
    pub type_ids: Vec<usize>,
}
pub(super) fn primitive_binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
) -> Result<PrimitiveBinding> {
    use anyhow::Context;
    ensure!(
        source.loader == "bootstrap"
            && source.source_id == "jdk:java.base"
            && caller.name.rsplit_once('/').map(|v| v.0) == Some("java/lang"),
        "Class.getPrimitiveClass requires its bootstrap java.lang package caller"
    );
    let caller_id = registry.class("bootstrap", &caller.name)?;
    ensure!(
        matches!(&registry.types[caller_id], types::Type::Class { origin, .. } if origin.as_ref() == source),
        "Primitive class caller differs from verified metadata"
    );
    let id = registry.class("bootstrap", "java/lang/Class")?;
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
        key.loader == "bootstrap" && origin.source_id == "jdk:java.base" && access & 0x211 == 0x11,
        "Primitive lookup requires the pinned final bootstrap Class"
    );
    let origin = origin.as_ref().clone();
    let method = registry
        .definition(id)
        .context("Missing Class definition")?
        .method("getPrimitiveClass", Some(PRIMITIVE_DESCRIPTOR))?;
    ensure!(
        method.access == 0x108 && method.code.is_none(),
        "Primitive lookup must name the package static native Class member"
    );
    registry.class("bootstrap", "java/lang/String")?;
    use types::Primitive as P;
    let type_ids = [
        P::Boolean,
        P::Byte,
        P::Char,
        P::Short,
        P::Int,
        P::Long,
        P::Float,
        P::Double,
        P::Void,
    ]
    .into_iter()
    .map(|p| registry.primitive(p))
    .collect::<Result<Vec<_>>>()?;
    Ok(PrimitiveBinding {
        caller: source.clone(),
        origin,
        type_ids,
    })
}

pub(super) fn emit_primitives(assembly: &mut String, bindings: &[PrimitiveBinding]) -> Result<()> {
    use std::fmt::Write;
    if let Some(first) = bindings.first() {
        ensure!(
            first.type_ids.len() == 9
                && bindings
                    .iter()
                    .all(|b| b.type_ids == first.type_ids && b.origin == first.origin),
            "Inconsistent primitive lookup bindings"
        );
        assembly.push_str("EXTERN boom_mirror_primitive:PROC\n.const\nALIGN 4\nboom_primitive_type_ids LABEL DWORD\n");
        for id in &first.type_ids {
            writeln!(assembly, "    DWORD {id}")?;
        }
        assembly.push_str(".code\n");
    }
    Ok(())
}

pub(super) struct Inputs<'a> {
    pub explicit: BTreeMap<String, (Vec<u8>, ClassOrigin)>,
    pub base: types::VanillaTypes<'a>,
}
impl TypeProvider for Inputs<'_> {
    fn name_in_use(&self, name: &str) -> Result<bool> {
        Ok(self.explicit.contains_key(name) || self.base.name_in_use(name)?)
    }
    fn resolve(&self, loader: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
        if self.base.bootstrap_contains(name) {
            ensure!(
                !self.explicit.contains_key(name),
                "Explicit metadata collides with a bootstrap class: {name}"
            );
            return self.base.resolve("bootstrap", name);
        }
        // Explicit development classes define a separate application namespace.
        // Bootstrap requests always retain parent-first verified JDK identity.
        if loader == "explicit-application"
            && !name.starts_with("java/")
            && let Some((bytes, origin)) = self.explicit.get(name)
        {
            return Ok((bytes.clone(), origin.clone()));
        }
        self.base.resolve(
            if loader == "bootstrap" {
                "bootstrap"
            } else {
                "vanilla-application"
            },
            name,
        )
    }
}

pub(super) fn explicit_origin(class: &ClassFile, bytes: &[u8]) -> Result<ClassOrigin> {
    ensure!(
        !class.name.starts_with("java/"),
        "Explicit inputs cannot redefine bootstrap java.* classes"
    );
    let sha256 = files::digest_bytes(bytes).sha256;
    Ok(ClassOrigin {
        generated: None,
        loader: "explicit-application".into(),
        binary_name: class.name.replace('/', "."),
        source_id: format!("explicit-sha256:{sha256}"),
        jar_entry: format!("{}.class", class.name),
        java_class_major: class.major,
        sha256,
    })
}

pub(super) fn name(types: &[types::Type], id: usize) -> String {
    use types::{Primitive as P, Type as T};
    match &types[id] {
        T::Class { key, .. } => key.name.replace('/', "."),
        T::Primitive { value } => match value {
            P::Boolean => "boolean",
            P::Byte => "byte",
            P::Char => "char",
            P::Short => "short",
            P::Int => "int",
            P::Long => "long",
            P::Float => "float",
            P::Double => "double",
            P::Void => "void",
        }
        .into(),
        T::Array { component } => {
            let part = match &types[*component] {
                T::Primitive { value } => match value {
                    P::Boolean => "Z",
                    P::Byte => "B",
                    P::Char => "C",
                    P::Short => "S",
                    P::Int => "I",
                    P::Long => "J",
                    P::Float => "F",
                    P::Double => "D",
                    P::Void => unreachable!("void cannot be an array component"),
                }
                .into(),
                T::Class { .. } => format!("L{};", name(types, *component)),
                T::Array { .. } => name(types, *component),
            };
            format!("[{part}")
        }
    }
}

pub(super) fn emit(
    assembly: &mut String,
    types: &[types::Type],
    names: &[usize],
    assertions: Option<super::assertions::Policy>,
) -> Result<()> {
    use std::fmt::Write;
    ensure!(types.len() == names.len(), "Mirror/name metadata mismatch");
    // The type emitter's standalone END is removed when embedding in a program.
    let metadata = types::emit_metadata(types)?;
    assembly.push_str(
        metadata
            .strip_suffix("END\n")
            .or_else(|| metadata.strip_suffix("END"))
            .unwrap_or(&metadata),
    );
    assembly.push_str("\nEXTERN boom_mirror_load:PROC\nEXTERN boom_mirror_intrinsic:PROC\n.const\nALIGN 8\nboom_mirror_layout DWORD 04F424A43h, 1\n    QWORD 8\n    DWORD 0, 1\nALIGN 8\nboom_mirror_array_layout DWORD 052454641h, 1\n    QWORD OFFSET boom_mirror_layout\nboom_mirror_rows LABEL BYTE\n");
    let object = types.iter().position(|ty| matches!(ty, types::Type::Class{key,..} if key.loader=="bootstrap" && key.name=="java/lang/Object"));
    for (id, ty) in types.iter().enumerate() {
        let (parent, component) = match ty {
            types::Type::Class {
                superclass, access, ..
            } => (
                if access & 0x200 != 0 {
                    None
                } else {
                    *superclass
                },
                None,
            ),
            types::Type::Array { component } => (object, Some(*component)),
            types::Type::Primitive { .. } => (None, None),
        };
        writeln!(
            assembly,
            "    QWORD OFFSET boom_t{id}\n    DWORD {}, {}, {}, 0",
            names[id],
            parent.unwrap_or(u32::MAX as usize),
            component.unwrap_or(u32::MAX as usize)
        )?;
    }
    let (abi, policy_pointer) = if let Some(policy) = assertions {
        writeln!(
            assembly,
            "ALIGN 8\nboom_assertion_policy DWORD 041535354h, 1, {}, {}\n    QWORD OFFSET boom_assertion_statuses, 0\nboom_assertion_statuses LABEL DWORD",
            policy.bits(),
            types.len()
        )?;
        for ty in types {
            writeln!(assembly, "    DWORD {}", policy.status(ty))?;
        }
        (2, "OFFSET boom_assertion_policy")
    } else {
        (1, "0")
    };
    writeln!(
        assembly,
        ".data\nALIGN 8\nboom_mirror_pool DWORD 04D495252h, {abi}, 0, {}\n    QWORD OFFSET boom_mirror_roots, OFFSET boom_mirror_rows, OFFSET boom_mirror_layout, OFFSET boom_string_pool, 0, {policy_pointer}\n.code",
        types.len()
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture(name: &str, method_access: u16) -> Vec<u8> {
        let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 8];
        fn utf(b: &mut Vec<u8>, value: &str) {
            b.push(1);
            b.extend((value.len() as u16).to_be_bytes());
            b.extend(value.as_bytes());
        }
        utf(&mut b, name);
        b.extend([7, 0, 1]);
        utf(&mut b, "java/lang/Object");
        b.extend([7, 0, 3]);
        for value in ["getPrimitiveClass", PRIMITIVE_DESCRIPTOR, "Code"] {
            utf(&mut b, value);
        }
        let is_class = name == "java/lang/Class";
        for value in [
            if is_class { 0x31u16 } else { 0x21 },
            2,
            if name == "java/lang/Object" { 0 } else { 4 },
            0,
            0,
            u16::from(is_class),
        ] {
            b.extend(value.to_be_bytes());
        }
        if is_class {
            for value in [method_access, 5, 6, 0] {
                b.extend(value.to_be_bytes());
            }
        }
        b.extend([0, 0]);
        b
    }
    struct Provider {
        method_access: u16,
        class_loader: &'static str,
    }
    impl TypeProvider for Provider {
        fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let bytes = fixture(name, self.method_access);
            let origin = ClassOrigin {
                generated: None,
                loader: if name == "java/lang/Class" {
                    self.class_loader
                } else {
                    "bootstrap"
                }
                .into(),
                binary_name: name.replace('/', "."),
                source_id: "jdk:java.base".into(),
                jar_entry: format!("{name}.class"),
                java_class_major: 65,
                sha256: files::digest_bytes(&bytes).sha256,
            };
            Ok((bytes, origin))
        }
    }
    #[test]
    fn primitive_native_binding_preserves_package_and_source_boundaries() {
        for (method_access, class_loader, valid) in [
            (0x108, "bootstrap", true),
            (0x109, "bootstrap", false),
            (0x128, "bootstrap", false),
            (8, "bootstrap", false),
            (0x108, "application", false),
        ] {
            let provider = Provider {
                method_access,
                class_loader,
            };
            let (bytes, origin) = provider.resolve("bootstrap", "java/lang/Integer").unwrap();
            let class = ClassFile::parse(&bytes).unwrap();
            let mut registry = types::Registry::new(&provider);
            let result = primitive_binding(&mut registry, &class, &origin);
            assert_eq!(
                result.is_ok(),
                valid,
                "{method_access:x}/{class_loader}: {result:?}"
            );
        }
        let provider = Provider {
            method_access: 0x108,
            class_loader: "bootstrap",
        };
        let (bytes, origin) = provider.resolve("bootstrap", "java/lang/Integer").unwrap();
        let class = ClassFile::parse(&bytes).unwrap();
        for altered in 0..3 {
            let mut origin = origin.clone();
            match altered {
                0 => origin.loader = "application".into(),
                1 => origin.source_id = "other".into(),
                _ => origin.sha256 = "changed".into(),
            }
            assert!(
                primitive_binding(&mut types::Registry::new(&provider), &class, &origin).is_err()
            );
        }
        let (bytes, origin) = provider.resolve("bootstrap", "java/util/Other").unwrap();
        assert!(
            primitive_binding(
                &mut types::Registry::new(&provider),
                &ClassFile::parse(&bytes).unwrap(),
                &origin
            )
            .is_err()
        );
    }
}
