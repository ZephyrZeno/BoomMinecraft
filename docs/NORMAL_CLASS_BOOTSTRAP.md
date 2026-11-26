# 原始 Class 初始化与基础引导

v99 为正常源布局补充三个 Class 原生入口，接入同一自动批量生成、来源校验、依赖选择及 COFF 校验流程。游戏执行代码全部为 MASM；开发宿主和 JVM 只用于调用与对照。

## 三个入口的契约

| 入口 | 原始访问位 | 行为 |
| --- | --- | --- |
| registerNatives()V | private static native，0x10a | 检查已有 AOT 原生目标表，原子发布就绪状态 |
| getPrimitiveClass(String)Class | 包访问 static native，0x108 | 按名称内容取得八种基础类型与 void 的规范 Class 镜像 |
| desiredAssertionStatus0(Class)Z | private static native，0x10a | 根据所表示类型、加载器与冻结 VM 默认配置查询断言状态 |

注册表包含八项已有 Class 实例 native，以及基础类型查找、断言查询两个新目标。注册过程检查操作集合、重复操作、目标、方法 ID、native 标志和保留位，然后以 CAS 发布；重复注册保持幂等。其余 Class 声明继续未提供，不生成成功占位函数。Class 完整原生注册仍未完成。

基础类型名称通过正常 String 的 byte[]、coder 和源布局读取，接受 Latin-1 或 UTF-16 的等价内容，返回已有 Class 工厂中的同一规范对象。创建镜像不初始化所表示的类。空引用保留 NPE 错误种类，未知名称保留 ClassNotFoundException 种类；正常 Throwable 物化仍待完成，负向检查只证明待处理上下文。

断言配置当前固定为系统与应用默认关闭。基础类型、void 和数组返回 false；普通类／接口按定义加载器选择默认值。内核支持两个默认配置位，交付批次尚未接入类／包覆盖或可配置的断言选项。原始 Class.desiredAssertionStatus Java 包装器及其 ClassLoader 分支未在此轮执行。

依据：[OpenJDK 基础类型查找与断言查询](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/jvm.cpp)、[原始 Class](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/java/lang/Class.java)。使用锁定 JDK 的实际声明、类散列和 Code 身份；先验契约在全输入方法生成前检查，避免声明不匹配后才失败。

## 数据与初始化

ClassBootstrap Pool80 独立于 Java 对象字段：magic/ABI 0/4，注册状态 8、表项数 12，Class 池 16、String 池 24、NativeRow24 表 32、PrimitiveRow16 表 40，基础类型数 48、保留 52、系统／应用默认值 56/60、源 Class ID 64、保留 68/72。NativeRow24 保存操作、方法 ID、目标和访问位；PrimitiveRow16 保存 UTF-16 名称、长度和类型 ID。

三个普通入口保留真实 Class 类初始化门禁。原始 Class 初始化器调用注册入口，再实际创建 EMPTY_CLASS_ARRAY、serialPersistentFields 两个不同的空引用数组。测试开始时描述符状态、注册状态和两个静态槽均为零；C# 宿主不将其预置为完成。

## 实际执行与范围

两侧均选取原始 Class 初始化器、Boolean／Byte／Short／Integer／Long／Double／Void 七个包装类初始化器，以及 Class.getName、getComponentType 原方法体。独立闭包校验核对源 Code、原函数、静态状态、注册表模块及实际 COFF；没有改写这些 Java 初始化器或以宿主实现替代。

每侧验证：

- 8 工作者同时请求冷 Class 初始化，原始初始化器成功发布两个静态数组。
- 七个原始包装类初始化器为 TYPE 赋予正确的规范基础类型镜像。
- 9 种基础类型与 JVM 对照；Latin-1／UTF-16 名称取得相同身份。
- 29 次显式源 Java 调用／初始化入口，以及 8,192 次并发查找与重复初始化请求。
- 26 项错误检查，包括未知／空名称、待处理错误、未注册状态、元数据及错误绑定表。
- 静止回收释放 128 个未保留对象，同时保持 Class、源静态数组、规范镜像及输入图；回收后重复查找通过。

Rust 191、Python 107 项测试通过，fmt 与 clippy 通过。运行时为 79 个汇编源。原始 String 构造／初始化、完整异常物化、模块引导、System 各阶段、Minecraft、世界和自动回收仍未完成；并发测试不计作游戏侧多核优化完成。

schema 15 的三个原生入口和共享绑定规则已纳入自动流水线。System.initPhase1 直接扫描的前沿由 765 降为 762，其中 605 项仍是已有分派规则的继续展开动作，缺失请求由 160 降为 157。全输入家族数保持 407／577，待提供请求分别为 31,268／37,430。静态数量不代表启动进度百分比。

启动器继续只提供启动入口。完整原版未启动，发布目录仍为 v70。

## ClassLoader 断言快照对照（2026-11-26）

`java/reference/ClassLoaderAssertionsReference.java` 是独立开发对照，通过锁定 JDK 的原始 `ClassLoader.retrieveDirectives` 读取五个源字段。`scripts/test-class-loader-assertions-oracle.py` 核对批次的原始系统目录与实际 JDK 模块镜像摘要，在项目 `.boom` 的新目录编译并运行对照，不参与游戏运行。

八组实际 JVM 配置全部通过：应用默认开／关、系统默认开／关，以及是否存在两个类和两个包的覆盖规则。快照的 `deflt` 始终为应用默认值；系统 `Object` 的断言状态单独核对。四个数组保持真实 `String[]`／`boolean[]` 类型及名称与开关配对，两次读取所得对象和数组共十个不同引用。没有覆盖规则时四个数组为空。

结果在 `.boom/class-loader-assertions-oracle/v145-defaults-and-overrides/result.json`，SHA256 为 `e3559733a8b0855631c6e3e8686c7b80fc3e3dfc76613ffe7f2b8b8222249f97`。该结果只验证 JVM 参考行为；当前汇编配置仍不支持类／包覆盖，ClassLoader 汇编实现和原始初始化执行另行验收。
