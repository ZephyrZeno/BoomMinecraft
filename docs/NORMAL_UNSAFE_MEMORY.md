# 正常 Unsafe 堆内存与原子规则

v107 在正常字段表之上增加一个共享汇编服务，由同一声明规则生成 42 个原始 `jdk/internal/misc/Unsafe` native 适配器。源类必须来自锁定的 bootstrap `java.base`，逐项核对类摘要、签名、访问标志和不存在 Java Code；原来的 Java 包装方法继续交给普通字节码后端。

## 一条规则覆盖一组接口

`src/compiler/batch_unsafe_memory.rs` 将九种数据类型与四种动作相乘，生成普通／volatile 的 get、put，共 36 项；Int、Long、Reference 再各生成 CAS 和 compareAndExchange，共 6 项。每项保留原始方法 ID 和声明身份，调用 `boom_java_unsafe_memory`。不依据调用点、某个 Java 类或当前测试数值生成专用实现。

适配器先经过原始 Unsafe 类初始化，然后调用汇编服务。参数使用现有托管 ABI：每个逻辑参数一个 QWORD，包括 long／double；原始 Java 方法的局部变量槽规则仍由字节码后端处理。操作码为 `action * 16 + kind`，kind 为 Boolean、Byte、Char、Short、Int、Long、Float、Double、Reference 对应的 1 至 9；action 为普通读 0、普通写 1、volatile 读 2、volatile 写 3、CAS 4、exchange 5。

`verify-batch-unsafe-memory.py` 独立重建 42 项声明契约、适配器正文和 COFF 导入／导出，并绑定汇编内核摘要。schema 21 的完整批量校验将这一家族纳入已提供 native 集合。启动路径选择器自动连入字段池、源类及全部依赖，不需要逐个编写桥接。

## 汇编内存语义和边界

实现位于 `native/runtime/java_unsafe_fields.asm`，复用 [UFMP128 字段池](NORMAL_UNSAFE_FIELDS.md)。字段 cookie 是不透明声明标识；运行时按实际接收者类型解析地址，支持子类引用前缀重排。相同宽度的标量别名允许 Java 的 float／double 原子包装使用 int／long CAS；引用区与标量区不能混用。

原始基本类型数组支持有界字节视图，普通标量读写可以不对齐。引用数组使用实际源数组类型，要求引用槽对齐且引用前缀与负载一致。volatile 和原子操作目前要求自然对齐；不支持的对齐、静态基址和堆外地址保留明确失败，不能当作接口全部域均已实现。

普通读写使用 MOV；volatile 读取采用保守 MFENCE，volatile 写入采用 XCHG；Int／Long／Reference CAS 和 exchange 使用 LOCK CMPXCHG。Boolean 写入取最低位，读取按非零归一化；Byte／Short／Int 返回符号扩展，Char 无符号扩展，Float／Double 保留原始位模式。该实现先保证语义，没有宣称屏障已做性能优化。

对象、接收者及引用参数必须属于当前汇编堆。引用写入现有可追踪前缀，不分配游戏堆对象。当前回收契约仍为显式静止点；本规则没有引入并发／自动回收，也没有完成正常 Throwable 对象物化。空目标所代表的堆外访问不提供；不会借用本机任意指针执行。

## 执行验证

`Test-BatchUnsafeMemory.ps1` 在两侧实际原版输入中选择 42 个源 native 和原始 AtomicInteger 构造器、get、compareAndSet、getAndIncrement。准备夹具仅提供目标存储和测试参数；原始 Unsafe 初始化、原子方法和被选择的 Java 方法真实执行生成的汇编。C# 仅为开发 FFI 宿主，不属于交付游戏运行时。

每侧独立选择／链接／执行通过：

- 4,272 组标量向量，与开发 JVM 的字段／数组、普通／volatile 行为对照；52,386 次顺序源 native 调用，包含后续关系检查。
- 354 项 CAS／exchange 成败与见证值检查，以及 22 项普通字节视图／Boolean 归一化检查。
- 8 个测试工作者完成 24,576 次受争用的原子更新；128 轮 volatile 顺序一致性 litmus 检查未观察到禁止结果。有限测试不代替内存模型证明。
- 原始 Java `AtomicInteger.getAndIncrement` 在 8 个工作者上执行 4,096 次，最终计数一致。
- 32 项错误检查，以及引用写入保持、CAS 清除后可回收两项显式静止点回收检查。

JVM 对照另执行 324 项原子关系、一个未对齐普通字节视图及一个 Boolean 非零读取；两个 VM 的数值字段偏移和对象地址不作比较。浮点信号 NaN 的允许静默化单独计数，本轮两侧均为 0。

实际 System.initPhase1 两侧各经七轮诊断，从 375 项准入自动扩展至 516 项，越过 CAS 后到达尚未提供的 `Class.forName0` 源 native。该结果说明一组真实运行时规则可以批量接通原有 Java 方法；完整 System 引导、Minecraft 启动和游戏多核优化仍未完成，继续单独验收。

```powershell
./scripts/Test-BatchUnsafeMemory.ps1 -Batch <schema-21-batch> -Plan <matching-plan> -Runtime .boom/assembly-runtime-v107
```
