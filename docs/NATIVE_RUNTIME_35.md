# 35 包来源校验与原版资源读取接入

35 包已在当前 117 项工具来源下完成来源、Frame 和实际 COFF 校验。
新的标准原生入口已实际越过反射缺口，停在 JDK 资源映射的原生声明。
状态仍为 `pending_runtime_acceptance`；完整 Main、帮助输出、游戏和世界尚未启动。
[31 包原生运行](NATIVE_RUNTIME_31.md)保留为原来输入下的独立历史，不改写成新版本的运行结果。

## 当前来源

本轮保留原来 31 包的汇编和机器码，重新验证其当前工具来源，并登记四组新实现：

| 新增提供者 | 原生声明数 | 已有独立执行验证 |
| --- | ---: | --- |
| [原始 Method 枚举](NORMAL_METHODS.md) | 1 | 原 Java API、JDK 对照、OS 线程和显式回收 |
| [原始常量池读取](NORMAL_CONSTANT_POOL.md) | 14 | 原 Java API、类型错误和只读常量数据 |
| [有界反射调用](METHOD_INVOKE_STATIC.md) | 2 | 原 Java 调用与异常包装 |
| [标准输出](FILE_OUTPUT_STANDARD.md) | 2 | 原输出流、管道和错误返回 |

合计 35 包、102 个原生声明。独立候选的执行范围仍由各自回执限定；新状态没有继承这些候选之外的运行结论。
65 槽命名模块 batch 保留 1,011 项原始 Java 单元／分片记录，没有重做整个 Java 批次的代码生成。
原汇编运行时 DLL 与其实际 89 个汇编源保持原样。

来源迁移结果位于本地忽略的 `.boom/native-reflection-migrations/v204-combined117-b/source-provider-migration-complete.json`，
SHA256 为 `7dc2abc9962c0fe4f3ec9b7d2155366b954f8991b0794a3e055f98cbe5d3a19c`。
新状态 `.boom/formal-native-transitions/v204-combined117-b/pending-state.json`
的 SHA256 为 `7dd0b532630aad054d890fc6fdbe485169883aaf57f18f8366905f0277a73a0d`。
二者均明确保留运行验收未完成标志。

## 同一来源下的资源读取候选

五个额外候选已针对这份 pending35 状态重新构建，完成原始声明／Code、Frame 和完整机器码检查：

- [资源映射与自有库](JIMAGE_NATIVE_MAP.md)：原 `NativeImageBuffer.getNativeMap` 和受限 `jimage` 库加载。
- [AtomicLong 能力查询](ATOMIC_LONG_CAS.md)：原 `VMSupportsCS8` 的硬件能力入口。
- [标量读取](JIMAGE_UNSAFE_READ.md)：五个已持有映射内的只读 Unsafe 操作。
- [批量复制](JIMAGE_UNSAFE_COPY.md)：映射到正常堆 byte[] 的原 `copyMemory0`。

这些额外候选未登记到原始 35 包集合，派生镜像的实际运行另列于下文。旧的 [Java 联合读取试验](JIMAGE_JAVA_BULK.md)
仍绑定旧来源与旧测试镜像，其成功不记作当前 117 项来源下的正式 Main 运行。
本轮独立复核重新执行了标量和复制候选的来源、Frame、规范重汇编、完整 COFF／PE 比对，
并实际拒绝了 11 个旧来源或损坏状态。17 项现有相关回归测试通过。

本地五候选汇总 `.boom/current35-native-preparation-v207-a/candidates.json`
的 SHA256 为 `0583925994df13bd2c23f76fcf3c25665d1047152fe1ee765b9432dcd0d0f3ad`；
主 agent 的独立复核 `.boom/root-current35-review-v209-a.json`
的 SHA256 为 `578529652a8db4c56c410ee48749f1f906d4b9bb082606f6a21c2327b90888ac`。

候选构建工具只接受 31 或 35 包状态，并要求状态中的完整工具摘要与当前工具来源相等。
这项限制用于开发构建的一致性，不是游戏性能优化。

## Main 来源与实际运行

新 Main 源选择仅补入资源读取必需的三个类和四个原始 Java 方法：
`NativeImageBuffer`、其 `$1` 类和 `DirectBuffer` 接口。
私有 `DirectByteBuffer(long,long)` 构造器及标量／复制 Java 调用链原已选入。
完整独立来源验证自然退出 0，用时 965.938 秒，覆盖 8,655 类、71,775 个 Java 方法、
192,735 个汇编函数及 26,932 格静态／初始化失败根。相对旧 Main 恰好增加三个类和四个 Code；
其余 71,771 个方法的来源与 Code 摘要逐个保持不变。
源目录为 `.boom/diagnostic-startup/v205-current35-jimage-source-a`，
`selection-verification.json` 的 SHA256 为
`c498825de85af8b660c97554519add80e4ec0727562c27042c7acd0d8944c317`。

标准原生入口 `.boom/vm-entry-images/v210-current35-main-baseline-a` 已完成实际构建、独立验证和执行。
它复用全部已校验 Java 对象，仅新汇编进程入口，没有接入上述五个额外候选。
原 System 三阶段返回、VM 到达 4，原 argv 为 `['--help']`；
Main 日志初始化越过先前的反射缺口，停在原 `NativeImageBuffer.getNativeMap` 方法 111359，
源行 51461，原 Java caller 111087／PC45。Main 类初始化未返回，Main 方法体和帮助输出均未执行。
该诊断声明的停止不证明 `NativeImageBuffer` 自身初始化已经执行。

实际 ABI14／576 字节报告记录两个后台 Thread.exit 和两个 OS 记录回收、
完整根快照 2,637 个非空项、Parker 打开和关闭各一次；
活动 Parker、文件输入句柄／缓冲／owner 根、监视器持有及 worker failure 全部为零。
堆、注册表、Java 帧清理标志为 7；没有触发自动回收。

```text
native proof  fe7b13518b36a71f7bd057b35ccce79741b183100e79e2e777c6d15b15d225ba
execution     c6e4e262c7474d79e60255a9f15f99b6df7ec2a8a4bfa1bc8c4743400cc78707
ABI14 report  d957b84c53a03ca4da353a80c6dcd16100dd60c8271b233f94b6e3e968fcabe8
```

## 资源 owner 的接入边界

[纯汇编资源 owner 及其生成器](MAIN_JIMAGE_OWNER.md)已通过源码、完整 COFF 和五类实际原生资源测试，
单独的[资源接入与 Signal 清理修复镜像](SIGNAL_SHUTDOWN_ORDER.md)已实际完成原库卸载、
三工作线程回收及全部资源关闭，原 Main Context 保持不变；初始化链的新缺口为
`Unsafe.allocateMemory0(J)J`，原生方法 113555、诊断行 51631。
对应的[纯汇编可写内存 owner](NATIVE_MEMORY_OWNER.md)已通过独立 native、并发和 JDK 向量验证；
[六声明及类型路由的组合服务](UNSAFE_OWNED_MEMORY.md)已接入另一独立 Main 派生镜像，实际运行结果见下节。
[原始类型数组的物理范围检查](PRIMITIVE_HEAP_SPAN.md)也已通过 181 个 native 用例、
8 个 OS 线程共 512 次调用及完整 COFF／PE 等价验证，为堆与原生内存复制提供成员身份和字节边界检查。
该派生镜像复用当前 Java 来源，没有把额外 native 当作原始 35 包 source V 已覆盖的内容。
必须按原 `java.home/lib/modules` 路径打开真实锁定输入，在工作线程全部退出后卸载自有库引用，
并在 Java／堆用户结束后释放 ByteBuffer 持有的映射与文件句柄。
先前组件试验的宿主准备没有被用作这次进程生命周期的执行证据。
自动／并发回收、任意地址 Unsafe 操作、完整游戏和游戏性能提升仍未验收。

## 可写内存接入后的实际 Main

本次绑定为原版专用服务器 `net/minecraft/server/Main`（方法 491841、类 49839），参数 `--help`。
这是无账号的共用运行时初始化验证；客户端图形入口需要另行选择来源、构建和实际执行。

`.boom/vm-entry-images/v234-current35-owned-memory-main-a` 已完成实际构建、规范机器码检查、
完整 PE 独立重链接比对及主 agent 的一次隔离进程执行。
它替换原镜像索引 94／95／196／202 的四个对象，增加五个对象，合计 210 个；
其余 201 个对象保持原字节，原 RO 复制内核保留。
原 71,775 个 Java Code、元数据、根和 runtime DLL 没有重编，未重复完整 source V。
新 native 的九对完整 COFF 另有证明，未被归入原 35 包 source V。

该进程自然退出 86、没有超时，System 三阶段到 VM4，越过原 `allocateMemory0` 停止。
owner 实际分配一块 2,048 字节区域，关闭时完成一次释放，最终 state3、live0、lease0、logical0、metadata0。
记录一次正常内存服务分派和 806 次类型服务分派；分派计数只表示进入服务。
三个工作线程实际退出并回收，堆／注册表／帧清理标志为 7；
Parker／等待／引用处理关闭，映射和文件均清零，自有库引用 3→0、原 unload 调用三次。
三份报告中的 Main Context 一致，pending Throwable 和 VM plan 均为零。

新的首个原生停止为 `sun/nio/fs/WindowsNativeDispatcher.initIDs()V`，方法 138270、诊断行 53934。
Main 类初始化尚未返回，Main 方法体、帮助输出、完整游戏和世界均未执行。
外层 Context 70790／PC2 和静态诊断 binding 分别记录，没有据此推导动态调用栈。

最终 c 元数据修订明确九对新 COFF 的本地 3／组合 6 来源，以及九份继承证明；
补齐两项实际消费的 adapter 源文件直接 pin，并核对状态、source selection、完整验证和 runtime 跨链相等。
原 a／b 文件保留。c 没有重编汇编或重链 PE，不新增执行成功声明。
主 agent 随后实际运行的就是该完整机器码和 c 来源绑定。

本地证据 SHA256：

| 证据 | SHA256 |
| --- | --- |
| 最终 c 机器码／来源验证 | `f51b8b990cd6aaac26f786803309abf25812ed1ba86ba5b4cdbd0d485d8abc34` |
| 完整 PE 重链接逐字节比对 | `5c4f619876a78766180655aa8aff4d7f0962de9f7f06a8be1c9371440e12c878` |
| 实际进程 `overlay-execution.json` | `48b4a5575690d35c99fd27ac19cea7e6a409a1064c3aa8f3df4244de8c6d6f23` |
| 原 576 字节报告 | `78d46aea90229f7f8af7f6f0d92b580196e105544dd77326a407b256f1823865` |
| JIMAGE 256 字节报告 | `f5b90b6090baf283a781d08e5107a3b1c4b23a7640a4c493d357096db5d65fb7` |
| RW owner 320 字节报告 | `a6e439f08a6a90272979d2e80b611b4bf048764422d9ca6d34746505fb694d2e` |

后续[Windows NIO 字段登记镜像](WINDOWS_NIO_INIT_IDS.md)已实际越过 `initIDs`：七个原结果类完成正常初始化，
二十项地址缓存通过独立组件验证。该派生入口只替换一个对象、增加两个对象，其余 209 个保持原字节；
新的停止为原 `GetFileAttributesEx0(JJ)V`，方法 138204、行 53887。
三工作线程及全部资源仍完成清理，Main 类初始化、方法体、帮助输出、客户端和完整游戏仍未完成。
