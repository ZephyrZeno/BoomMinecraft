# 正常平台线程的 Unsafe.park / unpark 候选

本批实现锁定 JDK 原声明 `jdk/internal/misc/Unsafe.park(ZJ)V` 与
`unpark(Ljava/lang/Object;)V`，交付代码为 MASM。真实原 Java
`FileInputStream(String/File)` → `FileCleanable.register` → Common-Cleaner →
`ReferenceQueue` → `LockSupport.parkUntil` 已执行；线程实际等待并通过既有 VM stop
协议退出。本批尚未登记正式 provider，未接入生产 VM driver，也未完成 Minecraft 启动。

## 源、帧与复用范围

`scripts/unsafe-park-source.py` 从锁定原 classfile 动态取得两个 native 的方法、类、
access、descriptor 和 source hash，要求原 native 无 Code，access 为 public native。
本 server 的证据编号是 park 113401、unpark 113400、Unsafe 12149；这些编号不作为跨批次
schema 约束。普通 native adapter 使用既有 Context32 / argv / 原 native frame，未暴露
Context 指针为 JNI 指针。

模型复用正常 Thread start 和 Object.wait 的源验证，动态取得 Thread.eetop、tid、
interrupted 的 FMAP，保留派生 receiver 映射和正常 heap/type 验证。每个 gate 由
`boom_object_new` 分配正常 Object，再调用原 `Object.<init>()V`；该原 Code 为一字节
`return`，已作为正式 Java 依赖声明。模型依赖正常 Thread primitives、Thread start、
Object.wait、Reference processing 四个既有 family。

原运行时 DLL SHA-256 为
`572f28fac6ccf9851eca128929698c8d60c55d8b102972041f7f89a8dba05a26`。
候选逐项核对该 DLL 的 runtime manifest 与现有 monitor/wait/Thread/Reference/heap/field
内核源 hash。没有复制或修改这些内核、已有 Thread provider、共享 registry 或 TOOL_FILES。
新 ASM 的 Win32 外部依赖只有四个 SRW acquire/release 入口及
`GetSystemTimeAsFileTime`。等待仍由该已验证 DLL 的 MWAI 实现。

Windows JDK 语义来自锁定 `jdk-21.0.13+3` 的
[Unsafe native 源](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/share/prims/unsafe.cpp)、
[Windows Parker 源](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/os/windows/os_windows.cpp)
及 [Parker 声明](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/share/runtime/park.hpp)。
下载回执和锁定 src.zip 的 Unsafe/LockSupport/Thread Java 源保存在
`.boom/unsafe-park/pinned-sources/jdk-21.0.13+3`，六个源 hash 是模型输入。

## 等待、中断与所有权

PARK128/1 池在 OWAI128/1 与 RPRC88/2 打开后开启。primordial Thread 的实际 FLS
身份在开启时取得；正常 Thread registry 为其保留 JavaId 1。其他线程必须属于 TLCP256/1
的真实 source-owned slot。目标身份同时比较真实 record token、JavaId、Java Thread oop，
并在 TLCP shared lock 下核对当前 eetop cell。没有解引用任意 Java long 作为原生 record。

最多 16,384 个 Slot64，各持有一个正常私有 Object gate。slot 的 Thread oop 是弱身份键，
不会被标为根；只有 gate 在 `boom_unsafe_park_gate_roots` 的 16,384 个 QWORD span 中保根。
全局 up_lock 仅用于短暂 lookup、发布、借用和关闭。分配 gate、调用 Java constructor、
进入 gate monitor、实际等待均不持该全局锁。每个 gate 独立保护单 permit 与 notify。

调用者无需持 Java monitor。实现直接调用 runtime monitor enter/wait/notify/exit，不调用
原 `Object.wait` Java/native 入口，不制造该源 Java frame，也不增加 OWAI 的源 wait 计数。
它没有加入新的跨线程轮询等待器或宿主线程回退。

MWAI 返回 `0x10001` 时已经清除原 interrupted byte；Parker 在返回 Java 前原子恢复该
byte 为 true，保留 interrupt status，不构造 InterruptedException。现有正常
`Thread.interrupt()` 可通过同一 MWAI 域唤醒实际 Parker。MWAI 返回 995 时，先退出私有
gate，再调用既有 `boom_provider_reference_issue_stop`，传播真实 Context/TLS 的 B002。
正常控制边界只能消费自己的 stop token，Context+24 payload 不作私有标志使用。

slot 借用计数保护活跃调用。空闲容量用尽时，仅允许回收不再由 primordial/TLCP 拥有、
且 borrow 为零的身份；不解引用其已退休弱 oop。该容量回收分支已实现，未以 16,384 个
不同已启动线程进行容量压力测试。关闭必须在 Reference/OWAI stop 且 Java worker 全部
join 后进行；活跃等待期间 close 返回 170 且根不变，重复 open 返回 170。成功 close
清除 slot 与 gate 根，重复 close 返回 0。正式 VM driver 仍需按此顺序接线并纳入根 span。

## Windows 时间和目标边界

每线程最多一个 permit，连续 unpark 合并；提前 unpark 可由随后 park 消耗。负 long 或
已过期绝对时间先返回，保留尚未消耗的 permit。有效 park 无论已有 interrupt 或已有
permit 均保留 Java interrupt status，并清除该次消费的 permit。

相对时间单位为纳秒。零表示无限等待，正值按 Windows 原 Parker 向下除以 1,000,000，
不足一毫秒取一。随后按 DWORD 截断；截断后零为即时返回，`0xffffffff` 为无限等待。
绝对时间以 Unix epoch 毫秒计算，不把绝对零解释为无限。测试包括 LONG_MIN、相对
LONG_MAX、绝对 LONG_MAX，以及截断成 0 / INFINITE 的大值；没有实际等待数十天。

正常 NULL、未启动及已终止 Thread 的 unpark 为 no-op。错误 heap 指针和非 Thread
对象 fail closed 为 Context kind 7；这不是对 HotSpot 非法 Unsafe 参数的 Java 异常兼容声明。
已有异常 Context 原样保留。无正常 Java/FLS 所有权的宿主 OS 线程返回 kind 20。
VirtualThread 和外部 JNI 附着线程不在本候选支持范围。没有实现完整 JNI、自动 Cleaner
调度、弱引用发现、移动 GC 或运行中 safepoint collection。

## 真实执行与 GC

source/ASM/COFF 候选位于 `.boom/unsafe-park/source-bound-v147-a`。源契约消费已接受的
28 状态及其 frame proof；执行镜像沿用已独立验证的完整原 26 Java source selection、
冻结八项文件 I/O 候选与公开 FIS primordial fixture。只替换精确匹配 source hash 的两个
原 native diagnostic stop，添加新 provider COFF 和测试 owner 的 park lifecycle。
两项原 native frame row 在 26 与 28 输入间逐项相同；原 Java Code、原 Java COFF、虚表、
类初始化状态和生产 runtime 不变。本结果不是 fresh 正式 28 selection 的整体验收。

测试 owner 仅在 `.boom` 生成。它复用已有正常 primordial 构造、FLS、Reference/OWAI
生命周期；新增 quiesce 入口复用原 stop/join 前缀，以便 join 后、域关闭前显式收集。
公开 FIS 执行器通过封存 AST 复用构造/注册/读取/关闭及清理规则。准备夹具通过真正
Properties.setProperty、System.getProperties、VM.saveProperties 和原 System JLA helper
建立普通 API 上下文，没有宿主写 savedProps、JLA、Thread 字段或任何根 oop 槽。

两个独立冷进程分别执行原 FIS(String)、FIS(File)，均完成原清理登记、读出全部内容及
显式 close/Phantom clear。随后各使用原 `Cleaner.create(ThreadFactory)` 和原
`CleanerFactory$1` 构造其余七个 Common-Cleaner 模式的实际 Java 线程。八个线程的真实
Windows OSId、record token、JavaId 和 source oop 已只读交叉核对。各进程完成 1,024 次
定向 wake/repark，至少 2,048 次真实 park/unpark；每次只指定一个目标，另外七个 wait
序号不变。这是等待正确性和独立性证据，不是吞吐或加速结论。

各进程均验证早 permit、合并、时间边界、原 LockSupport 四入口、原 self interrupt/clear、
foreign 原 Thread.interrupt 对真实等待的唤醒、无效对象和已有异常、未启动/终止 no-op。
八个原 Java worker 经共享 VM stop 退出，exit callback/reaped 各八，uncaught/failure/held
monitor 均为零。后停止入口另验证精确 B002 及 Context payload 保持。

每进程两轮真实静止非移动 GC，均在 worker join 后进行。九份普通 source root span、
五个 primordial root cell、空的 4,096 个 FD owner cell、16,384 个 Parker gate root cell
完整快照，物理 cell 合计 1,204,245。首轮 246 个非空值去重为 216 个，第二轮 237 去重
为 207；逐个断言非空值存在于紧缩根向量，保存每 span 和向量 digest，收集前后根 bank
完全不改。没有额外宿主强根。首轮保留全部九个 gate，close 清除 native 根后次轮回收
全部九个；freed 依次为 `[174, 9]`。此证明只适用于当前静止非移动 collector。

锁定 JDK 仅在本项目 `.boom/.../jdk-oracle` 独立运行，二十项 permit/时间/interrupt/
target-lifecycle 结果与两份 MASM 执行一致。DWORD 解码数值另由已 pin 的原 Windows 源
规则核准；对极长时间使用提前 permit，不把长时间等待作为已测事实。

## 回执和保留失败

最终执行目录为 `.boom/unsafe-park/execution-v147-h`。以下均为 SHA-256；source proof
和各 execution / images / oracle 保留独立文件，不将两层 source 与执行证明合并成一份。

| 文件 | SHA-256 |
| --- | --- |
| `source-bound-v147-a/candidate.json` | `a13e622ca8d154950edd04070657ead86a6bb2564218844432e5033276a84d92` |
| `source-bound-v147-a/verification.json` | `8ee5331a868ee65dc9f95efc3f6d1bebde5f0faa6837661988e92f049531af3c` |
| `execution-v147-h/result.json` | `423244100a6131231b0e59b7e8bd33e183745ad339472c256675fc0196bc0a91` |
| `execution-v147-h/images.json` | `af01c464c282adcc89288c9ca0a3b2f83d75a22d1242418ad0e1d63e3bb74186` |
| `execution-v147-h/string-park-execution.json` | `6aa63c9e6fa7807069ddbd8e64918538bced509f04721e8b4dc7f8d3ef98e710` |
| `execution-v147-h/file-park-execution.json` | `ba3d0ebb524960b1b08516457890bbb225d44da1c1bdf95f7708a032b8faa93c` |
| `execution-v147-h/jdk-oracle/result.json` | `9f97d6cefdd2e67ca98feca622a319155c2dae57c9d323700cf7775c28bb92b8` |

历史目录保持原样：a 是实际一线程公开 FIS/park/VMstop 初验；b 缺正常 VM saved-property
准备，额外默认 Cleaner.create 到原 VM.getSavedProperty 失败；c 准备后到旧 26 镜像的
WinNTFileSystem.canonicalize0 原 stop。两者不作为 park 算法或完整默认 Cleaner 成功。
b 沿用旧公开 FIS 的 verified 字段只覆盖 FIS 本身，未计新增 suite failure；该原始结果
不计完整验收。后续 wrapper 同时要求 failure 为空且新增 suite 完成。d 为测试代码把
模块别名误作 ctypes 指针类型，首个异常和原工具快照已保存。e/f/g 为逐步补齐的独立
执行证明，各次工具快照均保留。最终没有通过修改原 Java 或原 runtime 掩盖这些失败。

主 agent 使用自己的公开 FIS 镜像，在另外两个全新目录独立重建并完整复跑。
source proof `.boom/unsafe-park/root-review-source-v148-a/verification.json` 的
SHA256 为 `832a6341dd5bda3ae035589457ba701576c905e41a4606eef76def7b6a4de37e`；
`.boom/unsafe-park/root-review-execution-v148-a/result.json` 的 SHA256 为
`8707654a3a6b2a09b1c5a568d2d2129eb9eafcaf7167cd14997c4610be87696c`。
两个冷进程、完整新增等待 suite 和二十项 oracle 均通过，`verified=true`、
`all_park_semantics_completed=true`；该标志仅指本页声明的有界候选语义。

本候选没有声称默认 `Cleaner.create()`、完整 System phase1、完整 Cleaner/weak GC、
正式 provider 消费或游戏启动成功。

重建和独立回放需使用全新输出目录：

```powershell
D:\Dev\Python312\python.exe scripts/unsafe-park-candidate.py --state .boom/accepted-native-windows-runtime-v147-28.json --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe --output .boom/unsafe-park/fresh-source
D:\Dev\Python312\python.exe scripts/test-unsafe-park.py --candidate .boom/unsafe-park/fresh-source/candidate.json --public-images .boom/file-input-stream/public-v147-d/public-images.json --output .boom/unsafe-park/fresh-execution
```
