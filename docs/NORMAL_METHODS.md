# 正常布局的原方法反射候选

`scripts/normal-methods-source.py` 从锁定的原 classfile 读取方法目录，
`native/providers/normal_methods.asm.inc` 执行
`Class.getDeclaredMethods0(boolean)`。当前为独立候选，未登记 provider family，
未修改交付 runtime DLL、原 Java Code、Class 初始化状态或正常 JCLS 模块目录。

目录按实际 defining loader、原 class SHA、原 method-table slot 和描述符绑定。
返回本类声明的方法，排除 `<init>` 和 `<clinit>`，保留 bridge、synthetic、
native、abstract 和可变参数标志；`publicOnly` 只筛选 ACC_PUBLIC。
primitive/array Class 返回正常的空 `Method[]`。返回顺序采用原 classfile 顺序，
不要求与 HotSpot 内部重排顺序相同。

每个 Method 都使用正常布局、正常 Class mirrors、typed `Class[]` 和 `byte[]`。
方法名通过现有 ASM String interner 登记；签名保留原 UTF16。
String 工厂读取本批 compact_strings 配置，Latin1 与 UTF16 coder 均按正常表示生成。
ASM 调用原 `Method` 构造器写入 clazz、name、parameterTypes、returnType、
exceptionTypes、modifiers、slot、signature、annotations、parameterAnnotations
和 annotationDefault。原 `Class.getDeclaredMethod` 的查找、过滤、缓存、
ReflectionFactory 和 `Method.copy` Java 代码保留。

枚举不要求被反射方法的 Java Code 已选入镜像，也不会初始化 declaring class。
它要求原类型目录、Class mirror 和真实 loader/module 绑定可用，以及原 Method
构造器等实际 upcall 已选入。缺失或当前不可绑定的类型保留 Context20。
本目录不把缺失方法代码变成可调用代码，不实现 `invoke0`。

Signature、Exceptions、RuntimeVisibleAnnotations、RuntimeVisibleParameterAnnotations、
AnnotationDefault、RuntimeVisibleTypeAnnotations 和 MethodParameters 均绑定原字节；
缺失属性与存在但为空的属性分开记录。提供这些原始数据不代表常量池 native、
注解解析器、泛型仓库或 `Executable.getTypeAnnotationBytes0` 已实现。
原 classfile slot 属于本 AOT 目录，不能当作另一个 HotSpot 进程的 idnum。
后续 invoke adapter 必须重新验证 owner/slot/descriptor 对应的原方法和实际已选代码。

目录只接收锁定原 classfile；重定义、变换链和动态生成类需要新目录版本及失效校验，
不能继续沿用这里的原始目录。当前 GC 为显式静止点收集，未宣称自动栈根。

候选工具会重新生成完整 ASM，逐项验证原 native frame，并用固定 ML64 独立重汇编。
实际 AMD64 COFF 的执行节、节标志、指令与数据、重定位目标及 addend、非调试主符号、
`.pdata` 和 `.xdata` 必须与规范产物相等；文件名、调试节和物理文件偏移不参与执行比较。

开发组件使用已独立验证的原 Main source selection，精确移除该 native 的一处
fail-only stop，其余 Java/COFF 保留。测试构造前缀使用正常 VM 绑定池和原 primordial
构造器，不改 Java 字段来补初始化。source/API 首败和失败目录保留。
组件结果只说明方法枚举及原 Java 查找/复制范围，不代表服务器帮助、世界或完整游戏启动。

已完成的独立冷执行为 `.boom/normal-methods/execution-v152-e/execution.json`。
它复用 d 目录未改的 DLL，在新 OS 进程、新 heap 和冷 Java 状态中执行：7 个原类、
primitive/array 的空表、298 条与锁定 JDK 的无序方法对照、原构造器/getters、原
`Class.getDeclaredMethod` 和 `Method.copy`、8 OS 工人共 128 次并发调用、bad input、
已有 Context、4 次标准根静止点 GC、真实分配失败及 GC 后恢复。
registry、frame TLS 和 heap 均清理完成。d 目录原 OOM 测试失败保留：大块分配失败
并不能证明小对象已无法分配；e 按更小粒度耗尽尾部并保存实际 Context3 观察。

d 候选的源码、frame、规范 ASM、实际 COFF 及独立重汇编证明位于
`.boom/normal-methods/source-bound-v152-d/verification.json`。
另一个拥有进程的派生前缀已在原 System 三阶段后越过此 native，下一实际边界为
`Class.getConstantPool`；证据为 `.boom/normal-methods/main-prefix-v156-a/result.json`。
该前缀是独立候选实验，不能替代正式 provider 选择和完整 source verification。

根独立重新构造并验证 d 的全部来源、ASM 与规范机器 COFF 后，独立删除同一处
native stop、重新 ML64 并保留原 Main 的全部 Java／数据对象和原 VM 入口对象。
实际派生进程完成 System123／VM4，停在原 `Class.getConstantPool`，Main 方法体仍
未调用；两个工人退出／回收均2，failure0、cleanup7，ASM 根快照非空2540。
该回执 SHA256 为 `9724d2c0aef835a73117b6a1c6dbe85ae9486a34886f696d4b08c781f93cbf3a`，
独立原 ABI14 解码结果为 `ead2ddecb9911b3d7dac0828141fdea137b0a3229a9d21f35003ffdfa85b95eb`。

随后工具清单切换后，对旧105输入的根 API 复跑被原验证器严格拒绝，未运行 guest，
失败保留于 `.boom/normal-methods/root-review-execution-v156-a`。不会把旧收据改成当前
107来源；新的当前 frame／provider 迁移和独立冷复跑继续单独验证。

当前工具来源的冷复跑现已完成：新候选只接受明确 `accepted` 或
`pending_runtime_acceptance` 的已完整源验输入，核对当前全部工具与 fresh frame；
pending 的运行验收／发布标志必须保持 false。开发执行器仅在显式
`--allow-equivalent-batch` 且完整 named batch／原 Java／机器数据等价证明完全匹配
迁移状态后复用历史 Java 闭包，不改称当前完整 source selection 已复验。
17项源码／机器／状态边界测试及新 OS 冷进程的全部 API suite 通过。
`.boom/normal-methods/root-source-current107-v159-a/verification.json` 为
`328a89f3e0fce6246fd38e7cb223a454f6076035e27700f216e6ad2f3094dd98`；
`.boom/normal-methods/root-current107-execution-v159-a/execution.json` 为
`1c081480354b3e5a0654fbd58781c82bf454df5e736577903a6a6d557f935bc3`。
