# 原 FileInputStream 只读 native 候选

`native/providers/file_input_readonly.asm.inc` 提供原 FileInputStream 的七个只读 native 和 FileDescriptor.close0。`scripts/file-input-source.py`、`scripts/file-input-candidate.py`、`scripts/test-file-input.py` 分别核对锁定源码、生成独立候选、执行原 Java／native 与 JDK 对照。游戏执行仍全部为 MASM；Python 仅作构建和开发测试宿主，JDK 仅作 oracle。

## 实际声明和复用边界

模型逐项核对原 bootstrap `jdk:java.base` classfile 的类名、源摘要、方法／字段清单、声明 flags 和 native frame。类号、方法号、字段偏移均从当前已验证批次解析，不作为跨批次常量。本 server 的八项编号如下：

| 原类 | 原 native | 当前方法号 |
| --- | --- | --- |
| FileInputStream | open0(String)void | 39418 |
| FileInputStream | read0()int | 39421 |
| FileInputStream | readBytes(byte[],int,int)int | 39422 |
| FileInputStream | length0()long | 39429 |
| FileInputStream | position0()long | 39431 |
| FileInputStream | skip0(long)long | 39433 |
| FileInputStream | available0()int | 39435 |
| FileDescriptor | close0()void | 39399 |

八项原 access 均为 `0x102`，无 Java Code；帧必须带 native 标志 32，不能带开发 stub 标志 128。FIS 类 4319、FD 类 4316 只是本批证据。原 FIS.initIDs、FD.initIDs／getHandle／getAppend 继续由已存在的 `normal-file-bootstrap-v1` 提供，不重复注册；FileOutputStream、FD.sync0、FileCleanable.cleanupClose0、FileChannel 以及写入 native 不在本批。

原 C 协议固定在 OpenJDK `jdk-21.0.13+3`：[FileInputStream.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/FileInputStream.c)、[FileDescriptor_md.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/windows/native/libjava/FileDescriptor_md.c)、[io_util.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/io_util.c) 和 Windows [io_util_md.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/windows/native/libjava/io_util_md.c)。相关八份文件的下载内容和 SHA256 保存在 `.boom/file-input-stream/pinned-sources/jdk-21.0.13+3` 及候选 metadata；其中 canonicalize_md.c 仅核对 getPrefixed 辅助协议，没有复用 canonical provider。

`native/runtime/file_streams.asm` 只负责原 fd 字段表发布和读取；`file_descriptors.asm` 的历史 I/O 服务为 Context16、直接堆数组缓冲区，缺少本批需要的句柄关闭生存期协议。因此本候选不把历史 read op 当作已完成的正常 readBytes。它复用已接受 runtime 中完全未修改的 `boom_stream_descriptor`，从公开 `boom_provider_file_bootstrap_pool` 取得原已发布 input pool；该子程序只使用 Context32 的前 16 字节兼容前缀。新的外层和八个普通 native adapter 均为 Context32。

服务还核对原已发布 FD 表指针、源布局、fd／handle／append 的动态 offset 和实际 4／8／1 字节宽度。原 runtime.json 的 kernel SHA 必须与当前 `file_streams.asm`、`file_descriptors.asm`、heap／object／frame 等源码相同；候选不内联改写这些旧核，不修改 runtime572。新读写协议是新的 MASM 实现，未声称与旧开发 I/O 服务的全部机器码相同。

## 对象、路径和 typed 错误

独立服务为 `boom_provider_file_input_service`，只读 String pool 为 `boom_provider_file_input_pool`，112 字节、PROP ABI 2。String 的四个正常字段和工厂形状均动态核对；路径执行原 String.length／toCharArray，以第一个嵌 NUL 结束 native 路径。路径转换使用调用私有的 HeapAlloc 缓冲区，超过原长路径阈值时按原 Windows 规则展开绝对路径并加 drive／UNC 扩展前缀，最大有效路径为 32767 UTF-16 单元。没有把路径改为符号链接目标，没有 NIO Dispatcher 字段依赖。

只读打开的实际 WinAPI 参数为 GENERIC_READ、FILE_SHARE_READ|FILE_SHARE_WRITE、OPEN_EXISTING、FILE_ATTRIBUTE_NORMAL；没有额外共享删除标志。当前有界实现只接纳成功打开的 FILE_TYPE_DISK 普通文件，目录打开实际产生错误，其他设备类型明确阻断并释放本次拥有的句柄。原 open／read／seek／length 系统错误及时保存真实 Win32 code，typed 消息使用 256 单元 FormatMessageW，按原顺序去 LF／CR／ASCII 句点。FileNotFoundException 使用原私有 (String,String) 构造器，IOException 使用原 (String) 构造器；null 数组和 bounds 错误执行原 NullPointerException()／IndexOutOfBoundsException()，并保留原 Throwable.fillInStackTrace() 依赖。

readBytes 按原顺序检查 null、signed offset／length 和边界，再允许零长度直接返回 0，包括已经关闭的流。非空读取先写调用私有缓冲区，成功后才复制至源 byte[] 指定范围；8192 字节以内用已逐页探测的调用栈，更大请求用 HeapAlloc，失败不会先改 Java 数组。EOF 为 -1，单字节结果为无符号 0..255。length／position 使用真实文件句柄；skip 采用 signed long 相对 seek，允许倒退及越过 EOF，负位置由真实 WinAPI 拒绝。available 为剩余长度，负数归零并截至 int 上限。

源模型显式依赖 `runtime_metadata`、`properties`、`normal-file-bootstrap-v1`、`normal-throwable-v1`，以及上述原 String／异常构造器／回溯 Java Code。已有错误在所有对象／argv 验证前原样保留。外堆、错误布局或未实现的 private-native 使用条件明确失败。

## 句柄所有权、关闭和 GC

只有本服务 open0 实际创建并发布的句柄可以借用或关闭。FD 身份、真实拥有 HANDLE 和原 handle 字段必须匹配；原 fd 字段为普通文件的 -1。原 Java FIS(FileDescriptor) 可以共享本服务已经拥有的同一正常 FD。外部传入但未在本服务登记的 FileDescriptor，以及标准 0／1／2 描述符，不自动取得所有权，调用停在 Context kind 20；不会以调用者字段里的任意整数执行 ReadFile 或 CloseHandle。

静态 owner 槽最多 4096 项。每槽有实际状态、借用计数和独立 I/O SRW 锁；全局 SRW 只用于表查找及短状态发布，不包住 ReadFile。关闭先将正常源 FD.handle 写为 -1 并进入 closing，阻止新借用；已有调用完成并释放借用后才调用 CloseHandle。竞争 close 等待同一状态转换；重复成功 close 不再次调用 OS。CloseHandle 失败时保存 failed-owned 槽和真实句柄，源 handle 保持 -1，读取继续拒绝，后续 FD.close0 可重试真正释放。Java 构造器和异常回调均在所有 OS 锁、I/O 锁和借用退出后执行。

`boom_file_input_owner_roots` 是 4096 个正常 oop 槽。打开／关闭过程中只由 ASM 发布和清除，防止仍有本模块拥有句柄的 FD 地址被 GC 重用；原 FD.parent／otherParents 保留正常 FIS 关系。当前实现因此将打开的 FD 强保留至显式关闭，尚未实现自动 Cleaner 或完整弱引用 GC。**未来正式 source 选择和主进程 GC 消费者必须纳入 metadata 的这份 native_root_spans；目前仅候选测试纳入，不能在未接入根的情况下宣布正式 provider accepted。** 此设计也不是原 JDK 无限制资源预算，超过 4096 owner 的私有 native 请求明确阻断。

native scratch OOM 为 Context kind 3。尚未注入或证明所有原 JDK malloc 点、Java 分配点、HeapFree 失败和任意设备错误的逐点相同表现。未虚拟化跨调用历史 Win32 LastError；空路径等不产生自身 OS 错误的逻辑失败不承诺复现原 C 借用先前 TLS 值的消息。本批只验证当前非移动堆、无并发回收、所有工人 join 后的显式静止 GC。

## 实际原 Java 链和对照结果

测试从已独立完整校验且实际执行过的正式 26 基线重链到新目录：

- source：`.boom/diagnostic-startup/v146-native-three-families-9c5d0bc2e4db4866b30ad467ceb39e8c/round-000`。
- native manifest／proof／execution：`.boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1`。

执行器核对两层 proof 绑定、原实际主进程 cleanup=7／worker failure=0，并逐项核对本测试所用原 Java class／Code。仅移除八个真实 native 开发 stop，加入候选 COFF 和原 PUBLIC 观察导出；其余 Java、COFF、虚表、类状态和原基线输入不变。原 FileDescriptor()、FileInputStream(FileDescriptor) 构造并发布 fd／parent／closeLock，宿主不写引用字段。原 Properties 构造器／setProperty／System.setProperties 仅准备属性 API 夹具；另实际调用原 System.setJavaLangAccess() helper，使原 Blocker 具备正常 JLA。这不是完整 System Phase1，也没有宿主直接写 JLA 或 System.props。

真正执行原 Java read()、read(byte[],off,len)、skip、available、close，并调用八个普通有帧 native。另用第二个原 FIS(FD) 构造共享 FD，验证共享文件位置和原 otherParents／closeAll 关闭链。读操作包括偏移范围、8192 单元以上私有缓冲区、EOF、越过 EOF、负 skip、负位置错误、missing／目录的完整 FileNotFoundException 消息、关闭错误、零读、typed null／bounds、早 NUL、337 UTF-16 单元路径、标准流和外来句柄拒绝、已有错误和坏指针。故意伪造的 unowned scalar handle 仅为负例存储夹具，不冒充 Java 字段发布。

锁定 Windows JDK 的 16 组协议输出完全一致。oracle 同样以原 FIS(FD) 构造后调用原 open0，再执行 public Java delegates；它不替代本机 ASM 运行。8 个实际 OS 线程各持有独立正常 FD，每个线程执行 129 次 native，总计 1032 次，数据、位置、available 和最终关闭均通过；每个生产／观察映像都独立执行该轮。没有根据线程数量声称性能提速。

观察映像只将生成 COFF 的 ReadFile／CloseHandle 两个重定位目标改到测试专用 ASM shim；去别名后的全文与生产 ASM 相同，实际 `.text*`／`.rdata*`／`.data*` 字节相同。shim 平时调用真正的 WinAPI，只有测试臂控路径等待或一次失败注入：

1. 让一条真实 ReadFile 在已有借用期间受控等待，再发起 close。源 handle 已为 -1，但物理 CloseHandle 尚未调用。
2. 另一独立 FD 的真实 ReadFile 在放行第一条前成功完成，证明不存在包围全部 I/O 的全局锁。
3. 放行后第一条读取成功，等待中的 close 再实际释放句柄。
4. 仅注入一次 CloseHandle 错误 5，验证 typed 消息、failed-owned／root 保留和新读取拒绝；retry 只执行一次真正 CloseHandle。
5. 8 个真实 OS 线程同时 close 同一 FD，物理 CloseHandle 只调用一次。

正常／观察映像各完成两轮静止 GC。9 份原正常根 span 加 4096 个 owner 根共 1,187,856 个物理槽，完整快照全部非空值后去重，逐值断言无遗漏；原根槽不写。正常首轮有 91 个非空值、79 个去重 oop，没有额外宿主强根。owner-root 保留原 FD.parent→FIS 图，关闭清根后两对象均被真实回收。两轮释放数正常为 223／3，观察为 249／3。最终 owner 根、真实拥有句柄和私有缓冲区计数均为 0，源 trace TLS 释放和正常堆销毁成功。

## 回执、首次失败和重放

- source candidate：`.boom/file-input-stream/source-bound-v146-c/candidate.json`，SHA256 `9507dfd5236d789e17ff8b45b8973cacddab5cf8797e5d7a88952d6aded567b0`。
- source／frame／ASM／COFF proof：同目录 `verification.json`，SHA256 `4f956ac58cb40d6e1e8b82f2ab985ab10de30edaca1cfeb35654a920af312320`。
- 实际完整执行：`.boom/file-input-stream/execution-v146-c/execution-eec029866c114a5e9a51112589ba7ff6.json`，SHA256 `ea57ba446b42358f6e5354930438bab8a0c1562166b8aaca0083dd6525a053c9`。
- `execution-v146-c/images.json`，SHA256 `10660b5f95f31a868c3e00249e4f3c3136ab14118f4cd02aef67373003589431`，封存全部原输入、八个 stop 替换、两个映像、观察代码比较和原 Java fixture 身份。

首次 source-bound a 的 MASM 已成功，COFF 校验发现两个内部 leaf PROC 默认成为 PUBLIC；改为 PRIVATE 后 source-bound b 通过，实际指令未因此变化。execution a 的原生／Java／并发／GC 已完成，但 Windows JDK launcher 的原始非 BMP 命令行参数丢失，oracle 失败；首次 stderr、原工具及 first-failure.json 保留。execution b 的 14 组普通协议 JDK 对照已通过，观察测试宿主误从 kernel32 动态查 WakeByAddressAll 而失败；原工具、first-failure 和已完成 native suites 保留。最终 c 改为 UTF-16 hex oracle 参数及 KernelBase 观察调用，补全全部控制测试和长路径／早 NUL 对照；生产 ASM 未因此修改。

在两个全新目录重放：

```powershell
& D:/Dev/Python312/python.exe scripts/file-input-candidate.py `
  --state .boom/pending-native-three-families-v145-three-families-26-9e4944c57a424d038bb7679b56009811.json `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --output .boom/file-input-stream/review-source

& D:/Dev/Python312/python.exe scripts/test-file-input.py `
  --candidate .boom/file-input-stream/review-source/candidate.json `
  --selection .boom/diagnostic-startup/v146-native-three-families-9c5d0bc2e4db4866b30ad467ceb39e8c/round-000 `
  --native-manifest .boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1/vm-entry.json `
  --native-execution .boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1/execution.json `
  --output .boom/file-input-stream/review-execution
```

主 agent 在另外两个全新目录独立重建并完整复跑：

- `.boom/file-input-stream/root-review-source-v147-a/verification.json`，SHA256 `90f7d3e606676e0cb8be8762b2429b9c63d23526a441b81a947c4a1509c6703f`。
- `.boom/file-input-stream/root-review-execution-v147-a/execution-7305ee5e54cf4dd4ada506146c3e4173.json`，SHA256 `3802862bd01ac58f00ad11caa0d5a7a6f343a692047848cdec0a560d141559cd`。

16 项 JDK 协议、原 Java 读／关闭链及正常／观察两份映像的并发、受控关闭、失败重试和静止 GC 检查通过；两个映像最终各自句柄、owner 根和缓冲区归零，堆正常销毁。实际打开类型的门槛是 `GetFileType == FILE_TYPE_DISK`，已验证对象是普通文件；没有把这个门槛当作额外的设备路径过滤器或任意卷设备的兼容证明。

本批仍为未注册候选。公开 FileInputStream(String／File) 构造器后的 FileCleanable 完整链、自动 Cleaner、来源未知 FD／设备、FIS 子类布局、写入及 channel、完整 System／VM／Minecraft 启动均不在完成声明内。
