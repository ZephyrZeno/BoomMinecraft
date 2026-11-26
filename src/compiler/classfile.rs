use anyhow::{Context, Result, bail, ensure};

#[derive(Debug)]
enum Constant {
    Utf8(Vec<u8>),
    Integer(i32),
    Float(u32),
    Long(i64),
    Double(u64),
    Class(u16),
    StringLiteral(u16),
    FieldRef(u16, u16),
    MethodRef(u16, u16),
    InterfaceMethodRef(u16, u16),
    MethodHandle(u8, u16),
    MethodType(u16),
    Dynamic(u16, u16),
    InvokeDynamic(u16, u16),
    NameAndType(u16, u16),
    Module(u16),
    Package(u16),
    Other,
}

#[derive(Debug)]
pub struct ClassFile {
    pub name: String,
    pub super_name: String,
    pub access: u16,
    pub interfaces: u16,
    pub interface_names: Vec<String>,
    pub fields: u16,
    pub field_info: Vec<Field>,
    pub major: u16,
    pub methods: Vec<Method>,
    pub module: Option<ModuleDescriptor>,
    pub nest_host: Option<String>,
    pub nest_members: Option<Vec<String>>,
    pub source_file: Option<String>,
    pub inner_simple_name: Option<String>,
    pub inner_class_entry: bool,
    pub declaring_class: Option<String>,
    pub enclosing_class: Option<String>,
    pub record_components: Option<Vec<(String, String)>>,
    method_reflection: Vec<ReflectionMetadata>,
    constants: Vec<Constant>,
    bootstrap_methods: Vec<BootstrapMethod>,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct ModuleRequire {
    pub module: String,
    pub flags: u16,
    pub version: Option<String>,
}
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct ModuleExport {
    pub package: String,
    pub flags: u16,
    pub targets: Vec<String>,
}
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct ModuleProvide {
    pub service: String,
    pub providers: Vec<String>,
}
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct ModuleDescriptor {
    pub name: String,
    pub flags: u16,
    pub version: Option<String>,
    pub requires: Vec<ModuleRequire>,
    pub exports: Vec<ModuleExport>,
    pub opens: Vec<ModuleExport>,
    pub uses: Vec<String>,
    pub provides: Vec<ModuleProvide>,
    pub packages: Vec<String>,
    pub resolution_flags: u16,
    pub target: Option<String>,
    pub main_class: Option<String>,
}

fn module_name(constants: &[Constant], index: u16) -> Result<String> {
    let Some(Constant::Module(name)) = constants.get(index as usize) else {
        bail!("Expected Module constant at index {index}")
    };
    text(constants, *name)
}
fn package_name(constants: &[Constant], index: u16) -> Result<String> {
    let Some(Constant::Package(name)) = constants.get(index as usize) else {
        bail!("Expected Package constant at index {index}")
    };
    text(constants, *name)
}
fn optional_text(constants: &[Constant], index: u16) -> Result<Option<String>> {
    if index == 0 {
        Ok(None)
    } else {
        Ok(Some(text(constants, index)?))
    }
}
fn unique<T: Ord>(values: impl IntoIterator<Item = T>) -> bool {
    let mut seen = std::collections::BTreeSet::new();
    values.into_iter().all(|value| seen.insert(value))
}
fn module_attribute(constants: &[Constant], bytes: &[u8]) -> Result<ModuleDescriptor> {
    let mut r = Reader::new(bytes);
    let name = module_name(constants, r.u16()?)?;
    let flags = r.u16()?;
    ensure!(flags & !0x9020 == 0, "Invalid module flags");
    let version = optional_text(constants, r.u16()?)?;
    let mut requires = Vec::new();
    for _ in 0..r.u16()? {
        let module = module_name(constants, r.u16()?)?;
        let flags = r.u16()?;
        ensure!(
            flags & !0x9060 == 0 && module != name,
            "Invalid module requires flags or self dependency"
        );
        requires.push(ModuleRequire {
            module,
            flags,
            version: optional_text(constants, r.u16()?)?,
        });
    }
    let mut directives = || -> Result<Vec<ModuleExport>> {
        let mut result = Vec::new();
        for _ in 0..r.u16()? {
            let package = package_name(constants, r.u16()?)?;
            let flags = r.u16()?;
            ensure!(flags & !0x9000 == 0, "Invalid module package flags");
            let mut targets = Vec::new();
            for _ in 0..r.u16()? {
                targets.push(module_name(constants, r.u16()?)?);
            }
            ensure!(unique(&targets), "Duplicate module directive targets");
            result.push(ModuleExport {
                package,
                flags,
                targets,
            });
        }
        ensure!(
            unique(result.iter().map(|entry| &entry.package)),
            "Duplicate module package directive"
        );
        Ok(result)
    };
    let exports = directives()?;
    let opens = directives()?;
    ensure!(
        flags & 0x20 == 0 || opens.is_empty(),
        "Open module has explicit opens directives"
    );
    let mut uses = Vec::new();
    for _ in 0..r.u16()? {
        uses.push(class_name(constants, r.u16()?)?);
    }
    let mut provides = Vec::new();
    for _ in 0..r.u16()? {
        let service = class_name(constants, r.u16()?)?;
        let count = r.u16()?;
        ensure!(count != 0, "Module provides needs an implementation");
        let mut providers = Vec::new();
        for _ in 0..count {
            providers.push(class_name(constants, r.u16()?)?);
        }
        ensure!(
            unique(&providers),
            "Duplicate module service implementation"
        );
        provides.push(ModuleProvide { service, providers });
    }
    r.finish()?;
    ensure!(
        unique(requires.iter().map(|r| &r.module))
            && unique(&uses)
            && unique(provides.iter().map(|p| &p.service)),
        "Duplicate module requires/uses/provides"
    );
    ensure!(
        if name == "java.base" {
            requires.is_empty()
        } else {
            requires
                .iter()
                .any(|r| r.module == "java.base" && r.flags & 0x60 == 0)
        },
        "Module must require java.base without static/transitive flags; java.base cannot require other modules"
    );
    Ok(ModuleDescriptor {
        name,
        flags,
        version,
        requires,
        exports,
        opens,
        uses,
        provides,
        packages: Vec::new(),
        resolution_flags: 0,
        target: None,
        main_class: None,
    })
}
#[derive(Debug)]
struct BootstrapMethod {
    handle: u16,
    arguments: Vec<u16>,
}
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct MethodHandle {
    pub reference_kind: u8,
    pub owner: String,
    pub name: String,
    pub descriptor: String,
    pub interface: bool,
}
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct DynamicSite {
    pub name: String,
    pub descriptor: String,
    pub bootstrap: MethodHandle,
    pub arguments: Vec<u16>,
}

#[derive(Debug, Clone)]
pub struct Field {
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub constant_value: Option<u16>,
}

#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct ReflectionMetadata {
    pub signature: Option<String>,
    pub exceptions: Vec<String>,
    pub annotations: Vec<u8>,
    pub parameter_annotations: Vec<u8>,
    pub type_annotations: Vec<u8>,
    pub parameters: Vec<u8>,
}
#[derive(Debug)]
pub struct Method {
    pub name: String,
    pub descriptor: String,
    pub access: u16,
    pub code: Option<Code>,
    pub line_numbers: Vec<LineNumber>,
    pub runtime_visible_annotations: Vec<String>,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct LineNumber {
    pub pc: u16,
    pub line: u16,
}

#[derive(Debug)]
pub struct Code {
    pub max_stack: u16,
    pub max_locals: u16,
    pub bytes: Vec<u8>,
    pub handlers: Vec<ExceptionHandler>,
}

/// Code exception entries retain their original order; the first matching row wins.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExceptionHandler {
    pub start_pc: u16,
    pub end_pc: u16,
    pub handler_pc: u16,
    /// None is the JVM catch-all entry (catch_type == 0).
    pub catch_type: Option<String>,
}

#[derive(Debug, Clone, Copy)]
pub enum NumericConstant {
    Int(i32),
    Float(u32),
    Long(i64),
    Double(u64),
}

struct Reader<'a> {
    bytes: &'a [u8],
    position: usize,
}

impl<'a> Reader<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, position: 0 }
    }
    fn take(&mut self, count: usize) -> Result<&'a [u8]> {
        let end = self
            .position
            .checked_add(count)
            .context("Class file length overflow")?;
        let value = self
            .bytes
            .get(self.position..end)
            .with_context(|| format!("Truncated class file at byte {}", self.position))?;
        self.position = end;
        Ok(value)
    }
    fn u8(&mut self) -> Result<u8> {
        Ok(self.take(1)?[0])
    }
    fn u16(&mut self) -> Result<u16> {
        Ok(u16::from_be_bytes(self.take(2)?.try_into()?))
    }
    fn u32(&mut self) -> Result<u32> {
        Ok(u32::from_be_bytes(self.take(4)?.try_into()?))
    }
    fn finish(&self) -> Result<()> {
        ensure!(
            self.position == self.bytes.len(),
            "Unexpected trailing class data"
        );
        Ok(())
    }
}

fn annotation(constants: &[Constant], r: &mut Reader<'_>, depth: usize) -> Result<String> {
    ensure!(depth < 64, "Annotation nesting exceeds parser budget");
    let name = text(constants, r.u16()?)?;
    ensure!(
        name.starts_with('L') && name.ends_with(';'),
        "Invalid annotation descriptor"
    );
    let mut names = std::collections::BTreeSet::new();
    for _ in 0..r.u16()? {
        ensure!(
            names.insert(text(constants, r.u16()?)?),
            "Duplicate annotation element"
        );
        annotation_value(constants, r, depth + 1)?;
    }
    Ok(name)
}
fn annotation_value(constants: &[Constant], r: &mut Reader<'_>, depth: usize) -> Result<()> {
    ensure!(depth < 64, "Annotation nesting exceeds parser budget");
    match r.u8()? {
        b'B' | b'C' | b'I' | b'S' | b'Z' => ensure!(
            matches!(constants.get(r.u16()? as usize), Some(Constant::Integer(_))),
            "Invalid integer annotation constant"
        ),
        b'D' => ensure!(
            matches!(constants.get(r.u16()? as usize), Some(Constant::Double(_))),
            "Invalid double annotation constant"
        ),
        b'F' => ensure!(
            matches!(constants.get(r.u16()? as usize), Some(Constant::Float(_))),
            "Invalid float annotation constant"
        ),
        b'J' => ensure!(
            matches!(constants.get(r.u16()? as usize), Some(Constant::Long(_))),
            "Invalid long annotation constant"
        ),
        b's' | b'c' => {
            text(constants, r.u16()?)?;
        }
        b'e' => {
            text(constants, r.u16()?)?;
            text(constants, r.u16()?)?;
        }
        b'@' => {
            annotation(constants, r, depth + 1)?;
        }
        b'[' => {
            for _ in 0..r.u16()? {
                annotation_value(constants, r, depth + 1)?;
            }
        }
        _ => bail!("Invalid annotation element tag"),
    }
    Ok(())
}
fn text(constants: &[Constant], index: u16) -> Result<String> {
    let Some(Constant::Utf8(bytes)) = constants.get(index as usize) else {
        bail!("Expected UTF8 constant at index {index}")
    };
    // Decode names only; unrelated Java string constants can use modified UTF8.
    Ok(std::str::from_utf8(bytes)
        .context("Non-UTF8 identifiers are outside the current subset")?
        .to_owned())
}

fn class_name(constants: &[Constant], index: u16) -> Result<String> {
    let Some(Constant::Class(name)) = constants.get(index as usize) else {
        bail!("Expected Class constant at index {index}")
    };
    text(constants, *name)
}

impl ClassFile {
    /// Raw constant category for whole-input planning; no execution permission.
    pub fn constant_tag(&self, index: u16) -> Result<u8> {
        Ok(
            match self
                .constants
                .get(index as usize)
                .context("Invalid constant index")?
            {
                Constant::Utf8(_) => 1,
                Constant::Integer(_) => 3,
                Constant::Float(_) => 4,
                Constant::Long(_) => 5,
                Constant::Double(_) => 6,
                Constant::Class(_) => 7,
                Constant::StringLiteral(_) => 8,
                Constant::FieldRef(..) => 9,
                Constant::MethodRef(..) => 10,
                Constant::InterfaceMethodRef(..) => 11,
                Constant::NameAndType(..) => 12,
                Constant::MethodHandle(..) => 15,
                Constant::MethodType(_) => 16,
                Constant::Dynamic(..) => 17,
                Constant::InvokeDynamic(..) => 18,
                Constant::Module(_) => 19,
                Constant::Package(_) => 20,
                Constant::Other => bail!("Unusable wide constant slot"),
            },
        )
    }
    pub fn reflection_metadata(&self, method: usize) -> Result<&ReflectionMetadata> {
        self.method_reflection
            .get(method)
            .context("Missing method reflection metadata")
    }

    pub fn class_literal(&self, index: u16) -> Result<Option<String>> {
        if matches!(self.constants.get(index as usize), Some(Constant::Class(_))) {
            return Ok(Some(self.constant_class(index)?));
        }
        Ok(None)
    }
    pub fn string_literal(&self, index: u16) -> Result<Option<Vec<u16>>> {
        let Some(Constant::StringLiteral(utf8)) = self.constants.get(index as usize) else {
            return Ok(None);
        };
        let Some(Constant::Utf8(bytes)) = self.constants.get(*utf8 as usize) else {
            bail!("String literal does not reference UTF8")
        };
        Ok(Some(modified_utf16(bytes)?))
    }
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        ensure!(
            bytes.len() <= 16 * 1024 * 1024,
            "Class file exceeds compiler limit"
        );
        let mut reader = Reader::new(bytes);
        ensure!(reader.u32()? == 0xcafebabe, "Invalid Java class magic");
        let minor = reader.u16()?;
        let major = reader.u16()?;
        ensure!(
            (45..=65).contains(&major) && minor != 65535,
            "Only non-preview class versions up to Java 21 are supported"
        );
        let count = reader.u16()? as usize;
        ensure!(count > 0, "Empty constant pool");
        let mut constants = vec![Constant::Other];
        while constants.len() < count {
            let tag = reader.u8()?;
            let value = match tag {
                1 => {
                    let size = reader.u16()? as usize;
                    Constant::Utf8(reader.take(size)?.to_vec())
                }
                3 => Constant::Integer(reader.u32()? as i32),
                4 => Constant::Float(reader.u32()?),
                7 => Constant::Class(reader.u16()?),
                9 => Constant::FieldRef(reader.u16()?, reader.u16()?),
                10 => Constant::MethodRef(reader.u16()?, reader.u16()?),
                11 => Constant::InterfaceMethodRef(reader.u16()?, reader.u16()?),
                12 => Constant::NameAndType(reader.u16()?, reader.u16()?),
                17 => {
                    ensure!(major >= 55, "Dynamic constant requires Java 11");
                    Constant::Dynamic(reader.u16()?, reader.u16()?)
                }
                18 => {
                    ensure!(major >= 51, "InvokeDynamic requires Java 7");
                    Constant::InvokeDynamic(reader.u16()?, reader.u16()?)
                }
                5 | 6 => {
                    let bits = u64::from_be_bytes(reader.take(8)?.try_into()?);
                    ensure!(constants.len() + 1 < count, "Invalid two-slot constant");
                    constants.push(if tag == 5 {
                        Constant::Long(bits as i64)
                    } else {
                        Constant::Double(bits)
                    });
                    Constant::Other
                }
                8 => Constant::StringLiteral(reader.u16()?),
                16 => {
                    ensure!(major >= 51, "MethodType requires Java 7");
                    Constant::MethodType(reader.u16()?)
                }
                19 | 20 => {
                    ensure!(major >= 53, "Module/Package constant requires Java 9");
                    let name = reader.u16()?;
                    if tag == 19 {
                        Constant::Module(name)
                    } else {
                        Constant::Package(name)
                    }
                }
                15 => {
                    ensure!(major >= 51, "MethodHandle requires Java 7");
                    Constant::MethodHandle(reader.u8()?, reader.u16()?)
                }
                _ => bail!("Unknown constant pool tag {tag}"),
            };
            constants.push(value);
        }
        let access = reader.u16()?;
        let name = class_name(&constants, reader.u16()?)?;
        let super_index = reader.u16()?;
        let super_name = if super_index == 0 {
            String::new()
        } else {
            class_name(&constants, super_index)?
        };
        let interfaces = reader.u16()?;
        let mut interface_names = Vec::new();
        for _ in 0..interfaces {
            interface_names.push(class_name(&constants, reader.u16()?)?);
        }
        let fields = reader.u16()?;
        let mut field_info = Vec::new();
        for _ in 0..fields {
            let access = reader.u16()?;
            let name = text(&constants, reader.u16()?)?;
            let descriptor = text(&constants, reader.u16()?)?;
            let mut constant_value = None;
            for _ in 0..reader.u16()? {
                let attribute = text(&constants, reader.u16()?)?;
                let size = reader.u32()? as usize;
                let content = reader.take(size)?;
                if attribute == "ConstantValue" {
                    ensure!(
                        size == 2 && constant_value.is_none(),
                        "Malformed or duplicate ConstantValue"
                    );
                    constant_value = Some(u16::from_be_bytes(content.try_into()?));
                }
            }
            field_info.push(Field {
                access,
                name,
                descriptor,
                constant_value,
            });
        }
        let method_count = reader.u16()?;
        let mut methods = Vec::new();
        let mut method_reflection = Vec::new();
        for _ in 0..method_count {
            let access = reader.u16()?;
            let name = text(&constants, reader.u16()?)?;
            let descriptor = text(&constants, reader.u16()?)?;
            let attributes = reader.u16()?;
            let mut code = None;
            let mut line_numbers = Vec::new();
            let mut runtime_visible_annotations = None;
            let mut reflection = ReflectionMetadata::default();
            let mut reflection_seen = std::collections::BTreeSet::new();
            for _ in 0..attributes {
                let attribute = text(&constants, reader.u16()?)?;
                let size = reader.u32()? as usize;
                let content = reader.take(size)?;
                if matches!(
                    attribute.as_str(),
                    "Signature"
                        | "Exceptions"
                        | "RuntimeVisibleAnnotations"
                        | "RuntimeVisibleParameterAnnotations"
                        | "RuntimeVisibleTypeAnnotations"
                        | "MethodParameters"
                ) {
                    ensure!(
                        reflection_seen.insert(attribute.clone()),
                        "Duplicate method reflection attribute"
                    );
                    match attribute.as_str() {
                        "Signature" => {
                            ensure!(content.len() == 2, "Malformed method Signature");
                            reflection.signature =
                                Some(text(&constants, u16::from_be_bytes(content.try_into()?))?);
                        }
                        "Exceptions" => {
                            let mut r = Reader::new(content);
                            for _ in 0..r.u16()? {
                                reflection
                                    .exceptions
                                    .push(class_name(&constants, r.u16()?)?);
                            }
                            r.finish()?;
                        }
                        "RuntimeVisibleAnnotations" => reflection.annotations = content.to_vec(),
                        "RuntimeVisibleParameterAnnotations" => {
                            reflection.parameter_annotations = content.to_vec()
                        }
                        "RuntimeVisibleTypeAnnotations" => {
                            reflection.type_annotations = content.to_vec()
                        }
                        "MethodParameters" => reflection.parameters = content.to_vec(),
                        _ => unreachable!(),
                    }
                }
                if attribute == "RuntimeVisibleAnnotations" {
                    ensure!(
                        runtime_visible_annotations.is_none(),
                        "Duplicate RuntimeVisibleAnnotations attribute"
                    );
                    let mut body = Reader::new(content);
                    let mut values = Vec::new();
                    for _ in 0..body.u16()? {
                        values.push(annotation(&constants, &mut body, 0)?);
                    }
                    body.finish()?;
                    ensure!(unique(values.iter()), "Duplicate runtime annotation");
                    runtime_visible_annotations = Some(values);
                } else if attribute == "Code" {
                    ensure!(code.is_none(), "Duplicate Code attribute");
                    let mut body = Reader::new(content);
                    let max_stack = body.u16()?;
                    let max_locals = body.u16()?;
                    let size = body.u32()? as usize;
                    ensure!(size > 0 && size <= 65535, "Invalid method Code length");
                    let bytes = body.take(size)?.to_vec();
                    let mut handlers = Vec::new();
                    for _ in 0..body.u16()? {
                        let start_pc = body.u16()?;
                        let end_pc = body.u16()?;
                        let handler_pc = body.u16()?;
                        let catch_index = body.u16()?;
                        ensure!(
                            start_pc < end_pc
                                && usize::from(end_pc) <= bytes.len()
                                && usize::from(handler_pc) < bytes.len(),
                            "Invalid exception table range or handler target"
                        );
                        let catch_type = if catch_index == 0 {
                            None
                        } else {
                            let name = class_name(&constants, catch_index)?;
                            ensure!(
                                !name.is_empty() && !name.starts_with('['),
                                "Exception handler catch type must be a class"
                            );
                            Some(name)
                        };
                        handlers.push(ExceptionHandler {
                            start_pc,
                            end_pc,
                            handler_pc,
                            catch_type,
                        });
                    }
                    // A Code attribute may contain multiple LineNumberTables.
                    // Preserve row order, including duplicate start PCs.
                    for _ in 0..body.u16()? {
                        let attribute = text(&constants, body.u16()?)?;
                        let length = body.u32()? as usize;
                        let data = body.take(length)?;
                        if attribute == "LineNumberTable" {
                            let mut rows = Reader::new(data);
                            for _ in 0..rows.u16()? {
                                let pc = rows.u16()?;
                                let line = rows.u16()?;
                                ensure!(
                                    usize::from(pc) < bytes.len(),
                                    "LineNumberTable start_pc outside Code"
                                );
                                line_numbers.push(LineNumber { pc, line });
                            }
                            rows.finish()?;
                        }
                    }
                    body.finish()?;
                    code = Some(Code {
                        max_stack,
                        max_locals,
                        bytes,
                        handlers,
                    });
                }
            }
            method_reflection.push(reflection);
            methods.push(Method {
                name,
                descriptor,
                access,
                code,
                line_numbers,
                runtime_visible_annotations: runtime_visible_annotations.unwrap_or_default(),
            });
        }
        let mut bootstrap_methods = None;
        let mut module = None;
        let mut packages = None;
        let mut resolution = None;
        let mut module_target = None;
        let mut main_class = None;
        let mut nest_host = None;
        let mut nest_members = None;
        let mut source_file = None;
        let mut inner_simple_name = None;
        let mut inner_class_entry = false;
        let mut declaring_class = None;
        let mut enclosing_class = None;
        let mut record_components = None;
        let mut inner_classes_seen = false;
        for _ in 0..reader.u16()? {
            let attribute = text(&constants, reader.u16()?)?;
            let size = reader.u32()? as usize;
            let content = reader.take(size)?;
            match attribute.as_str() {
                "EnclosingMethod" => {
                    ensure!(
                        enclosing_class.is_none(),
                        "Duplicate EnclosingMethod attribute"
                    );
                    let mut body = Reader::new(content);
                    enclosing_class = Some(class_name(&constants, body.u16()?)?);
                    let method = body.u16()?;
                    if method != 0 {
                        let Some(Constant::NameAndType(n, d)) = constants.get(method as usize)
                        else {
                            bail!("Invalid EnclosingMethod name/type");
                        };
                        text(&constants, *n)?;
                        text(&constants, *d)?;
                    }
                    body.finish()?;
                }
                "Record" => {
                    ensure!(
                        major >= 60 && record_components.is_none(),
                        "Invalid or duplicate Record attribute"
                    );
                    let mut body = Reader::new(content);
                    let mut components = Vec::new();
                    for _ in 0..body.u16()? {
                        let name = text(&constants, body.u16()?)?;
                        let descriptor = text(&constants, body.u16()?)?;
                        for _ in 0..body.u16()? {
                            text(&constants, body.u16()?)?;
                            let length = body.u32()? as usize;
                            body.take(length)?;
                        }
                        ensure!(
                            !components.iter().any(|(n, _)| n == &name),
                            "Duplicate record component"
                        );
                        components.push((name, descriptor));
                    }
                    body.finish()?;
                    record_components = Some(components);
                }
                "InnerClasses" => {
                    ensure!(!inner_classes_seen, "Duplicate InnerClasses attribute");
                    inner_classes_seen = true;
                    let mut body = Reader::new(content);
                    let mut matched = false;
                    for _ in 0..body.u16()? {
                        let inner = class_name(&constants, body.u16()?)?;
                        let outer = body.u16()?;
                        if outer != 0 {
                            class_name(&constants, outer)?;
                        }
                        let simple = optional_text(&constants, body.u16()?)?;
                        body.u16()?;
                        if inner == name {
                            ensure!(!matched, "Duplicate own InnerClasses entry");
                            matched = true;
                            inner_class_entry = true;
                            inner_simple_name = simple;
                            declaring_class = if outer == 0 {
                                None
                            } else {
                                Some(class_name(&constants, outer)?)
                            };
                        }
                    }
                    body.finish()?;
                }
                "SourceFile" => {
                    ensure!(source_file.is_none(), "Duplicate SourceFile attribute");
                    let mut body = Reader::new(content);
                    source_file = Some(text(&constants, body.u16()?)?);
                    body.finish()?;
                }
                "NestHost" => {
                    ensure!(
                        major >= 55 && nest_host.is_none() && nest_members.is_none(),
                        "Invalid or duplicate NestHost attribute"
                    );
                    let mut body = Reader::new(content);
                    nest_host = Some(class_name(&constants, body.u16()?)?);
                    body.finish()?;
                }
                "NestMembers" => {
                    ensure!(
                        major >= 55 && nest_members.is_none() && nest_host.is_none(),
                        "Invalid or duplicate NestMembers attribute"
                    );
                    let mut body = Reader::new(content);
                    let mut members = Vec::new();
                    for _ in 0..body.u16()? {
                        members.push(class_name(&constants, body.u16()?)?);
                    }
                    body.finish()?;
                    nest_members = Some(members);
                }
                "Module" => {
                    ensure!(module.is_none(), "Duplicate Module attribute");
                    module = Some(module_attribute(&constants, content)?);
                }
                "ModulePackages" => {
                    ensure!(packages.is_none(), "Duplicate ModulePackages attribute");
                    let mut body = Reader::new(content);
                    let mut names = Vec::new();
                    for _ in 0..body.u16()? {
                        names.push(package_name(&constants, body.u16()?)?);
                    }
                    body.finish()?;
                    ensure!(unique(&names), "Duplicate module package");
                    packages = Some(names);
                }
                "ModuleResolution" => {
                    ensure!(resolution.is_none(), "Duplicate ModuleResolution attribute");
                    let mut body = Reader::new(content);
                    let flags = body.u16()?;
                    body.finish()?;
                    ensure!(flags & !15 == 0, "Unknown ModuleResolution flags");
                    resolution = Some(flags);
                }
                "ModuleTarget" => {
                    ensure!(module_target.is_none(), "Duplicate ModuleTarget attribute");
                    let mut body = Reader::new(content);
                    module_target = Some(optional_text(&constants, body.u16()?)?);
                    body.finish()?;
                }
                "ModuleMainClass" => {
                    ensure!(main_class.is_none(), "Duplicate ModuleMainClass attribute");
                    let mut body = Reader::new(content);
                    main_class = Some(class_name(&constants, body.u16()?)?);
                    body.finish()?;
                }
                _ => (),
            }
            if attribute == "BootstrapMethods" {
                ensure!(
                    major >= 51 && bootstrap_methods.is_none(),
                    "Invalid or duplicate BootstrapMethods attribute"
                );
                let mut body = Reader::new(content);
                let mut methods = Vec::new();
                for _ in 0..body.u16()? {
                    let handle = body.u16()?;
                    let mut arguments = Vec::new();
                    for _ in 0..body.u16()? {
                        arguments.push(body.u16()?);
                    }
                    methods.push(BootstrapMethod { handle, arguments });
                }
                body.finish()?;
                bootstrap_methods = Some(methods);
            }
        }
        reader.finish()?;
        if let Some(module) = &mut module {
            ensure!(
                major >= 53
                    && access == 0x8000
                    && name == "module-info"
                    && super_index == 0
                    && interfaces == 0
                    && fields == 0
                    && methods.is_empty(),
                "Invalid module-info class structure"
            );
            module.packages = packages.unwrap_or_default();
            module.resolution_flags = resolution.unwrap_or_default();
            module.target = module_target.flatten();
            module.main_class = main_class;
        } else {
            ensure!(
                access & 0x8000 == 0
                    && packages.is_none()
                    && resolution.is_none()
                    && module_target.is_none()
                    && main_class.is_none(),
                "Module metadata requires module-info and a Module attribute"
            );
        }
        let result = Self {
            name,
            super_name,
            access,
            interfaces,
            interface_names,
            fields,
            field_info,
            major,
            methods,
            module,
            nest_host,
            nest_members,
            source_file,
            inner_simple_name,
            inner_class_entry,
            declaring_class,
            enclosing_class,
            record_components,
            method_reflection,
            constants,
            bootstrap_methods: bootstrap_methods.unwrap_or_default(),
        };
        for method in &result.bootstrap_methods {
            let handle = result.method_handle(method.handle)?;
            ensure!(
                matches!(handle.reference_kind, 6 | 8),
                "Bootstrap method must be invokeStatic or newInvokeSpecial"
            );
            for &index in &method.arguments {
                ensure!(
                    matches!(
                        result.constants.get(index as usize),
                        Some(
                            Constant::StringLiteral(_)
                                | Constant::Integer(_)
                                | Constant::Float(_)
                                | Constant::Long(_)
                                | Constant::Double(_)
                                | Constant::Class(_)
                                | Constant::MethodHandle(_, _)
                                | Constant::MethodType(_)
                                | Constant::Dynamic(_, _)
                        )
                    ),
                    "Invalid bootstrap argument constant"
                );
            }
        }
        for constant in &result.constants {
            if let Constant::Dynamic(bootstrap, signature)
            | Constant::InvokeDynamic(bootstrap, signature) = constant
            {
                ensure!(
                    (*bootstrap as usize) < result.bootstrap_methods.len(),
                    "Dynamic constant bootstrap index out of bounds"
                );
                result.name_and_type(*signature)?;
            }
        }
        Ok(result)
    }

    pub fn integer(&self, index: u16) -> Result<i32> {
        match self.constants.get(index as usize) {
            Some(Constant::Integer(value)) => Ok(*value),
            _ => bail!("ldc constant {index} is not an int"),
        }
    }

    pub fn numeric(&self, index: u16) -> Result<NumericConstant> {
        match self.constants.get(index as usize) {
            Some(Constant::Integer(value)) => Ok(NumericConstant::Int(*value)),
            Some(Constant::Float(bits)) => Ok(NumericConstant::Float(*bits)),
            Some(Constant::Long(value)) => Ok(NumericConstant::Long(*value)),
            Some(Constant::Double(bits)) => Ok(NumericConstant::Double(*bits)),
            Some(Constant::StringLiteral(utf8)) => bail!(
                "String constant {index} (UTF8 #{utf8}) requires linked java.lang.String literals and interning"
            ),
            Some(Constant::Class(_)) => {
                bail!("Class constant {index} requires linked java.lang.Class mirrors")
            }
            _ => bail!("Constant {index} is not a numeric literal"),
        }
    }

    pub fn local_static_target(&self, index: u16) -> Result<usize> {
        let (owner, name, descriptor, interface) = self.static_method_reference(index)?;
        ensure!(
            owner == self.name && interface == (self.access & 0x200 != 0),
            "Local static reference has wrong owner or class/interface kind"
        );
        let member = self.method(&name, Some(&descriptor))?;
        let target = self
            .methods
            .iter()
            .position(|m| std::ptr::eq(m, member))
            .unwrap();
        ensure!(
            self.methods[target].access & 8 != 0,
            "invokestatic target is not static"
        );
        Ok(target)
    }

    pub fn constant_class(&self, index: u16) -> Result<String> {
        class_name(&self.constants, index)
    }

    pub fn method_reference(&self, index: u16) -> Result<(String, String, String)> {
        let Some(Constant::MethodRef(owner, signature)) = self.constants.get(index as usize) else {
            bail!("Invocation requires a class Methodref")
        };
        let (name, descriptor) = self.name_and_type(*signature)?;
        Ok((class_name(&self.constants, *owner)?, name, descriptor))
    }
    pub fn interface_method_reference(&self, index: u16) -> Result<(String, String, String)> {
        let Some(Constant::InterfaceMethodRef(owner, signature)) =
            self.constants.get(index as usize)
        else {
            bail!("invokeinterface requires InterfaceMethodref");
        };
        let (name, descriptor) = self.name_and_type(*signature)?;
        Ok((class_name(&self.constants, *owner)?, name, descriptor))
    }
    pub fn special_method_reference(&self, index: u16) -> Result<(String, String, String, bool)> {
        let interface = matches!(
            self.constants.get(index as usize),
            Some(Constant::InterfaceMethodRef(..))
        );
        let (owner, name, descriptor) = if interface {
            ensure!(
                self.major >= 52,
                "Interface invokestatic/invokespecial requires Java 8 class format"
            );
            self.interface_method_reference(index)?
        } else {
            self.method_reference(index)?
        };
        Ok((owner, name, descriptor, interface))
    }
    pub fn static_method_reference(&self, index: u16) -> Result<(String, String, String, bool)> {
        self.special_method_reference(index)
    }
    pub fn method_type(&self, index: u16) -> Result<String> {
        let Some(Constant::MethodType(descriptor)) = self.constants.get(index as usize) else {
            bail!("Expected MethodType constant");
        };
        text(&self.constants, *descriptor)
    }
    pub fn method_handle(&self, index: u16) -> Result<MethodHandle> {
        let Some(Constant::MethodHandle(kind, reference)) = self.constants.get(index as usize)
        else {
            bail!("Expected MethodHandle constant");
        };
        let (owner, signature, interface) = match (kind, self.constants.get(*reference as usize)) {
            (1..=4, Some(Constant::FieldRef(owner, signature))) => (*owner, *signature, false),
            (5..=8, Some(Constant::MethodRef(owner, signature))) => (*owner, *signature, false),
            (6 | 7, Some(Constant::InterfaceMethodRef(owner, signature))) if self.major >= 52 => {
                (*owner, *signature, true)
            }
            (9, Some(Constant::InterfaceMethodRef(owner, signature))) => (*owner, *signature, true),
            _ => bail!("MethodHandle reference kind/tag mismatch"),
        };
        let (name, descriptor) = self.name_and_type(signature)?;
        ensure!(
            (*kind == 8 && name == "<init>")
                || (*kind != 8
                    && (!matches!(*kind, 5..=9)
                        || !matches!(name.as_str(), "<init>" | "<clinit>"))),
            "Invalid MethodHandle special name"
        );
        Ok(MethodHandle {
            reference_kind: *kind,
            owner: class_name(&self.constants, owner)?,
            name,
            descriptor,
            interface,
        })
    }
    pub fn dynamic_site(&self, index: u16) -> Result<DynamicSite> {
        let Some(Constant::InvokeDynamic(bootstrap, signature)) =
            self.constants.get(index as usize)
        else {
            bail!("Expected InvokeDynamic constant");
        };
        self.bootstrap_site(*bootstrap, *signature)
    }

    /// Preserve a CONSTANT_Dynamic symbol without executing its bootstrap.
    pub fn dynamic_constant(&self, index: u16) -> Result<DynamicSite> {
        let Some(Constant::Dynamic(bootstrap, signature)) = self.constants.get(index as usize)
        else {
            bail!("Expected Dynamic constant");
        };
        self.bootstrap_site(*bootstrap, *signature)
    }

    fn bootstrap_site(&self, bootstrap: u16, signature: u16) -> Result<DynamicSite> {
        let (name, descriptor) = self.name_and_type(signature)?;
        ensure!(
            !matches!(name.as_str(), "<init>" | "<clinit>"),
            "Invalid InvokeDynamic call name"
        );
        let method = self
            .bootstrap_methods
            .get(bootstrap as usize)
            .context("Missing bootstrap method")?;
        Ok(DynamicSite {
            name,
            descriptor,
            bootstrap: self.method_handle(method.handle)?,
            arguments: method.arguments.clone(),
        })
    }

    fn name_and_type(&self, index: u16) -> Result<(String, String)> {
        let Some(Constant::NameAndType(name, descriptor)) = self.constants.get(index as usize)
        else {
            bail!("Invalid NameAndType")
        };
        Ok((
            text(&self.constants, *name)?,
            text(&self.constants, *descriptor)?,
        ))
    }

    pub fn local_field_target(&self, index: u16) -> Result<usize> {
        let (owner, name, descriptor) = self.field_reference(index)?;
        ensure!(
            owner == self.name,
            "Cross-class fields require class linking"
        );
        self.field_info
            .iter()
            .position(|f| f.name == name && f.descriptor == descriptor)
            .context("Missing local field")
    }

    pub fn field_reference(&self, index: u16) -> Result<(String, String, String)> {
        let Some(Constant::FieldRef(owner, signature)) = self.constants.get(index as usize) else {
            bail!("Expected Fieldref")
        };
        let (name, descriptor) = self.name_and_type(*signature)?;
        Ok((class_name(&self.constants, *owner)?, name, descriptor))
    }

    pub fn local_method_target(&self, index: u16) -> Result<usize> {
        let (owner, name, descriptor) = self.method_reference(index)?;
        ensure!(
            owner == self.name,
            "Cross-class calls require class linking and initialization; not implemented"
        );
        let target = self.method(&name, Some(&descriptor))?;
        self.methods
            .iter()
            .position(|method| std::ptr::eq(method, target))
            .context("Missing local method")
    }

    pub fn method(&self, name: &str, descriptor: Option<&str>) -> Result<&Method> {
        let methods: Vec<_> = self
            .methods
            .iter()
            .filter(|method| {
                method.name == name
                    && descriptor.is_none_or(|descriptor| method.descriptor == descriptor)
            })
            .collect();
        ensure!(
            methods.len() == 1,
            "Select exactly one method; use --descriptor for overloads"
        );
        Ok(methods[0])
    }
}

/// JVMS modified UTF-8 encodes UTF-16 units, including unpaired surrogates.
fn modified_utf16(bytes: &[u8]) -> Result<Vec<u16>> {
    let mut output = Vec::new();
    let mut position = 0;
    while position < bytes.len() {
        let first = bytes[position];
        position += 1;
        let value = match first {
            1..=0x7f => first as u16,
            0xc0..=0xdf => {
                let second = *bytes.get(position).context("Truncated modified UTF8")?;
                position += 1;
                ensure!(second & 0xc0 == 0x80, "Invalid modified UTF8 continuation");
                let value = ((first as u16 & 0x1f) << 6) | (second as u16 & 0x3f);
                ensure!(value == 0 || value >= 0x80, "Overlong modified UTF8");
                value
            }
            0xe0..=0xef => {
                let second = *bytes.get(position).context("Truncated modified UTF8")?;
                let third = *bytes.get(position + 1).context("Truncated modified UTF8")?;
                position += 2;
                ensure!(
                    second & 0xc0 == 0x80 && third & 0xc0 == 0x80,
                    "Invalid modified UTF8 continuation"
                );
                let value = ((first as u16 & 15) << 12)
                    | ((second as u16 & 0x3f) << 6)
                    | (third as u16 & 0x3f);
                ensure!(value >= 0x800, "Overlong modified UTF8");
                value
            }
            _ => bail!("Invalid modified UTF8 leading byte"),
        };
        output.push(value);
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn visible_annotations_preserve_types_and_validate_nested_elements() {
        let constants = vec![
            Constant::Other,
            Constant::Utf8(b"Lp/Outer;".to_vec()),
            Constant::Utf8(b"value".to_vec()),
            Constant::Utf8(b"Lp/Nested;".to_vec()),
            Constant::Integer(7),
        ];
        // @Outer(value={@Nested,7})
        let bytes = [0, 1, 0, 1, 0, 2, b'[', 0, 2, b'@', 0, 3, 0, 0, b'I', 0, 4];
        let mut r = Reader::new(&bytes);
        assert_eq!(annotation(&constants, &mut r, 0).unwrap(), "Lp/Outer;");
        r.finish().unwrap();
        let mut invalid = bytes;
        invalid[14] = b'Q';
        assert!(annotation(&constants, &mut Reader::new(&invalid), 0).is_err());
        assert!(annotation(&constants, &mut Reader::new(&bytes[..16]), 0).is_err());
        let mut invalid = bytes;
        invalid[16] = 3; // Integer element cannot reference UTF8.
        assert!(annotation(&constants, &mut Reader::new(&invalid), 0).is_err());
    }
    fn debug_fixture(bad_pc: bool, duplicate_source: bool) -> Vec<u8> {
        fn utf(b: &mut Vec<u8>, s: &str) {
            b.push(1);
            b.extend((s.len() as u16).to_be_bytes());
            b.extend(s.as_bytes());
        }
        fn attr(b: &mut Vec<u8>, name: u16, data: &[u8]) {
            b.extend(name.to_be_bytes());
            b.extend((data.len() as u32).to_be_bytes());
            b.extend(data);
        }
        let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 11];
        utf(&mut b, "p/Debug");
        b.extend([7, 0, 1]);
        utf(&mut b, "java/lang/Object");
        b.extend([7, 0, 3]);
        for s in [
            "m",
            "()V",
            "Code",
            "LineNumberTable",
            "SourceFile",
            "Sample.java",
        ] {
            utf(&mut b, s);
        }
        for n in [0x21u16, 2, 4, 0, 0, 1, 9, 5, 6, 1] {
            b.extend(n.to_be_bytes());
        }
        let mut code = vec![0, 0, 0, 0, 0, 0, 0, 2, 0, 0xb1, 0, 0, 0, 2];
        attr(&mut code, 8, &[0, 2, 0, 0, 0, 10, 0, 1, 0, 11]);
        attr(&mut code, 8, &[0, 1, 0, if bad_pc { 2 } else { 1 }, 0, 12]);
        attr(&mut b, 7, &code);
        b.extend((if duplicate_source { 2u16 } else { 1u16 }).to_be_bytes());
        attr(&mut b, 9, &[0, 10]);
        if duplicate_source {
            attr(&mut b, 9, &[0, 10]);
        }
        b
    }
    #[test]
    fn debug_metadata_preserves_source_and_multiple_line_tables_without_collapsing_rows() {
        let class = ClassFile::parse(&debug_fixture(false, false)).unwrap();
        assert_eq!(class.source_file.as_deref(), Some("Sample.java"));
        assert_eq!(
            class.methods[0]
                .line_numbers
                .iter()
                .map(|r| (r.pc, r.line))
                .collect::<Vec<_>>(),
            vec![(0, 10), (1, 11), (1, 12)]
        );
    }
    #[test]
    fn debug_metadata_rejects_out_of_code_lines_and_duplicate_source_attributes() {
        assert!(ClassFile::parse(&debug_fixture(true, false)).is_err());
        assert!(ClassFile::parse(&debug_fixture(false, true)).is_err());
    }
    fn concat_fixture(bootstrap: u16, handle_kind: u8, argument: u16, duplicate: bool) -> Vec<u8> {
        fn u16be(v: &mut Vec<u8>, x: u16) {
            v.extend_from_slice(&x.to_be_bytes());
        }
        fn utf(v: &mut Vec<u8>, x: &[u8]) {
            v.push(1);
            u16be(v, x.len() as u16);
            v.extend_from_slice(x);
        }
        fn pair(v: &mut Vec<u8>, tag: u8, a: u16, b: u16) {
            v.push(tag);
            u16be(v, a);
            u16be(v, b);
        }
        let mut v = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65];
        u16be(&mut v, 20);
        utf(&mut v, b"p/Concat");
        v.push(7);
        u16be(&mut v, 1);
        utf(&mut v, b"java/lang/Object");
        v.push(7);
        u16be(&mut v, 3);
        utf(&mut v, b"BootstrapMethods");
        utf(&mut v, b"java/lang/invoke/StringConcatFactory");
        v.push(7);
        u16be(&mut v, 6);
        utf(&mut v, b"makeConcatWithConstants");
        utf(&mut v,b"(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;Ljava/lang/String;[Ljava/lang/Object;)Ljava/lang/invoke/CallSite;");
        pair(&mut v, 12, 8, 9);
        pair(&mut v, 10, 7, 10);
        v.extend_from_slice(&[15, handle_kind]);
        u16be(&mut v, 11);
        utf(&mut v, b"(J)Ljava/lang/String;");
        pair(&mut v, 12, 8, 13);
        pair(&mut v, 18, bootstrap, 14);
        utf(&mut v, b"prefix\x01suffix");
        v.push(8);
        u16be(&mut v, 16);
        utf(&mut v, b"run");
        utf(&mut v, b"Code");
        for x in [1, 2, 4, 0, 0, 1, 9, 18, 13, 1, 19] {
            u16be(&mut v, x);
        }
        v.extend_from_slice(&19u32.to_be_bytes());
        for x in [2, 2] {
            u16be(&mut v, x);
        }
        v.extend_from_slice(&7u32.to_be_bytes());
        v.extend_from_slice(&[0x1e, 0xba, 0, 15, 0, 0, 0xb0]);
        for x in [0, 0, if duplicate { 2 } else { 1 }] {
            u16be(&mut v, x);
        }
        for _ in 0..if duplicate { 2 } else { 1 } {
            u16be(&mut v, 5);
            v.extend_from_slice(&8u32.to_be_bytes());
            for x in [1, 12, 1, argument] {
                u16be(&mut v, x);
            }
        }
        v
    }
    #[test]
    fn dynamic_sites_retain_exact_bootstrap_handle_and_recipe() {
        let bytes = concat_fixture(0, 6, 17, false);
        let class = ClassFile::parse(&bytes).unwrap();
        let site = class.dynamic_site(15).unwrap();
        assert_eq!(site.descriptor, "(J)Ljava/lang/String;");
        assert_eq!(site.bootstrap.reference_kind, 6);
        assert_eq!(site.bootstrap.owner, "java/lang/invoke/StringConcatFactory");
        let plan = crate::compiler::concat::plan(&class, &site).unwrap();
        assert_eq!(
            plan.arguments,
            vec![crate::compiler::concat::Argument::Long]
        );
        assert_eq!(plan.parts.len(), 3);
        assert_eq!(
            class.string_literal(site.arguments[0]).unwrap().unwrap(),
            "prefix\u{1}suffix".encode_utf16().collect::<Vec<_>>()
        );
        for bytes in [
            concat_fixture(1, 6, 17, false),
            concat_fixture(0, 5, 17, false),
            concat_fixture(0, 6, 18, false),
            concat_fixture(0, 6, 17, true),
        ] {
            assert!(ClassFile::parse(&bytes).is_err());
        }
        for end in 0..bytes.len() {
            assert!(ClassFile::parse(&bytes[..end]).is_err());
        }
    }
    #[test]
    fn interface_static_constants_require_java8_and_preserve_virtual_tag_checks() {
        let mut class = ClassFile::parse(&concat_fixture(0, 6, 17, false)).unwrap();
        let (owner, signature) = match class.constants[11] {
            Constant::MethodRef(owner, signature) => (owner, signature),
            _ => panic!("fixture method"),
        };
        let index = class.constants.len() as u16;
        class
            .constants
            .push(Constant::InterfaceMethodRef(owner, signature));
        assert!(class.static_method_reference(index).unwrap().3);
        assert!(!class.static_method_reference(11).unwrap().3);
        assert!(class.method_reference(index).is_err());
        class.major = 51;
        assert!(class.static_method_reference(index).is_err());
        assert!(class.special_method_reference(index).is_err());
        assert!(class.static_method_reference(11).is_ok());
    }
    fn handler_fixture(rows: &[[u16; 4]]) -> Vec<u8> {
        let mut bytes = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65];
        let names: &[&[u8]] = &[
            b"p/Catch",
            b"java/lang/Object",
            b"run",
            b"()V",
            b"Code",
            b"java/lang/Throwable",
        ];
        bytes.extend_from_slice(&10u16.to_be_bytes());
        for name in names {
            bytes.push(1);
            bytes.extend_from_slice(&(name.len() as u16).to_be_bytes());
            bytes.extend_from_slice(name);
        }
        for index in [1u16, 2, 6] {
            bytes.push(7);
            bytes.extend_from_slice(&index.to_be_bytes());
        }
        for value in [1u16, 7, 8, 0, 0, 1, 9, 3, 4, 1, 5] {
            bytes.extend_from_slice(&value.to_be_bytes());
        }
        let mut body = vec![0, 1, 0, 1, 0, 0, 0, 3, 0xb1, 0x4b, 0xb1];
        body.extend_from_slice(&(rows.len() as u16).to_be_bytes());
        for row in rows {
            for value in row {
                body.extend_from_slice(&value.to_be_bytes());
            }
        }
        body.extend_from_slice(&0u16.to_be_bytes());
        bytes.extend_from_slice(&(body.len() as u32).to_be_bytes());
        bytes.extend(body);
        bytes.extend_from_slice(&0u16.to_be_bytes());
        bytes
    }
    #[test]
    fn exception_table_retains_catch_all_order_and_half_open_ranges() {
        let class = ClassFile::parse(&handler_fixture(&[[0, 1, 1, 9], [0, 3, 1, 0]])).unwrap();
        assert_eq!(
            class.methods[0].code.as_ref().unwrap().handlers,
            vec![
                ExceptionHandler {
                    start_pc: 0,
                    end_pc: 1,
                    handler_pc: 1,
                    catch_type: Some("java/lang/Throwable".into())
                },
                ExceptionHandler {
                    start_pc: 0,
                    end_pc: 3,
                    handler_pc: 1,
                    catch_type: None
                },
            ]
        );
        for row in [
            [1, 1, 1, 9],
            [2, 1, 1, 9],
            [0, 4, 1, 9],
            [0, 1, 3, 9],
            [0, 1, 1, 6],
            [0, 1, 1, 100],
        ] {
            assert!(
                ClassFile::parse(&handler_fixture(&[row])).is_err(),
                "{row:?}"
            );
        }
        let bytes = handler_fixture(&[[0, 1, 1, 9]]);
        for end in 0..bytes.len() {
            assert!(ClassFile::parse(&bytes[..end]).is_err());
        }
    }
    #[test]
    fn string_modified_utf8_preserves_nul_and_utf16_surrogates() {
        assert_eq!(
            modified_utf16(&[
                65, 0xc0, 0x80, 0xed, 0xa0, 0xbd, 0xed, 0xba, 0x80, 0xed, 0xa0, 0x80
            ])
            .unwrap(),
            vec![65, 0, 0xd83d, 0xde80, 0xd800]
        );
        for bytes in [
            &[0][..],
            &[0xc1, 0x81],
            &[0xe0, 0x80, 0x80],
            &[0xf0, 0x9f, 0x9a, 0x80],
            &[0xc2],
            &[0xe1, 0x80],
            &[0xed, 0, 0x80],
        ] {
            assert!(modified_utf16(bytes).is_err());
        }
    }
    #[test]
    fn malformed_class_files_fail_without_reading_out_of_bounds() {
        for bytes in [
            &b""[..],
            &b"not a class"[..],
            &[0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 3, 1, 0, 10, b'a'][..],
        ] {
            assert!(ClassFile::parse(bytes).is_err());
        }
    }
}

#[cfg(test)]
mod module_metadata_tests {
    use super::*;
    fn words(values: &[u16]) -> Vec<u8> {
        values.iter().flat_map(|v| v.to_be_bytes()).collect()
    }
    fn fixture(access: u16, body: &[u8], duplicate: bool) -> Vec<u8> {
        let mut b = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 24];
        fn utf(b: &mut Vec<u8>, value: &str) {
            b.push(1);
            b.extend((value.len() as u16).to_be_bytes());
            b.extend(value.as_bytes());
        }
        utf(&mut b, "module-info");
        b.extend([7, 0, 1]);
        utf(&mut b, "Module");
        utf(&mut b, "sample");
        b.extend([19, 0, 4]);
        utf(&mut b, "java.base");
        b.extend([19, 0, 6]);
        utf(&mut b, "p/q");
        b.extend([20, 0, 8]);
        utf(&mut b, "p/Service");
        b.extend([7, 0, 10]);
        utf(&mut b, "p/Impl");
        b.extend([7, 0, 12]);
        for name in [
            "ModulePackages",
            "ModuleResolution",
            "ModuleTarget",
            "windows-amd64",
            "ModuleMainClass",
            "p/Main",
        ] {
            utf(&mut b, name);
        }
        b.extend([7, 0, 19]);
        utf(&mut b, "21");
        utf(&mut b, "friend");
        b.extend([19, 0, 22]);
        b.extend(words(&[
            access,
            2,
            0,
            0,
            0,
            0,
            if duplicate { 6 } else { 5 },
        ]));
        let mut attrs = vec![
            (3, body.to_vec()),
            (14, words(&[1, 9])),
            (15, words(&[1])),
            (16, words(&[17])),
            (18, words(&[20])),
        ];
        if duplicate {
            attrs.push((3, body.to_vec()));
        }
        for (name, content) in attrs {
            b.extend((name as u16).to_be_bytes());
            b.extend((content.len() as u32).to_be_bytes());
            b.extend(content);
        }
        b
    }
    fn body() -> Vec<u8> {
        words(&[
            5, 0, 21, 1, 7, 0x8000, 21, 1, 9, 0, 1, 23, 0, 1, 11, 1, 11, 1, 13,
        ])
    }
    #[test]
    fn module_info_retains_qualified_exports_services_and_extended_metadata() {
        let d = ClassFile::parse(&fixture(0x8000, &body(), false))
            .unwrap()
            .module
            .unwrap();
        assert_eq!(d.name, "sample");
        assert_eq!(d.version.as_deref(), Some("21"));
        assert_eq!(d.requires[0].flags, 0x8000);
        assert_eq!(d.exports[0].targets, vec!["friend"]);
        assert_eq!(d.uses, vec!["p/Service"]);
        assert_eq!(d.provides[0].providers, vec!["p/Impl"]);
        assert_eq!(d.packages, vec!["p/q"]);
        assert_eq!(d.resolution_flags, 1);
        assert_eq!(d.target.as_deref(), Some("windows-amd64"));
        assert_eq!(d.main_class.as_deref(), Some("p/Main"));
    }
    #[test]
    fn malformed_module_structure_tags_and_directives_are_rejected() {
        let original = body();
        assert!(ClassFile::parse(&fixture(0, &original, false)).is_err());
        assert!(ClassFile::parse(&fixture(0x8000, &original, true)).is_err());
        let mut invalid = original.clone();
        invalid[1] = 4;
        assert!(ClassFile::parse(&fixture(0x8000, &invalid, false)).is_err());
        let mut invalid = original.clone();
        invalid[3] = 1;
        assert!(ClassFile::parse(&fixture(0x8000, &invalid, false)).is_err());
        let mut invalid = original.clone();
        invalid.push(0);
        assert!(ClassFile::parse(&fixture(0x8000, &invalid, false)).is_err());
        let duplicate = words(&[5, 0, 21, 2, 7, 0x8000, 21, 7, 0x8000, 21, 0, 0, 0, 0]);
        assert!(ClassFile::parse(&fixture(0x8000, &duplicate, false)).is_err());
        let no_base = words(&[5, 0, 21, 0, 0, 0, 0, 0]);
        assert!(ClassFile::parse(&fixture(0x8000, &no_base, false)).is_err());
        for flags in [0x20u16, 0x40] {
            let mut invalid = original.clone();
            invalid[10..12].copy_from_slice(&flags.to_be_bytes());
            assert!(ClassFile::parse(&fixture(0x8000, &invalid, false)).is_err());
        }
    }
}
