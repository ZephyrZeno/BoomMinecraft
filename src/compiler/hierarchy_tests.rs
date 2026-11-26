use super::hierarchy::*;
use super::types::{Registry, TypeProvider};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result};
use std::collections::{BTreeMap, BTreeSet};

struct Memory(BTreeMap<String, Vec<u8>>);
impl TypeProvider for Memory {
    fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
        let bytes = self.0.get(name).context("Missing test class")?.clone();
        Ok((
            bytes.clone(),
            ClassOrigin {
                generated: None,
                loader: if name == "java/lang/Object" {
                    "bootstrap".into()
                } else {
                    "application".into()
                },
                binary_name: name.replace('/', "."),
                source_id: "test".into(),
                jar_entry: format!("{name}.class"),
                java_class_major: 65,
                sha256: files::digest_bytes(&bytes).sha256,
            },
        ))
    }
}
fn fixture(
    name: &str,
    parent: &str,
    interfaces: &[&str],
    access: u16,
    fields: &[(&str, &str, u16)],
    methods: &[(&str, &str, u16)],
) -> Vec<u8> {
    fn short(out: &mut Vec<u8>, value: u16) {
        out.extend_from_slice(&value.to_be_bytes());
    }
    fn utf(pool: &mut Vec<Vec<u8>>, value: &str) -> u16 {
        let mut data = vec![1];
        short(&mut data, value.len() as u16);
        data.extend_from_slice(value.as_bytes());
        pool.push(data);
        pool.len() as u16
    }
    fn class(pool: &mut Vec<Vec<u8>>, value: &str) -> u16 {
        let name = utf(pool, value);
        let mut data = vec![7];
        short(&mut data, name);
        pool.push(data);
        pool.len() as u16
    }
    let mut pool = Vec::new();
    let this = class(&mut pool, name);
    let parent = if parent.is_empty() {
        0
    } else {
        class(&mut pool, parent)
    };
    let interfaces = interfaces
        .iter()
        .map(|name| class(&mut pool, name))
        .collect::<Vec<_>>();
    let mut members = Vec::new();
    for group in [fields, methods] {
        let mut data = Vec::new();
        short(&mut data, group.len() as u16);
        for &(name, descriptor, access) in group {
            short(&mut data, access);
            short(&mut data, utf(&mut pool, name));
            short(&mut data, utf(&mut pool, descriptor));
            short(&mut data, 0);
        }
        members.push(data);
    }
    let mut out = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65];
    short(&mut out, pool.len() as u16 + 1);
    for entry in pool {
        out.extend(entry);
    }
    for value in [access, this, parent, interfaces.len() as u16] {
        short(&mut out, value);
    }
    for interface in interfaces {
        short(&mut out, interface);
    }
    for data in members {
        out.extend(data);
    }
    short(&mut out, 0);
    out
}
#[test]
fn inherited_defaults_reabstraction_conflicts_and_class_precedence() {
    let provider = Memory(BTreeMap::from([
        (
            "java/lang/Object".into(),
            fixture("java/lang/Object", "", &[], 1, &[], &[]),
        ),
        (
            "p/I".into(),
            fixture(
                "p/I",
                "java/lang/Object",
                &[],
                0x601,
                &[],
                &[("f", "(I)I", 1)],
            ),
        ),
        (
            "p/J".into(),
            fixture(
                "p/J",
                "java/lang/Object",
                &["p/I"],
                0x601,
                &[],
                &[("f", "(I)I", 1)],
            ),
        ),
        (
            "p/K".into(),
            fixture(
                "p/K",
                "java/lang/Object",
                &["p/I"],
                0x601,
                &[],
                &[("f", "(I)I", 0x401)],
            ),
        ),
        (
            "p/L".into(),
            fixture(
                "p/L",
                "java/lang/Object",
                &[],
                0x601,
                &[],
                &[("f", "(I)I", 1)],
            ),
        ),
        (
            "p/Base".into(),
            fixture(
                "p/Base",
                "java/lang/Object",
                &[],
                1,
                &[],
                &[("f", "(I)I", 1)],
            ),
        ),
        (
            "p/C".into(),
            fixture("p/C", "p/Base", &["p/J"], 1, &[], &[]),
        ),
        (
            "p/D".into(),
            fixture("p/D", "java/lang/Object", &["p/J"], 1, &[], &[]),
        ),
        (
            "p/E".into(),
            fixture("p/E", "java/lang/Object", &["p/K"], 0x401, &[], &[]),
        ),
        (
            "p/F".into(),
            fixture("p/F", "java/lang/Object", &["p/J", "p/L"], 1, &[], &[]),
        ),
        (
            "p/N".into(),
            fixture("p/N", "java/lang/Object", &[], 1, &[], &[]),
        ),
    ]));
    let mut registry = Registry::new(&provider);
    let i = registry.class("application", "p/I").unwrap();
    let base = registry.class("application", "p/Base").unwrap();
    let resolved = resolve_method(&registry, i, "f", "(I)I", true).unwrap();
    for (name, expected) in [
        ("p/C", Some("p/Base")),
        ("p/D", Some("p/J")),
        ("p/E", None),
        ("p/F", None),
        ("p/N", None),
    ] {
        let receiver = registry.class("application", name).unwrap();
        let selection = select_method(&registry, receiver, i, &resolved, true).unwrap();
        match expected {
            Some(name) => {
                let owner = registry.class("application", name).unwrap();
                assert!(matches!(selection,Selection::Method{member} if member.owner==owner));
            }
            None => assert_eq!(
                selection,
                if name == "p/E" {
                    Selection::AbstractMethod
                } else {
                    Selection::IncompatibleClassChange
                }
            ),
        }
    }
    assert!(resolve_method(&registry, base, "f", "(I)I", true).is_err());
    assert!(resolve_method(&registry, i, "<init>", "()V", true).is_err());
    let d = registry.class("application", "p/D").unwrap();
    let f = registry.class("application", "p/F").unwrap();
    assert!(
        matches!(select_special(&registry,base,"f","(I)I").unwrap(),Selection::Method{member} if member.owner==base)
    );
    assert!(
        matches!(select_special(&registry,d,"f","(I)I").unwrap(),Selection::Method{member} if registry.definition(member.owner).unwrap().name=="p/J")
    );
    assert_eq!(
        select_special(&registry, f, "f", "(I)I").unwrap(),
        Selection::IncompatibleClassChange
    );
}
#[test]
fn inherited_fields_keep_declaring_identity_and_reference_prefix() {
    let provider = Memory(BTreeMap::from([
        (
            "java/lang/Object".into(),
            fixture("java/lang/Object", "", &[], 1, &[], &[]),
        ),
        (
            "p/Base".into(),
            fixture(
                "p/Base",
                "java/lang/Object",
                &[],
                1,
                &[("value", "I", 0), ("parent", "Ljava/lang/Object;", 2)],
                &[],
            ),
        ),
        (
            "p/Child".into(),
            fixture(
                "p/Child",
                "p/Base",
                &[],
                1,
                &[("child", "Ljava/lang/Object;", 0), ("value", "I", 0)],
                &[],
            ),
        ),
    ]));
    let mut registry = Registry::new(&provider);
    let child = registry.class("application", "p/Child").unwrap();
    let base = registry.class("application", "p/Base").unwrap();
    let inherited = layout(&registry, child).unwrap();
    assert_eq!(
        (inherited.payload_bytes, inherited.reference_prefix),
        (32, 2)
    );
    assert_eq!(
        layout(&registry, base)
            .unwrap()
            .fields
            .iter()
            .find(|f| f.member.name == "value")
            .unwrap()
            .offset,
        8
    );
    assert_eq!(
        inherited
            .fields
            .iter()
            .find(|f| f.member.owner == base && f.member.name == "value")
            .unwrap()
            .offset,
        16
    );
    assert_eq!(
        resolve_field(&registry, child, "value", "I").unwrap().owner,
        child
    );
    assert_eq!(
        resolve_field(&registry, child, "parent", "Ljava/lang/Object;")
            .unwrap()
            .owner,
        base
    );
}

#[test]
fn compact_fields_are_aligned_distinct_and_keep_inherited_reference_identity() {
    let provider = Memory(BTreeMap::from([
        (
            "java/lang/Object".into(),
            fixture("java/lang/Object", "", &[], 1, &[], &[]),
        ),
        (
            "p/Base".into(),
            fixture(
                "p/Base",
                "java/lang/Object",
                &[],
                1,
                &[
                    ("flag", "Z", 0),
                    ("value", "I", 0),
                    ("ref", "Ljava/lang/Object;", 2),
                    ("wide", "J", 0),
                ],
                &[],
            ),
        ),
        (
            "p/Child".into(),
            fixture(
                "p/Child",
                "p/Base",
                &[],
                1,
                &[
                    ("flag", "Z", 0),
                    ("small", "B", 0),
                    ("character", "C", 0),
                    ("fraction", "D", 0),
                    ("factor", "F", 0),
                    ("ref", "Ljava/lang/Object;", 0),
                ],
                &[],
            ),
        ),
    ]));
    let mut registry = Registry::new(&provider);
    let child = registry.class("application", "p/Child").unwrap();
    let legacy = layout(&registry, child).unwrap();
    let packed = compact_layout(&registry, child).unwrap();
    assert_eq!(legacy.payload_bytes, 80);
    assert_eq!(packed.payload_bytes, 45);
    assert_eq!(packed.reference_prefix, 2);
    let mut occupied = BTreeSet::new();
    for field in &packed.fields {
        assert_eq!(field.offset % field.storage_bytes, 0);
        for byte in field.offset..field.offset + field.storage_bytes {
            assert!(occupied.insert(byte));
            assert!(byte < packed.payload_bytes);
        }
        if field.reference {
            assert!(field.offset < packed.reference_prefix * 8);
            assert_eq!(field.storage_bytes, 8);
        } else {
            assert!(field.offset >= packed.reference_prefix * 8);
        }
    }
    let flags = packed
        .fields
        .iter()
        .filter(|field| field.member.name == "flag")
        .collect::<Vec<_>>();
    assert_eq!(flags.len(), 2);
    assert_ne!(flags[0].offset, flags[1].offset);
    assert_ne!(flags[0].member.owner, flags[1].member.owner);
    assert!(storage_bytes("V").is_err());
}
