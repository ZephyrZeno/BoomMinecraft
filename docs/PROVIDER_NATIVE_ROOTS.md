# 原生 provider 根的物理验证与静止快照

本批新增构建验证 helper、纯 MASM 快照内核和独立测试。原 Java 源镜像中，九份普通
source root bank、primordial/main 根、FileInputStream 的 4,096 个 FD owner cell、
Parker 的 16,384 个 gate cell 已由 ASM 快照产生实际 collector 输入。当前没有自动 GC、
并发 GC、活动 Java frame/线程栈根扫描或完整游戏启动；正式 provider/VM driver 接线仍待
下一轮独立验收。已有 IO8、Parker、runtime572 和共享生产工具没有修改。

## 构建期物理证据

`scripts/provider-native-roots.py` 不读取运行中的游戏 heap，也不执行游戏收集逻辑。
`verify_object(obj, declarations, assembly=...)` 检查真实 AMD64 COFF：

- 根是实际 PUBLIC data symbol，section 可读写、非执行、非 COMDAT，QWORD 对齐。
- 整个 `count * 8` 范围在同一真实 section 内，没有别的 COFF label 或重叠根侵入。
- initialized data 对应字节全零且没有指针 relocation；BSS 必须没有物理初始数据。
- 封存 ASM 中恰有对应的 PUBLIC `QWORD N DUP(0)` 或 `DUP(?)` 数组声明。
- 不能把只读目录、pool 指针、函数、标量 metadata 或一个布尔“已验证”声明当作根。

`provider_projection(manifest, verified_source_metadata)` 要求顶层 `native_root_spans` 与
已独立重建的原 source model 严格相同、符号在真实 exports 中，并重新检查 ASM/COFF。
调用者必须先完成现有正常 provider 的 source/class/Code/frame/ABI/ASM/COFF 验证；该
helper 不替代这些验证，也不从任意 receipt 旗标推导 source 语义。

`selection(packs, indices, objects)` 消费本次独立验证的 `load_packs` 契约，核对封存
manifest/receipt identity，仅投影实际选中的 pack，要求其真实 object 在 closure 中恰好
一次；未选中的根不得泄入集合。再次物理验证后返回可封存进 closure 的
`selected_provider_native_root_spans`。不允许在声明缺失时静默跳过有根的新 source family。

`directory_assembly` 重新验证物理 proof，再产生只读 `{address, count}` 目录。目录是
原生 metadata，不是 oop bank，永远不将目录自身提交给 collector。
`complete_consumer_assembly` 必须获得全部九源 bank 及 primordial/main 的源 exports，
缺少任意一项即失败。它读取原 count 符号作为整数，在私有栈上组成完整描述符集合，
追加同一选择集中的 native spans；不会为此补选 Java 方法或模块。

本轮实际 IO root 为 `.data+8`，4,096 QWORD / 32,768 字节；Parker root 为
`.data+1048736`，16,384 QWORD / 131,072 字节。偏移由各自真实 COFF 取得，不作为其它
批次的硬编码 schema。方法 ID、Java 字段偏移和 typed error 仍由既有冻结 source model
动态验证。

## ASM 消费协议及范围

新文件 `native/kernels/provider_native_root_snapshot.asm.inc` 提供：

```text
DWORD boom_provider_native_roots_snapshot(
    Span16* spans, DWORD spanCount, QWORD* output, DWORD capacity, QWORD* outputCount)
Span16 = { aligned native address, QWORD cellCount }
```

成功为 0。先完整校验和统计，再逐 cell 复制全部非空 oop，保留重复值，最后发布 count。
容量上限为既有 collector 的 1,048,576，物理根 bank 总长度可以大于此值。122 表示非空
值无法容纳；87 表示参数、溢出、对齐或元数据/根/output/count 之间不允许的重叠。
在有效静止调用中，两种失败均不写 output 和 outputCount；成功不写任何源 bank。
该函数不分配、不调用宿主、不轮询 worker、不借全局锁等待，也不触发收集。

完整 wrapper `boom_provider_native_roots_full_snapshot(output, capacity, outputCount)` 从
真实已链接符号读取九个 source count、实际 primordial count，并按同一物理 proof 的
native 数量追加 IO/Parker。它只在自己的栈上写描述符。测试将其产生的向量直接交给
原 MASM `boom_heap_collect`；Python 只负责夹具、调用及只读 multiset/digest 对照，没有
用 Python 填充 collector 根向量。

完整性只成立于当前静止非移动 collector 的这个集合：无活动 Java frame、没有外部
native 调用正在使用 oop、没有待处理 Java Throwable，且 worker 全部 join。这里不覆盖
`Context32+16` 的 pending exception oop、未来活动 Java/native frame 根、线程栈、JIT/
寄存器根或运行中的 safepoint 协议。若这些情况存在，必须先有单独、可验证的根协议；
不能把本目录称作全部运行期根。跨两遍扫描的并发写违反调用前提；防越界检查不构成
并发快照或原子事务保证。

## 实际测试

`tests/provider_native_roots.py` 使用真实 ml64/COFF/link/DLL 通过 21 项测试，包括正常
initialized/BSS 根、只读/执行 metadata、移动边界、label 侵入、非零初值、relocation、
源长度不符、遗漏声明/export、伪造 proof、选择/重复 object、遗漏普通/main 根，以及
ASM 压紧、重复值、空集、122 不写、错误 alias、对齐、容量和地址溢出。

`scripts/test-provider-native-roots.py` 消费根 agent 已独立通过的 Parker 执行
`.boom/unsafe-park/root-review-execution-v148-a/result.json`，只新增一个 source consumer
COFF 并重链到新目录。原 Java/所有 native provider/runtime COFF 与 stop 均不变。封存
AST 仅扩充测试：在 worker 静止前通过真正公开 FIS 构造打开一个额外普通文件，在两次
collection 中使用 ASM 向量，首轮后验证原 FD.parent/FIS 图仍可读，再调用原 Java close。
该过程没有宿主写 FD、JLA、Thread、普通 root bank 或 native root bank。

两个独立进程的公开 FIS(String/File)、八个原 Java Cleaner 的 1,024 次定向 wake/repark、
共享 stop、二十项锁定 JDK oracle 均通过。每次 collection 读取 1,204,245 个物理 cell：
九源 bank + main 五 cell + IO 4,096 + Parker 16,384。ASM 非空向量分别为 247 和 237，
与独立只读观察的完整 multiset 相同；去重计数分别 217 / 207，collector 实际接收的是
保留重复的 ASM 向量。首轮 native FD 非空数为 1、Parker 为 9，原 read 返回 `Q`；原
close 后 FD 根变零，Parker close 后 gate 根变零；两轮 freed 为 `[177,18]`。全部 bank
前后 digest 不变，FD/FIS 图和九个 gate 最终回收。worker exit/reaped 各八，failure、
uncaught、held monitor 均为零。这是正确性与完整传递证据，没有加速或自动 GC 声明。

开发执行：`.boom/provider-native-roots/source-consumer-v148-c/result.json`。首次 a 的
测试快照函数名被原执行器局部字典遮蔽，异常日志、进度和工具快照原样保留；修正只在
新测试脚本，新 b/c 输出未覆盖 a，也未修改 source/ASM 算法。

根 agent 独立复验 21 项物理/负例：
`.boom/provider-native-roots/unit-tests/4d4e9feee27f4919982fb1983d38acd2/result.json`，
SHA-256 `66b71140d8e0635fb8418c7d75c11e0ebb7706118171078d66d77c9be4a1297b`。
其独立真实 consumer 两冷进程及 oracle：
`.boom/provider-native-roots/root-review-source-consumer-v149-a/result.json`，
SHA-256 `2d389dc868667582950f5b814f829a4fc78acfeaedad45ed46645e655a205759`。

## 待接入的三处生产改动

只读草案位于 `.boom/provider-native-roots/integration-draft-v148-a`，未应用。
`inputs.json` 记录原共享文件 digest；必须在 29 native 轮结束后，结合最终 registry 名称
一次性应用并重新生成/严格验证新批次，不能把本组件通过记作正式 provider 接入通过。

1. `build-runtime-provider-pack.py:230` 与 `framed-runtime-service.py:36`：从独立重建的
   source metadata 投影根声明，保留两个新族的原 Java 回调和 family 依赖；组装后独立
   verifier 物理检查并发布 proof。新 helper/ASM 与新 family 源同批纳入 TOOL_FILES。
2. `prepare-class-init-probe.py:476/560` 与 `verify-initialization-closure.py:435/460`：
   精确投影已选 pack 的根及 object 恰一次，closure 封存集合；V 从本次 source-verified
   packs 独立重算物理 proof，缺项、额外项、错 count、换 object 均失败。旧无根包兼容空集。
3. `vm-entry-source.py:176/200/232/281` 与 `native/entry/vm_process.asm.inc:200/225`：
   正常 FLS/primordial bootstrap 后、OWAI open 成功后，且任何 Java worker 前调用
   Parker.open。共享 Reference/OWAI stop 不变，worker join 真成功后、OWAI.close 前
   Parker.close；失败时沿原 owner 错误路径保留 VM 内存。完整根 wrapper 包含九源/
   main/native 集合，不能只纳 IO/Parker。IO live handle/buffer/owner 非零时不假装释放
   heap 成功，也不擅自调用原 close 替代 Cleaner 或采纳外部句柄。原 OWAI 416..440 的
   源 wait/IE/stop/wake 统计保持原义，Parker 不添加未调用的 Object.wait Java 帧或统计。

草案新增生命周期观察字段时，512-byte report ABI12 与 decoder/runner 验收必须同批
更新。验收至少包括 open 前置顺序、重复/失败 open、活跃 close 拒绝且根不变、join
失败保留内存、正常 close、根全部进入实际 ASM collector 输入、故意遗漏任一普通/
main/native span 拒绝，以及旧 29 无新族镜像保持原 report 布局。正式输入必须重走完整
source/frame/COFF/native-entry V 和实际执行。此草案本身没有生产执行成功的声明。

复验命令使用新输出目录：

```powershell
D:\Dev\Python312\python.exe tests/provider_native_roots.py
D:\Dev\Python312\python.exe scripts/test-provider-native-roots.py --park-result .boom/unsafe-park/root-review-execution-v148-a/result.json --output .boom/provider-native-roots/fresh-consumer
```
