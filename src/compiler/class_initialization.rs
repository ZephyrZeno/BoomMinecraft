//! Source-proven SharedSecrets initialization requests for frozen Class constants.
//! This does not expose a general MethodHandles/Lookup implementation.
use super::{
    classfile::{ClassFile, Code},
    types,
};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

pub const OWNER: &str = "jdk/internal/access/SharedSecrets";
pub const METHOD: &str = "ensureClassInitialized";
pub const DESCRIPTOR: &str = "(Ljava/lang/Class;)V";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Site {
    pub method: String,
    pub descriptor: String,
    pub pc: usize,
    pub constant: u16,
    pub target: String,
    pub mirror_type: usize,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub abi: u32,
    pub caller: ClassOrigin,
    pub site: Site,
    pub target: ClassOrigin,
    pub class_id: usize,
}
pub(super) fn resolves(owner: &str, name: &str, descriptor: &str) -> bool {
    owner == OWNER && name == METHOD && descriptor == DESCRIPTOR
}
pub(super) fn site(
    caller: &ClassFile,
    code: &Code,
    pc: usize,
    constant: u16,
    target: &str,
    mirror_type: usize,
) -> Result<Site> {
    ensure!(
        caller.name == OWNER,
        "SharedSecrets private initializer requires its original caller"
    );
    let method = caller
        .methods
        .iter()
        .find(|m| m.code.as_ref().is_some_and(|c| std::ptr::eq(c, code)))
        .context("Class initialization request lacks an identified caller method")?;
    let (owner, name, descriptor, interface) = caller.static_method_reference(constant)?;
    ensure!(
        !interface && resolves(&owner, &name, &descriptor),
        "Invalid SharedSecrets initialization request"
    );
    ensure!(
        !target.starts_with('['),
        "SharedSecrets initialization requires an ordinary constant Class"
    );
    Ok(Site {
        method: method.name.clone(),
        descriptor: method.descriptor.clone(),
        pc,
        constant,
        target: target.into(),
        mirror_type,
    })
}
fn helper(class: &ClassFile) -> Result<()> {
    let member = class.method(METHOD, Some(DESCRIPTOR))?;
    let code = member
        .code
        .as_ref()
        .context("Missing SharedSecrets initialization helper Code")?;
    let b = &code.bytes;
    ensure!(
        member.access == 0xa
            && code.max_stack == 2
            && code.max_locals == 2
            && b.len() == 13
            && b[0] == 0xb8
            && b[3..5] == [0x2a, 0xb6]
            && b[7..] == [0x57, 0xa7, 0, 4, 0x4c, 0xb1],
        "SharedSecrets initialization helper body changed"
    );
    let lookup = class.static_method_reference(u16::from_be_bytes([b[1], b[2]]))?;
    ensure!(
        lookup
            == (
                "java/lang/invoke/MethodHandles".into(),
                "lookup".into(),
                "()Ljava/lang/invoke/MethodHandles$Lookup;".into(),
                false
            ),
        "SharedSecrets lookup contract changed"
    );
    let init = class.method_reference(u16::from_be_bytes([b[5], b[6]]))?;
    ensure!(
        init == (
            "java/lang/invoke/MethodHandles$Lookup".into(),
            "ensureInitialized".into(),
            "(Ljava/lang/Class;)Ljava/lang/Class;".into()
        ),
        "SharedSecrets ensureInitialized contract changed"
    );
    ensure!(
        code.handlers.len() == 1
            && code.handlers[0].start_pc == 0
            && code.handlers[0].end_pc == 8
            && code.handlers[0].handler_pc == 11
            && code.handlers[0].catch_type.as_deref() == Some("java/lang/IllegalAccessException"),
        "SharedSecrets initialization helper exception contract changed"
    );
    Ok(())
}
pub(super) fn binding(
    registry: &mut types::Registry<'_>,
    caller: &ClassFile,
    source: &ClassOrigin,
    site: Site,
    class_id: usize,
) -> Result<Binding> {
    let id = registry.class("bootstrap", OWNER)?;
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
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none()
            && access & 0x601 == 1
            && caller.name == OWNER
            && source == origin.as_ref(),
        "SharedSecrets initialization requires its original bootstrap java.base definition"
    );
    helper(caller)?;
    let target_id = registry.class("bootstrap", &site.target)?;
    ensure!(
        target_id == site.mirror_type,
        "Initialization Class constant differs from its metadata target"
    );
    let types::Type::Class {
        key,
        origin,
        access,
        ..
    } = &registry.types[target_id]
    else {
        unreachable!()
    };
    // Same module and public class: Lookup.accessClass succeeds. Other access
    // cases must retain the helper's IllegalAccessException behavior first.
    ensure!(
        key.loader == "bootstrap"
            && origin.source_id == "jdk:java.base"
            && origin.generated.is_none()
            && access & 1 != 0,
        "SharedSecrets initialization currently requires an accessible public java.base target"
    );
    Ok(Binding {
        abi: 1,
        caller: source.clone(),
        site,
        target: origin.as_ref().clone(),
        class_id,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Pool(Vec<Vec<u8>>);
    impl Pool {
        fn add(&mut self, b: Vec<u8>) -> u16 {
            self.0.push(b);
            self.0.len() as u16
        }
        fn utf(&mut self, s: &str) -> u16 {
            let mut b = vec![1];
            b.extend((s.len() as u16).to_be_bytes());
            b.extend(s.as_bytes());
            self.add(b)
        }
        fn class(&mut self, s: &str) -> u16 {
            let n = self.utf(s);
            let mut b = vec![7];
            b.extend(n.to_be_bytes());
            self.add(b)
        }
        fn method(&mut self, owner: &str, name: &str, descriptor: &str) -> u16 {
            let c = self.class(owner);
            let n = self.utf(name);
            let d = self.utf(descriptor);
            let mut nt = vec![12];
            nt.extend(n.to_be_bytes());
            nt.extend(d.to_be_bytes());
            let t = self.add(nt);
            let mut b = vec![10];
            b.extend(c.to_be_bytes());
            b.extend(t.to_be_bytes());
            self.add(b)
        }
    }
    fn fixture(name: &str, access: u16) -> Vec<u8> {
        let mut p = Pool(vec![]);
        let this = p.class(name);
        let parent = p.class("java/lang/Object");
        let method = p.utf(METHOD);
        let descriptor = p.utf(DESCRIPTOR);
        let code = p.utf("Code");
        let lookup = p.method(
            "java/lang/invoke/MethodHandles",
            "lookup",
            "()Ljava/lang/invoke/MethodHandles$Lookup;",
        );
        let initialize = p.method(
            "java/lang/invoke/MethodHandles$Lookup",
            "ensureInitialized",
            "(Ljava/lang/Class;)Ljava/lang/Class;",
        );
        let catch = p.class("java/lang/IllegalAccessException");
        let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65];
        b.extend(((p.0.len() + 1) as u16).to_be_bytes());
        for constant in p.0 {
            b.extend(constant);
        }
        for v in [
            access,
            this,
            if name == "java/lang/Object" {
                0
            } else {
                parent
            },
            0,
            0,
            u16::from(name == OWNER),
        ] {
            b.extend(v.to_be_bytes());
        }
        if name == OWNER {
            for v in [0xau16, method, descriptor, 1, code] {
                b.extend(v.to_be_bytes());
            }
            let mut c = vec![0, 2, 0, 2, 0, 0, 0, 13, 0xb8];
            c.extend(lookup.to_be_bytes());
            c.extend([0x2a, 0xb6]);
            c.extend(initialize.to_be_bytes());
            c.extend([0x57, 0xa7, 0, 4, 0x4c, 0xb1]);
            for v in [1u16, 0, 8, 11, catch, 0] {
                c.extend(v.to_be_bytes());
            }
            b.extend((c.len() as u32).to_be_bytes());
            b.extend(c);
        }
        b.extend([0, 0]);
        b
    }
    struct Provider {
        target_access: u16,
        caller_loader: &'static str,
    }
    impl types::TypeProvider for Provider {
        fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let bytes = fixture(
                name,
                if name == "java/io/FileDescriptor" {
                    self.target_access
                } else {
                    0x21
                },
            );
            let origin = ClassOrigin {
                generated: None,
                loader: if name == OWNER {
                    self.caller_loader
                } else {
                    "bootstrap"
                }
                .into(),
                binary_name: name.replace('/', "."),
                source_id: "jdk:java.base".into(),
                jar_entry: format!("{name}.class"),
                java_class_major: 65,
                sha256: crate::files::digest_bytes(&bytes).sha256,
            };
            Ok((bytes, origin))
        }
    }
    #[test]
    fn original_helper_proves_lookup_body_and_only_ignored_access_exception() {
        let mut class = ClassFile::parse(&fixture(OWNER, 0x21)).unwrap();
        assert!(helper(&class).is_ok());
        class.methods[0].code.as_mut().unwrap().handlers[0].catch_type =
            Some("java/lang/Exception".into());
        assert!(helper(&class).is_err());
        class.methods[0].code.as_mut().unwrap().handlers[0].catch_type =
            Some("java/lang/IllegalAccessException".into());
        class.methods[0].code.as_mut().unwrap().bytes[7] = 0x00;
        assert!(helper(&class).is_err());
    }
    #[test]
    fn original_helper_rejects_changed_access_and_handler_ranges() {
        for access in [0x9, 0x2, 0x10a] {
            let mut class = ClassFile::parse(&fixture(OWNER, 0x21)).unwrap();
            class.methods[0].access = access;
            assert!(helper(&class).is_err());
        }
        for field in 0..3 {
            let mut class = ClassFile::parse(&fixture(OWNER, 0x21)).unwrap();
            let h = &mut class.methods[0].code.as_mut().unwrap().handlers[0];
            match field {
                0 => h.start_pc = 1,
                1 => h.end_pc = 7,
                _ => h.handler_pc = 12,
            };
            assert!(helper(&class).is_err());
        }
    }
    #[test]
    fn initialization_binding_requires_original_caller_accessible_target_and_matching_mirror() {
        use types::TypeProvider;
        for (target_access, caller_loader, valid) in [
            (0x31, "bootstrap", true),
            (0x20, "bootstrap", false),
            (0x31, "application", false),
        ] {
            let p = Provider {
                target_access,
                caller_loader,
            };
            let (bytes, source) = p.resolve("bootstrap", OWNER).unwrap();
            let class = ClassFile::parse(&bytes).unwrap();
            let mut registry = types::Registry::new(&p);
            let mirror = registry
                .class("bootstrap", "java/io/FileDescriptor")
                .unwrap();
            let site = Site {
                method: "getAccess".into(),
                descriptor: "()V".into(),
                pc: 10,
                constant: 35,
                target: "java/io/FileDescriptor".into(),
                mirror_type: mirror,
            };
            assert_eq!(
                binding(&mut registry, &class, &source, site.clone(), 4).is_ok(),
                valid
            );
            if valid {
                let mut wrong = source.clone();
                wrong.sha256 = "different".into();
                assert!(binding(&mut registry, &class, &wrong, site.clone(), 4).is_err());
                let mut wrong = site;
                wrong.mirror_type = usize::MAX;
                assert!(binding(&mut registry, &class, &source, wrong, 4).is_err());
            }
        }
    }
}
