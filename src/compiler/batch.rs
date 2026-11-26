use super::{classfile::ClassFile, i32, managed, numeric};
use crate::{
    bytecode::{BytecodeProvider, ClassOrigin, VanillaBytecodeProvider},
    files,
    lock::InputLock,
    parallel,
};
use anyhow::{Context, Result};
use serde::Serialize;
use std::{
    collections::BTreeMap,
    fs::{self, File},
    path::{Path, PathBuf},
};

#[derive(Serialize)]
pub struct MethodResult {
    pub class: String,
    pub method: String,
    pub descriptor: String,
    pub supported: bool,
    pub reason: Option<String>,
    pub manifest: Option<PathBuf>,
}

#[derive(Serialize)]
pub struct BatchReport {
    pub backend: String,
    pub input_fingerprint: String,
    pub workers: usize,
    pub elapsed_ms: u128,
    pub classes: usize,
    pub candidate_methods: usize,
    pub supported_methods: usize,
    pub emitted_methods: usize,
    pub assembled: bool,
    pub full_game_ready: bool,
    pub results: Vec<MethodResult>,
}

/// Class tasks are independent. Method order and classpath precedence stay deterministic.
pub fn compile_set(
    inputs: &InputLock,
    output: &Path,
    jobs: usize,
    assemble: bool,
    numeric_backend: bool,
) -> Result<BatchReport> {
    let set = VanillaBytecodeProvider { inputs }.snapshot()?;
    fs::create_dir_all(output)?;
    let output = files::absolute(output)?;
    let origins: Vec<_> = set.classes.values().collect();
    // Avoid rebuilding a large ZIP central-directory index for every class.
    // Small JAR-local chunks retain load balancing without holding all class bytes.
    let mut jars: BTreeMap<&str, Vec<(usize, &ClassOrigin)>> = BTreeMap::new();
    for (index, origin) in origins.iter().enumerate() {
        jars.entry(&origin.source_id)
            .or_default()
            .push((index, origin));
    }
    let tasks: Vec<_> = jars
        .values()
        .flat_map(|entries| entries.chunks(256).map(|chunk| chunk.to_vec()))
        .collect();
    let work = parallel::ordered_map(&tasks, jobs, |_, task| -> Result<Vec<MethodResult>> {
        let mut archive =
            zip::ZipArchive::new(File::open(&inputs.file(&task[0].1.source_id)?.path)?)?;
        let mut task_results = Vec::new();
        for (class_index, origin) in task {
            let bytes = origin.read_from(&mut archive)?;
            let class = ClassFile::parse(&bytes)
                .with_context(|| format!("Cannot parse {}", origin.binary_name))?;
            let mut results = Vec::new();
            let source_directory = output.join(format!("classes/{class_index:06}"));
            let source = source_directory.join("input.class");
            for (index, method) in class.methods.iter().enumerate() {
                // The report covers all static int signatures, including rejected bodies/classes.
                let signature_supported = if numeric_backend {
                    numeric::Signature::parse(&method.descriptor).is_ok()
                } else {
                    i32::argument_count(&method.descriptor).is_ok()
                };
                if method.access & 8 == 0 || !signature_supported {
                    continue;
                }
                let check = if numeric_backend {
                    numeric::compile(&class, method).map(|_| ())
                } else {
                    i32::compile(&class, method).map(|_| ())
                };
                let mut entry = MethodResult {
                    class: origin.binary_name.clone(),
                    method: method.name.clone(),
                    descriptor: method.descriptor.clone(),
                    supported: check.is_ok(),
                    reason: check.as_ref().err().map(|error| format!("{error:#}")),
                    manifest: None,
                };
                if check.is_ok() {
                    if !source.exists() {
                        files::write_atomic(&source, &bytes)?;
                    }
                    let directory = source_directory.join(format!("method-{index:04}"));
                    if numeric_backend {
                        managed::compile(
                            &source,
                            &method.name,
                            Some(&method.descriptor),
                            &directory,
                            assemble,
                        )?;
                    } else {
                        super::compile(
                            &source,
                            &method.name,
                            Some(&method.descriptor),
                            &directory,
                            assemble,
                        )?;
                    }
                    entry.manifest = Some(directory.join("compilation.json"));
                }
                results.push(entry);
            }
            task_results.extend(results);
        }
        Ok(task_results)
    })?;
    // No success report is published if an input, assembler, or linker fails.
    let mut results = work
        .results
        .into_iter()
        .collect::<Result<Vec<_>>>()?
        .into_iter()
        .flatten()
        .collect::<Vec<_>>();
    results.sort_by(|a, b| {
        (&a.class, &a.method, &a.descriptor).cmp(&(&b.class, &b.method, &b.descriptor))
    });
    let report = BatchReport {
        backend: if numeric_backend {
            managed::BACKEND.into()
        } else {
            "boom-i32-v2-masm-x64".into()
        },
        input_fingerprint: inputs.fingerprint.clone(),
        workers: work.workers,
        elapsed_ms: work.elapsed_ms,
        classes: origins.len(),
        candidate_methods: results.len(),
        supported_methods: results.iter().filter(|m| m.supported).count(),
        emitted_methods: results.iter().filter(|m| m.manifest.is_some()).count(),
        assembled: assemble,
        full_game_ready: false,
        results,
    };
    files::write_atomic(
        &output.join("report.json"),
        &serde_json::to_vec_pretty(&report)?,
    )?;
    Ok(report)
}
