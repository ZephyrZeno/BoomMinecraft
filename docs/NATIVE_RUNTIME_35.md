# 35 包来源校验与原版资源读取接入

35 包已在当前 117 项工具来源下完成来源、Frame 和实际 COFF 校验。
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

这些候选尚未加入 35 包的 Main 运行镜像。旧的 [Java 联合读取试验](JIMAGE_JAVA_BULK.md)
仍绑定旧来源与旧测试镜像，其成功不记作当前 117 项来源下的正式 Main 运行。
本轮独立复核重新执行了标量和复制候选的来源、Frame、规范重汇编、完整 COFF／PE 比对，
并实际拒绝了 11 个旧来源或损坏状态。17 项现有相关回归测试通过。

本地五候选汇总 `.boom/current35-native-preparation-v207-a/candidates.json`
的 SHA256 为 `0583925994df13bd2c23f76fcf3c25665d1047152fe1ee765b9432dcd0d0f3ad`；
主 agent 的独立复核 `.boom/root-current35-review-v209-a.json`
的 SHA256 为 `578529652a8db4c56c410ee48749f1f906d4b9bb082606f6a21c2327b90888ac`。

候选构建工具只接受 31 或 35 包状态，并要求状态中的完整工具摘要与当前工具来源相等。
这项限制用于开发构建的一致性，不是游戏性能优化。

## 正式入口剩余接入

新 Main 源选择仅补入资源读取必需的三个类和四个原始 Java 方法：
`NativeImageBuffer`、其 `$1` 类和 `DirectBuffer` 接口。
私有 `DirectByteBuffer(long,long)` 构造器及标量／复制 Java 调用链原已选入。
源准备结果为 8,655 类、71,775 个 Java 方法和 192,735 个汇编函数；完整来源验证与实际执行单独记录。

正式进程还需要纯汇编的资源 owner 启动和退出流程。
必须按原 `java.home/lib/modules` 路径打开真实锁定输入，在工作线程全部退出后卸载自有库引用，
并在 Java／堆用户结束后释放 ByteBuffer 持有的映射与文件句柄。
先前组件试验的宿主准备不能替代正式进程的这段实现。
自动／并发回收、任意地址 Unsafe 操作、完整游戏和游戏性能提升仍未验收。
