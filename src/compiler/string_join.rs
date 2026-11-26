//! Source-verified String.join plans. Callbacks and joining execute as MASM.
use super::{numeric, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Kind {
    Array,
    Iterable,
    Replace,
}
impl Kind {
    pub(super) fn resolve(owner: &str, name: &str, descriptor: &str) -> Option<Self> {
        if owner == "java/lang/String"
            && name == "replace"
            && descriptor == "(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;"
        {
            return Some(Self::Replace);
        }
        if owner != "java/lang/String" || name != "join" {
            return None;
        }
        match descriptor {
            "(Ljava/lang/CharSequence;[Ljava/lang/CharSequence;)Ljava/lang/String;" => {
                Some(Self::Array)
            }
            "(Ljava/lang/CharSequence;Ljava/lang/Iterable;)Ljava/lang/String;" => {
                Some(Self::Iterable)
            }
            _ => None,
        }
    }
    pub(super) fn member_name(self) -> &'static str {
        if self == Self::Replace {
            "replace"
        } else {
            "join"
        }
    }
    pub(super) fn invocation_descriptor(self) -> &'static str {
        if self == Self::Replace {
            "(Ljava/lang/String;Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;"
        } else {
            self.descriptor()
        }
    }
    pub(super) fn descriptor(self) -> &'static str {
        match self {
            Self::Replace => "(Ljava/lang/CharSequence;Ljava/lang/CharSequence;)Ljava/lang/String;",
            Self::Array => "(Ljava/lang/CharSequence;[Ljava/lang/CharSequence;)Ljava/lang/String;",
            Self::Iterable => "(Ljava/lang/CharSequence;Ljava/lang/Iterable;)Ljava/lang/String;",
        }
    }
    pub(super) fn callbacks(self) -> Vec<(&'static str, &'static str, &'static str)> {
        let mut v = vec![("java/lang/CharSequence", "toString", "()Ljava/lang/String;")];
        if self == Self::Iterable {
            v.extend([
                ("java/lang/Iterable", "iterator", "()Ljava/util/Iterator;"),
                ("java/util/Iterator", "hasNext", "()Z"),
                ("java/util/Iterator", "next", "()Ljava/lang/Object;"),
            ]);
        }
        v
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub id: usize,
    pub kind: Kind,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub origin: ClassOrigin,
    pub char_sequence_type: usize,
    pub dispatch_sites: Vec<usize>,
    pub null_literal: usize,
    pub source_method: String,
    pub code_sha256: String,
    pub native_source_sha256: String,
    pub literal_role: String,
    pub original_java_api_body_executed: bool,
}
pub(super) struct Link {
    pub id: usize,
    pub signature: numeric::Signature,
    pub targets: Vec<usize>,
    pub owners: Vec<usize>,
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    kind: Kind,
) -> Result<(ClassOrigin, usize, String)> {
    let id = registry.class("bootstrap", "java/lang/String")?;
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
        "String.join requires the pinned final bootstrap String"
    );
    let origin = origin.as_ref().clone();
    let m = registry
        .definition(id)
        .context("Missing String definition")?
        .method(kind.member_name(), Some(kind.descriptor()))?;
    ensure!(
        m.access & (1 | 8 | 0x20 | 0x100 | 0x400) == (if kind == Kind::Replace { 1 } else { 9 })
            && m.code.is_some(),
        "String.join source member contract changed"
    );
    let code_sha256 = files::digest_bytes(&m.code.as_ref().unwrap().bytes).sha256;
    let cs = registry.class("bootstrap", "java/lang/CharSequence")?;
    ensure!(
        matches!(&registry.types[cs],types::Type::Class{key,origin,access,..} if key.loader=="bootstrap" && origin.source_id=="jdk:java.base" && access&0x201==0x201),
        "CharSequence callback type is not its original bootstrap interface"
    );
    Ok((origin, cs, code_sha256))
}
pub(super) fn emit(assembly: &mut String, plans: &[Plan]) -> Result<()> {
    use std::fmt::Write;
    if plans.is_empty() {
        return Ok(());
    }
    assembly.push_str("EXTERN boom_string_join:PROC\n.const\n");
    for (id, p) in plans.iter().enumerate() {
        ensure!(
            p.id == id && p.dispatch_sites.len() == if p.kind == Kind::Iterable { 4 } else { 1 },
            "String.join callback plan mismatch"
        );
        ensure!(
            p.dispatch_sites
                .iter()
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                == p.dispatch_sites.len(),
            "String.join callback roles cannot reuse one dispatch site"
        );
        writeln!(
            assembly,
            "ALIGN 8\nboom_string_join_plan{id} DWORD 04A4F494Eh, 1, {}, 0\n    QWORD OFFSET boom_string_pool, OFFSET boom_runtime_type_map, OFFSET boom_t{}",
            match p.kind {
                Kind::Array => 0,
                Kind::Iterable => 1,
                Kind::Replace => 2,
            },
            p.char_sequence_type
        )?;
        for i in 0..4 {
            writeln!(
                assembly,
                "    QWORD {}",
                p.dispatch_sites
                    .get(i)
                    .map_or("0".into(), |site| format!("OFFSET boom_dispatch{site}"))
            )?;
        }
        writeln!(
            assembly,
            "    QWORD OFFSET boom_string_array_layout\n    DWORD {}, 0",
            p.null_literal
        )?;
    }
    assembly.push_str(
        ".code\nPUBLIC boom_get_sequence_replace_plan\nboom_get_sequence_replace_plan PROC\n",
    );
    for p in plans.iter().filter(|p| p.kind == Kind::Replace) {
        writeln!(
            assembly,
            "    cmp ecx,{}\n    jne boom_sequence_plan_next{}\n    lea rax,boom_string_join_plan{}\n    ret\nboom_sequence_plan_next{}:",
            p.id, p.id, p.id, p.id
        )?;
    }
    assembly.push_str("    xor eax,eax\n    ret\nboom_get_sequence_replace_plan ENDP\n");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture(name: &str, kind: Kind, member_access: u16, string_access: u16) -> Vec<u8> {
        let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 10];
        fn utf(b: &mut Vec<u8>, s: &str) {
            b.push(1);
            b.extend((s.len() as u16).to_be_bytes());
            b.extend(s.as_bytes());
        }
        utf(&mut b, name);
        b.extend([7, 0, 1]);
        utf(&mut b, "java/lang/Object");
        b.extend([7, 0, 3]);
        utf(&mut b, "java/lang/CharSequence");
        b.extend([7, 0, 5]);
        for s in [kind.member_name(), kind.descriptor(), "Code"] {
            utf(&mut b, s);
        }
        let string = name == "java/lang/String";
        let access = if string {
            string_access
        } else if name == "java/lang/CharSequence" {
            0x601
        } else {
            0x21
        };
        for n in [
            access,
            2,
            if name == "java/lang/Object" { 0 } else { 4 },
            u16::from(string),
        ] {
            b.extend(n.to_be_bytes());
        }
        if string {
            b.extend(6u16.to_be_bytes());
        }
        for n in [0, u16::from(string)] {
            b.extend(n.to_be_bytes());
        }
        if string {
            for n in [member_access, 7, 8, u16::from(member_access & 0x100 == 0)] {
                b.extend(n.to_be_bytes());
            }
            if member_access & 0x100 == 0 {
                b.extend(9u16.to_be_bytes());
                b.extend(14u32.to_be_bytes());
                b.extend([0, 1, 0, 2, 0, 0, 0, 2, 0x01, 0xb0, 0, 0, 0, 0]);
            }
        }
        b.extend([0, 0]);
        b
    }
    struct Provider {
        kind: Kind,
        member: u16,
        class: u16,
        loader: &'static str,
        source: &'static str,
    }
    impl types::TypeProvider for Provider {
        fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let b = fixture(name, self.kind, self.member, self.class);
            Ok((
                b.clone(),
                ClassOrigin {
                    generated: None,
                    loader: if name == "java/lang/String" {
                        self.loader
                    } else {
                        "bootstrap"
                    }
                    .into(),
                    binary_name: name.replace('/', "."),
                    source_id: if name == "java/lang/String" {
                        self.source
                    } else {
                        "jdk:java.base"
                    }
                    .into(),
                    jar_entry: format!("{name}.class"),
                    java_class_major: 65,
                    sha256: crate::files::digest_bytes(&b).sha256,
                },
            ))
        }
    }
    #[test]
    fn join_binding_requires_both_original_member_contracts() {
        for kind in [Kind::Array, Kind::Iterable] {
            for (member, class, loader, source, valid) in [
                (9, 0x31, "bootstrap", "jdk:java.base", true),
                (0x89, 0x31, "bootstrap", "jdk:java.base", true),
                (0x109, 0x31, "bootstrap", "jdk:java.base", false),
                (8, 0x31, "bootstrap", "jdk:java.base", false),
                (9, 0x21, "bootstrap", "jdk:java.base", false),
                (9, 0x31, "application", "jdk:java.base", false),
                (9, 0x31, "bootstrap", "other", false),
            ] {
                let provider = Provider {
                    kind,
                    member,
                    class,
                    loader,
                    source,
                };
                assert_eq!(
                    binding(&mut types::Registry::new(&provider), kind).is_ok(),
                    valid
                );
            }
        }
        assert!(Kind::resolve("app/String", "join", Kind::Array.descriptor()).is_none());
        assert!(Kind::resolve("java/lang/String", "join", "(II)I").is_none());
    }
    #[test]
    fn sequence_replace_requires_an_instance_member_and_original_string() {
        for (member, valid) in [
            (1, true),
            (0x81, true),
            (9, false),
            (0x101, false),
            (0, false),
        ] {
            let provider = Provider {
                kind: Kind::Replace,
                member,
                class: 0x31,
                loader: "bootstrap",
                source: "jdk:java.base",
            };
            assert_eq!(
                binding(&mut types::Registry::new(&provider), Kind::Replace).is_ok(),
                valid
            );
        }
        assert_eq!(
            Kind::resolve("java/lang/String", "replace", Kind::Replace.descriptor()),
            Some(Kind::Replace)
        );
        assert_eq!(Kind::Replace.callbacks().len(), 1);
    }
    #[test]
    fn join_callback_roles_and_plan_identity_are_explicit() {
        let provider = Provider {
            kind: Kind::Iterable,
            member: 9,
            class: 0x31,
            loader: "bootstrap",
            source: "jdk:java.base",
        };
        let (origin, cs, code_sha256) =
            binding(&mut types::Registry::new(&provider), Kind::Iterable).unwrap();
        let mut p = Plan {
            id: 0,
            kind: Kind::Iterable,
            caller: origin.clone(),
            constant: 7,
            origin,
            char_sequence_type: cs,
            dispatch_sites: vec![0, 1, 2, 3],
            null_literal: 0,
            source_method: "join".into(),
            code_sha256,
            native_source_sha256: String::new(),
            literal_role: "null".into(),
            original_java_api_body_executed: false,
        };
        emit(&mut String::new(), &[p.clone()]).unwrap();
        p.dispatch_sites.pop();
        assert!(emit(&mut String::new(), &[p.clone()]).is_err());
        p.dispatch_sites = vec![0, 0, 2, 3];
        assert!(emit(&mut String::new(), &[p.clone()]).is_err());
        p.kind = Kind::Array;
        p.dispatch_sites = vec![0];
        p.id = 1;
        assert!(emit(&mut String::new(), &[p]).is_err());
    }
}
