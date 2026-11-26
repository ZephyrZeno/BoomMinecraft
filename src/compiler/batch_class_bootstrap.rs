//! Source Class bootstrap natives. Registration confirms prelinked AOT entries;
//! unsupported declarations stay unprovided and cannot become zero-return stubs.
use super::{
    batch_catalog::Catalog,
    batch_classes,
    batch_compile::{AssemblyUnit, Symbols, write_unit},
    batch_metadata::{self, TypeRecord},
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeSet,
    fmt::Write as _,
    fs,
    io::{Read, Write},
    path::Path,
};
use zip::{ZipArchive, ZipWriter, write::SimpleFileOptions};

pub const SPECS: [(&str, &str, u16, u32); 3] = [
    ("registerNatives", "()V", 0x10a, 0),
    (
        "getPrimitiveClass",
        "(Ljava/lang/String;)Ljava/lang/Class;",
        0x108,
        10,
    ),
    ("desiredAssertionStatus0", "(Ljava/lang/Class;)Z", 0x10a, 11),
];
pub const PRIMITIVES: [(&str, &str); 9] = [
    ("Z", "boolean"),
    ("B", "byte"),
    ("C", "char"),
    ("S", "short"),
    ("I", "int"),
    ("J", "long"),
    ("F", "float"),
    ("D", "double"),
    ("V", "void"),
];

#[derive(Serialize, Deserialize, Clone)]
pub struct Method {
    pub method: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub operation: u32,
    pub assembly_unit: usize,
}
#[derive(Serialize, Deserialize, Clone)]
pub struct Primitive {
    pub descriptor: String,
    pub name: String,
    pub type_id: usize,
}
#[derive(Serialize, Deserialize, Clone)]
pub struct Registration {
    pub operation: u32,
    pub method: usize,
    pub access: u16,
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub pool_bytes: usize,
    pub native_methods: usize,
    pub class_id: usize,
    pub class_sha256: String,
    pub source_native_declarations: usize,
    pub registered_prelinked_methods: usize,
    pub registered_methods_are_subset: bool,
    pub unsupported_natives_remain_unprovided: bool,
    pub system_assertions_enabled: bool,
    pub application_assertions_enabled: bool,
    pub class_assertion_overrides_supported: bool,
    pub kernel_sha256: String,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub original_class_initialization_executed: bool,
    pub full_class_native_registration_complete: bool,
    pub game_started: bool,
}

pub(super) fn native_body(method: usize, class: usize, operation: u32) -> String {
    native_adapter(
        method,
        class,
        "boom_java_class_bootstrap_pool",
        "boom_java_class_bootstrap",
        operation,
    )
}

pub(super) fn native_adapter(
    method: usize,
    class: usize,
    pool: &str,
    service: &str,
    operation: u32,
) -> String {
    format!(
        ".code\nboom_m{method} PROC FRAME\n sub rsp,56\n .allocstack 56\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n test rcx,rcx\n jz boom_m{method}_zero\n cmp DWORD PTR [rcx],0\n jne boom_m{method}_zero\n lea rcx,boom_class{class}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz boom_m{method}_zero\n mov rcx,QWORD PTR [rsp+32]\n mov rdx,QWORD PTR [rsp+40]\n call boom_m{method}_native\n add rsp,56\n ret\nboom_m{method}_zero:\n xor eax,eax\n add rsp,56\n ret\nboom_m{method} ENDP\nboom_m{method}_native PROC\n lea r8,{pool}\n mov r9d,{operation}\n jmp {service}\nboom_m{method}_native ENDP\n"
    )
}

pub(super) fn data(
    class: usize,
    primitives: &[Primitive],
    registration: &[Registration],
) -> String {
    let mut out = String::from(
        ".const\nALIGN 8\nPUBLIC boom_java_class_bootstrap_natives\nboom_java_class_bootstrap_natives LABEL BYTE\n",
    );
    for row in registration {
        writeln!(
            out,
            " DWORD {},{}\n QWORD OFFSET boom_m{}_native\n DWORD {},0",
            row.operation, row.method, row.method, row.access
        )
        .unwrap();
    }
    out.push_str(
        "ALIGN 8\nPUBLIC boom_java_primitive_names\nboom_java_primitive_names LABEL BYTE\n",
    );
    for (i, row) in primitives.iter().enumerate() {
        writeln!(
            out,
            " QWORD OFFSET boom_java_primitive_name{i}\n DWORD {},{}",
            row.name.len(),
            row.type_id
        )
        .unwrap();
    }
    for (i, row) in primitives.iter().enumerate() {
        writeln!(
            out,
            "ALIGN 2\nboom_java_primitive_name{i} WORD {}",
            row.name
                .encode_utf16()
                .map(|u| u.to_string())
                .collect::<Vec<_>>()
                .join(",")
        )
        .unwrap();
    }
    writeln!(out,".data\nALIGN 8\nPUBLIC boom_java_class_bootstrap_pool\nboom_java_class_bootstrap_pool DWORD 04A434254h,1,0,{}\n QWORD OFFSET boom_java_class_pool,OFFSET boom_java_string_literal_pool,OFFSET boom_java_class_bootstrap_natives,OFFSET boom_java_primitive_names\n DWORD 9,0,0,0,{class},0\n QWORD 0",registration.len()).unwrap();
    out
}

pub(super) fn source_methods(catalog: &Catalog) -> Result<Vec<Method>> {
    let class_id = catalog.lookup("bootstrap", "java/lang/Class")?;
    let node = &catalog.nodes[class_id];
    ensure!(
        node.origin.source_id == "jdk:java.base"
            && node.origin.generated.is_none()
            && node.access == 0x31,
        "Class bootstrap requires original java.base Class"
    );
    let mut methods = Vec::new();
    for (name, desc, access, operation) in SPECS {
        let i = node
            .methods
            .iter()
            .position(|m| m.name == name && m.descriptor == desc)
            .context("Missing source Class bootstrap native")?;
        ensure!(
            node.methods[i].access == access,
            "Class bootstrap native access changed"
        );
        methods.push(Method {
            method: node.method_ids[i],
            class_id,
            class_sha256: node.origin.sha256.clone(),
            name: name.into(),
            descriptor: desc.into(),
            access,
            operation,
            assembly_unit: 0,
        });
    }
    Ok(methods)
}

pub(super) fn generate(
    catalog: &Catalog,
    metadata: &batch_metadata::Summary,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, BTreeSet<usize>)> {
    let class_id = catalog.lookup("bootstrap", "java/lang/Class")?;
    let node = &catalog.nodes[class_id];
    let methods = source_methods(catalog)?;
    let mut archive = ZipArchive::new(fs::File::open(&metadata.index.path)?)?;
    let mut text = String::new();
    archive.by_name("types.jsonl")?.read_to_string(&mut text)?;
    let types = text
        .lines()
        .map(serde_json::from_str::<TypeRecord>)
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let mut primitives = Vec::new();
    for (descriptor, name) in PRIMITIVES {
        let matches: Vec<_> = types
            .iter()
            .filter(|t| t.kind == 0 && t.name == descriptor)
            .collect();
        ensure!(matches.len() == 1, "Primitive source type identity differs");
        primitives.push(Primitive {
            descriptor: descriptor.into(),
            name: name.into(),
            type_id: matches[0].id,
        });
    }
    let mut registration = Vec::new();
    for (owner, name, desc, access, operation) in batch_classes::SPECS {
        if owner != "java/lang/Class" {
            continue;
        }
        let i = node
            .methods
            .iter()
            .position(|m| m.name == name && m.descriptor == desc)
            .context("Missing prelinked Class native")?;
        ensure!(
            node.methods[i].access == access,
            "Prelinked Class native flags differ"
        );
        registration.push(Registration {
            operation,
            method: node.method_ids[i],
            access,
        });
    }
    registration.extend(
        methods
            .iter()
            .filter(|m| m.operation != 0)
            .map(|m| Registration {
                operation: m.operation,
                method: m.method,
                access: m.access,
            }),
    );
    registration.sort_by_key(|r| r.operation);
    ensure!(
        registration.len() == 10,
        "Class prelinked table shape differs"
    );
    let mut assembly = data(class_id, &primitives, &registration);
    for method in &methods {
        assembly.push_str(&native_body(method.method, class_id, method.operation));
    }
    let directory = output.join("class-bootstrap");
    fs::create_dir_all(&directory)?;
    let unit = write_unit(
        &Symbols::new()?,
        &directory.join("0000.asm"),
        0,
        &assembly,
        assemble,
    )?;
    let path = directory.join("index.zip");
    let mut temporary = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut z = ZipWriter::new(temporary.as_file_mut());
        let options =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, rows) in [
            ("methods.jsonl", serde_json::to_value(&methods)?),
            ("primitives.jsonl", serde_json::to_value(&primitives)?),
            ("registration.jsonl", serde_json::to_value(&registration)?),
        ] {
            z.start_file(name, options)?;
            for row in rows.as_array().context("Invalid Class bootstrap records")? {
                serde_json::to_writer(&mut z, row)?;
                z.write_all(b"\n")?;
            }
        }
        z.finish()?;
    }
    temporary.persist(&path).map_err(|e| e.error)?;
    let provided = methods.iter().map(|m| m.method).collect();
    Ok((
        Summary {
            abi: 1,
            context_bytes: 32,
            pool_bytes: 80,
            native_methods: 3,
            class_id,
            class_sha256: node.origin.sha256.clone(),
            source_native_declarations: node
                .methods
                .iter()
                .filter(|m| m.access & 0x100 != 0)
                .count(),
            registered_prelinked_methods: 10,
            registered_methods_are_subset: true,
            unsupported_natives_remain_unprovided: true,
            system_assertions_enabled: false,
            application_assertions_enabled: false,
            class_assertion_overrides_supported: false,
            kernel_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/java_class_bootstrap.asm"
            ))
            .sha256,
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units: vec![unit],
            original_class_initialization_executed: false,
            full_class_native_registration_complete: false,
            game_started: false,
        },
        provided,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bootstrap_wrappers_keep_real_class_initialization_and_pending_error() {
        let b = native_body(7, 8, 0);
        assert!(b.contains("call boom_class_ensure32") && b.contains("jne boom_m7_zero"));
        assert!(
            b.find("call boom_class_ensure32").unwrap() < b.find("call boom_m7_native").unwrap()
        );
        assert!(!b.contains("mov DWORD PTR [boom_class8+8],2"));
    }
    #[test]
    fn names_and_registration_are_separate_from_java_object_fields() {
        let p = vec![Primitive {
            descriptor: "I".into(),
            name: "int".into(),
            type_id: 99,
        }];
        let r = vec![Registration {
            operation: 10,
            method: 7,
            access: 0x10a,
        }];
        let d = data(8, &p, &r);
        assert!(d.contains("DWORD 10,7\n QWORD OFFSET boom_m7_native\n DWORD 266,0"));
        assert!(d.contains("WORD 105,110,116") && d.contains("DWORD 3,99"));
        assert!(!d.contains("boom_class8"));
    }
}
