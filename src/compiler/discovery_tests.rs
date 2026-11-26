use super::*;
use crate::bytecode::ClassOrigin;

#[derive(Default)]
struct Pool(Vec<Vec<u8>>);
fn u16s(out: &mut Vec<u8>, value: u16) {
    out.extend(value.to_be_bytes());
}
impl Pool {
    fn utf(&mut self, s: &str) -> u16 {
        let mut v = vec![1];
        u16s(&mut v, s.len() as u16);
        v.extend(s.as_bytes());
        self.0.push(v);
        self.0.len() as u16
    }
    fn class(&mut self, name: &str) -> u16 {
        let id = self.utf(name);
        let mut v = vec![7];
        u16s(&mut v, id);
        self.0.push(v);
        self.0.len() as u16
    }
    fn reference(&mut self, owner: &str, name: &str, desc: &str, interface: bool) -> u16 {
        let owner = self.class(owner);
        let name = self.utf(name);
        let desc = self.utf(desc);
        let mut v = vec![12];
        u16s(&mut v, name);
        u16s(&mut v, desc);
        self.0.push(v);
        let nt = self.0.len() as u16;
        let mut v = vec![if interface { 11 } else { 10 }];
        u16s(&mut v, owner);
        u16s(&mut v, nt);
        self.0.push(v);
        self.0.len() as u16
    }
}
fn fixture(name: &str, interface_call: bool) -> Vec<u8> {
    let mut cp = Pool::default();
    let this = cp.class(name);
    let parent = if name == "java/lang/Object" {
        0
    } else {
        cp.class(if name == "p/Unused" {
            "p/Poison"
        } else {
            "java/lang/Object"
        })
    };
    let interfaces = if name == "p/Concrete" {
        vec![cp.class("p/I")]
    } else {
        Vec::new()
    };
    let (method, desc, access, max_locals, bytes) = match name {
        "p/Main" => {
            let object = cp.class("p/Concrete");
            let ctor = cp.reference("p/Concrete", "<init>", "()V", false);
            let call = cp.reference(
                if interface_call { "p/I" } else { "p/Concrete" },
                "f",
                "(I)I",
                interface_call,
            );
            let mut b = vec![0xbb];
            u16s(&mut b, object);
            b.push(0x59);
            b.push(0xb7);
            u16s(&mut b, ctor);
            b.push(0x06);
            b.push(if interface_call { 0xb9 } else { 0xb6 });
            u16s(&mut b, call);
            if interface_call {
                b.extend([2, 0]);
            }
            b.push(0xac);
            ("run", "()I", 9, 0, b)
        }
        "p/Concrete" => {
            let ctor = cp.reference("java/lang/Object", "<init>", "()V", false);
            let mut b = vec![0x2a, 0xb7];
            u16s(&mut b, ctor);
            b.push(0xb1);
            ("<init>", "()V", 1, 1, b)
        }
        "p/I" => {
            let helper = cp.reference("p/Helper", "plus", "(I)I", false);
            let mut b = vec![0x1b, 0xb8];
            u16s(&mut b, helper);
            b.push(0xac);
            ("f", "(I)I", 1, 2, b)
        }
        "p/Helper" => ("plus", "(I)I", 9, 1, vec![0x1a, 0x04, 0x60, 0xac]),
        "java/lang/Object" => ("<init>", "()V", 1, 1, vec![0xb1]),
        "p/Unused" => ("unused", "()V", 9, 0, vec![0xb1]),
        "p/Poison" => ("<clinit>", "()V", 8, 0, vec![0xca]),
        _ => panic!("Unexpected fixture"),
    };
    let method = cp.utf(method);
    let desc = cp.utf(desc);
    let code = cp.utf("Code");
    let mut out = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65];
    u16s(&mut out, cp.0.len() as u16 + 1);
    for entry in cp.0 {
        out.extend(entry);
    }
    for n in [
        if name == "p/I" { 0x601 } else { 0x21 },
        this,
        parent,
        interfaces.len() as u16,
    ] {
        u16s(&mut out, n);
    }
    for id in interfaces {
        u16s(&mut out, id);
    }
    for n in [0, 1, access, method, desc, 1, code] {
        u16s(&mut out, n);
    }
    out.extend((12 + bytes.len() as u32).to_be_bytes());
    u16s(&mut out, 4);
    u16s(&mut out, max_locals);
    out.extend((bytes.len() as u32).to_be_bytes());
    out.extend(bytes);
    for _ in 0..3 {
        u16s(&mut out, 0);
    }
    out
}
struct Memory(BTreeMap<String, Vec<u8>>);
impl types::TypeProvider for Memory {
    fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
        let bytes = self
            .0
            .get(name)
            .context("Unexpected discovery source")?
            .clone();
        Ok((
            bytes.clone(),
            ClassOrigin {
                generated: None,
                loader: if name == "java/lang/Object" {
                    "bootstrap"
                } else {
                    "vanilla-application"
                }
                .into(),
                binary_name: name.replace('/', "."),
                source_id: "memory".into(),
                jar_entry: format!("{name}.class"),
                java_class_major: 65,
                sha256: files::digest_bytes(&bytes).sha256,
            },
        ))
    }
}
#[test]
fn discovers_selected_default_body_and_its_transitive_static_dependencies() {
    use types::TypeProvider;
    for interface in [true, false] {
        let provider = Memory(
            [
                "java/lang/Object",
                "p/Main",
                "p/Concrete",
                "p/I",
                "p/Helper",
            ]
            .into_iter()
            .map(|name| (name.into(), fixture(name, interface)))
            .collect(),
        );
        let mut registry = types::Registry::new(&provider);
        let loaded = discover_static(
            |loader, name| provider.resolve(loader, name),
            "p/Main",
            "run",
            Some("()I"),
            Some(&mut registry),
        )
        .unwrap();
        assert_eq!(
            loaded
                .iter()
                .map(|(class, _, _)| class.name.as_str())
                .collect::<Vec<_>>(),
            vec!["p/Concrete", "p/Helper", "p/I", "p/Main"]
        );
        assert!(
            !loaded
                .iter()
                .any(|(class, _, _)| class.name == "java/lang/Object")
        );
    }
}

#[test]
fn interface_slot_count_and_reserved_byte_are_verified_before_emission() {
    struct Links;
    impl numeric::StaticLinker for Links {
        fn resolve(&self, _: &ClassFile, _: u16) -> Result<(usize, numeric::Signature)> {
            anyhow::bail!("Unexpected static call")
        }
        fn class_id(&self, _: &ClassFile) -> Result<usize> {
            Ok(0)
        }
        fn object_class(&self, _: &ClassFile, _: &str) -> Result<usize> {
            Ok(0)
        }
        fn instance(&self, _: &ClassFile, _: u16, _: bool) -> Result<(usize, numeric::Signature)> {
            Ok((
                0,
                numeric::Signature {
                    arguments: vec![numeric::Type::LinkedObject(0)],
                    result: numeric::Type::Void,
                },
            ))
        }
        fn interface_call(&self, _: &ClassFile, _: u16) -> Result<numeric::InterfaceLink> {
            Ok((
                0,
                numeric::Signature {
                    arguments: vec![numeric::Type::LinkedObject(0), numeric::Type::I32],
                    result: numeric::Type::I32,
                },
                Vec::new(),
                Vec::new(),
            ))
        }
    }
    let mut class = ClassFile::parse(&fixture("p/Main", true)).unwrap();
    assert!(numeric::linked_dependencies(&class, &class.methods[0], &Links).is_ok());
    let index = class.methods[0]
        .code
        .as_ref()
        .unwrap()
        .bytes
        .iter()
        .position(|&b| b == 0xb9)
        .unwrap();
    class.methods[0].code.as_mut().unwrap().bytes[index + 3] = 3;
    assert!(numeric::linked_dependencies(&class, &class.methods[0], &Links).is_err());
    class.methods[0].code.as_mut().unwrap().bytes[index + 3] = 2;
    class.methods[0].code.as_mut().unwrap().bytes[index + 4] = 1;
    assert!(numeric::linked_dependencies(&class, &class.methods[0], &Links).is_err());
}

#[test]
fn supplied_but_inactive_definitions_do_not_discover_super_initializers() {
    use types::TypeProvider;
    let provider = Memory(
        [
            "java/lang/Object",
            "p/Main",
            "p/Concrete",
            "p/I",
            "p/Helper",
            "p/Unused",
            "p/Poison",
        ]
        .into_iter()
        .map(|name| (name.into(), fixture(name, true)))
        .collect(),
    );
    let mut registry = types::Registry::new(&provider);
    let loaded = discover_with_definitions(
        |loader, name| provider.resolve(loader, name),
        "p/Main",
        "run",
        Some("()I"),
        Some(&mut registry),
        "vanilla-application",
        &[("p/Unused".into(), "vanilla-application".into())],
        false,
        false,
        false,
    )
    .unwrap();
    assert!(loaded.iter().any(|(class, _, _)| class.name == "p/Unused"));
    assert!(!loaded.iter().any(|(class, _, _)| class.name == "p/Poison"));
}
