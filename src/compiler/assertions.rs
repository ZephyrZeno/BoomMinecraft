//! Frozen startup assertion configuration. This is compiler metadata, not a game runtime.
use super::types;
use serde::{Deserialize, Serialize};

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Policy {
    pub application_enabled: bool,
    pub system_enabled: bool,
}
impl Policy {
    pub(super) fn bits(self) -> u32 {
        u32::from(self.application_enabled) | (u32::from(self.system_enabled) << 1)
    }
    pub(super) fn status(self, ty: &types::Type) -> u32 {
        match ty {
            types::Type::Class { key, .. } => u32::from(if key.loader == "bootstrap" {
                self.system_enabled
            } else {
                self.application_enabled
            }),
            types::Type::Primitive { .. } | types::Type::Array { .. } => 0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn class(loader: &str) -> types::Type {
        types::Type::Class {
            key: types::ClassKey {
                loader: loader.into(),
                name: "p/T".into(),
            },
            origin: Box::new(crate::bytecode::ClassOrigin {
                generated: None,
                loader: loader.into(),
                binary_name: "p.T".into(),
                source_id: "fixture".into(),
                jar_entry: "p/T.class".into(),
                java_class_major: 65,
                sha256: "fixture".into(),
            }),
            access: 1,
            superclass: None,
            interfaces: Vec::new(),
        }
    }
    #[test]
    fn startup_flags_separate_application_and_system_types() {
        for application_enabled in [false, true] {
            for system_enabled in [false, true] {
                let policy = Policy {
                    application_enabled,
                    system_enabled,
                };
                assert_eq!(
                    policy.bits(),
                    u32::from(application_enabled) | (u32::from(system_enabled) << 1)
                );
                assert_eq!(
                    policy.status(&class("bootstrap")),
                    u32::from(system_enabled)
                );
                assert_eq!(
                    policy.status(&class("vanilla-application")),
                    u32::from(application_enabled)
                );
                assert_eq!(
                    policy.status(&class("explicit-application")),
                    u32::from(application_enabled)
                );
                assert_eq!(
                    policy.status(&types::Type::Primitive {
                        value: types::Primitive::Int
                    }),
                    0
                );
                assert_eq!(policy.status(&types::Type::Array { component: 0 }), 0);
            }
        }
        assert_eq!(Policy::default().bits(), 0);
    }
    #[test]
    fn serialized_policy_rejects_unknown_configuration() {
        let policy = Policy {
            application_enabled: true,
            system_enabled: false,
        };
        assert_eq!(
            serde_json::from_slice::<Policy>(&serde_json::to_vec(&policy).unwrap()).unwrap(),
            policy
        );
        assert!(
            serde_json::from_str::<Policy>(
                r#"{"application_enabled":true,"system_enabled":false,"permissive_fallback":true}"#
            )
            .is_err()
        );
    }
}
