# 原始终结策略查询

`normal-finalization-policy-v1` 绑定锁定 bootstrap `java/lang/ref/Finalizer.isFinalizationEnabled()Z`（50096），保留原始私有静态 native 标志和 `ENABLED:Z` 静态 final 字段。VM 使用与原始默认配置相同的启用策略；汇编服务读取被冻结的布尔配置，不替换原始 Java 终结类、构造器或线程。

该入口只查询策略。原始实现经 [Finalizer.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/Finalizer.c) 进入 VM 查询；本项目不链接或调用该 JVM 实现。终结对象登记、引用发现、自动回收及完整终结执行仍未完成；同类的 reportComplete native 尚未绑定。

开发对照程序 `java/reference/FinalizationPolicyReference.java` 在锁定 JVM 上读取原始 ENABLED 字段，分别验证默认、显式 enabled、显式 disabled，结果为 true、true、false。只在开发命令中使用 JVM，并记录锁文件、可执行文件、源程序、class 与脚本摘要；没有 JVM 游戏运行回退。最新证据由 `.boom/latest-finalization-policy-oracle.txt` 指向。

新提供者已通过原始声明／字段来源、精确 ASM、实际 COFF 与禁止替换已有 native 的独立校验，全部 295 项 Python 检查通过。

## 实际原生执行

`.boom/diagnostic-startup/v127-native-System-finalization-ff0fed7065cc42e1bf601316cc09802d/result.json` 保留 5,370 个原始 Java 方法；独立 EXE 位于 `.boom/vm-entry-images/3dc8da82e0ef4b29bddf615e6a5eab67`。实际越过策略查询，引用处理和终结两个工作者均请求原始 run 分派；优先级应用、启动、分派请求、原始 Thread.exit 与记录回收各为 2，正常 run 完成数为 0。该计数发生在调用分派表前，尚不能证明目标子类 run 方法体实际执行。

共享诊断记录的首个缺口为 `Object.notifyAll()V`（42393），来源调用者为 `NativeReferenceQueue`（5163）的 50118 方法。工作者首个失败 Context 为 kind45057、method0、pc0；单靠这些坐标仍不能识别其独立来源诊断行。后续需要为每个 Context 保留实际诊断行，避免并发工作者只共享一个首错记录。

本轮停止时持有一个监视器，注册表锁为零，清理标志为 6：注册表和 Java 帧显式清理完成，堆未显式释放，由隔离测试进程退出回收。不能将它记录成清理7或正常 System 完成。现有汇编通知内核只支持经过检查的空 Java 等待集合，下一步需把正常 Object.notify／notifyAll 声明接到该内核，并继续实现真实等待、中断和控制展开中的监视器释放。

Java 批次和 86 源文件汇编运行时保持不变；15 个旧模块和帧视图重新校验，仅新增此策略模块。另行实现并测试的[待处理引用内核](REFERENCE_PENDING_RUNTIME.md)尚未接入当前运行时。完整 System、VM、Minecraft、世界与游戏优化均未完成。
