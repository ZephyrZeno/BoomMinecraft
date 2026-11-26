# 正常布局 Thread 优先级

目标版本为 Java 版 1.21.1 使用的锁定 JDK 21 输入。游戏运行中的对象校验、字段访问、线程查找及 OS 调度调用全部由自研 MASM 实现；Python 只生成并校验绑定，C# 只用于内核开发测试。

## 调度与对象生命周期

`boom_threads_set_priority(registry, sourceThread, JavaPriority)` 在注册表共享锁内查找源对象。普通工作者使用受锁保护的 OS 句柄；外部附加线程通过其 OS ID 打开临时线程句柄，在释放注册表锁前完成设置和关闭，避免与 FLS 脱离、记录释放或线程 ID 重用竞争。失败返回实际 Win32 状态。

合法但尚未启动、已经结束或已经回收的源 Thread 没有可调度的 OS 同伴，此时不进行 OS 调用。空对象、非法注册表和范围以外的优先级不会被接受。Java 优先级 1..10 采用 [OpenJDK 21u Windows 默认策略](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/os/windows/os_windows.cpp#L3709)对应的 -2、-2、-1、-1、0、0、1、1、2、2。

`normal-thread-priority-v1` 只绑定原始 bootstrap `java/lang/Thread.setPriority0(I)V`，要求原始私有 native 标志、无 Java Code、锁定类摘要和原始变换链。Java `Thread` 方法自己写入 `holder.priority`；native 服务负责改变现存 OS 线程的调度优先级。

新工作者附加到真实当前线程身份后，通过经过校验的 `Thread.holder` 与 `FieldHolder.priority` 字段映射读取继承值，在进入原始 Java Runnable 分派前应用。Thread 子类保留原始分派关系。虚拟线程继续明确报告尚未支持。此绑定不扩充原来只有五个可执行入口的 registerNatives 表，也不宣称全部 Thread native 已实现。

## 原生进程退出

VM 先关闭并等待信号分发线程，再在池锁以外等待并回收普通工作者。有限等待用于当前诊断进程的退出；超时保留堆、注册表和帧池，报告清理错误，由进程退出回收资源。它不是完整游戏的 daemon 停止协议。

如果工作者已经发布首个失败而主线程 Context 仍正常，退出入口在捕获报告前传播该 Context，并保留主线程的调用深度。报告 ABI 5／240 字节额外保留优先级应用次数、普通工作者启动数、Java run 进入数与记录回收数，不能把工作者失败记作完整 System 成功。

## 已完成的内核证据

- `.boom/thread-priority-tests/94ea9258c0ee4375a78a718e27563eb7/result.json`：1,000 次普通工作者 OS 查询、10 次外部线程自身查询、10 次远程查询、4,000 次设置与脱离竞争、非法范围及 NEW／结束／回收对象检查通过。另核对工作者完整结果、回调返回值和退出状态，注册表与堆清理完成。
- `.boom/thread-registry-regression-v126.json`：用新运行时重新执行已有注册表与发布测试，包括 512 个工作者；已有 AOT 工作负载、JVM 对照字节及适配器复用，未重新生成整批 Java 或构建第二份运行时。
- 291 项 Python 检查通过，包括原始 native 的所有者、标志、Code 和声明库存拒绝检查。新优先级提供者与更新后的线程启动提供者已分别完成精确 ASM／实际 COFF 校验。

## 原始 Java 的实际执行

普通线程验证：`.boom/diagnostic-startup/v126-native-Thread-priority-ce2ac618d1f8457ea491b7582e0ac473/result.json`；对应原生 EXE 位于 `.boom/vm-entry-images/79a5a98aa9234bec9f95599048152221`。5,178 个源 Java 方法参与选择。原始公开构造器传入主 Thread 作为非空 Runnable，完整执行原始 start／runWith／接口分派／exit，优先级应用、启动、run 入口与回收计数各为 1，工作者失败状态为 0，清理标志为 7。主 Thread 自身 task 为空，这不是实际游戏任务。

System 验证：`.boom/diagnostic-startup/v126-native-System-priority-0bd3acb123fe480293e4cc4eaa694a61/result.json`；对应原生 EXE 位于 `.boom/vm-entry-images/af8433fb6c604565a7faf49fe61a6479`。5,370 个源 Java 方法参与选择。主线程实际越过 setPriority0，引用处理工作者应用优先级并请求 run 分派，随后原始 Thread.exit 与回收完成。分派计数发生在实际调用前，不能证明子类 run 方法体执行。主线程停在未实现的 `Finalizer.isFinalizationEnabled()Z`（50096），工作者失败状态为 2，其具体失败 Context 尚未单独写入报告；不能将其计作正常 run 完成。信号线程关闭、退出、脱离和三项资源清理均通过。

VM 退出使用真实源码诊断停止，没有跳过后台线程。完整 System、Minecraft、世界创建和游戏多核性能优化尚未完成。引用处理及终结工作者后续需要真正的等待服务与 VM 停止／唤醒协议，不能用空成功返回替代等待。
