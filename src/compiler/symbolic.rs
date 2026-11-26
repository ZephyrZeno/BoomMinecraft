//! Link-independent Java bytecode IR. No runtime substitution or execution.
use super::{
    classfile::{ClassFile, Code, DynamicSite, Method, MethodHandle, NumericConstant},
    exceptions,
};
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub const SCHEMA: u32 = 1;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum JavaType {
    Boolean,
    Byte,
    Char,
    Short,
    Int,
    Long,
    Float,
    Double,
    Void,
    Object(String),
    Array {
        dimensions: u8,
        element: Box<JavaType>,
    },
}
impl JavaType {
    pub fn slots(&self) -> usize {
        match self {
            Self::Long | Self::Double => 2,
            Self::Void => 0,
            _ => 1,
        }
    }
    fn read(bytes: &[u8], position: &mut usize, allow_void: bool) -> Result<Self> {
        let byte = *bytes.get(*position).context("Truncated type descriptor")?;
        *position += 1;
        Ok(match byte {
            b'Z' => Self::Boolean,
            b'B' => Self::Byte,
            b'C' => Self::Char,
            b'S' => Self::Short,
            b'I' => Self::Int,
            b'J' => Self::Long,
            b'F' => Self::Float,
            b'D' => Self::Double,
            b'V' if allow_void => Self::Void,
            b'L' => {
                let start = *position;
                while bytes.get(*position).is_some_and(|b| *b != b';') {
                    *position += 1;
                }
                ensure!(
                    *position > start && bytes.get(*position) == Some(&b';'),
                    "Invalid object descriptor"
                );
                let name = std::str::from_utf8(&bytes[start..*position])?;
                ensure!(
                    !name.contains(['.', '[', '\0'])
                        && !name.starts_with('/')
                        && !name.ends_with('/')
                        && !name.contains("//"),
                    "Invalid internal class name"
                );
                *position += 1;
                Self::Object(name.into())
            }
            b'[' => {
                let mut dimensions = 1usize;
                while bytes.get(*position) == Some(&b'[') {
                    dimensions += 1;
                    *position += 1;
                }
                ensure!(dimensions <= 255, "Array descriptor exceeds 255 dimensions");
                Self::Array {
                    dimensions: dimensions as u8,
                    element: Box::new(Self::read(bytes, position, false)?),
                }
            }
            _ => bail!("Invalid type descriptor byte 0x{byte:02x}"),
        })
    }
    pub fn field(descriptor: &str) -> Result<Self> {
        let mut position = 0;
        let ty = Self::read(descriptor.as_bytes(), &mut position, false)?;
        ensure!(
            position == descriptor.len(),
            "Trailing field descriptor data"
        );
        Ok(ty)
    }
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MethodType {
    pub parameters: Vec<JavaType>,
    pub result: JavaType,
}
impl MethodType {
    pub fn parse(descriptor: &str) -> Result<Self> {
        let bytes = descriptor.as_bytes();
        ensure!(bytes.first() == Some(&b'('), "Invalid method descriptor");
        let mut position = 1;
        let mut parameters = vec![];
        let mut slots = 0;
        while bytes.get(position) != Some(&b')') {
            let ty = JavaType::read(bytes, &mut position, false)?;
            slots += ty.slots();
            ensure!(slots <= 255, "Method parameters exceed 255 slots");
            parameters.push(ty);
        }
        position += 1;
        let result = JavaType::read(bytes, &mut position, true)?;
        ensure!(position == bytes.len(), "Trailing method descriptor data");
        Ok(Self { parameters, result })
    }
    pub fn parameter_slots(&self) -> usize {
        self.parameters.iter().map(JavaType::slots).sum()
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum Operand {
    None,
    Immediate(i32),
    Local(u16),
    Increment {
        local: u16,
        amount: i16,
    },
    Constant(u16),
    Branch(u16),
    Switch {
        default: u16,
        cases: Vec<(i32, u16)>,
    },
    Interface {
        constant: u16,
        count: u8,
    },
    PrimitiveArray(u8),
    MultiArray {
        constant: u16,
        dimensions: u8,
    },
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Instruction {
    pub pc: u16,
    /// Original encoded opcode, including wide; no runtime policy applied.
    pub opcode: u8,
    pub wide_opcode: Option<u8>,
    pub next: u16,
    pub operand: Operand,
}
impl Instruction {
    pub fn effective_opcode(&self) -> u8 {
        self.wide_opcode.unwrap_or(self.opcode)
    }
    pub fn constant(&self) -> Option<u16> {
        match self.operand {
            Operand::Constant(i)
            | Operand::Interface { constant: i, .. }
            | Operand::MultiArray { constant: i, .. } => Some(i),
            _ => None,
        }
    }
    pub fn successors(&self, length: usize) -> Vec<u16> {
        match (&self.operand, self.effective_opcode()) {
            (Operand::Switch { default, cases }, _) => std::iter::once(*default)
                .chain(cases.iter().map(|c| c.1))
                .collect(),
            (Operand::Branch(target), 0xa7 | 0xc8) => vec![*target],
            (Operand::Branch(target), _) => std::iter::once(*target)
                .chain((usize::from(self.next) < length).then_some(self.next))
                .collect(),
            (_, 0xac..=0xb1 | 0xbf | 0xa9) => vec![],
            _ => (usize::from(self.next) < length)
                .then_some(self.next)
                .into_iter()
                .collect(),
        }
    }
}
fn u16_at(bytes: &[u8], at: usize) -> Result<u16> {
    Ok(u16::from_be_bytes(
        bytes
            .get(at..at + 2)
            .context("Truncated u16 operand")?
            .try_into()?,
    ))
}
fn i32_at(bytes: &[u8], at: usize) -> Result<i32> {
    Ok(i32::from_be_bytes(
        bytes
            .get(at..at + 4)
            .context("Truncated i32 operand")?
            .try_into()?,
    ))
}

/// Shared structural/operand frontend. It never asks a linker to resolve a member.
pub fn decode_stream(bytes: &[u8]) -> Result<Vec<Instruction>> {
    let starts = exceptions::boundaries(bytes)?;
    let positions = starts.iter().copied().collect::<Vec<_>>();
    let branch = |pc: usize, offset: i32| -> Result<u16> {
        let target = pc as i64 + i64::from(offset);
        ensure!(
            target >= 0 && starts.contains(&(target as usize)),
            "Branch at {pc} does not target an instruction boundary"
        );
        Ok(target as u16)
    };
    let mut out = Vec::with_capacity(starts.len());
    for (index, &pc) in positions.iter().enumerate() {
        let opcode = bytes[pc];
        let next = positions.get(index + 1).copied().unwrap_or(bytes.len());
        let mut wide_opcode = None;
        let operand = match opcode {
            0x10 => Operand::Immediate(i32::from(bytes[pc + 1] as i8)),
            0x11 => Operand::Immediate(i32::from(u16_at(bytes, pc + 1)? as i16)),
            0x12 => Operand::Constant(u16::from(bytes[pc + 1])),
            0x13..=0x14 | 0xb2..=0xb8 | 0xbb | 0xbd | 0xc0..=0xc1 => {
                Operand::Constant(u16_at(bytes, pc + 1)?)
            }
            0x15..=0x19 | 0x36..=0x3a | 0xa9 => Operand::Local(u16::from(bytes[pc + 1])),
            0x1a..=0x2d => Operand::Local(u16::from((opcode - 0x1a) % 4)),
            0x3b..=0x4e => Operand::Local(u16::from((opcode - 0x3b) % 4)),
            0x84 => Operand::Increment {
                local: u16::from(bytes[pc + 1]),
                amount: i16::from(bytes[pc + 2] as i8),
            },
            0x99..=0xa8 | 0xc6..=0xc7 => {
                Operand::Branch(branch(pc, i32::from(u16_at(bytes, pc + 1)? as i16))?)
            }
            0xc8..=0xc9 => Operand::Branch(branch(pc, i32_at(bytes, pc + 1)?)?),
            0xaa..=0xab => {
                let base = (pc + 4) & !3;
                let default = branch(pc, i32_at(bytes, base)?)?;
                let mut cases = vec![];
                if opcode == 0xaa {
                    let low = i32_at(bytes, base + 4)?;
                    let high = i32_at(bytes, base + 8)?;
                    for (index, key) in (low..=high).enumerate() {
                        cases.push((key, branch(pc, i32_at(bytes, base + 12 + index * 4)?)?));
                    }
                } else {
                    let count = i32_at(bytes, base + 4)? as usize;
                    for index in 0..count {
                        cases.push((
                            i32_at(bytes, base + 8 + index * 8)?,
                            branch(pc, i32_at(bytes, base + 12 + index * 8)?)?,
                        ));
                    }
                }
                Operand::Switch { default, cases }
            }
            0xb9 => {
                ensure!(
                    bytes[pc + 3] != 0 && bytes[pc + 4] == 0,
                    "Invalid invokeinterface count/reserved byte at {pc}"
                );
                Operand::Interface {
                    constant: u16_at(bytes, pc + 1)?,
                    count: bytes[pc + 3],
                }
            }
            0xba => {
                ensure!(
                    bytes[pc + 3] == 0 && bytes[pc + 4] == 0,
                    "Nonzero invokedynamic reserved bytes at {pc}"
                );
                Operand::Constant(u16_at(bytes, pc + 1)?)
            }
            0xbc => {
                ensure!(
                    (4..=11).contains(&bytes[pc + 1]),
                    "Invalid newarray atype at {pc}"
                );
                Operand::PrimitiveArray(bytes[pc + 1])
            }
            0xc4 => {
                wide_opcode = Some(bytes[pc + 1]);
                let local = u16_at(bytes, pc + 2)?;
                if bytes[pc + 1] == 0x84 {
                    Operand::Increment {
                        local,
                        amount: u16_at(bytes, pc + 4)? as i16,
                    }
                } else {
                    Operand::Local(local)
                }
            }
            0xc5 => {
                ensure!(bytes[pc + 3] != 0, "Zero multianewarray dimensions at {pc}");
                Operand::MultiArray {
                    constant: u16_at(bytes, pc + 1)?,
                    dimensions: bytes[pc + 3],
                }
            }
            _ => Operand::None,
        };
        out.push(Instruction {
            pc: pc as u16,
            opcode,
            wide_opcode,
            next: next as u16,
            operand,
        });
    }
    Ok(out)
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum Constant {
    Int(i32),
    Long(i64),
    FloatBits(u32),
    DoubleBits(u64),
    StringUtf16(Vec<u16>),
    Class(String),
    Field {
        owner: String,
        name: String,
        descriptor: String,
    },
    Method {
        owner: String,
        name: String,
        descriptor: String,
        interface: bool,
    },
    Handle(MethodHandle),
    MethodType(String),
    Dynamic(DynamicSite),
    InvokeDynamic(DynamicSite),
}
pub(super) fn constant(class: &ClassFile, index: u16) -> Result<Constant> {
    Ok(match class.constant_tag(index)? {
        3..=6 => match class.numeric(index)? {
            NumericConstant::Int(v) => Constant::Int(v),
            NumericConstant::Long(v) => Constant::Long(v),
            NumericConstant::Float(v) => Constant::FloatBits(v),
            NumericConstant::Double(v) => Constant::DoubleBits(v),
        },
        7 => Constant::Class(class.constant_class(index)?),
        8 => Constant::StringUtf16(
            class
                .string_literal(index)?
                .context("Missing String constant")?,
        ),
        9 => {
            let (owner, name, descriptor) = class.field_reference(index)?;
            JavaType::field(&descriptor)?;
            Constant::Field {
                owner,
                name,
                descriptor,
            }
        }
        10..=11 => {
            let interface = class.constant_tag(index)? == 11;
            let (owner, name, descriptor) = if interface {
                class.interface_method_reference(index)?
            } else {
                class.method_reference(index)?
            };
            MethodType::parse(&descriptor)?;
            Constant::Method {
                owner,
                name,
                descriptor,
                interface,
            }
        }
        15 => Constant::Handle(class.method_handle(index)?),
        16 => {
            let descriptor = class.method_type(index)?;
            MethodType::parse(&descriptor)?;
            Constant::MethodType(descriptor)
        }
        17 => {
            let site = class.dynamic_constant(index)?;
            JavaType::field(&site.descriptor)?;
            Constant::Dynamic(site)
        }
        18 => {
            let site = class.dynamic_site(index)?;
            MethodType::parse(&site.descriptor)?;
            Constant::InvokeDynamic(site)
        }
        tag => bail!("Constant tag {tag} cannot be used as an instruction/bootstrap operand"),
    })
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Handler {
    pub start: u16,
    pub end: u16,
    pub target: u16,
    pub catch_type: Option<String>,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Block {
    pub start: u16,
    pub end: u16,
    pub first_instruction: usize,
    pub instruction_count: usize,
    pub successors: Vec<u16>,
    /// Original handler indices in their original precedence order.
    pub handlers: Vec<usize>,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Body {
    pub max_stack: u16,
    pub max_locals: u16,
    pub code_length: usize,
    pub instructions: Vec<Instruction>,
    pub blocks: Vec<Block>,
    pub handlers: Vec<Handler>,
    pub contains_legacy_subroutines: bool,
}
pub struct Decoder<'a> {
    class: &'a ClassFile,
    pub constants: BTreeMap<u16, Constant>,
}
impl<'a> Decoder<'a> {
    pub fn new(class: &'a ClassFile) -> Self {
        Self {
            class,
            constants: BTreeMap::new(),
        }
    }
    pub(super) fn intern(&mut self, index: u16) -> Result<()> {
        let mut todo = vec![index];
        while let Some(index) = todo.pop() {
            if self.constants.contains_key(&index) {
                continue;
            }
            let value = constant(self.class, index)?;
            if let Constant::Dynamic(site) | Constant::InvokeDynamic(site) = &value {
                todo.extend(site.arguments.iter().copied());
            }
            self.constants.insert(index, value);
        }
        Ok(())
    }
    pub fn method(&mut self, method: &Method) -> Result<Body> {
        let signature = MethodType::parse(&method.descriptor)?;
        let code = method.code.as_ref().context("Missing Java Code")?;
        let slots = signature.parameter_slots() + usize::from(method.access & 8 == 0);
        ensure!(
            slots <= 255 && slots <= usize::from(code.max_locals),
            "Method parameters do not fit max_locals"
        );
        self.body(code)
    }
    pub fn body(&mut self, code: &Code) -> Result<Body> {
        let instructions = decode_stream(&code.bytes)?;
        let starts = instructions.iter().map(|i| i.pc).collect::<BTreeSet<_>>();
        let mut leaders = BTreeSet::from([0]);
        let mut legacy = false;
        for instruction in &instructions {
            let op = instruction.effective_opcode();
            legacy |= matches!(op, 0xa8 | 0xa9 | 0xc9);
            let local = match instruction.operand {
                Operand::Local(i) => Some(i),
                Operand::Increment { local, .. } => Some(local),
                _ => None,
            };
            if let Some(local) = local {
                let wide = matches!(op,0x16|0x18|0x1e..=0x21|0x26..=0x29|0x37|0x39|0x3f..=0x42|0x47..=0x4a);
                ensure!(
                    usize::from(local) + if wide { 2 } else { 1 } <= usize::from(code.max_locals),
                    "Local operand outside max_locals at {}",
                    instruction.pc
                );
            }
            if let Some(index) = instruction.constant() {
                self.intern(index)?;
                let symbol = &self.constants[&index];
                let correct = match op {
                    0x12..=0x14 => {
                        let slots = match symbol {
                            Constant::Long(_) | Constant::DoubleBits(_) => 2,
                            Constant::Dynamic(site) => JavaType::field(&site.descriptor)?.slots(),
                            _ => 1,
                        };
                        let loadable = matches!(
                            symbol,
                            Constant::Int(_)
                                | Constant::Long(_)
                                | Constant::FloatBits(_)
                                | Constant::DoubleBits(_)
                                | Constant::Class(_)
                                | Constant::StringUtf16(_)
                                | Constant::Handle(_)
                                | Constant::MethodType(_)
                                | Constant::Dynamic(_)
                        );
                        loadable && (slots == 2) == (op == 0x14)
                    }
                    0xb2..=0xb5 => matches!(symbol, Constant::Field { .. }),
                    0xb6 => matches!(
                        symbol,
                        Constant::Method {
                            interface: false,
                            ..
                        }
                    ),
                    0xb7 | 0xb8 => {
                        matches!(symbol, Constant::Method { interface, .. } if !interface || self.class.major >= 52)
                    }
                    0xb9 => matches!(
                        symbol,
                        Constant::Method {
                            interface: true,
                            ..
                        }
                    ),
                    0xba => matches!(symbol, Constant::InvokeDynamic(_)),
                    0xbb | 0xbd | 0xc0 | 0xc1 | 0xc5 => matches!(symbol, Constant::Class(_)),
                    _ => false,
                };
                ensure!(
                    correct,
                    "Constant kind does not match opcode at {}",
                    instruction.pc
                );
                if let Operand::Interface { count, .. } = instruction.operand
                    && let Constant::Method { descriptor, .. } = symbol
                {
                    ensure!(
                        MethodType::parse(descriptor)?.parameter_slots() + 1 == usize::from(count),
                        "invokeinterface argument slots differ at {}",
                        instruction.pc
                    );
                }
                if let Constant::Class(name) = symbol {
                    if op == 0xbb {
                        ensure!(
                            !name.starts_with('['),
                            "new cannot instantiate an array class"
                        );
                    }
                    if let Operand::MultiArray { dimensions, .. } = instruction.operand {
                        let JavaType::Array {
                            dimensions: available,
                            ..
                        } = JavaType::field(name)?
                        else {
                            bail!("multianewarray needs an array descriptor");
                        };
                        ensure!(
                            dimensions <= available,
                            "multianewarray dimensions exceed descriptor"
                        );
                    }
                }
            }
            if matches!(
                instruction.operand,
                Operand::Branch(_) | Operand::Switch { .. }
            ) {
                leaders.extend(instruction.successors(code.bytes.len()));
                if usize::from(instruction.next) < code.bytes.len() {
                    leaders.insert(instruction.next);
                }
            } else if matches!(op, 0xac..=0xb1 | 0xbf | 0xa9)
                && usize::from(instruction.next) < code.bytes.len()
            {
                leaders.insert(instruction.next);
            }
        }
        let mut handlers = vec![];
        for h in &code.handlers {
            ensure!(
                h.start_pc < h.end_pc
                    && starts.contains(&h.start_pc)
                    && (usize::from(h.end_pc) == code.bytes.len() || starts.contains(&h.end_pc))
                    && starts.contains(&h.handler_pc),
                "Invalid exception table boundary"
            );
            leaders.insert(h.start_pc);
            leaders.insert(h.handler_pc);
            if usize::from(h.end_pc) < code.bytes.len() {
                leaders.insert(h.end_pc);
            }
            handlers.push(Handler {
                start: h.start_pc,
                end: h.end_pc,
                target: h.handler_pc,
                catch_type: h.catch_type.clone(),
            });
        }
        let positions = instructions
            .iter()
            .enumerate()
            .map(|(index, i)| (i.pc, index))
            .collect::<BTreeMap<_, _>>();
        let leaders = leaders.into_iter().collect::<Vec<_>>();
        let mut blocks = vec![];
        for (index, &start) in leaders.iter().enumerate() {
            let end = leaders
                .get(index + 1)
                .copied()
                .unwrap_or(code.bytes.len() as u16);
            let first = positions[&start];
            let limit = positions.get(&end).copied().unwrap_or(instructions.len());
            let last = &instructions[limit - 1];
            let successors = last
                .successors(code.bytes.len())
                .into_iter()
                .collect::<BTreeSet<_>>()
                .into_iter()
                .collect();
            blocks.push(Block {
                start,
                end,
                first_instruction: first,
                instruction_count: limit - first,
                successors,
                handlers: handlers
                    .iter()
                    .enumerate()
                    .filter_map(|(i, h)| (h.start <= start && start < h.end).then_some(i))
                    .collect(),
            });
        }
        Ok(Body {
            max_stack: code.max_stack,
            max_locals: code.max_locals,
            code_length: code.bytes.len(),
            instructions,
            blocks,
            handlers,
            contains_legacy_subroutines: legacy,
        })
    }
}

#[cfg(test)]
pub(super) fn fixture(bodies: &[(u16, u16, &[u8])]) -> Vec<u8> {
    fn utf(bytes: &mut Vec<u8>, value: &str) {
        bytes.push(1);
        bytes.extend((value.len() as u16).to_be_bytes());
        bytes.extend(value.as_bytes());
    }
    let mut bytes = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 65, 0, 25];
    utf(&mut bytes, "p/IR");
    bytes.extend([7, 0, 1]);
    utf(&mut bytes, "java/lang/Object");
    bytes.extend([7, 0, 3]);
    for text in ["eval", "(I)I", "Code", "p/Missing"] {
        utf(&mut bytes, text);
    }
    bytes.extend([7, 0, 8]);
    utf(&mut bytes, "call");
    bytes.extend([12, 0, 10, 0, 6, 10, 0, 9, 0, 11]);
    utf(&mut bytes, "bootstrap");
    utf(
        &mut bytes,
        "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;",
    );
    bytes.extend([12, 0, 13, 0, 14, 10, 0, 9, 0, 15, 15, 6, 0, 16]);
    utf(&mut bytes, "BootstrapMethods");
    utf(&mut bytes, "apply");
    utf(&mut bytes, "()Ljava/lang/Runnable;");
    bytes.extend([12, 0, 19, 0, 20, 18, 0, 0, 0, 21]);
    utf(&mut bytes, "dynamic");
    utf(&mut bytes, "()I");
    for value in [0x21u16, 2, 4, 0, 0, bodies.len() as u16] {
        bytes.extend(value.to_be_bytes());
    }
    for (name, descriptor, code) in bodies {
        for value in [9u16, *name, *descriptor, 1, 7] {
            bytes.extend(value.to_be_bytes());
        }
        bytes.extend((12u32 + code.len() as u32).to_be_bytes());
        bytes.extend([0, 2, 0, 1]);
        bytes.extend((code.len() as u32).to_be_bytes());
        bytes.extend(*code);
        bytes.extend([0, 0, 0, 0]);
    }
    bytes.extend([0, 1, 0, 18, 0, 0, 0, 6, 0, 1, 0, 17, 0, 0]);
    bytes
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn descriptors_keep_named_and_multidimensional_types_without_loading_classes() {
        let sig = MethodType::parse("(J[[Lp/Missing;[Z)Ljava/lang/Other;").unwrap();
        assert_eq!(sig.parameter_slots(), 4);
        assert_eq!(sig.result, JavaType::Object("java/lang/Other".into()));
        assert!(matches!(
            sig.parameters[1],
            JavaType::Array { dimensions: 2, .. }
        ));
        for invalid in [
            "(V)V",
            "([V)V",
            "()Vx",
            "(Lp//Bad;)V",
            "()Lp.Missing;",
            "(I",
        ] {
            assert!(MethodType::parse(invalid).is_err(), "{invalid}");
        }
    }
    #[test]
    fn branches_reject_middle_of_instruction_and_end_of_code() {
        assert!(decode_stream(&[0xa7, 0, 1]).is_err());
        assert!(decode_stream(&[0xa7, 0, 3]).is_err());
        assert_eq!(
            decode_stream(&[0x03, 0x99, 0, 4, 0xb1, 0xb1]).unwrap()[1].successors(6),
            vec![5, 4]
        );
    }
    #[test]
    fn wide_locals_and_signed_increment_are_preserved() {
        let instructions = decode_stream(&[0xc4, 0x84, 0x01, 0x02, 0xff, 0x80, 0xb1]).unwrap();
        assert_eq!(
            instructions[0].operand,
            Operand::Increment {
                local: 258,
                amount: -128
            }
        );
        assert_eq!(instructions[0].effective_opcode(), 0x84);
        assert_eq!(instructions[0].next, 6);
    }
    #[test]
    fn reserved_invocation_bytes_and_array_kinds_are_rejected() {
        assert!(decode_stream(&[0xba, 0, 1, 0, 1, 0xb1]).is_err());
        assert!(decode_stream(&[0xb9, 0, 1, 0, 0, 0xb1]).is_err());
        assert!(decode_stream(&[0xbc, 3, 0xb1]).is_err());
        assert!(decode_stream(&[0xc5, 0, 1, 0, 0xb1]).is_err());
    }
    #[test]
    fn java_six_interface_calls_do_not_require_java_eight_static_interface_rules() {
        fn utf(bytes: &mut Vec<u8>, value: &str) {
            bytes.push(1);
            bytes.extend((value.len() as u16).to_be_bytes());
            bytes.extend(value.as_bytes());
        }
        let mut bytes = vec![0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 50, 0, 13];
        utf(&mut bytes, "p/Old");
        bytes.extend([7, 0, 1]);
        utf(&mut bytes, "java/lang/Object");
        bytes.extend([7, 0, 3]);
        for name in ["eval", "()V", "Code", "p/Missing"] {
            utf(&mut bytes, name);
        }
        bytes.extend([7, 0, 8]);
        utf(&mut bytes, "call");
        bytes.extend([12, 0, 10, 0, 6, 11, 0, 9, 0, 11]);
        for value in [0x21u16, 2, 4, 0, 0, 1, 9, 5, 6, 1, 7] {
            bytes.extend(value.to_be_bytes());
        }
        bytes.extend(19u32.to_be_bytes());
        bytes.extend([
            0, 1, 0, 0, 0, 0, 0, 7, 0x01, 0xb9, 0, 12, 1, 0, 0xb1, 0, 0, 0, 0, 0, 0,
        ]);
        let class = ClassFile::parse(&bytes).unwrap();
        let mut decoder = Decoder::new(&class);
        let body = decoder.method(&class.methods[0]).unwrap();
        assert_eq!(body.instructions.len(), 3);
        assert!(matches!(
            &decoder.constants[&12],
            Constant::Method {
                interface: true,
                ..
            }
        ));
    }
    #[test]
    fn unknown_method_and_bootstrap_remain_unresolved_symbols() {
        let bytes = fixture(&[
            (5, 6, &[0x1a, 0xb8, 0, 12, 0xac]),
            (23, 20, &[0xba, 0, 22, 0, 0, 0xb0]),
        ]);
        let class = ClassFile::parse(&bytes).unwrap();
        let mut decoder = Decoder::new(&class);
        let first = decoder.method(&class.methods[0]).unwrap();
        let second = decoder.method(&class.methods[1]).unwrap();
        assert_eq!(first.instructions[1].constant(), Some(12));
        assert!(matches!(&decoder.constants[&12],Constant::Method{owner,..} if owner=="p/Missing"));
        assert!(
            matches!(&decoder.constants[&22],Constant::InvokeDynamic(site) if site.bootstrap.owner=="p/Missing")
        );
        assert_eq!(second.instructions[0].opcode, 0xba);
        assert_eq!(
            serde_json::from_slice::<Body>(&serde_json::to_vec(&first).unwrap()).unwrap(),
            first
        );
    }
    #[test]
    fn exception_blocks_preserve_handler_order_and_protected_boundaries() {
        let class =
            ClassFile::parse(&fixture(&[(5, 24, &[0x03, 0xac, 0x57, 0x04, 0xac])])).unwrap();
        let mut code = class.methods[0].code.as_ref().unwrap().bytes.clone();
        let mut decoder = Decoder::new(&class);
        let mut code = Code {
            max_stack: 2,
            max_locals: 1,
            bytes: std::mem::take(&mut code),
            handlers: vec![],
        };
        for _ in 0..2 {
            code.handlers
                .push(super::super::classfile::ExceptionHandler {
                    start_pc: 0,
                    end_pc: 2,
                    handler_pc: 2,
                    catch_type: None,
                });
        }
        let body = decoder.body(&code).unwrap();
        assert_eq!(body.blocks.len(), 2);
        assert_eq!(body.blocks[0].handlers, vec![0, 1]);
        assert!(body.blocks[1].handlers.is_empty());
        assert_eq!(body.blocks[1].start, 2);
    }
}
