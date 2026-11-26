use std::collections::{BTreeMap, BTreeSet, VecDeque};

use anyhow::{Context, Result, bail, ensure};

use super::classfile::{ClassFile, Code, Method};

#[derive(Debug, Clone, Copy)]
enum Condition {
    Eq,
    Ne,
    Lt,
    Ge,
    Gt,
    Le,
}
impl Condition {
    fn jump(self) -> &'static str {
        match self {
            Self::Eq => "je",
            Self::Ne => "jne",
            Self::Lt => "jl",
            Self::Ge => "jge",
            Self::Gt => "jg",
            Self::Le => "jle",
        }
    }
}

#[derive(Debug, Clone, Copy)]
enum Binary {
    Add,
    Sub,
    Mul,
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
    Const(i32),
    Load(usize),
    Store(usize),
    Pop,
    Dup,
    Swap,
    Neg,
    Binary(Binary),
    Increment(usize, i32),
    If(Condition, usize),
    Compare(Condition, usize),
    Goto(usize),
    Switch {
        default: usize,
        cases: Vec<(i32, usize)>,
    },
    Call {
        method: usize,
        args: usize,
    },
    Return,
}

#[derive(Debug)]
struct Instruction {
    pc: usize,
    next: usize,
    op: Op,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Frame {
    stack: usize,
    initialized: Vec<bool>,
}

pub struct CompiledMethod {
    pub assembly: String,
    pub argument_count: usize,
    pub instruction_count: usize,
    pub linked_methods: usize,
}

pub fn argument_count(descriptor: &str) -> Result<usize> {
    let params = descriptor
        .strip_prefix('(')
        .and_then(|text| text.strip_suffix(")I"))
        .context("i32-v1 requires a method descriptor (I...)I")?;
    ensure!(
        params.len() <= 4 && params.bytes().all(|byte| byte == b'I'),
        "i32-v1 supports zero to four int arguments and an int return"
    );
    Ok(params.len())
}

fn byte(code: &[u8], position: &mut usize) -> Result<u8> {
    let value = *code
        .get(*position)
        .context("Truncated bytecode instruction")?;
    *position += 1;
    Ok(value)
}
fn u16(code: &[u8], position: &mut usize) -> Result<u16> {
    Ok(u16::from_be_bytes([
        byte(code, position)?,
        byte(code, position)?,
    ]))
}
fn target(pc: usize, offset: i32, length: usize) -> Result<usize> {
    let value = pc as i64 + offset as i64;
    ensure!(
        value >= 0 && value < length as i64,
        "Branch target is outside method at bytecode {pc}"
    );
    Ok(value as usize)
}

fn read_i32(code: &[u8], position: &mut usize) -> Result<i32> {
    Ok(i32::from_be_bytes([
        byte(code, position)?,
        byte(code, position)?,
        byte(code, position)?,
        byte(code, position)?,
    ]))
}

fn decode(code: &Code, class: &ClassFile) -> Result<Vec<Instruction>> {
    let bytes = &code.bytes;
    let mut position = 0;
    let mut result = Vec::new();
    while position < bytes.len() {
        let pc = position;
        let opcode = byte(bytes, &mut position)?;
        let op = match opcode {
            0x00 => Op::Nop,
            0x02..=0x08 => Op::Const(opcode as i32 - 3),
            0x10 => Op::Const(byte(bytes, &mut position)? as i8 as i32),
            0x11 => Op::Const(u16(bytes, &mut position)? as i16 as i32),
            0x12 => Op::Const(class.integer(byte(bytes, &mut position)? as u16)?),
            0x13 => Op::Const(class.integer(u16(bytes, &mut position)?)?),
            0x15 => Op::Load(byte(bytes, &mut position)? as usize),
            0x1a..=0x1d => Op::Load((opcode - 0x1a) as usize),
            0x36 => Op::Store(byte(bytes, &mut position)? as usize),
            0x3b..=0x3e => Op::Store((opcode - 0x3b) as usize),
            0x57 => Op::Pop,
            0x59 => Op::Dup,
            0x5f => Op::Swap,
            0x60 => Op::Binary(Binary::Add),
            0x64 => Op::Binary(Binary::Sub),
            0x68 => Op::Binary(Binary::Mul),
            0x74 => Op::Neg,
            0x78 => Op::Binary(Binary::Shl),
            0x7a => Op::Binary(Binary::Shr),
            0x7c => Op::Binary(Binary::Ushr),
            0x7e => Op::Binary(Binary::And),
            0x80 => Op::Binary(Binary::Or),
            0x82 => Op::Binary(Binary::Xor),
            0x84 => Op::Increment(
                byte(bytes, &mut position)? as usize,
                byte(bytes, &mut position)? as i8 as i32,
            ),
            0x99..=0x9e => {
                let offset = u16(bytes, &mut position)? as i16 as i32;
                Op::If(condition(opcode - 0x99), target(pc, offset, bytes.len())?)
            }
            0x9f..=0xa4 => {
                let offset = u16(bytes, &mut position)? as i16 as i32;
                Op::Compare(condition(opcode - 0x9f), target(pc, offset, bytes.len())?)
            }
            0xa7 => {
                let offset = u16(bytes, &mut position)? as i16 as i32;
                Op::Goto(target(pc, offset, bytes.len())?)
            }
            0xaa | 0xab => {
                while position % 4 != 0 {
                    ensure!(
                        byte(bytes, &mut position)? == 0,
                        "Nonzero switch padding at {pc}"
                    );
                }
                let default = target(pc, read_i32(bytes, &mut position)?, bytes.len())?;
                let mut cases = Vec::new();
                if opcode == 0xaa {
                    let low = read_i32(bytes, &mut position)?;
                    let high = read_i32(bytes, &mut position)?;
                    let count = high as i64 - low as i64 + 1;
                    ensure!(
                        count > 0 && count <= ((bytes.len() - position) / 4) as i64,
                        "Invalid tableswitch bounds at {pc}"
                    );
                    for key in low..=high {
                        cases.push((
                            key,
                            target(pc, read_i32(bytes, &mut position)?, bytes.len())?,
                        ));
                    }
                } else {
                    let count = read_i32(bytes, &mut position)?;
                    ensure!(
                        count >= 0 && count as usize <= (bytes.len() - position) / 8,
                        "Invalid lookupswitch size at {pc}"
                    );
                    for _ in 0..count {
                        let key = read_i32(bytes, &mut position)?;
                        ensure!(
                            cases.last().is_none_or(|(previous, _)| *previous < key),
                            "lookupswitch keys must be strictly sorted"
                        );
                        cases.push((
                            key,
                            target(pc, read_i32(bytes, &mut position)?, bytes.len())?,
                        ));
                    }
                }
                Op::Switch { default, cases }
            }
            0xb8 => {
                let method = class.local_static_target(u16(bytes, &mut position)?)?;
                let args = argument_count(&class.methods[method].descriptor)?;
                Op::Call { method, args }
            }
            0xac => Op::Return,
            0xc4 => {
                let wide = byte(bytes, &mut position)?;
                let index = u16(bytes, &mut position)? as usize;
                match wide {
                    0x15 => Op::Load(index),
                    0x36 => Op::Store(index),
                    0x84 => Op::Increment(index, u16(bytes, &mut position)? as i16 as i32),
                    _ => bail!("Unsupported wide opcode 0x{wide:02x} at bytecode {pc}"),
                }
            }
            0xc8 => {
                let offset = i32::from_be_bytes([
                    byte(bytes, &mut position)?,
                    byte(bytes, &mut position)?,
                    byte(bytes, &mut position)?,
                    byte(bytes, &mut position)?,
                ]);
                Op::Goto(target(pc, offset, bytes.len())?)
            }
            _ => bail!(
                "Unsupported opcode 0x{opcode:02x} at bytecode {pc}; outside i32-v2 (division, objects and exceptions are not implemented)"
            ),
        };
        result.push(Instruction {
            pc,
            next: position,
            op,
        });
    }
    Ok(result)
}

fn condition(value: u8) -> Condition {
    match value {
        0 => Condition::Eq,
        1 => Condition::Ne,
        2 => Condition::Lt,
        3 => Condition::Ge,
        4 => Condition::Gt,
        5 => Condition::Le,
        _ => unreachable!(),
    }
}

fn verify(
    instructions: &[Instruction],
    code: &Code,
    args: usize,
) -> Result<BTreeMap<usize, Frame>> {
    ensure!(!instructions.is_empty(), "Empty method body");
    ensure!(
        code.max_locals as usize >= args && code.max_locals <= 256 && code.max_stack <= 256,
        "i32-v1 requires at most 256 locals and stack slots"
    );
    let indices: BTreeMap<_, _> = instructions
        .iter()
        .enumerate()
        .map(|(index, inst)| (inst.pc, index))
        .collect();
    for instruction in instructions {
        if let Op::If(_, dest) | Op::Compare(_, dest) | Op::Goto(dest) = instruction.op {
            ensure!(
                indices.contains_key(&dest),
                "Branch at {} does not target an instruction boundary",
                instruction.pc
            );
        }
        if let Op::Switch { default, ref cases } = instruction.op {
            for dest in std::iter::once(&default).chain(cases.iter().map(|(_, dest)| dest)) {
                ensure!(
                    indices.contains_key(dest),
                    "Switch at {} does not target an instruction boundary",
                    instruction.pc
                );
            }
        }
    }
    let mut initialized = vec![false; code.max_locals as usize];
    initialized[..args].fill(true);
    let mut frames = BTreeMap::from([(
        0,
        Frame {
            stack: 0,
            initialized,
        },
    )]);
    let mut queue = VecDeque::from([0]);
    while let Some(pc) = queue.pop_front() {
        let instruction =
            &instructions[*indices.get(&pc).context("Invalid instruction address")?];
        let mut frame = frames[&pc].clone();
        let (pops, pushes) = match instruction.op {
            Op::Const(_) | Op::Load(_) => (0, 1),
            Op::Store(_) | Op::Pop | Op::If(_, _) | Op::Return | Op::Switch { .. } => (1, 0),
            Op::Call { args, .. } => (args, 1),
            Op::Dup => (1, 2),
            Op::Swap => (2, 2),
            Op::Neg => (1, 1),
            Op::Binary(_) => (2, 1),
            Op::Compare(_, _) => (2, 0),
            _ => (0, 0),
        };
        ensure!(
            frame.stack >= pops,
            "Operand stack underflow at bytecode {pc}"
        );
        if matches!(instruction.op, Op::Return) {
            ensure!(
                frame.stack == 1,
                "i32-v1 return requires exactly one stack value at bytecode {pc}"
            );
        }
        frame.stack = frame.stack - pops + pushes;
        ensure!(
            frame.stack <= code.max_stack as usize,
            "Operand stack exceeds max_stack at bytecode {pc}"
        );
        match instruction.op {
            Op::Load(index) | Op::Increment(index, _) => {
                ensure!(
                    index < frame.initialized.len(),
                    "Local index out of range at bytecode {pc}"
                );
                ensure!(
                    frame.initialized[index],
                    "Read of uninitialized local at bytecode {pc}"
                );
            }
            Op::Store(index) => {
                ensure!(
                    index < frame.initialized.len(),
                    "Local index out of range at bytecode {pc}"
                );
                frame.initialized[index] = true;
            }
            _ => (),
        }
        let successors = match instruction.op {
            Op::Return => Vec::new(),
            Op::Goto(dest) => vec![dest],
            Op::If(_, dest) | Op::Compare(_, dest) => vec![dest, instruction.next],
            Op::Switch { default, ref cases } => std::iter::once(default)
                .chain(cases.iter().map(|(_, dest)| *dest))
                .collect(),
            _ => vec![instruction.next],
        };
        for successor in successors {
            ensure!(
                indices.contains_key(&successor),
                "Execution falls off method at bytecode {pc}"
            );
            match frames.get_mut(&successor) {
                None => {
                    frames.insert(successor, frame.clone());
                    queue.push_back(successor);
                }
                Some(previous) => {
                    ensure!(
                        previous.stack == frame.stack,
                        "Inconsistent stack heights at merge bytecode {successor}"
                    );
                    let mut changed = false;
                    for (old, new) in previous.initialized.iter_mut().zip(&frame.initialized) {
                        let merged = *old && *new;
                        if merged != *old {
                            *old = merged;
                            changed = true;
                        }
                    }
                    if changed {
                        queue.push_back(successor);
                    }
                }
            }
        }
    }
    Ok(frames)
}

fn memory(offset: usize) -> String {
    format!("DWORD PTR [rsp+{offset}]")
}
fn immediate(value: i32) -> String {
    format!("0{:08X}h", value as u32)
}

fn compile_function(
    class: &ClassFile,
    method: &Method,
    symbol: &str,
    symbols: &BTreeMap<usize, String>,
) -> Result<CompiledMethod> {
    ensure!(
        class.super_name == "java/lang/Object"
            && class.interfaces == 0
            && class.fields == 0
            && class.access & 0x2600 == 0,
        "i32-v1 requires an ordinary Object subclass without fields or interfaces"
    );
    ensure!(
        !class.methods.iter().any(|method| method.name == "<clinit>"),
        "Class initialization is not implemented; <clinit> is rejected"
    );
    ensure!(
        class
            .name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"_$/".contains(&byte))
            && method
                .name
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || b"_$".contains(&byte)),
        "i32-v1 requires plain ASCII identifiers; control characters and assembler syntax are rejected"
    );
    ensure!(
        method.access & 0x0008 != 0 && method.access & (0x0020 | 0x0100 | 0x0400) == 0,
        "i32-v1 requires a static non-synchronized Java method"
    );
    let args = argument_count(&method.descriptor)?;
    let code = method
        .code
        .as_ref()
        .context("Selected method has no Code")?;
    ensure!(
        code.handlers.is_empty(),
        "Java exception handlers are not implemented"
    );
    let instructions = decode(code, class)?;
    let frames = verify(&instructions, code, args)?;
    // Every caller reserves the Win64 32-byte outgoing shadow space.
    let frame_bytes =
        (32 + (code.max_locals as usize + code.max_stack as usize) * 4 + 8).div_ceil(16) * 16 - 8;
    let frame_bytes = frame_bytes.max(8);
    let stack = |index: usize| memory(32 + (code.max_locals as usize + index) * 4);
    let local = |index: usize| memory(32 + index * 4);
    let mut lines = vec![
        "; Generated directly from JVM bytecode by BoomMinecraft i32-v2.".into(),
        format!(
            "; class={} method={}{}",
            class.name, method.name, method.descriptor
        ),
        format!("{symbol} PROC FRAME"),
        format!("    sub rsp, {frame_bytes}"),
        format!("    .allocstack {frame_bytes}"),
        "    .endprolog".into(),
    ];
    for (index, register) in ["ecx", "edx", "r8d", "r9d"].iter().enumerate().take(args) {
        lines.push(format!("    mov {}, {register}", local(index)));
    }
    for instruction in &instructions {
        let Some(frame) = frames.get(&instruction.pc) else {
            continue;
        };
        let depth = frame.stack;
        lines.push(format!("{symbol}_L_{}:", instruction.pc));
        lines.push(format!(
            "    ; bytecode {} {:?}",
            instruction.pc, instruction.op
        ));
        let mut emit = |text: String| lines.push(format!("    {text}"));
        match instruction.op {
            Op::Nop => emit("nop".into()),
            Op::Const(value) => emit(format!("mov {}, {}", stack(depth), immediate(value))),
            Op::Load(index) => {
                emit(format!("mov eax, {}", local(index)));
                emit(format!("mov {}, eax", stack(depth)));
            }
            Op::Store(index) => {
                emit(format!("mov eax, {}", stack(depth - 1)));
                emit(format!("mov {}, eax", local(index)));
            }
            Op::Pop => (),
            Op::Dup => {
                emit(format!("mov eax, {}", stack(depth - 1)));
                emit(format!("mov {}, eax", stack(depth)));
            }
            Op::Swap => {
                emit(format!("mov eax, {}", stack(depth - 1)));
                emit(format!("mov ecx, {}", stack(depth - 2)));
                emit(format!("mov {}, eax", stack(depth - 2)));
                emit(format!("mov {}, ecx", stack(depth - 1)));
            }
            Op::Neg => {
                emit(format!("mov eax, {}", stack(depth - 1)));
                emit("neg eax".into());
                emit(format!("mov {}, eax", stack(depth - 1)));
            }
            Op::Increment(index, value) => {
                emit(format!("add {}, {}", local(index), immediate(value)))
            }
            Op::Binary(binary) => {
                emit(format!("mov eax, {}", stack(depth - 2)));
                emit(format!("mov ecx, {}", stack(depth - 1)));
                emit(
                    match binary {
                        Binary::Add => "add eax, ecx",
                        Binary::Sub => "sub eax, ecx",
                        Binary::Mul => "imul eax, ecx",
                        Binary::And => "and eax, ecx",
                        Binary::Or => "or eax, ecx",
                        Binary::Xor => "xor eax, ecx",
                        Binary::Shl => "shl eax, cl",
                        Binary::Shr => "sar eax, cl",
                        Binary::Ushr => "shr eax, cl",
                    }
                    .into(),
                );
                emit(format!("mov {}, eax", stack(depth - 2)));
            }
            Op::If(condition, dest) => {
                emit(format!("mov eax, {}", stack(depth - 1)));
                emit("cmp eax, 0".into());
                emit(format!("{} {symbol}_L_{dest}", condition.jump()));
            }
            Op::Compare(condition, dest) => {
                emit(format!("mov eax, {}", stack(depth - 2)));
                emit(format!("cmp eax, {}", stack(depth - 1)));
                emit(format!("{} {symbol}_L_{dest}", condition.jump()));
            }
            Op::Goto(dest) => emit(format!("jmp {symbol}_L_{dest}")),
            Op::Switch { default, ref cases } => {
                emit(format!("mov eax, {}", stack(depth - 1)));
                for (key, dest) in cases {
                    emit(format!("cmp eax, {}", immediate(*key)));
                    emit(format!("je {symbol}_L_{dest}"));
                }
                emit(format!("jmp {symbol}_L_{default}"));
            }
            Op::Call { method, args } => {
                for (index, register) in ["ecx", "edx", "r8d", "r9d"].iter().enumerate().take(args)
                {
                    emit(format!("mov {register}, {}", stack(depth - args + index)));
                }
                emit(format!(
                    "call {}",
                    symbols.get(&method).context("Unlinked local method")?
                ));
                emit(format!("mov {}, eax", stack(depth - args)));
            }
            Op::Return => {
                emit(format!("mov eax, {}", stack(depth - 1)));
                emit(format!("add rsp, {frame_bytes}"));
                emit("ret".into());
            }
        }
    }
    lines.push(format!("{symbol} ENDP"));
    Ok(CompiledMethod {
        assembly: lines.join("\n") + "\n",
        argument_count: args,
        instruction_count: instructions.len(),
        linked_methods: 1,
    })
}

pub fn compile(class: &ClassFile, method: &Method) -> Result<CompiledMethod> {
    fn visit(
        class: &ClassFile,
        index: usize,
        active: &mut BTreeSet<usize>,
        done: &mut BTreeSet<usize>,
        order: &mut Vec<usize>,
    ) -> Result<()> {
        ensure!(
            !active.contains(&index),
            "Recursive call graph requires stack overflow handling; not implemented"
        );
        if done.contains(&index) {
            return Ok(());
        }
        ensure!(order.len() < 128, "i32-v2 call graph exceeds 128 methods");
        active.insert(index);
        order.push(index);
        let method = &class.methods[index];
        let code = method
            .code
            .as_ref()
            .context("Call target has no Java Code")?;
        for inst in decode(code, class)? {
            if let Op::Call { method, .. } = inst.op {
                visit(class, method, active, done, order)?;
            }
        }
        active.remove(&index);
        done.insert(index);
        Ok(())
    }
    let root = class
        .methods
        .iter()
        .position(|candidate| std::ptr::eq(candidate, method))
        .context("Method does not belong to class")?;
    let mut order = Vec::new();
    visit(
        class,
        root,
        &mut BTreeSet::new(),
        &mut BTreeSet::new(),
        &mut order,
    )?;
    let symbols: BTreeMap<usize, String> = order
        .iter()
        .enumerate()
        .map(|(n, index)| {
            (
                *index,
                if n == 0 {
                    "boom_entry".into()
                } else {
                    format!("boom_fn_{n}")
                },
            )
        })
        .collect();
    let mut assembly = String::from("option casemap:none\n.code\nPUBLIC boom_entry\n");
    let mut instructions = 0;
    let args = argument_count(&method.descriptor)?;
    for index in &order {
        let function = compile_function(class, &class.methods[*index], &symbols[index], &symbols)?;
        instructions += function.instruction_count;
        assembly.push_str(&function.assembly);
    }
    assembly.push_str("END\n");
    Ok(CompiledMethod {
        assembly,
        argument_count: args,
        instruction_count: instructions,
        linked_methods: order.len(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn check(
        bytes: Vec<u8>,
        locals: u16,
        stack: u16,
        args: usize,
    ) -> Result<BTreeMap<usize, Frame>> {
        // These verifier cases do not contain ldc or need a constant pool.
        let instructions = bytes
            .iter()
            .enumerate()
            .map(|(pc, byte)| Instruction {
                pc,
                next: pc + 1,
                op: match byte {
                    0 => Op::Const(0),
                    1 => Op::Return,
                    2 => Op::Load(0),
                    3 => Op::Store(0),
                    _ => Op::Goto(1),
                },
            })
            .collect::<Vec<_>>();
        verify(
            &instructions,
            &Code {
                bytes,
                max_locals: locals,
                max_stack: stack,
                handlers: Vec::new(),
            },
            args,
        )
    }
    #[test]
    fn rejects_underflow_and_uninitialized_locals() {
        assert!(check(vec![1], 1, 1, 0).is_err());
        assert!(check(vec![2, 1], 1, 1, 0).is_err());
        assert!(check(vec![2, 1], 1, 1, 1).is_ok());
    }
    #[test]
    fn invalid_descriptor_is_not_silently_lowered() {
        for descriptor in ["(J)I", "(I)J", "([I)I", "(IIIII)I"] {
            assert!(argument_count(descriptor).is_err());
        }
    }
    #[test]
    fn branches_cannot_enter_the_middle_of_an_instruction() {
        let instructions = vec![
            Instruction {
                pc: 0,
                next: 3,
                op: Op::Goto(1),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::Const(0),
            },
            Instruction {
                pc: 4,
                next: 5,
                op: Op::Return,
            },
        ];
        assert!(
            verify(
                &instructions,
                &Code {
                    bytes: vec![0; 5],
                    max_locals: 0,
                    max_stack: 1,
                    handlers: Vec::new()
                },
                0
            )
            .is_err()
        );
    }
    #[test]
    fn local_must_be_initialized_on_every_incoming_branch() {
        let instructions = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Const(1),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::If(Condition::Eq, 4),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Const(2),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::Store(0),
            },
            Instruction {
                pc: 4,
                next: 5,
                op: Op::Load(0),
            },
            Instruction {
                pc: 5,
                next: 6,
                op: Op::Return,
            },
        ];
        assert!(
            verify(
                &instructions,
                &Code {
                    bytes: vec![0; 6],
                    max_locals: 1,
                    max_stack: 1,
                    handlers: Vec::new()
                },
                0
            )
            .is_err()
        );
    }
    #[test]
    fn inconsistent_branch_merge_is_rejected() {
        let instructions = vec![
            Instruction {
                pc: 0,
                next: 1,
                op: Op::Const(1),
            },
            Instruction {
                pc: 1,
                next: 2,
                op: Op::If(Condition::Eq, 3),
            },
            Instruction {
                pc: 2,
                next: 3,
                op: Op::Const(2),
            },
            Instruction {
                pc: 3,
                next: 4,
                op: Op::Return,
            },
        ];
        assert!(
            verify(
                &instructions,
                &Code {
                    bytes: vec![0; 4],
                    max_locals: 0,
                    max_stack: 2,
                    handlers: Vec::new()
                },
                0
            )
            .is_err()
        );
    }
}
