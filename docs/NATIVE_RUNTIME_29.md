# 模块定义的 29 组输入集成

第 29 组 `normal-module-definitions-v1` 注册原 Module.defineModule0、addReads0、addExports0、addExportsToAll0、addExportsToAllUnnamed0。声明、类／字段／方法身份来自锁定 classfile；执行为正常 Module 对象上的汇编定义、读边和导出图。组件范围和未覆盖项见 [Module 候选](MODULE_DEFINITIONS_CANDIDATE.md)。

锁定默认模块图还要求没有 Java 类型的 jdk.jdwp.agent。新的 [JCLS 派生验证](JCLS_NAMED_MODULE_APPEND.md)追加 named slot64，保留原 0..63、全部 1011 个 Java 单元、原 frame 和 runtime572。原 Boot native 对模块容量使用精确检查，因此该包按 65 槽正常重新生成、汇编和验证；没有放宽为最小容量检查。

当前生产派生批次 `.boom/named-module-batches/v148-jdwp-production-b` 已完成真实完整验证，自然退出 0，用时 308.766 秒：

```text
summary     271870db974403d34343f7218a781e118caeef3bf79c3b18188df992a3f17056
full proof  9252005a2e8b02422d5beb4dc8aee15c2cf0c9e9eb0dabc8538f29b0f12f1cff
lineage     88cb18736469cf0cdefe762bb25e6147a2db06ca7306d73b1bc8e099981aaee7
```

Class verifier 从原类型和实际 module-info 重建期望模块；闭包解析器仅接受认证父批次保留的产物及新 JCLS 单元。实际 COFF 符号交换负测曾暴露原 raw relocation index 比较的漏检，现已加入逐索引符号名称、类型、storage、aux 和合法偏移归一化比较。旧首轮完整验证及原工具快照保持历史，不充当补强后的收据。相关两个测试模块共 17 项，其中新增 11 项；全套 Python 测试 387 项通过。

增量输入准备命令为：

```powershell
& D:/Dev/Python312/python.exe scripts/extend-runtime-provider-set.py `
  --state .boom/accepted-native-windows-runtime-v147-28.json `
  --batch .boom/named-module-batches/v148-jdwp-production-b `
  --regenerate-family normal-boot-unnamed-module-v1 `
  --family normal-module-definitions-v1 `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --output .boom/formal-native-transitions/modules-fresh
```

`--batch` 必须通过当前严格派生解析器，并精确继承 accepted 状态的父 summary；仅复制真实 verification.json 到修改过的 summary 旁边会被拒绝。`--regenerate-family` 指定已有包重建，保持原清单位置；新增 family 追加到末尾，重复 native／PUBLIC 拒绝。

本次 `.boom/formal-native-transitions/module-runtime-v148-a/pending-state.json` 已成功准备 29 包：27 个旧包的 ASM／COFF 原样复用并在当前模型下重验，Boot 和 Module 两包实际生成、汇编、验证；用时 303.125 秒。该 pending 状态 SHA256 为 `49e29c180fbdd4d72ce358ed58a38c8cfd5a0e66d397c2f9981dc6d6d02972c8`。准备后的只读复核补强了 override 来源 guard，原成功 producer 已存入 `transition-producer-before-lineage-guard.py`，原 pending 和收据未改。补强 guard 已真实接受当前 65 批次、拒绝替换 Java COFF 记录后复制真实收据的夹具。

正常 29 组主进程已完成完整源选择／独立校验和实际执行：原 System.initPhase1、initPhase2 均正常返回，Phase2 结果为 0，VM 级别 1→2；原生进程退出码 0、主 Context 0、无 fault。两个后台原 Thread.exit 与 OS 记录回收各为 2，worker failure／held monitor／registry lock 均为 0，Reference／Object.wait 停止关闭和清理标志 7 通过。停止前活对象 13330，不代表自动回收已实现。

源选择为 `.boom/diagnostic-startup/v148-native-modules-ae1c57ec1bb24f1d812d5dc91d4987d7/round-000`，5818 类、56665 个原 Java 方法、149383 个汇编函数，独立完整校验自然退出 0，用时 626.968 秒。这些数字为来源和链接范围，不能当作全部执行覆盖。

```text
source proof  2e34f7b6d93242b43ba5f70f644d1920362412ce4df5ef783e8d2dae0954b847
native proof  651605a3fd27ca139b706dd4befd0741356e1c56c084b002d2b0b7f9f18481a3
execution     52c22140b4f765071fb296ece9e3985058d6c4a8cd271a442f55c363d419d96f
ABI11 report  323ef50feaa5e0be74300949effcf2f55f1ba16ca05c58d02f2f2692f98e04a7
```

原生目录为 `.boom/vm-entry-images/311ed8c0d18b45b5b26dfafbbabb0bdc`。独立 65 槽 Module 候选还在这份真实 29 组选择上完成组件复验：16 项锁定 JDK 错误对照、8 OS 线程的定义竞争与 1024 次图变更、两次明确静止回收。原 Java／diagnostic stops 不变；候选与正式 Module 对象所有非 debug section、data、符号、relocation 目标和 pdata／xdata 相同，仅平台换行、文件名 debug 等非执行字段不同。组件回执为 `.boom/module-definitions/root-review-execution-v149-65a/execution.json`，SHA256 `99fb8a8afb57ef9ca91cae68ce31c1308e5b2b1e867991a186db27558f4f36b2`。

已发布 `.boom/accepted-native-modules-v149-29.json`，SHA256 `99f48017acc81733bab549d19b953588c1010cae8d098b500c4fda580077afea`；444 个实际产物在发布前各核对两遍。仅新 accepted 视图把成功 producer 引用指向原字节相同的归档，原 pending、旧记录和位置记录均保留。范围是当前 29 组输入与原版 System 前两个阶段，没有宣称每个 native 均穷尽执行。

旧 64 槽十四项增量探针在原 Module 构造器的 Context 20 失败仍作为历史记录保留，不能只凭构造器 PC 推断当时是哪次模块定义或具体原因。第三阶段、完整 VM、Minecraft 入口和世界未完成。[文件输入](FILE_INPUT_READONLY.md)与 [park/unpark](UNSAFE_PARK.md)已经完成独立有界候选验证，[原生根完整 ASM 快照](PROVIDER_NATIVE_ROOTS.md)也已通过独立复验；正式根区传递和 VM 生命周期接线正在推进，未计入这 29 包。全套当前 Python 测试含新增 21 项根检查，共 408 项通过。
