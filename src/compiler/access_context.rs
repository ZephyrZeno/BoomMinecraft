//! VM access-control context capture from actual AOT shadow frames. Protection
//! domains are VM-assigned, rooted and immutable after binding, never guessed.
use super::{classfile::ClassFile, frames, numeric, program::ProgramObjectLayout, types};
use crate::{bytecode::ClassOrigin, files};
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
pub const OWNER: &str = "java/security/AccessController";
pub const CONTEXT: &str = "java/security/AccessControlContext";
pub const DOMAIN: &str = "java/security/ProtectionDomain";
pub const REFLECTION: &str = "jdk/internal/reflect/Reflection";
const MEMBERS: [(&str, &str, u16); 3] = [
    (
        "getStackAccessControlContext",
        "()Ljava/security/AccessControlContext;",
        0x10a,
    ),
    (
        "getInheritedAccessControlContext",
        "()Ljava/security/AccessControlContext;",
        0x108,
    ),
    (
        "ensureMaterializedForStackWalk",
        "(Ljava/lang/Object;)V",
        0x10a,
    ),
];
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u32)]
pub enum Operation {
    Stack,
    Inherited,
    Materialize,
    CallerClass,
}
impl Operation {
    pub(super) fn resolve(owner: &str, name: &str, desc: &str) -> Option<Self> {
        if owner == REFLECTION && name == "getCallerClass" && desc == "()Ljava/lang/Class;" {
            return Some(Self::CallerClass);
        }
        if owner != OWNER {
            return None;
        }
        MEMBERS
            .iter()
            .position(|m| m.0 == name && m.1 == desc)
            .map(|i| match i {
                0 => Self::Stack,
                1 => Self::Inherited,
                _ => Self::Materialize,
            })
    }
    pub(super) fn descriptor(self) -> &'static str {
        if self == Self::CallerClass {
            "()Ljava/lang/Class;"
        } else {
            MEMBERS[self as usize].1
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Binding {
    pub caller: ClassOrigin,
    pub constant: u16,
    pub operation: Operation,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MethodView {
    pub method: usize,
    pub type_id: usize,
    pub privileged: bool,
    pub caller_sensitive: bool,
    pub security_ignored: bool,
    pub locals_displacement: i32,
    pub max_locals: u16,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub abi: u32,
    pub origin: ClassOrigin,
    pub context_origin: ClassOrigin,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reflection_origin: Option<ClassOrigin>,
    pub owner: usize,
    pub context: usize,
    pub thread: usize,
    pub domain: usize,
    pub context_type: usize,
    pub thread_type: usize,
    pub domain_type: usize,
    pub domain_array: usize,
    pub domain_layout: numeric::ObjectLayout,
    pub bindings: Vec<Binding>,
    pub methods: Vec<MethodView>,
    pub entry: Option<(usize, Operation)>,
    pub native_source_sha256: String,
    pub application_domains_require_explicit_binding: bool,
    pub automatic_gc: bool,
}
impl Plan {
    pub(super) fn new(
        registry: &mut types::Registry<'_>,
        ids: [usize; 4],
        domain_layout: numeric::ObjectLayout,
    ) -> Result<Self> {
        let mut origins = Vec::new();
        let mut tids = Vec::new();
        for owner in [OWNER, CONTEXT, "java/lang/Thread", DOMAIN] {
            let id = registry.class("bootstrap", owner)?;
            let types::Type::Class { origin, key, .. } = &registry.types[id] else {
                unreachable!()
            };
            ensure!(
                key.loader == "bootstrap"
                    && origin.source_id == "jdk:java.base"
                    && origin.generated.is_none(),
                "Access contexts require original java.base classes"
            );
            origins.push(origin.as_ref().clone());
            tids.push(id);
        }
        for (name, desc, flags) in MEMBERS {
            let m = registry
                .definition(tids[0])
                .unwrap()
                .method(name, Some(desc))?;
            ensure!(
                m.access == flags && m.code.is_none(),
                "AccessController native declaration changed: {name}"
            );
        }
        let domain_array = registry.field("bootstrap", "[Ljava/security/ProtectionDomain;")?;
        Ok(Self {
            abi: 1,
            origin: origins.remove(0),
            context_origin: origins.remove(0),
            reflection_origin: None,
            owner: ids[0],
            context: ids[1],
            thread: ids[2],
            domain: ids[3],
            context_type: tids[1],
            thread_type: tids[2],
            domain_type: tids[3],
            domain_array,
            domain_layout,
            bindings: Vec::new(),
            methods: Vec::new(),
            entry: None,
            native_source_sha256: files::digest_bytes(include_bytes!(
                "../../native/runtime/access_context.asm"
            ))
            .sha256,
            application_domains_require_explicit_binding: true,
            automatic_gc: false,
        })
    }
    pub(super) fn bind(
        &mut self,
        caller: &ClassFile,
        source: &ClassOrigin,
        constant: u16,
        op: Operation,
    ) -> Result<()> {
        let (owner, name, desc, interface) = caller.static_method_reference(constant)?;
        ensure!(
            !interface && Operation::resolve(&owner, &name, &desc) == Some(op),
            "Access context callsite changed"
        );
        if op == Operation::CallerClass {
            ensure!(
                self.reflection_origin.is_some(),
                "CallerClass requires verified Reflection declaration"
            );
        } else if op == Operation::Inherited {
            ensure!(
                source.loader == "bootstrap"
                    && caller.name.rsplit_once('/').map(|x| x.0) == Some("java/security"),
                "Inherited access context requires its bootstrap runtime package"
            );
        } else {
            ensure!(
                source == &self.origin && caller.name == OWNER,
                "Private AccessController native requires its original caller"
            );
        }
        if !self
            .bindings
            .iter()
            .any(|b| b.caller == *source && b.constant == constant)
        {
            self.bindings.push(Binding {
                caller: source.clone(),
                constant,
                operation: op,
            });
            self.bindings.sort_by(|a, b| {
                (&a.caller.binary_name, a.constant).cmp(&(&b.caller.binary_name, b.constant))
            });
        }
        Ok(())
    }
    pub(super) fn finish(
        &mut self,
        trace: &frames::Plan,
        classes: &[ClassFile],
        registry: &types::Registry<'_>,
    ) -> Result<()> {
        for m in &trace.methods {
            let class = classes
                .iter()
                .find(|c| c.name == m.class_name)
                .context("Missing access-context frame class")?;
            let code = class
                .method(&m.name, Some(&m.descriptor))?
                .code
                .as_ref()
                .context("Missing frame source Code")?;
            let privileged = m.class_name == OWNER && m.name == "executePrivileged";
            let original_holder = super::jdk_bridges::original_holder(registry, class, &m.source)?;
            let trusted = original_holder.is_some()
                || (m.source.loader == "bootstrap" && m.source.source_id == "jdk:java.base");
            let annotations = &class
                .method(&m.name, Some(&m.descriptor))?
                .runtime_visible_annotations;
            let caller_sensitive = trusted
                && annotations
                    .iter()
                    .any(|a| a == "Ljdk/internal/reflect/CallerSensitive;");
            let accessor = registry.types.iter().position(|t| matches!(t, types::Type::Class {key,..} if key.loader == "bootstrap" && key.name == "jdk/internal/reflect/MethodAccessorImpl"));
            let security_ignored = trusted
                && ((m.class_name == "java/lang/reflect/Method"
                    && m.name == "invoke"
                    && m.descriptor
                        == "(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;")
                    || accessor.is_some_and(|id| registry.assignable(m.type_id, id))
                    || annotations
                        .iter()
                        .any(|a| a == "Ljava/lang/invoke/LambdaForm$Compiled;"));
            if privileged {
                ensure!(
                    m.source == self.origin
                        && code.max_locals >= 3
                        && (m.descriptor
                            == "(Ljava/security/PrivilegedAction;Ljava/security/AccessControlContext;Ljava/lang/Class;)Ljava/lang/Object;"
                            || m.descriptor
                                == "(Ljava/security/PrivilegedExceptionAction;Ljava/security/AccessControlContext;Ljava/lang/Class;)Ljava/lang/Object;"),
                    "Privileged frame source signature changed"
                );
            }
            self.methods.push(MethodView {
                method: m.id,
                type_id: original_holder.unwrap_or(m.type_id),
                privileged,
                caller_sensitive,
                security_ignored,
                locals_displacement: -8 * (i32::from(code.max_locals) + i32::from(code.max_stack)),
                max_locals: code.max_locals,
            });
        }
        Ok(())
    }
    pub(super) fn prepare_reflection(&mut self, registry: &mut types::Registry<'_>) -> Result<()> {
        let id = registry.class("bootstrap", REFLECTION)?;
        let types::Type::Class { origin, key, .. } = &registry.types[id] else {
            unreachable!()
        };
        ensure!(
            key.loader == "bootstrap"
                && origin.source_id == "jdk:java.base"
                && origin.generated.is_none(),
            "CallerClass requires original Reflection definition"
        );
        let m = registry
            .definition(id)
            .unwrap()
            .method("getCallerClass", Some("()Ljava/lang/Class;"))?;
        ensure!(
            m.access == 0x109
                && m.code.is_none()
                && m.runtime_visible_annotations
                    .iter()
                    .any(|a| a == "Ljdk/internal/reflect/CallerSensitive;"),
            "Reflection.getCallerClass native/annotation changed"
        );
        self.reflection_origin = Some(origin.as_ref().clone());
        Ok(())
    }
    pub(super) fn emit(
        &self,
        out: &mut String,
        layouts: &[ProgramObjectLayout],
        types: &[types::Type],
    ) -> Result<()> {
        let layout = |owner| -> Result<&numeric::ObjectLayout> {
            Ok(&layouts
                .iter()
                .find(|l| l.class_id == owner)
                .context("Missing access context executable layout")?
                .layout)
        };
        let offset = |owner, name: &str| -> Result<usize> {
            Ok(layout(owner)?
                .fields
                .iter()
                .find(|f| f.name == name)
                .context("Missing access context VM field")?
                .offset)
        };
        out.push_str("EXTERN boom_access_context_query:PROC\nEXTERN boom_access_bind_domain:PROC\n.const\nALIGN 8\n");
        out.push_str(&format!(
            "boom_access_pd_layout DWORD 04F424A43h,{}\n    QWORD {}\n    DWORD {},{}\n",
            self.domain_layout.abi,
            self.domain_layout.payload_bytes,
            self.domain_layout.reference_prefix_fields,
            self.domain_layout.fields.len()
        ));
        let count = self.methods.iter().map(|m| m.method + 1).max().unwrap_or(1);
        out.push_str("boom_access_methods LABEL BYTE\n");
        for id in 0..count {
            if let Some(m) = self.methods.iter().find(|m| m.method == id) {
                let flags = u32::from(m.privileged)
                    | (u32::from(m.caller_sensitive) << 1)
                    | (u32::from(m.security_ignored) << 2);
                out.push_str(&format!("    QWORD OFFSET boom_trace_method{id}\n    DWORD {},{flags}\n    SDWORD {}\n    DWORD {}\n    QWORD 0\n",m.type_id,m.locals_displacement,m.max_locals));
            } else {
                out.push_str("    QWORD 0,0,0,0\n");
            }
        }
        out.push_str(".data\nALIGN 4\nboom_access_domain_bound LABEL DWORD\n");
        for t in types {
            let bound = match t {
                types::Type::Class { key, .. } => key.loader == "bootstrap",
                _ => true,
            };
            out.push_str(&format!("    DWORD {}\n", u32::from(bound)));
        }
        out.push_str(&format!("ALIGN 8\nboom_access_pool DWORD 050434341h,1,4,0\n    QWORD OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_mirror_pool,OFFSET boom_trace_pool\n    QWORD OFFSET boom_class{},OFFSET boom_layout{},OFFSET boom_t{},OFFSET boom_thread_registry_ptr\n    QWORD OFFSET boom_t{},OFFSET boom_t{}\n    DWORD {},{},{},{},{},{}\n    QWORD OFFSET boom_access_domain_roots,OFFSET boom_access_domain_bound,OFFSET boom_access_methods\n    DWORD {count},0\n    QWORD OFFSET boom_t{},0,0,0,0\n.code\nPUBLIC boom_get_access_context_pool\nboom_get_access_context_pool PROC\n    lea rax,boom_access_pool\n    ret\nboom_get_access_context_pool ENDP\n",self.context,self.context,self.domain_array,self.context_type,self.domain_type,offset(self.context,"context")?,offset(self.context,"privilegedContext")?,offset(self.context,"isPrivileged")?,offset(self.context,"isAuthorized")?,offset(self.thread,"inheritedAccessControlContext")?,types.len(),self.thread_type));
        if let Some((entry, op)) = self.entry {
            out.push_str(&format!("boom_m{entry} PROC FRAME\n    sub rsp,56\n    .allocstack 56\n    .endprolog\n    mov QWORD PTR [rsp+32],rcx\n    mov QWORD PTR [rsp+40],rdx\n    lea rcx,boom_class{}\n    mov rdx,QWORD PTR [rsp+32]\n    call boom_class_ensure\n    test eax,eax\n    jnz boom_access_entry_error\n    mov rcx,QWORD PTR [rsp+32]\n    mov rdx,QWORD PTR [rsp+40]\n    lea r8,boom_access_pool\n    mov r9d,{}\n    call boom_access_context_query\n    jmp boom_access_entry_done\nboom_access_entry_error:\n    xor eax,eax\nboom_access_entry_done:\n    add rsp,56\n    ret\nboom_m{entry} ENDP\n",self.owner,op as u32));
        }
        Ok(())
    }
}
