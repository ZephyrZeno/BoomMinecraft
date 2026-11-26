# 原始反射构造器调用

v113 归档的实际语义前沿是 `jdk.internal.reflect.DirectConstructorHandleAccessor$NativeAccessor.newInstance0(Constructor,Object[])Object`，源方法 ID 为 116676。两侧 System 诊断各经两轮执行，从 634 项 Java 准入增至 636 项，已越过类标志查询。v114 已生成该 native 和旧 NativeConstructorAccessorImpl 同签名入口的正常布局绑定，两侧来源、汇编、COFF 及接入闭包校验通过。服务器的两个入口进一步通过了正常 Constructor 对象调用测试；完整异常契约仍未完成。

## 已完成的汇编参数内核

`native/providers/constructor_widen.asm.inc` 实现 Z、B、C、S、I、J、F、D 的反射参数转换，禁止 Java 不允许的窄化或 boolean／数值混用。窄整数按实际宽度归一化，整数向浮点及 float 向 double 使用汇编转换指令。转换临时使用 Java 所需的浮点模式，并恢复调用者的完整 MXCSR；不会通过 Rust、C# 或 JVM 执行游戏转换。

`native/providers/constructor_unbox.asm.inc` 在真实汇编堆中验证引用，经正常运行时类型表匹配原始包装类的类型 ID 与布局，再按原始 value 字段的偏移和宽度读取值，调用上述转换内核。它不接受未注册包装类型、内部地址、错误布局或越界字段，不为查询分配游戏对象。元数据为 BCNV48/1，八行，每行 24 字节。

两项内核都通过了 JDK 21 真实反射构造器的 456 项独立结果对照：175 项允许转换，281 项拒绝转换。每层另检查五种 MXCSR 设置下的 2,280 次结果及八工作者 32,768 次并发调用。标量层通过五项错误检查；正常堆拆箱在服务器和客户端的原始类型数据上分别通过 20 项错误检查及上述全部对照／并发检查，预热后没有游戏对象分配。

拆箱测试中的包装对象是明确的正常布局夹具，由开发宿主写入测试值，没有宣称执行它们的 Java 构造器。JVM 只生成独立对照结果，C# 只提供 FFI、夹具和断言。当前检查覆盖正常引用、字段读取、转换及错误协议，尚未覆盖完整 Java Throwable 物化和 catch 行为。

## 接入原始构造器的顺序

`constructor_callsite.asm.inc` 已实现共享调用内核：初始化目标类，检查能否实例化并分配正常对象，再处理参数及调用原始构造器汇编。这个顺序与 [OpenJDK 的反射构造器调用](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/runtime/reflection.cpp)一致；初始化副作用、参数失败及构造器异常不能任意交换次序。[VM 的入口](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/jvm.cpp)负责转入该调用流程。

服务器来源映像的 13 个原始 JDK 调用现场已执行通过，覆盖 Object、八种包装类、双引用参数的 SimpleImmutableEntry，以及 String、StringBuilder、ArrayList 的实际构造器体错误。175 项基本类型构造结果与 JVM 一致，281 项转换被拒绝；验证六次原始冷类初始化、三项构造器体错误、十项调用前错误，以及八工作者 512 次并发原始 Integer 构造。返回的正常对象字段由原始 Java 汇编构造器写入，没有使用空构造桩。

调用内核返回独立的阶段标记，区分构造器体异常与初始化／参数检查失败；目前保留原始 Context 错误，尚未完成 InvocationTargetException 包装。调用现场使用已核对的不可变源记录；单独调用现场不是面向 Java 的 Constructor 对象入口。v114 的 `constructor_invoke.asm.inc` 读取正常 Constructor 的原始 clazz／slot 字段，核对真实堆对象、Class 身份和原始元数据，再选择相应现场。

实现应复用已来源核对的全部构造器元数据，并生成共享的调用现场与工厂规则，而非为每个类手写构造函数。诊断选择器需要根据实际达到的目标自动选择原始构造器／初始化器及对应工厂；未选择的方法保持明确停止。普通 Java 构造器本身继续使用自研后端已有的汇编，不生成空对象冒充执行成功。

调用期间需要真实 native 帧，相关[帧数据扩展与入口适配](NATIVE_FRAME_OVERLAY.md)已通过两侧现有入口和冷反射回调测试。两个新 native 使用原始声明的 ABI3 native 帧；包绑定同一个独立校验的帧数据扩展，闭包选择器替换原帧数据对象。目标类初始化失败必须保留其异常；构造器体的异常还需按反射契约包装，完整正常异常协议仍须继续接入。不得用旧的 opaque Constructor 布局或 JVM 回退代替正常源布局。

## 批量目标选择与停止边界

`constructor-invocation-source.py` 自动核对服务器 67,407／客户端 75,305 项构造器的原始类、Code 身份、参数类型、正常布局和初始化状态。NIVK96/1 池引用原枚举池的范围表、32 字节构造器记录、16 字节选择行，以及共享拆箱和调用池；同一汇编服务处理全部匹配目标。

已选择的类与原始构造器体生成 CINV64/1 现场。未选择的类或方法只生成明确的诊断回调，记录真实来源，按实际调用自动准入下一轮；不把这些回调当成构造器执行，也不伪造缺少的类描述符。来源不完整的记录保持不可用。闭包独立校验器重新生成选择表，核对数据、来源、所需提供者家族及唯一帧数据对象。

## 正常 Constructor 入口执行验证

`Test-ConstructorInvocationBindings.ps1` 复用已独立校验的服务器来源映像。正常 Constructor 对象由原始枚举入口产生；测试通过两个原始 `newInstance0` 绑定进入共享汇编选择器，并执行上述 13 个原始 JDK 构造器体。175 项允许转换、281 项拒绝转换、六次冷初始化、五项调用前错误，以及八工作者 512 次并发构造通过；两个 native 入口分别实际调用 235／744 次。加载器、模块和输入包装对象仍为明确夹具，完整模块引导为 false。

三项原始构造器体错误仍以原始 Context 错误返回，本次专门记录为“未完成 InvocationTargetException 包装”，没有将错误类型不完整算作完整反射兼容。测试准备绑定调用者明确接受的独立校验证据 SHA256，运行前后核对映像、对象、配置、运行时及源码输入散列。首次正常 System 执行已进入 GBK 原始构造器的自动选择，后续轮次继续由真实停止记录驱动。

完整 `newInstance0` 兼容、异常包装、完整 System、游戏与世界仍未验收完成。v114 新增两个经过执行验证的源绑定；绑定数量不表示每种异常、加载器或未来变换语义已经覆盖。
