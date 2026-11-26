# 正常布局的反射构造器枚举

本项继续推进 Minecraft Java 1.21.1 的原始 System 启动路径。v110 实际执行停在 `Class.getDeclaredConstructors0(Z)[Ljava/lang/reflect/Constructor;`，该声明没有 Java Code。新增 `normal-constructors-v1` 提供者从锁定的原始 class 文件批量提取元数据，游戏执行由 `native/providers/constructors.asm.inc` 完成。基础 v109 Java ASM／COFF 与原始编译器身份不变。

生成与实际 COFF 校验已通过：服务器 67,407 项、客户端 75,305 项构造器记录。分别有 42／57 项参数或异常类型尚不可用，保留显式不可用状态；不会为缺失类型生成空 Class，也不会返回不完整的构造器列表。数量覆盖不等于所有构造器的实际执行。

## 来源与对象

记录来自每个原始声明的访问标志、方法序号、描述符、Exceptions、Signature、RuntimeVisibleAnnotations 和 RuntimeVisibleParameterAnnotations。另保留类型注解及 MethodParameters 的原始字节，供后续反射服务使用。原始类散列和锁定归档散列继续绑定；JDK 与游戏／库来源按各自定义加载器解析，不能把同名应用类型混入 bootstrap。

返回对象采用当前原始 `java/lang/reflect/Constructor` 的完整继承布局；声明类、参数和异常使用正常 Class 池中的规范镜像。参数与异常数组每次创建，泛型签名为正常 String，注解为真实 byte[]。slot 使用本后端的原始方法序号，保留给后续调用解析；不借用旧 VM 内部对象布局。

服务按 publicOnly 过滤原始声明；原始 primitive／数组类型返回空 Constructor[]。枚举只解析元数据，不执行被查询类的构造器或初始化器。创建非空反射对象时，原始 Constructor 类及其父类的初始化仍通过汇编类状态机执行。

行为依据为 [OpenJDK 构造器枚举](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/jvm.cpp)、[反射对象字段设置](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/runtime/reflection.cpp)与[Constructor 创建时的类初始化](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/classfile/javaClasses.cpp)。实现为本项目独立汇编；没有 JVM 或 GraalVM 回退。

## ABI 与增量构建

Pool 为 NCTR160／1，绑定正常 ClassPool、非移动 Heap ABI1、原始 Constructor／String 布局、结果数组类型、类状态、字段偏移、类型范围和构造器行。Range16 保存每个类型的首行、数量与可用状态；Row80 保存访问标志、参数／异常类型 ID 和原始属性指针。普通 Java 包装及 getter 继续复用自研后端的既有方法体。

类型容量必须与所绑定 ClassPool 一致；黑盒错误输入测试曾发现漏检该不变量，v111c 已加入检查。异常或原生失败不会因此变成正常 Java 返回值。

包的独立校验从原始输入重建元数据，核对布局、生成汇编和真实 COFF 导入／定义。尚缺的声明保持未提供。更改规则或 ABI 后需要新包；旧批次和既有证据不改写。

本服务包含 Java 类初始化回调，清单明确 `leaf_guest_services=false`。当前基础批次只为三项原生声明生成调用栈帧，本次尚未扩展至所有 native。完整 native 栈、异常物化、活动根、安全点、自动回收与动态重定义仍未完成，不能把本包当成完整反射运行时。

## 执行验收

开发测试通过 FFI 请求原始 native，执行七个原始 Constructor getter，并与独立 JVM 比较构造器数量、描述符、修饰符、泛型签名、注解原始字节及异常类型。另检查 publicOnly、primitive／数组、目标类保持冷状态、错误输入及多线程枚举。

为了覆盖不同来源的元数据，专项测试给 java.desktop、java.xml 提供两个明确标注的正常布局 Module 准备夹具，并准备一个应用加载器及其未命名模块。它没有执行这些加载器／Module 的构造或完整模块引导，不计作游戏模块启动完成。JDK 原始构造器中没有所需的运行时参数注解样本，因此另查询一个原版 `aaf$a` 类的构造器元数据；没有执行该原版类的构造器、初始化器或其他游戏方法。

直接从冷 System 类调用 initPhase1 的旧诊断准备还暴露了初始化顺序缺口：ReflectionFactory 早于 AccessibleObject 初始化时，会从 SharedSecrets 取得空的 JavaLangReflectAccess。用同一已校验映像先执行原始 AccessibleObject 初始化，原先的 NPE 消失，推进至 ReflectAccess 的已有 Java 目标；没有手填该静态字段。HotSpot 在 [System 阶段前初始化反射 Method 类](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/runtime/threads.cpp)，从而先运行其 AccessibleObject 父类初始化。

新诊断显式请求 String、System、Class、Method 四个原始类根，再调用 System.initPhase1。ThreadGroup／主线程、Module、Finalizer 等 VM 引导步骤仍需实现；这是一组明确的诊断前置条件，不能标为完整 VM 引导。来源种子只复用已验证的 Java 选择记录，新类根仍必须实际执行。

两侧专项执行测试均通过：15 种类型、48 项原始构造器的 JVM 元数据对照，81 个正常 Constructor 对象及七个原始 getter 的检查，八个冷目标类保持不变，18 项错误检查，八个工作者并发枚举 512 次。参数注解、泛型签名、方法注解与异常列表均有实际覆盖；夹具的加载器／模块身份与完整启动分开统计。

真正的 System 重跑两侧均经四轮完成本次诊断，Java 自动准入从 566 增至 634，推进至尚未提供的 `jdk/internal/reflect/Reflection.getClassAccessFlags(Class)`（117015）。该接口需要真实类访问标志，不能用固定 public 标志代替。完整阶段尚未完成，末轮的一个监视器持有继续由独立进程退出回收，没有强制解锁。完整原版、世界往返及游戏侧多核／GPU／内存优化继续单独验收。
