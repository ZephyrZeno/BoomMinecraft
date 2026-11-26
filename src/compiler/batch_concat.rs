//! Standard concat protocol expansion, source Java conversion edges and MASM.
//! Bootstrap initialization remains a real source-class dependency.
use super::{
    batch_catalog::Catalog,
    batch_compile::{ASSEMBLY_BODY_BUDGET, AssemblyBodies, AssemblyUnit, Symbols, write_unit},
    batch_literals::StringShape,
    batch_types::Binding,
    classfile::DynamicSite,
    symbolic::{Constant, JavaType, MethodType},
    translation_plan::Artifact,
};
use crate::files;
use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    fmt::Write as _,
    fs,
    io::Write,
    path::Path,
};
use zip::{ZipWriter, write::SimpleFileOptions};

pub(super) const OWNER: &str = "java/lang/invoke/StringConcatFactory";
const STRING: &str = "Ljava/lang/String;";
#[derive(Clone, Serialize)]
pub struct Request {
    pub binding: Binding,
    pub class_sha256: String,
    pub source: DynamicSite,
    pub constants: BTreeMap<u16, Constant>,
    pub caller_methods: BTreeSet<usize>,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Part {
    Literal { utf16: Vec<u16> },
    Argument { index: usize, operation: u32 },
}
#[derive(Debug, Clone, Serialize)]
pub struct Conversion {
    pub argument: usize,
    pub method: usize,
    pub descriptor: String,
}
#[derive(Debug, Clone, Serialize)]
pub struct Plan {
    pub arguments: Vec<String>,
    pub parts: Vec<Part>,
    pub conversions: Vec<Conversion>,
}
#[derive(Serialize)]
pub struct Site {
    pub label: String,
    pub caller_class: usize,
    pub class_sha256: String,
    pub constant: u16,
    pub opcode: u8,
    pub descriptor: String,
    pub caller_methods: BTreeSet<usize>,
    pub source: DynamicSite,
    pub plan: Option<Plan>,
    pub diagnostic: Option<String>,
    pub assembly_unit: Option<usize>,
}
#[derive(Serialize)]
pub struct Bootstrap {
    pub class_id: usize,
    pub class_sha256: String,
    pub methods: BTreeMap<String, usize>,
    pub string_class: usize,
    pub string_sha256: String,
    pub conversion_methods: BTreeMap<String, usize>,
}
#[derive(Serialize)]
pub struct Summary {
    pub abi: u32,
    pub context_bytes: usize,
    pub pool_bytes: usize,
    pub sites: usize,
    pub generated_sites: usize,
    pub rejected_sites: usize,
    pub source_conversion_sites: usize,
    pub bootstrap: Bootstrap,
    pub source_layout: StringShape,
    pub index: Artifact,
    pub units: Vec<AssemblyUnit>,
    pub kernel_sha256: String,
    pub bootstrap_class_initialization_required: bool,
    pub bootstrap_class_initialization_executed: bool,
    pub active_roots_registered: bool,
    pub linked: bool,
    pub game_started: bool,
}
pub(super) fn recognizes(binding: &Binding) -> bool {
    binding.kind == "invokedynamic"
        && binding
            .protocol
            .as_ref()
            .is_some_and(|p| p.starts_with(&format!("{OWNER}.")))
}
pub(super) fn record(
    out: &mut BTreeMap<String, Request>,
    method: usize,
    sha: &str,
    binding: &Binding,
    constants: &BTreeMap<u16, Constant>,
) -> Result<()> {
    ensure!(
        recognizes(binding) && binding.opcode == 186,
        "Invalid concat source binding"
    );
    let Some(Constant::InvokeDynamic(source)) = constants.get(&binding.constant) else {
        anyhow::bail!("Concat binding lacks original invokedynamic");
    };
    let values = source
        .arguments
        .iter()
        .map(|i| {
            Ok((
                *i,
                constants
                    .get(i)
                    .context("Missing concat bootstrap constant")?
                    .clone(),
            ))
        })
        .collect::<Result<BTreeMap<_, _>>>()?;
    let old = out.entry(binding.label.clone()).or_insert_with(|| Request {
        binding: binding.clone(),
        class_sha256: sha.into(),
        source: source.clone(),
        constants: values.clone(),
        caller_methods: BTreeSet::new(),
    });
    ensure!(
        old.binding.caller_class == binding.caller_class
            && old.binding.constant == binding.constant
            && old.binding.descriptor == binding.descriptor
            && old.class_sha256 == sha
            && old.source == *source
            && old.constants == values,
        "Conflicting concat source site"
    );
    old.caller_methods.insert(method);
    Ok(())
}
fn descriptor(ty: &JavaType) -> String {
    match ty {
        JavaType::Boolean => "Z".into(),
        JavaType::Byte => "B".into(),
        JavaType::Char => "C".into(),
        JavaType::Short => "S".into(),
        JavaType::Int => "I".into(),
        JavaType::Long => "J".into(),
        JavaType::Float => "F".into(),
        JavaType::Double => "D".into(),
        JavaType::Void => "V".into(),
        JavaType::Object(n) => format!("L{n};"),
        JavaType::Array {
            dimensions,
            element,
        } => format!(
            "{}{}",
            "[".repeat(*dimensions as usize),
            descriptor(element)
        ),
    }
}
fn source_method(
    catalog: &Catalog,
    class: usize,
    name: &str,
    desc: &str,
    flags: u16,
) -> Result<usize> {
    let node = &catalog.nodes[class];
    let i = node
        .methods
        .iter()
        .position(|m| m.name == name && m.descriptor == desc)
        .with_context(|| format!("Missing source {}.{name}{desc}", node.key.name))?;
    ensure!(
        node.methods[i].access & 0x109 == flags && node.methods[i].access & 0x400 == 0,
        "Concat source conversion/bootstrap method flags differ"
    );
    Ok(node.method_ids[i])
}
fn bootstrap(catalog: &Catalog) -> Result<Bootstrap> {
    let class = catalog.lookup("bootstrap", OWNER)?;
    let string = catalog.lookup("bootstrap", "java/lang/String")?;
    for id in [class, string] {
        let n = &catalog.nodes[id];
        ensure!(
            n.origin.source_id == "jdk:java.base"
                && n.origin.generated.is_none()
                && n.access & 0x611 == 0x11,
            "Concat requires original final bootstrap classes"
        );
    }
    let mut methods = BTreeMap::new();
    for (name, desc) in [
        (
            "makeConcat",
            "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;",
        ),
        (
            "makeConcatWithConstants",
            "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/invoke/CallSite;",
        ),
    ] {
        methods.insert(name.into(), source_method(catalog, class, name, desc, 9)?);
    }
    let mut conversion_methods = BTreeMap::new();
    for ty in ["F", "D", "Ljava/lang/Object;"] {
        let desc = format!("({ty}){STRING}");
        conversion_methods.insert(
            ty.into(),
            source_method(catalog, string, "valueOf", &desc, 9)?,
        );
    }
    Ok(Bootstrap {
        class_id: class,
        class_sha256: catalog.nodes[class].origin.sha256.clone(),
        methods,
        string_class: string,
        string_sha256: catalog.nodes[string].origin.sha256.clone(),
        conversion_methods,
    })
}
pub(super) fn plan(
    source: &DynamicSite,
    constants: &BTreeMap<u16, Constant>,
    converters: &BTreeMap<String, usize>,
) -> Result<Plan> {
    let b = &source.bootstrap;
    ensure!(
        b.reference_kind == 6 && !b.interface && b.owner == OWNER,
        "Concat bootstrap handle differs"
    );
    let sig = MethodType::parse(&source.descriptor)?;
    ensure!(
        sig.result == JavaType::Object("java/lang/String".into()) && sig.parameter_slots() <= 200,
        "Concat result/argument slots unsupported"
    );
    let arguments: Vec<_> = sig.parameters.iter().map(descriptor).collect();
    let mut conversions = vec![];
    let operations: Vec<_> = sig
        .parameters
        .iter()
        .enumerate()
        .map(|(argument, ty)| match ty {
            JavaType::Byte | JavaType::Short | JavaType::Int => 1,
            JavaType::Long => 2,
            JavaType::Boolean => 3,
            JavaType::Char => 4,
            JavaType::Object(n) if n == "java/lang/String" => 5,
            _ => {
                let ty = match ty {
                    JavaType::Float => "F",
                    JavaType::Double => "D",
                    _ => "Ljava/lang/Object;",
                };
                conversions.push(Conversion {
                    argument,
                    method: converters[ty],
                    descriptor: format!("({ty}){STRING}"),
                });
                5
            }
        })
        .collect();
    let (recipe, values) = match (b.name.as_str(), b.descriptor.as_str()) {
        (
            "makeConcat",
            "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;",
        ) => {
            ensure!(
                source.arguments.is_empty(),
                "makeConcat has static arguments"
            );
            (vec![1; arguments.len()], vec![])
        }
        (
            "makeConcatWithConstants",
            "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/invoke/CallSite;",
        ) => {
            let mut it = source.arguments.iter();
            let Some(Constant::StringUtf16(recipe)) = it.next().and_then(|i| constants.get(i))
            else {
                anyhow::bail!("Concat recipe must be a static String");
            };
            let values = it
                .map(|i| match &constants[i] {
                    Constant::StringUtf16(v) => Ok(v.clone()),
                    _ => anyhow::bail!("Concat constant requires link-time String conversion"),
                })
                .collect::<Result<Vec<_>>>()?;
            (recipe.clone(), values)
        }
        _ => anyhow::bail!("Unknown concat bootstrap signature"),
    };
    let (mut dynamic, mut fixed) = (0, 0);
    let mut literal = vec![];
    let mut parts = vec![];
    for u in recipe {
        match u {
            1 => {
                if !literal.is_empty() {
                    parts.push(Part::Literal {
                        utf16: std::mem::take(&mut literal),
                    });
                }
                let operation = *operations
                    .get(dynamic)
                    .context("Extra concat argument marker")?;
                parts.push(Part::Argument {
                    index: dynamic,
                    operation,
                });
                dynamic += 1;
            }
            2 => {
                literal
                    .extend_from_slice(values.get(fixed).context("Extra concat constant marker")?);
                fixed += 1;
            }
            _ => literal.push(u),
        }
    }
    if !literal.is_empty() {
        parts.push(Part::Literal { utf16: literal });
    }
    ensure!(
        dynamic == arguments.len() && fixed == values.len() && parts.len() <= 65535,
        "Concat marker/part count differs"
    );
    Ok(Plan {
        arguments,
        parts,
        conversions,
    })
}
pub(super) fn body(label: &str, plan: &Plan, bsm: usize, shape: &StringShape) -> String {
    let mut out = format!(".const\nALIGN 8\n{label}_rows LABEL BYTE\n");
    if plan.parts.is_empty() {
        out.push_str(" DWORD 0,0\n QWORD 0,0\n");
    }
    for (i, part) in plan.parts.iter().enumerate() {
        match part {
            Part::Literal { utf16 } => out.push_str(&format!(
                " DWORD 0,0\n QWORD OFFSET {label}_text{i},{}\n",
                utf16.len()
            )),
            Part::Argument { index, operation } => {
                out.push_str(&format!(" DWORD {operation},{index}\n QWORD 0,0\n"))
            }
        }
    }
    for (i, part) in plan.parts.iter().enumerate() {
        if let Part::Literal { utf16 } = part {
            writeln!(out, "ALIGN 2\n{label}_text{i} LABEL WORD").unwrap();
            for chunk in utf16.chunks(16) {
                writeln!(
                    out,
                    " WORD {}",
                    chunk
                        .iter()
                        .map(|u| format!("0{u:04X}h"))
                        .collect::<Vec<_>>()
                        .join(",")
                )
                .unwrap();
            }
        }
    }
    writeln!(out,"ALIGN 8\n{label}_pool DWORD 04A434E43h,1,{},{}\n QWORD OFFSET {label}_rows,OFFSET boom_heap_ptr,OFFSET boom_layout{}\n DWORD {},{},{},{},1,0,32,0\n QWORD 0",plan.parts.len(),plan.arguments.len(),shape.class_id,shape.value_offset,shape.coder_offset,shape.hash_offset,shape.hash_is_zero_offset).unwrap();
    let frame = (80 + plan.arguments.len() * 8).div_ceil(16) * 16 + 8;
    writeln!(out,".code\n{label} PROC FRAME\n sub rsp,{frame}\n .allocstack {frame}\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n test rcx,rcx\n jz {label}_zero\n cmp DWORD PTR [rcx],0\n jne {label}_zero").unwrap();
    if !plan.arguments.is_empty() {
        writeln!(out," test rdx,rdx\n jnz {label}_args\n mov DWORD PTR [rcx],7\n jmp {label}_zero\n{label}_args:").unwrap();
    }
    writeln!(out," lea rcx,boom_class{bsm}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz {label}_zero\n mov r10,QWORD PTR [rsp+40]").unwrap();
    for i in 0..plan.arguments.len() {
        writeln!(
            out,
            " mov rax,QWORD PTR [r10+{}]\n mov QWORD PTR [rsp+{}],rax",
            i * 8,
            80 + i * 8
        )
        .unwrap();
    }
    for c in &plan.conversions {
        writeln!(out," mov rcx,QWORD PTR [rsp+32]\n lea rdx,[rsp+{}]\n call boom_m{}\n mov r10,QWORD PTR [rsp+32]\n cmp DWORD PTR [r10],0\n jne {label}_zero\n mov QWORD PTR [rsp+{}],rax",80+c.argument*8,c.method,80+c.argument*8).unwrap();
    }
    writeln!(out," mov rcx,QWORD PTR [rsp+32]\n lea rdx,[rsp+80]\n lea r8,{label}_pool\n call boom_java_concat\n add rsp,{frame}\n ret\n{label}_zero:\n xor eax,eax\n add rsp,{frame}\n ret\n{label} ENDP").unwrap();
    out
}
pub(super) fn generate(
    catalog: &Catalog,
    shape: &StringShape,
    requests: BTreeMap<String, Request>,
    output: &Path,
    assemble: bool,
) -> Result<(Summary, Vec<Request>)> {
    let bootstrap = bootstrap(catalog)?;
    let mut rejected = vec![];
    let mut sites = vec![];
    let mut bodies = AssemblyBodies::new(ASSEMBLY_BODY_BUDGET);
    for (label, request) in requests {
        let caller = &catalog.nodes[request.binding.caller_class];
        ensure!(
            caller.origin.sha256 == request.class_sha256,
            "Concat caller origin differs"
        );
        let result = (|| -> Result<Plan> {
            ensure!(
                catalog.lookup(&caller.key.loader, OWNER)? == bootstrap.class_id,
                "Concat bootstrap defining loader differs"
            );
            plan(
                &request.source,
                &request.constants,
                &bootstrap.conversion_methods,
            )
        })();
        let (plan, diagnostic, unit) = match result {
            Ok(p) => {
                let unit = bodies.push(&body(&label, &p, bootstrap.class_id, shape));
                (Some(p), None, Some(unit))
            }
            Err(e) => {
                rejected.push(request.clone());
                (None, Some(format!("{e:#}")), None)
            }
        };
        sites.push(Site {
            label,
            caller_class: request.binding.caller_class,
            class_sha256: request.class_sha256,
            constant: request.binding.constant,
            opcode: 186,
            descriptor: request.binding.descriptor,
            caller_methods: request.caller_methods,
            source: request.source,
            plan,
            diagnostic,
            assembly_unit: unit,
        });
    }
    let directory = output.join("string-concat");
    fs::create_dir_all(&directory)?;
    let mut units = vec![];
    for (id, body) in bodies.parts.into_iter().enumerate() {
        units.push(write_unit(
            &Symbols::new()?,
            &directory.join(format!("{id:04}.asm")),
            id,
            &body,
            assemble,
        )?);
    }
    let path = directory.join("index.zip");
    let mut temp = tempfile::NamedTempFile::new_in(&directory)?;
    {
        let mut zip = ZipWriter::new(temp.as_file_mut());
        zip.start_file(
            "sites.jsonl",
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )?;
        for site in &sites {
            serde_json::to_writer(&mut zip, site)?;
            zip.write_all(b"\n")?;
        }
        zip.finish()?;
    }
    temp.persist(&path).map_err(|e| e.error)?;
    let generated = sites.iter().filter(|s| s.plan.is_some()).count();
    Ok((
        Summary {
            abi: 1,
            context_bytes: 32,
            pool_bytes: 80,
            sites: sites.len(),
            generated_sites: generated,
            rejected_sites: rejected.len(),
            source_conversion_sites: sites
                .iter()
                .filter(|s| s.plan.as_ref().is_some_and(|p| !p.conversions.is_empty()))
                .count(),
            bootstrap,
            source_layout: shape.clone(),
            index: Artifact {
                path: path.display().to_string(),
                digest: files::digest(&path)?,
            },
            units,
            kernel_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/java_concat.asm"
            ))
            .sha256,
            bootstrap_class_initialization_required: true,
            bootstrap_class_initialization_executed: false,
            active_roots_registered: false,
            linked: false,
            game_started: false,
        },
        rejected,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::compiler::classfile::MethodHandle;
    fn converters() -> BTreeMap<String, usize> {
        BTreeMap::from([
            ("F".into(), 1),
            ("D".into(), 2),
            ("Ljava/lang/Object;".into(), 3),
        ])
    }
    fn site(
        desc: &str,
        recipe: Vec<u16>,
        constants: Vec<Constant>,
    ) -> (DynamicSite, BTreeMap<u16, Constant>) {
        let mut values = BTreeMap::from([(1, Constant::StringUtf16(recipe))]);
        for (i, v) in constants.into_iter().enumerate() {
            values.insert((i + 2) as u16, v);
        }
        let source = DynamicSite { name: "makeConcatWithConstants".into(), descriptor: desc.into(),
            bootstrap: MethodHandle { reference_kind: 6, interface: false, owner: OWNER.into(), name: "makeConcatWithConstants".into(),
            descriptor: "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/invoke/CallSite;".into() },
            arguments: values.keys().copied().collect() };
        (source, values)
    }
    #[test]
    fn source_reference_arrays_use_object_conversion_not_char_content() {
        let (s, c) = site("([CFD)Ljava/lang/String;", vec![1, 1, 1], vec![]);
        let p = plan(&s, &c, &converters()).unwrap();
        assert_eq!(
            p.conversions
                .iter()
                .map(|c| (c.argument, c.method))
                .collect::<Vec<_>>(),
            vec![(0, 3), (1, 1), (2, 2)]
        );
        assert_eq!(
            p.conversions[0].descriptor,
            "(Ljava/lang/Object;)Ljava/lang/String;"
        );
    }
    #[test]
    fn primitive_and_string_paths_need_no_source_conversion() {
        let (s, c) = site(
            "(BCSIJZLjava/lang/String;)Ljava/lang/String;",
            vec![1; 7],
            vec![],
        );
        let p = plan(&s, &c, &converters()).unwrap();
        assert!(p.conversions.is_empty());
        assert_eq!(
            p.parts,
            vec![1, 4, 1, 1, 2, 3, 5]
                .into_iter()
                .enumerate()
                .map(|(index, operation)| Part::Argument { index, operation })
                .collect::<Vec<_>>()
        );
    }
    #[test]
    fn static_marker_characters_and_surrogates_remain_literal_data() {
        let (s, c) = site(
            "(I)Ljava/lang/String;",
            vec![0, 0xd800, 2, 1, 0xdc00],
            vec![Constant::StringUtf16(vec![1, 2])],
        );
        let p = plan(&s, &c, &converters()).unwrap();
        assert_eq!(
            p.parts[0],
            Part::Literal {
                utf16: vec![0, 0xd800, 1, 2]
            }
        );
        assert_eq!(
            p.parts[2],
            Part::Literal {
                utf16: vec![0xdc00]
            }
        );
    }
    #[test]
    fn bootstrap_constant_conversion_is_not_guessed() {
        let (s, c) = site("(I)Ljava/lang/String;", vec![1, 2], vec![Constant::Int(42)]);
        assert!(
            plan(&s, &c, &converters())
                .unwrap_err()
                .to_string()
                .contains("link-time")
        );
    }
    #[test]
    fn dynamic_marker_arity_is_checked() {
        for recipe in [vec![], vec![1, 1]] {
            let (s, c) = site("(I)Ljava/lang/String;", recipe, vec![]);
            assert!(plan(&s, &c, &converters()).is_err());
        }
    }
    #[test]
    fn two_slot_arguments_respect_the_factory_limit() {
        for (n, ok) in [(100, true), (101, false)] {
            let (s, c) = site(
                &format!("({})Ljava/lang/String;", "J".repeat(n)),
                vec![1; n],
                vec![],
            );
            assert_eq!(plan(&s, &c, &converters()).is_ok(), ok);
        }
    }
    #[test]
    fn bootstrap_owner_signature_and_handle_are_exact() {
        for kind in [5, 9] {
            let (mut s, c) = site("()Ljava/lang/String;", vec![], vec![]);
            s.bootstrap.reference_kind = kind;
            assert!(plan(&s, &c, &converters()).is_err());
        }
        let (mut s, c) = site("()Ljava/lang/String;", vec![], vec![]);
        s.bootstrap.descriptor = "()V".into();
        assert!(plan(&s, &c, &converters()).is_err());
    }
}
