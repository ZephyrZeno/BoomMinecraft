# 原始类型数组的物理字节范围

`native/kernels/primitive_heap_span64.asm.inc` 提供纯 MASM 的
`boom_primitive_heap_span(heap, oop, byteOffset, byteLength, outAddress)`。
它是 Unsafe 堆／原生内存复制服务的基础组件，尚未代表这些服务或 Main 已执行。
现有 89 源运行时、117 项工具来源、原 Java Code 和正式运行验收状态保持不变。

函数取得现有堆锁，从真实块链起点走到候选对象，随后检查存活标记、无引用前缀、
八种原始类型数组标签和物理载荷范围。不能只依赖 `heap_contains`：
该接口的候选 header 检查不足以排除在数组载荷中伪造的内部对象。
新函数不会分配、触发 safepoint、写 Java 字段、修改 Context 或登记 oop 根。
调用者负责持有正常对象引用及现有非移动堆的回收生命周期。

`oop[-16]` 已是物理字节数，不能再乘元素宽度。
成功返回 0 并发布实际地址；失败保留输出值，返回参数、成员身份、形状、范围或溢出错误。
零长度允许位于合法载荷末端，所有前置检查仍然执行。

通用构建工具为 `scripts/primitive-heap-span.py`，支持 `build`／`verify`。
显式参数包括 runtime 路径、全新 `.boom` 输出、assembler 和 linker；
`scripts/test-primitive-heap-span.py` 接受 runtime、helper.json 输入及全新输出。
两者的 `--help` 列出完整参数。工具会核对 runtime.json 绑定的全部汇编／数据来源，
并限制到已确认的 heap／arrays／objects ABI，不重建运行时或执行游戏。

主 agent 已从发布源码实际构建并独立运行：

- 181 个边界／错误用例，覆盖实际八种数组、空数组、非对齐字节范围和末端零长度。
- 普通对象、引用数组、伪造内部对象、无效标签／形状／引用前缀、错误堆和溢出拒绝。
- 显式静止回收后的旧指针拒绝；没有启动自动回收。
- 8 个 OS 线程共 512 次真实汇编分配和范围查询，以及实际堆销毁。
- 完整 COFF 的指令／数据、节标志、符号辅助记录、重定位和 unwind 比对。
- 规范重链的完整 PE，以及最初冻结对象重链后的 PE，逐字节相同。

夹具单独生成测试 DLL，不进入 provider 或 Main；实际数组由原运行时创建。
本地独立回执为
`.boom/primitive-heap-span/published-root-test-v232-a/verification.json`，
SHA256 `741d8816839bf74efd52fcb71cabb8247ab02648e2ce67231c970474c4839fea`。
该组件验证不包含原 Java 包装执行、Main 启动、任意地址访问或多核性能提升。
