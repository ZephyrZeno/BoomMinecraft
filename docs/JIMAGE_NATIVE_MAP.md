# 原 NativeImageBuffer 映射查询

本组件仍是独立、未注册候选。原 Java 类初始化、正常对象构造和文件映射 owner 的职责分开验证；机器候选通过不代表完整资源读取或 Minecraft 启动通过。

锁定 JDK21.0.13+3 的 `NativeImageBuffer.cpp` 只执行 `GetStringUTFChars`、`ImageFileReader::find_image` 和 `NewDirectByteBuffer`。`find_image` 在已有 reader 表中逐字节比较名字并增加 use count，不会打开文件；没有已有 reader 时返回 null。原 `BasicImageReader` 的 null 分支继续执行 FileChannel 路径，组件不替换这个分支，不修改 `USE_JVM_MAP`。

原 `NativeImageBuffer.<clinit>` 经匿名 PrivilegedAction 调用 `System.loadLibrary("jimage")`。源 native adapter 先初始化 owner，再进入 native frame 和服务。原 diagnostic native stop 没有这些前置动作，因此旧主进程到达裸 stop 不能证明该初始化或库装载已经发生。

官方固定源在 `.boom/jimage-native-map/pinned-sources/jdk-21.0.13+3`，下载 URL 和 SHA256 保存在 `native-downloads.json`。Java 源来自锁定 SDK 的 `src.zip`，条目与 ZIP 摘要在 `sources.json`。

- `NativeImageBuffer.cpp` SHA256 `31eed6d4d7e45595c883a239d6cc228709ac59cb6dfe11010b60de7ddbfd03cb`。
- `imageFile.cpp` SHA256 `1484ea4c11a226cb8b795d4a36ce797bf1e9496c3d7f26b34f3c1cdb489a03f2`。
- `imageFile.hpp` SHA256 `dec917541c8cb7f112a6b230b44633c0a4367ab728f5ebce47f6644327d8b44f`。
- `jni.cpp` SHA256 `49f0d0c7507c23afa7c3cdf56a4c5ee0d5e5bd18e9e52fd98376d54ea52544b3`。

JNI 的真实构造入口是私有 `DirectByteBuffer(long,long)`，描述符 **`(JJ)V`**。容量检查由原 Java `checkCapacity(long)` 完成；不改成 `(JI)V`，不截断 long 容量，不宿主写 address/capacity。模型从原声明、Code、正常 String 和继承的 Buffer FMAP 动态取得方法 ID、字段偏移、布局和普通 native frame。当前 server 中的 111359、53515 等编号只是证据，不是跨 plan 的 schema 约束。

独立的 [JIMAGE owner](JIMAGE_OWNER.md) 使用真实只读 Win32 file mapping。bridge 仅调用其 lookup/release，不能调用 open。组件中的资源 bootstrap 是显式额外 ASM owner 操作，需要实际输入文件、精确 key、预期长度和生命周期；不会声称此前 VM 已持有映射。

JMAP80/1 的 owner 指针在 +8，状态在 +24。open/ready 会核对真实 Owner128 magic、大小、ABI，并在 owner 锁内核对 ready 状态。每次 lookup 成功都获得一份真实租约。Node96 仅保存 native job、真实 view/length、HeapAlloc owner、token 和链表指针；lookup 结束立即清掉临时 char[] 地址，另存 token 以免 release 清零 Job 输出后丢失重试信息。没有 Java oop，因此本族 `native_root_spans=[]`。

成功返回的缓冲区租约一直保留到受控 VM 结束，即使 Java buffer 在静止 GC 中被回收。构造失败只释放本次 lookup 的租约。release/HeapFree 失败的节点继续跟踪，关闭可重试；close 拒绝活动 native 调用和并行 close。释放这些租约前必须先 join 工人、结束所有 Java 帧和所有 heap/view 使用者。目录不是自动 Cleaner，也不是并发 GC。

key 使用原 UTF16 code units 精确比较，不折叠大小写、不规范化路径；对来源于同一 Java 名字的 key，UTF16 身份与 JNI modified UTF8 的身份一致。Win32 owner 的真实 key 不可能为空、含 NUL 或超过 32767 units，故这些有效 Java 查询可预先证明为 miss；实际 owner 状态 4 至 12 仍显式失败，不能转成 null。未证明任意外部 VM 引导路径的 UTF8/modified-UTF8 编码历史与本 UTF16 registry 一致。

自有 jimage 库变体替换原 net/nio provider 的一个 COFF，不能与原对象同时链接。原 net/nio helper、数据、全部机器执行前缀和 relocation 保留；只改四个原 native adapter 的终端跳转，另接独立 dispatcher 与单模块状态机。实际 GetModuleHandleExW self pin、真实附着 Thread、bridge/owner ready callback 和 1.8 版本检查完成后，才发布原 `NativeLibraryImpl.handle/jniVersion`。它是本项目 ASM 模块，不声称原 C jimage 定义了此 JNI_OnLoad；不会暴露 Context/argv 为 JNI 指针，也不提供标准 `findEntry0` 地址或加载 JDK C DLL。模块卸载不关闭独立 VM mapping owner。

JDK oracle 在 `.boom/jimage-native-map/jdk-oracle-v179-a/result.json`。13 项实际结果包括 VM 已持有 SDK image 的 hit、重复调用得到不同 wrapper/相同真实 view，及未缓存的已存在文件、空串、NUL、大小写、dot、斜杠、长 key、孤代理 miss。JNI buffer 的容量、位置、限制、direct/array/read-only 标志、字节序和 header 来自真实 JDK；JVM 只用于 oracle 子进程，不进入交付运行时。JDK 既有 SDK registry 与组件显式填充的项目隔离 registry 不冒充相同初始化历史。

首个原主进程 owner 初始化观察保存在 `.boom/jimage-native-map/owner-init-main-v173-a/result.json`，SHA256 `8c781a6e11ea1e5798c766a2d958e78143bf2365d02d1de5f049ee00315be803`。该次只在真正进入 native 前要求原 owner 初始化，实际停在原 class11971 的 source-admission row7425；未造 class descriptor、未返回 null、未执行新 native。

开发首败保留：`frame-check-v176-a` 记录测试器把 frame SHA 字符串误比摘要对象的假阴性及独立重验零差异；`focused-source-v177-a/observation-first-failure.json` 记录接口 DirectBuffer 无可分配 layout 的观察 EXPORT 请求被拒。新的 focused b 仅移除该无效观察，Java/共享工具/原 COFF 不变。`source-bound-v176-a/b` 和 `library-source-v178-a/b` 为历史候选，不用当前 verifier 冒充其仍可验真。

本次正常源选择已自然完成完整 V：`focused-source-v177-b/source-selection/images.json` SHA256 `f454d178646b0ed1228765a6b7a182c9d96a64afbb64eb405add8b0299f74d38`，完整回执 SHA256 `e45acae7e9998b002714c01b760589b787a34ff86d04889585d791a16e5c60e5`。最终实际集合是 8583 classes、71603 Java methods、192236 functions、26761 source roots 和 95 assembly units；旧进度中的 7831/70091 不当作最终数目。后续 native-only 镜像逐项重核 F.inputs、当前通用 E.context、原 canonical 对象顺序/RSP，并分别封存首次/最终 SHA；原 full V 不重复运行，也不声称覆盖额外 native 对象。

`execution-v180-f/images.json` SHA256 `4bcf59b972506ef49a6adac41d7c82ca81ecbf0e21c2da93ef05ef4f04d9b9c4` 的冷原 Java 执行回执 SHA256 `588f01228452e82e3a5a135bbf10337b86a5cd3039df31737e0bf4a83fb0fdee` 明确 **verified=false**。已经实际通过的是原 primordial Thread/ThreadGroups、正常 FLS 与 RPR/OWAI/Parker/Signal 生命周期，原 Properties/System.setProperties/VM.saveProperties/System.setJavaLangAccess 配置 API，以及：

- 原 NativeImageBuffer owner 从 cold 到 ready，匿名 action 的 System.loadLibrary 真正返回；没有宿主写 Java 字段或类状态。
- 真实 self pin 和 1.8 检查后，原 Java ConcurrentHashMap 持有的 NativeLibraryImpl.handle 等于 DLL 实际 HMODULE，jniVersion 为 65544。
- 已初始化但没有 image 的真实 registry 只 lookup/miss 一次，返回 null；没有打开映射，长期 native node 数为 0。
- 显式 ASM resource open 后，原 DirectByteBuffer/Bits 初始化继续到 AtomicLong.VMSupportsCS8 原 native 70380，原 row131819，caller52776 pc41，Context B001；没有绕过 AtomicLong 的原静态赋值。
- 此次失败构造的新 lookup 租约释放成功。独立 cleanup Context 先 quiesce/join 工人，再调用原 native unload，最后按 Parker→OWAI→RPR 关闭、detach/destroy、frame release、heap destroy、bridge/owner close 执行。原失败 Context 32 bytes 不变；最终 native nodes/leases、文件/映射和 self module pins 均为 0，worker failure/held monitor 均为 0。

独立 `jimage-native-machine.py` 在原 B/N 回执之外重汇编两份 canonical COFF，额外约束 section flags、所有 symbol value/type/storage/aux、全部代码/数据/relocation/unwind。f 镜像封存的两个完整机器回执 SHA256 分别为 `828f6fdd4a8d9f0d1538dba1153ac91bb70793bd3e335887436e17d80c2a4fb6` 和 `6a6a4899aa583c3ec35b554db939e82b5cf4bcbfeee198623c3c316ffa1abfba`。实际 formal31 的原 NativeLibraries COFF 4555-byte 执行前缀也独立对比通过，差异仅四个 adapter JMP operand。

a 至 d 是测试器在 guest 前被拒的历史：缺正常 worker 关闭边界、误用 entry_exports API、未显式允许 M 原有 GetTickCount64/Sleep、及用 `.boom` 专用检查器处理工具/SDK 输入。没有替换 Java 或绕过拒绝；各目录保留。e 已真实达到同一 AtomicLong frontier，但 finally 的 self pin 未卸载；f 用独立清理 Context 补全原 unload，保留 e 原证据。

上述 f 回执不包含成功的 JNI JJ 构造、8 OS 并发、4 轮 GC、原 ByteBuffer typed read 或 bulk copy；后续联合执行见下文。测试器中的断言须有实际执行结果才能计入验收。任何 GC 验收只能在所有 Java 帧及外部工人静止时覆盖本选择的九源 bank、primordial/main 和 native spans；Context pending exception oop、活动 frame/线程栈需要另一协议，不能称全部运行期根或自动 GC。正式 registry、工具清单、原 runtime DLL 均未接入或改动。

主 agent 在全新 `root-frontier-v189-a` 冷进程独立重建并执行同一前缀，两份完整 COFF 校验再次通过。`execution.json` SHA256 为 `add7c1174d3e33b6b5ab6ba576ef56123bca7d2f90e20cf3f02f7a9c424261ed`，仍明确 `verified=false`，原 Context 为 B001、caller52776 pc41、native70380；所有清理项通过且 self module pins 为 0。独立 `review.json` SHA256 `2b88ad0fe479ebed5b8c5a9336cf102794009f69259f915c808d9f10c7df7f7a` 仅验收上述前缀、预期停止及完整清理，不提升 JNI 构造或游戏启动范围。全新 `root-oracle-v189-a` 的 13 项原 JDK 对照也通过；完整机器验证器的 2 个阳性和 8 个真实 COFF 篡改负例通过。早期独立复核把平面冻结记录传给仅接受嵌套摘要的检查接口，在任何 Java 执行前被拒；改为显式记录格式转换后重跑，原候选与共享源没有变化。

后续 `atomic-baseline-v189-c` 在仅补入[真实 CX8 查询](ATOMIC_LONG_CAS.md)后完成原 AtomicLong/Bits/DirectByteBuffer 初始化和 JNI `(JJ)V` 构造。8 个真实 OS 线程各调用 64 次原 getNativeMap 与构造器，4 轮静止 GC 通过；此时原 `getInt` 仍报告 Context20，明确记录旧 typed 模块的堆外读取边界。

`atomic-scalar-v192-a` 接入[只读标量读取](JIMAGE_UNSAFE_READ.md)后实际通过原 `getInt(0)`：Context.kind=0、值 `0xDADAFECA` 与映射文件头的大端解释及 JDK 一致。原 Java、源数据、VM 入口及已有 native 保持原字节；额外 native 对象分别经过来源、Frame8、完整 COFF 验证，剩余诊断桩使用严格的全叶函数校验器。父 accepted31 与候选 pending31 各自保留原标签，只在完整 batch/plan/provider/frame/runtime/tool 身份及明确父引用相等时合流。

主 agent 在 `root-joint-v193-a` 全新构建和冷进程中再次完成上述原调用链、8 OS 线程共 512 次查询/构造/读取及 4 轮 GC，回收对象数为 `[1143,0,1,1]`。主线程、后台线程、句柄、映射、native 节点、租约和 self pin 全部正常关闭。`execution.json` SHA256 为 `3b1063a22c93c884af8b88bc9c6142bf9d129850471c7f8c7f76fca8a8f16ba5`；另一次 13 项 JDK 联合对照位于 `root-joint-oracle-v196-a/result.json`，SHA256 `d34a2b021b9d8faaa6319bfe06e78b089a3675c65e4af1d8bb216a2267aaca0f`。

该联合结果验收正常映射缓冲区及上述标量读取。原 Java 批量读取仍在单独接线；完整 Main、完整 VM 启动、自动或并发 GC、完整 Minecraft 和世界均未完成。原 f、失败尝试和独立内核回执保留各自的历史范围。
