# 正式 IO8 / Parker provider 输入与根投影

本轮登记 `normal-file-input-readonly-v1`、`normal-unsafe-park-v1`，从已接受 29 输入生成
独立 31 输入。没有修改原 batch、运行时 DLL、旧 provider 的 ASM/COFF 或已冻结模型/
内核；VM driver、Parker 生命周期、Phase3 与完整 main 执行由独立后续验收负责。本页
不将 provider 注册、COFF 验证或 pending 状态记作正式 31 启动成功。

## 已落地的生产链

registry 精确登记原 FIS `open0/read0/readBytes/length0/position0/skip0/available0`、原
FileDescriptor `close0`，以及原 Unsafe `park/unpark`。方法 ID、source class hash、
声明 access、原 native frame 与正常字段布局仍由对应源模型动态重建。FileDescriptor
的 close0 不替换既有 file-bootstrap 的 initIDs/getHandle/getAppend 注册。

两个 framed family 使用 `file_input_metadata` / `unsafe_park_metadata`，保留全部真实
原 Java callback、provider family、base module 与 required class 依赖，并核对精确
PUBLIC/import 集合。IO 仍只做已验证的读文件批次；`GetFileType == FILE_TYPE_DISK`
不构成设备黑名单或严格 regular-file 判定，未测试任意 volume/device 路径。

源模型的 `native_root_spans` 投影进入 provider manifest，独立 verifier 重新检查源
声明、实际 writable COFF section、完整范围、对齐、初始全零、无 relocation、无外来
COFF label，并把物理 proof 写入 `source_native_root_spans`。无该源模型契约的 legacy
family 不能冒充声明额外 native oop 根。只读 metadata 与 pool 地址不得当作根。

普通 selector 按实际选中的 pack 及实际链接 object 生成
`selected_provider_native_root_spans`，只纳入选中的根，且 object 恰好出现一次。
closure V 从本次独立 source-verified packs 重新计算完整物理集合，拒绝遗漏、额外项、
错误 count、替换 object 或重复链接。该 helper 不代替当前 source model 的完整验证。

TOOL identity 从 99 项扩为 105 项，新增两个冻结模型/内核及根 helper/ASM 六项。旧 29
缓存只复制原字节，全部经当前 source/frame/metadata/ASM/COFF verifier 后才发布新的
receipt；cache 复制同时处理两份新 metadata。冻结根 helper 和 ASM 字节没有修改。

## 新 31 输入

生产者真实 exit 0，用时 306.718 秒：

- 输入：`.boom/accepted-native-modules-v149-29.json`，SHA-256
  `99f48017acc81733bab549d19b953588c1010cae8d098b500c4fda580077afea`。
- pending state：`.boom/formal-native-transitions/io-park-runtime-v149-a/pending-state.json`，
  SHA-256 `66e428666bc53c9599265915616738829b6e9e025aa8822d9cfc8822677279cc`。
- provider list：`.boom/runtime-providers/io-park-runtime-v149-a/candidate/providers.json`，
  SHA-256 `06695d06bd5df5b9878edd7b40ca91423045ecac4a540cf890b8502df8a48b39`。
- frame：`.boom/native-frame-overlays/io-park-runtime-v149-a/overlay.json`；独立 proof SHA-256
  `63f28e601a54f01f0fef5a9c7fdf95b62b7b60e934a0ee0a06b3a32f30884cfa`。

原 29 包 ASM/COFF 现源重验后原样缓存；两个新 family 实际 ml64 组装并独立验证。IO 根
为 `.data+8` 的 4,096 QWORD，Parker 为 `.data+1048736` 的 16,384 QWORD；这些是本批
物理证据偏移，不是跨批次 schema。原 batch/plan/runtime 不变，未重新生成原 Java
ASM/COFF。状态为 `pending_runtime_acceptance`，`runtime_acceptance_complete=false`。

## 验证及后续边界

四项新登记测试及既有 21 项物理/ASM 测试通过。全实际 unittest 回归为 421 项、11 项
skip、零 failure/error，回执位于
`.boom/formal-io-park-input-tests/regression-7e07f728192b4c79a0185d227eff90f3/result.json`。
首次通配 discover 导入了 CLI fixture 重写器 `strip_fixture_nest.py`，把 `discover` 当作
classfile 路径；首败说明已保留，后续明确只排除此非测试 CLI，没有修改旧 fixture 工具。

`scripts/test-io-park-formal-inputs.py` 在新的目录重新独立验证 31 输入，逐族保留真实
源/帧/依赖/COFF proof，并检查遗漏根、错误 count、错误符号、缺 export、遗漏 Java
callback、错误 native frame/upcall 声明和实际非零 COFF 初值均被拒绝；再对两新包做
原字节 cache 复制及 metadata 搬移复验。第二轮真实独立验证已完成：31 包严格加载、
14 个破坏样本全部拒绝、两份新包 cache 搬移保持 ASM/COFF/metadata digest 相同。
其中 `wrong_frame_claim` 具体改变 manifest 的 native Java upcall 声明，没有修改原
native frame row 或 Java Code。回执
`.boom/formal-io-park-input-tests/production-v149-a/result.json`，SHA-256 为
`b776879b9e1e3b23a12b48a827854f6986587314b80bdb17423828a3bfdfcd64`。

根独立复跑同一真实 31 包来源、14 个破坏样本和两新包 cache 搬移也通过：
`.boom/formal-io-park-input-tests/root-review-v149-a/result.json`，SHA-256
`6f5ddebbeaedea9987197fed8db577a8e3169b5480a1fed863b6ada175ed4c79`。
新的 VM owner fixture 实际组装完整九源／main／native 消费者、Parker 生命周期、
IO 残留保护和 Phase3，实际 COFF 导入／导出合同匹配；该 emitter 检查没有链接或执行，
不作为正式 31 运行收据。它还发现 literal 根 bank 未在旧 selector 导出：现有 native
根时 producer 同时导出 `boom_java_string_literal_roots`／count，V 严查缺项，VM 准备
避免重复 count 导出。两 selector 不在 105 provider TOOL 集，原输入证明未被改写。

新增 TOOL 项改变了通用 helper 的整个文件摘要，因此旧 65 槽 batch 的严格 named
来源记录不能直接用于当前 fresh source selection。已按当前 105 工具重新生成并完整
验证相同 65 数据，原 Java 不变；[显式输入重建](PROVIDER_INPUT_REBASE.md)把原 31
缓存全部重验后发布新 pending，未放宽原 parent guard 或复制旧 full receipt。
后续正常 31 源选择使用
`.boom/runtime-provider-rebases/io-park-tool105-v149-a/pending-state.json`，SHA-256
`95f92cab38ecb4652c7905ea5b9ab5e167d261f8c5eb73d3bc8ed57835e66ad5`。
原 pending、原 accepted29 和两份历史 batch 保留原样。

本批不绕过仍绑定 26 输入的旧 focused helper，不复制其 framework。真实 31 source
selection、closure V 中的 selected roots、VM entry 生命周期及后续 Java 执行须由新的
正式 31 输入完整验收。静止 snapshot 仍要求九源根、main/primordial 根和同一选择集的
native 根全部存在，且没有活动 Java/native frame、外部 oop 借用或未注册的 pending
exception 根；本轮没有实现自动/并发 GC、活动栈扫描或完整 Cleaner/弱引用收集。

```powershell
D:\Dev\Python312\python.exe -m unittest discover -s tests -p io_park_provider_registration.py -v
D:\Dev\Python312\python.exe scripts/test-io-park-formal-inputs.py --state .boom/formal-native-transitions/io-park-runtime-v149-a/pending-state.json --output .boom/formal-io-park-input-tests/fresh
```
