//! Automatic, source-bound virtual/interface contracts and compatibility worklist.
//! Rust plans immutable metadata offline; every guest invocation runs MASM.
use super::{
    batch_catalog::{Catalog, Layout},
    batch_compile::{ASSEMBLY_BODY_BUDGET, AssemblyBodies, AssemblyUnit, Symbols, write_unit},
    batch_types::{Binding, Universe, VirtualCall},
    hierarchy::{self, Member, Metadata, Selection},
    translation_plan::Artifact,
};
use crate::{files, parallel};
use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt::Write as _,
    fs,
    path::Path,
};
use zip::{ZipWriter, write::SimpleFileOptions};

#[derive(Debug, Serialize)]
pub struct Site {
    pub label: String,
    pub caller_class: usize,
    pub class_sha256: String,
    pub constant: u16,
    pub opcode: u8,
    pub descriptor: String,
    pub resolved_method: usize,
    pub dispatch: VirtualCall,
    pub caller_methods: BTreeSet<usize>,
    pub table: Option<usize>,
    pub assembly_unit: Option<usize>,
    pub diagnostic: Option<String>,
}
#[derive(Default, Serialize)]
struct Gap {
    kind: String,
    protocol: String,
    native_method: Option<usize>,
    symbols: BTreeSet<String>,
    affected_methods: BTreeSet<usize>,
    examples: BTreeMap<String, Binding>,
}
#[derive(Default)]
pub(super) struct Requests {
    sites: BTreeMap<String, Site>,
    gaps: BTreeMap<(String, String), Gap>,
    emitted: BTreeSet<usize>,
    pub(super) array_clones: BTreeMap<String, super::batch_array_clone::Site>,
    pub(super) class_literals: BTreeMap<String, super::batch_classes::Site>,
    pub(super) concat_sites: BTreeMap<String, super::batch_concat::Request>,
    provided_natives: BTreeSet<usize>,
}
impl Requests {
    pub(super) fn resolve_native_methods(&mut self, provided: &BTreeSet<usize>) {
        self.provided_natives.extend(provided);
        self.gaps.retain(|_, gap| {
            !gap.native_method
                .is_some_and(|method| provided.contains(&method))
        });
    }
    pub(super) fn record(
        &mut self,
        method: usize,
        sha256: &str,
        bindings: &[Binding],
        constants: &BTreeMap<u16, super::symbolic::Constant>,
    ) -> Result<()> {
        self.emitted.insert(method);
        for binding in bindings {
            if super::batch_concat::recognizes(binding) {
                super::batch_concat::record(
                    &mut self.concat_sites,
                    method,
                    sha256,
                    binding,
                    constants,
                )?;
                continue;
            }
            if binding.kind == "string_literal_resolution" {
                continue;
            }
            if binding.kind == "literal_resolution"
                && binding.protocol.as_deref() == Some("java/lang/Class")
            {
                super::batch_classes::record(&mut self.class_literals, method, sha256, binding)?;
                continue;
            }
            if binding.kind == "array_clone" {
                super::batch_array_clone::record(&mut self.array_clones, method, sha256, binding)?;
                continue;
            }
            if binding.kind == "virtual_dispatch" {
                let spec = binding
                    .dispatch
                    .clone()
                    .context("Virtual binding has no selection contract")?;
                let resolved = binding
                    .resolved_method
                    .context("Virtual binding has no resolved member")?;
                let site = self
                    .sites
                    .entry(binding.label.clone())
                    .or_insert_with(|| Site {
                        label: binding.label.clone(),
                        caller_class: binding.caller_class,
                        class_sha256: sha256.into(),
                        constant: binding.constant,
                        opcode: binding.opcode,
                        descriptor: binding.descriptor.clone(),
                        resolved_method: resolved,
                        dispatch: spec.clone(),
                        caller_methods: BTreeSet::new(),
                        table: None,
                        assembly_unit: None,
                        diagnostic: None,
                    });
                ensure!(
                    site.caller_class == binding.caller_class
                        && site.class_sha256 == sha256
                        && site.constant == binding.constant
                        && site.opcode == binding.opcode
                        && site.descriptor == binding.descriptor
                        && site.resolved_method == resolved
                        && site.dispatch == spec,
                    "Conflicting virtual call-site identity"
                );
                site.caller_methods.insert(method);
            } else {
                let protocol = if binding.kind == "native_declaration" {
                    format!(
                        "native:{}",
                        binding
                            .resolved_method
                            .context("Native binding has no declaration")?
                    )
                } else {
                    binding
                        .protocol
                        .clone()
                        .unwrap_or_else(|| binding.kind.clone())
                };
                let gap = self
                    .gaps
                    .entry((binding.kind.clone(), protocol.clone()))
                    .or_insert_with(|| Gap {
                        kind: binding.kind.clone(),
                        protocol,
                        native_method: (binding.kind == "native_declaration")
                            .then_some(binding.resolved_method)
                            .flatten(),
                        ..Gap::default()
                    });
                gap.symbols.insert(binding.label.clone());
                gap.affected_methods.insert(method);
                if gap.examples.len() < 6 {
                    gap.examples
                        .entry(binding.label.clone())
                        .or_insert_with(|| binding.clone());
                }
            }
        }
        Ok(())
    }
    pub(super) fn merge(&mut self, other: Self) -> Result<()> {
        for (label, site) in other.concat_sites {
            ensure!(
                self.concat_sites.insert(label, site).is_none(),
                "Concat source class occurs in multiple shards"
            );
        }
        for (label, site) in other.class_literals {
            ensure!(
                self.class_literals.insert(label, site).is_none(),
                "Class literal source class occurs in multiple shards"
            );
        }
        for (label, site) in other.array_clones {
            ensure!(
                self.array_clones.insert(label, site).is_none(),
                "Array clone source class occurs in multiple shards"
            );
        }
        for (key, site) in other.sites {
            ensure!(
                self.sites.insert(key, site).is_none(),
                "A virtual source class occurs in multiple shards"
            );
        }
        for (key, gap) in other.gaps {
            if let Some(old) = self.gaps.get_mut(&key) {
                old.symbols.extend(gap.symbols);
                old.affected_methods.extend(gap.affected_methods);
                for (name, binding) in gap.examples {
                    if old.examples.len() < 6 {
                        old.examples.entry(name).or_insert(binding);
                    }
                }
            } else {
                self.gaps.insert(key, gap);
            }
        }
        self.emitted.extend(other.emitted);
        Ok(())
    }
    pub(super) fn reject_concat(
        &mut self,
        requests: Vec<super::batch_concat::Request>,
    ) -> Result<()> {
        for r in requests {
            let binding = r.binding;
            let protocol = binding
                .protocol
                .clone()
                .context("Concat rejection lacks protocol")?;
            let gap = self
                .gaps
                .entry(("invokedynamic".into(), protocol.clone()))
                .or_insert_with(|| Gap {
                    kind: "invokedynamic".into(),
                    protocol,
                    native_method: None,
                    ..Gap::default()
                });
            gap.symbols.insert(binding.label.clone());
            gap.affected_methods.extend(r.caller_methods);
            if gap.examples.len() < 6 {
                gap.examples.entry(binding.label.clone()).or_insert(binding);
            }
        }
        Ok(())
    }
}
#[derive(Debug, Serialize)]
pub struct Row {
    pub receiver: usize,
    pub target: Option<usize>,
    pub error: u32,
}
#[derive(Serialize)]
pub struct Table {
    pub id: usize,
    pub resolved_method: usize,
    pub interface: bool,
    pub rows: Vec<Row>,
    pub array_target: Option<usize>,
    pub array_error: u32,
    pub assembly_unit: Option<usize>,
    pub diagnostic: Option<String>,
}
#[derive(Serialize)]
pub struct Target {
    pub method: usize,
    pub class_id: usize,
    pub defining_loader: String,
    pub class_sha256: String,
    pub owner: String,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub java_assembly_emitted: bool,
    pub native_binding_provided: bool,
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub virtual_sites: usize,
    pub generated_sites: usize,
    pub shared_tables: usize,
    pub generated_tables: usize,
    pub receiver_rows: usize,
    pub java_targets_emitted: usize,
    pub java_targets_missing: usize,
    pub native_targets_unbound: usize,
    pub pending_contract_groups: usize,
    pub pending_contract_symbols: usize,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub kernel_sha256: String,
    pub class_initialization_performed_by_dispatch: bool,
    pub linked: bool,
    pub runtime_abi_verified: bool,
    pub game_started: bool,
}
fn target(
    catalog: &Catalog,
    owners: &[(usize, usize)],
    id: usize,
    emitted: &BTreeSet<usize>,
) -> Result<Target> {
    let &(class_id, index) = owners.get(id).context("Invalid dispatch target ID")?;
    let node = &catalog.nodes[class_id];
    let method = &node.methods[index];
    Ok(Target {
        method: id,
        class_id,
        defining_loader: node.key.loader.clone(),
        class_sha256: node.origin.sha256.clone(),
        owner: node.key.name.clone(),
        name: method.name.clone(),
        descriptor: method.descriptor.clone(),
        access: method.access,
        java_assembly_emitted: emitted.contains(&id),
        native_binding_provided: false,
    })
}
fn selection_row(catalog: &Catalog, receiver: usize, selection: Selection) -> Result<Row> {
    let (target, error) = match selection {
        Selection::Method { member } => (Some(catalog.declared_method_id(&member)?), 0),
        Selection::IncompatibleClassChange => (None, 13),
        Selection::AbstractMethod => (None, 14),
        Selection::IllegalAccess => (None, 15),
    };
    Ok(Row {
        receiver,
        target,
        error,
    })
}
fn table_body(table: &Table) -> Result<String> {
    let id = table.id;
    let array = table
        .array_target
        .map_or_else(|| "0".into(), |m| format!("OFFSET boom_m{m}"));
    let mut body = format!(
        ".const\nALIGN 8\nPUBLIC boom_batch_vtable{id}\nboom_batch_vtable{id} DWORD 056445350h,1,{},0\n QWORD OFFSET boom_batch_vrows{id},{array}\n DWORD {},0\nboom_batch_vrows{id} LABEL BYTE\n",
        table.rows.len(),
        table.array_error
    );
    for row in &table.rows {
        let target = row
            .target
            .map_or_else(|| "0".into(), |m| format!("OFFSET boom_m{m}"));
        writeln!(
            body,
            " DWORD {},{}\n QWORD {target}",
            row.receiver, row.error
        )?;
    }
    Ok(body)
}
fn site_body(site: &Site, table: usize) -> String {
    format!(
        ".const\nALIGN 8\nboom_batch_vconstraints_{} QWORD OFFSET boom_t{},OFFSET boom_t{}\n.code\n{} PROC\n lea r8,boom_batch_vtable{table}\n lea r9,boom_batch_vconstraints_{}\n jmp boom_batch_virtual_invoke\n{} ENDP\n",
        site.label,
        site.dispatch.symbolic_owner,
        site.dispatch.receiver_constraint,
        site.label,
        site.label,
        site.label
    )
}
fn write_entry<T: Serialize>(
    zip: &mut ZipWriter<&mut fs::File>,
    name: &str,
    rows: impl Iterator<Item = T>,
) -> Result<()> {
    use std::io::Write;
    zip.start_file(
        name,
        SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
    )?;
    for row in rows {
        serde_json::to_writer(&mut *zip, &row)?;
        zip.write_all(b"\n")?;
    }
    Ok(())
}
pub(super) fn generate(
    catalog: &Catalog,
    universe: &Universe,
    layouts: &[Layout],
    mut requests: Requests,
    output: &Path,
    assemble: bool,
    workers: usize,
) -> Result<Summary> {
    let mut owners = vec![(usize::MAX, usize::MAX); catalog.methods];
    for node in &catalog.nodes {
        for (index, &id) in node.method_ids.iter().enumerate() {
            owners[id] = (node.id, index);
        }
    }
    // One inverted ancestry pass, rather than a whole-image scan per call site.
    let mut receivers = vec![vec![]; catalog.nodes.len()];
    for node in &catalog.nodes {
        if node.access & 0x200 != 0 || layouts[node.id].candidate.is_none() {
            continue;
        }
        for &ancestor in catalog.ancestors(node.id)? {
            receivers[ancestor].push(node.id);
        }
    }
    let mut keys = BTreeMap::new();
    for site in requests.sites.values() {
        ensure!(
            site.dispatch.receiver_constraint < catalog.nodes.len() + universe.arrays.len(),
            "Invalid receiver constraint"
        );
        let key = (site.resolved_method, site.dispatch.interface);
        let &(owner, index) = owners
            .get(key.0)
            .context("Invalid resolved dispatch method")?;
        ensure!(
            owner == site.dispatch.resolved_owner && index == site.dispatch.resolved_index,
            "Dispatch declaration identity differs from source"
        );
        keys.entry(key).or_insert_with(|| site.dispatch.clone());
    }
    let ordered = keys.into_iter().collect::<Vec<_>>();
    let planned = parallel::ordered_map(
        &ordered,
        workers,
        |id, ((method_id, interface), spec)| -> Result<Table> {
            let node = &catalog.nodes[spec.resolved_owner];
            let m = &node.methods[spec.resolved_index];
            let member = Member {
                owner: node.id,
                index: spec.resolved_index,
                name: m.name.clone(),
                descriptor: m.descriptor.clone(),
                access: m.access,
            };
            let mut rows = vec![];
            let result = (|| -> Result<()> {
                for &receiver in &receivers[node.id] {
                    rows.push(selection_row(
                        catalog,
                        receiver,
                        hierarchy::select_method(catalog, receiver, node.id, &member, *interface)?,
                    )?);
                }
                Ok(())
            })();
            let diagnostic = result.err().map(|e| format!("{e:#}"));
            if diagnostic.is_some() {
                rows.clear();
            }
            let array_target = (node.id == catalog.root_object()?
                && member.access & (8 | 0x400) == 0
                && (!*interface || member.access & 1 != 0))
                .then_some(*method_id);
            Ok(Table {
                id,
                resolved_method: *method_id,
                interface: *interface,
                rows,
                array_target,
                array_error: if array_target.is_some() { 0 } else { 13 },
                assembly_unit: None,
                diagnostic,
            })
        },
    )?;
    let mut tables = planned.results.into_iter().collect::<Result<Vec<_>>>()?;
    let table_ids = ordered
        .iter()
        .enumerate()
        .map(|(id, (key, _))| (*key, id))
        .collect::<BTreeMap<_, _>>();
    let mut bodies = AssemblyBodies::new(ASSEMBLY_BODY_BUDGET);
    let kernel = include_str!("../../native/kernels/batch_virtual_dispatch.inc");
    if !tables.is_empty() {
        bodies.push(kernel);
    }
    let mut used_targets = BTreeSet::new();
    for table in &mut tables {
        if table.diagnostic.is_none() {
            table.assembly_unit = Some(bodies.push(&table_body(table)?));
            used_targets.extend(table.rows.iter().filter_map(|r| r.target));
            used_targets.extend(table.array_target);
        }
    }
    for site in requests.sites.values_mut() {
        let id = table_ids[&(site.resolved_method, site.dispatch.interface)];
        site.table = Some(id);
        site.diagnostic.clone_from(&tables[id].diagnostic);
        if site.diagnostic.is_none() {
            site.assembly_unit = Some(bodies.push(&site_body(site, id)));
        }
    }
    let mut targets = BTreeMap::new();
    for method in used_targets {
        let mut record = target(catalog, &owners, method, &requests.emitted)?;
        record.native_binding_provided = requests.provided_natives.contains(&method);
        targets.insert(method, record);
    }
    for gap in requests.gaps.values_mut() {
        if let Some(method) = gap.native_method {
            let t = target(catalog, &owners, method, &requests.emitted)?;
            gap.protocol = format!(
                "{}:{}.{}{}",
                t.defining_loader, t.owner, t.name, t.descriptor
            );
        }
    }
    let directory = output.join("dispatch");
    fs::create_dir_all(&directory)?;
    eprintln!(
        "Automatic dispatch: {} sites, {} shared selection tables, {} receiver rows; other protocols remain in compatibility index",
        requests.sites.len(),
        tables.len(),
        tables.iter().map(|t| t.rows.len()).sum::<usize>()
    );
    let generated = parallel::ordered_map(&bodies.parts, workers, |id, body| {
        write_unit(
            &Symbols::new()?,
            &directory.join(format!("{id:04}.asm")),
            id,
            body,
            assemble,
        )
    })?;
    let units = generated.results.into_iter().collect::<Result<Vec<_>>>()?;
    let path = directory.join("index.zip");
    let mut temp = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut zip = ZipWriter::new(temp.as_file_mut());
        write_entry(&mut zip, "sites.jsonl", requests.sites.values())?;
        write_entry(&mut zip, "tables.jsonl", tables.iter())?;
        write_entry(&mut zip, "targets.jsonl", targets.values())?;
        write_entry(&mut zip, "gaps.jsonl", requests.gaps.values())?;
        zip.finish()?;
    }
    temp.persist(&path).map_err(|e| e.error)?;
    Ok(Summary {
        abi: 1,
        context_bytes: 32,
        virtual_sites: requests.sites.len(),
        generated_sites: requests
            .sites
            .values()
            .filter(|s| s.assembly_unit.is_some())
            .count(),
        shared_tables: tables.len(),
        generated_tables: tables.iter().filter(|t| t.assembly_unit.is_some()).count(),
        receiver_rows: tables.iter().map(|t| t.rows.len()).sum(),
        java_targets_emitted: targets.values().filter(|t| t.java_assembly_emitted).count(),
        java_targets_missing: targets
            .values()
            .filter(|t| !t.java_assembly_emitted && t.access & 0x100 == 0)
            .count(),
        native_targets_unbound: targets
            .values()
            .filter(|t| t.access & 0x100 != 0 && !t.native_binding_provided)
            .count(),
        pending_contract_groups: requests.gaps.len(),
        pending_contract_symbols: requests
            .gaps
            .values()
            .flat_map(|g| g.symbols.iter())
            .collect::<BTreeSet<_>>()
            .len(),
        index: Artifact {
            path: path.display().to_string(),
            digest: files::digest(&path)?,
        },
        units,
        kernel_sha256: files::digest_bytes(kernel.as_bytes()).sha256,
        class_initialization_performed_by_dispatch: false,
        linked: false,
        runtime_abi_verified: false,
        game_started: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn source_call_sites_share_tables_but_keep_protected_receiver_constraints() {
        let binding = |method| Binding {
            label: "boom_batch_call_3_7_182".into(),
            kind: "virtual_dispatch".into(),
            caller_class: 3,
            caller_method: method,
            constant: 7,
            opcode: 182,
            resolved_method: Some(12),
            descriptor: "()I".into(),
            implemented: false,
            dispatch: Some(VirtualCall {
                symbolic_owner: 1,
                receiver_constraint: 3,
                resolved_owner: 1,
                resolved_index: 2,
                interface: false,
            }),
            protocol: None,
            array_type: None,
            literal_type: None,
        };
        let mut requests = Requests::default();
        requests
            .record(4, "hash", &[binding(4)], &BTreeMap::new())
            .unwrap();
        requests
            .record(5, "hash", &[binding(5)], &BTreeMap::new())
            .unwrap();
        assert_eq!(requests.sites.len(), 1);
        let site = &requests.sites["boom_batch_call_3_7_182"];
        assert_eq!(site.caller_methods, BTreeSet::from([4, 5]));
        assert!(site_body(site, 2).contains("QWORD OFFSET boom_t1,OFFSET boom_t3"));
        let mut changed = binding(6);
        changed.dispatch.as_mut().unwrap().receiver_constraint = 1;
        assert!(
            requests
                .record(6, "hash", &[changed], &BTreeMap::new())
                .is_err()
        );
    }
    #[test]
    fn table_targets_use_method_envelopes_and_keep_native_dependencies_real() {
        let table = Table {
            id: 7,
            resolved_method: 8,
            interface: false,
            rows: vec![
                Row {
                    receiver: 2,
                    target: Some(11),
                    error: 0,
                },
                Row {
                    receiver: 4,
                    target: None,
                    error: 14,
                },
            ],
            array_target: Some(8),
            array_error: 0,
            assembly_unit: None,
            diagnostic: None,
        };
        let body = table_body(&table).unwrap();
        assert!(body.contains("OFFSET boom_m11") && !body.contains("boom_m11_body"));
        assert!(body.contains("DWORD 4,14\n QWORD 0"));
        let (module, _, _) = Symbols::new().unwrap().module(&body);
        assert!(module.contains("EXTERN boom_m11:BYTE"));
        assert!(!module.contains("boom_m11 PROC"));
    }
}
