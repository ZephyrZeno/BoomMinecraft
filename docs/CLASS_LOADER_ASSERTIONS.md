# 正常 ClassLoader 登记与断言快照候选

汇编候选接入原始 ClassLoader 的 `registerNatives`（41548）与 `retrieveDirectives`（41631）。前者核对唯一的真实目标后原子发布登记状态；后者读取已经登记的 JCBT 应用默认值，创建正常 AssertionStatusDirectives 对象和四个独立的带类型空数组，再写入原始五个字段。

系统和应用默认值保持独立。类／包覆盖规则当前不受支持，非空规则、未知选项或错误类型显式拒绝。四种默认组合在测试宿主中于原始 Class.registerNatives 之前设置，代表开发启动配置；没有手动设置任何 Java 类的初始化状态。交付批次仍固定两个默认值均关闭。

## 实际验证

- 对照进程确实停在尚未绑定的 41548；候选执行原始 ClassLoader 初始化器，完成 nocerts 和 assertionsDisabled 静态字段赋值。
- 四组启动默认值均通过，两次 retrieve 产生十个不同的正常对象与 typed 数组，字段与默认值正确；[独立锁定 JDK 对照](NORMAL_CLASS_BOOTSTRAP.md#classloader-断言快照对照2026-11-26)验证参考语义。
- 八个 OS 线程并发冷初始化和读取，共得到四十个不同对象，全部调用后 guest 帧深度为零。
- 未登记、错误池、非法配置、已有异常、三十二次重复登记及实际填满堆后的分配失败均通过。OOM 验证的是待处理错误上下文。
- AssertionStatusDirectives 的原始冷描述符、Object 依赖初始化函数和失败根由已验证批次精确抽取。新增失败根实际登记进 GC 根跨度；静止收集释放一个垃圾对象，十个快照对象全部保留。

九组执行记录在 `.boom/class-loader-assertions/execution-v145-b/result.json`，SHA256 为 `90f2dabfe291202a31572d7382db4c3d83a8a7871c78862a005730b47e32273c`。候选不会调用这个 VM 分配对象的 Java 构造器。

正式 source 模型另行声明所需的 AssertionStatusDirectives、Class 和 ClassLoader，使常规选择器真正纳入描述符与根。预检产出的指令、数据、unwind 及按名称归一化的重定位与已执行候选相同，仅规范化 CodeView 中的对象路径。该模型现已登记为 `normal-class-loader-assertions-v1`。

## 正式第 23 包验收

新帧、22 个旧包的当前源码重验和新 ClassLoader 包的独立验证全部通过，原 Java 批次及运行时 DLL 未重建。accepted23 状态为 `.boom/pending-native-class-loader-v145-23-23a1a5d3dc5646749ab64939274c821d.json`，SHA256 为 `a1250a1205e74deb37aae6f8a86e4308f60feef31e9f073b5dcad8ac2a8ae680`。

正式冷测另建 1,018 类／4,444 个 Java 方法的源镜像，从 23 包清单实际选入 18 包。AssertionStatusDirectives 由 provider 依赖选入，未放入手工类根或 admitted_classes；其失败根位于正常 3,102 格静态根 bank。完整源码／ASM／COFF 校验后，四种默认值、八个 OS 线程、异常／重复调用、OOM 和实际 GC 共八组全部通过；没有 scratch 补充或手写类初始化状态。

执行记录在 `.boom/class-loader-assertions/formal-execution-v145-23-exports-23a1a5d3dc5646749ab64939274c821d/result.json`，SHA256 为 `081bc4c080b3276d5c5f2c06baecd741ad1a0b1df9427cdf0bfdbcafbb208cfd`。首次尝试缺少只读观察导出，日志保留；后续独立链接先复现已验证基线，再仅增加三个观察导出，源码和 COFF 输入均未改。

## 原版进程前沿与范围

正式 23 包现已合流进完整的源初始化选择：4,056 个类、37,546 个原 Java 方法和 8,920 格正常静态根，全部 23 个 provider 实际链接。独立源码／ASM／COFF 与原生入口校验后，原始 System Phase1 返回，Phase2 实际越过 ClassLoader.registerNatives，推进到尚未提供的 Reference.refersTo0（50141）。两个后台原 Thread.exit 及记录回收完成，工作者失败与监视器持有数为零，全部清理标志为 7。

源选择为 `.boom/diagnostic-startup/v145-native-class-loader-parallel-ec0736fc2365423ebb73fa7afb89c5ed/round-000`，证明 SHA256 为 `bbeaeef00ce19d601e6585167383e0424c7cc4e5df87ee83c67acf027bd44f0c`；实际执行在 `.boom/vm-entry-images/ea06ed49ac6a4fc0a9943f74c5d8ef55/execution.json`，SHA256 为 `984f23e9fcf8eaee04c984a33d0fd94c6fbaee24afdd94aa167b3f8d57911d44`。本轮使用可选并行源分组汇编，没有 scratch 补充或手动设置类初始化状态。

以下开发观察保留为早期定位记录：

保留原 Java 目标文件的开发拥有进程已实际返回 System Phase1、进入 Phase2，接入候选后越过 ClassLoader.registerNatives，推进到未选入的 WeakHashMap.isEmpty（67260）。记录为 `.boom/vm-entry-sparse-probes/class-loader-2ae2db85b9fd43528024025b119980c7/observations.json`。

这个旧入口仍保留旧引用服务和 Object.wait 缺口，没有完成整套选择复验，也没有将补充类失败根接入旧入口的标准根跨度；该进程不执行自动 GC。独立候选的 GC 测试与此进程前沿分别记录。

独立冷初始化基线未执行 Java initializeJavaAssertionMaps／desiredAssertionStatus 的完整接收者调用流程，因此不宣称验证了 Java 断言 Map API。正式进程已越过登记这一启动前缀，完整 System 第二阶段和 Minecraft 启动仍待完成。
