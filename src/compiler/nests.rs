//! Loader/package-aware nest access, proved from reciprocal class attributes.
use super::types;
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Proof {
    pub caller: ClassOrigin,
    pub owner: ClassOrigin,
    pub host: ClassOrigin,
}
fn key<'r>(registry: &'r types::Registry<'_>, id: usize) -> (&'r types::ClassKey, &'r ClassOrigin) {
    let types::Type::Class { key, origin, .. } = &registry.types[id] else {
        unreachable!()
    };
    (key, origin)
}
fn package(name: &str) -> &str {
    name.rsplit_once('/').map_or("", |(p, _)| p)
}
fn host(registry: &mut types::Registry<'_>, id: usize) -> Result<usize> {
    let (member, _) = key(registry, id);
    let member = member.clone();
    let Some(name) = registry
        .definition(id)
        .context("Missing nest member definition")?
        .nest_host
        .clone()
    else {
        return Ok(id);
    };
    // JVMS 5.4.4: resolution/package/reciprocity failure makes M its own host.
    let Ok(candidate) = registry.class(&member.loader, &name) else {
        return Ok(id);
    };
    let (candidate_key, _) = key(registry, candidate);
    if candidate_key.loader != member.loader
        || package(&candidate_key.name) != package(&member.name)
    {
        return Ok(id);
    }
    Ok(
        if registry
            .definition(candidate)
            .and_then(|c| c.nest_members.as_ref())
            .is_some_and(|v| v.contains(&member.name))
        {
            candidate
        } else {
            id
        },
    )
}
pub(super) fn prove(
    registry: &mut types::Registry<'_>,
    caller_loader: &str,
    caller: &str,
    owner_loader: &str,
    owner: &str,
) -> Result<Option<Proof>> {
    if caller_loader != owner_loader || package(caller) != package(owner) {
        return Ok(None);
    }
    let c = registry.class(caller_loader, caller)?;
    let d = registry.class(owner_loader, owner)?;
    let h = host(registry, d)?;
    let other = host(registry, c)?;
    if h != other {
        return Ok(None);
    }
    Ok(Some(Proof {
        caller: key(registry, c).1.clone(),
        owner: key(registry, d).1.clone(),
        host: key(registry, h).1.clone(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;
    fn class(name: &str, host: Option<&str>, members: Option<&[&str]>) -> Vec<u8> {
        let mut pool = Vec::new();
        let mut count = 1u16;
        fn utf(pool: &mut Vec<u8>, count: &mut u16, s: &str) -> u16 {
            let id = *count;
            *count += 1;
            pool.push(1);
            pool.extend((s.len() as u16).to_be_bytes());
            pool.extend(s.as_bytes());
            id
        }
        fn cls(pool: &mut Vec<u8>, count: &mut u16, s: &str) -> u16 {
            let n = utf(pool, count, s);
            let id = *count;
            *count += 1;
            pool.push(7);
            pool.extend(n.to_be_bytes());
            id
        }
        let this = cls(&mut pool, &mut count, name);
        let parent = cls(&mut pool, &mut count, "java/lang/Object");
        let host_attr = utf(&mut pool, &mut count, "NestHost");
        let members_attr = utf(&mut pool, &mut count, "NestMembers");
        let h = host.map(|s| cls(&mut pool, &mut count, s));
        let m = members.map(|v| {
            v.iter()
                .map(|s| cls(&mut pool, &mut count, s))
                .collect::<Vec<_>>()
        });
        let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65];
        b.extend(count.to_be_bytes());
        b.extend(pool);
        for n in [
            0x21,
            this,
            if name == "java/lang/Object" {
                0
            } else {
                parent
            },
            0,
            0,
            0,
            u16::from(h.is_some()) + u16::from(m.is_some()),
        ] {
            b.extend(n.to_be_bytes());
        }
        if let Some(h) = h {
            b.extend(host_attr.to_be_bytes());
            b.extend(2u32.to_be_bytes());
            b.extend(h.to_be_bytes());
        }
        if let Some(m) = m {
            b.extend(members_attr.to_be_bytes());
            b.extend((2 + 2 * m.len() as u32).to_be_bytes());
            b.extend((m.len() as u16).to_be_bytes());
            for n in m {
                b.extend(n.to_be_bytes());
            }
        }
        b
    }
    struct Provider(BTreeMap<String, Vec<u8>>);
    impl types::TypeProvider for Provider {
        fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let bytes = if name == "java/lang/Object" {
                class(name, None, None)
            } else {
                self.0.get(name).context("Missing nest host")?.clone()
            };
            let origin = ClassOrigin {
                generated: None,
                loader: if name == "java/lang/Object" {
                    "bootstrap"
                } else {
                    "app"
                }
                .into(),
                binary_name: name.replace('/', "."),
                source_id: "test:nests".into(),
                jar_entry: format!("{name}.class"),
                java_class_major: 65,
                sha256: crate::files::digest_bytes(&bytes).sha256,
            };
            Ok((bytes, origin))
        }
    }
    #[test]
    fn access_requires_reciprocal_membership_and_runtime_package() {
        for (host_members, valid) in [
            (vec!["p/A", "p/B"], true),
            (vec!["p/A"], false),
            (vec![], false),
        ] {
            let p = Provider(BTreeMap::from([
                ("p/H".into(), class("p/H", None, Some(&host_members))),
                ("p/A".into(), class("p/A", Some("p/H"), None)),
                ("p/B".into(), class("p/B", Some("p/H"), None)),
            ]));
            let mut r = types::Registry::new(&p);
            assert_eq!(
                prove(&mut r, "app", "p/A", "app", "p/B").unwrap().is_some(),
                valid
            );
            assert!(
                prove(&mut r, "app", "p/A", "other", "p/B")
                    .unwrap()
                    .is_none()
            );
            assert!(prove(&mut r, "app", "p/A", "app", "q/B").unwrap().is_none());
        }
        let p = Provider(BTreeMap::from([
            ("p/A".into(), class("p/A", Some("p/Missing"), None)),
            ("p/B".into(), class("p/B", Some("p/Missing"), None)),
        ]));
        assert!(
            prove(&mut types::Registry::new(&p), "app", "p/A", "app", "p/B")
                .unwrap()
                .is_none()
        );
    }
    #[test]
    fn nest_attributes_keep_their_structural_exclusion_and_version() {
        assert!(
            super::super::classfile::ClassFile::parse(&class("p/A", Some("p/H"), Some(&[])))
                .is_err()
        );
        let mut b = class("p/A", Some("p/H"), None);
        b[7] = 54;
        assert!(super::super::classfile::ClassFile::parse(&b).is_err());
        let c =
            super::super::classfile::ClassFile::parse(&class("p/H", None, Some(&["p/A", "p/B"])))
                .unwrap();
        assert_eq!(c.nest_members.unwrap(), ["p/A", "p/B"]);
    }
}
