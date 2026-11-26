# 正常布局的调用者查询与生成方法调用栈

首个目标仍是 Minecraft Java 1.21.1。运行时实现为 `native/runtime/frames.asm`、`java_caller.asm` 和 `stack_probe.asm`；Rust 只负责读取来源、生成汇编与元数据。此项不是完整游戏启动、栈根扫描或自动内存回收。

## 要解决的问题

v108 的真实 `System.initPhase1` 诊断遇到未提供的 `Reflection.getCallerClass()`。原始来源计划中，类 4972 为 `java/lang/invoke/MethodHandles`，方法 47106 为 `lookup()Ljava/lang/invoke/MethodHandles$Lookup;`，包含该 native 的调用现场。此前文档把它误写为 `Constructor.newInstance`，现已更正；运行时始终使用原始来源 ID／注解，未依赖这个错误名称。Context32 中的 method／PC 是错误传播快照，返回过程中会更新，不能用它推测实际调用者，也不能由静态调用现场证明它已经执行完成。

批量后端现在为每个生成的 Java 方法加入原生栈上的 Node48：进入时连接当前线程 TLS，逐字节码更新 PC，正常返回和错误返回均解除连接。已有的两个会回调 Java 初始化器的类查找 native 也使用相同的带帧桥接；新的调用者 native 自身建立源 native 帧。其余当前服务未因此宣称具备所有 native 栈帧。

## 来源与安全标记

编译器从本轮已经校验过的原始 ClassFile 读取 Code、方法声明和 RuntimeVisibleAnnotations，不从方法名猜测 CallerSensitive。只有锁定的原始 bootstrap／platform JDK 来源可授予内部注解标记；应用类声明同名注解不能获得该权限。

调用者服务核对当前 native 帧、紧邻的 CallerSensitive 帧，再按安全栈遍历规则选择声明类，返回正常 Class 池中的规范镜像。Hidden 标记单独存在时不作为安全遍历的忽略条件。行为依据为 [OpenJDK 调用者查询](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/jvm.cpp)与[方法的安全栈遍历判定](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/oops/method.cpp)；代码实现为本项目的独立汇编服务。

## ABI

TracePool 仍为 48 字节，新增版本 3。Node 保留版本 2 与 48 字节布局，以兼容原有进入／退出内核；旧 Pool ABI2 的记录解释不变。

Pool ABI3 的 MethodRow32：

| 偏移 | 内容 |
| --- | --- |
| 0 | 原始方法 ID，DWORD |
| 4 | 方法标记，DWORD |
| 8 | 声明类型描述符指针，QWORD |
| 16 | Code 字节数；已记录的 native 为零，DWORD |
| 20 | 原始声明类 ID，DWORD |
| 24 | 保留，必须为零，QWORD |

标记为 constructor=1、fillInStackTrace=2、generated=4、CallerSensitive=8、Hidden=16、native=32、security-ignored=64、声明类型尚未提供=128。最后一种状态保持明确失败，不合成猜测的 Class。原始 Code 方法均有来源记录，是否已成功生成汇编另列。

CallerPool64/1 绑定正常 ClassPool、TracePool、源 getter 方法／类 ID 和记录／Context 大小。遍历核对池、行边界、PC、声明类型身份与同一 Context；跨开发宿主 Context 边界结束，不混入上一条嵌入调用链。错误沿 Context32 传播；本项不据此宣称完整 Throwable 对象物化。

帧数据与 caller native 分成两个 COFF 单元。普通 Java 链接帧数据时无需选择 Reflection 初始化器；真正选择 caller native 后，才引入相应源类描述符和 Class 镜像依赖。DLL 只导出池与释放入口等必要符号，不把几十万条方法记录全部作为 PE 导出。

## 生命周期与大帧

同一 Context 的外层进入持有池租约，内部帧复用该租约；线程的 TLS 链相互独立。活动租约存在时拒绝释放。开发宿主只在所有 Java 调用返回后释放 TLS 池，再卸载映像；诊断停止时仍不得强行释放 Java 持有的监视器。

记录帧增加原生栈用量。生成器对较大帧先调用本项目的 `boom_stack_probe` 逐页触碰，再调整 RSP；特殊序言 ABI 保留 RAX 和四个参数寄存器。操作系统保留栈耗尽向 Java StackOverflowError 的完整转换仍未实现，现有调用深度限制继续有效。

## 独立校验与实际范围

`verify-batch-frames.py` 从锁定来源的真实 class 字节重新解析方法和注解，核对类／Code 散列、声明 ID、标记、元数据、生成汇编与实际 COFF。普通方法部分另核对 Node 布局、进入／退出、PC 映射和大帧序言。它是来源及结构校验，不把整个输入的每个方法宣称为已经执行。

`Test-NormalCaller.ps1` 是明确的开发夹具：测试 TLS／元数据、CallerSensitive、Hidden 与安全忽略、Context 边界、已有错误、旧 ABI2 和释放生命周期。8 工作者执行 8,192 次并发查询；独立汇编夹具另执行 640 次实际 64 KiB 栈增长和参数寄存器保持检查，30 项错误／生命周期检查通过。这些夹具不创建正常 Class 镜像，也不执行原始 Java；真实源执行证据单独记录。

本轮两侧全量生成仍为服务器 498,179、客户端 562,769 个 Java 方法。帧来源记录分别为 498,909／563,773 条，包含原始 Code 方法和三个需记录的 native。声明类型未提供的记录分别为 268／392 条；不据此删除失败来源或提高完整运行时完成度。

两侧批次已通过完整来源／帧／COFF 校验。两侧原始 System 诊断均进入 Reflection 所需的初始化链，停止于 `CDS.getRandomSeedForDumping()`；它发生在新的 native 桥接完成声明类初始化之前。因此，Reflection 初始化完成与原始 `getCallerClass` 调用点的返回行为仍未获得这次启动验证，不能把“已提供入口”写成“已经运行通过”。

服务端正常类查找回归已用本轮带帧映像重跑：34,945 个名字分别执行 forName0 和 bootstrap 服务，44 个原始公开 forName 对照、原始枚举 getter、8 工作者冷初始化和 4,096 次并发热查找通过。模块对象仍是明确的正常布局准备夹具，没有执行 Module 构造和完整模块引导；ClassLoader 原始初始化也未执行。客户端这项全表执行沿用 v108 证据，本轮不宣称已重跑。

开发诊断入口会核对帧所需内核与运行时 DLL 的构建身份，拒绝把 ABI3 批次误接到旧运行时。原始诊断宿主和本轮类查找宿主在卸载映像前检查帧池已静止并释放 TLS。

尚未覆盖活动栈根、安全点、完整 Throwable 回溯、任意 native 上调、continuation／JVMTI 包装帧、模组变换后的映射和完整游戏启动。未来自动展开的合成类型／方法必须登记父来源和帧语义，不能直接把 helper 当作原始调用者。
