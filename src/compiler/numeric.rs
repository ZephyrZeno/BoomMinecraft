//! Typed primitive backend. Every executable operation is emitted as MASM.
use super::classfile::{ClassFile, Code, Method, NumericConstant};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Type {
    I32,
    I64,
    F32,
    F64,
    Array(ArrayKind),
    Null,
    AnyRef,
    Object,
    ObjectArray,
    LinkedObject(usize),
    LinkedObjectArray(usize),
    BootstrapString,
    BootstrapStringArray,
    BootstrapClass,
    BootstrapClassArray,
    MetadataReference(usize),
    ReferenceJoin(usize),
    Uninitialized(usize),
    UninitializedThis,
    UninitializedLinked(usize, usize),
    UninitializedLinkedThis(usize),
    UninitializedString(usize),
    Void,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ArrayKind {
    Boolean,
    Char,
    Float,
    Double,
    Byte,
    Short,
    Int,
    Long,
}
impl ArrayKind {
    pub(super) fn descriptor(self) -> &'static str {
        match self {
            Self::Boolean => "[Z",
            Self::Char => "[C",
            Self::Float => "[F",
            Self::Double => "[D",
            Self::Byte => "[B",
            Self::Short => "[S",
            Self::Int => "[I",
            Self::Long => "[J",
        }
    }
    fn atype(self) -> u8 {
        match self {
            Self::Boolean => 4,
            Self::Char => 5,
            Self::Float => 6,
            Self::Double => 7,
            Self::Byte => 8,
            Self::Short => 9,
            Self::Int => 10,
            Self::Long => 11,
        }
    }
    fn from_atype(value: u8) -> Result<Self> {
        Ok(match value {
            4 => Self::Boolean,
            5 => Self::Char,
            6 => Self::Float,
            7 => Self::Double,
            8 => Self::Byte,
            9 => Self::Short,
            10 => Self::Int,
            11 => Self::Long,
            _ => bail!("Unsupported primitive array kind"),
        })
    }
    fn value_type(self) -> Type {
        match self {
            Self::Long => Type::I64,
            Self::Float => Type::F32,
            Self::Double => Type::F64,
            _ => Type::I32,
        }
    }
}
impl Type {
    pub fn is_reference(self) -> bool {
        matches!(
            self,
            Self::Array(_)
                | Self::Null
                | Self::AnyRef
                | Self::Object
                | Self::ObjectArray
                | Self::LinkedObject(_)
                | Self::LinkedObjectArray(_)
                | Self::BootstrapString
                | Self::BootstrapStringArray
                | Self::BootstrapClass
                | Self::BootstrapClassArray
                | Self::MetadataReference(_)
                | Self::ReferenceJoin(_)
        )
    }
    fn reference_slot(self) -> bool {
        self.is_reference() || self.uninitialized()
    }
    fn uninitialized(self) -> bool {
        matches!(
            self,
            Self::Uninitialized(_)
                | Self::UninitializedString(_)
                | Self::UninitializedThis
                | Self::UninitializedLinked(_, _)
                | Self::UninitializedLinkedThis(_)
        )
    }
    fn bits64(self) -> bool {
        !matches!(self, Self::I32 | Self::F32)
    }
    fn width(self) -> usize {
        if self == Self::Void {
            0
        } else if matches!(self, Self::I64 | Self::F64) {
            2
        } else {
            1
        }
    }
    fn integer(self) -> bool {
        matches!(self, Self::I32 | Self::I64)
    }
    fn from_opcode(index: u8) -> Self {
        [Self::I32, Self::I64, Self::F32, Self::F64][index as usize]
    }
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Signature {
    pub arguments: Vec<Type>,
    pub result: Type,
}
impl Signature {
    pub fn parse(text: &str) -> Result<Self> {
        Self::parse_with(text, &mut |name, array| {
            ensure!(
                !name.starts_with('['),
                "Nested arrays require loader-aware metadata"
            );
            Ok(if array {
                Type::ObjectArray
            } else {
                Type::Object
            })
        })
    }
    pub(super) fn parse_with(
        text: &str,
        resolve: &mut dyn FnMut(&str, bool) -> Result<Type>,
    ) -> Result<Self> {
        let (args, result) = text
            .strip_prefix('(')
            .and_then(|s| s.split_once(')'))
            .context("Invalid method descriptor")?;
        fn ty(
            bytes: &[u8],
            position: &mut usize,
            resolve: &mut dyn FnMut(&str, bool) -> Result<Type>,
        ) -> Result<Type> {
            let byte = *bytes.get(*position).context("Truncated type descriptor")?;
            *position += 1;
            if byte == b'L' {
                let start = *position;
                while *bytes
                    .get(*position)
                    .context("Unterminated object descriptor")?
                    != b';'
                {
                    *position += 1;
                }
                ensure!(*position > start, "Empty object descriptor");
                let name = std::str::from_utf8(&bytes[start..*position])?;
                *position += 1;
                return resolve(name, false);
            }
            if byte == b'[' {
                if bytes.get(*position) == Some(&b'[') {
                    let start = *position - 1;
                    while bytes.get(*position) == Some(&b'[') {
                        *position += 1;
                    }
                    ensure!(
                        *position - start <= 255,
                        "Array descriptor exceeds 255 dimensions"
                    );
                    let element = *bytes.get(*position).context("Truncated array descriptor")?;
                    *position += 1;
                    if element == b'L' {
                        let name = *position;
                        while bytes.get(*position).is_some_and(|&b| b != b';') {
                            *position += 1;
                        }
                        ensure!(
                            *position > name && bytes.get(*position) == Some(&b';'),
                            "Unterminated/empty array element"
                        );
                        *position += 1;
                    } else {
                        ensure!(
                            b"ZBCSIJFD".contains(&element),
                            "Invalid array element descriptor"
                        );
                    }
                    return resolve(std::str::from_utf8(&bytes[start..*position])?, false);
                }
                let element = *bytes.get(*position).context("Truncated array descriptor")?;
                *position += 1;
                if element == b'L' {
                    let start = *position;
                    while *bytes
                        .get(*position)
                        .context("Unterminated reference array descriptor")?
                        != b';'
                    {
                        *position += 1;
                    }
                    ensure!(*position > start, "Empty array component descriptor");
                    let name = std::str::from_utf8(&bytes[start..*position])?;
                    *position += 1;
                    return resolve(name, true);
                }
                return Ok(Type::Array(match element {
                    b'Z' => ArrayKind::Boolean,
                    b'C' => ArrayKind::Char,
                    b'F' => ArrayKind::Float,
                    b'D' => ArrayKind::Double,
                    b'B' => ArrayKind::Byte,
                    b'S' => ArrayKind::Short,
                    b'I' => ArrayKind::Int,
                    b'J' => ArrayKind::Long,
                    _ => bail!("Only one-dimensional primitive array descriptors are supported"),
                }));
            }
            Ok(match byte {
                b'I' | b'Z' | b'B' | b'C' | b'S' => Type::I32,
                b'J' => Type::I64,
                b'F' => Type::F32,
                b'D' => Type::F64,
                _ => bail!("Numeric backend requires numeric values or primitive arrays"),
            })
        }
        let mut arguments = Vec::new();
        let mut position = 0;
        while position < args.len() {
            arguments.push(ty(args.as_bytes(), &mut position, resolve)?);
            ensure!(
                arguments.iter().map(|t| t.width()).sum::<usize>() <= 255,
                "Method parameters exceed the JVM limit of 255 slots"
            );
        }
        position = 0;
        let result_type = if result == "V" {
            position = 1;
            Type::Void
        } else {
            ty(result.as_bytes(), &mut position, resolve)?
        };
        ensure!(position == result.len(), "Trailing return descriptor data");
        Ok(Self {
            arguments,
            result: result_type,
        })
    }
    pub(super) fn check_arguments(&self) -> Result<()> {
        ensure!(
            self.arguments.iter().map(|t| t.width()).sum::<usize>() <= 255,
            "Receiver and arguments exceed the JVM limit of 255 slots"
        );
        Ok(())
    }
}

pub(super) fn field_type(descriptor: &str) -> Result<Type> {
    if descriptor.starts_with("[[") {
        return Ok(
            Signature::parse_with(&format!("(){descriptor}"), &mut |_, _| Ok(Type::AnyRef))?.result,
        );
    }
    let ty = Signature::parse(&format!("(){descriptor}"))?.result;
    ensure!(ty != Type::Void, "Field cannot have void type");
    Ok(ty)
}

// This increment deliberately links one concrete class. Reject other named
// references instead of erasing distinct classes into the local Object type.
fn validate_local_references(descriptor: &str, class: &ClassFile) -> Result<()> {
    let mut rest = descriptor;
    while let Some((_, tail)) = rest.split_once('L') {
        let (name, tail) = tail.split_once(';').context("Unterminated object type")?;
        ensure!(
            name == class.name,
            "Cross-class object types require the program class linker"
        );
        rest = tail;
    }
    Ok(())
}

fn method_signature(class: &ClassFile, method: &Method) -> Result<Signature> {
    validate_local_references(&method.descriptor, class)?;
    let mut sig = Signature::parse(&method.descriptor)?;
    if method.access & 8 == 0 {
        sig.arguments.insert(0, Type::Object);
    }
    sig.check_arguments()?;
    Ok(sig)
}

pub(super) fn field_offset(class: &ClassFile, field: usize) -> Result<usize> {
    let reference = field_type(&class.field_info[field].descriptor)?.is_reference();
    let mut preceding = 0;
    for (index, info) in class.field_info.iter().enumerate() {
        if info.access & 8 != 0 {
            continue;
        }
        let other_ref = field_type(&info.descriptor)?.is_reference();
        if (other_ref && !reference) || (other_ref == reference && index < field) {
            preceding += 1;
        }
    }
    Ok(preceding * 8)
}

#[derive(Debug, Clone, Copy)]
enum Binary {
    Add,
    Sub,
    Mul,
    Div,
    Rem,
    And,
    Or,
    Xor,
    Shl,
    Shr,
    Ushr,
}
#[derive(Debug, Clone)]
enum Op {
    Nop,
    Constant(Type, u64),
    ExternalCall(String, Signature, bool),
    StringLiteral(usize),
    ClassLiteral(usize),
    ClassIntrinsic(ClassIntrinsic, Signature),
    ClassLoaderField(Signature),
    ClassValueField(Signature, bool),
    ClassLoaderRegister(usize),
    ScopedRegister(usize),
    WinFsInit(usize, usize),
    ReflectArray(super::reflection_arrays::Operation, Signature, usize),
    PrimitiveClass(Signature),
    ModuleIntrinsic(super::modules::Operation, Signature, Option<usize>),
    ResourceStream(usize, Signature, usize, usize),
    VmIntrinsic(super::vm::Operation),
    VmNative(super::vm_registration::Operation, usize),
    SignalFind(usize),
    SignalControl(super::signal_natives::Operation, usize),
    WindowsErrorMode(usize),
    ThreadNative(super::thread_natives::Operation, usize),
    UnsafeNative(super::unsafe_bootstrap::Operation, Signature, usize),
    ShutdownNative(super::shutdown::Operation, Signature, usize),
    AccessContext(super::access_context::Operation, Signature, usize),
    Cds(super::cds::Operation, usize),
    FileDescriptor(super::file_descriptors::Operation, usize),
    ConstantClassInitialization(usize),
    StreamInit(usize),
    ThrowableFill(Signature),
    NpeMessage(Signature),
    Monitor(bool),
    MonitorNotify(bool, Signature),
    RuntimeResource(super::runtime_resources::Operation, Signature),
    StringJoin(usize, Signature, Vec<usize>, Vec<usize>),
    BooleanString([usize; 2]),
    RequireNonNull,
    StringIntrinsic(StringIntrinsic, Signature),
    StringConcatApi(Signature),
    StringReplace(Signature),
    LiteralRegexReplace(u16, u16, Signature),
    StringChars(Signature),
    StringGetChars(Signature),
    StringLowercase(Signature),
    StringSplit(Signature),
    ReflectNew(usize, Signature),
    ReflectConstructor(usize, super::reflect_constructors::Operation, Signature),
    ReflectField(super::reflect_fields::Operation, Signature),
    ClassForName(Signature, bool),
    StringPrefix(Signature),
    SystemStream(Signature, super::system_streams::Operation, usize),
    ArrayClone(Signature, usize),
    IdentityHash(Signature, bool),
    HexString(super::hex_strings::Kind, Signature, usize),
    BuilderSnapshot(Signature, usize),
    Bitcast(Signature, usize),
    RawProperties(super::system_properties::Operation, Signature, usize),
    Concat(usize, Signature, Option<usize>),
    CheckCast(usize, Type),
    InstanceOf(usize),
    GetClass,
    Load(Type, usize),
    Store(Type, usize),
    Pop,
    Pop2,
    Dup,
    Dup2,
    Reorder(u8),
    Swap,
    Neg(Type),
    Binary(Type, Binary),
    Cast(Type, Type),
    Narrow(u8),
    Increment(usize, i32),
    Compare(Type, i32),
    If(u8, usize),
    IfPair(u8, usize),
    BootGuard(u8, u8, bool, usize),
    Goto(usize),
    Switch(usize, Vec<(i32, usize)>),
    Call(usize, Signature),
    BridgeCall(usize, Signature),
    StaticLoad(LinkedField),
    StaticStore(LinkedField),
    Return(Type),
    Throw,
    NewArray(ArrayKind),
    NewTypedArray(usize, Type, u8),
    ArrayLength,
    ArrayLoad(ArrayKind),
    ArrayStore(ArrayKind),
    IfNull(bool, usize),
    IfRefs(bool, usize),
    NewObject,
    NewString,
    InitializeString(Signature),
    NewLinkedObject(usize),
    FieldLoad(usize, Type),
    FieldStore(usize, Type),
    LinkedFieldLoad(LinkedInstanceField),
    LinkedFieldStore(LinkedInstanceField),
    InstanceCall(usize, Signature),
    InterfaceCall(usize, Signature, Vec<usize>, Vec<usize>),
    Initialize(Option<usize>, Signature),
    ProtectedInitialize(usize, Signature, usize),
    NewReferenceArray,
    NewLinkedReferenceArray(usize),
    NewStringArray,
    NewClassArray,
    ReferenceArrayLoad,
    ReferenceArrayStore,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StringIntrinsic {
    Length,
    IsEmpty,
    CharAt,
    HashCode,
    Equals,
    CompareTo,
    ToString,
    Intern,
    EqualsIgnoreCase,
    IndexOfCodePoint,
    IndexOfCodePointFrom,
    Substring,
    SubstringRange,
    LastIndexOfCodePoint,
    LastIndexOfCodePointFrom,
    IndexOfString,
    IndexOfStringFrom,
    LastIndexOfString,
    LastIndexOfStringFrom,
    Trim,
    CodePointAt,
    RegionMatches,
    RegionMatchesIgnoreCase,
    Coder,
    GetBytes,
    GetBytesRange,
}
#[derive(Debug, Clone, Copy)]
pub(super) enum ClassIntrinsic {
    GetName,
    IsArray,
    IsPrimitive,
    IsInterface,
    GetSuperclass,
    GetComponentType,
    IsAssignableFrom,
    DesiredAssertionStatus,
    IsHidden,
    IsInstance,
    CanonicalName,
    SimpleName,
}
impl ClassIntrinsic {
    pub(super) fn resolve(name: &str, descriptor: &str) -> Result<(Self, Signature)> {
        use Type::{AnyRef, BootstrapClass as C, BootstrapString as S, I32};
        let (operation, arguments, result) = match (name, descriptor) {
            ("desiredAssertionStatus", "()Z") => (Self::DesiredAssertionStatus, vec![C], I32),
            ("getName", "()Ljava/lang/String;") => (Self::GetName, vec![C], S),
            ("getCanonicalName", "()Ljava/lang/String;") => (Self::CanonicalName, vec![C], S),
            ("getSimpleName", "()Ljava/lang/String;") => (Self::SimpleName, vec![C], S),
            ("isArray", "()Z") => (Self::IsArray, vec![C], I32),
            ("isPrimitive", "()Z") => (Self::IsPrimitive, vec![C], I32),
            ("isInterface", "()Z") => (Self::IsInterface, vec![C], I32),
            ("isHidden", "()Z") => (Self::IsHidden, vec![C], I32),
            ("isInstance", "(Ljava/lang/Object;)Z") => (Self::IsInstance, vec![C, AnyRef], I32),
            ("getSuperclass", "()Ljava/lang/Class;") => (Self::GetSuperclass, vec![C], C),
            ("getComponentType", "()Ljava/lang/Class;") => (Self::GetComponentType, vec![C], C),
            ("isAssignableFrom", "(Ljava/lang/Class;)Z") => {
                (Self::IsAssignableFrom, vec![C, C], I32)
            }
            _ => bail!("Class operation {name}{descriptor} requires the full reflection runtime"),
        };
        Ok((operation, Signature { arguments, result }))
    }
}
impl StringIntrinsic {
    pub fn resolve(name: &str, descriptor: &str) -> Result<(Self, Signature)> {
        use Type::{AnyRef, Array, BootstrapString as S, I32, Void};
        let (operation, arguments, result) = match (name, descriptor) {
            ("length", "()I") => (Self::Length, vec![S], I32),
            ("isEmpty", "()Z") => (Self::IsEmpty, vec![S], I32),
            ("charAt", "(I)C") => (Self::CharAt, vec![S, I32], I32),
            ("codePointAt", "(I)I") => (Self::CodePointAt, vec![S, I32], I32),
            ("coder", "()B") => (Self::Coder, vec![S], I32),
            ("getBytes", "([BIB)V") => (
                Self::GetBytes,
                vec![S, Array(ArrayKind::Byte), I32, I32],
                Void,
            ),
            ("getBytes", "([BIIBI)V") => (
                Self::GetBytesRange,
                vec![S, Array(ArrayKind::Byte), I32, I32, I32, I32],
                Void,
            ),
            ("regionMatches", "(ILjava/lang/String;II)Z") => {
                (Self::RegionMatches, vec![S, I32, S, I32, I32], I32)
            }
            ("regionMatches", "(ZILjava/lang/String;II)Z") => (
                Self::RegionMatchesIgnoreCase,
                vec![S, I32, I32, S, I32, I32],
                I32,
            ),
            ("hashCode", "()I") => (Self::HashCode, vec![S], I32),
            ("equals", "(Ljava/lang/Object;)Z") => (Self::Equals, vec![S, AnyRef], I32),
            ("compareTo", "(Ljava/lang/String;)I") => (Self::CompareTo, vec![S, S], I32),
            ("toString", "()Ljava/lang/String;") => (Self::ToString, vec![S], S),
            ("intern", "()Ljava/lang/String;") => (Self::Intern, vec![S], S),
            ("equalsIgnoreCase", "(Ljava/lang/String;)Z") => {
                (Self::EqualsIgnoreCase, vec![S, S], I32)
            }
            ("indexOf", "(I)I") => (Self::IndexOfCodePoint, vec![S, I32], I32),
            ("indexOf", "(II)I") => (Self::IndexOfCodePointFrom, vec![S, I32, I32], I32),
            ("lastIndexOf", "(I)I") => (Self::LastIndexOfCodePoint, vec![S, I32], I32),
            ("lastIndexOf", "(II)I") => (Self::LastIndexOfCodePointFrom, vec![S, I32, I32], I32),
            ("indexOf", "(Ljava/lang/String;)I") => (Self::IndexOfString, vec![S, S], I32),
            ("indexOf", "(Ljava/lang/String;I)I") => {
                (Self::IndexOfStringFrom, vec![S, S, I32], I32)
            }
            ("lastIndexOf", "(Ljava/lang/String;)I") => (Self::LastIndexOfString, vec![S, S], I32),
            ("lastIndexOf", "(Ljava/lang/String;I)I") => {
                (Self::LastIndexOfStringFrom, vec![S, S, I32], I32)
            }
            ("substring", "(I)Ljava/lang/String;") => (Self::Substring, vec![S, I32], S),
            ("substring", "(II)Ljava/lang/String;") => (Self::SubstringRange, vec![S, I32, I32], S),
            ("trim", "()Ljava/lang/String;") => (Self::Trim, vec![S], S),
            _ => bail!("Unsupported bootstrap String method {name}{descriptor}"),
        };
        Ok((operation, Signature { arguments, result }))
    }
}
impl Op {
    fn constructor(&self) -> Option<(Option<usize>, &Signature)> {
        match self {
            Self::Initialize(target, signature) => Some((*target, signature)),
            Self::InitializeString(signature) => Some((None, signature)),
            Self::ProtectedInitialize(target, signature, _) => Some((Some(*target), signature)),
            _ => None,
        }
    }
}
#[derive(Debug, Clone)]
struct Instruction {
    pc: usize,
    next: usize,
    op: Op,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Local {
    Value(Type),
    Tail,
}
#[derive(Debug, Clone, PartialEq, Eq)]
struct Frame {
    locals: Vec<Option<Local>>,
    stack: Vec<Type>,
    this_initialized: bool,
}
impl Frame {
    fn pop(&mut self, ty: Type) -> Result<()> {
        self.pop_with(ty, None)
    }
    fn pop_with(&mut self, ty: Type, links: Option<&dyn StaticLinker>) -> Result<()> {
        let actual = self.stack.pop().context("Operand stack underflow")?;
        ensure!(
            actual == ty
                || (actual == Type::Null && ty.is_reference())
                || (ty == Type::AnyRef && actual.is_reference())
                || links
                    .map(|links| links.assignable(actual, ty))
                    .transpose()?
                    .unwrap_or(false),
            "Operand type mismatch or underflow: expected {ty:?}, found {actual:?}"
        );
        Ok(())
    }
    fn initialize(&mut self, receiver: Type) {
        let initialized = match receiver {
            Type::UninitializedString(_) => Type::BootstrapString,
            Type::UninitializedLinked(_, owner) | Type::UninitializedLinkedThis(owner) => {
                Type::LinkedObject(owner)
            }
            _ => Type::Object,
        };
        for ty in &mut self.stack {
            if *ty == receiver {
                *ty = initialized;
            }
        }
        for local in &mut self.locals {
            if *local == Some(Local::Value(receiver)) {
                *local = Some(Local::Value(initialized));
            }
        }
        if matches!(
            receiver,
            Type::UninitializedThis | Type::UninitializedLinkedThis(_)
        ) {
            self.this_initialized = true;
        }
    }
    fn pop_array(
        &mut self,
        kind: Option<ArrayKind>,
        links: Option<&dyn StaticLinker>,
    ) -> Result<()> {
        let actual = self.stack.pop().context("Array stack underflow")?;
        ensure!(
            match actual {
                Type::Null => true,
                Type::ObjectArray
                | Type::LinkedObjectArray(_)
                | Type::BootstrapStringArray
                | Type::BootstrapClassArray => kind.is_none(),
                Type::Array(array) => kind.is_none_or(|expected| array == expected
                    || (array == ArrayKind::Boolean && expected == ArrayKind::Byte)),
                _ =>
                    if let Some(links) = links {
                        if let Some(kind) = kind {
                            links.primitive_array(actual, kind)?
                        } else {
                            links.is_array(actual)?
                        }
                    } else {
                        false
                    },
            },
            "Wrong array element/reference type"
        );
        Ok(())
    }
    fn store(&mut self, index: usize, ty: Type) -> Result<()> {
        ensure!(
            index + ty.width() <= self.locals.len(),
            "Local index outside max_locals"
        );
        // Writing either half invalidates the old category-2 local.
        for slot in index..index + ty.width() {
            if self.locals[slot] == Some(Local::Tail) && slot > 0 {
                self.locals[slot - 1] = None;
            }
            if let Some(Local::Value(old)) = self.locals[slot]
                && old.width() == 2
                && slot + 1 < self.locals.len()
            {
                self.locals[slot + 1] = None;
            }
            self.locals[slot] = None;
        }
        self.locals[index] = Some(Local::Value(ty));
        if ty.width() == 2 {
            self.locals[index + 1] = Some(Local::Tail);
        }
        Ok(())
    }
    fn normalize(&mut self) {
        for index in 0..self.locals.len() {
            match self.locals[index] {
                Some(Local::Tail)
                    if index == 0
                        || !matches!(
                            self.locals[index - 1],
                            Some(Local::Value(Type::I64 | Type::F64))
                        ) =>
                {
                    self.locals[index] = None
                }
                Some(Local::Value(Type::I64 | Type::F64))
                    if self.locals.get(index + 1) != Some(&Some(Local::Tail)) =>
                {
                    self.locals[index] = None
                }
                _ => (),
            }
        }
    }
}

fn byte(bytes: &[u8], p: &mut usize) -> Result<u8> {
    let b = *bytes.get(*p).context("Truncated bytecode")?;
    *p += 1;
    Ok(b)
}
fn u16(bytes: &[u8], p: &mut usize) -> Result<u16> {
    Ok(u16::from_be_bytes([byte(bytes, p)?, byte(bytes, p)?]))
}
fn i32(bytes: &[u8], p: &mut usize) -> Result<i32> {
    Ok(i32::from_be_bytes([
        byte(bytes, p)?,
        byte(bytes, p)?,
        byte(bytes, p)?,
        byte(bytes, p)?,
    ]))
}
fn target(pc: usize, offset: i32, len: usize) -> Result<usize> {
    let dest = pc as i64 + offset as i64;
    ensure!(dest >= 0 && dest < len as i64, "Branch target outside Code");
    Ok(dest as usize)
}
fn constant(class: &ClassFile, index: u16, wide: bool) -> Result<Op> {
    let (ty, bits) = match class.numeric(index)? {
        NumericConstant::Int(v) => (Type::I32, v as u32 as u64),
        NumericConstant::Long(v) => (Type::I64, v as u64),
        NumericConstant::Float(v) => (Type::F32, v as u64),
        NumericConstant::Double(v) => (Type::F64, v),
    };
    ensure!(
        (ty.width() == 2) == wide,
        "ldc/ldc2_w constant category mismatch"
    );
    Ok(Op::Constant(ty, bits))
}
pub(super) type InterfaceLink = (usize, Signature, Vec<usize>, Vec<usize>);

pub(super) trait StaticLinker {
    fn symbolic_reference(
        &self,
        _: &super::symbolic::Constant,
        _: u16,
        _: u8,
    ) -> Result<SymbolicReference> {
        bail!("Symbolic reference lowering requires a nominal IR environment")
    }
    fn class_loader_field(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("Class loader field requires its VM-owned representation")
    }
    fn class_loader_register(&self, _: &ClassFile, _: u16) -> Result<usize> {
        bail!("ClassLoader registration requires original private native source")
    }
    fn scoped_register(&self, _: &ClassFile, _: u16) -> Result<usize> {
        bail!("ScopedMemoryAccess registration requires its original source")
    }
    fn winfs_init(&self, _: &ClassFile, _: u16) -> Result<(usize, usize)> {
        bail!("WinNTFileSystem field mapping requires original source")
    }
    fn reflect_array(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::reflection_arrays::Operation,
    ) -> Result<(Signature, usize)> {
        bail!("Reflection array allocation requires its original native source")
    }
    fn windows_error_mode(&self, _: &ClassFile, _: u16) -> Result<usize> {
        bail!("Windows startup requires original private native source")
    }
    fn signal_control(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::signal_natives::Operation,
    ) -> Result<usize> {
        bail!("Signal control requires its original Java declaration and live VM transport")
    }
    fn access_context(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::access_context::Operation,
    ) -> Result<(Signature, usize)> {
        bail!("Access contexts require original java.base VM bindings")
    }
    fn primordial_body(&self, _: &ClassFile, _: &Code) -> bool {
        false
    }
    fn exception_method(&self, _: &ClassFile, _: &Method) -> Result<()> {
        Ok(())
    }
    fn context_bytes(&self) -> usize {
        16
    }
    fn normal_class_mirrors(&self) -> bool {
        false
    }
    fn runtime_resources(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::runtime_resources::Operation,
    ) -> Result<Signature> {
        bail!("Processor queries require original Runtime native source")
    }
    fn monitor_notify(&self, _: &ClassFile, _: u16, _: bool) -> Result<Signature> {
        bail!("Object notifications require verified Context32 monitors")
    }
    fn monitor_opcode(&self, _: &ClassFile) -> Result<()> {
        bail!("monitor bytecodes require the Context32 runtime")
    }
    fn npe_message(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("NPE diagnostics require verified source and Context32")
    }
    fn runtime_frames(&self) -> bool {
        false
    }
    fn runtime_stack_probe(&self) -> bool {
        false
    }
    fn string_case(&self, _: &ClassFile, _: u16) -> Result<()> {
        bail!("Unicode String comparison requires verified java.base and case tables")
    }
    fn string_concat_api(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("String.concat requires verified original java.base")
    }
    fn string_replace(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("String replacement requires original source and VM-owned UTF16 storage")
    }
    fn literal_regex_replace(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::literal_regex::Proof,
    ) -> Result<Signature> {
        bail!("Literal regex replacement requires verified original java.base")
    }
    fn string_construction(&self, _: &ClassFile, _: u16, _: bool) -> Result<()> {
        bail!("String construction requires verified java.base and VM String storage")
    }
    fn reflected_constructor(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::reflect_constructors::Operation,
    ) -> Result<(usize, Signature)> {
        bail!("Constructor reflection needs verified metadata")
    }
    fn reflected_field(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::reflect_fields::Operation,
    ) -> Result<Signature> {
        bail!("Field reflection requires verified metadata")
    }
    fn reflected_field_filter(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::field_filters::Proof,
    ) -> Result<Signature> {
        bail!("Field filter registration requires verified metadata")
    }
    fn reflect_new(&self, _: &ClassFile, _: u16) -> Result<(usize, Signature)> {
        bail!("Reflection requires a source-bound constructor image")
    }
    fn string_split(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("String split requires original public wrapper proof")
    }
    fn string_lowercase(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("Locale case conversion requires original source and UTF16 runtime")
    }
    fn string_chars(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("String character copy requires original source and VM-owned UTF16 storage")
    }
    fn string_prefix(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("String prefix comparison requires original source and VM UTF16 storage")
    }
    fn system_stream(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::system_streams::Operation,
    ) -> Result<(Signature, usize)> {
        bail!("System stream setters require verified private native source and static roots")
    }
    fn array_clone(&self, _: &ClassFile, _: u16) -> Result<(Signature, usize)> {
        bail!("Array clone requires original Object source and typed heap metadata")
    }
    fn identity_hash(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("System identity hashes require verified original java.base")
    }
    fn hex_string(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::hex_strings::Kind,
    ) -> Result<(Signature, usize)> {
        bail!("Hex strings require original numeric source and class initialization")
    }
    fn string_storage(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::string_storage::Property,
    ) -> Result<u32> {
        bail!("String storage configuration requires original VM-owned source")
    }
    fn builder_snapshot(&self, _: &ClassFile, _: u16) -> Result<(Signature, usize)> {
        bail!("Builder snapshot requires original inherited storage layout")
    }
    fn jdk_bridge(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::jdk_bridges::Kind,
    ) -> Result<(usize, Signature)> {
        bail!("JDK Java bridges require verified source")
    }
    fn class_query(&self, _: &ClassFile, _: u16, _: super::class_queries::Kind) -> Result<()> {
        bail!("Class queries require original VM source and nominal type metadata")
    }
    fn bitcast(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::bitcasts::Kind,
    ) -> Result<(Signature, usize)> {
        bail!("Bitcasts require original numeric VM source")
    }
    fn fixed_identity_hash(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("Array hashes require verified original Object native source")
    }
    fn raw_properties(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::system_properties::Operation,
    ) -> Result<(Signature, usize)> {
        bail!("Raw platform properties require original private native proof")
    }
    fn throwable_fill(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("Throwable capture requires original native fields and generated Java frames")
    }
    fn initializer_source_abi(&self) -> u32 {
        1
    }
    fn stream_init(&self, _: &ClassFile, _: u16) -> Result<usize> {
        bail!("Stream initIDs requires verified reference-field bindings")
    }
    fn constant_class_initialization(
        &self,
        _: &ClassFile,
        _: super::class_initialization::Site,
    ) -> Result<usize> {
        bail!("Constant Class initialization requires a source-verified bootstrap helper")
    }
    fn file_descriptor(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::file_descriptors::Operation,
    ) -> Result<usize> {
        bail!("FileDescriptor requires verified native field bindings")
    }
    fn cds(&self, _: &ClassFile, _: u16, _: super::cds::Operation) -> Result<usize> {
        bail!("CDS requires a verified no-archive runtime profile")
    }
    fn string_value(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::string_values::Kind,
    ) -> Result<super::string_values::Link> {
        bail!("String.valueOf requires source-verified primitive conversion metadata")
    }
    fn string_join(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::string_join::Kind,
    ) -> Result<super::string_join::Link> {
        bail!("String.join needs source-verified callbacks and the assembly string runtime")
    }
    fn system_registration(&self) -> bool {
        false
    }
    fn primitive_class(&self, _: &ClassFile) -> Result<()> {
        bail!("Primitive class lookup requires verified java.base native metadata")
    }
    fn resource_stream(&self, _: &ClassFile) -> Result<super::resources::Link> {
        bail!("Class resources require a verified frozen resource namespace")
    }
    fn method_monitor(&self, _: &ClassFile, method: &Method) -> Result<Option<usize>> {
        ensure!(
            method.access & 0x20 == 0,
            "Synchronized methods need verified monitor metadata"
        );
        Ok(None)
    }
    fn lambda_capture(&self, _: &ClassFile, _: u16) -> Result<(usize, Signature)> {
        bail!("Lambda capture requires a source-verified metadata linker")
    }
    fn require_non_null(&self) -> Result<()> {
        bail!("Objects.requireNonNull requires verified java.base metadata")
    }
    fn type_target(&self, _: &ClassFile, _: &str) -> Result<(usize, Type)> {
        bail!("Type checks require verified metadata and runtime type mapping")
    }
    fn module_intrinsic(
        &self,
        _: &ClassFile,
        _: super::modules::Operation,
    ) -> Result<(Signature, Option<usize>)> {
        bail!("Module operations require verified module identities")
    }
    fn get_class(&self, _: &ClassFile, _: &str, _: bool) -> Result<()> {
        bail!("Object.getClass requires runtime type mapping")
    }
    fn assignable(&self, _: Type, _: Type) -> Result<bool> {
        Ok(false)
    }
    fn reference_join(&self, _: Type, _: Type) -> Result<Option<Type>> {
        Ok(None)
    }
    fn resolve(&self, caller: &ClassFile, constant: u16) -> Result<(usize, Signature)>;
    fn field(&self, _caller: &ClassFile, _constant: u16) -> Result<LinkedField> {
        bail!("Static fields need a program class-state linker")
    }
    fn class_id(&self, _class: &ClassFile) -> Result<usize> {
        bail!("Missing linked class identity")
    }
    fn signature(&self, _class: &ClassFile, method: &Method) -> Result<Signature> {
        Signature::parse(&method.descriptor)
    }
    fn object_class(&self, _caller: &ClassFile, _name: &str) -> Result<usize> {
        bail!("Missing linked object class")
    }
    fn allocate_class(&self, caller: &ClassFile, name: &str) -> Result<usize> {
        self.object_class(caller, name)
    }
    fn constructor_parent(&self, _: usize, _: usize) -> Result<bool> {
        Ok(false)
    }
    fn protected_constructor_receiver(&self, _: &ClassFile, _: u16) -> Result<Option<usize>> {
        Ok(None)
    }
    fn direct_object_parent(&self, _: usize) -> Result<bool> {
        Ok(false)
    }
    fn root_object_allocation(&self, _: usize) -> Result<bool> {
        Ok(false)
    }
    fn class_for_name(&self, _: &ClassFile, _: u16) -> Result<Signature> {
        bail!("Class lookup requires a source-bound name/initialization catalog")
    }
    fn class_value_field(&self, _: &ClassFile, _: u16, _: bool) -> Result<Signature> {
        bail!("ClassValue fields require a source-verified mirror sidecar")
    }
    fn shutdown_native(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::shutdown::Operation,
    ) -> Result<(Signature, usize)> {
        bail!("Shutdown natives require original Java package provenance")
    }
    fn root_object_constructor(&self, _: &ClassFile) -> Result<bool> {
        Ok(false)
    }
    fn object_constructor(&self, caller: &ClassFile) -> Result<()> {
        ensure!(
            caller.super_name == "java/lang/Object",
            "Object constructor must initialize a direct Object subclass"
        );
        Ok(())
    }
    fn field_receivers(&self, field: &LinkedInstanceField) -> Result<Vec<usize>> {
        Ok(vec![field.owner])
    }
    fn covariant_arrays(&self) -> bool {
        false
    }
    fn typed_array(&self, _: &ClassFile, _: &str, _: u8) -> Result<(usize, Type)> {
        bail!("Typed arrays require loader-aware metadata")
    }
    fn is_array(&self, _: Type) -> Result<bool> {
        Ok(false)
    }
    fn primitive_array(&self, _: Type, _: ArrayKind) -> Result<bool> {
        Ok(false)
    }
    fn array_component(&self, _: Type) -> Result<Option<Type>> {
        Ok(None)
    }
    fn interface_call(&self, _: &ClassFile, _: u16) -> Result<InterfaceLink> {
        bail!("Interface dispatch requires hierarchy method selection")
    }
    fn inherited_virtual(&self, _: &ClassFile, _: u16) -> Result<Option<InterfaceLink>> {
        Ok(None)
    }
    fn special_call(&self, _: &ClassFile, _: u16) -> Result<Option<InterfaceLink>> {
        Ok(None)
    }
    fn instance(
        &self,
        _caller: &ClassFile,
        _constant: u16,
        _constructor: bool,
    ) -> Result<(usize, Signature)> {
        bail!("Missing linked instance target")
    }
    fn instance_field(&self, _caller: &ClassFile, _constant: u16) -> Result<LinkedInstanceField> {
        bail!("Missing linked instance field")
    }
    fn string_literal(&self, _: &ClassFile, _: u16) -> Result<usize> {
        bail!("String literals require a bootstrap runtime linker")
    }
    fn string_get_chars(&self, _: &ClassFile, _: u16) -> Result<()> {
        bail!("String.getChars requires a source-verified ASM binding")
    }
    fn concat(&self, _: &ClassFile, _: u16, _: super::concat::Plan) -> Result<usize> {
        bail!("String concatenation requires a program runtime linker")
    }
    fn vm_intrinsic(&self, _: &ClassFile, _: super::vm::Operation) -> Result<()> {
        bail!("VM services require a source-verified native binding")
    }
    fn vm_registration(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::vm_registration::Operation,
    ) -> Result<usize> {
        bail!("VM registration requires original bootstrap native source")
    }
    fn signal_lookup(&self, _: &ClassFile, _: u16) -> Result<usize> {
        bail!("Signal lookup requires original private source and Windows native runtime")
    }
    fn unsafe_native(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::unsafe_bootstrap::Operation,
    ) -> Result<(Signature, usize)> {
        bail!("Unsafe natives require original bootstrap source")
    }
    fn thread_native(
        &self,
        _: &ClassFile,
        _: u16,
        _: super::thread_natives::Operation,
    ) -> Result<usize> {
        bail!("Thread natives require original bootstrap registration and VM thread context")
    }
    fn assertion_status(&self) -> Result<()> {
        bail!("Assertion queries require an explicit startup policy and mirror ABI2")
    }
    fn class_constant(&self, caller: &ClassFile, name: &str) -> Result<usize> {
        self.class_literal(caller, name)
    }
    fn class_literal(&self, _: &ClassFile, _: &str) -> Result<usize> {
        bail!("Class constants require verified bootstrap metadata and mirrors")
    }
}

pub(super) enum SymbolicReference {
    ExternalCall(String, Signature, bool),
    DirectCall {
        method: usize,
        signature: Signature,
        is_static: bool,
        constructor: bool,
        protected_receiver: Option<usize>,
    },
    StaticField(LinkedField),
    InstanceField(LinkedInstanceField),
}

#[derive(Debug, Clone, Copy)]
pub(super) struct LinkedInstanceField {
    pub owner: usize,
    pub index: usize,
    pub offset: usize,
    pub ty: Type,
    pub access: u16,
    pub narrow: u8,
    pub receiver: Type,
    pub mapping: Option<usize>,
    pub storage_bytes: usize,
}

fn object_label(ty: Type) -> String {
    if let Type::LinkedObject(owner) = ty {
        format!("boom_layout{owner}")
    } else {
        "boom_class_layout".into()
    }
}
fn reference_label(ty: Type) -> String {
    if ty == Type::BootstrapClassArray {
        return "boom_mirror_array_layout".into();
    }
    if ty == Type::BootstrapStringArray {
        return "boom_string_array_layout".into();
    }
    if let Type::LinkedObjectArray(owner) = ty {
        format!("boom_ref_layout{owner}")
    } else {
        "boom_reference_array_layout".into()
    }
}

fn constant_with_links(
    class: &ClassFile,
    index: u16,
    wide: bool,
    links: Option<&dyn StaticLinker>,
) -> Result<Op> {
    if !wide && let Some(name) = class.class_literal(index)? {
        return Ok(Op::ClassLiteral(
            links
                .context("Class constants require a metadata-aware program linker")?
                .class_constant(class, &name)?,
        ));
    }
    if !wide && class.string_literal(index)?.is_some() {
        return Ok(Op::StringLiteral(
            links
                .context("String literals require a program bootstrap linker")?
                .string_literal(class, index)?,
        ));
    }
    constant(class, index, wide)
}

#[derive(Debug, Clone, Copy)]
pub(super) struct LinkedField {
    pub owner: usize,
    pub index: usize,
    pub ty: Type,
    pub access: u16,
    pub narrow: u8,
}

fn decode(code: &Code, class: &ClassFile) -> Result<Vec<Instruction>> {
    decode_with_links(code, class, None)
}

fn decode_with_links(
    code: &Code,
    class: &ClassFile,
    links: Option<&dyn StaticLinker>,
) -> Result<Vec<Instruction>> {
    let bytes = &code.bytes;
    // Parse all raw instructions before asking the linker for runtime services.
    // The same stream is persisted by the whole-input symbolic pipeline.
    let raw_instructions = super::symbolic::decode_stream(bytes)?;
    let mut raw_index = 0;
    let mut p = 0;
    let mut result: Vec<Instruction> = Vec::new();
    let primordial = links.is_some_and(|l| l.primordial_body(class, code));
    if primordial {
        super::thread_bootstrap::check(class, code)?;
    }
    while p < bytes.len() {
        if primordial && let Some(end) = super::thread_bootstrap::skip(p) {
            p = end;
            while raw_instructions
                .get(raw_index)
                .is_some_and(|raw| usize::from(raw.pc) < end)
            {
                raw_index += 1;
            }
            continue;
        }
        let raw = raw_instructions
            .get(raw_index)
            .context("Missing symbolic instruction")?;
        ensure!(
            usize::from(raw.pc) == p,
            "Typed lowering diverged from symbolic instruction boundaries"
        );
        raw_index += 1;
        let pc = p;
        let opcode = byte(bytes, &mut p)?;
        let op = match opcode {
            0x00 => Op::Nop,
            0x01 => Op::Constant(Type::Null, 0),
            0x02..=0x08 => Op::Constant(Type::I32, (opcode as i32 - 3) as u32 as u64),
            0x09..=0x0a => Op::Constant(Type::I64, (opcode - 9) as u64),
            0x0b..=0x0d => Op::Constant(Type::F32, ((opcode - 0x0b) as f32).to_bits() as u64),
            0x0e..=0x0f => Op::Constant(Type::F64, ((opcode - 0x0e) as f64).to_bits()),
            0x10 => Op::Constant(Type::I32, byte(bytes, &mut p)? as i8 as i32 as u32 as u64),
            0x11 => Op::Constant(Type::I32, u16(bytes, &mut p)? as i16 as i32 as u32 as u64),
            0x12 => constant_with_links(class, byte(bytes, &mut p)? as u16, false, links)?,
            0x13 => constant_with_links(class, u16(bytes, &mut p)?, false, links)?,
            0x14 => constant(class, u16(bytes, &mut p)?, true)?,
            0x15..=0x18 => Op::Load(
                Type::from_opcode(opcode - 0x15),
                byte(bytes, &mut p)? as usize,
            ),
            0x1a..=0x29 => Op::Load(
                Type::from_opcode((opcode - 0x1a) / 4),
                ((opcode - 0x1a) % 4) as usize,
            ),
            0x19 => Op::Load(Type::AnyRef, byte(bytes, &mut p)? as usize),
            0x2a..=0x2d => Op::Load(Type::AnyRef, (opcode - 0x2a) as usize),
            0x2e..=0x31 => Op::ArrayLoad(
                [
                    ArrayKind::Int,
                    ArrayKind::Long,
                    ArrayKind::Float,
                    ArrayKind::Double,
                ][(opcode - 0x2e) as usize],
            ),
            0x32 => Op::ReferenceArrayLoad,
            0x33..=0x35 => Op::ArrayLoad(
                [ArrayKind::Byte, ArrayKind::Char, ArrayKind::Short][(opcode - 0x33) as usize],
            ),
            0x36..=0x39 => Op::Store(
                Type::from_opcode(opcode - 0x36),
                byte(bytes, &mut p)? as usize,
            ),
            0x3b..=0x4a => Op::Store(
                Type::from_opcode((opcode - 0x3b) / 4),
                ((opcode - 0x3b) % 4) as usize,
            ),
            0x3a => Op::Store(Type::AnyRef, byte(bytes, &mut p)? as usize),
            0x4b..=0x4e => Op::Store(Type::AnyRef, (opcode - 0x4b) as usize),
            0x4f..=0x52 => Op::ArrayStore(
                [
                    ArrayKind::Int,
                    ArrayKind::Long,
                    ArrayKind::Float,
                    ArrayKind::Double,
                ][(opcode - 0x4f) as usize],
            ),
            0x53 => Op::ReferenceArrayStore,
            0x54..=0x56 => Op::ArrayStore(
                [ArrayKind::Byte, ArrayKind::Char, ArrayKind::Short][(opcode - 0x54) as usize],
            ),
            0x57 => Op::Pop,
            0x58 => Op::Pop2,
            0x59 => Op::Dup,
            0x5a | 0x5b | 0x5d | 0x5e => Op::Reorder(opcode),
            0x5c => Op::Dup2,
            0x5f => Op::Swap,
            0x60..=0x73 => {
                let ty = Type::from_opcode((opcode - 0x60) % 4);
                let binary = [
                    Binary::Add,
                    Binary::Sub,
                    Binary::Mul,
                    Binary::Div,
                    Binary::Rem,
                ][((opcode - 0x60) / 4) as usize];
                Op::Binary(ty, binary)
            }
            0x74..=0x77 => Op::Neg(Type::from_opcode(opcode - 0x74)),
            0x78..=0x83 => Op::Binary(
                if opcode % 2 == 0 {
                    Type::I32
                } else {
                    Type::I64
                },
                [
                    Binary::Shl,
                    Binary::Shr,
                    Binary::Ushr,
                    Binary::And,
                    Binary::Or,
                    Binary::Xor,
                ][((opcode - 0x78) / 2) as usize],
            ),
            0x84 => Op::Increment(
                byte(bytes, &mut p)? as usize,
                byte(bytes, &mut p)? as i8 as i32,
            ),
            0x85..=0x90 => {
                let (from, to) = [
                    (Type::I32, Type::I64),
                    (Type::I32, Type::F32),
                    (Type::I32, Type::F64),
                    (Type::I64, Type::I32),
                    (Type::I64, Type::F32),
                    (Type::I64, Type::F64),
                    (Type::F32, Type::I32),
                    (Type::F32, Type::I64),
                    (Type::F32, Type::F64),
                    (Type::F64, Type::I32),
                    (Type::F64, Type::I64),
                    (Type::F64, Type::F32),
                ][(opcode - 0x85) as usize];
                Op::Cast(from, to)
            }
            0x91..=0x93 => Op::Narrow(opcode),
            0x94 => Op::Compare(Type::I64, 0),
            0x95..=0x98 => Op::Compare(
                if opcode < 0x97 { Type::F32 } else { Type::F64 },
                if opcode % 2 == 1 { -1 } else { 1 },
            ),
            0x99..=0x9e => Op::If(
                opcode - 0x99,
                target(pc, u16(bytes, &mut p)? as i16 as i32, bytes.len())?,
            ),
            0x9f..=0xa4 => Op::IfPair(
                opcode - 0x9f,
                target(pc, u16(bytes, &mut p)? as i16 as i32, bytes.len())?,
            ),
            0xa7 => Op::Goto(target(pc, u16(bytes, &mut p)? as i16 as i32, bytes.len())?),
            0xa5 | 0xa6 => Op::IfRefs(
                opcode == 0xa6,
                target(pc, u16(bytes, &mut p)? as i16 as i32, bytes.len())?,
            ),
            0xaa | 0xab => {
                while !p.is_multiple_of(4) {
                    ensure!(byte(bytes, &mut p)? == 0, "Invalid switch padding");
                }
                let default = target(pc, i32(bytes, &mut p)?, bytes.len())?;
                let mut cases = Vec::new();
                if opcode == 0xaa {
                    let low = i32(bytes, &mut p)?;
                    let high = i32(bytes, &mut p)?;
                    let count = high as i64 - low as i64 + 1;
                    ensure!(
                        count > 0 && count <= ((bytes.len() - p) / 4) as i64,
                        "Invalid tableswitch bounds"
                    );
                    for key in low..=high {
                        cases.push((key, target(pc, i32(bytes, &mut p)?, bytes.len())?));
                    }
                } else {
                    let count = i32(bytes, &mut p)?;
                    ensure!(
                        count >= 0 && count as usize <= (bytes.len() - p) / 8,
                        "Invalid lookupswitch length"
                    );
                    for _ in 0..count {
                        let key = i32(bytes, &mut p)?;
                        ensure!(
                            cases.last().is_none_or(|(old, _)| *old < key),
                            "Unsorted switch keys"
                        );
                        cases.push((key, target(pc, i32(bytes, &mut p)?, bytes.len())?));
                    }
                }
                Op::Switch(default, cases)
            }
            0xac..=0xaf => Op::Return(Type::from_opcode(opcode - 0xac)),
            0xb0 => Op::Return(Type::AnyRef),
            0xb1 => Op::Return(Type::Void),
            0xbb => {
                let constant = u16(bytes, &mut p)?;
                let owner = class.constant_class(constant)?;
                if let Some(links) = links
                    && owner == super::string_construction::OWNER
                {
                    links.string_construction(class, constant, true)?;
                    Op::NewString
                } else if let Some(links) = links {
                    Op::NewLinkedObject(links.allocate_class(class, &owner)?)
                } else {
                    ensure!(owner == class.name, "new requires a linked class");
                    Op::NewObject
                }
            }
            0xb4 | 0xb5 => {
                let constant = u16(bytes, &mut p)?;
                if let Some(links) = links {
                    if matches!(class.field_reference(constant),Ok((o,n,d)) if super::class_loaders::field(&o,&n,&d))
                    {
                        ensure!(
                            opcode == 0xb4,
                            "Class.classLoader is assigned only by VM binding"
                        );
                        Op::ClassLoaderField(links.class_loader_field(class, constant)?)
                    } else if matches!(class.field_reference(constant),Ok((o,n,d)) if super::class_queries::class_value_field(&o,&n,&d))
                    {
                        links.class_literal(class, "java/lang/Class")?;
                        Op::ClassValueField(
                            links.class_value_field(class, constant, opcode == 0xb5)?,
                            opcode == 0xb5,
                        )
                    } else if opcode == 0xb4
                        && matches!(class.field_reference(constant),Ok((o,n,d)) if super::class_queries::component_field(&o,&n,&d))
                    {
                        links.class_literal(class, "java/lang/Class")?;
                        links.class_query(
                            class,
                            constant,
                            super::class_queries::Kind::ComponentField,
                        )?;
                        Op::ClassIntrinsic(
                            ClassIntrinsic::GetComponentType,
                            Signature {
                                arguments: vec![Type::BootstrapClass],
                                result: Type::BootstrapClass,
                            },
                        )
                    } else {
                        let field = links.instance_field(class, constant)?;
                        if opcode == 0xb4 {
                            Op::LinkedFieldLoad(field)
                        } else {
                            Op::LinkedFieldStore(field)
                        }
                    }
                } else {
                    let field = class.local_field_target(constant)?;
                    ensure!(
                        class.field_info[field].access & (8 | 0x40) == 0,
                        "Static/volatile fields require their runtime"
                    );
                    let ty = field_type(&class.field_info[field].descriptor)?;
                    if opcode == 0xb4 {
                        Op::FieldLoad(field, ty)
                    } else {
                        Op::FieldStore(field, ty)
                    }
                }
            }
            0xb6 | 0xb7 => {
                let constant = u16(bytes, &mut p)?;
                let (owner, name, descriptor) = if opcode == 0xb7 {
                    let (owner, name, descriptor, _) = class.special_method_reference(constant)?;
                    (owner, name, descriptor)
                } else {
                    class.method_reference(constant)?
                };
                if let Some(links) = links
                    && opcode == 0xb7
                    && owner == super::string_construction::OWNER
                    && name == "<init>"
                    && super::string_construction::supports(&descriptor)
                {
                    links.string_construction(class, constant, false)?;
                    Op::InitializeString(super::string_construction::signature(&descriptor))
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && let Some(op) =
                        super::reflect_fields::Operation::resolve(&owner, &name, &descriptor)
                {
                    Op::ReflectField(op, links.reflected_field(class, constant, op)?)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && let Some(op) =
                        super::reflect_constructors::Operation::resolve(&owner, &name, &descriptor)
                {
                    let (site, sig) = links.reflected_constructor(class, constant, op)?;
                    Op::ReflectConstructor(site, op, sig)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && let Some(op) =
                        super::runtime_resources::Operation::resolve(&owner, &name, &descriptor)
                {
                    Op::RuntimeResource(op, links.runtime_resources(class, constant, op)?)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && matches!(name.as_str(), "notify" | "notifyAll")
                    && descriptor == "()V"
                {
                    Op::MonitorNotify(
                        name == "notifyAll",
                        links.monitor_notify(class, constant, name == "notifyAll")?,
                    )
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && owner == "java/lang/NullPointerException"
                    && name == "getExtendedNPEMessage"
                    && descriptor == "()Ljava/lang/String;"
                {
                    Op::NpeMessage(links.npe_message(class, constant)?)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::throwables::is_fill(&owner, &name, &descriptor)
                {
                    Op::ThrowableFill(links.throwable_fill(class, constant)?)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && name == "getClass"
                    && descriptor == "()Ljava/lang/Class;"
                {
                    links.get_class(class, &owner, false)?;
                    Op::GetClass
                } else if opcode == 0xb7
                    && owner == "java/lang/Object"
                    && name == "<init>"
                    && descriptor == "()V"
                {
                    if let Some(links) = links {
                        links.object_constructor(class)?;
                    }
                    Op::Initialize(
                        None,
                        Signature {
                            arguments: vec![if let Some(links) = links {
                                Type::LinkedObject(links.class_id(class)?)
                            } else {
                                Type::Object
                            }],
                            result: Type::Void,
                        },
                    )
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && let Some(op) =
                        super::unsafe_bootstrap::Operation::resolve(&owner, &name, &descriptor)
                {
                    let (sig, owner) = links.unsafe_native(class, constant, op)?;
                    Op::UnsafeNative(op, sig, owner)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && let Some(kind) =
                        super::jdk_bridges::Kind::resolve(&owner, &name, &descriptor, false)
                {
                    let (target, sig) = links.jdk_bridge(class, constant, kind)?;
                    Op::BridgeCall(target, sig)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::builder_snapshot::is_snapshot(&owner, &name, &descriptor)
                {
                    let (sig, owner) = links.builder_snapshot(class, constant)?;
                    Op::BuilderSnapshot(sig, owner)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::array_clone::is_clone(&owner, &name, &descriptor)
                {
                    let (signature, owner) = links.array_clone(class, constant)?;
                    Op::ArrayClone(signature, owner)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::identity_hash::fixed_receiver(&owner)
                    && name == "hashCode"
                    && descriptor == "()I"
                {
                    Op::IdentityHash(links.fixed_identity_hash(class, constant)?, false)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::string_concat_api::is_concat(&owner, &name, &descriptor)
                {
                    Op::StringConcatApi(links.string_concat_api(class, constant)?)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::string_join::Kind::resolve(&owner, &name, &descriptor)
                        == Some(super::string_join::Kind::Replace)
                {
                    let link =
                        links.string_join(class, constant, super::string_join::Kind::Replace)?;
                    Op::StringJoin(link.id, link.signature, link.targets, link.owners)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::string_replace::is_replace(&owner, &name, &descriptor)
                {
                    Op::StringReplace(links.string_replace(class, constant)?)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::literal_regex::is_call(&owner, &name, &descriptor)
                {
                    let proof = super::literal_regex::prove(class, code, pc)?;
                    Op::LiteralRegexReplace(
                        proof.old,
                        proof.new,
                        links.literal_regex_replace(class, constant, proof)?,
                    )
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::string_chars::is_to_chars(&owner, &name, &descriptor)
                {
                    Op::StringChars(links.string_chars(class, constant)?)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::string_prefix::is_prefix(&owner, &name, &descriptor)
                {
                    Op::StringPrefix(links.string_prefix(class, constant)?)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::string_split::is_call(&owner, &name, &descriptor)
                {
                    Op::StringSplit(links.string_split(class, constant)?)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && super::string_lowercase::is_call(&owner, &name, &descriptor)
                {
                    Op::StringLowercase(links.string_lowercase(class, constant)?)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && owner == "java/lang/String"
                    && name == "getChars"
                    && descriptor == super::string_getchars::DESCRIPTOR
                {
                    links.string_get_chars(class, constant)?;
                    Op::StringGetChars(super::string_getchars::signature())
                } else if let Some(links) = links
                    && owner == "java/lang/String"
                    && opcode == 0xb6
                {
                    let (operation, signature) = StringIntrinsic::resolve(&name, &descriptor)?;
                    if matches!(
                        operation,
                        StringIntrinsic::Coder
                            | StringIntrinsic::GetBytes
                            | StringIntrinsic::GetBytesRange
                    ) {
                        links.string_storage(
                            class,
                            constant,
                            match operation {
                                StringIntrinsic::Coder => super::string_storage::Property::Coder,
                                StringIntrinsic::GetBytes => {
                                    super::string_storage::Property::GetBytes
                                }
                                _ => super::string_storage::Property::GetBytesRange,
                            },
                        )?;
                    } else if operation as u32 >= StringIntrinsic::EqualsIgnoreCase as u32 {
                        links.string_case(class, constant)?;
                    }
                    Op::StringIntrinsic(operation, signature)
                } else if let Some(links) = links
                    && opcode == 0xb6
                    && let Some(operation) =
                        super::modules::Operation::resolve(&owner, &name, &descriptor)?
                {
                    ensure!(
                        !operation.is_static(),
                        "Static layer service requires invokestatic"
                    );
                    let (signature, factory) = links.module_intrinsic(class, operation)?;
                    Op::ModuleIntrinsic(operation, signature, factory)
                } else if let Some(links) = links
                    && owner == "java/lang/Class"
                    && opcode == 0xb6
                {
                    if name == "getResourceAsStream" && descriptor == super::resources::DESCRIPTOR {
                        let link = links.resource_stream(class)?;
                        Op::ResourceStream(
                            link.caller,
                            link.signature,
                            link.class_id,
                            link.constructor,
                        )
                    } else if super::reflect_new::is_call(&owner, &name, &descriptor) {
                        {
                            let (site, sig) = links.reflect_new(class, constant)?;
                            Op::ReflectNew(site, sig)
                        }
                    } else {
                        links.class_literal(class, "java/lang/Class")?;
                        let (operation, signature) = ClassIntrinsic::resolve(&name, &descriptor)?;
                        if matches!(operation, ClassIntrinsic::DesiredAssertionStatus) {
                            links.assertion_status()?;
                        }
                        if matches!(
                            operation,
                            ClassIntrinsic::IsHidden
                                | ClassIntrinsic::IsInstance
                                | ClassIntrinsic::CanonicalName
                                | ClassIntrinsic::SimpleName
                        ) {
                            links.class_query(
                                class,
                                constant,
                                match operation {
                                    ClassIntrinsic::IsHidden => {
                                        super::class_queries::Kind::IsHidden
                                    }
                                    ClassIntrinsic::IsInstance => {
                                        super::class_queries::Kind::IsInstance
                                    }
                                    ClassIntrinsic::CanonicalName => {
                                        super::class_queries::Kind::CanonicalName
                                    }
                                    ClassIntrinsic::SimpleName => {
                                        super::class_queries::Kind::SimpleName
                                    }
                                    _ => unreachable!(),
                                },
                            )?;
                        }
                        Op::ClassIntrinsic(operation, signature)
                    }
                } else if let Some(links) = links {
                    ensure!(
                        !name.starts_with('<') || (opcode == 0xb7 && name == "<init>"),
                        "Invalid special method call"
                    );
                    if opcode == 0xb7
                        && name != "<init>"
                        && let Some((site, sig, targets, owners)) =
                            links.special_call(class, constant)?
                    {
                        Op::InterfaceCall(site, sig, targets, owners)
                    } else if opcode == 0xb6
                        && let Some((site, sig, targets, owners)) =
                            links.inherited_virtual(class, constant)?
                    {
                        Op::InterfaceCall(site, sig, targets, owners)
                    } else {
                        ensure!(
                            opcode != 0xb7 || name == "<init>" || owner == class.name,
                            "Superclass/default special calls require verified hierarchy support"
                        );
                        // Direct Object subclasses have no class inheritance overrides.
                        let (target, sig) = links.instance(class, constant, name == "<init>")?;
                        if name == "<init>" {
                            if let Some(receiver) =
                                links.protected_constructor_receiver(class, constant)?
                            {
                                Op::ProtectedInitialize(target, sig, receiver)
                            } else {
                                Op::Initialize(Some(target), sig)
                            }
                        } else {
                            Op::InstanceCall(target, sig)
                        }
                    }
                } else {
                    let target = class.local_method_target(constant)?;
                    ensure!(
                        class.methods[target].access & 8 == 0,
                        "Instance call target is static"
                    );
                    let sig = method_signature(class, &class.methods[target])?;
                    if name == "<init>" {
                        ensure!(
                            opcode == 0xb7 && sig.result == Type::Void,
                            "Invalid constructor invocation"
                        );
                        Op::Initialize(Some(target), sig)
                    } else {
                        ensure!(!name.starts_with('<'), "Invalid instance target");
                        Op::InstanceCall(target, sig)
                    }
                }
            }
            0xbc => Op::NewArray(ArrayKind::from_atype(byte(bytes, &mut p)?)?),
            0xbd => {
                let owner = class.constant_class(u16(bytes, &mut p)?)?;
                if owner.starts_with('[') {
                    let (id, ty) = links
                        .context("Nested arrays require a program linker")?
                        .typed_array(class, &format!("[{owner}"), 1)?;
                    Op::NewTypedArray(id, ty, 1)
                } else if let Some(links) = links
                    && owner == "java/lang/Class"
                {
                    links.class_literal(class, "java/lang/Class")?;
                    Op::NewClassArray
                } else if links.is_some() && owner == "java/lang/String" {
                    Op::NewStringArray
                } else if let Some(links) = links {
                    Op::NewLinkedReferenceArray(links.object_class(class, &owner)?)
                } else {
                    ensure!(
                        owner == class.name,
                        "Reference array component requires the class linker"
                    );
                    Op::NewReferenceArray
                }
            }
            0xb9 => {
                let constant = u16(bytes, &mut p)?;
                let count = byte(bytes, &mut p)?;
                let reserved = byte(bytes, &mut p)?;
                ensure!(
                    count != 0 && reserved == 0,
                    "Invalid invokeinterface count/reserved bytes"
                );
                let (owner, name, descriptor) = class.interface_method_reference(constant)?;
                let links = links.context("invokeinterface requires program mode")?;
                if name == "getClass" && descriptor == "()Ljava/lang/Class;" {
                    ensure!(count == 1, "Wrong invokeinterface slot count");
                    links.get_class(class, &owner, true)?;
                    Op::GetClass
                } else {
                    let (site, signature, calls, classes) =
                        links.interface_call(class, constant)?;
                    ensure!(
                        signature
                            .arguments
                            .iter()
                            .map(|ty| ty.width())
                            .sum::<usize>()
                            == count as usize,
                        "Wrong invokeinterface slot count"
                    );
                    Op::InterfaceCall(site, signature, calls, classes)
                }
            }
            0xbe => Op::ArrayLength,
            0xc5 => {
                let descriptor = class.constant_class(u16(bytes, &mut p)?)?;
                let dimensions = byte(bytes, &mut p)?;
                let (id, ty) = links
                    .context("multianewarray requires a program linker")?
                    .typed_array(class, &descriptor, dimensions)?;
                Op::NewTypedArray(id, ty, dimensions)
            }
            0xbf => Op::Throw,
            0xc2 | 0xc3 => {
                links
                    .context("monitor bytecodes require a program runtime")?
                    .monitor_opcode(class)?;
                Op::Monitor(opcode == 0xc2)
            }
            0xc0 | 0xc1 => {
                let name = class.constant_class(u16(bytes, &mut p)?)?;
                let (id, ty) = links
                    .context("checkcast/instanceof require a metadata-aware program linker")?
                    .type_target(class, &name)?;
                if opcode == 0xc0 {
                    Op::CheckCast(id, ty)
                } else {
                    Op::InstanceOf(id)
                }
            }
            0xb8 => {
                let constant = u16(bytes, &mut p)?;
                if let Some(links) = links {
                    let (owner, name, descriptor, interface) =
                        class.static_method_reference(constant)?;
                    if !interface && super::field_filters::is_call(&owner, &name, &descriptor) {
                        let proof = super::field_filters::prove(class, code, pc)?;
                        Op::ReflectField(
                            super::reflect_fields::Operation::RegisterFilter,
                            links.reflected_field_filter(class, constant, proof)?,
                        )
                    } else if !interface
                        && super::file_streams::resolves(&owner, &name, &descriptor)
                    {
                        Op::StreamInit(links.stream_init(class, constant)?)
                    } else if !interface
                        && super::class_initialization::resolves(&owner, &name, &descriptor)
                    {
                        let previous = result
                            .last()
                            .context("Initialization helper requires a constant Class argument")?;
                        let Op::ClassLiteral(mirror) = previous.op else {
                            bail!(
                                "Initialization helper requires an immediately preceding constant Class"
                            )
                        };
                        let literal = match bytes[previous.pc] {
                            0x12 => u16::from(bytes[previous.pc + 1]),
                            0x13 => {
                                u16::from_be_bytes([bytes[previous.pc + 1], bytes[previous.pc + 2]])
                            }
                            _ => unreachable!(),
                        };
                        let target = class
                            .class_literal(literal)?
                            .context("Missing initialization Class constant")?;
                        let site = super::class_initialization::site(
                            class, code, pc, constant, &target, mirror,
                        )?;
                        Op::ConstantClassInitialization(
                            links.constant_class_initialization(class, site)?,
                        )
                    } else if interface {
                        let (target, signature) = links.resolve(class, constant)?;
                        Op::Call(target, signature)
                    } else if let Some(op) =
                        super::system_properties::Operation::resolve(&owner, &name, &descriptor)
                    {
                        let (signature, owner) = links.raw_properties(class, constant, op)?;
                        Op::RawProperties(op, signature, owner)
                    } else if super::class_for_name::is_call(&owner, &name, &descriptor) {
                        Op::ClassForName(
                            links.class_for_name(class, constant)?,
                            super::class_for_name::is_bootstrap_call(&owner, &name, &descriptor),
                        )
                    } else if let Some(op) =
                        super::shutdown::Operation::resolve(&owner, &name, &descriptor)
                    {
                        let (signature, owner) = links.shutdown_native(class, constant, op)?;
                        Op::ShutdownNative(op, signature, owner)
                    } else if let Some(op) =
                        super::file_descriptors::Operation::resolve(&owner, &name, &descriptor)
                    {
                        Op::FileDescriptor(op, links.file_descriptor(class, constant, op)?)
                    } else if let Some(op) =
                        super::cds::Operation::resolve(&owner, &name, &descriptor)
                    {
                        Op::Cds(op, links.cds(class, constant, op)?)
                    } else if let Some(kind) =
                        super::jdk_bridges::Kind::resolve(&owner, &name, &descriptor, true)
                    {
                        let (target, sig) = links.jdk_bridge(class, constant, kind)?;
                        Op::Call(target, sig)
                    } else if let Some(kind) =
                        super::bitcasts::Kind::resolve(&owner, &name, &descriptor)
                    {
                        let (sig, owner) = links.bitcast(class, constant, kind)?;
                        Op::Bitcast(sig, owner)
                    } else if super::string_storage::endian_method(&owner, &name, &descriptor) {
                        Op::Constant(
                            Type::I32,
                            u64::from(links.string_storage(
                                class,
                                constant,
                                super::string_storage::Property::BigEndian,
                            )?),
                        )
                    } else if let Some(kind) =
                        super::hex_strings::Kind::resolve(&owner, &name, &descriptor)
                    {
                        let (sig, owner) = links.hex_string(class, constant, kind)?;
                        Op::HexString(kind, sig, owner)
                    } else if let Some(kind) =
                        super::string_values::Kind::resolve(&owner, &name, &descriptor)
                    {
                        match links.string_value(class, constant, kind)? {
                            super::string_values::Link::Concat(id, sig, owner) => {
                                Op::Concat(id, sig, owner)
                            }
                            super::string_values::Link::Boolean(literals) => {
                                Op::BooleanString(literals)
                            }
                        }
                    } else if let Some(kind) =
                        super::string_join::Kind::resolve(&owner, &name, &descriptor)
                            .filter(|k| *k != super::string_join::Kind::Replace)
                    {
                        let link = links.string_join(class, constant, kind)?;
                        Op::StringJoin(link.id, link.signature, link.targets, link.owners)
                    } else if owner == "java/util/Objects"
                        && name == "requireNonNull"
                        && descriptor == "(Ljava/lang/Object;)Ljava/lang/Object;"
                    {
                        links.require_non_null()?;
                        Op::RequireNonNull
                    } else if let Some(op) =
                        super::modules::Operation::resolve(&owner, &name, &descriptor)?
                    {
                        ensure!(
                            op.is_static(),
                            "Instance module service requires invokevirtual"
                        );
                        let (signature, factory) = links.module_intrinsic(class, op)?;
                        Op::ModuleIntrinsic(op, signature, factory)
                    } else if super::identity_hash::system_member(&owner, &name, &descriptor) {
                        Op::IdentityHash(links.identity_hash(class, constant)?, true)
                    } else if let Some(op) =
                        super::system_streams::Operation::resolve(&owner, &name, &descriptor)
                    {
                        let (sig, owner) = links.system_stream(class, constant, op)?;
                        Op::SystemStream(sig, op, owner)
                    } else if let Some(op) =
                        super::access_context::Operation::resolve(&owner, &name, &descriptor)
                    {
                        let (sig, owner) = links.access_context(class, constant, op)?;
                        Op::AccessContext(op, sig, owner)
                    } else if let Some(op) =
                        super::unsafe_bootstrap::Operation::resolve(&owner, &name, &descriptor)
                    {
                        ensure!(
                            op == super::unsafe_bootstrap::Operation::Register,
                            "Unsafe instance native requires invokevirtual"
                        );
                        let (sig, owner) = links.unsafe_native(class, constant, op)?;
                        Op::UnsafeNative(op, sig, owner)
                    } else if super::signals::is_lookup(&owner, &name, &descriptor) {
                        Op::SignalFind(links.signal_lookup(class, constant)?)
                    } else if let Some(op) =
                        super::reflection_arrays::Operation::resolve(&owner, &name, &descriptor)
                    {
                        let (sig, owner) = links.reflect_array(class, constant, op)?;
                        Op::ReflectArray(op, sig, owner)
                    } else if super::winnt_file_system::initialization(&owner, &name, &descriptor) {
                        let (owner, file) = links.winfs_init(class, constant)?;
                        Op::WinFsInit(owner, file)
                    } else if super::scoped_memory::registration(&owner, &name, &descriptor) {
                        Op::ScopedRegister(links.scoped_register(class, constant)?)
                    } else if super::class_loaders::registration(&owner, &name, &descriptor) {
                        Op::ClassLoaderRegister(links.class_loader_register(class, constant)?)
                    } else if super::windows_startup::is_native(&owner, &name, &descriptor) {
                        Op::WindowsErrorMode(links.windows_error_mode(class, constant)?)
                    } else if let Some(op) =
                        super::signal_natives::Operation::resolve(&owner, &name, &descriptor)
                    {
                        Op::SignalControl(op, links.signal_control(class, constant, op)?)
                    } else if let Some(op) =
                        super::thread_natives::Operation::resolve(&owner, &name, &descriptor)
                    {
                        Op::ThreadNative(op, links.thread_native(class, constant, op)?)
                    } else if let Some(op) =
                        super::vm_registration::Operation::resolve(&owner, &name, &descriptor)
                    {
                        Op::VmNative(op, links.vm_registration(class, constant, op)?)
                    } else if let Some(op) =
                        super::vm::Operation::resolve(&owner, &name, &descriptor)
                    {
                        links.vm_intrinsic(class, op)?;
                        Op::VmIntrinsic(op)
                    } else if owner == "java/lang/Class"
                        && name == "getPrimitiveClass"
                        && descriptor == super::mirrors::PRIMITIVE_DESCRIPTOR
                    {
                        links.primitive_class(class)?;
                        Op::PrimitiveClass(Signature {
                            arguments: vec![Type::BootstrapString],
                            result: Type::BootstrapClass,
                        })
                    } else {
                        let (target, signature) = links.resolve(class, constant)?;
                        Op::Call(target, signature)
                    }
                } else {
                    let method = class.local_static_target(constant)?;
                    Op::Call(method, Signature::parse(&class.methods[method].descriptor)?)
                }
            }
            0xba => {
                let constant = u16(bytes, &mut p)?;
                ensure!(
                    u16(bytes, &mut p)? == 0,
                    "InvokeDynamic reserved bytes must be zero"
                );
                let site = class.dynamic_site(constant)?;
                if site.bootstrap.owner == "java/lang/invoke/LambdaMetafactory"
                    || site.bootstrap.owner == super::records::BOOTSTRAP_OWNER
                {
                    let (target, signature) = links
                        .context("Lambda capture requires a program linker")?
                        .lambda_capture(class, constant)?;
                    Op::Call(target, signature)
                } else {
                    let plan = super::concat::plan(class, &site)?;
                    let signature = Signature {
                        arguments: plan
                            .arguments
                            .iter()
                            .map(|arg| match arg {
                                super::concat::Argument::Long => Type::I64,
                                super::concat::Argument::String => Type::BootstrapString,
                                _ => Type::I32,
                            })
                            .collect(),
                        result: Type::BootstrapString,
                    };
                    Op::Concat(
                        links
                            .context("Concat requires a program linker")?
                            .concat(class, constant, plan)?,
                        signature,
                        None,
                    )
                }
            }
            0xb2 | 0xb3 => {
                let constant = u16(bytes, &mut p)?;
                let links = links.context("getstatic/putstatic requires program mode")?;
                if opcode == 0xb2
                    && matches!(class.field_reference(constant),Ok((owner,name,descriptor)) if super::string_storage::compact_field(&owner,&name,&descriptor))
                {
                    Op::Constant(
                        Type::I32,
                        u64::from(links.string_storage(
                            class,
                            constant,
                            super::string_storage::Property::CompactStrings,
                        )?),
                    )
                } else {
                    let field = links.field(class, constant)?;
                    if opcode == 0xb2 {
                        Op::StaticLoad(field)
                    } else {
                        Op::StaticStore(field)
                    }
                }
            }
            0xc4 => {
                let op = byte(bytes, &mut p)?;
                let index = u16(bytes, &mut p)? as usize;
                match op {
                    0x15..=0x18 => Op::Load(Type::from_opcode(op - 0x15), index),
                    0x36..=0x39 => Op::Store(Type::from_opcode(op - 0x36), index),
                    0x84 => Op::Increment(index, u16(bytes, &mut p)? as i16 as i32),
                    0x19 => Op::Load(Type::AnyRef, index),
                    0x3a => Op::Store(Type::AnyRef, index),
                    _ => bail!("Unsupported numeric wide instruction"),
                }
            }
            0xc8 => Op::Goto(target(pc, i32(bytes, &mut p)?, bytes.len())?),
            0xc6 | 0xc7 => Op::IfNull(
                opcode == 0xc7,
                target(pc, u16(bytes, &mut p)? as i16 as i32, bytes.len())?,
            ),
            _ => bail!("Unsupported numeric opcode 0x{opcode:02x} at bytecode {pc}"),
        };
        ensure!(
            usize::from(raw.next) == p,
            "Typed lowering consumed a different symbolic operand at {pc}"
        );
        let op = if primordial && let Some(taken) = super::thread_bootstrap::branch(pc) {
            let (kind, relation, target) = match op {
                Op::If(r, d) => (0, r, d),
                Op::IfPair(r, d) => (1, r, d),
                Op::IfNull(ne, d) => (2, u8::from(ne), d),
                Op::IfRefs(ne, d) => (3, u8::from(ne), d),
                _ => bail!("Primordial guard must retain a conditional instruction"),
            };
            Op::BootGuard(kind, relation, taken, if taken { target } else { p })
        } else {
            op
        };
        result.push(Instruction { pc, next: p, op });
    }
    validate_initialization_predecessors(&result, code)?;
    Ok(result)
}

fn validate_initialization_predecessors(instructions: &[Instruction], code: &Code) -> Result<()> {
    let calls: BTreeSet<_> = instructions
        .iter()
        .filter_map(|i| matches!(i.op, Op::ConstantClassInitialization(_)).then_some(i.pc))
        .collect();
    if calls.is_empty() {
        return Ok(());
    }
    for instruction in instructions {
        let bypass = match &instruction.op {
            Op::Goto(pc)
            | Op::If(_, pc)
            | Op::IfPair(_, pc)
            | Op::IfNull(_, pc)
            | Op::IfRefs(_, pc) => calls.contains(pc),
            Op::Switch(default, cases) => {
                calls.contains(default) || cases.iter().any(|(_, pc)| calls.contains(pc))
            }
            _ => false,
        };
        ensure!(
            !bypass,
            "Initialization call has an incoming edge bypassing its constant Class"
        );
    }
    ensure!(
        !code
            .handlers
            .iter()
            .any(|h| calls.contains(&usize::from(h.handler_pc))),
        "Initialization handler entry bypasses its constant Class"
    );
    Ok(())
}

#[cfg(test)]
mod initialization_edge_tests {
    use super::*;
    fn instruction(pc: usize, op: Op) -> Instruction {
        Instruction {
            pc,
            next: pc + 1,
            op,
        }
    }
    fn code() -> Code {
        Code {
            max_stack: 1,
            max_locals: 0,
            bytes: vec![0; 4],
            handlers: vec![],
        }
    }
    #[test]
    fn literal_initialization_accepts_normal_fallthrough_and_consumes_a_class() {
        let ops = vec![
            instruction(0, Op::ClassLiteral(7)),
            instruction(1, Op::ConstantClassInitialization(2)),
            instruction(2, Op::Return(Type::Void)),
        ];
        let sig = Signature {
            arguments: vec![],
            result: Type::Void,
        };
        assert!(validate_initialization_predecessors(&ops, &code()).is_ok());
        assert!(verify(&ops, &code(), &sig).is_ok());
        let wrong = vec![
            instruction(0, Op::Constant(Type::I32, 7)),
            ops[1].clone(),
            ops[2].clone(),
        ];
        assert!(verify(&wrong, &code(), &sig).is_err());
    }
    #[test]
    fn literal_initialization_rejects_all_direct_branch_and_switch_bypasses() {
        for op in [
            Op::Goto(1),
            Op::If(0, 1),
            Op::IfPair(0, 1),
            Op::IfNull(false, 1),
            Op::IfRefs(false, 1),
            Op::Switch(1, vec![]),
            Op::Switch(2, vec![(9, 1)]),
        ] {
            let ops = vec![
                instruction(0, Op::ClassLiteral(7)),
                instruction(1, Op::ConstantClassInitialization(2)),
                instruction(2, op),
            ];
            assert!(validate_initialization_predecessors(&ops, &code()).is_err());
        }
    }
    #[test]
    fn literal_initialization_rejects_exception_handler_bypasses() {
        let ops = vec![
            instruction(0, Op::ClassLiteral(7)),
            instruction(1, Op::ConstantClassInitialization(2)),
        ];
        let mut code = code();
        code.handlers
            .push(super::super::classfile::ExceptionHandler {
                start_pc: 0,
                end_pc: 1,
                handler_pc: 1,
                catch_type: None,
            });
        assert!(validate_initialization_predecessors(&ops, &code).is_err());
        code.handlers[0].handler_pc = 0;
        assert!(validate_initialization_predecessors(&ops, &code).is_ok());
    }
}

struct ExceptionTypes {
    throwable: Type,
    catches: Vec<Type>,
}

fn exception_types(
    class: &ClassFile,
    code: &Code,
    instructions: &[Instruction],
    links: Option<&dyn StaticLinker>,
) -> Result<Option<ExceptionTypes>> {
    if code.handlers.is_empty() && !instructions.iter().any(|inst| matches!(inst.op, Op::Throw)) {
        return Ok(None);
    }
    let links = links.context("Exceptions require loader-verified Throwable metadata")?;
    let (_, throwable) = links.type_target(class, "java/lang/Throwable")?;
    ensure!(
        throwable.is_reference(),
        "Throwable must resolve to a reference type"
    );
    let mut catches = Vec::new();
    for handler in &code.handlers {
        let ty = if let Some(name) = &handler.catch_type {
            let (_, ty) = links.type_target(class, name)?;
            ensure!(
                ty == throwable || links.assignable(ty, throwable)?,
                "Exception handler type {name} is not assignable to bootstrap Throwable"
            );
            ty
        } else {
            throwable
        };
        catches.push(ty);
    }
    Ok(Some(ExceptionTypes { throwable, catches }))
}

#[cfg(test)]
fn verify(
    instructions: &[Instruction],
    code: &Code,
    signature: &Signature,
) -> Result<BTreeMap<usize, Frame>> {
    verify_method(instructions, code, signature, false)
}

#[cfg(test)]
fn verify_method(
    instructions: &[Instruction],
    code: &Code,
    signature: &Signature,
    constructor: bool,
) -> Result<BTreeMap<usize, Frame>> {
    verify_method_with_links(instructions, code, signature, constructor, None, None)
}
fn verify_method_with_links(
    instructions: &[Instruction],
    code: &Code,
    signature: &Signature,
    constructor: bool,
    links: Option<&dyn StaticLinker>,
    exceptions: Option<&ExceptionTypes>,
) -> Result<BTreeMap<usize, Frame>> {
    let pop = |frame: &mut Frame, ty: Type| {
        if links.is_some() {
            frame.pop_with(ty, links)
        } else {
            frame.pop(ty)
        }
    };
    ensure!(
        instructions
            .len()
            .saturating_mul(usize::from(code.max_locals) + usize::from(code.max_stack) + 1)
            <= 20_000_000,
        "Method verification exceeds the operand/local state budget"
    );
    let indices: BTreeMap<_, _> = instructions
        .iter()
        .enumerate()
        .map(|(i, inst)| (inst.pc, i))
        .collect();
    ensure!(indices.contains_key(&0), "Empty Code");
    for inst in instructions {
        let targets = match &inst.op {
            Op::If(_, dest)
            | Op::IfPair(_, dest)
            | Op::IfRefs(_, dest)
            | Op::IfNull(_, dest)
            | Op::Goto(dest)
            | Op::BootGuard(_, _, _, dest) => vec![*dest],
            Op::Switch(default, cases) => std::iter::once(*default)
                .chain(cases.iter().map(|(_, dest)| *dest))
                .collect(),
            _ => Vec::new(),
        };
        for dest in targets {
            ensure!(
                indices.contains_key(&dest),
                "Branch/switch target is not an instruction boundary"
            );
        }
    }
    ensure!(
        code.handlers.is_empty() || code.max_stack >= 1,
        "Exception handler requires one operand stack slot"
    );
    ensure!(
        code.handlers.is_empty()
            || exceptions.is_some_and(|types| types.catches.len() == code.handlers.len()),
        "Missing resolved exception handler types"
    );
    for handler in &code.handlers {
        ensure!(
            handler.start_pc < handler.end_pc
                && indices.contains_key(&usize::from(handler.start_pc))
                && (usize::from(handler.end_pc) == code.bytes.len()
                    || indices.contains_key(&usize::from(handler.end_pc)))
                && indices.contains_key(&usize::from(handler.handler_pc)),
            "Exception range/target is not an instruction boundary"
        );
    }
    let mut initial = Frame {
        locals: vec![None; code.max_locals as usize],
        stack: Vec::new(),
        this_initialized: !constructor,
    };
    let mut slot = 0;
    for (arg, ty) in signature.arguments.iter().enumerate() {
        initial.store(
            slot,
            if constructor && arg == 0 {
                if let Type::LinkedObject(owner) = ty {
                    Type::UninitializedLinkedThis(*owner)
                } else {
                    Type::UninitializedThis
                }
            } else {
                *ty
            },
        )?;
        slot += ty.width();
    }
    let mut frames = BTreeMap::from([(0, initial)]);
    let mut queue = VecDeque::from([0]);
    while let Some(pc) = queue.pop_front() {
        let inst = &instructions[indices[&pc]];
        let before = frames[&pc].clone();
        let mut frame = before.clone();
        let result = (|| -> Result<()> {
            match &inst.op {
                Op::CheckCast(_, ty) => {
                    pop(&mut frame, Type::AnyRef)?;
                    frame.stack.push(*ty);
                }
                Op::InstanceOf(_) => {
                    pop(&mut frame, Type::AnyRef)?;
                    frame.stack.push(Type::I32);
                }
                Op::GetClass => {
                    pop(&mut frame, Type::AnyRef)?;
                    frame.stack.push(Type::BootstrapClass);
                }

                Op::BooleanString(_) => {
                    pop(&mut frame, Type::I32)?;
                    frame.stack.push(Type::BootstrapString);
                }
                Op::Monitor(_) => {
                    pop(&mut frame, Type::AnyRef)?;
                }
                Op::NpeMessage(sig) | Op::ThrowableFill(sig) => {
                    for ty in sig.arguments.iter().rev() {
                        pop(&mut frame, *ty)?;
                    }
                    frame.stack.push(sig.result);
                }
                Op::StreamInit(_) | Op::ClassLoaderRegister(_) | Op::ScopedRegister(_) => (),
                Op::WinFsInit(_, _) => (),
                Op::ConstantClassInitialization(_) => {
                    pop(&mut frame, Type::BootstrapClass)?;
                }
                Op::FileDescriptor(op, _) => {
                    let sig = op.signature();
                    for ty in sig.arguments.iter().rev() {
                        pop(&mut frame, *ty)?;
                    }
                    if sig.result != Type::Void {
                        frame.stack.push(sig.result);
                    }
                }
                Op::Cds(op, _) => {
                    let sig = op.signature();
                    for ty in sig.arguments.iter().rev() {
                        pop(&mut frame, *ty)?;
                    }
                    if sig.result != Type::Void {
                        frame.stack.push(sig.result);
                    }
                }
                Op::SignalFind(_) => {
                    let sig = super::signals::signature();
                    pop(&mut frame, sig.arguments[0])?;
                    frame.stack.push(sig.result);
                }
                Op::UnsafeNative(_, sig, _)
                | Op::AccessContext(_, sig, _)
                | Op::ShutdownNative(_, sig, _) => {
                    for ty in sig.arguments.iter().rev() {
                        pop(&mut frame, *ty)?;
                    }
                    if sig.result != Type::Void {
                        frame.stack.push(sig.result);
                    }
                }
                Op::ThreadNative(op, owner) => {
                    let sig = op.signature(*owner);
                    for ty in sig.arguments.iter().rev() {
                        pop(&mut frame, *ty)?;
                    }
                    if sig.result != Type::Void {
                        frame.stack.push(sig.result);
                    }
                }
                Op::SignalControl(op, _) => {
                    let sig = op.signature();
                    for ty in sig.arguments.iter().rev() {
                        pop(&mut frame, *ty)?;
                    }
                    if sig.result != Type::Void {
                        frame.stack.push(sig.result);
                    }
                }
                Op::WindowsErrorMode(_) => {
                    pop(&mut frame, Type::I64)?;
                    frame.stack.push(Type::I64);
                }
                Op::VmNative(op, _) => {
                    let sig = op.signature();
                    for ty in sig.arguments.iter().rev() {
                        pop(&mut frame, *ty)?;
                    }
                    if sig.result != Type::Void {
                        frame.stack.push(sig.result);
                    }
                }
                Op::VmIntrinsic(op) => {
                    let sig = op.signature();
                    for ty in sig.arguments.iter().rev() {
                        pop(&mut frame, *ty)?;
                    }
                    if sig.result != Type::Void {
                        frame.stack.push(sig.result);
                    }
                }
                Op::RequireNonNull => {
                    let ty = *frame
                        .stack
                        .last()
                        .context("requireNonNull stack underflow")?;
                    ensure!(
                        ty.is_reference(),
                        "requireNonNull requires an initialized reference"
                    );
                }
                Op::Constant(ty, _) => frame.stack.push(*ty),
                Op::StringLiteral(_) => frame.stack.push(Type::BootstrapString),
                Op::ClassLiteral(_) => frame.stack.push(Type::BootstrapClass),
                Op::Load(ty, index) => {
                    if *ty == Type::AnyRef {
                        let Some(Some(Local::Value(actual))) = frame.locals.get(*index) else {
                            bail!("Uninitialized reference local")
                        };
                        ensure!(actual.reference_slot(), "aload requires a reference local");
                        frame.stack.push(*actual);
                    } else {
                        ensure!(
                            frame.locals.get(*index) == Some(&Some(Local::Value(*ty))),
                            "Read of wrong/uninitialized local type"
                        );
                        if ty.width() == 2 {
                            ensure!(
                                frame.locals.get(index + 1) == Some(&Some(Local::Tail)),
                                "Invalid wide local tail"
                            );
                        }
                        frame.stack.push(*ty);
                    }
                }
                Op::Store(ty, index) => {
                    if *ty == Type::AnyRef {
                        let actual = frame.stack.pop().context("astore underflow")?;
                        ensure!(actual.reference_slot(), "astore requires a reference");
                        frame.store(*index, actual)?;
                    } else {
                        pop(&mut frame, *ty)?;
                        frame.store(*index, *ty)?;
                    }
                }
                Op::Pop => {
                    ensure!(
                        frame.stack.pop().context("pop underflow")?.width() == 1,
                        "pop cannot remove a category-2 value"
                    );
                }
                Op::Pop2 => {
                    let top = frame.stack.pop().context("pop2 underflow")?;
                    if top.width() == 1 {
                        ensure!(
                            frame.stack.pop().context("pop2 underflow")?.width() == 1,
                            "Invalid pop2 shape"
                        );
                    }
                }
                Op::Dup => {
                    let top = *frame.stack.last().context("dup underflow")?;
                    ensure!(top.width() == 1, "dup requires category-1 value");
                    frame.stack.push(top);
                }
                Op::Dup2 => {
                    let top = *frame.stack.last().context("dup2 underflow")?;
                    if top.width() == 2 {
                        frame.stack.push(top);
                    } else {
                        ensure!(frame.stack.len() >= 2, "dup2 underflow");
                        let below = frame.stack[frame.stack.len() - 2];
                        ensure!(below.width() == 1, "Invalid dup2 shape");
                        frame.stack.extend([below, top]);
                    }
                }
                Op::Reorder(op) => {
                    let (count, order) = stack_reorder(*op, &frame.stack)?;
                    let tail = frame.stack.split_off(frame.stack.len() - count);
                    frame.stack.extend(order.iter().map(|i| tail[*i]));
                }
                Op::Swap => {
                    ensure!(frame.stack.len() >= 2, "swap underflow");
                    let len = frame.stack.len();
                    ensure!(
                        frame.stack[len - 1].width() == 1 && frame.stack[len - 2].width() == 1,
                        "swap requires category-1 values"
                    );
                    frame.stack.swap(len - 1, len - 2);
                }
                Op::Neg(ty) => {
                    pop(&mut frame, *ty)?;
                    frame.stack.push(*ty);
                }
                Op::Binary(ty, op) => {
                    pop(
                        &mut frame,
                        if matches!(op, Binary::Shl | Binary::Shr | Binary::Ushr) {
                            Type::I32
                        } else {
                            *ty
                        },
                    )?;
                    pop(&mut frame, *ty)?;
                    frame.stack.push(*ty);
                }
                Op::Cast(from, to) => {
                    pop(&mut frame, *from)?;
                    frame.stack.push(*to);
                }
                Op::Narrow(_) => {
                    pop(&mut frame, Type::I32)?;
                    frame.stack.push(Type::I32);
                }
                Op::Compare(ty, _) => {
                    pop(&mut frame, *ty)?;
                    pop(&mut frame, *ty)?;
                    frame.stack.push(Type::I32);
                }
                Op::Increment(index, _) => ensure!(
                    frame.locals.get(*index) == Some(&Some(Local::Value(Type::I32))),
                    "iinc requires initialized int local"
                ),
                Op::If(_, _) | Op::Switch(_, _) => pop(&mut frame, Type::I32)?,
                Op::IfPair(_, _) => {
                    pop(&mut frame, Type::I32)?;
                    pop(&mut frame, Type::I32)?;
                }
                Op::Call(_, sig)
                | Op::ExternalCall(_, sig, _)
                | Op::BridgeCall(_, sig)
                | Op::InstanceCall(_, sig)
                | Op::InterfaceCall(_, sig, _, _)
                | Op::StringIntrinsic(_, sig)
                | Op::StringConcatApi(sig)
                | Op::StringReplace(sig)
                | Op::LiteralRegexReplace(_, _, sig)
                | Op::StringChars(sig)
                | Op::StringGetChars(sig)
                | Op::StringLowercase(sig)
                | Op::StringSplit(sig)
                | Op::ReflectNew(_, sig)
                | Op::ReflectConstructor(_, _, sig)
                | Op::ReflectField(_, sig)
                | Op::ClassForName(sig, _)
                | Op::MonitorNotify(_, sig)
                | Op::RuntimeResource(_, sig)
                | Op::StringPrefix(sig)
                | Op::SystemStream(sig, _, _)
                | Op::ArrayClone(sig, _)
                | Op::IdentityHash(sig, _)
                | Op::HexString(_, sig, _)
                | Op::BuilderSnapshot(sig, _)
                | Op::Bitcast(sig, _)
                | Op::RawProperties(_, sig, _)
                | Op::Concat(_, sig, _)
                | Op::ClassIntrinsic(_, sig)
                | Op::ClassLoaderField(sig)
                | Op::ClassValueField(sig, _)
                | Op::ReflectArray(_, sig, _)
                | Op::StringJoin(_, sig, _, _)
                | Op::PrimitiveClass(sig)
                | Op::ResourceStream(_, sig, _, _)
                | Op::ModuleIntrinsic(_, sig, _) => {
                    for ty in sig.arguments.iter().rev() {
                        pop(&mut frame, *ty)?;
                    }
                    if sig.result != Type::Void {
                        frame.stack.push(sig.result);
                    }
                }
                Op::StaticLoad(field) => frame.stack.push(field.ty),
                Op::StaticStore(field) => pop(&mut frame, field.ty)?,
                Op::NewObject | Op::NewLinkedObject(_) | Op::NewString => {
                    let ty = match inst.op {
                        Op::NewLinkedObject(owner) => Type::UninitializedLinked(pc, owner),
                        Op::NewString => Type::UninitializedString(pc),
                        _ => Type::Uninitialized(pc),
                    };
                    ensure!(
                        !frame.stack.contains(&ty)
                            && !frame.locals.contains(&Some(Local::Value(ty))),
                        "Repeated live uninitialized allocation site"
                    );
                    frame.stack.push(ty);
                }
                Op::InitializeString(sig) => {
                    for ty in sig.arguments.iter().skip(1).rev() {
                        pop(&mut frame, *ty)?;
                    }
                    let receiver = frame
                        .stack
                        .pop()
                        .context("Missing String constructor receiver")?;
                    ensure!(
                        matches!(receiver, Type::UninitializedString(_)),
                        "String constructor requires its exact uninitialized allocation"
                    );
                    frame.initialize(receiver);
                }
                Op::Initialize(_, _) | Op::ProtectedInitialize(_, _, _) => {
                    let (target, sig) = inst.op.constructor().unwrap();
                    for ty in sig.arguments.iter().skip(1).rev() {
                        pop(&mut frame, *ty)?;
                    }
                    let receiver = frame.stack.pop().context("Constructor receiver missing")?;
                    ensure!(
                        matches!(
                            receiver,
                            Type::Uninitialized(_)
                                | Type::UninitializedThis
                                | Type::UninitializedLinked(_, _)
                                | Type::UninitializedLinkedThis(_)
                        ),
                        "Constructor requires an uninitialized object"
                    );
                    if target.is_none() {
                        let valid = match receiver {
                            Type::UninitializedThis => constructor,
                            Type::UninitializedLinkedThis(owner) => {
                                constructor
                                    && links
                                        .map(|l| l.direct_object_parent(owner))
                                        .transpose()?
                                        .unwrap_or(true)
                            }
                            Type::UninitializedLinked(_, owner) => links
                                .map(|l| l.root_object_allocation(owner))
                                .transpose()?
                                .unwrap_or(false),
                            _ => false,
                        };
                        ensure!(
                            valid,
                            "Object constructor requires direct-super this or a verified Object allocation"
                        );
                    }
                    if target.is_some()
                        && let Some(Type::LinkedObject(expected)) = sig.arguments.first()
                    {
                        ensure!(
                            match receiver {
                                Type::UninitializedLinked(_, owner) => owner == *expected,
                                Type::UninitializedLinkedThis(owner) =>
                                    owner == *expected
                                        || links
                                            .map(|links| links.constructor_parent(owner, *expected))
                                            .transpose()?
                                            .unwrap_or(false),
                                _ => false,
                            },
                            "Constructor owner differs from allocation type"
                        );
                    }
                    if let Op::ProtectedInitialize(_, _, current) = inst.op {
                        let actual = match receiver {
                            Type::UninitializedLinked(_, owner)
                            | Type::UninitializedLinkedThis(owner) => Type::LinkedObject(owner),
                            _ => bail!("Protected constructor requires an identified receiver"),
                        };
                        let expected = Type::LinkedObject(current);
                        ensure!(
                            actual == expected
                                || links
                                    .map(|l| l.assignable(actual, expected))
                                    .transpose()?
                                    .unwrap_or(false),
                            "Protected constructor receiver is not assignable to the current class"
                        );
                    }
                    frame.initialize(receiver);
                }
                Op::FieldLoad(_, ty) => {
                    pop(&mut frame, Type::Object)?;
                    frame.stack.push(*ty);
                }
                Op::FieldStore(_, ty) => {
                    pop(&mut frame, *ty)?;
                    pop(&mut frame, Type::Object)?;
                }
                Op::LinkedFieldLoad(field) => {
                    pop(&mut frame, field.receiver)?;
                    frame.stack.push(field.ty);
                }
                Op::LinkedFieldStore(field) => {
                    pop(&mut frame, field.ty)?;
                    if constructor
                        && frame.stack.last() == Some(&Type::UninitializedLinkedThis(field.owner))
                    {
                        frame.stack.pop();
                    } else {
                        pop(&mut frame, field.receiver)?;
                    }
                }
                Op::Throw => {
                    let throwable = exceptions
                        .context("athrow requires resolved Throwable metadata")?
                        .throwable;
                    pop(&mut frame, throwable)?;
                    // A throw discards all remaining operand stack values.
                    frame.stack.clear();
                }
                Op::Return(ty) => {
                    ensure!(
                        frame.this_initialized,
                        "Constructor returned before this was initialized"
                    );
                    ensure!(
                        *ty == signature.result
                            || (*ty == Type::AnyRef && signature.result.is_reference()),
                        "Wrong return instruction type"
                    );
                    if signature.result != Type::Void {
                        pop(&mut frame, signature.result)?;
                    }
                    // JVMS 6.5: a return discards the rest of this frame's stack.
                    // Generated JDK module tables deliberately retain such values.
                    frame.stack.clear();
                }
                Op::Nop | Op::Goto(_) => (),
                Op::NewArray(kind) => {
                    pop(&mut frame, Type::I32)?;
                    frame.stack.push(Type::Array(*kind));
                }
                Op::NewTypedArray(_, ty, dimensions) => {
                    for _ in 0..*dimensions {
                        pop(&mut frame, Type::I32)?;
                    }
                    frame.stack.push(*ty);
                }
                Op::NewReferenceArray
                | Op::NewLinkedReferenceArray(_)
                | Op::NewStringArray
                | Op::NewClassArray => {
                    pop(&mut frame, Type::I32)?;
                    frame.stack.push(if matches!(inst.op, Op::NewClassArray) {
                        Type::BootstrapClassArray
                    } else if matches!(inst.op, Op::NewStringArray) {
                        Type::BootstrapStringArray
                    } else if let Op::NewLinkedReferenceArray(owner) = inst.op {
                        Type::LinkedObjectArray(owner)
                    } else {
                        Type::ObjectArray
                    });
                }
                Op::ReferenceArrayLoad => {
                    pop(&mut frame, Type::I32)?;
                    let array = frame.stack.pop().context("aaload array missing")?;
                    frame.stack.push(match array {
                        Type::ObjectArray => Type::Object,
                        Type::LinkedObjectArray(owner) => Type::LinkedObject(owner),
                        Type::BootstrapStringArray => Type::BootstrapString,
                        Type::BootstrapClassArray => Type::BootstrapClass,
                        Type::Null => Type::Null,
                        _ => links
                            .map(|l| l.array_component(array))
                            .transpose()?
                            .flatten()
                            .context("aaload requires reference array")?,
                    });
                }
                Op::ReferenceArrayStore => {
                    let value = frame.stack.pop().context("aastore value missing")?;
                    pop(&mut frame, Type::I32)?;
                    let array = frame.stack.pop().context("aastore array missing")?;
                    let expected = match array {
                        Type::ObjectArray => Type::Object,
                        Type::LinkedObjectArray(owner) => Type::LinkedObject(owner),
                        Type::BootstrapStringArray => Type::BootstrapString,
                        Type::BootstrapClassArray => Type::BootstrapClass,
                        Type::Null => Type::AnyRef,
                        _ => links
                            .map(|l| l.array_component(array))
                            .transpose()?
                            .flatten()
                            .context("aastore requires reference array")?,
                    };
                    ensure!(
                        value == expected
                            || (value == Type::Null)
                            || (expected == Type::AnyRef && value.is_reference())
                            || (links.is_some_and(|links| links.covariant_arrays())
                                && value.is_reference()),
                        "Reference array component type mismatch"
                    );
                }
                Op::ArrayLength => {
                    frame.pop_array(None, links)?;
                    frame.stack.push(Type::I32);
                }
                Op::ArrayLoad(kind) => {
                    pop(&mut frame, Type::I32)?;
                    frame.pop_array(Some(*kind), links)?;
                    frame.stack.push(kind.value_type());
                }
                Op::ArrayStore(kind) => {
                    pop(&mut frame, kind.value_type())?;
                    pop(&mut frame, Type::I32)?;
                    frame.pop_array(Some(*kind), links)?;
                }
                Op::BootGuard(kind, relation, _, _) => {
                    ensure!(*kind <= 3, "Invalid bootstrap guard operand category");
                    ensure!(
                        *relation < if *kind < 2 { 6 } else { 2 },
                        "Invalid bootstrap guard relation"
                    );
                    let ty = if *kind < 2 { Type::I32 } else { Type::AnyRef };
                    pop(&mut frame, ty)?;
                    if *kind == 1 || *kind == 3 {
                        pop(&mut frame, ty)?;
                    }
                }
                Op::IfNull(_, _) => pop(&mut frame, Type::AnyRef)?,
                Op::IfRefs(_, _) => {
                    pop(&mut frame, Type::AnyRef)?;
                    pop(&mut frame, Type::AnyRef)?;
                }
            }
            ensure!(
                frame.stack.iter().map(|t| t.width()).sum::<usize>() <= code.max_stack as usize,
                "max_stack exceeded"
            );
            Ok(())
        })();
        result.with_context(|| format!("Verification at bytecode {pc}"))?;
        let successors = match &inst.op {
            Op::Return(_) | Op::Throw => Vec::new(),
            Op::Goto(dest) | Op::BootGuard(_, _, _, dest) => vec![*dest],
            Op::If(_, dest) | Op::IfPair(_, dest) | Op::IfNull(_, dest) | Op::IfRefs(_, dest) => {
                vec![*dest, inst.next]
            }
            Op::Switch(default, cases) => std::iter::once(*default)
                .chain(cases.iter().map(|(_, dest)| *dest))
                .collect(),
            _ => vec![inst.next],
        };
        let mut edges: Vec<_> = successors
            .into_iter()
            .map(|dest| (dest, frame.clone(), false))
            .collect();
        for (index, handler) in code.handlers.iter().enumerate() {
            if usize::from(handler.start_pc) <= pc && pc < usize::from(handler.end_pc) {
                let mut caught = before.clone();
                caught.stack = vec![exceptions.unwrap().catches[index]];
                if let Some((_, signature)) = inst.op.constructor() {
                    let receiver_slot = before
                        .stack
                        .len()
                        .checked_sub(signature.arguments.len())
                        .context("Constructor arguments exceed incoming stack")?;
                    let receiver = *before
                        .stack
                        .get(receiver_slot)
                        .context("Constructor signature is missing its receiver")?;
                    for local in &mut caught.locals {
                        if *local == Some(Local::Value(receiver)) {
                            *local = None;
                        }
                    }
                }
                edges.push((usize::from(handler.handler_pc), caught, true));
            }
        }
        for (dest, frame, exceptional) in edges {
            ensure!(
                exceptional
                    || dest > pc
                    || (!frame.stack.iter().any(|t| t.uninitialized())
                        && !frame
                            .locals
                            .iter()
                            .any(|t| matches!(t,Some(Local::Value(ty)) if ty.uninitialized()))),
                "Uninitialized object across a backward edge is unsupported"
            );
            ensure!(indices.contains_key(&dest), "Execution falls off method");
            if let Some(old) = frames.get_mut(&dest) {
                let previous = old.clone();
                // Keep flagThisUninit if any incoming path still has it.
                old.this_initialized &= frame.this_initialized;
                ensure!(
                    old.stack.len() == frame.stack.len(),
                    "Operand stack height mismatch at {dest}"
                );
                for (a, b) in old.stack.iter_mut().zip(&frame.stack) {
                    if *a == Type::Null && b.is_reference() {
                        *a = *b;
                    } else if *a != *b && !(*b == Type::Null && a.is_reference()) {
                        *a = links
                            .map(|links| links.reference_join(*a, *b))
                            .transpose()?
                            .flatten()
                            .context(format!("Operand type mismatch at merge {dest}"))?;
                    }
                }
                for (a, b) in old.locals.iter_mut().zip(&frame.locals) {
                    if a != b {
                        *a = match (*a, *b) {
                            (Some(Local::Value(Type::Null)), Some(Local::Value(other)))
                                if other.is_reference() =>
                            {
                                *b
                            }
                            (Some(Local::Value(other)), Some(Local::Value(Type::Null)))
                                if other.is_reference() =>
                            {
                                *a
                            }
                            (Some(Local::Value(left)), Some(Local::Value(right)))
                                if left.is_reference() && right.is_reference() =>
                            {
                                links
                                    .map(|links| links.reference_join(left, right))
                                    .transpose()?
                                    .flatten()
                                    .map(Local::Value)
                            }
                            _ => None,
                        };
                    }
                }
                old.normalize();
                if *old != previous {
                    queue.push_back(dest);
                }
            } else {
                frames.insert(dest, frame.clone());
                queue.push_back(dest);
            }
        }
    }
    Ok(frames)
}

pub struct Compiled {
    pub assembly: String,
    pub signature: Signature,
    pub instructions: usize,
    pub linked_methods: usize,
    pub requires_heap: bool,
    pub object_layout: Option<ObjectLayout>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ObjectLayout {
    pub abi: u32,
    pub payload_bytes: usize,
    pub reference_prefix_fields: usize,
    pub fields: Vec<FieldLayout>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FieldLayout {
    pub name: String,
    pub descriptor: String,
    pub offset: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub declaring_class: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub declaring_field: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub storage_bytes: Option<usize>,
}

fn stack_reorder(op: u8, stack: &[Type]) -> Result<(usize, Vec<usize>)> {
    let width = |back: usize| -> Result<usize> {
        Ok(stack
            .get(stack.len().checked_sub(back + 1).context("dup underflow")?)
            .context("dup underflow")?
            .width())
    };
    let result = match op {
        0x5a if width(0)? == 1 && width(1)? == 1 => (2, vec![1, 0, 1]),
        0x5b if width(0)? == 1 && width(1)? == 2 => (2, vec![1, 0, 1]),
        0x5b if width(0)? == 1 && width(1)? == 1 && width(2)? == 1 => (3, vec![2, 0, 1, 2]),
        0x5d if width(0)? == 2 && width(1)? == 1 => (2, vec![1, 0, 1]),
        0x5d if width(0)? == 1 && width(1)? == 1 && width(2)? == 1 => (3, vec![1, 2, 0, 1, 2]),
        0x5e if width(0)? == 2 && width(1)? == 2 => (2, vec![1, 0, 1]),
        0x5e if width(0)? == 2 && width(1)? == 1 && width(2)? == 1 => (3, vec![2, 0, 1, 2]),
        0x5e if width(0)? == 1 && width(1)? == 1 && width(2)? == 2 => (3, vec![1, 2, 0, 1, 2]),
        0x5e if width(0)? == 1 && width(1)? == 1 && width(2)? == 1 && width(3)? == 1 => {
            (4, vec![2, 3, 0, 1, 2, 3])
        }
        _ => bail!("Invalid dup category shape"),
    };
    Ok(result)
}

// Code generation follows below; no external compiler or interpreter is used.
fn imm(bits: u64) -> String {
    format!("0{bits:016X}h")
}
fn memory(offset: usize, wide: bool) -> String {
    format!(
        "{} PTR [rsp+{offset}]",
        if wide { "QWORD" } else { "DWORD" }
    )
}
fn jump(condition: u8) -> &'static str {
    ["je", "jne", "jl", "jge", "jg", "jle"][condition as usize]
}

fn emit_cast(
    lines: &mut Vec<String>,
    from: Type,
    to: Type,
    source: usize,
    dest: usize,
    label: &str,
) {
    let mut emit = |text: String| lines.push(format!("    {text}"));
    let load_float = |ty: Type| {
        format!(
            "mov{} xmm0, {}",
            if ty == Type::F32 { "ss" } else { "sd" },
            memory(source, ty == Type::F64)
        )
    };
    match (from, to) {
        (Type::I32, Type::I64) => emit(format!("movsxd rax, {}", memory(source, false))),
        (Type::I64, Type::I32) => emit(format!("mov eax, {}", memory(source, false))),
        (Type::I32 | Type::I64, Type::F32 | Type::F64) => {
            emit(format!(
                "mov {}, {}",
                if from == Type::I64 { "rax" } else { "eax" },
                memory(source, from == Type::I64)
            ));
            emit(format!(
                "cvtsi2{} xmm0, {}",
                if to == Type::F32 { "ss" } else { "sd" },
                if from == Type::I64 { "rax" } else { "eax" }
            ));
            emit(if to == Type::F32 {
                "movd eax, xmm0".into()
            } else {
                "movq rax, xmm0".into()
            });
        }
        (Type::F32, Type::F64) | (Type::F64, Type::F32) => {
            emit(load_float(from));
            emit(if from == Type::F32 {
                "cvtss2sd xmm0, xmm0".into()
            } else {
                "cvtsd2ss xmm0, xmm0".into()
            });
            emit(if to == Type::F32 {
                "movd eax, xmm0".into()
            } else {
                "movq rax, xmm0".into()
            });
        }
        (Type::F32 | Type::F64, Type::I32 | Type::I64) => {
            let suffix = if from == Type::F32 { "ss" } else { "sd" };
            let limits = format!(
                "boom_{}_{}",
                if from == Type::F32 { "f32" } else { "f64" },
                if to == Type::I32 { "i32" } else { "i64" }
            );
            emit(load_float(from));
            emit(format!("ucomi{suffix} xmm0, xmm0"));
            emit(format!("jp {label}_nan"));
            emit(format!(
                "ucomi{suffix} xmm0, {} PTR [{}_hi]",
                if from == Type::F32 { "DWORD" } else { "QWORD" },
                limits
            ));
            emit(format!("jae {label}_high"));
            emit(format!(
                "ucomi{suffix} xmm0, {} PTR [{}_lo]",
                if from == Type::F32 { "DWORD" } else { "QWORD" },
                limits
            ));
            emit(format!("jbe {label}_low"));
            emit(format!(
                "cvtt{suffix}2si {}, xmm0",
                if to == Type::I64 { "rax" } else { "eax" }
            ));
            emit(format!("jmp {label}_cast_done"));
            emit(format!("{label}_nan:"));
            emit("xor eax, eax".into());
            emit(format!("jmp {label}_cast_done"));
            emit(format!("{label}_high:"));
            emit(format!(
                "mov rax, {}",
                imm(if to == Type::I64 {
                    i64::MAX as u64
                } else {
                    i32::MAX as u64
                })
            ));
            emit(format!("jmp {label}_cast_done"));
            emit(format!("{label}_low:"));
            emit(format!(
                "mov rax, {}",
                imm(if to == Type::I64 {
                    i64::MIN as u64
                } else {
                    i32::MIN as u32 as u64
                })
            ));
            emit(format!("{label}_cast_done:"));
        }
        _ => unreachable!("decoder only emits numeric conversions"),
    }
    emit(format!("mov {}, rax", memory(dest, true)));
}

fn emit_function(class: &ClassFile, index: usize) -> Result<(String, usize)> {
    emit_function_with_links(class, index, index, None)
}

pub(super) fn emit_linked_function(
    class: &ClassFile,
    method_index: usize,
    id: usize,
    links: &dyn StaticLinker,
) -> Result<(String, usize)> {
    let body = emit_function_with_links(class, method_index, id, Some(links))?;
    wrap_linked_function(class, method_index, id, links, body)
}
pub(super) fn emit_prepared_linked_function(
    class: &ClassFile,
    method_index: usize,
    id: usize,
    links: &dyn StaticLinker,
    prepared: &PreparedMethod,
) -> Result<(String, usize)> {
    let body = emit_prepared_function(class, method_index, id, Some(links), prepared)?;
    wrap_linked_function(class, method_index, id, links, body)
}
fn wrap_linked_function(
    class: &ClassFile,
    method_index: usize,
    id: usize,
    links: &dyn StaticLinker,
    (body, count): (String, usize),
) -> Result<(String, usize)> {
    let owner = links.class_id(class)?;
    if class.methods[method_index].access & 0x20 != 0 {
        let mirror = links.method_monitor(class, &class.methods[method_index])?;
        return Ok((
            super::monitors::wrapper(
                id,
                owner,
                mirror,
                links.context_bytes() == 32,
                links.normal_class_mirrors(),
            ) + &body,
            count,
        ));
    }
    if class.methods[method_index].access & 8 == 0 {
        return Ok((
            format!("boom_m{id} PROC\n    jmp boom_m{id}_body\nboom_m{id} ENDP\n") + &body,
            count,
        ));
    }
    let failure_source = if links.initializer_source_abi() == 2 {
        // The class state machine already carries the actual initialization
        // error. A use-site wrapper must not replace that method/PC.
        String::new()
    } else {
        format!(
            "    mov r10, QWORD PTR [rsp+48]\n    mov DWORD PTR [r10+4], 0\n    mov DWORD PTR [r10+8], {id}\n"
        )
    };
    let wrapper = format!(
        "boom_m{id} PROC FRAME\n    sub rsp, 72\n    .allocstack 72\n    .endprolog\n    mov QWORD PTR [rsp+48], rcx\n    mov QWORD PTR [rsp+56], rdx\n    lea rcx, boom_class{owner}\n    mov rdx, QWORD PTR [rsp+48]\n    call boom_class_ensure\n    test eax, eax\n    jz boom_m{id}_ready\n{failure_source}    xor eax, eax\n    jmp boom_m{id}_exit\nboom_m{id}_ready:\n    mov rcx, QWORD PTR [rsp+48]\n    mov rdx, QWORD PTR [rsp+56]\n    call boom_m{id}_body\nboom_m{id}_exit:\n    add rsp, 72\n    ret\nboom_m{id} ENDP\n"
    );
    Ok((wrapper + &body, count))
}

fn emit_function_with_links(
    class: &ClassFile,
    method_index: usize,
    index: usize,
    links: Option<&dyn StaticLinker>,
) -> Result<(String, usize)> {
    let method = &class.methods[method_index];
    let signature = if let Some(links) = links {
        links.signature(class, method)?
    } else {
        method_signature(class, method)?
    };
    ensure!(
        method.access & (0x100 | 0x400) == 0,
        "Requires non-native concrete Java methods"
    );
    if method.access & 0x20 != 0 {
        links
            .context("Synchronized methods require program metadata and monitors")?
            .method_monitor(class, method)?;
    }
    let code = method.code.as_ref().context("Missing Java Code")?;
    let context32 = links.is_some_and(|l| l.context_bytes() == 32);
    ensure!(
        context32 || code.handlers.is_empty(),
        "Catch handlers require integrated Context32 Throwable materialization and code generation; Context16 cannot execute them"
    );
    let instructions = decode_with_links(code, class, links)?;
    ensure!(
        context32 || !instructions.iter().any(|inst| matches!(inst.op, Op::Throw)),
        "athrow needs the Context32 Throwable materialization and handler backend; Context16 cannot execute it"
    );
    let exceptions = exception_types(class, code, &instructions, links)?;
    let frames = verify_method_with_links(
        &instructions,
        code,
        &signature,
        method.name == "<init>"
            && !links
                .map(|l| l.root_object_constructor(class))
                .transpose()?
                .unwrap_or(false),
        links,
        exceptions.as_ref(),
    )?;
    let prepared = PreparedMethod {
        signature,
        instructions,
        frames,
    };
    emit_prepared_function(class, method_index, index, links, &prepared)
}

pub(super) struct PreparedMethod {
    signature: Signature,
    instructions: Vec<Instruction>,
    frames: BTreeMap<usize, Frame>,
}
#[derive(Serialize)]
pub struct ReferenceMap {
    pub pc: usize,
    pub local_slots: Vec<usize>,
    pub operand_values: Vec<usize>,
}
impl PreparedMethod {
    pub(super) fn reference_maps(&self) -> Vec<ReferenceMap> {
        self.frames
            .iter()
            .map(|(pc, frame)| ReferenceMap {
                pc: *pc,
                local_slots: frame
                    .locals
                    .iter()
                    .enumerate()
                    .filter_map(|(index, local)| {
                        matches!(local,Some(Local::Value(ty)) if ty.reference_slot())
                            .then_some(index)
                    })
                    .collect(),
                operand_values: frame
                    .stack
                    .iter()
                    .enumerate()
                    .filter_map(|(index, ty)| ty.reference_slot().then_some(index))
                    .collect(),
            })
            .collect()
    }
    pub(super) fn instruction_count(&self) -> usize {
        self.instructions.len()
    }
}

/// Resolve portable IR operands into the same typed operations used by MASM
/// generation. Runtime/native bindings may stay external, never become stubs.
pub(super) fn prepare_symbolic_method(
    class: &ClassFile,
    method_index: usize,
    unit: &super::translation_ir::Class,
    links: &dyn StaticLinker,
) -> Result<PreparedMethod> {
    use super::symbolic::{Constant as C, Operand as O};
    let source = class
        .methods
        .get(method_index)
        .context("Invalid source method index")?;
    let method = unit
        .methods
        .get(method_index)
        .context("Missing symbolic method")?;
    ensure!(
        source.name == method.name
            && source.descriptor == method.descriptor
            && source.access == method.access,
        "IR declaration differs from source"
    );
    ensure!(
        source.access & (0x100 | 0x400) == 0,
        "Native/abstract declarations have no Java body"
    );
    let body = method.body.as_ref().context("Missing symbolic Java body")?;
    let code = source.code.as_ref().context("Missing original Java Code")?;
    ensure!(
        body.max_stack == code.max_stack
            && body.max_locals == code.max_locals
            && super::symbolic::decode_stream(&code.bytes)? == body.instructions,
        "IR instructions differ from original Code"
    );
    let signature = links.signature(class, source)?;
    let mut instructions = Vec::with_capacity(body.instructions.len());
    for raw in &body.instructions {
        let op = raw.effective_opcode();
        let local = || -> Result<usize> {
            match raw.operand {
                O::Local(index) => Ok(usize::from(index)),
                _ => bail!("Missing local operand"),
            }
        };
        let branch = || -> Result<usize> {
            match raw.operand {
                O::Branch(pc) => Ok(usize::from(pc)),
                _ => bail!("Missing branch operand"),
            }
        };
        let reference = || -> Result<Op> {
            let index = raw.constant().context("Missing constant operand")?;
            let value = unit
                .constants
                .get(&index)
                .context("Missing symbolic constant")?;
            if matches!(op, 0x12..=0x14) {
                let number = match value {
                    C::Int(v) => Some((Type::I32, *v as u32 as u64)),
                    C::Long(v) => Some((Type::I64, *v as u64)),
                    C::FloatBits(v) => Some((Type::F32, u64::from(*v))),
                    C::DoubleBits(v) => Some((Type::F64, *v)),
                    _ => None,
                };
                if let Some((ty, bits)) = number {
                    return Ok(Op::Constant(ty, bits));
                }
            }
            Ok(match links.symbolic_reference(value, index, op)? {
                SymbolicReference::ExternalCall(label, sig, receiver) => {
                    Op::ExternalCall(label, sig, receiver)
                }
                SymbolicReference::DirectCall {
                    method,
                    signature,
                    is_static,
                    constructor,
                    protected_receiver,
                } => {
                    if constructor {
                        if let Some(current) = protected_receiver {
                            Op::ProtectedInitialize(method, signature, current)
                        } else {
                            Op::Initialize(Some(method), signature)
                        }
                    } else if is_static {
                        Op::Call(method, signature)
                    } else {
                        Op::BridgeCall(method, signature)
                    }
                }
                SymbolicReference::StaticField(field) => {
                    if op == 0xb2 {
                        Op::StaticLoad(field)
                    } else {
                        Op::StaticStore(field)
                    }
                }
                SymbolicReference::InstanceField(field) => {
                    if op == 0xb4 {
                        Op::LinkedFieldLoad(field)
                    } else {
                        Op::LinkedFieldStore(field)
                    }
                }
            })
        };
        let operation = match op {
            0x00 => Op::Nop,
            0x01 => Op::Constant(Type::Null, 0),
            0x02..=0x08 => Op::Constant(Type::I32, (i32::from(op) - 3) as u32 as u64),
            0x09..=0x0a => Op::Constant(Type::I64, u64::from(op - 9)),
            0x0b..=0x0d => Op::Constant(Type::F32, u64::from(f32::from(op - 0x0b).to_bits())),
            0x0e..=0x0f => Op::Constant(Type::F64, f64::from(op - 0x0e).to_bits()),
            0x10 | 0x11 => {
                let O::Immediate(value) = raw.operand else {
                    bail!("Missing signed immediate")
                };
                Op::Constant(Type::I32, value as u32 as u64)
            }
            0x12..=0x14 | 0xb2..=0xba => reference()?,
            0x15..=0x18 => Op::Load(Type::from_opcode(op - 0x15), local()?),
            0x19 | 0x2a..=0x2d => Op::Load(Type::AnyRef, local()?),
            0x1a..=0x29 => Op::Load(Type::from_opcode((op - 0x1a) / 4), local()?),
            0x2e..=0x31 => Op::ArrayLoad(
                [
                    ArrayKind::Int,
                    ArrayKind::Long,
                    ArrayKind::Float,
                    ArrayKind::Double,
                ][usize::from(op - 0x2e)],
            ),
            0x32 => Op::ReferenceArrayLoad,
            0x33..=0x35 => Op::ArrayLoad(
                [ArrayKind::Byte, ArrayKind::Char, ArrayKind::Short][usize::from(op - 0x33)],
            ),
            0x36..=0x39 => Op::Store(Type::from_opcode(op - 0x36), local()?),
            0x3a | 0x4b..=0x4e => Op::Store(Type::AnyRef, local()?),
            0x3b..=0x4a => Op::Store(Type::from_opcode((op - 0x3b) / 4), local()?),
            0x4f..=0x52 => Op::ArrayStore(
                [
                    ArrayKind::Int,
                    ArrayKind::Long,
                    ArrayKind::Float,
                    ArrayKind::Double,
                ][usize::from(op - 0x4f)],
            ),
            0x53 => Op::ReferenceArrayStore,
            0x54..=0x56 => Op::ArrayStore(
                [ArrayKind::Byte, ArrayKind::Char, ArrayKind::Short][usize::from(op - 0x54)],
            ),
            0x57 => Op::Pop,
            0x58 => Op::Pop2,
            0x59 => Op::Dup,
            0x5c => Op::Dup2,
            0x5f => Op::Swap,
            0x5a | 0x5b | 0x5d | 0x5e => Op::Reorder(op),
            0x60..=0x73 => Op::Binary(
                Type::from_opcode((op - 0x60) % 4),
                [
                    Binary::Add,
                    Binary::Sub,
                    Binary::Mul,
                    Binary::Div,
                    Binary::Rem,
                ][usize::from((op - 0x60) / 4)],
            ),
            0x74..=0x77 => Op::Neg(Type::from_opcode(op - 0x74)),
            0x78..=0x83 => Op::Binary(
                if op % 2 == 0 { Type::I32 } else { Type::I64 },
                [
                    Binary::Shl,
                    Binary::Shr,
                    Binary::Ushr,
                    Binary::And,
                    Binary::Or,
                    Binary::Xor,
                ][usize::from((op - 0x78) / 2)],
            ),
            0x84 => {
                let O::Increment { local, amount } = raw.operand else {
                    bail!("Missing iinc operand")
                };
                Op::Increment(usize::from(local), i32::from(amount))
            }
            0x85..=0x90 => {
                let (a, b) = [
                    (Type::I32, Type::I64),
                    (Type::I32, Type::F32),
                    (Type::I32, Type::F64),
                    (Type::I64, Type::I32),
                    (Type::I64, Type::F32),
                    (Type::I64, Type::F64),
                    (Type::F32, Type::I32),
                    (Type::F32, Type::I64),
                    (Type::F32, Type::F64),
                    (Type::F64, Type::I32),
                    (Type::F64, Type::I64),
                    (Type::F64, Type::F32),
                ][usize::from(op - 0x85)];
                Op::Cast(a, b)
            }
            0x91..=0x93 => Op::Narrow(op),
            0x94 => Op::Compare(Type::I64, 0),
            0x95..=0x98 => Op::Compare(
                if op < 0x97 { Type::F32 } else { Type::F64 },
                if op % 2 == 1 { -1 } else { 1 },
            ),
            0x99..=0x9e => Op::If(op - 0x99, branch()?),
            0x9f..=0xa4 => Op::IfPair(op - 0x9f, branch()?),
            0xa5 | 0xa6 => Op::IfRefs(op == 0xa6, branch()?),
            0xa7 | 0xc8 => Op::Goto(branch()?),
            0xaa | 0xab => {
                let O::Switch { default, cases } = &raw.operand else {
                    bail!("Missing switch operands")
                };
                Op::Switch(
                    usize::from(*default),
                    cases.iter().map(|(k, t)| (*k, usize::from(*t))).collect(),
                )
            }
            0xac..=0xaf => Op::Return(Type::from_opcode(op - 0xac)),
            0xb0 => Op::Return(Type::AnyRef),
            0xb1 => Op::Return(Type::Void),
            0xbb => {
                let C::Class(name) = &unit.constants[&raw.constant().unwrap()] else {
                    bail!("Missing allocation class")
                };
                Op::NewLinkedObject(links.allocate_class(class, name)?)
            }
            0xbc => {
                let O::PrimitiveArray(atype) = raw.operand else {
                    bail!("Missing atype")
                };
                Op::NewArray(ArrayKind::from_atype(atype)?)
            }
            0xbd | 0xc5 => {
                let C::Class(name) = &unit.constants[&raw.constant().unwrap()] else {
                    bail!("Missing array component")
                };
                let (descriptor, dimensions) = if op == 0xc5 {
                    let O::MultiArray { dimensions, .. } = raw.operand else {
                        bail!("Missing dimensions")
                    };
                    (name.clone(), dimensions)
                } else {
                    (
                        if name.starts_with('[') {
                            format!("[{name}")
                        } else {
                            format!("[L{name};")
                        },
                        1,
                    )
                };
                let (id, ty) = links.typed_array(class, &descriptor, dimensions)?;
                Op::NewTypedArray(id, ty, dimensions)
            }
            0xbe => Op::ArrayLength,
            0xbf => Op::Throw,
            0xc0 | 0xc1 => {
                let C::Class(name) = &unit.constants[&raw.constant().unwrap()] else {
                    bail!("Missing cast target")
                };
                let (id, ty) = links.type_target(class, name)?;
                if op == 0xc0 {
                    Op::CheckCast(id, ty)
                } else {
                    Op::InstanceOf(id)
                }
            }
            0xc2 | 0xc3 => Op::Monitor(op == 0xc2),
            0xc6 | 0xc7 => Op::IfNull(op == 0xc7, branch()?),
            _ => bail!("Symbolic opcode 0x{op:02x} requires further lowering"),
        };
        instructions.push(Instruction {
            pc: usize::from(raw.pc),
            next: usize::from(raw.next),
            op: operation,
        });
    }
    let exceptions = exception_types(class, code, &instructions, Some(links))?;
    let frames = verify_method_with_links(
        &instructions,
        code,
        &signature,
        source.name == "<init>" && !links.root_object_constructor(class)?,
        Some(links),
        exceptions.as_ref(),
    )?;
    Ok(PreparedMethod {
        signature,
        instructions,
        frames,
    })
}
fn emit_prepared_function(
    class: &ClassFile,
    method_index: usize,
    index: usize,
    links: Option<&dyn StaticLinker>,
    prepared: &PreparedMethod,
) -> Result<(String, usize)> {
    let method = &class.methods[method_index];
    let code = method
        .code
        .as_ref()
        .context("Missing original method Code")?;
    let context32 = links.is_some_and(|l| l.context_bytes() == 32);
    let signature = &prepared.signature;
    let instructions = &prepared.instructions;
    let frames = &prepared.frames;
    let symbol = if links.is_some() {
        format!("boom_m{index}_body")
    } else {
        format!("boom_m{index}")
    };
    let args_base = 64;
    // An invocation consumes at most max_stack JVM slots. Keep the existing
    // minimum for runtime adapters while allowing ordinary high-arity calls.
    let local_base = args_base + usize::from(code.max_stack).max(16) * 8;
    let stack_base = local_base + code.max_locals as usize * 8;
    let traced = links.is_some_and(|l| l.runtime_frames());
    let trace_base = stack_base + code.max_stack as usize * 8;
    let bytes = (trace_base + if traced { 64 } else { 0 } + 8).div_ceil(16) * 16 - 8;
    ensure!(
        bytes < 4096 || links.is_some_and(|l| l.runtime_stack_probe()),
        "Frame needs stack probing before it can be supported"
    );
    let local = |i: usize| memory(local_base + i * 8, true);
    let stack = |i: usize| memory(stack_base + i * 8, true);
    let mut lines = vec![
        asm_comment(&format!(
            "class={} method={}{}",
            class.name, method.name, method.descriptor
        )),
        format!("{symbol} PROC FRAME"),
        format!("    sub rsp, {bytes}"),
        format!("    .allocstack {bytes}"),
        "    .endprolog".into(),
        "    mov QWORD PTR [rsp+48], rcx".into(),
    ];
    if bytes >= 4096 {
        lines.splice(
            2..2,
            [
                format!("    mov eax, {bytes}"),
                "    call boom_stack_probe".into(),
            ],
        );
    }
    if context32 && !code.handlers.is_empty() {
        let links = links.unwrap();
        let (throwable, _) = links.type_target(class, "java/lang/Throwable")?;
        let mut table = format!(
            ".const\nALIGN 8\nboom_handlers{index} DWORD 045584348h, 1, {}, 0\n    QWORD OFFSET boom_handler_rows{index}, OFFSET boom_runtime_type_map, OFFSET boom_t{throwable}\nboom_handler_rows{index} LABEL BYTE\n",
            code.handlers.len()
        );
        for h in &code.handlers {
            let ty = if let Some(name) = &h.catch_type {
                format!("OFFSET boom_t{}", links.type_target(class, name)?.0)
            } else {
                "0".into()
            };
            table.push_str(&format!(
                "    DWORD {}, {}, {}, 0\n    QWORD {ty}\n",
                h.start_pc, h.end_pc, h.handler_pc
            ));
        }
        table.push_str(".code\n");
        lines.insert(0, table);
    }
    if traced {
        lines.push(format!("    mov QWORD PTR [rsp+{trace_base}], 0"));
        lines.push(format!("    mov QWORD PTR [rsp+{}], rdx", trace_base + 56));
    }
    lines.extend([
        "    cmp DWORD PTR [rcx+12], 128".into(),
        format!("    jae {symbol}_stack_limit"),
        "    inc DWORD PTR [rcx+12]".into(),
    ]);
    if traced {
        lines.extend([
            "    lea rcx, boom_trace_pool".into(),
            format!("    lea rdx, [rsp+{trace_base}]"),
            format!("    lea r8, boom_trace_method{index}"),
            "    mov r9, QWORD PTR [rsp+48]".into(),
            "    call boom_trace_enter".into(),
            "    test eax, eax".into(),
            format!("    jz {symbol}_trace_ready"),
            "    mov r10, QWORD PTR [rsp+48]".into(),
            "    mov DWORD PTR [r10+4], 0".into(),
            format!("    mov DWORD PTR [r10+8], {index}"),
            format!("    jmp {symbol}_throw"),
            format!("{symbol}_trace_ready:"),
            format!("    mov rdx, QWORD PTR [rsp+{}]", trace_base + 56),
        ]);
    }
    let mut slot = 0;
    for (arg, ty) in signature.arguments.iter().enumerate() {
        lines.push(format!(
            "    mov {}, {} PTR [rdx+{}]",
            if ty.bits64() { "rax" } else { "eax" },
            if ty.bits64() { "QWORD" } else { "DWORD" },
            arg * 8
        ));
        lines.push(format!("    mov {}, rax", local(slot)));
        slot += ty.width();
    }
    for inst in instructions {
        let Some(frame) = frames.get(&inst.pc) else {
            continue;
        };
        let depth = frame.stack.len();
        let label = format!("{symbol}_P{}", inst.pc);
        lines.push(format!("{symbol}_L{}:", inst.pc));
        if traced {
            lines.push(format!(
                "    mov DWORD PTR [rsp+{}], {}",
                trace_base + 24,
                inst.pc
            ));
        }
        // MASM enforces its line limit even for comments; large switches and
        // dispatch target sets must not make otherwise valid code unassemblable.
        let detail = match &inst.op {
            Op::Concat(plan, signature, None) => format!("Concat({plan}, {signature:?})"),
            op => format!("{op:?}"),
        };
        let preview: String = detail.chars().take(96).collect();
        lines.push(format!(
            "    ; bytecode {} {}{}",
            inst.pc,
            preview,
            if detail.chars().count() > 96 {
                " ..."
            } else {
                ""
            }
        ));
        if let Op::Cast(from, to) = inst.op {
            emit_cast(
                &mut lines,
                from,
                to,
                stack_base + (depth - 1) * 8,
                stack_base + (depth - 1) * 8,
                &label,
            );
            continue;
        }
        let mut emit = |text: String| lines.push(format!("    {text}"));
        match &inst.op {
            Op::Nop => (),
            Op::RequireNonNull => {
                emit(format!("cmp {}, 0", stack(depth - 1)));
                emit(format!("jne {label}_nonnull"));
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("mov DWORD PTR [r10], 4".into());
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_nonnull:"));
            }
            Op::Monitor(enter) | Op::MonitorNotify(enter, _) => {
                emit("mov rcx, QWORD PTR [boom_heap_ptr]".into());
                emit(format!("mov rdx, {}", stack(depth - 1)));
                emit("mov r8, QWORD PTR [rsp+48]".into());
                emit(format!(
                    "call boom_monitor_{}",
                    if matches!(inst.op, Op::MonitorNotify(_, _)) {
                        if *enter { "notify_all" } else { "notify" }
                    } else if *enter {
                        "enter"
                    } else {
                        "exit"
                    }
                ));
                emit("test eax, eax".into());
                emit(format!("jz {label}_monitor_ok"));
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_monitor_ok:"));
            }
            Op::NpeMessage(sig) => {
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("mov rdx, {}", stack(depth - 1)));
                emit("lea r8, boom_exception_vm".into());
                emit("call boom_exception_npe_message".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_npe_message_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_npe_message_ok:"));
                emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
            }
            Op::ThrowableFill(sig) => {
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("lea r8, boom_throwable_plan".into());
                emit("call boom_throwable_fill".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_trace_filled"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_trace_filled:"));
                emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
            }
            Op::StreamInit(owner) => {
                emit(format!("lea rcx, boom_class{owner}"));
                emit("mov rdx, QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax, eax".into());
                emit(format!("jnz {symbol}_throw"));
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, boom_stream_pool{owner}"));
                emit("call boom_stream_fields_init".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_stream_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_stream_ok:"));
            }
            Op::ConstantClassInitialization(owner) => {
                emit(format!("lea rcx, boom_class{owner}"));
                emit("mov rdx, QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax, eax".into());
                // Preserve the actual initializer's error source and failed state.
                emit(format!("jnz {symbol}_throw"));
            }
            Op::FileDescriptor(operation, owner) => {
                emit(format!("lea rcx, boom_class{owner}"));
                emit("mov rdx, QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax, eax".into());
                emit(format!("jnz {symbol}_throw"));
                let sig = operation.signature();
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("lea r8, boom_fd_pool".into());
                emit(format!("mov r9d, {}", *operation as u32));
                emit("call boom_fd_service".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_fd_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_fd_ok:"));
                if sig.result != Type::Void {
                    emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
                }
            }
            Op::Cds(operation, owner) => {
                emit(format!("lea rcx, boom_class{owner}"));
                emit("mov rdx, QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax, eax".into());
                emit(format!("jnz {symbol}_throw"));
                let sig = operation.signature();
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("lea r8, boom_cds_profile".into());
                emit(format!("mov r9d, {}", operation.code()));
                emit("call boom_cds_service".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_cds_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_cds_ok:"));
                if sig.result != Type::Void {
                    emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
                }
            }
            Op::SystemStream(sig, operation, owner) => {
                emit(format!("lea rcx, boom_class{owner}"));
                emit("mov rdx, QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax,eax".into());
                emit(format!("jnz {symbol}_throw"));
                emit(format!("mov rax, {}", stack(depth - sig.arguments.len())));
                emit(format!("mov {},rax", memory(args_base, true)));
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("lea r8,boom_system_stream_pool".into());
                emit(format!("mov r9d,{}", *operation as u32));
                emit("call boom_system_stream_set".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_stream_set_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_stream_set_ok:"));
            }
            Op::AccessContext(op, sig, owner) => {
                emit(format!("lea rcx,boom_class{owner}"));
                emit("mov rdx,QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax,eax".into());
                emit(format!("jnz {symbol}_throw"));
                let base = depth - sig.arguments.len();
                for arg in 0..sig.arguments.len() {
                    emit(format!("mov rax,{}", stack(base + arg)));
                    emit(format!("mov QWORD PTR [rsp+{}],rax", args_base + arg * 8));
                }
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("lea r8,boom_access_pool".into());
                emit(format!("mov r9d,{}", *op as u32));
                emit("call boom_access_context_query".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_access_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_access_ok:"));
                if sig.result != Type::Void {
                    emit(format!("mov {},rax", stack(base)));
                }
            }
            Op::ShutdownNative(op, sig, owner) => {
                emit(format!("lea rcx,boom_class{owner}"));
                emit("mov rdx,QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax,eax".into());
                emit(format!("jnz {symbol}_throw"));
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax,{}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov QWORD PTR [rsp+{}],rax", args_base + arg * 8));
                }
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("lea r8,boom_shutdown_pool".into());
                emit(format!("mov r9d,{}", *op as u32));
                emit("call boom_shutdown_native".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_shutdown_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_shutdown_ok:"));
            }
            Op::UnsafeNative(op, sig, _) => {
                let base = depth - sig.arguments.len();
                for arg in 0..sig.arguments.len() {
                    emit(format!("mov rax,{}", stack(base + arg)));
                    emit(format!("mov QWORD PTR [rsp+{}],rax", args_base + arg * 8));
                }
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("lea r8,boom_unsafe_pool".into());
                emit(format!("mov r9d,{}", *op as u32));
                emit("call boom_unsafe_native".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_unsafe_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_unsafe_ok:"));
                if sig.result != Type::Void {
                    emit(format!("mov {},rax", stack(base)));
                }
            }
            Op::ThreadNative(op, owner) => {
                let sig = op.signature(*owner);
                let base = depth - sig.arguments.len();
                if *op != super::thread_natives::Operation::Register {
                    emit(format!("lea rcx,boom_class{owner}"));
                    emit("mov rdx,QWORD PTR [rsp+48]".into());
                    emit("call boom_class_ensure".into());
                    emit("test eax,eax".into());
                    emit(format!("jnz {symbol}_throw"));
                }
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                if *op == super::thread_natives::Operation::Register {
                    emit("lea rdx,boom_thread_native_pool".into());
                    emit("call boom_thread_native_register".into());
                } else {
                    for arg in 0..sig.arguments.len() {
                        emit(format!("mov rax,{}", stack(base + arg)));
                        emit(format!("mov QWORD PTR [rsp+{}],rax", args_base + arg * 8));
                    }
                    emit(format!("lea rdx,[rsp+{args_base}]"));
                    emit("lea r8,boom_thread_native_pool".into());
                    emit(format!("mov r9d,{}", op.index()));
                    emit("call boom_thread_native_dispatch".into());
                }
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_thread_native_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_thread_native_ok:"));
                if sig.result != Type::Void {
                    emit(format!("mov {},rax", stack(base)));
                }
            }
            Op::SignalFind(owner) => {
                emit(format!("lea rcx,boom_class{owner}"));
                emit("mov rdx,QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax,eax".into());
                emit(format!("jnz {symbol}_throw"));
                emit(format!("mov rax,{}", stack(depth - 1)));
                emit(format!("mov {},rax", memory(args_base, true)));
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("lea r8,boom_string_pool".into());
                emit("call boom_signal_find".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_signal_find_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_signal_find_ok:"));
                emit(format!("mov {},rax", stack(depth - 1)));
            }
            Op::VmNative(operation, owner) => {
                let sig = operation.signature();
                emit(format!("lea rcx, boom_class{owner}"));
                emit("mov rdx, QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax, eax".into());
                emit(format!("jnz {symbol}_throw"));
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                if *operation == super::vm_registration::Operation::BootUnnamedModule {
                    emit("lea r8,boom_boot_unnamed_pool".into());
                    emit("call boom_boot_unnamed_publish".into());
                } else if *operation == super::vm_registration::Operation::FinalizationEnabled {
                    emit("call boom_finalization_enabled".into());
                } else if matches!(
                    operation,
                    super::vm_registration::Operation::InetAddressInit
                        | super::vm_registration::Operation::Inet4Init
                        | super::vm_registration::Operation::Inet6Init
                ) {
                    let pool = match operation {
                        super::vm_registration::Operation::Inet4Init => "boom_inet4_cache",
                        super::vm_registration::Operation::Inet6Init => "boom_inet6_cache",
                        _ => "boom_inet_cache",
                    };
                    emit(format!("lea r8,{pool}"));
                    emit("call boom_inet_address_init".into());
                } else if operation.is_inet() {
                    emit("lea r8,boom_inet_availability".into());
                    emit(format!(
                        "mov r9d,{}",
                        u32::from(*operation == super::vm_registration::Operation::InetAddressIPv6)
                    ));
                    emit("call boom_inet_address_available".into());
                } else {
                    emit("lea r8, boom_vm_native_pool".into());
                    emit(format!("mov r9d, {}", *operation as u32));
                    emit("call boom_vm_native".into());
                }
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_vm_native_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_vm_native_ok:"));
                if sig.result != Type::Void {
                    emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
                }
            }
            Op::ReflectArray(op, _, owner) => {
                emit(format!("lea rcx,boom_class{owner}"));
                emit("mov rdx,QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax,eax".into());
                emit(format!("jnz {symbol}_throw"));
                for arg in 0..2 {
                    emit(format!("mov rax,{}", stack(depth - 2 + arg)));
                    emit(format!("mov QWORD PTR [rsp+{}],rax", args_base + arg * 8));
                }
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("lea r8,boom_reflect_array_pool".into());
                emit(format!("mov r9d,{}", *op as u32));
                emit("call boom_reflect_array_allocate".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_reflect_array_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_reflect_array_ok:"));
                emit(format!("mov {},rax", stack(depth - 2)));
            }
            Op::WinFsInit(owner, file) => {
                for class in [owner, file] {
                    emit(format!("lea rcx,boom_class{class}"));
                    emit("mov rdx,QWORD PTR [rsp+48]".into());
                    emit("call boom_class_ensure".into());
                    emit("test eax,eax".into());
                    emit(format!("jnz {symbol}_throw"));
                }
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit("lea rdx,boom_winfs_pool".into());
                emit("call boom_winfs_init".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_winfs_init_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_winfs_init_ok:"));
            }
            Op::ScopedRegister(owner) => {
                emit(format!("lea rcx,boom_class{owner}"));
                emit("mov rdx,QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax,eax".into());
                emit(format!("jnz {symbol}_throw"));
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit("lea rdx,boom_scoped_native_pool".into());
                emit("call boom_scoped_native_register".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_scoped_registration_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_scoped_registration_ok:"));
            }
            Op::ClassLoaderRegister(owner) => {
                emit(format!("lea rcx,boom_class{owner}"));
                emit("mov rdx,QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax,eax".into());
                emit(format!("jnz {symbol}_throw"));
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit("lea rdx,boom_loader_native_pool".into());
                emit("call boom_class_loader_register".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_loader_registration_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_loader_registration_ok:"));
            }
            Op::WindowsErrorMode(owner) => {
                emit(format!("lea rcx,boom_class{owner}"));
                emit("mov rdx,QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax,eax".into());
                emit(format!("jnz {symbol}_throw"));
                emit(format!("mov rax,{}", stack(depth - 1)));
                emit(format!("mov QWORD PTR [rsp+{args_base}],rax"));
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("call boom_windows_error_mode".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_windows_mode_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_windows_mode_ok:"));
                emit(format!("mov {},rax", stack(depth - 1)));
            }
            Op::SignalControl(op, owner) => {
                let sig = op.signature();
                emit(format!("lea rcx,boom_class{owner}"));
                emit("mov rdx,QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax,eax".into());
                emit(format!("jnz {symbol}_throw"));
                let base = depth - sig.arguments.len();
                for arg in 0..sig.arguments.len() {
                    emit(format!("mov rax,{}", stack(base + arg)));
                    emit(format!("mov QWORD PTR [rsp+{}],rax", args_base + arg * 8));
                }
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("lea r8,boom_signal_native_pool".into());
                emit(format!("mov r9d,{}", *op as u32));
                emit("call boom_signal_native_query".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_signal_control_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_signal_control_ok:"));
                if sig.result != Type::Void {
                    emit(format!("mov {},rax", stack(base)));
                }
            }
            Op::VmIntrinsic(operation) => {
                let sig = operation.signature();
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                let registered = links.is_some_and(|l| l.system_registration());
                if *operation == super::vm::Operation::RegisterNatives || registered {
                    emit("lea r8, boom_system_native_pool".into());
                } else if *operation == super::vm::Operation::ArrayCopy {
                    emit("lea r8, boom_runtime_type_map".into());
                }
                if registered && let Some(slot) = operation.native_index() {
                    emit(format!("mov r9d, {slot}"));
                    emit("call boom_system_dispatch".into());
                } else {
                    emit(format!("call {}", operation.symbol()));
                }
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_vm_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_vm_ok:"));
                if sig.result != Type::Void {
                    emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
                }
            }
            Op::BooleanString(literals) => {
                emit(format!("mov rax, {}", stack(depth - 1)));
                emit("test eax, eax".into());
                emit(format!("mov r8d, {}", literals[0]));
                emit(format!("je {label}_boolean_value"));
                emit(format!("mov r8d, {}", literals[1]));
                emit(format!("{label}_boolean_value:"));
                emit("mov rcx, QWORD PTR [boom_heap_ptr]".into());
                emit("lea rdx, boom_string_pool".into());
                emit("mov r9, QWORD PTR [rsp+48]".into());
                emit("call boom_string_load".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_boolean_value_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_boolean_value_ok:"));
                emit(format!("mov {}, rax", stack(depth - 1)));
            }
            Op::StringJoin(plan, sig, _, _) => {
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("mov r8, QWORD PTR [boom_heap_ptr]".into());
                emit(format!("lea r9, boom_string_join_plan{plan}"));
                emit("call boom_string_join".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_join_ok"));
                emit("test edx, edx".into());
                emit(format!("jnz {symbol}_throw"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_join_ok:"));
                emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
            }
            Op::ResourceStream(caller, _, owner, constructor) => {
                for arg in 0..2 {
                    emit(format!("mov rax, {}", stack(depth - 2 + arg)));
                    emit(format!("mov QWORD PTR [rsp+{}], rax", args_base + arg * 8));
                }
                emit(format!("mov QWORD PTR [rsp+{}], {caller}", args_base + 16));
                emit("mov rcx, QWORD PTR [boom_heap_ptr]".into());
                emit("lea rdx, boom_resource_pool".into());
                emit(format!("lea r8, [rsp+{args_base}]"));
                emit("mov r9, QWORD PTR [rsp+48]".into());
                emit("call boom_resource_bytes".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("jne {label}_resource_error"));
                emit("test rax, rax".into());
                emit(format!("jz {label}_resource_done"));
                emit(format!("mov QWORD PTR [rsp+{}], rax", args_base + 8));
                emit(format!("lea rcx, boom_class{owner}"));
                emit("mov rdx, QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax, eax".into());
                emit(format!("jnz {label}_resource_error"));
                emit("mov rcx, QWORD PTR [boom_heap_ptr]".into());
                emit(format!("lea rdx, boom_layout{owner}"));
                emit("mov r8, QWORD PTR [rsp+48]".into());
                emit("call boom_object_new".into());
                emit("test rax, rax".into());
                emit(format!("jz {label}_resource_error"));
                emit(format!("mov QWORD PTR [rsp+{args_base}], rax"));
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit(format!("call boom_m{constructor}"));
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("jne {symbol}_throw"));
                emit(format!("mov rax, QWORD PTR [rsp+{args_base}]"));
                emit(format!("jmp {label}_resource_done"));
                emit(format!("{label}_resource_error:"));
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_resource_done:"));
                emit(format!("mov {}, rax", stack(depth - 2)));
            }
            Op::Throw => {
                let (throwable, _) = links.unwrap().type_target(class, "java/lang/Throwable")?;
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("mov DWORD PTR [rcx+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [rcx+8], {index}"));
                emit(format!("mov rdx, {}", stack(depth - 1)));
                emit("test rdx, rdx".into());
                emit(format!("jnz {label}_athrow_object"));
                emit("mov DWORD PTR [rcx], 4".into());
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_athrow_object:"));
                emit("lea r8, boom_runtime_type_map".into());
                emit(format!("lea r9, boom_t{throwable}"));
                emit("call boom_exception_set32".into());
                emit(format!("jmp {symbol}_throw"));
            }
            Op::Constant(_, bits) => {
                emit(format!("mov rax, {}", imm(*bits)));
                emit(format!("mov {}, rax", stack(depth)));
            }
            Op::CheckCast(target, _) | Op::InstanceOf(target) => {
                emit(format!("mov rcx, {}", stack(depth - 1)));
                emit("lea rdx, boom_runtime_type_map".into());
                emit(format!("lea r8, boom_t{target}"));
                emit("mov r9, QWORD PTR [rsp+48]".into());
                emit(format!(
                    "call {}",
                    if matches!(inst.op, Op::CheckCast(_, _)) {
                        "boom_runtime_cast"
                    } else {
                        "boom_runtime_instanceof"
                    }
                ));
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_type_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_type_ok:"));
                emit(format!("mov {}, rax", stack(depth - 1)));
            }
            Op::GetClass => {
                emit(format!("mov rax, {}", stack(depth - 1)));
                emit(format!("mov {}, rax", memory(args_base, true)));
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("mov r8, QWORD PTR [boom_heap_ptr]".into());
                emit("lea r9, boom_runtime_type_map".into());
                emit("call boom_runtime_getclass".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_getclass_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_getclass_ok:"));
                emit(format!("mov {}, rax", stack(depth - 1)));
            }
            Op::StringLiteral(literal) => {
                // Immutable roots are published as aligned QWORDs on x86-64.
                // Heap/module lifetime is fixed by boom_bind_heap; GC is quiescent.
                emit(format!(
                    "mov rax, QWORD PTR [boom_literal_roots+{}]",
                    literal * 8
                ));
                emit("test rax, rax".into());
                emit(format!("jnz {label}_string_ready"));
                emit("mov rcx, QWORD PTR [boom_heap_ptr]".into());
                emit("lea rdx, boom_string_pool".into());
                emit(format!("mov r8d, {literal}"));
                emit("mov r9, QWORD PTR [rsp+48]".into());
                emit("call boom_string_load".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_string_ready"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_string_ready:"));
                emit(format!("mov {}, rax", stack(depth)));
            }
            Op::ExternalCall(target, sig, receiver) => {
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                if *receiver {
                    emit(format!("cmp {},0", stack(depth - sig.arguments.len())));
                    emit(format!("jne {label}_external_receiver"));
                    emit("mov r10,QWORD PTR [rsp+48]".into());
                    emit("mov DWORD PTR [r10],4".into());
                    emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                    emit(format!("mov DWORD PTR [r10+8],{index}"));
                    emit(format!("jmp {symbol}_throw"));
                    emit(format!("{label}_external_receiver:"));
                }
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax,{}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {},rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit(format!("call {target}"));
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("jne {symbol}_throw"));
                if sig.result != Type::Void {
                    emit(format!("mov {},rax", stack(depth - sig.arguments.len())));
                }
            }
            Op::RawProperties(op, sig, owner) => {
                emit(format!("lea rcx, boom_class{owner}"));
                emit("mov rdx, QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax, eax".into());
                emit(format!("jnz {symbol}_throw"));
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                match op {
                    super::system_properties::Operation::Platform => {
                        emit("lea r8, boom_property_pool".into());
                        emit("call boom_platform_properties".into());
                    }
                    super::system_properties::Operation::Vm => {
                        emit("lea r8, boom_vm_property_pool".into());
                        emit("call boom_vm_properties".into());
                    }
                }
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_props_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_props_ok:"));
                emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
            }
            Op::Bitcast(sig, owner) => {
                emit(format!("lea rcx, boom_class{owner}"));
                emit("mov rdx, QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax, eax".into());
                emit(format!("jnz {symbol}_throw"));
                let reg = if sig.result.bits64() { "rax" } else { "eax" };
                emit(format!(
                    "mov {reg}, {}",
                    memory(stack_base + (depth - 1) * 8, sig.result.bits64())
                ));
                emit(format!("mov {}, rax", stack(depth - 1)));
            }
            Op::BuilderSnapshot(_, _) => {
                emit(format!("mov rax, {}", stack(depth - 1)));
                emit(format!("mov {}, rax", memory(args_base, true)));
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("lea r8, boom_builder_snapshot_pool".into());
                emit("call boom_builder_snapshot".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_snapshot_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_snapshot_ok:"));
                emit(format!("mov {}, rax", stack(depth - 1)));
            }
            Op::HexString(kind, sig, owner) => {
                emit(format!("lea rcx, boom_class{owner}"));
                emit("mov rdx, QWORD PTR [rsp+48]".into());
                emit("call boom_class_ensure".into());
                emit("test eax, eax".into());
                emit(format!("jnz {symbol}_throw"));
                emit(format!("mov rax, {}", stack(depth - 1)));
                emit(format!("mov {}, rax", memory(args_base, true)));
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("lea r8, boom_string_pool".into());
                emit(format!("mov r9d, {}", kind.bits()));
                emit("call boom_hex_string".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_hex_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_hex_ok:"));
                emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
            }
            Op::IdentityHash(_, nullable) => {
                emit(format!("mov rax, {}", stack(depth - 1)));
                emit(format!("mov {}, rax", memory(args_base, true)));
                if *nullable {
                    emit("test rax, rax".into());
                    emit(format!("je {label}_identity_valid"));
                }
                emit("mov rcx, rax".into());
                emit("lea rdx, boom_runtime_type_map".into());
                emit("mov r8, QWORD PTR [rsp+48]".into());
                emit("call boom_runtime_type".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_identity_valid"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_identity_valid:"));
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("mov rdx, {}", memory(args_base, true)));
                emit("call boom_identity_hash".into());
                emit(format!("mov {}, rax", stack(depth - 1)));
            }
            Op::ArrayClone(sig, owner) => {
                emit(format!("mov rax, {}", stack(depth - 1)));
                emit(format!("mov {}, rax", memory(args_base, true)));
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("lea r8, boom_array_clone_pool".into());
                emit(format!("lea r9, boom_t{owner}"));
                emit("call boom_array_clone".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_clone_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_clone_ok:"));
                emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
            }
            Op::StringConcatApi(sig)
            | Op::StringReplace(sig)
            | Op::LiteralRegexReplace(_, _, sig)
            | Op::StringChars(sig)
            | Op::StringLowercase(sig)
            | Op::StringSplit(sig)
            | Op::ReflectNew(_, sig)
            | Op::ReflectConstructor(_, _, sig)
            | Op::ReflectField(_, sig)
            | Op::ClassForName(sig, _)
            | Op::RuntimeResource(_, sig)
            | Op::InitializeString(sig)
            | Op::StringPrefix(sig) => {
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                if matches!(
                    inst.op,
                    Op::ReflectNew(_, _)
                        | Op::ClassForName(_, _)
                        | Op::ReflectConstructor(_, _, _)
                        | Op::ReflectField(_, _)
                ) {
                    emit("mov r10,QWORD PTR [rsp+48]".into());
                    emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                    emit(format!("mov DWORD PTR [r10+8], {index}"));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit(if let Op::ReflectNew(site, _) = inst.op {
                    format!("lea r8, boom_reflect_pool{site}")
                } else if let Op::ReflectConstructor(site, _, _) = inst.op {
                    format!("lea r8, boom_ctor_site{site}")
                } else if matches!(inst.op, Op::ReflectField(_, _)) {
                    "lea r8,boom_field_pool".into()
                } else if matches!(inst.op, Op::ClassForName(_, _)) {
                    "lea r8, boom_for_name_pool".into()
                } else if matches!(inst.op, Op::RuntimeResource(_, _)) {
                    "lea r8, boom_processor_pool".into()
                } else {
                    (if matches!(inst.op, Op::StringLowercase(_)) {
                        "lea r8, boom_lowercase_pool"
                    } else if matches!(inst.op, Op::StringSplit(_)) {
                        "lea r8, boom_split_pool"
                    } else {
                        "lea r8, boom_string_pool"
                    })
                    .into()
                });
                if let Op::ReflectConstructor(_, op, _) = inst.op {
                    emit(format!("mov r9d,{}", op as u32));
                }
                if let Op::ReflectField(op, _) = inst.op {
                    emit(format!("mov r9d,{}", op as u32));
                }
                if let Op::RuntimeResource(op, _) = inst.op {
                    emit(format!("mov r9d,{}", op as u32));
                }
                if let Op::LiteralRegexReplace(old, new, _) = inst.op {
                    emit(format!(
                        "mov r9d,{}",
                        u32::from(old) | (u32::from(new) << 16)
                    ));
                }
                emit(
                    match inst.op {
                        Op::LiteralRegexReplace(_, _, _) => {
                            "call boom_string_replace_literal_chars"
                        }
                        Op::StringReplace(_) => "call boom_string_replace",
                        Op::StringChars(_) => "call boom_string_to_chars",
                        Op::StringLowercase(_) => "call boom_string_lowercase",
                        Op::StringSplit(_) => "call boom_string_split",
                        Op::ReflectNew(_, _) => "call boom_reflect_new",
                        Op::ReflectConstructor(_, _, _) => "call boom_constructor_service",
                        Op::ReflectField(_, _) => "call boom_field_service",
                        Op::ClassForName(_, true) => "call boom_class_find_bootstrap",
                        Op::ClassForName(_, false) => "call boom_class_for_name",
                        Op::RuntimeResource(_, _) => "call boom_runtime_resource",
                        Op::InitializeString(ref sig) if sig.arguments.len() == 2 => {
                            "call boom_string_construct_chars_all"
                        }
                        Op::InitializeString(_) => "call boom_string_construct_chars",
                        Op::StringPrefix(_) => "call boom_string_starts_with",
                        _ => "call boom_string_concat_api",
                    }
                    .into(),
                );
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_concat_api_ok"));
                if matches!(
                    inst.op,
                    Op::ReflectNew(_, _)
                        | Op::ClassForName(_, _)
                        | Op::ReflectConstructor(_, _, _)
                        | Op::ReflectField(_, _)
                ) {
                    emit("test edx,edx".into());
                    emit(format!("jnz {symbol}_throw"));
                }
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_concat_api_ok:"));
                if sig.result != Type::Void {
                    emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
                }
            }
            Op::NewString => {
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit("lea rdx, boom_string_pool".into());
                emit("mov r8, QWORD PTR [boom_heap_ptr]".into());
                emit("call boom_string_new".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_new_string_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_new_string_ok:"));
                emit(format!("mov {}, rax", stack(depth)));
            }
            Op::StringGetChars(sig) => {
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax,{}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {},rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("lea r8,boom_string_pool".into());
                emit("lea r9,boom_getchars_plan".into());
                emit("call boom_string_get_chars".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_chars_done"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_chars_done:"));
            }
            Op::StringIntrinsic(operation, sig) => {
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("lea r8, boom_string_pool".into());
                emit(format!("mov r9d, {}", *operation as u32));
                emit("call boom_string_intrinsic".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_string_call_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_string_call_ok:"));
                emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
            }
            Op::Concat(plan, sig, owner) => {
                if let Some(owner) = owner {
                    emit(format!("lea rcx, boom_class{owner}"));
                    emit("mov rdx, QWORD PTR [rsp+48]".into());
                    emit("call boom_class_ensure".into());
                    emit("test eax, eax".into());
                    emit(format!("jnz {symbol}_throw"));
                }
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("mov r8, QWORD PTR [boom_heap_ptr]".into());
                emit(format!("lea r9, boom_concat_plan{plan}"));
                emit("call boom_string_concat".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_concat_call_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_concat_call_ok:"));
                emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
            }
            Op::ClassLiteral(literal) => {
                // Immutable roots are published as aligned QWORDs on x86-64.
                // Heap/module lifetime is fixed by boom_bind_heap; GC is quiescent.
                emit(format!(
                    "mov rax, QWORD PTR [boom_mirror_roots+{}]",
                    literal * 8
                ));
                emit("test rax, rax".into());
                emit(format!("jnz {label}_mirror_ready"));
                emit("mov rcx, QWORD PTR [boom_heap_ptr]".into());
                emit("lea rdx, boom_mirror_pool".into());
                emit(format!("mov r8d, {literal}"));
                emit("mov r9, QWORD PTR [rsp+48]".into());
                emit("call boom_mirror_load".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_mirror_ready"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_mirror_ready:"));
                emit(format!("mov {}, rax", stack(depth)));
            }
            Op::ClassValueField(sig, write) => {
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax,{}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {},rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("lea r8,boom_class_value_pool".into());
                emit(format!("mov r9d,{}", u32::from(*write)));
                emit("call boom_class_value_field".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_class_value_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_class_value_ok:"));
                if !write {
                    emit(format!("mov {},rax", stack(depth - sig.arguments.len())));
                }
            }
            Op::ClassLoaderField(_) => {
                emit(format!("mov rax,{}", stack(depth - 1)));
                emit(format!("mov QWORD PTR [rsp+{args_base}],rax"));
                emit("mov rcx,QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx,[rsp+{args_base}]"));
                emit("lea r8,boom_loader_pool".into());
                emit("call boom_class_loader_field".into());
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10],0".into());
                emit(format!("je {label}_loader_field_ok"));
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_loader_field_ok:"));
                emit(format!("mov {},rax", stack(depth - 1)));
            }
            Op::ClassIntrinsic(_, sig) | Op::PrimitiveClass(sig) => {
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("lea r8, boom_mirror_pool".into());
                if let Op::ClassIntrinsic(operation, _) = inst.op {
                    if matches!(operation, ClassIntrinsic::IsHidden) {
                        emit("lea r8, boom_class_query_pool".into());
                        emit("call boom_class_is_hidden".into());
                    } else if matches!(operation, ClassIntrinsic::IsInstance) {
                        emit("lea r8, boom_runtime_type_map".into());
                        emit("call boom_class_is_instance".into());
                    } else if matches!(
                        operation,
                        ClassIntrinsic::CanonicalName | ClassIntrinsic::SimpleName
                    ) {
                        emit("lea r8,boom_class_name_pool".into());
                        emit(format!(
                            "mov r9d,{}",
                            u32::from(matches!(operation, ClassIntrinsic::SimpleName))
                        ));
                        emit("call boom_class_name".into());
                    } else {
                        emit(format!("mov r9d, {}", operation as u32));
                        emit("call boom_mirror_intrinsic".into());
                    }
                } else {
                    emit("lea r9, boom_primitive_type_ids".into());
                    emit("call boom_mirror_primitive".into());
                }
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_mirror_call_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_mirror_call_ok:"));
                emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
            }
            Op::ModuleIntrinsic(operation, sig, factory) => {
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit("lea r8, boom_module_pool".into());
                emit(format!("mov r9d, {}", *operation as u32));
                emit(
                    if operation.uses_layer() {
                        "call boom_layer_intrinsic"
                    } else {
                        "call boom_module_intrinsic"
                    }
                    .into(),
                );
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_module_call_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_module_call_ok:"));
                if let Some(factory) = factory {
                    emit(format!("mov {}, rax", memory(args_base, true)));
                    emit("mov rcx, QWORD PTR [rsp+48]".into());
                    emit(format!("lea rdx, [rsp+{args_base}]"));
                    emit(format!("call boom_m{factory}"));
                    emit("mov r10, QWORD PTR [rsp+48]".into());
                    emit("cmp DWORD PTR [r10], 0".into());
                    emit(format!("jne {symbol}_throw"));
                }
                emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
            }
            Op::Load(_, i) => {
                emit(format!("mov rax, {}", local(*i)));
                emit(format!("mov {}, rax", stack(depth)));
            }
            Op::Store(_, i) => {
                emit(format!("mov rax, {}", stack(depth - 1)));
                emit(format!("mov {}, rax", local(*i)));
            }
            Op::Pop | Op::Pop2 => (),
            Op::Reorder(op) => {
                let (count, order) = stack_reorder(*op, &frame.stack)?;
                for i in 0..count {
                    emit(format!("mov rax, {}", stack(depth - count + i)));
                    emit(format!("mov {}, rax", memory(args_base + i * 8, true)));
                }
                for (dest, source) in order.iter().enumerate() {
                    emit(format!("mov rax, {}", memory(args_base + source * 8, true)));
                    emit(format!("mov {}, rax", stack(depth - count + dest)));
                }
            }
            Op::Dup => {
                emit(format!("mov rax, {}", stack(depth - 1)));
                emit(format!("mov {}, rax", stack(depth)));
            }
            Op::Dup2 => {
                if frame.stack[depth - 1].width() == 2 {
                    emit(format!("mov rax, {}", stack(depth - 1)));
                    emit(format!("mov {}, rax", stack(depth)));
                } else {
                    emit(format!("mov rax, {}", stack(depth - 2)));
                    emit(format!("mov rcx, {}", stack(depth - 1)));
                    emit(format!("mov {}, rax", stack(depth)));
                    emit(format!("mov {}, rcx", stack(depth + 1)));
                }
            }
            Op::Swap => {
                emit(format!("mov rax, {}", stack(depth - 1)));
                emit(format!("mov rcx, {}", stack(depth - 2)));
                emit(format!("mov {}, rax", stack(depth - 2)));
                emit(format!("mov {}, rcx", stack(depth - 1)));
            }
            Op::Neg(ty) => {
                emit(format!(
                    "mov {}, {}",
                    if ty.width() == 2 { "rax" } else { "eax" },
                    memory(stack_base + (depth - 1) * 8, ty.width() == 2)
                ));
                emit(
                    match ty {
                        Type::I32 => "neg eax",
                        Type::I64 => "neg rax",
                        Type::F32 => "xor eax, 080000000h",
                        Type::F64 => "btc rax, 63",
                        _ => unreachable!("neg only accepts numeric types"),
                    }
                    .into(),
                );
                emit(format!("mov {}, rax", stack(depth - 1)));
            }
            Op::Narrow(op) => {
                emit(format!(
                    "mov eax, {}",
                    memory(stack_base + (depth - 1) * 8, false)
                ));
                emit(
                    match op {
                        0x91 => "movsx eax, al",
                        0x92 => "movzx eax, ax",
                        0x93 => "movsx eax, ax",
                        _ => unreachable!(),
                    }
                    .into(),
                );
                emit(format!("mov {}, rax", stack(depth - 1)));
            }
            Op::Increment(i, value) => emit(format!(
                "add {}, {}",
                memory(local_base + i * 8, false),
                imm(*value as u32 as u64)
            )),
            Op::Binary(ty, Binary::Rem) if matches!(ty, Type::F32 | Type::F64) => {
                emit(format!("mov rcx,{}", stack(depth - 2)));
                emit(format!("mov rdx,{}", stack(depth - 1)));
                emit(format!(
                    "call boom_frem{}",
                    if *ty == Type::F32 { 32 } else { 64 }
                ));
                emit(format!("mov {},rax", stack(depth - 2)));
            }
            Op::Binary(ty, op) if ty.integer() => {
                let wide = *ty == Type::I64;
                let a = if wide { "rax" } else { "eax" };
                let b = if wide { "rcx" } else { "ecx" };
                emit(format!(
                    "mov {a}, {}",
                    memory(stack_base + (depth - 2) * 8, wide)
                ));
                let right_wide = wide && !matches!(op, Binary::Shl | Binary::Shr | Binary::Ushr);
                emit(format!(
                    "mov {}, {}",
                    if right_wide { "rcx" } else { "ecx" },
                    memory(stack_base + (depth - 1) * 8, right_wide)
                ));
                if matches!(op, Binary::Div | Binary::Rem) {
                    emit(format!("test {b}, {b}"));
                    emit(format!("jnz {label}_nonzero"));
                    emit("mov r10, QWORD PTR [rsp+48]".into());
                    emit("mov DWORD PTR [r10], 1".into());
                    emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                    emit(format!("mov DWORD PTR [r10+8], {index}"));
                    emit(format!("jmp {symbol}_throw"));
                    emit(format!("{label}_nonzero:"));
                    emit(format!(
                        "mov r10, {}",
                        imm(if wide {
                            i64::MIN as u64
                        } else {
                            i32::MIN as u32 as u64
                        })
                    ));
                    emit(format!("cmp {a}, {}", if wide { "r10" } else { "r10d" }));
                    emit(format!("jne {label}_divide"));
                    emit(format!("cmp {b}, -1"));
                    emit(format!("jne {label}_divide"));
                    if matches!(op, Binary::Rem) {
                        emit("xor eax, eax".into());
                    }
                    emit(format!("jmp {label}_div_done"));
                    emit(format!("{label}_divide:"));
                    emit(if wide { "cqo" } else { "cdq" }.into());
                    emit(format!("idiv {b}"));
                    if matches!(op, Binary::Rem) {
                        emit(if wide { "mov rax, rdx" } else { "mov eax, edx" }.into());
                    }
                    emit(format!("{label}_div_done:"));
                } else {
                    let operation = match op {
                        Binary::Add => "add",
                        Binary::Sub => "sub",
                        Binary::Mul => "imul",
                        Binary::And => "and",
                        Binary::Or => "or",
                        Binary::Xor => "xor",
                        Binary::Shl => "shl",
                        Binary::Shr => "sar",
                        Binary::Ushr => "shr",
                        _ => unreachable!(),
                    };
                    emit(format!(
                        "{operation} {a}, {}",
                        if matches!(op, Binary::Shl | Binary::Shr | Binary::Ushr) {
                            "cl"
                        } else {
                            b
                        }
                    ));
                }
                emit(format!("mov {}, rax", stack(depth - 2)));
            }
            Op::Binary(ty, op) => {
                let suffix = if *ty == Type::F32 { "ss" } else { "sd" };
                let wide = *ty == Type::F64;
                emit(format!(
                    "mov{suffix} xmm0, {}",
                    memory(stack_base + (depth - 2) * 8, wide)
                ));
                emit(format!(
                    "mov{suffix} xmm1, {}",
                    memory(stack_base + (depth - 1) * 8, wide)
                ));
                emit(format!(
                    "{}{suffix} xmm0, xmm1",
                    match op {
                        Binary::Add => "add",
                        Binary::Sub => "sub",
                        Binary::Mul => "mul",
                        Binary::Div => "div",
                        _ => unreachable!(),
                    }
                ));
                emit(
                    if wide {
                        "movq rax, xmm0"
                    } else {
                        "movd eax, xmm0"
                    }
                    .into(),
                );
                emit(format!("mov {}, rax", stack(depth - 2)));
            }
            Op::Compare(ty, nan) => {
                if *ty == Type::I64 {
                    emit(format!("mov rax, {}", stack(depth - 2)));
                    emit(format!("cmp rax, {}", stack(depth - 1)));
                } else {
                    let suffix = if *ty == Type::F32 { "ss" } else { "sd" };
                    let wide = *ty == Type::F64;
                    emit(format!(
                        "mov{suffix} xmm0, {}",
                        memory(stack_base + (depth - 2) * 8, wide)
                    ));
                    emit(format!(
                        "ucomi{suffix} xmm0, {}",
                        memory(stack_base + (depth - 1) * 8, wide)
                    ));
                    emit(format!("jp {label}_nan"));
                }
                emit("mov eax, 0".into());
                emit(format!("je {label}_cmp_done"));
                emit(format!(
                    "{} {label}_greater",
                    if *ty == Type::I64 { "jg" } else { "ja" }
                ));
                emit("mov eax, 0FFFFFFFFh".into());
                emit(format!("jmp {label}_cmp_done"));
                emit(format!("{label}_greater:"));
                emit("mov eax, 1".into());
                emit(format!("jmp {label}_cmp_done"));
                if *ty != Type::I64 {
                    emit(format!("{label}_nan:"));
                    emit(format!("mov eax, {}", imm(*nan as u32 as u64)));
                }
                emit(format!("{label}_cmp_done:"));
                emit(format!("mov {}, rax", stack(depth - 2)));
            }
            Op::BootGuard(kind, relation, taken, dest) => {
                match kind {
                    0 => emit(format!(
                        "cmp {},0",
                        memory(stack_base + (depth - 1) * 8, false)
                    )),
                    1 => {
                        emit(format!(
                            "mov eax,{}",
                            memory(stack_base + (depth - 2) * 8, false)
                        ));
                        emit(format!(
                            "cmp eax,{}",
                            memory(stack_base + (depth - 1) * 8, false)
                        ));
                    }
                    2 => emit(format!("cmp {},0", stack(depth - 1))),
                    _ => {
                        emit(format!("mov rax,{}", stack(depth - 2)));
                        emit(format!("cmp rax,{}", stack(depth - 1)));
                    }
                }
                let relation = if *taken { *relation } else { *relation ^ 1 };
                emit(format!("{} {label}_boot_guard_ok", jump(relation)));
                emit("mov r10,QWORD PTR [rsp+48]".into());
                emit("mov DWORD PTR [r10],7".into());
                emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8],{index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_boot_guard_ok:"));
                emit(format!("jmp {symbol}_L{dest}"));
            }
            Op::If(condition, dest) => {
                emit(format!(
                    "cmp {}, 0",
                    memory(stack_base + (depth - 1) * 8, false)
                ));
                emit(format!("{} {symbol}_L{dest}", jump(*condition)));
            }
            Op::IfPair(condition, dest) => {
                emit(format!(
                    "mov eax, {}",
                    memory(stack_base + (depth - 2) * 8, false)
                ));
                emit(format!(
                    "cmp eax, {}",
                    memory(stack_base + (depth - 1) * 8, false)
                ));
                emit(format!("{} {symbol}_L{dest}", jump(*condition)));
            }
            Op::Goto(dest) => emit(format!("jmp {symbol}_L{dest}")),
            Op::Switch(default, cases) => {
                emit(format!(
                    "mov eax, {}",
                    memory(stack_base + (depth - 1) * 8, false)
                ));
                for (key, dest) in cases {
                    emit(format!("cmp eax, {}", imm(*key as u32 as u64)));
                    emit(format!("je {symbol}_L{dest}"));
                }
                emit(format!("jmp {symbol}_L{default}"));
            }
            Op::Call(target, sig)
            | Op::BridgeCall(target, sig)
            | Op::InstanceCall(target, sig)
            | Op::ProtectedInitialize(target, sig, _)
            | Op::Initialize(Some(target), sig) => {
                if matches!(inst.op, Op::BridgeCall(_, _)) {
                    emit(format!("cmp {},0", stack(depth - sig.arguments.len())));
                    emit(format!("jne {label}_receiver_ok"));
                    emit("mov r10,QWORD PTR [rsp+48]".into());
                    emit("mov DWORD PTR [r10],4".into());
                    emit(format!("mov DWORD PTR [r10+4],{}", inst.pc));
                    emit(format!("mov DWORD PTR [r10+8],{index}"));
                    emit(format!("jmp {symbol}_throw"));
                    emit(format!("{label}_receiver_ok:"));
                } else if matches!(inst.op, Op::InstanceCall(_, _)) {
                    emit(format!("mov rcx, {}", stack(depth - sig.arguments.len())));
                    emit(format!("lea rdx, {}", object_label(sig.arguments[0])));
                    emit("mov r8, QWORD PTR [rsp+48]".into());
                    emit("call boom_object_check".into());
                    emit("mov r10, QWORD PTR [rsp+48]".into());
                    emit("cmp DWORD PTR [r10], 0".into());
                    emit(format!("je {label}_receiver_ok"));
                    emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                    emit(format!("mov DWORD PTR [r10+8], {index}"));
                    emit(format!("jmp {symbol}_throw"));
                    emit(format!("{label}_receiver_ok:"));
                }
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit(format!("call boom_m{target}"));
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("jne {symbol}_throw"));
                if sig.result != Type::Void {
                    emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
                }
            }
            Op::InterfaceCall(site, sig, _, _) => {
                for arg in 0..sig.arguments.len() {
                    emit(format!(
                        "mov rax, {}",
                        stack(depth - sig.arguments.len() + arg)
                    ));
                    emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                }
                emit("mov rcx, QWORD PTR [rsp+48]".into());
                emit(format!("lea rdx, [rsp+{args_base}]"));
                emit(format!("call boom_dispatch{site}"));
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_dispatch_ok"));
                emit("test edx, edx".into());
                emit(format!("jnz {symbol}_throw"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_dispatch_ok:"));
                if sig.result != Type::Void {
                    emit(format!("mov {}, rax", stack(depth - sig.arguments.len())));
                }
            }
            Op::StaticLoad(field) | Op::StaticStore(field) => {
                // The wrapper (or owning initializer) already ensures this class.
                // Foreign field owners still require their own initialization.
                if field.owner
                    != links
                        .context("Static field needs program context")?
                        .class_id(class)?
                {
                    emit(format!("lea rcx, boom_class{}", field.owner));
                    emit("mov rdx, QWORD PTR [rsp+48]".into());
                    emit("call boom_class_ensure".into());
                    emit("test eax, eax".into());
                    emit(format!("jz {label}_static_ok"));
                    emit("mov r10, QWORD PTR [rsp+48]".into());
                    emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                    emit(format!("mov DWORD PTR [r10+8], {index}"));
                    emit(format!("jmp {symbol}_throw"));
                    emit(format!("{label}_static_ok:"));
                }
                let name = format!("boom_s{}_{}", field.owner, field.index);
                if matches!(inst.op, Op::StaticLoad(_)) {
                    if field.access & 0x40 != 0 {
                        emit(
                            "; volatile acquire load (aligned x86-64 MOV; no hoisting/CSE)".into(),
                        );
                    }
                    emit(format!(
                        "mov {}, {} PTR [{name}]",
                        if field.ty.bits64() { "rax" } else { "eax" },
                        if field.ty.bits64() { "QWORD" } else { "DWORD" }
                    ));
                    emit(format!("mov {}, rax", stack(depth)));
                } else {
                    emit(format!("mov rax, {}", stack(depth - 1)));
                    match field.narrow {
                        b'Z' => emit("and eax, 1".into()),
                        b'B' => emit("movsx eax, al".into()),
                        b'C' => emit("movzx eax, ax".into()),
                        b'S' => emit("movsx eax, ax".into()),
                        _ => (),
                    }
                    emit(if field.access & 0x40 != 0 {
                        format!("xchg QWORD PTR [{name}], rax ; volatile SC store")
                    } else {
                        format!("mov QWORD PTR [{name}], rax")
                    });
                }
            }
            Op::Initialize(None, _) => (), // java/lang/Object.<init>()V has no body.
            Op::Return(ty) => {
                if *ty == Type::Void {
                    emit("xor eax, eax".into());
                    emit(format!("jmp {symbol}_return"));
                    continue;
                }
                emit(format!(
                    "mov {}, {}",
                    if ty.bits64() { "rax" } else { "eax" },
                    memory(stack_base + (depth - 1) * 8, ty.bits64())
                ));
                match method.descriptor.rsplit_once(')').map(|(_, result)| result) {
                    Some("Z") => emit("and eax, 1".into()),
                    Some("B") => emit("movsx eax, al".into()),
                    Some("C") => emit("movzx eax, ax".into()),
                    Some("S") => emit("movsx eax, ax".into()),
                    _ => (),
                }
                emit(format!("jmp {symbol}_return"));
            }
            Op::Cast(_, _) => unreachable!(),
            Op::NewObject
            | Op::NewLinkedObject(_)
            | Op::FieldLoad(_, _)
            | Op::FieldStore(_, _)
            | Op::LinkedFieldLoad(_)
            | Op::LinkedFieldStore(_) => {
                let object = match inst.op {
                    Op::NewLinkedObject(owner) => Type::LinkedObject(owner),
                    Op::LinkedFieldLoad(f) | Op::LinkedFieldStore(f) => Type::LinkedObject(f.owner),
                    _ => Type::Object,
                };
                let output = if matches!(inst.op, Op::NewObject | Op::NewLinkedObject(_)) {
                    if let Op::NewLinkedObject(owner) = inst.op {
                        emit(format!("lea rcx, boom_class{owner}"));
                        emit("mov rdx, QWORD PTR [rsp+48]".into());
                        emit("call boom_class_ensure".into());
                        emit("test eax, eax".into());
                        emit(format!("jz {label}_new_ready"));
                        emit("mov r10, QWORD PTR [rsp+48]".into());
                        emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                        emit(format!("mov DWORD PTR [r10+8], {index}"));
                        emit(format!("jmp {symbol}_throw"));
                        emit(format!("{label}_new_ready:"));
                    }
                    emit("mov rcx, QWORD PTR [boom_heap_ptr]".into());
                    emit(format!("lea rdx, {}", object_label(object)));
                    emit("mov r8, QWORD PTR [rsp+48]".into());
                    emit("call boom_object_new".into());
                    Some(depth)
                } else {
                    let store = matches!(inst.op, Op::FieldStore(_, _) | Op::LinkedFieldStore(_));
                    emit(format!(
                        "mov rcx, {}",
                        stack(depth - if store { 2 } else { 1 })
                    ));
                    let mapping = match inst.op {
                        Op::LinkedFieldLoad(field) | Op::LinkedFieldStore(field) => field.mapping,
                        _ => None,
                    };
                    if let Some(mapping) = mapping {
                        emit("mov rdx, QWORD PTR [rsp+48]".into());
                        emit(format!("call boom_field_map{mapping}"));
                    } else {
                        emit(format!("lea rdx, {}", object_label(object)));
                        emit("mov r8, QWORD PTR [rsp+48]".into());
                        emit("call boom_object_check".into());
                    }
                    None
                };
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_object_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_object_ok:"));
                match &inst.op {
                    Op::FieldLoad(field, ty) => {
                        let offset = field_offset(class, *field)?;
                        emit(format!(
                            "mov {}, {} PTR [rax+{offset}]",
                            if ty.bits64() { "rax" } else { "eax" },
                            if ty.bits64() { "QWORD" } else { "DWORD" }
                        ));
                        emit(format!("mov {}, rax", stack(depth - 1)));
                    }
                    Op::LinkedFieldLoad(field) => {
                        if field.access & 0x40 != 0 {
                            ensure!(
                                matches!(field.storage_bytes, 1 | 2 | 4 | 8)
                                    && (field.mapping.is_some()
                                        || field.offset % field.storage_bytes == 0),
                                "Volatile field alignment is not proven"
                            );
                            emit(
                                "; volatile acquire load (aligned x86-64 MOV; no hoisting/CSE)"
                                    .into(),
                            );
                        }
                        let offset = if field.mapping.is_some() {
                            0
                        } else {
                            field.offset
                        };
                        let instruction = match (field.storage_bytes, field.narrow) {
                            (1, b'B') => format!("movsx eax, BYTE PTR [rax+{offset}]"),
                            (1, b'Z') => format!("movzx eax, BYTE PTR [rax+{offset}]"),
                            (2, b'S') => format!("movsx eax, WORD PTR [rax+{offset}]"),
                            (2, b'C') => format!("movzx eax, WORD PTR [rax+{offset}]"),
                            (4, _) => format!("mov eax, DWORD PTR [rax+{offset}]"),
                            (8, _) => format!(
                                "mov {}, {} PTR [rax+{offset}]",
                                if field.ty.bits64() { "rax" } else { "eax" },
                                if field.ty.bits64() { "QWORD" } else { "DWORD" }
                            ),
                            _ => bail!("Unsupported field storage width"),
                        };
                        emit(instruction);
                        emit(format!("mov {}, rax", stack(depth - 1)));
                    }
                    Op::LinkedFieldStore(field) => {
                        emit("mov r11, rax".into());
                        emit(format!("mov rax, {}", stack(depth - 1)));
                        match field.narrow {
                            b'Z' => emit("and eax, 1".into()),
                            b'B' => emit("movsx eax, al".into()),
                            b'C' => emit("movzx eax, ax".into()),
                            b'S' => emit("movsx eax, ax".into()),
                            _ => (),
                        }
                        let offset = if field.mapping.is_some() {
                            0
                        } else {
                            field.offset
                        };
                        let (size, value) = match field.storage_bytes {
                            1 => ("BYTE", "al"),
                            2 => ("WORD", "ax"),
                            4 => ("DWORD", "eax"),
                            8 => ("QWORD", "rax"),
                            _ => bail!("Unsupported field storage width"),
                        };
                        if field.access & 0x40 != 0 {
                            ensure!(
                                matches!(field.storage_bytes, 1 | 2 | 4 | 8)
                                    && (field.mapping.is_some()
                                        || offset % field.storage_bytes == 0),
                                "Volatile field alignment is not proven"
                            );
                            emit(format!(
                                "xchg {size} PTR [r11+{offset}], {value} ; volatile SC store"
                            ));
                        } else {
                            emit(format!("mov {size} PTR [r11+{offset}], {value}"));
                        }
                    }
                    Op::FieldStore(field, _) => {
                        ensure!(
                            class.field_info[*field].access & 0x10 == 0 || method.name == "<init>",
                            "Final fields may only be assigned by a constructor"
                        );
                        let offset = field_offset(class, *field)?;
                        emit("mov r11, rax".into());
                        emit(format!("mov rax, {}", stack(depth - 1)));
                        match class.field_info[*field].descriptor.as_str() {
                            "Z" => emit("and eax, 1".into()),
                            "B" => emit("movsx eax, al".into()),
                            "C" => emit("movzx eax, ax".into()),
                            "S" => emit("movsx eax, ax".into()),
                            _ => (),
                        }
                        emit(format!("mov QWORD PTR [r11+{offset}], rax"));
                    }
                    _ => {
                        if let Some(slot) = output {
                            emit(format!("mov {}, rax", stack(slot)));
                        }
                    }
                }
            }
            Op::IfNull(ne, dest) => {
                emit(format!("cmp {}, 0", stack(depth - 1)));
                emit(format!(
                    "{} {symbol}_L{dest}",
                    if *ne { "jne" } else { "je" }
                ));
            }
            Op::IfRefs(ne, dest) => {
                emit(format!("mov rax, {}", stack(depth - 2)));
                emit(format!("cmp rax, {}", stack(depth - 1)));
                emit(format!(
                    "{} {symbol}_L{dest}",
                    if *ne { "jne" } else { "je" }
                ));
            }
            Op::NewTypedArray(type_id, _, dimensions) => {
                let dimensions = usize::from(*dimensions);
                emit("mov rcx, QWORD PTR [boom_heap_ptr]".into());
                emit(format!(
                    "lea rdx, [rsp+{}]",
                    stack_base + (depth - dimensions) * 8
                ));
                emit(format!("lea r8, boom_t{type_id}"));
                emit(format!("mov r9d, {dimensions}"));
                emit("mov rax, QWORD PTR [rsp+48]".into());
                emit("mov QWORD PTR [rsp+32], rax".into());
                emit("call boom_typed_multi_new".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_typed_new_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_typed_new_ok:"));
                emit(format!("mov {}, rax", stack(depth - dimensions)));
            }
            Op::ArrayLength
                if matches!(
                    frame.stack[depth - 1],
                    Type::MetadataReference(_) | Type::ReferenceJoin(_)
                ) =>
            {
                emit(format!("mov rcx, {}", stack(depth - 1)));
                emit("lea rdx, boom_runtime_type_map".into());
                emit("mov r8, QWORD PTR [rsp+48]".into());
                emit("call boom_typed_array_length".into());
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_typed_length_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_typed_length_ok:"));
                emit(format!("mov {}, rax", stack(depth - 1)));
            }
            Op::NewArray(_)
            | Op::ArrayLength
            | Op::ArrayLoad(_)
            | Op::ArrayStore(_)
            | Op::NewReferenceArray
            | Op::NewLinkedReferenceArray(_)
            | Op::NewStringArray
            | Op::NewClassArray
            | Op::ReferenceArrayLoad
            | Op::ReferenceArrayStore => {
                let dynamic = links.is_some_and(|l| l.covariant_arrays());
                let dynamic_op = match inst.op {
                    Op::ReferenceArrayLoad => Some((1, 2)),
                    Op::ReferenceArrayStore => Some((2, 3)),
                    Op::ArrayLength
                        if matches!(
                            frame.stack[depth - 1],
                            Type::ObjectArray
                                | Type::LinkedObjectArray(_)
                                | Type::BootstrapStringArray
                                | Type::BootstrapClassArray
                        ) =>
                    {
                        Some((0, 1))
                    }
                    _ => None,
                };
                let output = if dynamic && let Some((operation, arguments)) = dynamic_op {
                    for arg in 0..arguments {
                        emit(format!("mov rax, {}", stack(depth - arguments + arg)));
                        emit(format!("mov {}, rax", memory(args_base + arg * 8, true)));
                    }
                    emit("mov rcx, QWORD PTR [rsp+48]".into());
                    emit(format!("lea rdx, [rsp+{args_base}]"));
                    emit("lea r8, boom_runtime_type_map".into());
                    emit(format!("mov r9d, {operation}"));
                    emit("call boom_covariant_array".into());
                    if operation == 2 {
                        None
                    } else {
                        Some(depth - arguments)
                    }
                } else {
                    match &inst.op {
                        Op::NewArray(kind) => {
                            emit("mov rcx, QWORD PTR [boom_heap_ptr]".into());
                            emit(format!(
                                "mov edx, {}",
                                memory(stack_base + (depth - 1) * 8, false)
                            ));
                            emit(format!("mov r8d, {}", kind.atype()));
                            emit("mov r9, QWORD PTR [rsp+48]".into());
                            emit("call boom_array_new".into());
                            Some(depth - 1)
                        }
                        Op::ArrayLength => {
                            emit(format!("mov rcx, {}", stack(depth - 1)));
                            if matches!(
                                frame.stack[depth - 1],
                                Type::ObjectArray
                                    | Type::LinkedObjectArray(_)
                                    | Type::BootstrapStringArray
                                    | Type::BootstrapClassArray
                            ) {
                                emit(format!(
                                    "lea rdx, {}",
                                    reference_label(frame.stack[depth - 1])
                                ));
                                emit("mov r8, QWORD PTR [rsp+48]".into());
                                emit("call boom_reference_array_length".into());
                            } else {
                                emit("mov rdx, QWORD PTR [rsp+48]".into());
                                emit("call boom_array_length".into());
                            }
                            Some(depth - 1)
                        }
                        Op::ArrayLoad(kind) => {
                            emit(format!("mov rcx, {}", stack(depth - 2)));
                            emit(format!(
                                "mov edx, {}",
                                memory(stack_base + (depth - 1) * 8, false)
                            ));
                            emit(format!("mov r8d, {}", kind.atype()));
                            emit("mov r9, QWORD PTR [rsp+48]".into());
                            emit("call boom_array_load".into());
                            Some(depth - 2)
                        }
                        Op::ArrayStore(kind) => {
                            emit(format!("mov rcx, {}", stack(depth - 3)));
                            emit(format!(
                                "mov edx, {}",
                                memory(stack_base + (depth - 2) * 8, false)
                            ));
                            emit(format!("mov r8, {}", stack(depth - 1)));
                            emit(format!("mov r9d, {}", kind.atype()));
                            emit("mov rax, QWORD PTR [rsp+48]".into());
                            emit("mov QWORD PTR [rsp+32], rax".into());
                            emit("call boom_array_store".into());
                            None
                        }
                        Op::NewReferenceArray
                        | Op::NewLinkedReferenceArray(_)
                        | Op::NewStringArray
                        | Op::NewClassArray => {
                            emit("mov rcx, QWORD PTR [boom_heap_ptr]".into());
                            emit(format!(
                                "mov edx, {}",
                                memory(stack_base + (depth - 1) * 8, false)
                            ));
                            let ty = if matches!(inst.op, Op::NewClassArray) {
                                Type::BootstrapClassArray
                            } else if matches!(inst.op, Op::NewStringArray) {
                                Type::BootstrapStringArray
                            } else if let Op::NewLinkedReferenceArray(owner) = inst.op {
                                Type::LinkedObjectArray(owner)
                            } else {
                                Type::ObjectArray
                            };
                            emit(format!("lea r8, {}", reference_label(ty)));
                            emit("mov r9, QWORD PTR [rsp+48]".into());
                            emit("call boom_reference_array_new".into());
                            Some(depth - 1)
                        }
                        Op::ReferenceArrayLoad => {
                            emit(format!("mov rcx, {}", stack(depth - 2)));
                            emit(format!(
                                "mov edx, {}",
                                memory(stack_base + (depth - 1) * 8, false)
                            ));
                            emit(format!(
                                "lea r8, {}",
                                reference_label(frame.stack[depth - 2])
                            ));
                            emit("mov r9, QWORD PTR [rsp+48]".into());
                            emit("call boom_reference_array_load".into());
                            Some(depth - 2)
                        }
                        Op::ReferenceArrayStore => {
                            emit(format!("mov rcx, {}", stack(depth - 3)));
                            emit(format!(
                                "mov edx, {}",
                                memory(stack_base + (depth - 2) * 8, false)
                            ));
                            emit(format!("mov r8, {}", stack(depth - 1)));
                            emit(format!(
                                "lea r9, {}",
                                reference_label(frame.stack[depth - 3])
                            ));
                            emit("mov rax, QWORD PTR [rsp+48]".into());
                            emit("mov QWORD PTR [rsp+32], rax".into());
                            emit("call boom_reference_array_store".into());
                            None
                        }
                        _ => unreachable!(),
                    }
                };
                emit("mov r10, QWORD PTR [rsp+48]".into());
                emit("cmp DWORD PTR [r10], 0".into());
                emit(format!("je {label}_array_ok"));
                emit(format!("mov DWORD PTR [r10+4], {}", inst.pc));
                emit(format!("mov DWORD PTR [r10+8], {index}"));
                emit(format!("jmp {symbol}_throw"));
                emit(format!("{label}_array_ok:"));
                if let Some(slot) = output {
                    emit(format!("mov {}, rax", stack(slot)));
                }
            }
        }
    }
    lines.push(format!("{symbol}_throw:"));
    if context32 {
        lines.extend([
            "    mov rcx, QWORD PTR [rsp+48]".into(),
            "    call boom_exception_materialize".into(),
        ]);
        if !code.handlers.is_empty() {
            lines.extend([
                "    mov rcx, QWORD PTR [rsp+48]".into(),
                format!("    mov edx, DWORD PTR [rsp+{}]", trace_base + 24),
                format!("    lea r8, boom_handlers{index}"),
                "    call boom_exception_match32".into(),
                "    test eax, eax".into(),
                format!("    jz {symbol}_unhandled"),
                format!("    mov DWORD PTR [rsp+{}], eax", trace_base + 48),
                "    mov rcx, QWORD PTR [rsp+48]".into(),
                "    call boom_exception_take32".into(),
                format!("    mov {}, rax", memory(stack_base, true)),
            ]);
            for pc in code
                .handlers
                .iter()
                .map(|h| h.handler_pc)
                .collect::<BTreeSet<_>>()
            {
                lines.push(format!(
                    "    cmp DWORD PTR [rsp+{}], {}",
                    trace_base + 48,
                    u32::from(pc) + 1
                ));
                lines.push(format!("    je {symbol}_L{pc}"));
            }
            lines.push(format!("{symbol}_unhandled:"));
        }
    }
    lines.extend(["    xor eax, eax".into(), format!("{symbol}_return:")]);
    if traced {
        lines.extend([
            format!("    mov QWORD PTR [rsp+{}], rax", trace_base + 48),
            "    lea rcx, boom_trace_pool".into(),
            format!("    lea rdx, [rsp+{trace_base}]"),
            "    mov r8, QWORD PTR [rsp+48]".into(),
            "    call boom_trace_leave".into(),
            format!("    mov rax, QWORD PTR [rsp+{}]", trace_base + 48),
        ]);
    }
    lines.extend([
        "    mov r10, QWORD PTR [rsp+48]".into(),
        "    dec DWORD PTR [r10+12]".into(),
        format!("    jmp {symbol}_exit"),
        format!("{symbol}_stack_limit:"),
        "    mov r10, QWORD PTR [rsp+48]".into(),
        "    mov DWORD PTR [r10], 10".into(),
        "    mov DWORD PTR [r10+4], 0".into(),
        format!("    mov DWORD PTR [r10+8], {index}"),
        "    xor eax, eax".into(),
        format!("{symbol}_exit:"),
        format!("    add rsp, {bytes}"),
        "    ret".into(),
        format!("{symbol} ENDP"),
    ]);
    Ok((lines.join("\n") + "\n", instructions.len()))
}

pub fn compile(class: &ClassFile, method: &Method) -> Result<Compiled> {
    ensure!(
        class.super_name == "java/lang/Object"
            && class.interfaces == 0
            && class.access & 0x2600 == 0,
        "Backend currently requires one concrete Object subclass without interfaces"
    );
    for field in &class.field_info {
        ensure!(
            field.access & (8 | 0x40) == 0,
            "Static/volatile fields need class state and memory-model support"
        );
        validate_local_references(&field.descriptor, class)?;
        field_type(&field.descriptor)?;
    }
    ensure!(
        method.access & 8 != 0 && !method.name.starts_with('<'),
        "Diagnostic entry must be an ordinary static method"
    );
    ensure!(
        !class.methods.iter().any(|m| m.name == "<clinit>"),
        "Class initialization is not implemented"
    );
    ensure!(
        class
            .name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_$/".contains(&b)),
        "Unsafe class identifier"
    );
    fn visit(
        class: &ClassFile,
        index: usize,
        active: &mut BTreeSet<usize>,
        done: &mut BTreeSet<usize>,
        order: &mut Vec<usize>,
    ) -> Result<()> {
        if done.contains(&index) || active.contains(&index) {
            return Ok(());
        }
        ensure!(order.len() < 128, "Numeric call graph exceeds 128 methods");
        active.insert(index);
        order.push(index);
        let method = &class.methods[index];
        method_signature(class, method)?;
        ensure!(
            method
                .name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_$".contains(&b))
                || method.name == "<init>",
            "Unsafe method identifier"
        );
        for inst in decode(
            method.code.as_ref().context("Call target has no Code")?,
            class,
        )? {
            if let Op::Call(target, _)
            | Op::BridgeCall(target, _)
            | Op::InstanceCall(target, _)
            | Op::ProtectedInitialize(target, _, _)
            | Op::Initialize(Some(target), _) = inst.op
            {
                visit(class, target, active, done, order)?;
            }
        }
        active.remove(&index);
        done.insert(index);
        Ok(())
    }
    let root = class
        .methods
        .iter()
        .position(|m| std::ptr::eq(m, method))
        .context("Method belongs to another class")?;
    let mut order = Vec::new();
    visit(
        class,
        root,
        &mut BTreeSet::new(),
        &mut BTreeSet::new(),
        &mut order,
    )?;
    let mut assembly = module_header(root);
    let mut requires_heap = false;
    for index in &order {
        let code = class.methods[*index]
            .code
            .as_ref()
            .context("Missing Code")?;
        requires_heap |= decode(code, class)?.iter().any(|inst| {
            matches!(
                inst.op,
                Op::NewArray(_)
                    | Op::ArrayLength
                    | Op::ArrayLoad(_)
                    | Op::ArrayStore(_)
                    | Op::NewObject
                    | Op::FieldLoad(_, _)
                    | Op::FieldStore(_, _)
                    | Op::InstanceCall(_, _)
                    | Op::Initialize(_, _)
                    | Op::ProtectedInitialize(_, _, _)
                    | Op::NewReferenceArray
                    | Op::ReferenceArrayLoad
                    | Op::ReferenceArrayStore
            )
        });
    }
    if requires_heap {
        append_heap_declarations(&mut assembly, class);
    }
    let mut instructions = 0;
    for index in &order {
        let (text, count) = emit_function(class, *index)?;
        assembly.push_str(&text);
        instructions += count;
    }
    append_shared_kernels(&mut assembly);
    assembly.push_str("END\n");
    Ok(Compiled {
        assembly,
        signature: Signature::parse(&method.descriptor)?,
        instructions,
        linked_methods: order.len(),
        requires_heap,
        object_layout: if requires_heap {
            Some(ObjectLayout {
                abi: 1,
                payload_bytes: class.field_info.len() * 8,
                reference_prefix_fields: class
                    .field_info
                    .iter()
                    .filter(|f| field_type(&f.descriptor).is_ok_and(|t| t.is_reference()))
                    .count(),
                fields: class
                    .field_info
                    .iter()
                    .enumerate()
                    .map(|(index, f)| {
                        Ok(FieldLayout {
                            name: f.name.clone(),
                            descriptor: f.descriptor.clone(),
                            offset: field_offset(class, index)?,
                            declaring_class: None,
                            declaring_field: None,
                            storage_bytes: None,
                        })
                    })
                    .collect::<Result<_>>()?,
            })
        } else {
            None
        },
    })
}

pub(super) const FLOATING_REMAINDER_ASSEMBLY: &str =
    include_str!("../../native/kernels/floating_remainder.inc");
fn asm_comment(text: &str) -> String {
    let text = text.replace(['\r', '\n'], " ");
    let chars = text.chars().collect::<Vec<_>>();
    chars
        .chunks(100)
        .map(|part| format!("; {}", part.iter().collect::<String>()))
        .collect::<Vec<_>>()
        .join("\n")
}
pub(super) fn shared_numeric_module() -> String {
    let header = module_header(0);
    let data = header.split(".code").next().unwrap();
    format!(
        "{data}\nPUBLIC boom_default_mxcsr\nPUBLIC boom_f32_i32_hi,boom_f32_i32_lo,boom_f32_i64_hi,boom_f32_i64_lo\nPUBLIC boom_f64_i32_hi,boom_f64_i32_lo,boom_f64_i64_hi,boom_f64_i64_lo\n{FLOATING_REMAINDER_ASSEMBLY}\n"
    )
}
pub(super) fn append_shared_kernels(assembly: &mut String) {
    if assembly.contains("call boom_frem") && !assembly.contains("boom_frem64 PROC") {
        assembly.push('\n');
        assembly.push_str(FLOATING_REMAINDER_ASSEMBLY);
        assembly.push('\n');
    }
}

pub(super) fn module_header(root: usize) -> String {
    let mut assembly = String::from(
        "; Boom numeric-v1: JVM bytecode -> typed verifier -> x86-64 MASM.\noption casemap:none\n.const\nALIGN 8\nboom_default_mxcsr DWORD 01F80h\nboom_f32_i32_hi DWORD 04F000000h\nboom_f32_i32_lo DWORD 0CF000000h\nboom_f32_i64_hi DWORD 05F000000h\nboom_f32_i64_lo DWORD 0DF000000h\nALIGN 8\nboom_f64_i32_hi QWORD 041E0000000000000h\nboom_f64_i32_lo QWORD 0C1E0000000000000h\nboom_f64_i64_hi QWORD 043E0000000000000h\nboom_f64_i64_lo QWORD 0C3E0000000000000h\n.code\nPUBLIC boom_entry\nboom_entry PROC FRAME\n    sub rsp, 40\n    .allocstack 40\n    .endprolog\n    mov DWORD PTR [rcx+12], 0\n    stmxcsr DWORD PTR [rsp+32]\n    ldmxcsr DWORD PTR [boom_default_mxcsr]\n",
    );
    assembly.push_str(&format!("    call boom_m{root}\n    ldmxcsr DWORD PTR [rsp+32]\n    add rsp, 40\n    ret\nboom_entry ENDP\n"));
    assembly
}

pub(super) fn module_header32(root: usize) -> String {
    let old = module_header(root);
    let prefix = old.split("PUBLIC boom_entry").next().unwrap();
    format!(
        "{prefix}EXTERN boom_exception_prepare:PROC\nPUBLIC boom_entry\nPUBLIC boom_entry32\nboom_entry PROC FRAME\n    sub rsp, 104\n    .allocstack 104\n    .endprolog\n    mov QWORD PTR [rsp+48], rcx\n    mov QWORD PTR [rsp+56], rdx\n    mov rax, QWORD PTR [rcx]\n    mov QWORD PTR [rsp+64], rax\n    mov eax, DWORD PTR [rcx+8]\n    mov QWORD PTR [rsp+72], rax\n    mov QWORD PTR [rsp+80], 0\n    mov QWORD PTR [rsp+88], 0\n    lea rcx, [rsp+64]\n    call boom_entry32\n    mov rdx, QWORD PTR [rsp+48]\n    mov r10, QWORD PTR [rsp+64]\n    mov QWORD PTR [rdx], r10\n    mov r10, QWORD PTR [rsp+72]\n    mov QWORD PTR [rdx+8], r10\n    cmp DWORD PTR [rsp+64], 16\n    jne boom_entry_bridge_done\n    mov rax, QWORD PTR [rsp+80]\nboom_entry_bridge_done:\n    add rsp, 104\n    ret\nboom_entry ENDP\nboom_entry32 PROC FRAME\n    sub rsp, 72\n    .allocstack 72\n    .endprolog\n    mov QWORD PTR [rsp+48], rcx\n    mov QWORD PTR [rsp+56], rdx\n    stmxcsr DWORD PTR [rsp+64]\n    ldmxcsr DWORD PTR [boom_default_mxcsr]\n    lea rdx, boom_exception_vm\n    mov QWORD PTR [rcx+24], rdx\n    call boom_exception_prepare\n    test eax, eax\n    jnz boom_entry32_failed\n    mov rcx, QWORD PTR [rsp+48]\n    mov rdx, QWORD PTR [rsp+56]\n    call boom_m{root}\n    jmp boom_entry32_done\nboom_entry32_failed:\n    xor eax, eax\nboom_entry32_done:\n    ldmxcsr DWORD PTR [rsp+64]\n    add rsp, 72\n    ret\nboom_entry32 ENDP\n"
    )
}

pub(super) fn append_heap_declarations(assembly: &mut String, class: &ClassFile) {
    append_heap_declarations_with_policy(assembly, class, false);
}
pub(super) fn append_heap_declarations_with_policy(
    assembly: &mut String,
    class: &ClassFile,
    single_binding: bool,
) {
    assembly.push_str("EXTERN boom_reference_array_new:PROC\nEXTERN boom_reference_array_length:PROC\nEXTERN boom_reference_array_load:PROC\nEXTERN boom_reference_array_store:PROC\n.const\nALIGN 8\nboom_reference_array_layout DWORD 052454641h, 1\n    QWORD OFFSET boom_class_layout\n.code\n");
    let refs = class
        .field_info
        .iter()
        .filter(|field| field_type(&field.descriptor).is_ok_and(|ty| ty.is_reference()))
        .count();
    assembly.push_str(&format!("EXTERN boom_object_new:PROC\nEXTERN boom_object_check:PROC\n.const\nALIGN 8\nboom_class_layout DWORD 04F424A43h, 1\n    QWORD {}\n    DWORD {refs}, {}\n.code\n", class.field_info.len() * 8, class.field_info.len()));
    append_common_heap(assembly, single_binding);
}

pub(super) fn append_program_heap(
    assembly: &mut String,
    layouts: &[super::program::ProgramObjectLayout],
    entry: usize,
) -> Result<()> {
    assembly.push_str("EXTERN boom_reference_array_new:PROC\nEXTERN boom_reference_array_length:PROC\nEXTERN boom_reference_array_load:PROC\nEXTERN boom_reference_array_store:PROC\nEXTERN boom_object_new:PROC\nEXTERN boom_object_check:PROC\n.const\n");
    for layout in layouts {
        let owner = layout.class_id;
        let fields = layout.layout.fields.len();
        let refs = layout.layout.reference_prefix_fields;
        let bytes = layout.layout.payload_bytes;
        let abi = layout.layout.abi;
        assembly.push_str(&format!("ALIGN 8\nboom_layout{owner} DWORD 04F424A43h, {abi}\n    QWORD {bytes}\n    DWORD {refs}, {fields}\nALIGN 8\nboom_ref_layout{owner} DWORD 052454641h, 1\n    QWORD OFFSET boom_layout{owner}\n"));
    }
    // A definitely-null reference array is guaranteed to fail before reading this layout.
    assembly.push_str(&format!("ALIGN 8\nboom_reference_array_layout DWORD 052454641h, 1\n    QWORD OFFSET boom_layout{entry}\n.code\n"));
    append_common_heap(assembly, true);
    Ok(())
}

fn append_common_heap(assembly: &mut String, single_binding: bool) {
    assembly.push_str("EXTERN boom_array_new:PROC\nEXTERN boom_array_length:PROC\nEXTERN boom_array_load:PROC\nEXTERN boom_array_store:PROC\n.data\nALIGN 8\nboom_heap_ptr QWORD 0\n.code\nPUBLIC boom_bind_heap\nboom_bind_heap PROC\n    xor eax, eax\n    test rcx, rcx\n    jz boom_bind_done\n    cmp DWORD PTR [rcx], 048454150h\n    jne boom_bind_done\n    cmp DWORD PTR [rcx+4], 1\n    jne boom_bind_done\n");
    if single_binding {
        assembly.push_str("    mov rax, QWORD PTR [boom_heap_ptr]\n    test rax, rax\n    jz boom_bind_set\n    cmp rax, rcx\n    jne boom_bind_reject\nboom_bind_set:\n");
    }
    assembly.push_str(
        "    mov QWORD PTR [boom_heap_ptr], rcx\n    mov eax, 1\nboom_bind_done:\n    ret\n",
    );
    if single_binding {
        assembly.push_str("boom_bind_reject:\n    xor eax, eax\n    ret\n");
    }
    assembly.push_str("boom_bind_heap ENDP\n");
}

pub(super) struct Dependencies {
    pub calls: Vec<usize>,
    pub classes: BTreeSet<usize>,
    pub heap: bool,
    pub strings: bool,
    pub dynamic_strings: bool,
    pub volatile_accesses: bool,
}
pub(super) fn validate_linked(
    class: &ClassFile,
    method: &Method,
    links: &dyn StaticLinker,
) -> Result<()> {
    let signature = links.signature(class, method)?;
    let code = method.code.as_ref().context("Missing linked Code")?;
    let instructions = decode_with_links(code, class, Some(links))?;
    let exceptions = exception_types(class, code, &instructions, Some(links))?;
    verify_method_with_links(
        &instructions,
        code,
        &signature,
        method.name == "<init>" && !links.root_object_constructor(class)?,
        Some(links),
        exceptions.as_ref(),
    )?;
    Ok(())
}
pub(super) fn linked_dependencies(
    class: &ClassFile,
    method: &Method,
    links: &dyn StaticLinker,
) -> Result<Dependencies> {
    links.exception_method(class, method)?;
    links.method_monitor(class, method)?;
    let signature = links.signature(class, method)?;
    ensure!(
        signature
            .arguments
            .iter()
            .chain(std::iter::once(&signature.result))
            .all(|ty| matches!(
                ty,
                Type::I32
                    | Type::I64
                    | Type::F32
                    | Type::F64
                    | Type::Array(_)
                    | Type::LinkedObject(_)
                    | Type::LinkedObjectArray(_)
                    | Type::BootstrapString
                    | Type::BootstrapStringArray
                    | Type::BootstrapClass
                    | Type::BootstrapClassArray
                    | Type::MetadataReference(_)
                    | Type::Void
            )),
        "Linked program requires numeric values or identified reference types"
    );
    let instructions = decode_with_links(
        method.code.as_ref().context("Missing linked method Code")?,
        class,
        Some(links),
    )?;
    // Resolve the array ABI during dependency discovery, before type-map layout.
    links.covariant_arrays();
    let mut calls = Vec::new();
    let mut heap = method.access & 0x20 != 0
        || signature
            .arguments
            .iter()
            .chain(std::iter::once(&signature.result))
            .any(|ty| ty.is_reference());
    let mut classes = BTreeSet::from([links.class_id(class)?]);
    let mut strings = signature
        .arguments
        .iter()
        .chain(std::iter::once(&signature.result))
        .any(|ty| {
            matches!(
                ty,
                Type::BootstrapString
                    | Type::BootstrapStringArray
                    | Type::BootstrapClass
                    | Type::BootstrapClassArray
            )
        });
    let mut dynamic_strings = false;
    let mut volatile_accesses = false;
    for instruction in instructions {
        match instruction.op {
            Op::RuntimeResource(_, _)
            | Op::Monitor(_)
            | Op::MonitorNotify(_, _)
            | Op::NpeMessage(_)
            | Op::ThrowableFill(_) => {
                heap = true;
                strings = true;
            }
            Op::AccessContext(_, _, owner)
            | Op::UnsafeNative(_, _, owner)
            | Op::ShutdownNative(_, _, owner)
            | Op::ThreadNative(_, owner) => {
                heap = true;
                strings = true;
                classes.insert(owner);
            }
            Op::SignalFind(owner) | Op::SignalControl(_, owner) => {
                heap = true;
                strings = true;
                dynamic_strings = true;
                classes.insert(owner);
            }
            Op::WinFsInit(owner, file) => {
                heap = true;
                strings = true;
                classes.extend([owner, file]);
            }
            Op::VmNative(_, owner)
            | Op::ReflectArray(_, _, owner)
            | Op::ClassLoaderRegister(owner)
            | Op::ScopedRegister(owner)
            | Op::WindowsErrorMode(owner)
            | Op::StreamInit(owner)
            | Op::ConstantClassInitialization(owner) => {
                heap = true;
                strings = true;
                classes.insert(owner);
            }
            Op::FileDescriptor(_, owner) => {
                heap = true;
                strings = true;
                classes.insert(owner);
            }
            Op::Cds(_, owner) => {
                heap = true;
                strings = true;
                classes.insert(owner);
            }
            Op::StringJoin(_, _, targets, owners) => {
                heap = true;
                strings = true;
                dynamic_strings = true;
                calls.extend(targets);
                classes.extend(owners);
            }
            Op::VmIntrinsic(
                super::vm::Operation::ArrayCopy | super::vm::Operation::RegisterNatives,
            ) => {
                heap = true;
                strings = true;
            }
            Op::ResourceStream(_, _, owner, constructor) => {
                heap = true;
                strings = true;
                classes.insert(owner);
                calls.push(constructor);
            }
            Op::ModuleIntrinsic(_, _, factory) => {
                heap = true;
                strings = true;
                if let Some(factory) = factory {
                    calls.push(factory);
                }
            }
            Op::CheckCast(_, _) | Op::InstanceOf(_) | Op::GetClass => heap = true,
            Op::Concat(_, _, owner) => {
                heap = true;
                strings = true;
                dynamic_strings = true;
                classes.extend(owner);
            }
            Op::Bitcast(_, owner) => {
                heap = true;
                strings = true;
                classes.insert(owner);
            }
            Op::BuilderSnapshot(_, owner) => {
                heap = true;
                strings = true;
                dynamic_strings = true;
                classes.insert(owner);
            }
            Op::HexString(_, _, owner) => {
                heap = true;
                strings = true;
                dynamic_strings = true;
                classes.insert(owner);
            }
            Op::SystemStream(_, _, owner) => {
                heap = true;
                classes.insert(owner);
            }
            Op::ArrayClone(_, _) | Op::IdentityHash(_, _) => {
                heap = true;
                strings = true;
            }
            Op::StringConcatApi(_)
            | Op::StringReplace(_)
            | Op::LiteralRegexReplace(_, _, _)
            | Op::StringChars(_)
            | Op::StringLowercase(_)
            | Op::StringSplit(_)
            | Op::ReflectNew(_, _)
            | Op::ReflectConstructor(_, _, _)
            | Op::ReflectField(_, _)
            | Op::ClassForName(_, _)
            | Op::NewString
            | Op::InitializeString(_)
            | Op::StringPrefix(_) => {
                heap = true;
                strings = true;
                dynamic_strings = true;
            }
            Op::RawProperties(_, _, owner) => {
                heap = true;
                strings = true;
                dynamic_strings = true;
                classes.insert(owner);
            }
            Op::StringGetChars(_) => {
                heap = true;
                strings = true;
                dynamic_strings = true;
            }
            Op::StringIntrinsic(operation, _) => {
                heap = true;
                strings = true;
                dynamic_strings |= matches!(
                    operation,
                    StringIntrinsic::Substring
                        | StringIntrinsic::SubstringRange
                        | StringIntrinsic::Trim
                );
            }
            Op::StringLiteral(_)
            | Op::BooleanString(_)
            | Op::NewStringArray
            | Op::ClassLiteral(_)
            | Op::ClassLoaderField(_)
            | Op::ClassValueField(_, _)
            | Op::PrimitiveClass(_)
            | Op::NewClassArray => {
                heap = true;
                strings = true;
            }
            Op::ClassIntrinsic(operation, _) => {
                heap = true;
                strings = true;
                dynamic_strings |= matches!(
                    operation,
                    ClassIntrinsic::CanonicalName | ClassIntrinsic::SimpleName
                );
            }
            Op::Call(target, _)
            | Op::BridgeCall(target, _)
            | Op::InstanceCall(target, _)
            | Op::ProtectedInitialize(target, _, _)
            | Op::Initialize(Some(target), _) => calls.push(target),
            Op::InterfaceCall(_, _, targets, owners) => {
                heap = true;
                calls.extend(targets);
                classes.extend(owners);
            }
            Op::StaticLoad(field) | Op::StaticStore(field) => {
                volatile_accesses |= field.access & 0x40 != 0;
                strings |= matches!(
                    field.ty,
                    Type::BootstrapString
                        | Type::BootstrapStringArray
                        | Type::BootstrapClass
                        | Type::BootstrapClassArray
                );
                classes.insert(field.owner);
                if matches!(instruction.op, Op::StaticStore(_)) && field.access & 0x10 != 0 {
                    ensure!(
                        method.name == "<clinit>" && field.owner == links.class_id(class)?,
                        "Final static fields may only be assigned by their declaring class initializer"
                    );
                }
            }
            Op::NewTypedArray(_, _, _) => {
                heap = true;
                strings = true;
            }
            Op::NewArray(_) | Op::ArrayLength | Op::ArrayLoad(_) | Op::ArrayStore(_) => heap = true,
            Op::NewLinkedObject(owner) | Op::NewLinkedReferenceArray(owner) => {
                classes.insert(owner);
                heap = true;
            }
            Op::LinkedFieldLoad(field) | Op::LinkedFieldStore(field) => {
                volatile_accesses |= field.access & 0x40 != 0;
                strings |= matches!(
                    field.ty,
                    Type::BootstrapString
                        | Type::BootstrapStringArray
                        | Type::BootstrapClass
                        | Type::BootstrapClassArray
                );
                classes.extend(links.field_receivers(&field)?);
                classes.insert(field.owner);
                heap = true;
                if matches!(instruction.op, Op::LinkedFieldStore(_)) && field.access & 0x10 != 0 {
                    ensure!(
                        method.name == "<init>" && field.owner == links.class_id(class)?,
                        "Final instance field {} may only be assigned by its declaring constructor",
                        field.index
                    );
                }
            }
            Op::ReferenceArrayLoad | Op::ReferenceArrayStore => heap = true,
            Op::Initialize(None, _) => (),
            Op::NewObject | Op::FieldLoad(_, _) | Op::FieldStore(_, _) | Op::NewReferenceArray => {
                bail!("Object linkage is not implemented in static program mode")
            }
            _ => (),
        }
    }
    Ok(Dependencies {
        calls,
        classes,
        heap,
        strings,
        dynamic_strings,
        volatile_accesses,
    })
}

#[cfg(test)]
mod tests {
    #[test]
    fn vm_string_construction_preserves_aliases_and_invalidates_failed_receiver_locals() {
        use super::*;
        let uninitialized_return = [
            Instruction {
                pc: 0,
                next: 1,
                op: Op::NewString,
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Return(Type::AnyRef),
            },
        ];
        assert!(
            verify(
                &uninitialized_return,
                &Code {
                    max_stack: 1,
                    max_locals: 0,
                    bytes: vec![0; 2],
                    handlers: vec![]
                },
                &Signature {
                    arguments: vec![],
                    result: Type::BootstrapString
                }
            )
            .is_err()
        );
        let code = Code {
            max_stack: 4,
            max_locals: 2,
            bytes: vec![0; 11],
            handlers: vec![exception_handler(6, 7, 8)],
        };
        let exceptions = ExceptionTypes {
            throwable: Type::MetadataReference(7),
            catches: vec![Type::MetadataReference(7)],
        };
        let signature = Signature {
            arguments: vec![],
            result: Type::Void,
        };
        let operations = vec![
            Op::NewString,
            Op::Dup,
            Op::Store(Type::AnyRef, 0),
            Op::Constant(Type::Null, 0),
            Op::Constant(Type::I32, 0),
            Op::Constant(Type::I32, 0),
            Op::InitializeString(super::super::string_construction::signature(
                super::super::string_construction::DESCRIPTOR,
            )),
            Op::Return(Type::Void),
            Op::Store(Type::AnyRef, 1),
            Op::Load(Type::AnyRef, 1),
            Op::Throw,
        ];
        let mut instructions: Vec<_> = operations
            .into_iter()
            .enumerate()
            .map(|(pc, op)| Instruction {
                pc,
                next: pc + 1,
                op,
            })
            .collect();
        let frames = verify_method_with_links(
            &instructions,
            &code,
            &signature,
            false,
            None,
            Some(&exceptions),
        )
        .unwrap();
        assert_eq!(
            frames[&7].locals[0],
            Some(Local::Value(Type::BootstrapString))
        );
        assert_eq!(frames[&8].locals[0], None);
        instructions[9].op = Op::Load(Type::AnyRef, 0);
        assert!(
            verify_method_with_links(
                &instructions,
                &code,
                &signature,
                false,
                None,
                Some(&exceptions)
            )
            .is_err()
        );
        instructions[9].op = Op::Load(Type::AnyRef, 1);
        instructions[0].op = Op::NewObject;
        assert!(
            verify_method_with_links(
                &instructions,
                &code,
                &signature,
                false,
                None,
                Some(&exceptions)
            )
            .is_err()
        );
    }
    #[test]
    fn nested_descriptors_retain_rank_and_element_identity() {
        let mut names = Vec::new();
        let signature =
            Signature::parse_with("(I[[I[[[Ljava/lang/String;[BJ)[[D", &mut |name, array| {
                assert!(!array);
                let id = names.len();
                names.push(name.to_owned());
                Ok(Type::MetadataReference(id))
            })
            .unwrap();
        assert_eq!(names, vec!["[[I", "[[[Ljava/lang/String;", "[[D"]);
        assert_eq!(
            signature.arguments,
            vec![
                Type::I32,
                Type::MetadataReference(0),
                Type::MetadataReference(1),
                Type::Array(ArrayKind::Byte),
                Type::I64
            ]
        );
        assert_eq!(signature.result, Type::MetadataReference(2));
        for descriptor in [
            "()[[V",
            "()[[L;",
            "()[[Ljava/lang/Object",
            "()[[[",
            "()[[IX",
        ] {
            assert!(
                Signature::parse_with(descriptor, &mut |_, _| Ok(Type::AnyRef)).is_err(),
                "{descriptor}"
            );
        }
        let valid = format!("(){}I", "[".repeat(255));
        assert!(Signature::parse_with(&valid, &mut |_, _| Ok(Type::AnyRef)).is_ok());
        let invalid = format!("(){}I", "[".repeat(256));
        assert!(Signature::parse_with(&invalid, &mut |_, _| Ok(Type::AnyRef)).is_err());
        assert!(Signature::parse("()[[I").is_err());
    }
    #[test]
    fn erased_object_constructor_keeps_allocation_and_direct_parent_rules() {
        use super::*;
        struct Parents;
        impl StaticLinker for Parents {
            fn resolve(&self, _: &ClassFile, _: u16) -> Result<(usize, Signature)> {
                unreachable!()
            }
            fn root_object_allocation(&self, owner: usize) -> Result<bool> {
                Ok(owner == 0)
            }
            fn direct_object_parent(&self, owner: usize) -> Result<bool> {
                Ok(owner == 2)
            }
        }
        let mut code = Code {
            max_stack: 2,
            max_locals: 0,
            bytes: vec![0; 3],
            handlers: vec![],
        };
        let mut ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::NewLinkedObject(0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Initialize(
                    None,
                    Signature {
                        arguments: vec![Type::LinkedObject(2)],
                        result: Type::Void,
                    },
                ),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Return(Type::Void),
            },
        ];
        let signature = Signature {
            arguments: vec![],
            result: Type::Void,
        };
        assert!(
            verify_method_with_links(&ops, &code, &signature, false, Some(&Parents), None).is_ok()
        );
        ops[0].op = Op::NewLinkedObject(1);
        assert!(
            verify_method_with_links(&ops, &code, &signature, false, Some(&Parents), None).is_err()
        );
        code.max_locals = 1;
        ops[0].op = Op::Load(Type::AnyRef, 0);
        let signature = Signature {
            arguments: vec![Type::LinkedObject(2)],
            result: Type::Void,
        };
        assert!(
            verify_method_with_links(&ops, &code, &signature, true, Some(&Parents), None).is_ok()
        );
        let signature = Signature {
            arguments: vec![Type::LinkedObject(3)],
            result: Type::Void,
        };
        assert!(
            verify_method_with_links(&ops, &code, &signature, true, Some(&Parents), None).is_err()
        );
    }
    use super::*;
    fn exception_handler(
        start: u16,
        end: u16,
        target: u16,
    ) -> super::super::classfile::ExceptionHandler {
        super::super::classfile::ExceptionHandler {
            start_pc: start,
            end_pc: end,
            handler_pc: target,
            catch_type: None,
        }
    }
    #[test]
    fn exception_edges_use_pre_instruction_locals_and_replace_the_stack() {
        let mut code = Code {
            max_stack: 2,
            max_locals: 2,
            bytes: vec![0; 6],
            handlers: vec![exception_handler(1, 4, 4)],
        };
        let ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Constant(Type::I32, 1),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Store(Type::I32, 0),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Return(Type::Void),
            },
            Instruction {
                pc: 4,
                next: 5,
                op: Op::Store(Type::AnyRef, 1),
            },
            Instruction {
                pc: 5,
                next: 6,
                op: Op::Return(Type::Void),
            },
        ];
        let types = ExceptionTypes {
            throwable: Type::MetadataReference(7),
            catches: vec![Type::MetadataReference(7)],
        };
        let signature = Signature {
            arguments: vec![],
            result: Type::Void,
        };
        let frames =
            verify_method_with_links(&ops, &code, &signature, false, None, Some(&types)).unwrap();
        assert_eq!(frames[&4].stack, vec![Type::MetadataReference(7)]);
        assert_eq!(frames[&4].locals[0], None); // store at pc1 has not completed on its exceptional edge.
        assert_eq!(
            frames[&5].locals[1],
            Some(Local::Value(Type::MetadataReference(7)))
        );
        code.handlers[0].start_pc = 0;
        code.handlers[0].end_pc = 1;
        assert!(
            verify_method_with_links(&ops, &code, &signature, false, None, Some(&types)).is_ok()
        );
        code.handlers[0].handler_pc = 3;
        assert!(
            verify_method_with_links(&ops, &code, &signature, false, None, Some(&types)).is_err()
        );
        code.handlers[0].handler_pc = 4;
        code.max_stack = 0;
        assert!(
            verify_method_with_links(&ops, &code, &signature, false, None, Some(&types)).is_err()
        );
    }
    #[test]
    fn athrow_requires_initialized_throwable_and_has_no_fallthrough() {
        let code = Code {
            max_stack: 2,
            max_locals: 1,
            bytes: vec![0; 3],
            handlers: Vec::new(),
        };
        let types = ExceptionTypes {
            throwable: Type::MetadataReference(7),
            catches: vec![],
        };
        let mut ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Constant(Type::I32, 12),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Constant(Type::Null, 0),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Throw,
            },
        ];
        let signature = Signature {
            arguments: vec![],
            result: Type::Void,
        };
        assert!(
            verify_method_with_links(&ops, &code, &signature, false, None, Some(&types)).is_ok()
        );
        for ty in [
            Type::I32,
            Type::BootstrapString,
            Type::Uninitialized(1),
            Type::UninitializedLinked(1, 2),
        ] {
            ops[1].op = Op::Constant(ty, 0);
            assert!(
                verify_method_with_links(&ops, &code, &signature, false, None, Some(&types))
                    .is_err(),
                "{ty:?}"
            );
        }
        ops[1].op = Op::Constant(Type::MetadataReference(7), 0);
        assert!(
            verify_method_with_links(&ops, &code, &signature, false, None, Some(&types)).is_ok()
        );
        assert!(verify_method_with_links(&ops, &code, &signature, false, None, None).is_err());
    }
    #[test]
    fn failed_constructor_receiver_is_unusable_in_its_handler() {
        let code = Code {
            max_stack: 2,
            max_locals: 2,
            bytes: vec![0; 9],
            handlers: vec![exception_handler(4, 5, 6)],
        };
        let types = ExceptionTypes {
            throwable: Type::MetadataReference(7),
            catches: vec![Type::MetadataReference(7)],
        };
        let signature = Signature {
            arguments: vec![],
            result: Type::Void,
        };
        let mut ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::NewObject,
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Dup,
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Store(Type::AnyRef, 0),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::Nop,
            },
            Instruction {
                pc: 4,
                next: 5,
                op: Op::Initialize(
                    Some(0),
                    Signature {
                        arguments: vec![Type::Object],
                        result: Type::Void,
                    },
                ),
            },
            Instruction {
                pc: 5,
                next: 6,
                op: Op::Return(Type::Void),
            },
            Instruction {
                pc: 6,
                next: 7,
                op: Op::Store(Type::AnyRef, 1),
            },
            Instruction {
                pc: 7,
                next: 8,
                op: Op::Load(Type::AnyRef, 1),
            },
            Instruction {
                pc: 8,
                next: 9,
                op: Op::Throw,
            },
        ];
        let frames =
            verify_method_with_links(&ops, &code, &signature, false, None, Some(&types)).unwrap();
        assert_eq!(frames[&6].locals[0], None);
        ops[7].op = Op::Load(Type::AnyRef, 0);
        assert!(
            verify_method_with_links(&ops, &code, &signature, false, None, Some(&types)).is_err()
        );
        // A constructor's own flagThisUninit survives its failed super constructor.
        let mut constructor_code = Code {
            max_stack: 1,
            max_locals: 2,
            bytes: vec![0; 6],
            handlers: vec![exception_handler(1, 2, 3)],
        };
        let constructor_signature = Signature {
            arguments: vec![Type::Object],
            result: Type::Void,
        };
        let constructor_ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Load(Type::AnyRef, 0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Initialize(
                    None,
                    Signature {
                        arguments: vec![Type::Object],
                        result: Type::Void,
                    },
                ),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Return(Type::Void),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::Store(Type::AnyRef, 1),
            },
            Instruction {
                pc: 4,
                next: 5,
                op: Op::Load(Type::AnyRef, 1),
            },
            Instruction {
                pc: 5,
                next: 6,
                op: Op::Throw,
            },
        ];
        assert!(
            verify_method_with_links(
                &constructor_ops,
                &constructor_code,
                &constructor_signature,
                true,
                None,
                Some(&types)
            )
            .is_ok()
        );
        constructor_code.handlers[0].end_pc = 3;
        let mut invalid = constructor_ops;
        invalid[4].op = Op::Return(Type::Void);
        assert!(
            verify_method_with_links(
                &invalid,
                &constructor_code,
                &constructor_signature,
                true,
                None,
                Some(&types)
            )
            .is_err()
        );
    }
    #[test]
    fn reference_checks_keep_pointer_width_and_reject_uninitialized_values() {
        let code = Code {
            max_stack: 1,
            max_locals: 0,
            bytes: vec![0; 4],
            handlers: Vec::new(),
        };
        let mut instructions = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Constant(Type::Null, 0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::CheckCast(4, Type::MetadataReference(4)),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::InstanceOf(5),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::Return(Type::I32),
            },
        ];
        let signature = Signature {
            arguments: vec![],
            result: Type::I32,
        };
        let frames = verify(&instructions, &code, &signature).unwrap();
        assert_eq!(frames[&2].stack, vec![Type::MetadataReference(4)]);
        assert!(Type::MetadataReference(4).bits64());
        instructions[0].op = Op::Constant(Type::I32, 0);
        assert!(verify(&instructions, &code, &signature).is_err());
        instructions[0].op = Op::NewLinkedObject(0);
        assert!(verify(&instructions, &code, &signature).is_err());
    }
    #[test]
    fn linked_uninitialized_identity_cannot_cross_a_backward_edge() {
        let code = Code {
            max_stack: 1,
            max_locals: 1,
            bytes: vec![0; 3],
            handlers: Vec::new(),
        };
        let instructions = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::NewLinkedObject(0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Store(Type::AnyRef, 0),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Goto(0),
            },
        ];
        assert!(
            verify(
                &instructions,
                &code,
                &Signature {
                    arguments: vec![],
                    result: Type::Void
                }
            )
            .is_err()
        );
    }
    #[test]
    fn bootstrap_class_calls_keep_distinct_receiver_and_argument_types() {
        let (_, sig) = ClassIntrinsic::resolve("isAssignableFrom", "(Ljava/lang/Class;)Z").unwrap();
        assert_eq!(
            sig.arguments,
            vec![Type::BootstrapClass, Type::BootstrapClass]
        );
        assert_eq!(sig.result, Type::I32);
        assert!(ClassIntrinsic::resolve("getName", "()Ljava/lang/Object;").is_err());
        assert!(
            ClassIntrinsic::resolve("getDeclaredMethods", "()[Ljava/lang/reflect/Method;").is_err()
        );
        assert!(Type::BootstrapClass.is_reference());
        assert_ne!(Type::BootstrapClass, Type::BootstrapString);
    }
    #[test]
    fn linked_constructor_and_return_preserve_exact_allocation_identity() {
        let code = Code {
            max_stack: 2,
            max_locals: 0,
            bytes: vec![0; 4],
            handlers: Vec::new(),
        };
        let signature = Signature {
            arguments: vec![],
            result: Type::LinkedObject(3),
        };
        let constructor = Signature {
            arguments: vec![Type::LinkedObject(3)],
            result: Type::Void,
        };
        let mut ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::NewLinkedObject(3),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Dup,
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Initialize(Some(0), constructor.clone()),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::Return(Type::AnyRef),
            },
        ];
        assert!(verify(&ops, &code, &signature).is_ok());
        let mut wrong = constructor;
        wrong.arguments[0] = Type::LinkedObject(7);
        ops[2].op = Op::Initialize(Some(0), wrong);
        assert!(verify(&ops, &code, &signature).is_err());
        ops[2].op = Op::Nop;
        assert!(verify(&ops, &code, &signature).is_err());
    }
    #[test]
    fn linked_array_stores_do_not_erase_distinct_component_classes() {
        let code = Code {
            max_stack: 3,
            max_locals: 2,
            bytes: vec![0; 5],
            handlers: Vec::new(),
        };
        let mut signature = Signature {
            arguments: vec![Type::LinkedObjectArray(3), Type::LinkedObject(3)],
            result: Type::Void,
        };
        let ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Load(Type::AnyRef, 0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Constant(Type::I32, 0),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Load(Type::AnyRef, 1),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::ReferenceArrayStore,
            },
            Instruction {
                pc: 4,
                next: 5,
                op: Op::Return(Type::Void),
            },
        ];
        assert!(verify(&ops, &code, &signature).is_ok());
        signature.arguments[1] = Type::LinkedObject(7);
        assert!(verify(&ops, &code, &signature).is_err());
        signature.arguments[1] = Type::UninitializedLinked(0, 3);
        assert!(verify(&ops, &code, &signature).is_err());
        signature.arguments = vec![Type::BootstrapStringArray, Type::LinkedObject(3)];
        assert!(verify(&ops, &code, &signature).is_err());
        signature.arguments[1] = Type::BootstrapString;
        assert!(verify(&ops, &code, &signature).is_ok());
        signature.arguments = vec![Type::BootstrapClassArray, Type::BootstrapString];
        assert!(verify(&ops, &code, &signature).is_err());
        signature.arguments[1] = Type::BootstrapClass;
        assert!(verify(&ops, &code, &signature).is_ok());
    }
    #[test]
    fn constructor_initialization_is_verified_before_use_and_return() {
        let code = Code {
            max_stack: 2,
            max_locals: 1,
            bytes: vec![0; 3],
            handlers: Vec::new(),
        };
        let signature = Signature {
            arguments: vec![Type::Object],
            result: Type::Void,
        };
        let mut ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Load(Type::AnyRef, 0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Initialize(None, signature.clone()),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Return(Type::Void),
            },
        ];
        assert!(verify_method(&ops, &code, &signature, true).is_ok());
        ops[1].op = Op::FieldLoad(0, Type::I32);
        assert!(verify_method(&ops, &code, &signature, true).is_err());
        ops[0].op = Op::Nop;
        ops[1].op = Op::Nop;
        assert!(verify_method(&ops, &code, &signature, true).is_err());
    }
    #[test]
    fn new_references_cannot_escape_before_constructor_completion() {
        let code = Code {
            max_stack: 1,
            max_locals: 0,
            bytes: vec![0; 2],
            handlers: Vec::new(),
        };
        let ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::NewObject,
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Return(Type::AnyRef),
            },
        ];
        assert!(
            verify(
                &ops,
                &code,
                &Signature {
                    arguments: vec![],
                    result: Type::Object
                }
            )
            .is_err()
        );
    }
    #[test]
    fn reference_array_stores_require_initialized_component_objects() {
        let code = Code {
            max_stack: 3,
            max_locals: 3,
            bytes: vec![0; 5],
            handlers: Vec::new(),
        };
        let ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Load(Type::AnyRef, 0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Load(Type::I32, 1),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Load(Type::AnyRef, 2),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::ReferenceArrayStore,
            },
            Instruction {
                pc: 4,
                next: 5,
                op: Op::Return(Type::Void),
            },
        ];
        let mut sig = Signature {
            arguments: vec![Type::ObjectArray, Type::I32, Type::ObjectArray],
            result: Type::Void,
        };
        assert!(verify(&ops, &code, &sig).is_err());
        sig.arguments[2] = Type::Object;
        assert!(verify(&ops, &code, &sig).is_ok());
        assert_eq!(
            Signature::parse("([Ltest/Cell;)[Ltest/Cell;")
                .unwrap()
                .result,
            Type::ObjectArray
        );
    }
    #[test]
    fn dup_insertions_respect_all_category_two_shapes() {
        assert_eq!(
            stack_reorder(0x5b, &[Type::I64, Type::Object]).unwrap(),
            (2, vec![1, 0, 1])
        );
        assert_eq!(
            stack_reorder(0x5e, &[Type::I64, Type::F64]).unwrap(),
            (2, vec![1, 0, 1])
        );
        assert_eq!(
            stack_reorder(0x5e, &[Type::I32, Type::I32, Type::F64]).unwrap(),
            (3, vec![2, 0, 1, 2])
        );
        assert_eq!(
            stack_reorder(0x5e, &[Type::F64, Type::Object, Type::I32]).unwrap(),
            (3, vec![1, 2, 0, 1, 2])
        );
        assert_eq!(
            stack_reorder(0x5e, &[Type::I32; 4]).unwrap(),
            (4, vec![2, 3, 0, 1, 2, 3])
        );
        assert!(stack_reorder(0x5a, &[Type::I64, Type::I32]).is_err());
        assert!(stack_reorder(0x5d, &[]).is_err());
    }
    #[test]
    fn descriptors_track_numeric_object_and_void_types() {
        assert_eq!(
            Signature::parse("(IJFD)D").unwrap().arguments,
            vec![Type::I32, Type::I64, Type::F32, Type::F64]
        );
        assert_eq!(
            Signature::parse("([I)[J").unwrap().arguments,
            vec![Type::Array(ArrayKind::Int)]
        );
        assert_eq!(
            Signature::parse("(Ljava/lang/Object;)V").unwrap().result,
            Type::Void
        );
        for d in ["(L;)I", "([[I)I", "(V)I", "(I)II"] {
            assert!(Signature::parse(d).is_err());
        }
    }
    #[test]
    fn parameter_limits_count_jvm_slots_including_the_receiver() {
        let ints = format!("({})V", "I".repeat(255));
        let mut max = Signature::parse(&ints).unwrap();
        max.check_arguments().unwrap();
        max.arguments.insert(0, Type::Object);
        assert!(max.check_arguments().is_err());
        assert!(Signature::parse(&format!("({})V", "I".repeat(256))).is_err());
        assert!(Signature::parse(&format!("({}I)V", "J".repeat(127))).is_ok());
        assert!(Signature::parse(&format!("({})V", "D".repeat(128))).is_err());
    }
    #[test]
    fn writing_a_wide_tail_invalidates_its_head() {
        let mut frame = Frame {
            locals: vec![None; 4],
            stack: vec![],
            this_initialized: true,
        };
        frame.store(0, Type::I64).unwrap();
        frame.store(1, Type::I32).unwrap();
        assert_eq!(frame.locals[0], None);
        assert_eq!(frame.locals[1], Some(Local::Value(Type::I32)));
    }
    #[test]
    fn array_references_use_one_jvm_slot_but_keep_all_pointer_bits() {
        assert_eq!(Type::Array(ArrayKind::Int).width(), 1);
        assert!(Type::Array(ArrayKind::Int).bits64());
    }
    #[test]
    fn integer_bits_cannot_be_used_as_array_references() {
        let code = Code {
            max_stack: 2,
            max_locals: 0,
            bytes: vec![0; 3],
            handlers: Vec::new(),
        };
        let mut instructions = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Constant(Type::I32, 0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::ArrayLength,
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Return(Type::I32),
            },
        ];
        assert!(verify(&instructions, &code, &Signature::parse("()I").unwrap()).is_err());
        instructions[0].op = Op::Constant(Type::Null, 0);
        assert!(verify(&instructions, &code, &Signature::parse("()I").unwrap()).is_ok());
    }
    #[test]
    fn null_and_array_paths_merge_without_erasing_element_type() {
        let code = Code {
            max_stack: 1,
            max_locals: 2,
            bytes: vec![0; 7],
            handlers: Vec::new(),
        };
        let mut instructions = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Load(Type::I32, 1),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::If(0, 4),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Load(Type::AnyRef, 0),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::Goto(5),
            },
            Instruction {
                pc: 4,
                next: 5,
                op: Op::Constant(Type::Null, 0),
            },
            Instruction {
                pc: 5,
                next: 6,
                op: Op::ArrayLength,
            },
            Instruction {
                pc: 6,
                next: 7,
                op: Op::Return(Type::I32),
            },
        ];
        let signature = Signature::parse("([II)I").unwrap();
        let frames = verify(&instructions, &code, &signature).unwrap();
        assert_eq!(frames[&5].stack, vec![Type::Array(ArrayKind::Int)]);
        instructions[4].op = Op::Constant(Type::F32, 0);
        assert!(verify(&instructions, &code, &signature).is_err());
    }
    #[test]
    fn array_loads_check_the_element_type() {
        let code = Code {
            max_stack: 2,
            max_locals: 1,
            bytes: vec![0; 4],
            handlers: Vec::new(),
        };
        let instructions = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Load(Type::AnyRef, 0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Constant(Type::I32, 0),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::ArrayLoad(ArrayKind::Int),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::Return(Type::I32),
            },
        ];
        assert!(verify(&instructions, &code, &Signature::parse("([F)I").unwrap()).is_err());
        assert!(verify(&instructions, &code, &Signature::parse("([I)I").unwrap()).is_ok());
    }
    #[test]
    fn returns_discard_lower_stack_values_but_check_the_return_value() {
        let code = Code {
            max_stack: 3,
            max_locals: 0,
            bytes: vec![0; 3],
            handlers: Vec::new(),
        };
        let mut instructions = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Constant(Type::I64, 17),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Constant(Type::I32, 23),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Return(Type::I32),
            },
        ];
        assert!(verify(&instructions, &code, &Signature::parse("()I").unwrap()).is_ok());
        instructions[2].op = Op::Return(Type::Void);
        assert!(verify(&instructions, &code, &Signature::parse("()V").unwrap()).is_ok());
        instructions[2].op = Op::Return(Type::I64);
        assert!(verify(&instructions, &code, &Signature::parse("()J").unwrap()).is_err());
        assert!(verify(&instructions[2..], &code, &Signature::parse("()J").unwrap()).is_err());
    }
    #[test]
    fn verifier_checks_category_units_and_merge_types() {
        let code = Code {
            max_stack: 1,
            max_locals: 0,
            bytes: vec![0; 2],
            handlers: Vec::new(),
        };
        let instructions = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Constant(Type::I64, 0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Return(Type::I64),
            },
        ];
        assert!(verify(&instructions, &code, &Signature::parse("()J").unwrap()).is_err());
        let mut code = code;
        code.max_stack = 2;
        assert!(verify(&instructions, &code, &Signature::parse("()J").unwrap()).is_ok());
        let mut wrong = instructions;
        wrong[1].op = Op::Return(Type::I32);
        assert!(verify(&wrong, &code, &Signature::parse("()J").unwrap()).is_err());
    }

    #[test]
    fn only_uninitialized_this_can_delegate_to_the_direct_super_constructor() {
        struct Parents;
        impl StaticLinker for Parents {
            fn resolve(&self, _: &ClassFile, _: u16) -> Result<(usize, Signature)> {
                bail!("No symbolic lookup in verifier test")
            }
            fn constructor_parent(&self, owner: usize, parent: usize) -> Result<bool> {
                Ok(owner == 3 && parent == 2)
            }
        }
        let code = Code {
            max_stack: 1,
            max_locals: 1,
            bytes: vec![0; 3],
            handlers: Vec::new(),
        };
        let signature = Signature {
            arguments: vec![Type::LinkedObject(3)],
            result: Type::Void,
        };
        let mut ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Load(Type::AnyRef, 0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::Initialize(
                    Some(0),
                    Signature {
                        arguments: vec![Type::LinkedObject(2)],
                        result: Type::Void,
                    },
                ),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Return(Type::Void),
            },
        ];
        assert!(
            verify_method_with_links(&ops, &code, &signature, true, Some(&Parents), None).is_ok()
        );
        ops[1].op = Op::Initialize(
            Some(0),
            Signature {
                arguments: vec![Type::LinkedObject(1)],
                result: Type::Void,
            },
        );
        assert!(
            verify_method_with_links(&ops, &code, &signature, true, Some(&Parents), None).is_err()
        );
        ops[0].op = Op::NewLinkedObject(3);
        ops[1].op = Op::Initialize(
            Some(0),
            Signature {
                arguments: vec![Type::LinkedObject(2)],
                result: Type::Void,
            },
        );
        assert!(
            verify_method_with_links(&ops, &code, &signature, true, Some(&Parents), None).is_err()
        );
    }

    #[test]
    fn protected_constructor_checks_current_class_even_for_fresh_allocations() {
        struct Parents;
        impl StaticLinker for Parents {
            fn resolve(&self, _: &ClassFile, _: u16) -> Result<(usize, Signature)> {
                bail!("No symbolic lookup in verifier test")
            }
            fn constructor_parent(&self, owner: usize, parent: usize) -> Result<bool> {
                Ok(owner == 3 && parent == 2)
            }
        }
        let mut code = Code {
            max_stack: 1,
            max_locals: 1,
            bytes: vec![0; 3],
            handlers: Vec::new(),
        };
        let signature = Signature {
            arguments: vec![Type::LinkedObject(3)],
            result: Type::Void,
        };
        let parent = Signature {
            arguments: vec![Type::LinkedObject(2)],
            result: Type::Void,
        };
        let mut ops = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Load(Type::AnyRef, 0),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::ProtectedInitialize(0, parent.clone(), 3),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Return(Type::Void),
            },
        ];
        assert!(
            verify_method_with_links(&ops, &code, &signature, true, Some(&Parents), None).is_ok()
        );
        ops[1].op = Op::ProtectedInitialize(0, parent.clone(), 4);
        assert!(
            verify_method_with_links(&ops, &code, &signature, true, Some(&Parents), None).is_err()
        );
        code.max_locals = 0;
        ops[0].op = Op::NewLinkedObject(2);
        ops[1].op = Op::ProtectedInitialize(0, parent.clone(), 3);
        let ordinary = Signature {
            arguments: vec![],
            result: Type::Void,
        };
        let error = verify_method_with_links(&ops, &code, &ordinary, false, Some(&Parents), None)
            .unwrap_err();
        assert!(format!("{error:#}").contains("current class"), "{error:#}");
        ops[0].op = Op::NewLinkedObject(3);
        assert!(
            verify_method_with_links(&ops, &code, &ordinary, false, Some(&Parents), None).is_err()
        );
    }
}
