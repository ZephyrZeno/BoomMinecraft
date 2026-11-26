# 独立正常 Reference 读取、比较和清除

`native/providers/reference_referent_get.asm.inc` 统一处理四个锁定源码中的 private instance native。游戏执行仍是 MASM，Python 只负责来源核对、构建和测试，JDK 只作对照。

| 原声明 | 描述符 | access | 操作号 | 当前 server 编号 |
| --- | --- | --- | --- | --- |
| Reference.get0 | `()Ljava/lang/Object;` | `0x102` | 0 | 50138 |
| Reference.refersTo0 | `(Ljava/lang/Object;)Z` | `0x102` | 1 | 50141 |
| Reference.clear0 | `()V` | `0x102` | 2 | 50143 |
| PhantomReference.refersTo0 | `(Ljava/lang/Object;)Z` | `0x102` | 3 | 50128 |

这些编号仅是当前 server 的证据。模型按原 bootstrap `java.base` 类文件、声明、Code 和 referent 字段身份动态解析，不把方法／类／字段编号固定到跨批次 schema。Reference 的三个 pending-list native 继续由已有正式 `normal-reference-processing-v1` 提供，不在本族重复实现。

## 锁定语义与实现边界

锁定 OpenJDK `jdk-21.0.13+3` 的两份 libjava 包装将四个入口交给 HotSpot；比较使用对象身份，清空后的 referent 与 null 匹配，Phantom 有自己的比较入口。[Reference 包装](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/Reference.c)、[Phantom 包装](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/PhantomReference.c)、[HotSpot 实现](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/share/prims/jvm.cpp#L3001-L3040)

本后端仅在非移动堆、静止回收边界下实现读取、身份比较及显式清除。读取和比较各取一次对齐的 referent 快照，清除在线性化点执行原子 `xchg`，不调用入队操作。接收者、比较参数和非空 referent 均验证堆归属；继承 FMAP 验证实际类型、八字节引用宽度、对齐和引用前缀。已有错误保持不变，null 接收者与无效接收者分别保留当前源异常边界。

原 Phantom.get 是返回 null 的 Java 方法，原 Reference.refersTo 通过正常虚派发选择 Reference 或 Phantom 的实现；模型核对这六个 Java 方法的 Code 和调用目标。错误的 private-native 类型组合拒绝执行，clear0 也拒绝 FinalReference 类型。FinalReference 的合法非活动引用操作仍由其原 Java 方法管理。

HotSpot 的弱读取、无保活比较及清除还包含各 GC 专属访问规则。本后端没有实现这些并发 GC 屏障或自动弱可达发现，当前 collector 仍把正常引用前缀作为强边扫描；因此不能将这里的静止回收保根测试记作完整弱／软／虚引用 GC、自动通知或类重定义支持。

四份原生语义文件保存在 `.boom/reference-referent/pinned-sources/jdk-21.0.13+3`，摘要由模型固定核对：

| 文件 | SHA256 |
| --- | --- |
| jvm.cpp | `84436b103fb7869e445bac95d2e82e9de9160c2da327a4cf54f4e84555150ad9` |
| Reference.c | `f56c77e560530c747d9af26e907e051d7c49a36ca6360d75ca3e803a7cae0e90` |
| PhantomReference.c | `a0d730a87699e31a137079f45f1c3d91c0e2e33ce29e269b6357a38704d7b661` |
| javaClasses.inline.hpp | `954c5f971f3b7ee52b4572c3bf9b072d9ac2908478caa777291048efa3326ce5` |

## 正常布局和独立 source／COFF

服务名保留为 `boom_provider_reference_referent_get`，pool 为独立 `boom_provider_reference_referent_pool`，现为 `RGET48/2`：

| 字节偏移 | 内容 |
| --- | --- |
| 0／4 | magic／ABI 2 |
| 8 | 正常堆单元地址 |
| 16 | 原 referent FMAP 过程 |
| 24 | 正常 runtime type map |
| 32／40 | 原 PhantomReference／FinalReference 类型描述符 |

`reference-referent-source.py` 验证 88 个继承接收者的源身份、祖先和实际 referent 位置。本批字段映射为 29684，所需类为 FinalReference、PhantomReference、Reference（当前 5156、5165、5166）；这些数字同样动态取得。依赖仅为正常 `runtime_metadata` 基础模块，无 Java upcall、外部函数或新增持久根。实际 COFF 有 18 个导入、10 个导出和四份正常 native adapter／frame。

旧 `reference_referent_read.asm.inc` 和 NIO 源／COFF 均保持不变。历史 get-only 版本的 171 字节指令等价证明仍保存在 `source-bound-v145-c`；扩充后的类型检查和四操作内核使用新的 source／COFF 与执行回执，不沿用旧等价结论。

当前 source／frame／ASM／实际 COFF 证明：

- `.boom/reference-referent/operations-source-v145-a/candidate.json`
- `.boom/reference-referent/operations-source-v145-a/verification.json`
- verification SHA256：`2c85ae183c4a20b6065f4718949b1b336c34931c8164a503d9d760551b3097bb`

## 最新原版源码映像中的执行

独立重链消费已经完整验证并实际运行到 Reference.refersTo0 的正式 23 source 选择：

- `.boom/diagnostic-startup/v145-native-class-loader-parallel-ec0736fc2365423ebb73fa7afb89c5ed/round-000`
- source verification SHA256：`bbeaeef00ce19d601e6585167383e0424c7cc4e5df87ee83c67acf027bd44f0c`
- 原生进程 manifest：`.boom/vm-entry-images/ea06ed49ac6a4fc0a9943f74c5d8ef55/vm-entry.json`
- 原生进程 verification SHA256：`c2eb44e1acb7e3a8a719b2498767b8e483de9c7a3e1aec28ee2fe98ded3f5b7c`

测试分别核对两层摘要、原生 manifest 的 baseline_directory 和 accepted_source_verification_sha256、原生 proof 对 manifest 的摘要，以及实际执行回执绑定。两个 verification 不视作同一份证明。

新输出仅移除四个原 native 开发 stop，再链接独立 provider。原 Java、虚表、48 份已验证 source 分单元和其他 provider COFF 不改，正式 registry／清单／共享工具不改。Weak、Soft、Phantom 接收者通过原 Java 构造器写入 referent，测试调用原 get／refersTo／clear Java 委派及四个正常 framed native；宿主不写入或清空 referent。

实际检查覆盖身份相同／不同、原始 null、重复 clear、继承字段、Phantom.get 返回 null 而比较仍找到原 referent，以及错误接收者、内部指针、外堆比较参数、已有错误和回收后的接收者。FinalReference 仅用未构造的源布局对象作非法 private-native 类型负例，不计作其 Java 构造或合法操作验证。正常语义另与锁定 JDK 的 Weak／Soft／Phantom 行为对照。

8 个真实 OS 线程完成 16 轮、2048 次 get／refersTo／clear。每次操作保存开始／结束时间、结果和线程 ID；每轮要求在真实 clear 调用区间内存在一个共同切换点，满足全部清除前／后读结果及调用先后关系。包含并发重复清除，完成后所有工人 join。这里只证明并发正确性，不据线程数量声称提速。

## 静止 GC 与根快照

测试读取九份正常源／缓存根 span，总物理槽数 1,182,089，其中本次有 8 个非空值。所有工人退出后，宿主完整快照非空源 oop，去重形成临时根向量，并单列测试接收者／独立强目标句柄。每个非空值必须包含在紧缩集合内。每份 span 的物理／非空数、原始 bank 摘要、向量去重前后数和向量摘要均记录；每次 GC 后再次核对原 bank 摘要，宿主和 collector 都不修改原根槽。

四次真实 `boom_heap_collect` 分别验证：

1. 只附加接收者强根，当前引用前缀保留它的 referent。
2. 原 Java clear 后，独立目标强根仍保留目标，get 返回 null。
3. 去掉目标强根后，已清除的目标实际回收。
4. 去掉接收者根后，接收者实际回收，后续 stale native 调用被拒绝。

根向量去重前／后分别为 9／9、10／10、9／9、8／8；实际释放对象数为 27、0、1、1。最后堆销毁成功，没有遗留 monitor／heap 所有权。

第一次完整物理根数组超过 collector 的 1,048,576 参数上限，失败发生在宿主检查、尚未执行 GC。该失败、工具快照及已通过并发历史保存在 `operations-execution-v145-a/first-failure.json` 及同目录。没有为掩盖上限而修改 ASM。`operations-execution-v145-b` 保留后续已过四轮 GC、但 JDK oracle 泛型源码编译失败的记录；修正测试源码后使用全新的 c 目录完成全轮。

## 完整回执和重放

- 实际执行：`.boom/reference-referent/operations-execution-v145-c/execution-5c1fd2c2b39f4c67b76c03a973306bf4.json`，SHA256 `21895aa9ae07246a522b3ec86c905d3d0db82ba04e41b9f1305582a282a6edcf`。
- 同目录 `images.json`：SHA256 `f3d905cbb293134f1dae2e44cfe5a93450992789472466933f1ebaa6ac1791cb`，记录全部链接输入、两层原证明和四个 stop 的精确替换。
- `linearization-781a5d235fd240f9a8c0c67ba52aabe6.json`：SHA256 `8cd1f09e1be6e07898b1669423be770c7fc84dcfe4d5c2f336b2d1e558c29590`。
- `quiescent-GC-b8965861101e4302bfd0404ff7cb5b16.json`：SHA256 `1aca845841866a40f3956157280f0c3cf287a09c1fc190842b4e2b822b8e6b0e`。

主 agent 在独立新目录重复执行，四个 native／原 Java 入口、8 个 OS 线程的 2048 次操作、四轮真实 GC 和 JDK 对照均再次通过。回执为 `.boom/reference-referent/root-operations-v146-a/execution-7e3bcd953d064326927a788086893114.json`，SHA256 `3b60424e2a50a137b24b997496cae4b49f7e832e30e7337cfb742c164950eb2c`；同目录 `quiescent-GC-99d42ef8ebfd4e3394d09237843ad0f8.json` 的 SHA256 为 `5038919c0fee1fe00ec0b1a5f3155d5138272a9274a821c36f0e280038392b8a`，释放对象数同为 27、0、1、1。

在新目录建立 source 候选：

```powershell
& D:/Dev/Python312/python.exe scripts/reference-referent-candidate.py `
  --state .boom/pending-native-class-loader-v145-23-23a1a5d3dc5646749ab64939274c821d.json `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --output .boom/reference-referent/review-source
```

以已验证原输入独立重链执行：

```powershell
& D:/Dev/Python312/python.exe scripts/test-reference-referent.py `
  --candidate .boom/reference-referent/review-source/candidate.json `
  --baseline .boom/diagnostic-startup/v145-native-class-loader-parallel-ec0736fc2365423ebb73fa7afb89c5ed/round-000 `
  --baseline-execution .boom/diagnostic-startup/v145-native-class-loader-parallel-ec0736fc2365423ebb73fa7afb89c5ed/execution.json `
  --baseline-native-manifest .boom/vm-entry-images/ea06ed49ac6a4fc0a9943f74c5d8ef55/vm-entry.json `
  --output .boom/reference-referent/review-execution
```

该四入口 family 现已登记，并在[第 26 组正式冷源验证](REFERENCE_REFERENT_FORMAL.md)通过同一组原 Java／并发／GC 检查，没有替换 native stop。独立候选证据保留；完整 System、VM 和 Minecraft 仍未完成。源输入仍受非移动、静止 GC 和原版未变换边界约束，不提供完整弱引用 GC。
