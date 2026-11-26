# 正常 Class 的访问标志与反射修饰符

`class-flags-v1` 在基础 Java 批次之外实现两个原始 native：`jdk.internal.reflect.Reflection.getClassAccessFlags(Class)` 与 `Class.getModifiers()`。游戏执行路径为汇编；构建工具从锁定的原始 class 字节自动生成整个可用类型集合的只读元数据，不逐个补写类。

## 两种查询的区别

原始访问标志与反射修饰符不是同一组值。普通类的原始标志保留 `ACC_SUPER`；反射修饰符去掉它，并优先使用类自身的 `InnerClasses` 条目，因此嵌套类的 private、protected、static 等修饰符可以与 class 头不同。旧格式 `Synthetic` 属性也参与原始标志的计算。

数组的原始访问标志为零。数组反射修饰符包含 abstract、final，并继承最底层元素类型的可见性；基本类型及 void 的两种查询均为 public、abstract、final。元数据单独保存可用状态，不能把数组合法的零标志当成缺失类型。

行为依据为 [OpenJDK 21 的 JVM 查询入口](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/jvm.cpp)、[普通类修饰符计算](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/oops/instanceKlass.cpp)及[对象数组修饰符计算](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/oops/objArrayKlass.cpp)。本项目的独立 JVM 对照另比较实际返回值。

## 汇编服务与失效边界

池 ABI 为 JCFG32/1，行宽 16 字节，保存原始标志、反射修饰符、可用状态及保留字段。池容量必须与正常 Class 池一致。服务经正常 Class 类型验证后按类型 ID 查询，不修改 Java 字段、不初始化查询目标、不分配游戏对象。外层原始方法桥接仍执行声明类初始化。

null Class 产生 NPE，非法引用或池结构产生内部错误，元数据不可用产生明确的兼容停止；待处理错误保持不变。这里仍使用现有运行时的错误协议，不能由查询服务推断完整 Java 异常传播已经完成。

生成器与独立校验器重新读取原始 class、类计划、正常类型表、源 native 声明，并检查生成汇编及实际 COFF 定义和导入。输入、变换链、布局、类型编号或工具身份变化时重新构建提供者；当前冻结类型集合不支持动态重定义，未来模组变换必须使相关元数据失效。

## 验证范围

Python 测试覆盖 class 头与 InnerClasses 的差异、Synthetic 属性、接口及多维数组底层可见性。开发执行测试选择原始的两个 native 桥接，使用正常 Class 镜像，逐项与 JDK 21 查询结果比较，并检查非法参数、并发稳定性及预热后零游戏对象分配。

v112 的服务器和客户端执行测试均已通过：每侧 61 个类型样例，其中 37 个为数组，49 个样例明确区分原始标志与反射修饰符；122 个查询值与 JDK 对照一致。每侧另通过 13 项错误检查及八工作者 32,768 次预热后零分配调用。两侧原始 System 初始化均已越过旧类标志缺口，推进到需要自动选入的构造器访问器 Java 方法；这不表示完整 System 阶段已经完成。

开发宿主显式准备正常形状的 loader/module 夹具；这些夹具不代表完整模块或线程启动已经完成。C# 只作 FFI 驱动与断言，JVM 只作独立结果对照。完整游戏、世界创建、多核游戏调度、GPU 优化和自动内存回收仍须分别验收，不能由这两个 native 或测试并发次数推断完成。
