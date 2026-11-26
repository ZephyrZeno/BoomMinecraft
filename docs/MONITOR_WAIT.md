# 原始 Object.wait 与线程中断

`native/runtime/object_wait.asm` 实现同一对象上的真实等待集，沿用 Monitor32 的对象身份、持有者和递归深度。等待前释放该对象的全部递归持有，恢复执行前重新取得同样深度；其他已持有的对象保持不变。等待者计数维持堆强根，避免对象在等待和重新入锁期间被回收。

`Object.notify` 唤醒同一对象的一名等待者，`notifyAll` 广播该对象的等待集。普通 monitorenter 的争用与 Java 通知使用不同谓词，其他对象不会收到通知。现有编译器直调、原始 Object native 和线程退出时的 join 通知均调用同一个入口。有限等待使用真实经过时间，64 位超长等待不会被截成短超时。

## 原始声明与异常

`normal-object-wait-v1` 提供三个经过原始类摘要、访问标志和 native 声明校验的入口：`Object.wait0(J)V`、`Thread.interrupt0()V`、`Thread.clearInterruptEvent()V`。适配器保留原始方法 ID，使用源 ABI3 帧。

中断标志通过源 `Thread.interrupted` 字段映射按实际接收者定位。不能写死物理偏移：测试中的 Thread、FinalizerThread、ReferenceHandler 为 144，TimerThread 为 152。等待在中断后先重新持锁，再调用原始 `InterruptedException.<init>()V`，将真实异常对象传回 Java。原始 `Object.wait()` 的 catch/finally 和 `PipedInputStream.awaitSpace()` 的 typed catch 都由普通字节码后端执行。

线程没有监视器等待槽时，底层中断派发返回明确的未找到状态；这不表示 sleep、park 或 IO 中断已经提供。

## 进程关闭

引用等待和对象等待共用 RPRC88 的线程本地停止令牌控制器。关闭先停止等待域，再等待工作线程退出，最后关闭等待池。只有已停止的实际等待域、正确的操作系统线程和同一 Java Context 可以签发及消费令牌。

受控取消使用单独状态。它在恢复递归持锁后通过工作线程边界释放持有，不增加正常 Java `run` 返回计数。Context 的 VM 异常计划字段始终保留给异常运行时。

## 已验证范围

2026-11-26 的独立汇编内核测试覆盖递归持有恢复、对象隔离、单个/广播通知、真实超时、通知与中断的两种次序、48 次重复等待、16 个平台线程受控退出和实际源字段映射。

v145 原始有帧入口测试使用已验收的 22 包输入清单，实际链接其中 17 个提供器；该源镜像通过独立的源码、ASM 和 COFF 验证后，完成七次源等待：两次正常返回、三次构造实际 InterruptedException、两次受控取消。原始 `PipedInputStream` 将中断异常转为真实 `InterruptedIOException`。

原始平台 `Thread.start()`、无期限 `Thread.join()`、`Thread.run()`、`Thread.exit()` 与 `clearReferences()` 均执行。测试在启动前持有真实子线程监视器两层，`join()` 经一次原始 wait0 释放并恢复递归持有，由真实 `tl_exit` 发布终止状态并通知唤醒。源 Java run 和 exit 各正常返回一次，VM 失败状态为零，失败 Context 全零。

空 `TaskQueue` 上的原始 `TimerThread.run()/mainLoop()` 进入 Object.wait 后受控关闭：一次源 run 尝试、零次正常 run 返回、一次原始 Thread.exit 正常返回。它与另一名真实等待者共消费两个受控停止令牌，随后等待域、线程注册表、追踪池及堆全部完成清理。

Thread/TimerThread 的 holder、interruptLock 和空队列由测试夹具准备；原始 `System$2` 堆对象提供完整 Phase1 会在 SharedSecrets 中安装的 JavaLangAccess。这些准备不表示测试已执行完整 Phase1 或 Thread/TimerThread 的原始构造流程。

内核可通过 `D:\Dev\Python312\python.exe tests/monitor_wait/build.py --runtime <汇编运行时目录>` 复验；加 `--source-state` 可核对已有原始源镜像。`build_framed.py` 从锁定批次、计划和提供器列表重建原始有帧入口测试。完整初始化进程的合流验证继续单独记录，以上结果不表示 Minecraft 已启动，也不覆盖定时任务调度、虚拟线程或有限时长 join。
