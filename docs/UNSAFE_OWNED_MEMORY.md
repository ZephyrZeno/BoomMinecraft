# Unsafe 自有内存组合服务

本组件为当前原版 1.21.1 来源下的六个 Unsafe 原生声明生成正常 Frame 入口，
组合[可写内存 owner](NATIVE_MEMORY_OWNER.md)、[原始数组范围检查](PRIMITIVE_HEAP_SPAN.md)
及已有的只读 JIMAGE 域。游戏执行路径均为 MASM；Python 只负责来源投影、构建和开发测试。
它仍是独立 native 候选，没有修改原 35 包验收状态或运行时 DLL。

| 原生声明 | 当前实现 |
| --- | --- |
| allocateMemory0／reallocateMemory0／freeMemory0 | 自有 RW 区域，预算、存活借用及失败回滚 |
| setMemory0 | 自有 RW 区域或已验证的原始类型数组 |
| copyMemory0 | 堆↔RW、堆↔堆、RW↔RW，保留旧 RO→byte[] 路径 |
| copySwapMemory0 | 堆／RW 的 2／4／8 字节元素换序，处理重叠 |

八种基本类型的 plain 读／写共 16 条路径可访问登记的 RW 区域。
布尔值、byte／short／int 符号扩展、char 零扩展和浮点原始位模式分别处理。
原 42 个类型入口的公共前缀、别名和 unwind 保留，仅重定向这 16 条终端调用。
其他 26 条引用／volatile／CAS 路径保持原路由；这不代表它们可访问新 RW 区域。
原 ThreadIdentifiers 的四条计数器路径、原堆字段域和五种只读映射读取继续使用原验证器。
未知地址不会被当作可访问内存。

堆端先检查真实块成员身份、数组形状和物理字节范围。
堆↔RW 复制期间显式持有原生区域借用，复制完成后实际释放；有借用时 free／resize 返回 busy。
只对 busy 状态进行锁外 Sleep 重试，当前开发上限为两秒，超时产生明确失败。
分配失败返回 0，让原 Java 包装自行构造 OOME；不能靠清除 Context 后重试掩盖错误。
已有 pending Context 的全部 32 字节保持不变。

当前不支持 RO→RW、RO→char[]／换序、任意地址以及 RW volatile／CAS／引用操作。
原始地址在 OS 重用后的 ABA 限制仍存在。
这些是明确的兼容边界，组件测试没有给出游戏多核性能提升结论。

## 来源和构建检查

`scripts/unsafe-owned-memory-source.py` 从真实类文件投影六个声明、原 26 个 Java Code、
类型入口与数组布局；`scripts/unsafe-owned-memory-candidate.py` 构建 Frame 和类型路由候选。
`scripts/unsafe-owned-memory-service-source.py` 生成实际服务，
`scripts/unsafe-owned-memory-service-candidate.py` 组合六个实际汇编单元。
开发命令的 `--help` 列出所需状态、来源选择、owner 和数组 helper 证明输入。

验证器会重新投影完整 Source／Frame／Code 模型并要求元数据全等，
随后核对实际源码、EXTERN／PUBLIC、完整规范重汇编 COFF 和类型前缀差异。
不能仅给一个自洽的候选重新计算摘要，改变原声明到实际操作的映射。
复制入口的原 `copyMemory0` 定义被完整替换，旧 RO 复制服务及内核分别保留，避免重复定义或丢失依赖。

## 实际组件执行范围

冷进程组件测试通过原 System phase1、primordial／FLS 和原 `Unsafe.getUnsafe` 取得真实对象，
实际执行六个正常原生入口、plain 16 路径、char[]→RW→byte[]、堆间复制／填充／换序，
以及原 Java 分配／调整／释放和零长度／参数检查路径。
22 个 pending Context 用例逐 32 字节保持不变。

另一冷进程在 Java 前打开真实锁定 modules 映射，实际验证五种 RO 读取、旧 RO→byte[] 复制，
拒绝 RO 写入且回读字节不变，并执行四条原线程计数器路由。
测试结束实际完成线程、堆、RO 资源关闭及 RW owner 的 closed3／live0／lease0／metadata0。

对应本地组件回执为 `.boom/unsafe-owned-memory/consumer-smoke-v232-b/execution.json`，
SHA256 `1197c0d708d6249ec559f029de05e3fa89eaaf93c618e038d56a5c3fc568e2da`。
这些组件执行不等于 Main 或完整游戏启动；原版入口的实际观察另行记录。

完整 240 个 JDK 参考向量也已逐项通过原 Java／native 的值、载荷及真实 IAE 对象类型匹配。
8 个实际 OS 线程共执行 512 轮原 Java 分配／填充／复制／释放和非对齐 long 读写，核对 3,072 项结果；
最后实际关闭 owner，live／lease／metadata 均为零。
本地回执 `.boom/unsafe-owned-memory/consumer-vectors-v235-b/execution.json` 的 SHA256 为
`24b499d914a915ec36c4b60bff9e753ffa52e1a86fef5cfd18ab560b0418822d`。
初次向量测试误按另一 Context kind 判断 Java Throwable 的失败记录保留，修正仅涉及测试判定，服务汇编未改。

后续独立 c 组件保留服务源码不变，再次通过上述向量／并发，并增加真实借用冲突时的读写／释放／调整重试、
两秒超时后 Context20 且区域和内容保留、退租后的正常回收，以及静止后的四轮显式 GC 和根快照检查。
有意超时发生在测试私有进程，未记作正常游戏路径；没有启动自动或并发 GC。
本地 `consumer-vectors-v235-c/execution.json` SHA256 为
`6ac4c17d58c4de95d38dd73290475dc4051888124994dfd048e6013e8debaf57`。

## 原版进程生命周期

`scripts/main-native-memory-owner-source.py` 生成独立进程 owner 和四处可逆入口改动。
纯汇编 owner 在 Java 前初始化并绑定，在所有使用者退出、原库卸载、堆和 JIMAGE 资源关闭后再关闭、解绑。
关闭失败保留 owner 及绑定，不写成功状态。它只观察 Main Context，不修改 pending Throwable 或 VM plan。
当前开发配置为 4,096 个记录槽、1 GiB 预算；并非预分配 1 GiB。
独立 CREATE_NEW 的 320 字节报告记录真实状态、计数和前后完整 Context，未执行状态保留 FFFFFFFF。

主 agent 的[实际专用服务器 Main 初始化](NATIVE_RUNTIME_35.md#可写内存接入后的实际-main)现已越过内存分配停止，
实际创建 2 KiB 区域并在退出时释放，清理标志为 7。
新的缺口是 Windows NIO 文件系统初始化；Main 类初始化、方法体和完整游戏仍未完成。
