# 正常布局线程与主线程引导

首版仍以原始 Java 版 1.21.1 和锁定 Java 21 输入为准。Java 方法由自研后端生成汇编，线程注册、OS 线程绑定、对象分配和 VM 发布也执行汇编。

## 已实际执行的线程基础接口

原始 `java/lang/Thread` 有 20 项 native 声明，包含 `registerNatives` 和 `clearInterruptEvent`。`normal-thread-primitives-v1` 提供其中 6 项：注册、当前平台线程、当前载体线程、栈遍历物化边界、让出处理器、VM 线程 ID 地址查询。

既有注册表有 18 个非注册入口，尚未包含 `clearInterruptEvent`。其中 5 个操作可执行，其余入口保持明确错误；这不代表全部 Thread native 已实现。注册表的函数地址从运行时 DLL 的真实 IAT 单元发布，避免将导入跳板地址当成实际实现地址。

本轮修复运行时导出表，导出已有 18 个汇编入口。原有 85 份运行时汇编源码不变。服务器正常布局映像已通过源 Java／ASM／COFF 校验并实际完成原始 Thread 类初始化和 `yield0` 入口。

独立源执行测试通过：8 个冷注册工作者、8,192 次注册、全部 18 个真实导出地址核对，以及 8 个独立 OS 工作者的 24,576 次调用。还检查了当前线程身份、保留的主线程 ID、未绑定／已脱离拒绝、活跃注册表不能解绑、挂起上下文保留和静止清理。

该测试的 Thread 对象为明确的 VM 构造前存储夹具，没有执行 Thread 构造器、Java 线程启动或退出，不计作完整 VM／游戏启动。

## 原始主线程构造路径

新增 `native/runtime/vm_thread_bootstrap.asm`，通过源方法函数表调用完整、未剪枝的原始构造器：

- 根 ThreadGroup 的私有 `()V` 构造器。
- main ThreadGroup 的 VM／包级构造器，包括原始强引用登记路径。
- AccessControlContext 的授权引导构造器。
- Thread 的完整附加构造器；FieldHolder 由其原始 Java 调用链创建。

先将实际 OS 线程附加到新分配的 Thread 对象，再调用原始 Thread 构造器，使原始 `currentThread() == this` 分支生效。原始字节码在 `VM.initLevel() < 1` 时分配主线程 ID 1。构造成功后 VM 发布 RUNNABLE 状态；构造失败则撤销 OS 绑定与注册表。

构造器、布局偏移、名字字面量和 VM 静态字段都从锁定输入及已校验批次取得。专用开发宿主只建立 VM 绑定配置并断言结果，所有分配、构造与发布逻辑执行汇编。新运行时增加这一份汇编文件，保留原有 85 份实现。

`Invoke-NormalVmThreadBootstrap.ps1` 为开发命令，沿实际失败目标自动选入已有 Java 方法。服务器首轮独立校验保留 5,051 个原始 Java 方法、1,121 份类状态和全部分派行，实际执行已完成上述四个构造器入口及嵌套 FieldHolder 构造。主线程 ID 1、首个普通线程 ID 2、正常主线程身份、system／main 线程组关系、授权 ACC、优先级和 RUNNABLE 发布均核对通过。退出测试时堆与注册表清理成功，没有监视器或 Java 帧遗留。

这条验证仍使用开发宿主建立的 VM 函数／布局绑定配置；构造器、对象字段和 OS 绑定由实际汇编建立。没有把配置夹具当作完整 VM 引导或 Java 线程退出实现。构造器专项的确切源码已单独快照。

`-ContinueSystemPhase1` 组合路径也已实际执行：源选择包含 5,099 个 Java 方法，完成主线程构造后调用原始 `System.initPhase1`，实际停在尚未绑定的 `Signal.handle0(IJ)J`，而非线程构造或绑定处。停止时 2,472 个堆对象仍正常受管理，监视器持有数与监视器注册表锁均为零，堆和线程注册表清理成功。组合测试只观察线程 ID 计数器，不额外预留普通线程 ID。

完整 System 阶段仍未完成。下一步需要正常线程 ID 地址域的安全原子访问、原始 Java 分发回调和线程启动／退出，再绑定信号传输服务。

## 工作线程开始前的 VM 发布

注册表新增 `Start88/2` 协议，保留原来的 `Start64/1`。新协议携带汇编 VM 发布／回滚回调和可选栈预留大小。注册表持锁插入记录后，先发布 VM 字段，再调用实际 `CreateThread`；工作者仍通过原来的注册表锁接收已发布的记录和 OS 句柄。创建失败时先撤销 VM 字段，再移除／释放记录，并保留原始 OS 错误码。

发布与回滚回调仅能进行不抛错的 VM 存储，不能分配、等待、调用 Java 或重新进入注册表。后续正常布局适配器需要在调用前完成对象／字段／来源验证。非零栈大小使用 Windows 的栈预留参数，零值保留系统默认；协议与 [CreateThread 文档](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createthread) 对齐。

独立内核测试运行 512 个真实 OS 工作者，逐个核对执行前的 peer／状态及真实当前线程身份，核对退出后 peer 清理；另通过一次真实 OS 创建失败检查发布回滚和错误码保留，以及三种非法协议头拒绝。原有 66 个 AOT 任务／异常／退出回归、64 组 JVM 对照及 6,147 条并发唯一 ID 记录也通过。证据为 `.boom/thread-registry-tests/7b754ab73fdf4c90bcd342350322cf9b/result.json`。

发布测试使用明确的原始 VM 存储夹具，没有执行原版 `Thread.start`、`run` 或 `exit`。新协议仍需接入正常 Thread 字段及原始 Java 回调；不能将这些内核工作者计作原版线程生命周期或游戏多核优化完成。

## 正常 start0 与原始 Java 生命周期

`normal-thread-start-v1` 绑定原始私有 `Thread.start0`，复用 `Start88/2` 内核。原始 `run`、`exit` 和 `dispatchUncaughtException` 作为 Java 源回调选入；运行入口复用原始 `Thread.runWith` 中完整的 `Runnable.run` 分派契约，保留 Thread 子类的覆盖关系。

tid、eetop、holder、threadStatus 和 stackSize 通过已验证的运行时字段映射取得，覆盖 64 种 Thread 接收者布局，不把基类紧凑布局的标量偏移用于所有子类。取得的字段地址只借用于同一非移动堆的 VM 生命周期。发布回调只写已验证的字段地址；每个线程的 VM 槽保存本机 token 和根，回收使用零超时 OS join，不在池锁内等待仍可能创建其他线程的工作者。

原生验证记录增加 144 字节 ABI3，分别观察原始 public start 返回、run 完成、exit 完成、记录回收和工作线程失败。未提供 Java 目标的实际停止 Context 会传回验证进程，不把 OS 线程创建成功当成原版 Java 回调执行完成。新提供者已通过源声明、五项字段映射、精确 ASM 和实际 COFF 校验。

v123 的独立汇编 EXE 实际完成原始主线程构造、公开子线程构造及 `Thread.start`、`run`、`exit`，退出码为 0。首轮在退出路径准确报告未选入的原始 `threadContainer`；自动选入原有 Java 方法后，第二轮完成生命周期。最终保留 5,178 个原始 Java 方法，没有更改其字节码或生成汇编。主线程 ID 1、子线程 ID 2、下一 ID 3，结束后 peer 清零、状态为 TERMINATED，OS 记录已回收，工作线程失败状态为零。堆、注册表及 Java 帧清理全部通过，监视器持有数与注册表锁均为零。

证据为 `.boom/diagnostic-startup/v123-native-thread-lifecycle-308af3ca424a467499b97759155de995/result.json`，成功轮次为 `round-001`，独立 EXE 位于 `.boom/vm-entry-images/48ed222a66864b2a907ebef36b081cfe`。该轮子线程没有 Runnable 任务；非空任务、实际子类覆盖、未捕获异常、等待／中断及完整 System 引导仍需分别验证，不计作游戏启动或多核优化完成。

随后 v123b 复用相同的已验证 Java／COFF 选择，改用原始公开 `Thread(ThreadGroup,Runnable,String)` 构造器，把已构造的主线程对象作为子线程的非空 Runnable。汇编在调用 start 前检查构造结果中的实际 holder.task，随后执行未更改的原始 `Thread.run`、`runWith`、`Runnable.run` 接口分发及退出路径。该独立 EXE 同样退出 0，生命周期、OS 记录回收和三项清理全部通过。证据为 `.boom/vm-entry-images/v123-runnable-abc2e8350322493cb06846450ebe9908/execution.json`。这覆盖非空任务分支；任务本身是无任务的原版 Thread，不代表已运行游戏任务或验证全部 Thread 子类。

## 后续边界

信号传输增加兼容原 `Config48/1` 的 `Config64/2`：额外携带工作线程 enter／exit 回调。创建成功前等待真实 OS 工作者完成附加，关闭时先排空已接受的信号，再在同一工作线程退出并等待它结束。enter 失败保留其错误且不发布传输，不调用 exit；成功 enter 对应一次 exit，包括后续创建步骤失败的回滚。生命周期回调不能重新进入该传输服务。

`.boom/signal-control-tests/a11eb3615336460c8e6f9f0316f3d9f5/result.json` 已验证附加发布屏障、同线程分发／退出、关闭等待退出、失败保留及 10 对成功生命周期；既有 4,096 组 JVM 注册对照、并发队列、关闭排空和隔离 OS 信号回归也通过。该轮使用开发宿主与汇编回调夹具，尚未执行原始 `Signal.dispatch`，不能记作 System 或游戏启动。

`normal-signal-control-v1` 已通过原始 `handle0`／`raise0` 声明、原始 Java dispatch／Thread 构造器／exit 回调、正常字段映射及实际 ASM／COFF 校验。它使用原版构造器建立具名分发线程，OS 工作者附加后才绑定传输；退出时调用原始 Thread.exit，随后发布终止状态并解绑。VM BREAK 所需的真实线程转储仍未实现，该入口明确返回错误。原生启动入口的 208 字节 ABI4 分别记录传输开关、附加、Java 退出、脱离、实际 dispatch 进入次数和工作线程失败；实际 System 接入执行仍在验证中。

v124 第一轮原生进程已实际打开信号传输，附加 Java ID 2 的分发线程，执行原始 System.initPhase1 并越过原始 Signal.handle0 调用。实际停止于原始 Signal.handle 内尚未选入的 Hashtable.put（方法 64111，类别 1）。随后在同一分发 OS 线程完成原始 Thread.exit、脱离和关闭，工作线程失败状态为零；2,739 个对象受汇编堆管理，三项清理全部通过。独立 EXE 为 `.boom/vm-entry-images/f2501f530c784769b28bc6af9524ffab`，证据为 `.boom/diagnostic-startup/v124-native-System-signals-` 前缀目录的 `round-000/execution.json`，确切目录由 `.boom/pending-native-System-signals-v124.txt` 保存。该轮没有投递信号，原始 Signal.dispatch 进入次数为 0；它验证传输绑定和分发线程生命周期，尚未验证 Java 信号处理执行或完整 System 阶段。

v120 已接入受注册表生命周期约束的 VM 线程 ID 地址原子访问。v121 又接入正常权限上下文提供者，独立汇编 EXE 实际完成原始公开子线程构造，直接观察主线程 ID 1、子线程 ID 2 和下一 ID 3，子线程仍为 NEW，清理全部通过。详情及确切证据见[汇编进程启动入口](NATIVE_VM_ENTRY.md)。

一般堆外 Unsafe、线程等待／中断及异常退出的完整兼容、信号 Java 分发、虚拟线程和完整 System 引导尚未完成。静止堆检查和多线程接口测试也不代表游戏侧自动回收或多核性能优化已经验收。

v125 两轮原生执行已越过 Windows 错误模式服务，依次到达原始 `Reference$1.startThreads` 和真实缺失的 `Thread.setPriority0(I)V`（44197）。最后一轮保留 5,370 个 Java 方法、2,775 个管理对象，下一 Java ID 为 4；信号分发线程退出／脱离和三项清理全部通过。证据为 `.boom/diagnostic-startup/v125-native-System-Windows-7852c3a9fb3f4d508aeac8c752a1e6a7/result.json`，末轮独立 EXE 为 `.boom/vm-entry-images/87f6dc99824d48cbaa444dae4381dfa9`。原版引用处理线程在设置优先级前已经构造，但尚未开始运行。

v126 已实现[真实 OS 优先级与原始字段绑定](NORMAL_THREAD_PRIORITY.md)，并在普通工作者进入原始 Java run 前应用其 holder.priority。原始普通线程生命周期复测通过，System 实际前沿推进到 `Finalizer.isFinalizationEnabled()Z`。原始引用／终结线程仍需要等待、通知、引用待处理队列和 VM 关闭协议；不能把空队列直接返回成功或跳过这些线程来宣称系统引导完成。这些契约由自研汇编内存管理与同步服务实现，不要求采用 JVM 的收集器实现。

启动器继续只保留启动流程入口。上述开发校验不会增加玩家界面的编译、翻译或测试按钮。
