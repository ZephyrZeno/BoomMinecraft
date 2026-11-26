# 未注册 canonical native 的原生前沿探针

`scripts/probe-native-canonical-prefix.py` 在已接受的 26 项输入与原生主进程快照上加入候选中的两个 native 绑定，目的是快速定位下一处实际语义缺口。它是 development prefix，不是正式 27/28 项提供器验收，也不声称完整 VM、Minecraft 或世界启动。

输入包括：

- accepted26：`.boom/accepted-native-three-families-v146-26.json`。
- 原 native owner：`.boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1/`；原执行收据 SHA256 为 `400fe92c4cdfe4ac68a8eb1479960377e42036bbc78062ce620f5aae2e8d282d`。
- 原完整源码选择：`.boom/diagnostic-startup/v146-native-three-families-9c5d0bc2e4db4866b30ad467ceb39e8c/round-000/`，独立证明 SHA256 为 `af58f582032bca130111da68c70a850aab51c236e7f5378d44a34732f5fad93f`。
- 两 native 候选：`.boom/windows-path-canonicalization/source-bound-v146-b/candidate.json`，SHA256 为 `004eb006cd273d134d1a6f1413c2573757b4211db9b56b68543e05e73002746e`。实际 candidate COFF SHA256 为 `80acb16d125cba83a8977f3c14db27e12cb719d24d78febcacfd145f522dcae8`。

探针先运行候选自身的 source/frame/ASM/COFF 独立 verifier，再核对其四个原类 4338、4445、4680、4737 均在主选择的 4701 个类中。String length/toCharArray、IOException(String)、Throwable fillInStackTrace 和原 WinNTFileSystem.canonicalize 的代码及来源 SHA 也须实际选入；所需 normal family 和原 frame 证明不能缺失。

实际基线有 56 个 closure parts，其中 55 个 initialization 分片完全保留。探针只从原 diagnostic-stops ASM 精确移除 `boom_m40671`、`boom_m40674` 各自的 PUBLIC 声明及完整 fail-only PROC，保留原 CRLF、全部 rowdata、其他过程及所有余下字节。新的 stops COFF 与 candidate COFF 替换原 stops 那一项；原 VM-entry.obj、全部其他 COFF、四项库、链接选项和原 PE exports 顺序均保持。

原 ASM 大小为 111613210 字节；仅移除两段各 156 字节，余下 111612898 字节。全部非目标 125552 个 PROC 逐字节比较通过。原 rowdata 前缀 89361503 字节的 SHA256 为 `91c8c820b7e3938240c08146483dec6cabb07cca2e22fc4bd7014320578b5058`，没有修改 row 编号或伪造元数据。

每次必须使用新目录。例如在这些封存源码与输入的环境下：

```powershell
D:/Dev/Python312/python.exe -B scripts/probe-native-canonical-prefix.py `
  --accepted26 .boom/accepted-native-three-families-v146-26.json `
  --baseline-native .boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1 `
  --candidate .boom/windows-path-canonicalization/source-bound-v146-b/candidate.json `
  --output .boom/native-canonical-prefix/new-owned-development-run
```

namespace 后续切换时，旧 full proof 仍是这份历史 26 源码快照的证明，不能被此命令升级为当前正式 28 项的 source 验收。探针不调用完整源码选择 verifier；所有回执显式标记 `full_selection_reverified=false`、`prototype_native_added=2`、`shared_provider_registered=false` 和 `formal27_accepted=false`。

## 实际前沿与清理结果

最终回放目录为 `.boom/native-canonical-prefix/v146-accepted26-canonical-004eb006-c/`。`execution.json` SHA256 为 `330643f293d47e11be054da298995c16a5f05b8dd927e3d4f74e610cb70de379`，owned EXE 以诊断码 86 正常返回，探针进程自然退出 0。

它实际越过旧 canonicalize0 停点，下一处为原 row 99149：`java/io/WinNTFileSystem.getBooleanAttributes0(Ljava/io/File;)I`，native 方法 40676，主线程 Java 方法 39516、PC 2。这是 category 2 的 native 缺口，原声明没有 Java Code；没有把它归为 unselected Java，也没有通过代码改写抹掉新 stop。

448 字节 ABI11 报告 SHA256 为 `b014b25c7339fc8ddc7ef12de04e68f95b9ea9eb6eb64b88bc4e0ae76115a2d7`。Phase1 已返回，Phase2 已调用且未返回。两个原 worker 完成真实 exit 并回收，正常 run 返回计数仍为 0；worker failure、held monitor 和 registry lock 都是 0，cleanup 为 7。Reference、Object.wait 和 signal 域都正常关闭，Reference stop token 发出和消费各为 2。

`pre-link.json` 记录只有两个 stop 的差异、原始及实际有序对象集和原库。`pe-verification.json` 检查实际 AMD64 console EXE、原 exports、完整进口函数和 DLL 依赖、安全位与有序 unwind ranges，并确认 AddressOfEntryPoint 恰为原 `boom_process_entry` 导出 RVA 70282417。复制的运行时仍为 SHA256 `572f28fac6ccf9851eca128929698c8d60c55d8b102972041f7f89a8dba05a26`。

最终 344 项基线输入和生成的 ASM、COFF、RSP、PE、runtime、报告及日志均有后验 SHA；原目录未改动。完整增量回放约 35.453 秒，链接约 3.688 秒；回执的 `process_seconds` 还包含执行后的解码和哈希校验，不作为纯执行耗时。更早 `-a` 因严格匹配发现 CRLF 差异而失败、未执行，其失败目录保留；`-b` 已独立确认同一前沿，源快照也保留，最终使用补齐后验封存的 `-c` 回执。

主 agent 在共享源切换之前用全新目录 `.boom/native-canonical-prefix/root-review-v146-a/` 独立复跑，`execution.json` SHA256 为 `4eadbf07afa379404dba2c48c885f8de99d2d923f3632d0a5a3e130bf4fd5cb3`。同样停在 row 99149、方法 40676，生命周期及清理检查通过；完整探针用时约 36.532 秒，没有重跑完整 source verifier。

候选的临时 owned-buffer 计数不在原 448 字节报告中，本回放没有注入观察代码，也没有伪称最终计数为 0。错误消息仍保留候选已注明的范围：不宣称完整 JNI 错误消息调用序列兼容、不证明所有原 malloc 点的 OOM 行为完全相同，也不解析符号链接目标。正式 family 注册与完整新源码验真需在后续统一集成中单独完成。
