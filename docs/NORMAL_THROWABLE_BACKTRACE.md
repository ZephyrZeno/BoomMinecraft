# 正常 Throwable 回溯内核

`normal-throwable-v1` 已为原始私有实例 `Throwable.fillInStackTrace(int)` 生成独立汇编绑定，两侧通过声明、布局、原始 native 帧、规范汇编及实际 COFF 校验，原始 Java 调用的独立执行验收已通过。这不是完整异常运行时。`normal_throwable.asm.inc` 面向 Context32、正常对象布局和 TracePool48/3；`normal-throwable-source.py` 逐类核对正常 Throwable 继承链及原始 backtrace、depth、stackTrace 字段。

子类增加引用字段可能移动继承的标量 depth，不能沿用 Throwable 基类的固定偏移。来源模型根据每个类的实际布局生成 NTHP64/1 池与 48 字节接收者行，核对根声明、访问标志、字段序号、宽度、引用前缀和边界。服务端提供 955 行，客户端提供 1,033 行，均来自锁定的正常类型与布局。

ABI3 中 native 行允许零 Code 长度且 BCI 必须为零；Hidden 标记是 16，generated 标记 4 不等同于隐藏。内核保留这些规则，跳过 fill／构造器前缀并在嵌入 Context 边界结束。当前最多捕获 128 个可见帧，以私有 long[] 保存池身份和方法／BCI；它不会为回溯分配失败另抛一个 OOM。

两侧 `Test-NormalThrowableKernel.ps1` 已实际执行全部接收者布局、八个 ABI3 帧／边界样例、回溯分配 OOM 和八工作者 512 次并发捕获。对象和帧均为明确的开发夹具，未执行原始 Java 构造器或源方法帧；C# 只提供 FFI、夹具和断言，堆分配、类型检查、TLS 和捕获均执行汇编。

`Test-NormalNativeSource.ps1 -Mode throwable` 在独立校验后的正常来源映像中调用 JDK 自带的原始无参 `Unsafe.throwIllegalAccessError()`，检查原始 Java Error／Throwable 构造与显式 throw、真实调用者的方法／BCI、Java sentinel 和多线程捕获。这项检查不准备接收者或帧夹具，结果仍以实际执行记录为准，不能从包构建通过推断已通过。

该测试可显式复用另一入口已经实际到达、并逐类核对来源与 Code 身份的 Java 选择记录。只复用要链接的既有汇编方法集合；新入口仍从冷类状态重新执行，不复用旧堆、已初始化标记或 native 成功记录。默认仍要求入口相同，跨入口复用须明确指定 AllowDifferentEntries，记录中标记新入口尚未执行。

尚未完成：完整 Java StackTraceElement 物化、正常 VM 隐式异常工厂、InvocationTargetException 包装及端到端 catch 行为。活动栈根、安全点、自动回收、完整系统启动、Minecraft 和世界均不能从这些局部测试判为完成。

两侧实际执行记录已通过：冷 Throwable 初始化、原始 Unsafe.throwIllegalAccessError 的 Error／Throwable Java 构造链与显式 throw、一个真实调用者的方法／BCI、原始构造字段与 sentinel，以及各八工作者 512 次并发 Java 抛出。测试对象和帧均由原始 Java 与汇编运行时创建，测试宿主只做 FFI 和断言。内部布局与方法行通过已校验的运行时元数据定位，未为测试改写原始方法或增加 PE 方法导出。
