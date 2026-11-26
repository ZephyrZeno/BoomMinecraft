# 诊断镜像并行汇编候选 v145

这是独立构建工具实验。`scripts/parallel-diagnostic-assembly-candidate.py` 读取已经封存并完成独立验证的选择目录，将完整函数分到多个汇编单元，再与该选择原有的单体 COFF 做真实等价检查。现有 prepare、diagnostic-objects、验证器和启动流程均未接入这个候选。

## 源码与布局

函数边界来自 `batch-source.py` 的 `procedure_spans`，逐一匹配 `closure.selected_function_sha256`。每个完整 PROC/ENDP 的原始字节保留，方法入口与 `_body` 配对；跨函数跳转所需的完整组也保留。各单元内沿用原函数顺序。

所有类描述、派发表、异常处理表、静态字段和连续 GC 根留在同一个数据单元，数据源码 payload 原样保留。EXTERN 从去除旧全局声明后的实际引用生成；数据标签在需要跨单元引用时提供 COFF 公共符号，原有数据符号地址不变。

代码以约 8 MiB 源码分组，最多八个 ml64 工作者。规划器读取原 COFF 中实际跳转位置与宽度：若重排会使原 near 跳转缩成 short，就合并完整既有单元并恢复原有中间函数。它不改函数中的跳转语句或插入填充指令。合并后个别单元可以超过名义预算，实际合并记录保存在清单中。

## 等价检查

汇编之后另行重读原始源码和全部候选 ASM，逐函数校验原字节及数据 payload。实际 COFF 检查覆盖：

- 每个函数的完整机器码；保留 opcode 和指令宽度，分支与 RIP 相对字段按实际目标归一，其余字节直接比较。
- COFF 重定位及单体中已解析、没有重定位记录的同节直接 call/jmp，均按真实函数或数据地址比较。
- 每个函数的 x64 `.pdata` 边界和 `.xdata` 展开字节。当前候选明确拒绝未支持的 handler、chained unwind、版本或节格式。
- 完整 `.data`、`.rdata`、`.bss` 的大小、属性、数据字节和重定位目标，以及所有原有数据符号的节及偏移。
- 连续静态根起点、格数和字节跨度。

Capstone 只用于读取本项目生成 COFF 的 AMD64 指令字段，版本、Python 模块和本机库摘要纳入收据。实际样本中的 `66 0F 2E 05 disp32`（UCOMISD）被 Capstone 5.0.7 错报为两字节位移；候选根据实际 64 位地址模式、ModR/M、无 SIB、位移位置及指令边界严格确认四字节编码，相关真实指令已加入测试。

原输入、候选 ASM/COFF、ml64、索引器、候选脚本及解码器在验证期间都保持摘要绑定。输入采用封存的原选择证明及汇编来源收据；这一步证明该快照的分单元等价，不重新调用后来已经变更的 provider 验证工具。

## 实际结果（2026-11-26）

原样本位于 `.boom/diagnostic-startup/v145-native-boot-unnamed-40a5c3ea326e43c993fe3d8bef4841df/round-000`：ASM 433,596,877 字节，单体 COFF 106,617,525 字节。主任务中单体 ml64 实际耗时约 19 分钟。

成功候选位于 `.boom/parallel-diagnostic-assembly/v145-root-433mb-attempt004`：

| 项目 | 实测 |
| --- | ---: |
| 完整源函数 | 95,129 |
| 原机器码 | 57,774,581 字节 |
| 展开记录 | 51,684 |
| 代码 fixup / 真实目标 | 1,861,531 |
| 数据重定位 | 933,046 |
| 连续 GC 根 | 8,919 格 / 71,352 字节 |
| 汇编单元 | 1 个数据 + 44 个代码 |
| 保持跳转宽度的整单元合并 | 3 次 |
| 最大代码单元源码 | 13,037,138 字节 |
| 分组与源校验准备 | 38.938 秒 |
| 八工作者 ml64 墙钟 | 7.422 秒 |
| 逐函数机器码等价循环及末尾复核 | 101.015 秒 |
| 包含全部准备、汇编、源码复核和 COFF 读取的总耗时 | 182.000 秒 |

`equivalence.json` 的 SHA-256 为 `d37d4adfc94d567ca823c72a4a560c49c430ebd21c75db9af3ebe21fc235d885`。全部 95,129 函数和展开、数据及根布局通过；实际失败尝试也保留，包括捕获 near 跳转被缩短的第三轮。

`tests/parallel_diagnostic_assembly.py` 的十项真实 ml64 测试通过，覆盖重定位感知正向等价、UCOMISD 位移编码、opcode/目标/根布局/展开篡改拒绝、short/near 宽度变化拒绝、保留完整原函数的合并，以及机器码可能相同但源函数字节变化时的拒绝。

## 独立原生链接与执行

`scripts/parallel-diagnostic-native-prefix-probe.py` 在封存的 22 包 native owner 链接响应中，仅将原 initialization-closure.obj 替换为 45 个已证等价的对象，并更换 OUT；其余输入、顺序和选项保持原样。它将同一 SHA-256 `572f28fac6ccf9851eca128929698c8d60c55d8b102972041f7f89a8dba05a26` 的汇编运行时复制到全新目录，启动真实拥有进程。

最终回归位于 `.boom/parallel-diagnostic-native-prefix/v145-433mb-attempt002`。链接耗时 9.782 秒，拥有进程耗时 0.422 秒，执行后输入复核 2.047 秒，总耗时 17.062 秒。新 PE 的 AMD64、Console、NX、ASLR、HighEntropy、全部导入/导出及排序后的展开范围与封存 PE 相符。

448 字节 ABI11 报告与原进程逐字节完全相同，SHA-256 为 `53620a02582e53a87dd243f7332f8a46d25d0053187913cf04a32c46cfbf26bd`：原始 System.initPhase1 返回，initPhase2 已调用，在行 104316 的 `ClassLoader.registerNatives`（方法 41548）停止；两名后台工作者的原始 Java exit 完成，failure 为零、持锁为零、cleanup 为 7，Object.wait、Reference 和信号等待域均正常关闭。进程仍以明确诊断停止码 86 退出。

`tests/parallel_diagnostic_native_prefix.py` 的十二项检查通过，包括精确链接响应替换、真实封存报告接受，以及 ABI、长度、Phase1、源行、exit、持锁和等待域错误拒绝。当前候选保留 `linked`/`executed` 的独立执行收据，原编译等价收据仍只声明其自身的 COFF 等价范围。

## 复验

输出目录必须尚不存在，且位于项目 `.boom` 内。使用对应封存目录和同一 ml64：

```powershell
D:\Dev\Python312\python.exe scripts/parallel-diagnostic-assembly-candidate.py `
  --directory .boom/diagnostic-startup/v145-native-boot-unnamed-40a5c3ea326e43c993fe3d8bef4841df/round-000 `
  --output .boom/parallel-diagnostic-assembly/manual-check-001 `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --workers 8 --code-mib 8

D:\Dev\Python312\python.exe tests/parallel_diagnostic_assembly.py

D:\Dev\Python312\python.exe scripts/parallel-diagnostic-native-prefix-probe.py `
  --baseline-native .boom/vm-entry-images/a7c5084275e0419db074936e926fd155 `
  --candidate .boom/parallel-diagnostic-assembly/v145-root-433mb-attempt004 `
  --output .boom/parallel-diagnostic-native-prefix/manual-check-001
```

清单和收据分别为 `prepared.json`、`assembled.json`、`equivalence.json`；失败写入 `failure.json`。`--prepare-only` 只产生分组，不宣称完成 COFF 等价。

当前规划和严格二进制等价证明仍以已生成的单体 COFF 为基准。新一轮未有基准的函数以及共享构建接线属于后续工作。独立执行只回归同源的 22 包初始化前缀，完整 System、游戏和世界尚未由此完成；上述构建耗时也不是 Minecraft 运行性能数据。
