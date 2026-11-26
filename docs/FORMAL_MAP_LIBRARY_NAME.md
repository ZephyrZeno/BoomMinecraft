# 正式 26 提供器的冷 MapLibraryName 验证

`scripts/test-formal-map-library-name.py` 从待运行验收的 26 项提供器清单创建独立的小源码镜像。它不继承旧 NIO 或 Map candidate 测试镜像，不替换 diagnostic stop，不手写类初始化状态、静态字段或运行时元数据。

共同准备流程位于 `scripts/formal-provider-selection.py`，不属于游戏运行时，也不加入提供器 `TOOL_FILES`。输入为不可变的 pending26 state；活动进度 journal 不能作为输入。每次准备都保留当前 `load_packs` 对原来源、ASM、实际 COFF、全部独立收据与依赖的校验，再构建正常源码选择、并行汇编、严格 RSP 和完整独立 source verifier 收据。

Python 调用接口为：

```python
images = selection.prepare(
    pending_state, fresh_output,
    method_roots=[("bootstrap", owner, name, descriptor)],
    class_roots=[], admitted_methods=[], admitted_classes=[],
    source_profile=None, exports=[], optional_exports=[],
    harness_sources=[__file__],
)
proof = selection.verify(images)
```

额外 `exports` 必须是实际已选源码、COFF 或汇编运行时的公开符号。`optional_exports` 只取已经存在的交集，不会因此加入任何模块或 Java 方法；完整 GC bank 以原公开 base/count 成对请求。类失败根通过原 class descriptor 的 cause-root 指针只读观察，不能将私有数据升格后导出。`images.json` 封存公共 helper、执行器和构建验证输入，记录所选 family、原提供器 metadata、全部实际链接对象与库。`verify` 从头运行独立源码验证并核对封存输入，不恢复先前进程的校验缓存。

Map 测试将原 `System.mapLibraryName`、`String(char[])`、`String.toCharArray`、`Object()` 作为根。提供器自身要求的原 Java 回调保持原来源；实际碰到 lazy dispatch 或类初始化缺口时，只允许下一轮增加该完整原方法或类。每一轮的新 source selection、COFF、RSP、PE、独立 proof 和执行首败均保留。

重点断言包括：

- `selected_property_natives` 为空，Map 所需原 properties COFF 仍恰好出现一次，原 109 个 GC 根槽完整，原 `SystemProps$Raw` class state 与失败根在正常静态根区。
- 冷 `System`、`String`、`Raw` 状态来自未执行的原描述符。输入通过原 `String(char[])` 构造；8 个真实 OS 线程竞争普通 Map wrapper 的首次 `System` 初始化，不调用 `_native` 旁路。
- 14 个合法名字和 4 个 241 UTF-16 单元名字覆盖边界、NUL、补充字符和未配对代理。长名走原异常构造器、原 `Throwable.fillInStackTrace` Java 路径和正式 Throwable native；读取原字段中的消息和回溯，确认回溯含 Map 方法。
- 额外检查 null、外来指针、错误类与已有异常。8 个 OS 线程重复执行 1120 次正常映射。
- 工作者全部结束后，以实际链接的完整原 GC bank 快照和显式测试句柄调用原汇编 collector。不会修改根区；若 properties 根自然全空，不声称已验证其活对象保留。
- 锁定 JDK 只作为独立语义对照，检查 18 个名字及 null；它不承载被测游戏代码，也不是执行回退。

输入提供器的逐包验真不等同于 26 项的联合运行验收；本测试也不声称完整 VM 或 Minecraft 启动完成。

## 已完成的正式运行

输入为 `.boom/pending-native-three-families-v145-three-families-26-9e4944c57a424d038bb7679b56009811.json`，状态仍是 `pending_runtime_acceptance`。公共 helper SHA256 为 `906dbfe4699c3c2f05f7d8f40dcbcf1d09e3a84aa6611e44e6b7ba49d3485db2`。

正常源码选择和独立证明位于：

```text
.boom/formal-map-library-name/v145-formal26-cold-9e4944c57a424d038bb7679b56009811-b/round-000/
```

其中 `selection-verification.json` SHA256 为 `fea663b474c74f657bf98d6ffa34ab59c48571b60ff6032e7a8d71d6b87a0810`。它独立验证了 667 个类、2607 个原 Java 方法、6149 个完整函数，以及 `source_property_natives=0` 时依然存在的原 properties COFF 和 109 个连续根槽。properties COFF SHA256 为 `03626e0cb0558594f54d6a32b1d9148b3503d851a5202a719a1390be164f548c`，原根区位于 `.bss` 偏移 0，共 872 字节。Raw 类 12516 来自正常选择，其失败根仍位于原静态根区。

首轮执行在最后准备 JDK 对照时遇到测试器错误：catalog 摘要包含 `size/sha1/sha256`，而 `S.digest` 返回 `size/sha256`，整字典相等检查因此失败。该轮 `execution-result.json` 保持 `verified=false`，SHA256 为 `dc76b3183cef6aeeae6caa6947947ec0c98653df9bb4cd7f631dddc454c3fbed`。它没有被覆盖，也没有当成整体通过。更早因测试器子进程超时设置而停止的未完成准备目录及 `attempt-status.json` 也保留。

独立重验入口是 `scripts/recheck-formal-map-library-name.py`。它严格比对并封存原函数 AST：`execute` 仅改变 oracle 的输出目录；`oracle` 仅将错误摘要比较替换为实际计算全部 `size/sha1/sha256` 后逐项比较。其余运行、GC、清理、19 个 JDK 用例的源码、命令及输出断言完全相同，首条完整 `F.verify(images_file)` 也保留。它没有重新 prepare、修改原测试器、修改 Java/COFF 或改写旧收据。

重验命令为：

```powershell
D:/Dev/Python312/python.exe -B scripts/recheck-formal-map-library-name.py `
  --images .boom/formal-map-library-name/v145-formal26-cold-9e4944c57a424d038bb7679b56009811-b/round-000/images.json `
  --output .boom/formal-map-library-name/new-oracle-recheck-directory
```

实际重验结果位于 `.boom/formal-map-library-name/v145-formal26-cold-oracle-recheck-9e4944c57a424d038bb7679b56009811/result.json`，SHA256 为 `da65a9a7cd4bbda27b611a59fc0f6a09135ed62b0c8d7b389c8f0b2ef44f38ba`，进程自然退出 0。相邻 `harness-AST-proof.json`、`locked-catalog-digests.json` 和独立 `oracle/` 保存完整重验依据。

实际结果为初始 System/String/Raw 状态全 0，Raw 失败根为静态根区偏移 15224；8 个冷 OS 线程经普通 wrapper 完成 System 初始化。14 个正常名字及 4 个长名通过；4 个原异常回溯均为深度 1，含 Map 方法 43956、BCI 0。null、外来指针、错误类及已有异常检查通过。另 8 个 OS 线程完成 1120 次重复映射。7 个实际链接的完整根区参与静止期快照，原汇编 GC 回收 8459 个对象，根区未改变，堆和 trace pool 均正常关闭。

properties 的 109 个根槽在本轮自然全空，因此本轮不声称其活对象保留已测。原 Raw 类和失败根始终未经 host 修改；锁定 JDK 的 19 个对照全部一致。这些结果仍只覆盖正式 26 输入下的 focused Map 源码镜像，不提升为完整 VM、世界或 Minecraft 启动验收。
