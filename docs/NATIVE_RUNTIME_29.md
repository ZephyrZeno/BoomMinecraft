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

正常 29 组主进程仍在完整源选择／独立校验流程中，尚未发布 accepted29。旧 64 槽十四项增量探针曾在原 Module 构造器以 Context 20 返回，不能单凭该值断言原因或算作模块启动成功。完整 Phase2、游戏入口和世界未完成。[文件输入](FILE_INPUT_READONLY.md)与 [park/unpark](UNSAFE_PARK.md)已经完成独立有界候选验证，尚待正常根区和 VM 生命周期接入，未计入这 29 包。
