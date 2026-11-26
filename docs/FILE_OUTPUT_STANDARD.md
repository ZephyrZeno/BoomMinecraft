# 原 FileOutputStream 的标准输出写入候选

本批只实现锁定 OpenJDK 21.0.13+3 `java/io/FileOutputStream` 的两个原声明：`write(IZ)V`、`writeBytes([BIIZ)V`。本服务器批次对应 39453、39455，类为 4322；这些编号是回执证据，模型按原 classfile 声明、flags、Code、字段、布局及 native frame 动态解析，不把编号写成跨批次约束。`open0(String,boolean)` 未实现，原 `initIDs` 继续由现有 `normal-file-bootstrap-v1` 提供。本候选未注册到共享 provider，未修改 runtime572、TOOL105、正式31输入或任何原 Java Code/COFF/vtable/初始化状态。

范围仅限原 `FileDescriptor.out` / `err` 静态槽中实际对象。每次写入，包括数组的每次部分写入，重新读取原 FOS.fd，验证已发布的 file-bootstrap 字段表、普通 heap/receiver/FD 布局、原 fd/handle/append 字段，再比较实际 `GetStdHandle(-11/-12)`。另外构造的 FD 即使取得相同 HANDLE 也被拒绝。未知身份或非零 append 显式 Context20；关闭 FD 仍产生原 `IOException("Stream Closed")`。不收养任意 HANDLE，不实现磁盘输出、close0、通用设备写入、标准句柄所有权或源 close 的并发协议。

`boom_stream_descriptor` 只复用其真实注册表字段提取 ABI，核对 runtime 原文件哈希及 Context16 前缀与 Context32 兼容；没有复用旧开发 I/O host ABI。模型使用独立 PROP112 字符串服务池及普通 native frames，依赖原 `IOException`、`NullPointerException`、`IndexOutOfBoundsException`、`OutOfMemoryError` 的 `(String)V` 构造和 `normal-throwable-v1` 回溯。错误消息由真实 `FormatMessageW` 和原 String factory 构造。FD 静态槽属于正常源 static bank；该写入服务没有额外 native oop root span。计数器只存整数。

低八位单字节写入、null、signed off/len、范围和零长度顺序依据锁定 C 源。数组先复制完整私有字节：不超过8192字节用栈，较大数组真实 `HeapAlloc/HeapFree`。部分写循环始终使用该副本，所有已测失败路径释放私有内存。零长度在 FD/append 检查前返回。`writeSingle` 对成功但写零字节保持原 C 的正常返回；数组的成功零进度改为稳定 `IOException("Write error")`，避免原 C 的无进度循环。这是明确的故障域差异，不宣称与原 C 的无限循环等价。普通非移动 heap、外部调用静止时收集的现有边界仍适用，本批不提供自动或并发 GC。

来源为 `.boom/file-output-standard/pinned-sources/jdk-21.0.13+3/` 中官方固定 tag 的 `FileOutputStream.c`，以及锁定 src.zip 的 FOS/FD/PrintStream Java；复用 `.boom/file-input-stream/pinned-sources/jdk-21.0.13+3/` 的 `io_util.c`、`io_util_md.c`、`jni_util_md.c`。全部原内容哈希进入模型元数据。生产 provider 的 foreign imports 只有 GetStdHandle、WriteFile、GetLastError、FormatMessageW、GetProcessHeap、HeapAlloc、HeapFree，运行时写入算法全部是 MASM。

## 验证输入与唯一完整回执

候选使用已接受29的源声明、布局和 frame。执行镜像复用已独立验真的原26 Java 闭包与原公开 FIS/Parker 夹具，逐项核对本批涉及的原 class/Code、FD/FOS/String 布局、native frame 相同；仅精确移除两个原 native diagnostic stop，链接新的 provider。其余原 Java/运行时 COFF 不改。此处不把较早的原26闭包重命名成正式29/31执行。

- 候选 `.boom/file-output-standard/source-bound-v149-c/candidate.json`，SHA256 `23b14ad8bc5f46f2bdafa35774ec7d12e4b20860aaeb5742322fcbe119b34e77`；独立 source/ASM/COFF 回执 `verification.json`，SHA256 `9a82a2a8502bb222b53db62aee291b3dfb2b0b34b721d0d74548d2c6b40d488d`。
- 真实生成的 `provider.asm` SHA256 `dff0c66477068873f183489f70efe8308259b2007e5a93587c5f53d616ca5231`，`provider.obj` SHA256 `7478c1575886c7072e83a7064254ea93b3e7d4e11c3e1d170bb9501a6e1b2c03`。
- 完整执行 `.boom/file-output-standard/execution-v149-h/result.json`，SHA256 `ad1076c401da0e498fda6c2d93e73b0ae8c57dbe590bac74aa2dfa9c8cf8aab6`。`images.json` SHA256 `c43aba7cabb6adcc652721a314e0d18ba5d7263a6fbb70722cbd3e7edeabb8aa`；其对象列表、原 source/proof、只移除两个 stop 的差异、当前5文件中的执行工具及生成 runner 均有 artifact pin。

完整回执包含5个冷 ASM 子进程：正常 String/File 夹具各1、等价指令观测版各1、持有只读 stdout 的真实错误夹具1。每个子进程先运行原正常 primordial Thread/FLS、JLA helper、公开 FIS 构造/注册/读/显式关闭链，再调用本批原 `FOS(FD.out/err)` 构造和 public/native writes。正常源 Properties/VM.saveProperties 配置均由原 Java API 执行，没有宿主写 FD、JLA、Thread 或 root 槽。每个 Cleaner 工人真实退出并回收1次，worker failure/held monitor/owned buffers 均0。

正常两轮覆盖低八位、10000字节切片、1MiB+37数组、原 public write 三入口、null/4组 bounds/关闭 FD 的类型与消息、零长度、同 HANDLE 的非标准 FD 拒绝、append Context20、完整 pending Context32 保持以及坏 heap/错 receiver/错数组拒绝。每轮8个实际 OS 线程各调用原 public `write(byte[])` 128次，捕获文件逐行多重集合精确等于1024条输入，不声称并发顺序或性能提速。

默认 `PrintStream(OutputStream)` 确实构造并使用原 `InternalLock`，原 `print(String)`、`write(int)`、`write(byte[],int,int)`、flush、checkError 已执行，中文/非BMP和完整输出字节已验；未强制 `jdk.io.useMonitors`。两轮 JDK oracle 只在隔离 `.boom` 测试目录运行：正常 stdout/stderr 字节、1024条并发行多重集合、8项异常类型/消息，以及持有只读 stdout 的真实 ERROR_ACCESS_DENIED 单字节/数组消息和原 PrintStream.checkError 共3项精确一致。原 JDK private native 通过反射调用，没有作为交付游戏执行器。

观测 provider 只将 WriteFile/HeapAlloc 的 external/call 目标改为测试 shim。重新汇编后比较所有实际非 debug COFF section 字节和按名字归一的全部 relocation，连 `.pdata/.xdata` 也一致；只排除含不同输入文件名的 `.debug$S`。独立 shim 不进入生产 imports。真实 Win32 部分写 cap31时10003字节经历323次 WriteFile和323次源FD/标准句柄查询；成功零进度、真实消息5/6、私有 HeapAlloc OOM、127/10007字节副本在真实 WriteFile 阻塞时修改源 byte[]仍保持旧副本、首7字节后实际 SetStdHandle 切换使次轮 Context20均通过。只读句柄全程未关闭；另一个正常子进程仅由测试 CloseHandle 自己的 stderr，验证首个真实 ERROR_INVALID_HANDLE。生产代码从不关闭标准句柄。

## 保留的失败与当前边界

`execution-v149-a` 保留默认 PrintStream.println 首次失败：原 `System.lineSeparator()` 在 API 夹具中仍为 null，原 Writer.write(String) 出现 Context4；此前 FOS/native/public 输出已完成。`b` 保留尝试真实 System.initPhase1 到原 Signal.handle 的 Context20；`c` 保留独立 Signal owner 准备本身的 Context20，未归因为缺 native，也没有修改原 Java 状态掩盖。相应测试工具快照和 first-failure/progress/捕获输出均保留。当前h明确不执行完整 Phase1、不声称 println 已过；父级完整主进程的 Phase1/2/3 证据不挪作本夹具结果。

`execution-v149-e` 是最初将嵌文件名的 `.debug$S` 一起比较造成的真实验证失败；text/data/unwind 与 relocation 本来相同。`f` 是宿主从 Kernel32 查找 WakeByAddressAll 失败，后改用真实 KernelBase 导出，未改生产算法。`g` 保留4个完整通过的 ASM 子进程及原 JDK 错误序列差异：测试关闭 stderr 后首个数组写消息为6，紧接单字节为5。该已关闭 OS HANDLE 在原 JDK 内的后续状态未证明稳定，因此h只精确比较首个无效句柄调用，另外用仍持有的只读句柄稳定比较单字节及数组5；不宣称跨多次关闭句柄调用的 OS 历史一致。没有删掉g或把其最终比较失败改成pass。

这两项 native 声明不代表全域 FOS、标准流初始化、完整 PrintStream、完整 System 冷启动或 Minecraft 启动已完成。当前组件未正式发布注册，也不处理任意磁盘/世界/设备输出。

根独立重新生成 source／ASM／COFF 并复跑全部5个冷 ASM 进程和两个 JDK 对照：
`.boom/file-output-standard/root-review-source-v151-a/verification.json` 的 SHA256 为
`559af72bc9d52ea88b65b4266080b4ce2f60ca02b2e58241726e9c0205877b54`；
`.boom/file-output-standard/root-review-execution-v151-a/result.json` 的 SHA256 为
`e4241a747aa99f32b0e62196ed90519efd22e39a03aa7e98010bb99d41bfb525`。
完整有界 suite 通过，以上所有未覆盖项和故障域差异继续保留。

## 独立重放

```powershell
D:/Dev/Python312/python.exe scripts/file-output-standard-candidate.py --state .boom/accepted-native-modules-v149-29.json --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe --output .boom/file-output-standard/NEW-source
D:/Dev/Python312/python.exe scripts/test-file-output-standard.py --candidate .boom/file-output-standard/NEW-source/candidate.json --park-result .boom/unsafe-park/root-review-execution-v148-a/result.json --output .boom/file-output-standard/NEW-execution
```

输出目录必须全新。共享注册与正式31输入保持冻结，本批5文件由主 agent 独立复验后统一提交。
