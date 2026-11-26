# 原始 Java 窄字段原子操作

原版 JDK 的 `Unsafe.compareAndExchangeByte` 和 `compareAndExchangeShort` 在 Java 中把偏移向下对齐为 DWORD，用 `getIntVolatile` 和整数 CAS 更新其中的一个字节或短整数。布尔和字符包装器复用这些方法。

旧 UFMP ABI1 将偏移表示为字段 ID。对它执行对齐算术会选中其他字段。例如 `Module.enableNativeAccess` 的 ID 为 27622，旧 cookie 经 `& ~3L` 后会被解码为 `Module.name`。v141 的原生进程在此处得到错误种类 7。它已完成 `System.initPhase1` 并进入 `System.initPhase2`；此前报告中的字符串加载 PC 是残留调用位置。

## ABI2 虚拟字段槽

UFMP128 ABI2 保留 Field64 记录、源字段身份和接收者地址映射。cookie 高 32 位使用独立标记 `0x55464c32`，低 32 位为 `((fieldID + 1) << 8) | 0x80`。字段各有独立虚拟槽，固定字节 lane 为零。实际接收者仍通过已生成的字段映射选择物理地址，继承对象中的引用前缀重排不会改变 Java 持有的 cookie。

一个 byte 或 short 字段的对齐整数视图是独立的 32 位虚拟载体。运行时读取目标字段，将其余位补零；CAS 只对实际字段执行 `lock cmpxchg BYTE/WORD`。期望值的填充位非零时返回不匹配；希望写入非零填充位时明确拒绝。不会读写相邻字段、对象头或分配器填充区。Java int 参数只使用托管参数槽的低 32 位。

这个边界很重要：原始 `Module` 的逻辑负载为 65 字节，布尔字段恰好位于 offset 64；同时有些继承字段在不同接收者中的物理地址模 4 不同。直接对物理地址读写四字节无法保留这两种情况的语义。

宽标量字段可以使用字段内部的有界字节视图；引用字段要求原始锚点、引用类型和完整槽宽。错误标记、跨字段位移、静态字段和越界访问继续报错。旧 ABI1 的精确字段访问保留，ABI1/ABI2 标记不能混用。数组继续使用已有有界数组路径。

## 生成、验证和运行

Rust 生成器和独立 Python 校验器共同定义 ABI2 池。`refresh-unsafe-field-batch.py` 在全新 `.boom` 目录生成派生摘要，只重汇编字段池所在单元，其余 Java 汇编和元数据保留原始工件路径及摘要。派生说明与整个批次的验证回执分别保存；完整验证通过后才发布 `verification.json`。

`test-unsafe-field-carriers.py` 使用独立验证过的原始 Java 选择镜像及源接收者布局，执行原始 byte/short CAS、布尔包装器和 `Module.implAddEnableNativeAccess`。它检查对象尾部、继承布局变化、相邻存储、错误视图、两种 ABI 和实际操作系统线程争用。接收者的目标存储属于开发夹具；此测试本身不表示完整 VM 或 Minecraft 已启动。
