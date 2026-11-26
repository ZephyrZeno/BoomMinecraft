# 独立 Reference.get0 来源候选

`reference_referent_get.asm.inc` 将正常 Reference.get0 读取规则从 NIO 候选中独立出来。服务检查接收者和结果的堆归属，通过实际继承字段映射取得 referent；空引用及已有异常保持原上下文语义。它只依赖正常元数据、堆、类初始化和 native 帧，不依赖 Windows Dispatcher 的字段或缓冲区服务。

`reference-referent-source.py` 从原始 get0 声明、Java get 的唯一 native 调用点及 referent 字段身份动态取得方法和字段编号，验证实际 receiver 类型、八字节引用宽度、继承位置和引用前缀布局。本服务端输入得到方法 50138、字段映射 29684、88 个继承接收者；这些编号不作为其他批次的 schema 约束。

新服务与已执行的 NIO reader 分别由同一 ML64 编译，171 字节实际指令完全相同，外部调用目标仍只有 boom_heap_contains；新 pool 和服务使用独立名字。源码、精确汇编、实际 COFF、原生帧和所需依赖均通过独立检查。

最新证明为 `.boom/reference-referent/source-bound-v145-c/verification.json`，SHA256 为 `72e3ff0c23cd864330aaabd95b9c0cdc46b09ca64b641b534ef8949132a0eb3b`。独立候选尚未正式注册、链接或执行，不能将旧 reader 的运行记录扩大为新完整 family 的执行验收。

当前规则要求非移动堆和 GC 静止边界；它不提供自动引用发现、完整弱／软引用 GC 或类重定义。正式启动链仍需另外验证。
