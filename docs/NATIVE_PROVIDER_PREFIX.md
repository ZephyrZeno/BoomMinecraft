# 多候选 owned 原生前沿探针

`scripts/probe-native-provider-prefix.py` 复用封存 accepted26 主程序的全部原对象，组合多个已独立验证且已有组件执行证明的 native candidate。它不注册 provider、不重新 prepare、不调用完整 source-selection verifier。输出是 development prefix，不能代替正式 28 项源码与运行验收。

`--candidate` 可重复，格式为项目 `scripts` 中的 verifier 文件名加冒号和 candidate 路径；Windows 盘符中的后续冒号保留。每个 verifier 都必须实际重新计算并匹配自己的 source/frame/ASM/COFF 收据。每个 candidate 还必须有 `verified=true` 的 `--component-proof`，经其已封存 images 配置精确绑定到同一个 candidate。

目标声明完全从 `metadata.source.methods` 派生，不硬编码方法 ID。检查包括原 native 声明、原 class/source/descriptor、所需类的正常状态与失败根、实际选中的原 Java 回调及 normal family。候选 PUBLIC 和 native ID 不得互相冲突，也不得覆盖保留 COFF 的实际公开定义或原 runtime exports；实际 imports 精确核对，再按依赖合并。未提供或重复的组件绑定会拒绝。

变更只发生在原 diagnostic-stops 对象的位置：各目标的 PUBLIC 声明与完整 fail-only PROC 被精确移除，原 rowdata、CRLF 和其他所有源字节保留；新 remaining-stops.obj 与 candidate.obj 按命令顺序加入。55 个原 initialization 分片、原 VM-entry.obj、其他原对象、库、选项和 PE exports 都不变。完整 canonical RSP 不接受 `/FORCE` 或额外输入。

新 PE 检查 AMD64、console entry、原导出、实际进口函数与 DLL 依赖、安全位、排序 unwind 范围，并确认 AddressOfEntryPoint 恰是原 `boom_process_entry` 导出。所有基线输入、候选输入、生成的 ASM/COFF/RSP/PE/runtime/报告/日志都在执行后再次计算 SHA。原生报告保持 448 字节 ABI11，以原未修改的 row table 解码 main fault 和首个 process fault。

## canonical2 + queries7 实测

本轮使用两个独立候选及组件证明：

```powershell
D:/Dev/Python312/python.exe -B scripts/probe-native-provider-prefix.py `
  --accepted26 .boom/accepted-native-three-families-v146-26.json `
  --baseline-native .boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1 `
  --candidate windows-canonical-candidate.py:.boom/windows-path-canonicalization/source-bound-v146-b/candidate.json `
  --candidate windows-file-queries-candidate.py:.boom/windows-file-queries/source-v146-d/candidate.json `
  --component-proof .boom/windows-path-canonicalization/binding-execution-v146-e/execution-c11e3853c9074a48adf6fc12e84e4058.json `
  --component-proof .boom/windows-file-queries/execution-v146-j/execution.json `
  --output .boom/native-provider-prefix/new-owned-development-run
```

所有输出目录都必须全新。实际本轮目录是 `.boom/native-provider-prefix/v147-canonical2-queries7-a/`。`execution.json` SHA256 为 `bcc7745a671df133d7ccd509f07686011c63135b61d5c5886e709d14756ab031`，探针自然 exit 0，owned EXE 按预期诊断 exit 86。

动态合并了九个原 native：40671、40674、40676、40678、40680、40682、40700、40703、40704。它们分别来自 canonical2 和只读 queries7，不是新的 Java 方法体。查询候选 SHA256 为 `5e0e936f4266a1eabe1478d5245cdd31c242e48dccd610c92a10a29939539d7e`，其组件执行 SHA256 为 `0e97d244db17fd4fa43b732dac6d72f98c6b145153d02c08fb074681f63fcac0`。

实际已经越过 getBooleanAttributes0 等查询前沿，下一处为原 row 104319、category 2：`java/lang/Module.defineModule0(Ljava/lang/Module;ZLjava/lang/String;Ljava/lang/String;[Ljava/lang/Object;)V`，native 方法 42293、class 4573。主线程 Java 方法 64498、PC 26。该声明没有 Java Code，属于真正 native 缺口；没有把它误记为未准入 Java，也没有改写代码抹 stop。

Phase1 返回，Phase2 调用而未返回。cleanup=7，worker failure=0，held monitor=0；两个原 worker 完成 exit 并回收，正常 run 返回计数仍为 0。Reference、Object.wait 和 signal 域都正常关闭。360 项输入与生成物在退出后 hash 复核通过，增量回放约 47.469 秒，链接约 4.188 秒；`process_seconds` 包含执行后解码和校验。

主 agent 另外用自己的两份独立重建候选与组件执行证明，在 `.boom/native-provider-prefix/root-review-v147-a/` 复跑。`execution.json` SHA256 为 `7caab0b98520100eec3f4ac7ee262057dec841fe8eab16cf9cb940d2474190dd`，约 41.391 秒，仍得到 Module.defineModule0／row 104319 和相同正常清理结果。输入不是直接复用上面两份候选的路径，组件与所用候选的精确绑定同样通过。

回执明确 `prototype_native_added=9`、`full_selection_reverified=false`、`formal27_accepted=false`、`shared_provider_registered=false`、`full_VM_bootstrap=false`。这里的旧源码证明只作已封存 26 快照的来源证据，当前 namespace 的正式 28 验证仍需完整生产流程。原 448 ABI 不携带两个候选的最终 owned-buffer 计数，本探针没有注入计数观察代码，不声称该计数已读取为 0。两个候选的错误消息、缓存历史和 malloc/OOM 限制逐项保存在回执 policy 中。
