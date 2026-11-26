# 正常 String 信号名称查询

实际 System.initPhase1 已执行到原始 `jdk/internal/misc/Signal.findSignal0(String)`（113108）。原始 Signal 另有 handle0 和 raise0 两项 native；这三项都没有 Java Code，不能靠字节码翻译生成平台行为。

新 `signal-lookup-source.py` 从锁定 JDK 的原始 class 重建三项声明、访问标志和方法身份。暂存的 `signal_lookup.asm.inc` 使用正常 String 的原始布局、byte[] 和 coder，核对同一堆、对象布局、数组头和字段边界；直接比较 Latin1 或 UTF16 代码单元，不分配游戏堆内存，不转成开发宿主字符串。

Windows 的七个精确名称与编号遵循[固定 JDK 21.0.13+3 的 Windows 实现](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/os/windows/os_windows.cpp#L5658)，并与本机 Windows SDK 的 signal.h 及独立 JVM 查询对照。未知名称返回 Java int -1；大小写、内嵌 NUL、完整长度及原始 UTF16 代码单元均保留。这里没有把旧开发 StringPool3 的 char[] 对象用作正常源 String。

`Test-NormalSignalLookupKernel.ps1` 已验证 526,336 组原始 UTF16／紧凑表示输入、64 个边界用例、10 项错误与待处理 Context 检查，以及八工作者 16,384 次并发查询。JVM 只生成参考结果；被测查询在独立汇编 DLL 中执行，使用来源布局的明确对象夹具和复制的正常 String 池元数据。查询前后游戏堆对象数不变。

`normal-signal-lookup-v1` 现已注册到运行时提供者清单及启动诊断默认准备流程，原始 113108 声明由正常 Class 初始化包装调用本内核。`verify-signal-lookup.py` 已重建原始三项 native 身份，核对部分服务策略、规范汇编、实际 COFF 定义／导入及未覆盖既有实现；新包通过独立校验。原有八包在当前工具下重新重建来源模型后复用原 ASM／COFF，基础 Java 代码生成不重跑。

新的实际 System.initPhase1 已执行越过 findSignal0，完成原始 Signal 初始化与 INT 构造，并进入原始静态同步 Signal.handle；新的明确原生前沿是 handle0(IJ)J（113109），停止时没有监视器遗留。规范 Signal.class 锁的实际竞争与释放也通过独立 System 路径验证。handle0、raise0 原始声明尚未提供，Java dispatch 与真实线程引导继续待实现；现有传输内核不能代替这些 Java 绑定。

现有 `signal_natives.asm` 的传输绑定已扩展为接受 TracePool48 ABI2／ABI3。两种版本共用的租约与关闭字段保持原布局，分别检查方法数量上限、非空方法表、保留字段和生命周期状态。隔离重建的 85 个运行时汇编源中只有这一文件变化，既有源映像继续使用原 DLL。

`Test-NormalSignalFrames.ps1` 已使用经过独立校验的正常源映像复制其 ABI3 池元数据（501,044 条帧记录），并使用明确的 ABI2 元数据夹具，验证两个版本的绑定。19 项错误／租约／关闭检查、一次汇编回调及八工作者 16,384 次原生调用通过。帧记录数量是元数据规模；没有执行这些 Java 方法。测试回调为汇编夹具，没有调用原始 Signal.dispatch，没有建立正常 Java Thread 生命周期，也没有将 handle0／raise0 包装入口计作完成。
