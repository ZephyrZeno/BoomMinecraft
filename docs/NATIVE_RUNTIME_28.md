# Windows 路径与文件查询的正常运行时输入

在原 26 组运行时输入上注册两个正常源绑定：

| family | 原 native | 执行与依赖 |
| --- | --- | --- |
| normal-windows-canonical-v1 | canonicalize0、getDriveDirectory | 私有 WinAPI 工作区、原 String 回调、typed IOException |
| normal-windows-file-queries-v1 | 属性、mtime、长度、盘符、容量、文件名长度、访问检查 | 原 File.path 字段注册／继承映射、原 String 和异常构造器 |

九项 native 均从锁定 classfile 取得身份和声明，用普通有帧入口进入汇编服务。没有更改原 Java 字节码、原方法 ASM／COFF 或 runtime572。Python 负责源码核对、构建和测试，执行部分仍为 MASM。

## 可复用的增量准备命令

`scripts/extend-runtime-provider-set.py` 把已有验收范围的输入刷新为当前源码下的候选集合。它先核对 accepted 状态、实际 provider 清单和摘要，再刷新原 native frame 与每个旧包，实际运行独立 verifier；旧 ASM／COFF 不重编。新增 family 分别生成、ml64 汇编、封存并独立校验。它还检查 native／PUBLIC 冲突、所需 family，以及各包的内核摘要与实际汇编运行时 manifest 是否一致。

```powershell
& D:/Dev/Python312/python.exe scripts/extend-runtime-provider-set.py `
  --state .boom/accepted-native-three-families-v146-26.json `
  --family normal-windows-canonical-v1 `
  --family normal-windows-file-queries-v1 `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --output .boom/formal-native-transitions/windows-runtime-fresh
```

输出必须是全新目录。进度在该目录的 `progress.json`；成功准备得到 `pending-state.json`，其中 `runtime_acceptance_complete=false`。该命令不执行 Minecraft，也不会把准备成功改记为游戏启动或自动发布 accepted 状态。玩家启动器仍只有启动流程入口；本命令属于开发工具。

本次 `.boom/formal-native-transitions/windows-runtime-v147-a` 准备用时 284.531 秒：26 个原包和原 frame 的 ASM／COFF 保持原字节，两项新包实际汇编，全部输入通过当前模型校验。另一个 agent 的只读交叉核对确认了 96 项工具摘要、177 处运行时内核绑定和原 DLL，没有用这次交叉检查代替独立 verifier。

正式新包与主 agent 已独立执行的候选，生成 ASM 全文相同；所有非 debug 节的实际代码、数据、section flags、重定位目标和符号，以及 `.pdata`／`.xdata` 均相同。整体 COFF 文件因 `.debug$S` 源文件路径等字段不同，未宣称整文件摘要相等。比较封存在 `candidate-formal-semantic-comparison.json`；最初整文件比较为 false 的记录也保留。

准备成功后，只读审阅发现新命令的异常分支误用只写新文件的 helper 覆盖进度文件，会遮盖原错误。现已改为临时文件后原子替换；实际注入 frame 验证失败，确认原异常保持、已有 journal 变为 failed、没有 pending 状态。正向生成代码的 AST 未变。本次成功构建使用的原 producer 快照和 SHA256 单独保留于 run 目录，原 pending 及收据未改写。

## 执行证据与边界

[canonical 组件](WINDOWS_CANONICAL_PATH.md)与[七项文件查询组件](WINDOWS_FILE_QUERIES_CANDIDATE.md)均由主 agent 在全新目录独立重建和执行。组件保留完整顺序错误消息、未运行 Phase1 的 API 夹具，以及各自 OOM／设备范围的限制。

[九项 native 的 owned 增量探针](NATIVE_PROVIDER_PREFIX.md)已实际越过原 canonicalize0 和 getBooleanAttributes0 停点，下一原 native 为 Module.defineModule0（本批 42293、row 104319、main 64498／PC 26）。该探针显式 `full_selection_reverified=false`，不能替代正式 28 组的完整源选择和原生镜像验证。

当前正式 28 组主流程仍在独立完整校验。完整 System Phase2、Minecraft 入口、世界创建、自动／并发 GC 和游戏性能验收尚未完成。[八项文件输入候选](FILE_INPUT_READONLY.md)已独立通过原 Java 读／关闭链和并发关闭测试，但尚未注册；其新增 4096 格 owner 根必须由正式 GC 消费者接入后才能验收。
