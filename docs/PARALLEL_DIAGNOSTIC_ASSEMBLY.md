# 初始化闭包的可选并行汇编

`scripts/parallel-diagnostic-assembly.py` 提供无需单体 COFF 参照的构建辅助接口，供诊断构建的可选并行路径使用。当前只拆 `initialization-closure.asm`；带宏和 private 过程的 `diagnostic-stops.asm` 继续完整单体汇编。默认构建行为由消费层保持。

## 接口与收据

```python
manifest = H.prepare(source, output, expected_normalized_function_hashes,
                     budget_bytes=8 * 1024 * 1024)
receipt = H.assemble(manifest, assembler, workers=8)
proof = H.verify(receipt, source, expected_normalized_function_hashes)
```

`output` 必须是项目 `.boom` 内尚不存在的新目录。prepare 写入 `prepared.json`，assemble 写入 `receipt.json`；verify 纯读检查，返回不含当前时间和耗时的确定性 proof。artifact 统一为 `{path, digest: {size, sha256}}`。

manifest 和 receipt 中的 `units` 保序，单元包含 `unit`、`role`、`functions`、`assembly`、`exports`、`imports`、`extern_types`；assemble 后增加 `object`。单元 0 保留全部数据，后续单元只含完整函数。`promoted_data` 是去重排序后的数据符号列表，限于数据定义减原始 PUBLIC，不能包含任何 PROC。

helper 保留原始 PUBLIC 函数、入口与 `_body` 配对以及跨过程跳转组。每个单元内保持原函数顺序，以约 8 MiB 源码分组，最多八个 ml64 工作者；EXTERN 按实际引用生成，并保留原外部声明或数据定义的元素类型。

## 验证范围

verify 从原始源码和调用方提供的 normalized function SHA 重新建立模型，检查完整 raw ranges、各函数原字节、整单元 canonical ASM、数据 payload 和实际 COFF defs/imports。它核对全部 FRAME 过程的实际展开边界及记录，并检查原始 PUBLIC 完整保留、private code 没有升格、数据没有散入代码单元。

静态 GC 根区域由原始 QWORD 声明重建，核对实际 BSS 起点、格数、跨度、根计数常量及每个具名根格的 COFF 偏移，防止同样全零的 BSS 字节掩盖根符号移动。

收据与 proof 明确记录：

```text
monolithic_reference_used = false
monolithic_binary_equivalence = false
instruction_width_equivalence = false  # proof
```

这条 fresh 路径证明源码保留及实际 COFF 结构，不会把尚未生成的单体对象记为已比较。既有 95,129 函数的严格机器码等价、指令宽度保护和 22 包原生前缀回归单独保存在[候选验证记录](PARALLEL_DIAGNOSTIC_ASSEMBLY_CANDIDATE.md)。

## 全量验证（2026-11-27）

固定源样本 `.boom/diagnostic-startup/v145-native-boot-unnamed-40a5c3ea326e43c993fe3d8bef4841df/round-000/initialization-closure.asm` 的 fresh 路径验证结果位于 `.boom/parallel-diagnostic-assembly/v145-root-433mb-fresh001`：

- 95,129 个完整源函数、51,684 个 FRAME 展开记录。
- 48 个单元，包含一个完整数据单元和 47 个代码单元。
- 31,572 个原 private 数据符号的明确升格，零 private 过程升格。
- 8,919 个具名静态根逐格核对，BSS 起点为零，连续跨度 71,352 字节。
- 准备 36.703 秒，八工作者 ml64 墙钟 9.046 秒；包含两遍完整 verify 总耗时 126.547 秒。
- 同一输入的两次 proof 完全相等，`verification.json` SHA-256 为 `87f1fb24a4c5162c886dbac32f23676aadacff7469d589f17ffaa46ddc77f0d9`。

`tests/parallel_diagnostic_assembly_fresh.py` 使用真实 ml64 且不准备单体对象，覆盖正常源码/COFF/展开/根布局与确定性，以及 private code、错误 normalized SHA、错误根计数、代码升格、COFF 根符号别名和错误展开起点拒绝。

## 开发启动链与正式 23 包原生执行

`Build-DiagnosticClosure.ps1`、`Invoke-DiagnosticStartup.ps1` 和 `Invoke-NormalVmThreadBootstrap.ps1` 显式提供 `-ParallelAssembly`、`-AssemblyWorkers`（1..8）及 `-AssemblyCodeMiB`。未开启时继续使用原单体路径。`Build-VmEntry.ps1 -ParallelAssembly` 要求已接受的 schema 2 源证明，按封存顺序复用全部实际 COFF；来源变动时明确拒绝，不静默重编译单体。

schema 2 的 `assembly-provenance.json` 保存两个逻辑单元及全部实际分块、原始数据升格清单和 helper receipt。独立 source verifier 仍核对原始 Java／类状态／provider、实际分块 COFF、链接顺序及导出；VM 证明保存每个实际链接输入。原来的 schema 1 收据继续支持。自动源准入也已支持准确的 ABI11／448 字节原生报告，保留原生字节、源表、证明散列及主线程／首次停止两项观察核对。

`canonical-link-response.py` 核对完整的一行一参数链接响应文件，包括选项、输出、有序 COFF、受限运行时／SDK 库和导出。库路径仅在确认同一实际文件时接受大小写差异；diagnostic 导出尾部按完整集合且每项一次核对，以兼容 PowerShell 文化排序，native 导出继续要求原 ordinal 顺序。升格私有数据不得进入 PE 导出。

实际审计复现了旧筛选方式漏过前导空白对象的情况：额外 COFF 确实进入 PE，旧 verifier 仍返回成功。修复后 28 次小型真实 LINK 有 2 个正确输入获接受，26 个变体被拒绝，其中 22 个原本能成功链接；嵌套响应和 WHOLEARCHIVE 的四次尝试由 LINK 自身拒绝，分别记录。完整原生镜像的独立负测也实际链接成功，再被新 verifier 明确拒绝。审计索引 `.boom/source-integration-checks/60901311f1674360a4c9cad9900f8bfe/rsp-audit-summary.json`，SHA256 为 `c7ae874e45751d3f6ce800499e06313469a231f20dcb78631809f48bcfcf38f3`。

本轮正式 23 包源选择在 `.boom/diagnostic-startup/v145-native-class-loader-parallel-ec0736fc2365423ebb73fa7afb89c5ed/round-000`：

- 4,056 个类、37,546 个原始 Java 方法、95,130 个完整源函数及 51,685 个 FRAME 过程。
- 433,597,713 字节初始化 ASM，48 个分块加一个完整 diagnostic-stops COFF；31,573 个原 private 数据符号明确升格，原 private 过程未升格。
- 8,920 个静态根单元；新增 AssertionStatusDirectives 失败根进入正常根跨度。
- 八工作者汇编 4.843 秒；独立完整源／ASM／COFF 校验另耗时 1,033.765 秒，未把这个步骤算入汇编时间。
- 源证明 SHA256：`bbeaeef00ce19d601e6585167383e0424c7cc4e5df87ee83c67acf027bd44f0c`。

实际原生入口在 `.boom/vm-entry-images/ea06ed49ac6a4fc0a9943f74c5d8ef55`，证明 SHA256 为 `c2eb44e1acb7e3a8a719b2498767b8e483de9c7a3e1aec28ee2fe98ded3f5b7c`，执行 SHA256 为 `984f23e9fcf8eaee04c984a33d0fd94c6fbaee24afdd94aa167b3f8d57911d44`。原始 Phase1 返回、Phase2 进入并越过 ClassLoader，主线程在 Reference.refersTo0（50141）明确停止。两个后台原 Thread.exit 和记录回收完成，失败状态与停止时监视器持有数为零；两个停止令牌全部消费，清理标志为 7。没有 JVM／托管宿主或 VM 绑定夹具。

修复链接校验后，主 agent 复用已接受的原始源与 49 个闭包 COFF，另建 `.boom/vm-entry-images/v146-class-loader-final-fbd9e4ba00cb490da44c8421651e4bd7` 并真实执行。新 helper 已进入入口输入封存；原生证明 SHA256 为 `92134a56276c39b831dbb6780bc8a17be2b02ae7828ca28191a353f96b1e4b3b`，执行 SHA256 为 `d3caf8be094be48806874b10b2b386b4b19258459e2df51bd8c73d4d9ca1ff5a`。448 字节 ABI11 报告与首次执行逐字节相同，SHA256 为 `7bf48f2461d2c0d78a1da6acb869d41eb74d4658a6d375234c2a3bbf9c36a4ad`。全部 365 项 Python 测试通过，覆盖实际 ml64／link、源保留、COFF、展开、逐格根布局及篡改拒绝；日志为 `.boom/python-tests-v146-parallel-final2.log`。

该路径验证原生初始化前缀与构建并行性，完整 System 第二阶段、Minecraft 启动、世界创建及游戏性能优化仍未完成。
