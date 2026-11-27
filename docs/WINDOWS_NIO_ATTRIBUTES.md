# Windows NIO 文件属性查询

`native/providers/windows_nio_file_attributes.asm.inc` 实现
`WindowsNativeDispatcher.GetFileAttributesEx0(JJ)V` 的汇编服务。
它在经过验证的原生内存范围内调用 `GetFileAttributesExW`，读取真实的 36 字节
`WIN32_FILE_ATTRIBUTE_DATA`；成功结果继续由原 Java `WindowsFileAttributes` 方法解析。
正常 native Frame 和错误辅助函数由源投影工具生成，不更改原 Java 方法体。

此处平台语义依据锁定的
[OpenJDK 21.0.13+3 WindowsNativeDispatcher.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/windows/native/libnio/fs/WindowsNativeDispatcher.c)。
实际原始类输入来自本项目锁定的 Azul 21.0.13+1；两者分别记录，不能当作相同构建。

长期构建工具为 `scripts/windows-nio-file-attributes-source.py` 和
`scripts/windows-nio-file-attributes-candidate.py`。后者的 `build` 显式接受
state、source、parent、pinned-c、slot-abi、assembler 和新 output；`verify` 重新投影原始类及 Frame，
独立汇编四个对象并比较完整非调试 COFF，同时核对实际 Throwable 根区和原内存服务依赖。
槽、Span64 和关闭接口见 `native-config/windows-nio-file-attributes-abi.json`。
它们不选择新 Java、不运行游戏，也不把候选自动登记为已验收 provider；生成输出均留在 `.boom`。
主 agent 已从正式路径独立重建：四份生成 ASM 与已实际执行的版本逐字节相同，
旧对象、发布对象和新 canonical 对象的完整非调试 COFF 均相同；原 Class／Code／Frame／布局及结构常量也分别核对。
这次发布没有重复动态组件测试，也没有改变原 117 文件的来源状态。

## 内存与异常边界

`native_memory_borrowed_span.asm.inc` 在现有 Owner128／Job128 内存服务上提供 Span64 借用接口。
调用者先取得路径的读租约和输出的写租约，再使用指针；边界使用实际请求字节数，不扩大到提交页。
UTF-16 路径的 NUL 查找限制在当前分配范围内，输出至少需要 36 字节。
原 Java 包装路径使用不同的 NativeBuffer 分配；私有 native 的同一分配别名被明确拒绝。
短锁仅保护登记和状态，不跨 Win32 文件调用、Java 回调或等待。

API 失败时立即保留 `GetLastError`，释放两个租约，再通过正常类初始化、对象分配和原
`WindowsException(I)V` 构造器产生真实异常。已有异常／VM plan 时保留完整 Context32。
错误辅助模板为 `windows_nio_throw_error.asm.inc`，不直接写入 Java 异常字段。

256 个持久调用槽分别保存两个 Span64；释放失败时保留真实 token，等待明确重试，不能回收仍有租约的槽。
Java Throwable 临时根独立存放在 256 项 QWORD 数据区，已核对实际 COFF 中的可写、全零、连续存储。
实际进程入口将它加入第十三个原生根区；所有工作者静止、原库卸载后，先 drain 调用槽，再作根快照和堆销毁。
普通 Java 根图和原 35 包／117 文件的来源状态保持不变；没有自动或并发 GC 的验收声明。

## 实际验证

- 锁定 JDK 的解释执行和默认模式分别运行 21 个路径用例，原始结构、解析结果和公开属性一致。
  访问时间会随读取变化，跨进程比较时排除对应 8 字节，其余字段保持逐字节核对。
- 汇编组件实际完成原 System phase1、线程本地绑定和原 NativeBuffer／String 构造；
  20 个非空字符串用例均匹配，包括 Unicode、代理对、内嵌 NUL，以及五个真实 WindowsException 错误。
- 八个不同 OS 线程共执行 256 次原 native Frame 调用，各自核对完整结果和输出尾部；
  六种已有 pending Context 保留、边界／别名拒绝、实际写租约超时和释放后重试均通过。
- 组件退出完成全部线程、十三个根区、原生映射、RW Owner 和堆清理。独立 Span64 复跑也已通过真实租约、
  范围、只读域、失败重试、八线程和完整机器码检查。
- 单独的原生故障派生仅替换三个释放调用操作数，保留其余代码、数据和 unwind；
  释放失败时实际 token 留在持久槽中，真实 Owner.close 返回 busy。停止故障后 drain 真正释放两个租约，
  再完成全部清理。生产查询代码未改，也没有把故障夹具算作生产运行结果。

原 Java 包装器的 null String 用例在到达查询服务之前返回已有运行时的 Context kind4，
尚未物化为 JDK 对照中的 NPE 对象。这是保留的兼容缺口，不列入上述 20 项成功或完整等价结论。
并发正确性测试也不代表已测得游戏性能提升。

## 原版专用服务器入口

实际 216 对象镜像保留原 212 对象中的 210 个，只替换剩余 native 停止对象及进程入口，增加四个汇编对象。
六组实际／规范 COFF 比较通过，完整 PE 独立重链接后逐字节一致；消费者的十一项文件角色及必需输入集合另行核对。

原 `net/minecraft/server/Main --help` 初始化已越过 `GetFileAttributesEx0`，
新的缺口为 `java/io/RandomAccessFile.initIDs()V`：方法 40537，诊断行 104603，Context method75638／PC84。
进程自然退出 86，未超时；System 三阶段到 VM4，三工作者退出／回收，清理标志为 7。
RW 分配与释放各两次，4,096 字节及全部租约／元数据最终清零；原库卸载三次，文件／映射归零，三份报告的 Context 一致。

**Main 类初始化、Main 方法体、帮助输出、客户端窗口和世界均未完成。**
该派生镜像独立验证额外原生候选，没有把它们记作原 35 包的完整来源验收。
玩家启动器仍只保留启动入口。

| 本地证据 | SHA256 |
| --- | --- |
| 组件 20 路径／八线程与清理 | `d398b58ddb7d81df824dfe80f52e49509c6e3fcccc3cbaf5333d95e1d21585e9` |
| 隔离原生故障派生／保留及重试 | `45ba2d06619f7e97fbc099f3bf5de56c0c0bf06d06310cbecefc16eeb4eb134f` |
| Span64 主 agent 独立复跑 | `de202db8f0dcf043784f8b74532ee79c49208a5edf7371f9387c41d69a6951b1` |
| 正式构建工具主 agent 独立重建 | `1fad17b71b4d374daecef0a4273e20b79e74fe73ace1f7ded07f7057a5454284` |
| 旧／发布／新 canonical 四对象等价 | `2ff31d8f24fe980869aa84d53ecf504b4f9406291eb2b9de9d7b2dbf5fd3b766` |
| 216 对象完整来源／机器码验证 | `c5d3b8812d14001e31b5041c18d0e008a579dd53725934049febc5ed23e43091` |
| 独立完整 PE 比对 | `b64b5742741e9bdb3c2b0bc7e896fb7739eda8a1f34d2326f6731f9604067834` |
| 最终消费者角色及输入验证 | `d16107fbe703e0af48717e3a7f801c2b608edf8253c98758f33a8a78a4065c82` |
| 实际原生进程 `overlay-execution.json` | `bfd6c7ae896644abbeef7aa9c8fbb344846b9c99f8e34fe5e6df7058d4e14e7d` |

一次性测试、负例、复跑 Python 和所有 PowerShell 文件仅留在本地忽略目录，不发布到 Git。
