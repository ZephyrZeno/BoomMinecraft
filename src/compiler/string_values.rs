//! Primitive decimal/String bindings; formatting and allocation execute as MASM.
use super::{classfile::ClassFile, concat, numeric, types};
use crate::bytecode::ClassOrigin;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Kind {
    Boolean,
    Char,
    Int,
    Long,
    IntegerToString,
    LongToString,
}
impl Kind {
    pub(super) fn resolve(owner: &str, name: &str, descriptor: &str) -> Option<Self> {
        match (owner, name, descriptor) {
            ("java/lang/String", "valueOf", "(Z)Ljava/lang/String;") => Some(Self::Boolean),
            ("java/lang/String", "valueOf", "(C)Ljava/lang/String;") => Some(Self::Char),
            ("java/lang/String", "valueOf", "(I)Ljava/lang/String;") => Some(Self::Int),
            ("java/lang/String", "valueOf", "(J)Ljava/lang/String;") => Some(Self::Long),
            ("java/lang/Integer", "toString", "(I)Ljava/lang/String;") => {
                Some(Self::IntegerToString)
            }
            ("java/lang/Long", "toString", "(J)Ljava/lang/String;") => Some(Self::LongToString),
            _ => None,
        }
    }
    pub(super) fn descriptor(self) -> &'static str {
        match self {
            Self::Boolean => "(Z)Ljava/lang/String;",
            Self::Char => "(C)Ljava/lang/String;",
            Self::Int | Self::IntegerToString => "(I)Ljava/lang/String;",
            Self::Long | Self::LongToString => "(J)Ljava/lang/String;",
        }
    }
    pub(super) fn owner(self) -> &'static str {
        match self {
            Self::IntegerToString => "java/lang/Integer",
            Self::LongToString => "java/lang/Long",
            _ => "java/lang/String",
        }
    }
    pub(super) fn method(self) -> &'static str {
        if matches!(self, Self::IntegerToString | Self::LongToString) {
            "toString"
        } else {
            "valueOf"
        }
    }
    pub(super) fn initialization_owner(self) -> Option<&'static str> {
        match self {
            Self::Int | Self::IntegerToString => Some("java/lang/Integer"),
            Self::Long | Self::LongToString => Some("java/lang/Long"),
            _ => None,
        }
    }
    pub(super) fn signature(self) -> numeric::Signature {
        numeric::Signature {
            arguments: vec![if matches!(self, Self::Long | Self::LongToString) {
                numeric::Type::I64
            } else {
                numeric::Type::I32
            }],
            result: numeric::Type::BootstrapString,
        }
    }
    pub(super) fn concat(self) -> Option<concat::Plan> {
        let value = match self {
            Self::Boolean => return None,
            Self::Char => concat::Argument::Char,
            Self::Int | Self::IntegerToString => concat::Argument::Int,
            Self::Long | Self::LongToString => concat::Argument::Long,
        };
        Some(concat::Plan {
            descriptor: self.descriptor().into(),
            arguments: vec![value],
            parts: vec![concat::Part::Argument { index: 0, value }],
        })
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub kind: Kind,
    pub caller: ClassOrigin,
    pub constant: u16,
    pub origin: ClassOrigin,
    pub concat_plan: Option<usize>,
    pub boolean_literals: Option<[usize; 2]>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub initializer: Option<Initialization>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Initialization {
    pub class_id: usize,
    pub origin: ClassOrigin,
}
pub(super) struct Source {
    pub origin: ClassOrigin,
    pub initializer: Option<ClassOrigin>,
}
pub(super) enum Link {
    Concat(usize, numeric::Signature, Option<usize>),
    Boolean([usize; 2]),
}
fn member(
    registry: &mut types::Registry<'_>,
    owner: &str,
    name: &str,
    descriptor: &str,
) -> Result<ClassOrigin> {
    let id = registry.class("bootstrap", owner)?;
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
            && access & 0x211 == 0x11,
        "Primitive string conversion needs its original final bootstrap class"
    );
    let origin = origin.as_ref().clone();
    let class = registry
        .definition(id)
        .context("Missing primitive conversion definition")?;
    let method = class.method(name, Some(descriptor))?;
    ensure!(
        method.access == 9 && method.code.is_some(),
        "Primitive string conversion member contract changed"
    );
    Ok(origin)
}
pub(super) fn source(registry: &mut types::Registry<'_>, kind: Kind) -> Result<Source> {
    let origin = member(registry, kind.owner(), kind.method(), kind.descriptor())?;
    let id = registry.class("bootstrap", kind.owner())?;
    let class = registry
        .definition(id)
        .context("Missing conversion definition")?;
    if kind == Kind::Boolean {
        boolean_literals(class)?;
    }
    if matches!(kind, Kind::Int | Kind::Long) {
        delegation(class, kind)?;
    }
    let initializer = kind
        .initialization_owner()
        .map(|owner| member(registry, owner, "toString", kind.descriptor()))
        .transpose()?;
    Ok(Source {
        origin,
        initializer,
    })
}
fn delegation(class: &ClassFile, kind: Kind) -> Result<()> {
    let code = class
        .method("valueOf", Some(kind.descriptor()))?
        .code
        .as_ref()
        .context("Missing valueOf Code")?;
    let b = &code.bytes;
    ensure!(
        code.handlers.is_empty()
            && b.len() == 5
            && b[0] == if kind == Kind::Long { 0x1e } else { 0x1a }
            && b[1] == 0xb8
            && b[4] == 0xb0,
        "Numeric valueOf requires its original direct decimal delegation"
    );
    let (owner, name, descriptor, interface) =
        class.static_method_reference(u16::from_be_bytes([b[2], b[3]]))?;
    ensure!(
        Some(owner.as_str()) == kind.initialization_owner()
            && name == "toString"
            && descriptor == kind.descriptor()
            && !interface,
        "Numeric valueOf delegation target changed"
    );
    Ok(())
}
fn boolean_literals(class: &ClassFile) -> Result<()> {
    let code = class
        .method("valueOf", Some(Kind::Boolean.descriptor()))?
        .code
        .as_ref()
        .context("Missing boolean valueOf Code")?;
    let b = &code.bytes;
    ensure!(
        b.len() == 14
            && code.handlers.is_empty()
            && b[0..5] == [0x1a, 0x99, 0, 9, 0x13]
            && b[7..11] == [0xa7, 0, 6, 0x13]
            && b[13] == 0xb0,
        "Boolean valueOf literal identity requires the verified two-literal Java body"
    );
    let t = u16::from_be_bytes([b[5], b[6]]);
    let f = u16::from_be_bytes([b[11], b[12]]);
    ensure!(
        class.string_literal(t)? == Some("true".encode_utf16().collect())
            && class.string_literal(f)? == Some("false".encode_utf16().collect()),
        "Boolean valueOf no longer returns the expected literals"
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture(name: &str, kind: Kind, access: u16, final_string: bool, truth: &str) -> Vec<u8> {
        let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 17];
        fn utf(b: &mut Vec<u8>, s: &str) {
            b.push(1);
            b.extend((s.len() as u16).to_be_bytes());
            b.extend(s.as_bytes());
        }
        utf(&mut b, name);
        b.extend([7, 0, 1]);
        utf(&mut b, "java/lang/Object");
        b.extend([7, 0, 3]);
        for s in [
            if name == "java/lang/String" {
                "valueOf"
            } else {
                "toString"
            },
            kind.descriptor(),
            "Code",
            truth,
        ] {
            utf(&mut b, s);
        }
        b.extend([8, 0, 8]);
        utf(&mut b, "false");
        b.extend([8, 0, 10]);
        utf(
            &mut b,
            kind.initialization_owner().unwrap_or("java/lang/Integer"),
        );
        b.extend([7, 0, 12]);
        utf(&mut b, "toString");
        b.extend([12, 0, 14, 0, 6, 10, 0, 13, 0, 15]);
        let target = name == kind.owner() || Some(name) == kind.initialization_owner();
        for n in [
            if target && final_string {
                0x31u16
            } else {
                0x21
            },
            2,
            if name == "java/lang/Object" { 0 } else { 4 },
            0,
            0,
            u16::from(target),
        ] {
            b.extend(n.to_be_bytes());
        }
        if target {
            for n in [access, 5, 6, u16::from(access & 0x100 == 0)] {
                b.extend(n.to_be_bytes());
            }
            if access & 0x100 == 0 {
                let code = if kind == Kind::Boolean {
                    vec![0x1a, 0x99, 0, 9, 0x13, 0, 9, 0xa7, 0, 6, 0x13, 0, 11, 0xb0]
                } else if name == "java/lang/String" && matches!(kind, Kind::Int | Kind::Long) {
                    vec![
                        if kind == Kind::Long { 0x1e } else { 0x1a },
                        0xb8,
                        0,
                        16,
                        0xb0,
                    ]
                } else {
                    vec![0x01, 0xb0]
                };
                b.extend(7u16.to_be_bytes());
                b.extend((12u32 + code.len() as u32).to_be_bytes());
                b.extend(1u16.to_be_bytes());
                b.extend(
                    (if matches!(kind, Kind::Long | Kind::LongToString) {
                        2u16
                    } else {
                        1
                    })
                    .to_be_bytes(),
                );
                b.extend((code.len() as u32).to_be_bytes());
                b.extend(code);
                b.extend([0, 0, 0, 0]);
            }
        }
        b.extend([0, 0]);
        b
    }
    struct Provider {
        kind: Kind,
        access: u16,
        final_string: bool,
        loader: &'static str,
        truth: &'static str,
    }
    impl types::TypeProvider for Provider {
        fn resolve(&self, _: &str, name: &str) -> Result<(Vec<u8>, ClassOrigin)> {
            let bytes = fixture(name, self.kind, self.access, self.final_string, self.truth);
            Ok((
                bytes.clone(),
                ClassOrigin {
                    generated: None,
                    loader: if name == self.kind.owner()
                        || Some(name) == self.kind.initialization_owner()
                    {
                        self.loader
                    } else {
                        "bootstrap"
                    }
                    .into(),
                    binary_name: name.replace('/', "."),
                    source_id: "jdk:java.base".into(),
                    jar_entry: format!("{name}.class"),
                    java_class_major: 65,
                    sha256: crate::files::digest_bytes(&bytes).sha256,
                },
            ))
        }
    }
    #[test]
    fn primitive_value_bindings_keep_exact_members_and_bootstrap_identity() {
        for kind in [
            Kind::Boolean,
            Kind::Char,
            Kind::Int,
            Kind::Long,
            Kind::IntegerToString,
            Kind::LongToString,
        ] {
            for (access, final_string, loader, valid) in [
                (9, true, "bootstrap", true),
                (8, true, "bootstrap", false),
                (0x109, true, "bootstrap", false),
                (9, false, "bootstrap", false),
                (9, true, "application", false),
            ] {
                let p = Provider {
                    kind,
                    access,
                    final_string,
                    loader,
                    truth: "true",
                };
                assert_eq!(
                    source(&mut types::Registry::new(&p), kind).is_ok(),
                    valid,
                    "{kind:?}/{access:x}/{loader}"
                );
            }
            assert_eq!(
                Kind::resolve(kind.owner(), kind.method(), kind.descriptor()),
                Some(kind)
            );
            assert_eq!(kind.concat().is_none(), kind == Kind::Boolean);
        }
        assert!(Kind::resolve("app/String", "valueOf", Kind::Char.descriptor()).is_none());
        assert!(Kind::resolve("java/lang/String", "valueOf", "(F)Ljava/lang/String;").is_none());
    }
    #[test]
    fn numeric_valueof_keeps_the_exact_wrapper_initialization_obligation() {
        for kind in [Kind::Int, Kind::Long] {
            let mut bytes = fixture("java/lang/String", kind, 9, true, "true");
            delegation(&ClassFile::parse(&bytes).unwrap(), kind).unwrap();
            let opcode = if kind == Kind::Long { 0x1e } else { 0x1a };
            let offset = bytes
                .windows(5)
                .position(|v| v == [opcode, 0xb8, 0, 16, 0xb0])
                .unwrap();
            bytes[offset] = 0;
            assert!(delegation(&ClassFile::parse(&bytes).unwrap(), kind).is_err());
            let mut bytes = fixture("java/lang/String", kind, 9, true, "true");
            let owner = kind.initialization_owner().unwrap().as_bytes();
            let offset = bytes.windows(owner.len()).position(|v| v == owner).unwrap();
            bytes[offset] = b'x';
            assert!(delegation(&ClassFile::parse(&bytes).unwrap(), kind).is_err());
        }
    }
    #[test]
    fn boolean_literal_identity_requires_the_actual_literal_return_body() {
        let p = Provider {
            kind: Kind::Boolean,
            access: 9,
            final_string: true,
            loader: "bootstrap",
            truth: "changed",
        };
        assert!(source(&mut types::Registry::new(&p), Kind::Boolean).is_err());
        let mut bytes = fixture("java/lang/String", Kind::Boolean, 9, true, "true");
        let b = ClassFile::parse(&bytes).unwrap();
        boolean_literals(&b).unwrap();
        let offset = bytes
            .windows(14)
            .position(|v| v == [0x1a, 0x99, 0, 9, 0x13, 0, 9, 0xa7, 0, 6, 0x13, 0, 11, 0xb0])
            .unwrap();
        bytes[offset] = 0x00;
        assert!(boolean_literals(&ClassFile::parse(&bytes).unwrap()).is_err());
    }
}
