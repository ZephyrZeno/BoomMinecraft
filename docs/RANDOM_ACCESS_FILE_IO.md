# RandomAccessFile 共享文件操作

六个原 RAF native 由汇编实现：`open0`、`read0`、`readBytes0`、`getFilePointer`、`seek0`、`length0`。
普通 Java 构造器、包装方法及关闭链保持原字节码翻译结果。
目前打开只接受原 `O_RDONLY=1`，并检查 `GetFileType == FILE_TYPE_DISK`；这不是严格的设备路径排除。
写入、批量写入、截断和其他打开模式尚未实现，不为这三项生成成功入口。

原始语义分别核对锁定的
[RandomAccessFile.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/RandomAccessFile.c) 和
[Windows io_util_md.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/windows/native/libjava/io_util_md.c)。
原类文件输入仍为本项目锁定的 Azul 21.0.13+1，上游 C 参考版本为 21.0.13+3，分别记录来源。

长期工具为 `scripts/random-access-file-io-source.py` 和 `scripts/random-access-file-io-candidate.py`，
后者显式接受 state、source、parent、pinned、records-source、abi、assembler 和新 output，生成 native／combined 两对象。
完整 verify 同时检查原 FIS 前缀、六个 Frame、实际 4096 项根区及正常 RAF initIDs 的两个独立机器码见证。
通用前缀检查器为 `scripts/native-coff-prefix.py`，接口契约在 `native-config/random-access-file-io-abi.json`；
游戏侧追加模板是 `native/providers/raf_io_shared.asm.inc`。
正式工具从父来源清单定位 FIS，使用正式 initIDs 工具重新投影，不执行父历史候选记录中的临时 Python。
主 agent 从正式路径独立重建，两个生成 ASM 与实际执行版本逐字节相同，旧／发布／新 canonical 的完整 COFF 一致；
五个已有坏机器码用例也被正式前缀工具拒绝。没有因此重复动态组件或重跑原完整来源验证。

## 共享所有权

实现保留原 FIS 提供者的完整汇编前缀，只在最后 `END` 之前追加服务。
原 `FileDescriptor.close0`（39399）及它的正常 Frame、私有锁、4096 项 FD 根、句柄记录和关闭流程保持不变。
RAF 的文件描述符经过原字段地址函数验证后，在同一登记锁内保留 opening4 槽，
成功创建的 HANDLE 才能发布为 open1；Java 原关闭链能够查到并真正关闭它。
未知或外部句柄不因 Java 字段中出现一个 HANDLE 值而被采纳。

读取和定位先借用同一记录，再取得该文件的 I/O 锁；释放时先退出 I/O 锁，再归还借用。
Java 路径转换及异常回调均在锁和借用之外执行。
批量读取先检查 null、边界和零长度；有效零长度在 FD 查找前返回 0，EOF 返回原 Java int 的 -1。
读取结果只复制实际返回的字节，保持数组其余位置不变。
seek 使用完整 64 位位置，允许定位到 EOF 之后，不扩大文件。

RFIO64／ABI1 管理调用准入和活动计数；256 个持久请求槽只存原生 scratch、状态及不再解引用的 Context 标识。
HeapFree 或借用清理失败时保留相应资源供明确重试，已有 Context32 不会为了清理而被清空。
临时 Java 引用继续使用旧 FIS 的显式静止、非移动收集边界，不声称支持自动或并发 GC。

退出时先结束原工作者及库卸载，完成文件属性槽 drain，再执行共享 RAF/FIS drain。
它检查调用、借用及 opening／closing 状态，真正关闭登记内的句柄；失败保留 FD 根、句柄和 VM。
旧 `fir_path` 内部未返回指针的释放失败仍依靠原缓冲计数阻止 VM 销毁，不把它描述为可恢复指针。
全部资源清零后才做原十三个根区快照、线程登记、帧和堆销毁。

## 验证范围

JDK 解释执行和默认模式的 19 组、143 个动作完全一致。
实际汇编组件逐项执行同样的原 String／File 构造、读、定位和关闭操作，包括 64 KiB 读取、两次超过 4 GB 的定位、
关闭后的 null／边界／零长度顺序及完整异常消息。定位测试不写入或扩大文件。
每个用例的句柄、FD 根和原生缓冲都归零，最终共享 drain、十三个根区及 VM／Owner 清理通过。

另一次实际测试执行原 FIS(FileDescriptor) 与 RAF 的共享文件位置及 closeAll 关闭链，
并用八个不同 OS 线程的原 Java Thread／FLS 绑定执行 640 次只读操作和八次原 Java close；
已有 Context32 保留及 RW 模式拒绝通过，最终根、句柄、活动调用和全部 VM 资源清零。
这些是并发正确性记录，不是完整游戏多核性能测量。

null String 和 null File 由原 RAF 构造器显式构造真实 NPE；NUL 路径构造真实 FileNotFoundException，消息为 Invalid file path。
这些情况未进入 native open，不沿用其他包装器隐式 null 的 Context kind4 边界。
原 Java RAF.close 经 FileDescriptor.closeAll／close 调用原 39399，实际关闭句柄；重复 close 安全。

旧代码保护同时检查原源码字节前缀、代码／数据／unwind 前缀、重定位目标和旧符号辅助记录，
节长度和重定位数只允许随追加内容按实际头部增长。
五个保持结构有效的代码、数据、unwind 和重定位篡改被拒绝。
新合成对象另行完整 canonical COFF 比较；新对象中的原 4096 项根区重新核对物理位置，保留原逻辑符号和数量。

## 实际专用服务器初始化

219 对象 EXE 只替换剩余 native 停止对象、进程入口及 FIS 提供者，增加六个正常 Frame 的一个对象；
其他 215 对象保持原字节。完整 PE 独立重链接后逐字节一致，IAT 没有新增导入。
实际 `net/minecraft/server/Main --help` 初始化越过 RAF 打开，下一停止为
`jdk/internal/perf/Perf.registerNatives()V`，方法 116364、诊断行 52052，Context method116371／PC1。
这不证明 Main 已执行全部六种文件操作；六种操作的行为范围来自独立组件用例。

该进程自然退出 86、未超时，System 三阶段到 VM4；三工作者退出并回收，清理标志为 7，
文件、映射、RW 分配、租约及元数据完成清理，三个报告的 Context 一致。
**Main 类初始化、Main 方法体、帮助输出、客户端和世界仍未完成。**
原 35 包的来源证明保持原范围；额外原生实现和物理根区绑定由派生镜像单独验证。

| 本地证据 | SHA256 |
| --- | --- |
| JDK 两模式／19 组 143 动作 | `33d29daf9c813b54933f4e277481a7b52ef0b47d123f1b88893fc4e194add3b0` |
| 实际汇编组件／19 组 143 动作 | `713504fdc18c64868c18cd6d1d348d462cbf339bcfd17022092674101398cf5c` |
| 共享 FIS／八 OS 线程 640 操作与清理 | `468d1000b55f940989ede46abef15efb920502f27dd9ea5c6e6ab8dcf077db33` |
| 正式工具主 agent 独立重建 | `72b10ffe94871a86b09c28d71c873435d7522d02126135bd2e6d3535695337b2` |
| 旧／发布／新 canonical 两对象等价 | `559be24bb13ae934ae20a147aabf0fd0592f90ef8555b823809d06fbef7721e3` |
| 新共享对象完整机器码 | `a14885c6a9831eb0936e97c809cf96f06bdd1d8a432d984d720f7ce3cc715182` |
| 主 agent 旧代码前缀复核 | `53e61669c4891c9d0031cce1137181d14e597740c6c06a3d352fb54b8360dd62` |
| 219 对象消费者验证 | `6d88d39777d8a2242a8efc0d9884309129cc792d29e1dd748ec921648b3e1a52` |
| 独立完整 PE 比对 | `aa348fd01d3c95ad484b6dc10d40cd7d8dc33d5869b06ea9413117a3f4343981` |
| 实际原生进程 | `6c6a2df2238b00a193fcf8b7d7473d0c6d57f8806c4857461f45604ba22dd9e8` |

全部一次性测试与复跑脚本、PowerShell、输入和编译产物继续留在本地忽略目录。
