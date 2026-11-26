use std::collections::BTreeMap;

use anyhow::{Result, ensure};
use regex::Regex;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct VersionMetadata {
    pub id: String,
    pub main_class: String,
    pub java_version: JavaVersion,
    pub downloads: BTreeMap<String, Download>,
    pub libraries: Vec<Library>,
    pub arguments: Arguments,
    pub asset_index: AssetIndex,
    #[serde(rename = "type")]
    pub version_type: String,
    #[serde(default)]
    pub logging: BTreeMap<String, Logging>,
    pub inherits_from: Option<String>,
}

impl VersionMetadata {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            self.id == crate::GAME_VERSION,
            "Only Minecraft {} is supported, got {}",
            crate::GAME_VERSION,
            self.id
        );
        ensure!(
            self.inherits_from.is_none(),
            "Inherited or modded version metadata is not supported in V0"
        );
        ensure!(
            self.java_version.major_version == crate::JAVA_MAJOR,
            "Unexpected Java requirement"
        );
        ensure!(
            self.main_class == "net.minecraft.client.main.Main",
            "Unexpected vanilla client entry point"
        );
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct JavaVersion {
    pub component: String,
    pub major_version: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Download {
    pub sha1: String,
    pub size: u64,
    pub url: String,
    pub path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssetIndex {
    pub id: String,
    pub sha1: String,
    pub size: u64,
    pub url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Library {
    pub name: String,
    #[serde(default)]
    pub rules: Vec<Rule>,
    pub downloads: LibraryDownloads,
    #[serde(default)]
    pub natives: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LibraryDownloads {
    pub artifact: Option<Download>,
    #[serde(default)]
    pub classifiers: BTreeMap<String, Download>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Logging {
    pub argument: String,
    pub file: LoggingFile,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoggingFile {
    pub id: String,
    pub sha1: String,
    pub size: u64,
    pub url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Arguments {
    pub game: Vec<Argument>,
    pub jvm: Vec<Argument>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Argument {
    Plain(String),
    Conditional {
        rules: Vec<Rule>,
        value: ArgumentValue,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum ArgumentValue {
    One(String),
    Many(Vec<String>),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Rule {
    pub action: Action,
    pub os: Option<OsRule>,
    #[serde(default)]
    pub features: BTreeMap<String, bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Action {
    Allow,
    Disallow,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OsRule {
    pub name: Option<String>,
    pub arch: Option<String>,
    pub version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Target {
    pub os: String,
    pub arch: String,
    pub os_version: Option<String>,
}

impl Target {
    pub fn windows_x64() -> Self {
        Self {
            os: "windows".into(),
            arch: "x86_64".into(),
            os_version: None,
        }
    }
}

pub fn rules_allow(
    rules: &[Rule],
    target: &Target,
    features: &BTreeMap<String, bool>,
) -> Result<bool> {
    let mut allowed = rules.is_empty();
    for rule in rules {
        if let Some(os) = &rule.os {
            if os.name.as_ref().is_some_and(|n| n != &target.os) {
                continue;
            }
            if let Some(arch) = &os.arch
                && !Regex::new(&format!("^(?:{arch})$"))?.is_match(&target.arch)
            {
                continue;
            }
            if let Some(version) = &os.version {
                let actual = target.os_version.as_ref().ok_or_else(|| {
                    anyhow::anyhow!("OS version is required to evaluate rule {version}")
                })?;
                if !Regex::new(version)?.is_match(actual) {
                    continue;
                }
            }
        }
        if rule
            .features
            .iter()
            .any(|(k, expected)| features.get(k).copied().unwrap_or(false) != *expected)
        {
            continue;
        }
        allowed = matches!(rule.action, Action::Allow);
    }
    Ok(allowed)
}

pub fn expand_arguments(
    arguments: &[Argument],
    target: &Target,
    features: &BTreeMap<String, bool>,
) -> Result<Vec<String>> {
    let mut result = Vec::new();
    for argument in arguments {
        match argument {
            Argument::Plain(value) => result.push(value.clone()),
            Argument::Conditional { rules, value } if rules_allow(rules, target, features)? => {
                match value {
                    ArgumentValue::One(value) => result.push(value.clone()),
                    ArgumentValue::Many(values) => result.extend(values.clone()),
                }
            }
            _ => (),
        }
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn rules_use_last_matching_action_and_default_disallow() {
        let rules: Vec<Rule> = serde_json::from_value(json!([
            {"action":"allow","os":{"name":"windows"}},
            {"action":"disallow","os":{"arch":"x86_64"}},
            {"action":"allow","features":{"custom":true}}
        ]))
        .unwrap();
        assert!(!rules_allow(&rules, &Target::windows_x64(), &BTreeMap::new()).unwrap());
        assert!(
            rules_allow(
                &rules,
                &Target::windows_x64(),
                &BTreeMap::from([("custom".into(), true)])
            )
            .unwrap()
        );
        let linux: Vec<Rule> =
            serde_json::from_value(json!([{"action":"allow","os":{"name":"linux"}}])).unwrap();
        assert!(!rules_allow(&linux, &Target::windows_x64(), &BTreeMap::new()).unwrap());
    }

    #[test]
    fn conditional_argument_arrays_preserve_order() {
        let args: Vec<Argument> = serde_json::from_value(json!(["first", {"rules":[{"action":"allow","features":{"demo":true}}],"value":["--demo","yes"]}, "last"])).unwrap();
        assert_eq!(
            expand_arguments(&args, &Target::windows_x64(), &BTreeMap::new()).unwrap(),
            ["first", "last"]
        );
    }
}
