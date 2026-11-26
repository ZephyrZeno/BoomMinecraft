# 汇编进程启动入口

`Build-VmEntry.ps1` 把已独立校验的原始 Java 汇编、运行时提供者对象和新生成的 VM 绑定表链接为原生 `boom-vm-entry.exe`。游戏执行路径不加载 C#／CLR、JVM 或 CRT。Python 只在构建时读取锁定输入，PowerShell 只构建、启动隔离进程和读取验证记录。

## v150 原版 System 三阶段正常返回

[第三阶段](SYSTEM_PHASE3.md)已在同一独立完整验证的 29 组源选择上实际完成。新的原生入口及 Report544/ABI13 解码器分别封存、独立校验后，原 System.initPhase1／2／3 正常返回，VM 级别到达 4；进程退出码 0、主 Context 0／depth0、两个后台线程退出并回收，清理标志 7。没有重新生成原 Java Code、赋写 VM 级别或用 JVM／CLR 执行。

实际入口 `.boom/vm-entry-images/v149-phase3-sealed-b` 的执行回执 SHA256 为 `007971a9a797da52215771f37e16d1c2112b15a27a0edb8827fd639554dd9da2`。Scoped 验收 `.boom/accepted-system-phase3-v150.json` 的 SHA256 为 `4850a6478d3a9f9be8868984478b724144811eb981ba0956c12d30f5220d3897`，286 个实际产物核对两遍，并归档 15 份工具／入口源。该状态仅证明原 System 三阶段在此前 29 组选择上的执行；未验收 31 组、Minecraft 入口、世界、完整 VM 或游戏优化性能。

## v149 原版 System 第一、二阶段正常返回（历史记录）

[正式 29 组输入](NATIVE_RUNTIME_29.md)的完整原生进程已正常完成原始 System.initPhase1 和 initPhase2，VM 初始化级别由 1 到达 2，主 Context 为 0，进程退出码为 0。完整选择含 5818 类、56665 个原 Java 方法与 149383 个汇编函数；独立来源校验自然退出 0，用时 626.968 秒。这些选择数量不计作全部都已执行。

两个后台原 Thread.exit 和 OS 记录回收各完成两次；工作者失败、最终监视器持有和锁均为零，引用等待／Object.wait 关闭以及清理标志 7 通过。448 字节 ABI11 报告 SHA256 为 `323ef50feaa5e0be74300949effcf2f55f1ba16ca05c58d02f2f2692f98e04a7`，实际执行回执为 `52c22140b4f765071fb296ece9e3985058d6c4a8cd271a442f55c363d419d96f`。Scoped accepted29 为 `.boom/accepted-native-modules-v149-29.json`，SHA256 `99f48017acc81733bab549d19b953588c1010cae8d098b500c4fda580077afea`。

完整原 Java 模块启动链已越过此前的 Module.defineModule0 停点。第三阶段、Minecraft 入口、世界、完整动态类加载和自动／并发内存回收尚未完成；完整 VM／游戏启动标志仍为 false。

## v146／v147 第 26／28 组原生进程（历史记录）

注册两组 Windows 路径／文件查询后，[正式 28 组输入](NATIVE_RUNTIME_28.md)的完整原生镜像已实际越过 WinNTFileSystem.canonicalize0 和 getBooleanAttributes0，新的停止点为 Module.defineModule0（42293，当前选择 row 105103）。源选择含 5374 类、50860 个原 Java 方法和 12704 格正常根，独立完整校验自然退出 0；原始 Phase1 返回、Phase2 进入但未完成。两个后台原 Thread.exit／记录回收、零工作者失败、零监视器持有和清理标志 7 均通过。

源／入口／执行散列、三个新组件的实际范围及 scoped accepted26 状态见[第 26 组验收记录](NATIVE_RUNTIME_26.md)。它不表示完整 VM 或游戏启动。

## v145 正式 23 包并行汇编进程（历史记录）

原生镜像已从完整独立校验的 4,056 类／37,546 Java 方法源选择，实际链接全部 23 个正式 provider 并执行。初始化源码按完整函数分为 48 个单元，另保留完整 diagnostic-stops；入口按封存顺序复用 49 个闭包 COFF。源码、类状态、正常根跨度与原 Java 方法保持来源绑定，详见[并行构建证据](PARALLEL_DIAGNOSTIC_ASSEMBLY.md)。

本轮原始 System.initPhase1 返回，System.initPhase2 已越过 ClassLoader.registerNatives，主线程真实停在未提供的 Reference.refersTo0（50141）；观察到调用方法 111859、PC 80。Phase2 未返回，VM 级别仍为 1，原生诊断退出码为 86。

引用处理与 Object.wait 两个等待域均完成停止和关闭；两个停止令牌全部消费，两个后台原 Thread.exit 与 OS 记录回收完成。工作者／信号失败状态、最终监视器持有数和注册表锁均为零，堆／注册表／Java 帧清理标志为 7。停止前活对象数为 8,021；这不是自动回收或完整引用处理的证明。

源选择 `.boom/diagnostic-startup/v145-native-class-loader-parallel-ec0736fc2365423ebb73fa7afb89c5ed/round-000` 的证明 SHA256 为 `bbeaeef00ce19d601e6585167383e0424c7cc4e5df87ee83c67acf027bd44f0c`。原生入口证明在 `.boom/vm-entry-images/ea06ed49ac6a4fc0a9943f74c5d8ef55/verification.json`，SHA256 为 `c2eb44e1acb7e3a8a719b2498767b8e483de9c7a3e1aec28ee2fe98ded3f5b7c`；执行回执 SHA256 为 `984f23e9fcf8eaee04c984a33d0fd94c6fbaee24afdd94aa167b3f8d57911d44`，448 字节 ABI11 原生报告 SHA256 为 `7bf48f2461d2c0d78a1da6acb869d41eb74d4658a6d375234c2a3bbf9c36a4ad`。

没有托管执行宿主、JVM 回退或 VM 绑定配置夹具。完整 System、Minecraft 入口、世界创建及游戏侧多核／GPU／内存优化仍待完成。

## v145 正式 22 包初始化进程（历史记录）

原生镜像选入 4,055 个类和 37,546 个原始 Java 方法，链接全部 22 个正式 provider；来源、精确 ASM、实际 COFF 及原生入口均独立验证后执行。原始 System.initPhase1 正常返回，System.initPhase2 随后调用，VM 级别保持 1，主线程真实停在未提供的 ClassLoader.registerNatives（41548）。Phase2 和 Minecraft 仍未完成。

此次合流包含 UFL2 窄字段原子规则、正式 BootLoader 模块发布和共享监视器等待。引用处理与 Object.wait 等待域均完成打开、停止及关闭，两个后台工作者各完成一次原始 Thread.exit 并回收；正常 run 返回数仍为零。两个停止令牌全部消费，工作者与信号失败状态为零，最终监视器持有数为零。堆、注册表和 Java 帧清理标志为 7。

源选择在 `.boom/diagnostic-startup/v145-native-boot-unnamed-40a5c3ea326e43c993fe3d8bef4841df/round-000`，独立证明 SHA256 为 `a2fbf9ecdf9a06d7e91a1886fe484d8fa90eef8918a67e03d24a456587e244de`。实际执行在 `.boom/vm-entry-images/a7c5084275e0419db074936e926fd155/execution.json`，SHA256 为 `5b8a96a3919a0706d0213b87de946b86e1a6717d5c29b50e1882fece19671457`。选入的方法数不代表全部方法均已执行。

## 已完成的实际执行

- v123 原生进程实际完成原版 `Thread.start`、`run`、`exit` 和 OS 记录回收，退出码 0，三项清理全部通过。验证对象是无 Runnable 任务的正常 Thread；详见[线程生命周期证据](NORMAL_THREAD_BOOTSTRAP.md)。
- 构造器入口自行建立 128 MiB 汇编堆，执行四个原始构造器入口及嵌套 FieldHolder，建立主线程和 system／main 线程组；原生进程退出码 0，实际对象数 95，堆／线程注册表／Java 帧全部清理成功。
- System 入口保留真实主线程，继续执行原始 `System.initPhase1`；实际到达尚未实现的 `Signal.handle0`，诊断退出码 86。停止时有 2,472 个管理对象，无监视器遗留，三项清理全部成功。
- PE 导入表只有自研汇编运行时和 Windows API，绑定表、类初始化调用、对象分配与构造调用都由汇编执行。此前开发宿主生成运行绑定的方式已从这条原生路径移除。

这些结果证明 VM 启动前缀的原生执行，不代表完整 System 或 Minecraft 已启动。当前 EXE 仍链接明确的失败诊断入口，没有把未实现功能变成空实现。

## 来源与复用

构造器 ID、原始 Code 散列、字段宽度和偏移、类初始化描述符、主线程名字常量及 VM 启动级别字段均从原始来源和已验证批次重新取得。绑定数据为 MASM 数据段，五个 VM 根单元也由汇编声明。

原始 Java 汇编保持不变；构建只重新汇编选定的原始代码并链接。新独立校验记录封存选择清单及诊断清单的 SHA-256，因此新的原生入口可以直接使用已核验的源选择，不依赖一次 C# 宿主运行。较早的证据仍使用已保存的执行记录和对应源码快照。

提供者缓存可以跨源字节相同、公开 ABI 相同的编译批次复用。编译器身份可以变化，原始类／方法／计划散列、IR 身份及布局／帧／上下文 ABI 必须保持一致；每次仍完整重建当前来源模型并校验实际 ASM／COFF，旧成功标志不能代替当前校验。

## 线程 ID 地址域

新版汇编运行时增加了独立的 VM 线程 ID 计数器域。经过正常 Unsafe 接收者校验后，NULL 基址的 Long 读取、volatile 读取、CAS 和 compare-exchange 只能访问当前注册表的准确计数器地址，且必须匹配拥有该注册表的堆。

共享注册表锁覆盖地址验证、整个访问及结果捕获；销毁使用独占锁。任意其他地址、不同堆、未对齐地址和不支持的操作返回明确错误，不提供一般堆外内存访问。该地址属于一个 VM 注册表生命周期，不能作为跨 VM 重建的持久引用。

内核验证通过 8 个工作者的 32,768 次无重复并发增量、15 项错误检查、销毁竞争和 4,096 次销毁后访问拒绝。

v120 服务端源选择与原生进程实际执行到普通 Thread 构造器。原始 `ThreadIdentifiers.next`／Unsafe 原子调用链返回并写入子线程 ID 2，停止时 VM 计数器为 3，主线程 ID 保持 1；这些值由汇编进程直接观察，没有测试宿主设置线程字段或预留 ID。该轮完整子线程构造停在 `AccessController.getStackAccessControlContext` 的真实 native 缺口。堆、注册表和帧清理全部成功。

原生记录升级为 112 字节 ABI2，分别记录构造完成标志和实际观察到的 ID，避免把已经分配 ID 误记为整个构造器完成。普通线程启动／退出和完整权限上下文尚未接入。

`-NativeProcess -ConstructChild` 是开发验证选项，用原始公开 Thread 构造器创建未启动的子线程，核对 ID 2、未启动状态以及主线程身份。它不创建工作线程任务，也不代替 Java `Thread.start`／`Thread.exit` 的实现。

## 正常权限上下文提供者

`normal-access-context-v1` 为锁定输入的原始 `AccessController` 提供三个 native：`getStackAccessControlContext`、`getInheritedAccessControlContext` 和 `ensureMaterializedForStackWalk`。执行部分为汇编；构建工具从原始声明、正常 ACC／Thread 字段布局及源帧元数据生成 ACCP192/2 绑定池。内部辅助过程为私有 COFF 符号，独立校验拒绝额外导出及未声明的导入。

栈查询检查当前 Context 的实际影子帧、PC 和方法身份，按声明类收集保护域；在原始 `executePrivileged` 帧读取局部变量中的 ACC 和调用者 Class，并按该边界停止。返回对象使用正常 ACC／ProtectionDomain[] 布局。继承查询读取实际当前线程的正常字段。协议语义参照 [OpenJDK 21 的 VM 入口](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/jvm.cpp)，原始类和方法的实际身份以本项目锁定输入为准。

只有原始 JDK bootstrap 类预绑定系统域。应用类、变换后类及后续模组类的保护域需要 VM 显式绑定；未知帧或未绑定域返回错误。域表使用汇编读写锁，写入要求帧池处于静止状态；已绑定的域身份不能替换。域根表被单独导出，但这不表示活动栈根、通用类加载或自动内存回收已经完成。

新提供者已通过三个原始 native 声明、501,044 条源帧视图、109,945 个类型槽、精确 ASM 和实际 COFF 的独立校验。另有十项来源边界检查，覆盖变换后来源、native 的 Code／访问位、域数组组件、字段宽度和特权帧伪造；全部 255 项 Python 测试通过。

v121 的独立原生进程一轮完成原始主线程／线程组／ACC 构造及公开子线程构造，原生退出码为 0，没有语义停止。记录直接观察主线程 ID 1、子线程 ID 2、下一 ID 3，子线程仍为 NEW，当前 OS 线程身份仍指向主线程。停止前有 116 个管理对象，监视器持有数和注册表锁均为零，堆／线程注册表／Java 帧三项清理全部通过。证据为 `.boom/diagnostic-startup/v121b-native-child-08636deb674a4ac79860f87ded3464b5/result.json`，独立 EXE 位于 `.boom/vm-entry-images/63ae5a726b194ab0b004628619c9c650`。

该轮未调用 `Thread.start`、`Thread.exit` 或 `System.initPhase1`，仍不代表完整 VM／游戏启动或完整权限上下文验收。应用域绑定、全部活动栈根和变换失效处理仍需继续实现。

启动器继续只有启动流程入口。完整原版、世界创建以及游戏侧多核／GPU／内存优化仍待完成。
