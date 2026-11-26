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

正式 28 组的完整流程现已实际通过。新选择位于 `.boom/diagnostic-startup/v147-native-windows-runtime-4ebc28839a37447e9323d556b76759d7/round-000`，包含 5374 类、50860 个选入 Java 方法、131775 个源函数和 12704 格正常静态／失败根。558473573 字节初始化 ASM 完成并行汇编，独立完整 verifier 自然退出 0，用时 515.328 秒。

原生镜像 `.boom/vm-entry-images/82204015cd174cf695f9d937ae2534d4` 已实际执行：原 Phase1 返回，Phase2 越过两组 Windows 接口，停在原 Module.defineModule0／方法 42293、main 64498／PC 26。**这份新选择的 row 为 105103**，与旧快照增量探针的 row 104319 不同。Phase2 未返回，VM level 为 1。两个原后台线程退出并回收，worker failure、停止时 monitor 持有数均为 0，cleanup=7；停止前活对象 8978。未将源选择数量记作已执行方法数量。

```text
source proof 4b7c2eefd078550dcdd7699dd0587278e8aa71d6880ce8c9d6c06f76e0445820
native proof ca94078417abcd1519a2dc44f6db14c14765a1744f039573614d2b8fe2df9b29
execution    7f270e7fa5f3b4068b59eab48ae4ddd0d2e1320921e8195ce01886d969247652
report448    f0f80b4df52adf7b6d73afaf4a2393fbb54086ee2a300a51958e461897057a17
```

主 agent 对本轮 497 项实际输入和生成物分别在验收前后重新计算摘要，发布 `.boom/accepted-native-windows-runtime-v147-28.json`，SHA256 `31b53bd3c0627e1b0a3c9c315a722fec9e3e9aed37f3e08397761a0aa2c5b90d`。新 accepted 视图把 producer 引用指向内容相同的归档源码，并保留原位置和原 pending 的摘要，没有改写原收据。组件与正式对象的代码／数据／重定位等价证明 SHA256 为 `bf975f4c62a3bf39105756d907265fb377edc19485374e28a40c99b0898c2595`。接受范围为当前输入、两个组件的等价执行和实际原生前缀；未穷尽执行全部 native，原报告也没有观察两个候选的最终缓冲计数。

376 项现有 Python 测试通过。完整 System Phase2、Minecraft 入口、世界创建、自动／并发 GC 和游戏性能验收尚未完成。[八项文件输入候选](FILE_INPUT_READONLY.md)已独立通过原 Java 读／关闭链和并发关闭测试，但尚未注册；其新增 4096 格 owner 根必须由正式 GC 消费者接入后才能验收。
