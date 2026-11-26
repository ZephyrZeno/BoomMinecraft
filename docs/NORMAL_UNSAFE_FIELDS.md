# 正常布局的 Unsafe 字段定位

本模块提供原始 `jdk.internal.misc.Unsafe.objectFieldOffset1(Class,String)` 的汇编服务及正常实例字段地址解析器。它不是逐个 JDK 类的字段特例；声明元数据和可用字段映射从锁定输入统一生成。Minecraft 目标仍为 Java 1.21.1。

## 字段身份与执行边界

[OpenJDK Unsafe 的契约](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/jdk/internal/misc/Unsafe.java)把字段偏移定义为不供算术使用的标识；按类名／字段名的接口查找该类直接声明的字段，缺少时报告 InternalError。开发 JVM 仅用于声明、重复查询和错误关系对照，不要求其数值偏移等于本项目布局。

本项目采用 `0x55464c4400000000 | (globalFieldId + 1)` 的不透明标识。ID 对应加载器、来源类、原始字段序号和完整描述符。原始声明顺序保留，父类与子类的同名字段不会合并，也不会把父类字段作为子类直接声明返回。

不能直接返回声明类的物理字节偏移：当前布局将引用集中在可追踪前缀，子类加入引用时可能移动父类的标量字段。`boom_java_unsafe_field_address` 根据标识选择已有的 `boom_field_map<ID>`，再按接收者的实际类型解析地址，检查同堆完整对象、适用类型、宽度、对齐、前缀及边界。String 的四个最终字段复用正常字面量模块已有的映射。

查询仅读取已声明字段及规范 Class 镜像，不运行被查询类的初始化器。原始 Unsafe 初始化仍由源 native 入口的通用包装器保障；已有 JUNS80 注册子集仍保持原有范围。新的查询入口是单独的真实 AOT 绑定，没有将其伪装成 Java 方法体或扩充成完整 native 注册。

静态字段也保留声明及标识。地址解析器当前拒绝静态、数组与堆外地址，也明确拒绝没有可用实例映射的字段；本模块没有提供 typed get/put、CAS、静态 base、反射 Field 查询或堆外内存 native。后续内存家族可以复用同一身份与地址协议。

## 汇编 ABI

`boom_java_unsafe_field(Context32, argv*, pool, operation=0)` 返回 Java long 标识。参数槽依次为真实 Unsafe 对象、规范 Class 镜像、正常源布局 String。名称精确比较 UTF-16，支持 Latin1 与小端 UTF-16 的 String 存储，不分配对象、不修改名称缓存、不调用用户代码。

`boom_java_unsafe_field_address(Context32, pool, object, cookie)` 返回已检查的地址。它只解析地址；开发宿主的读写仅是布局夹具，不能计作已提供 Unsafe 内存 native。

UFMP128／ABI1：

| 偏移 | 内容 |
| --- | --- |
| 0／4／8／12 | magic、ABI、类型容量、字段容量 |
| 16／24／32／40 | heap cell、Class pool、runtime map、Unsafe layout |
| 48／56 | Unsafe bootstrap pool、String layout |
| 64／72／80 | UTF-16 名称区、类声明范围、字段页目录 |
| 88／92 | 名称区单元数、页数 |
| 96／100／104／108 | String value／coder 偏移、Unsafe 类型 ID、记录宽度 64 |
| 112／120 | 标识前缀、保留零 |

每页最多 1,024 条 Field64，低位 ID 精确定位页和槽。记录含来源类、原始字段序号、访问位、字段种类、名称范围、存储宽度、引用／静态标志、实际映射函数、全局 ID 和保留零。静态 cell 和未来协议的保留位置当前为零。所有表及名称为只读汇编数据。

生成器保留源类／字段声明摘要，原始 native 仍无 Java Code。独立验证器从原始计划重建字段顺序、名称区、可用映射、页目录、池、包装器及单元拆分，并核验实际 COFF 导出和依赖。缺少字段使用 Context kind 23，null 使用 4，错误形状使用 7，不可用地址能力使用 20；完整 Throwable 物化仍未接入本链路。

## 当前验证范围

服务器／客户端字段表分别包含 193,844／236,692 个原始声明，其中实例字段 101,693／117,471 个；可用实例地址映射 101,602／117,328 个。页数为 190／232。两侧完整来源与 COFF 校验已经通过；这些是元数据范围，不是游戏进度或所有字段的执行记录。

`Test-BatchUnsafeFields.ps1` 使用独立来源校验过的开发映像，执行源 Unsafe 与 AtomicInteger 的初始化器、原始构造器／getter，并检查 java.base 字段查询、继承布局、并发、错误及不触发目标初始化。名称 String 与大量普通目标对象明确为开发存储夹具，未执行这些任意类的 Java 构造器。执行结果另存项目隔离报告，不从静态表数量推导。AtomicBoolean 在当前原版输入中使用 VarHandle，其初始化仍属待实现的动态协议范围。

atomic 夹具只允许 AtomicInteger 构造器及 getter 两个指定的原始方法签名，由独立开发宿主传递原始槽参数。普通启动诊断的 `()V`／显式谓词限制保持有效；预先选择的夹具也必须经过原有链接、来源及诊断停止验证，`diagnostic_only` 不变。

两侧执行探针现已通过：每侧 26,743 条 java.base 字段查询涉及 5,173 个规范 Class；512 个地址夹具中有 18 个继承布局发生物理移动；另有 16,384 次并发查询和 59 项错误检查。8 工作者冷初始化原始 Unsafe，随后实际运行 AtomicInteger 初始化器及 6 组原始构造器／getter，验证通过映射地址写入的值能被原始 getter 读取。查询阶段保持该目标类未初始化，初始化器随后自行保存正确的字段标识。

开发 JVM 对照覆盖 83 条声明／重复查询关系及 3 条错误关系；未比较 VM 特有的偏移数值。Native 错误检查观察 Context kind，未宣称已生成可捕获的 Throwable 对象。全量静态字段表、这些 java.base 执行查询与全部游戏可执行能力分别记录。

两侧原始 System.initPhase1 均以 v104 的 258 个已核对 Java 选择为种子，经六轮真实执行，自动准入后续五类已有方法后停在 `Unsafe.compareAndSetInt(Object,long,int,int)`。字段查询已经在这条实际路径中执行通过；CAS、完整 System 阶段和游戏仍未完成。

完整 System 阶段、游戏启动、隔离世界、自动内存回收与游戏性能仍需各自的实际验收。源类、加载器、字段顺序／描述符、布局、映射、变换链、调用 ABI 或汇编实现变化，必须使相关表、绑定、链接和后续内存规则失效；动态定义和模组阶段仍未完成。
