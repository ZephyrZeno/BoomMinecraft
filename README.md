# BoomMinecraft

An experimental AOT compiler, assembly runtime, and launcher for Minecraft: Java Edition 1.21.1 on Windows x64.

自研编译器将 JVM 字节码翻译为 x86-64 汇编，目标是通过启动器运行完整原版 Minecraft。游戏逻辑、运行时及游戏执行中的多核、GPU、内存优化均以汇编实现。翻译器使用 Rust，正式构建与生成工具使用 Python，启动器使用 C#。PowerShell 文件和一次性 Python 驱动只保留在本地。

**项目处于开发阶段，完整 Minecraft 客户端和世界尚未启动。** 当前[原生初始化链](docs/NATIVE_RUNTIME_35.md)已完成 System 三阶段到 VM4；[内存接入镜像](docs/UNSAFE_OWNED_MEMORY.md)、[Windows NIO 登记](docs/WINDOWS_NIO_INIT_IDS.md)、[文件属性查询](docs/WINDOWS_NIO_ATTRIBUTES.md)、[RAF 文件操作](docs/RANDOM_ACCESS_FILE_IO.md)和[Perf 汇编服务](docs/PERF_NATIVE.md)已逐步接入原版初始化。[新的 Inflater 所有权与数组接口](docs/INFLATER_RW_OWNER.md)实际完成 14 个原 Java 测试的精确 JDK 对照，包含已修正的错误消息；[反射数组分配](docs/REFLECTION_ARRAY_ALLOCATION.md)的 49 个有效用例也已通过原 API 对照。原版专用服务器 `Main --help` 已越过 `Inflater.initIDs`，[Class.forName 汇编修复](docs/CLASS_LOOKUP_CNFE.md)已修正参数顺序并构造真实缺类异常；[原版系统／平台加载器的预链接查找](docs/CLASS_LOOKUP_BUILTIN.md)已通过 10 个原生用例，包含应用类及实际模块归属。

日志库已有汇编的 9,640 个 Java 方法已批量选入，并逐项核对原始 Class、字节码及汇编哈希；日志批次的完整来源校验覆盖 81,476 个原始 Java 方法，旧有 71,884 个方法及 193,025 个生成函数的身份全部保留。此前的 241 对象镜像实际推进到 `PropertiesUtil` 的[无捕获 Supplier Lambda 接线](docs/NORMAL_LAMBDA_EXPANSION.md)。批量派生镜像已接入 23 个同形态 Lambda 的元数据及 [Object.clone 汇编服务](docs/OBJECT_CLONE.md)，244 个对象、14 段根引用及完整 PE 独立重链接校验通过。复制服务的 26 项组件用例、8 个 OS 线程的 512 次复制和真实小堆 OOM 均通过。新增[字段解析与绑定发布汇编服务](docs/METHOD_HANDLE_FIELDS.md)后，249 对象镜像独立重链接通过，实际原生 Main 越过 `MethodHandleNatives.resolve`，停在 `ConcurrentSkipListMap.doPut` 的 `VarHandle.compareAndSet` 调用，全部资源清理通过。[正式容量检查工具](scripts/audit-namespace-capacities.py)已验证 NIO、RAF 和 Inflater 三类容量守卫的旧镜像负例与修复正例。各 Lambda 工厂及 SAM 的实际执行尚未逐项证明。Main 类初始化、方法体和帮助输出仍未完成；客户端窗口尚未验证。方法数量与实际执行范围分别记录。此前的[31 包运行记录](docs/NATIVE_RUNTIME_31.md)保留独立历史。

后续引用字段 CAS 桥已逐项核对 46 个原始常量池调用点及 81 处已选择字节码调用。251 对象映像的完整 PE 独立重链接通过；实际原生 Main 不再停在上述 VarHandle 缺口，推进到 `Class.getDeclaredFields0`。CAS 独立组件另通过 8 个 OS 线程、128 次争用和精确调用／异常验证。[正常字段反射汇编服务](docs/NORMAL_FIELDS.md)已通过 12 组、972 次原版调用；接入[反射字段的 Unsafe 偏移查询](docs/UNSAFE_REFLECTED_FIELDS.md)后，255 对象映像独立重链接及实际资源清理通过，推进到 `Striped64` 的 long 类型 `VarHandle.weakCompareAndSetRelease`。完整 Main、客户端和世界仍未完成；这不代表全部 CAS 调用点或完整 VarHandle 家族已执行验收。

[int/long VarHandle 比较桥](docs/PRIMITIVE_VARHANDLE_COMPARISONS.md)已接入 19 个原 CP 调用点，独立原版 LongAdder、AtomicBoolean 与 8 线程争用验证通过。257 对象镜像通过完整 PE 独立重链接，但实际运行退出70，严格清理验证失败。只读捕获定位到方法句柄对 `ServiceLoader.load(Class, ClassLoader)` 的静态方法解析；该失败记录对应当时尚未实现的方法域及 VM 原生 ResolvedMethodName 状态，没有计作启动成功。

后续来源选择已正常准入 `ResolvedMethodName` 原类及构造器，新的完整校验覆盖 81,477 个 Java 方法和 220,046 个生成函数，此前全部方法与函数保持一致。其原版初始化函数、类描述符和新增的一个普通失败根槽已通过独立汇编与完整 COFF 核对；此来源／机器准备阶段尚未执行新运行时或新 Main，后续运行结果另行记录。具体边界见[正常类准入记录](docs/NORMAL_LAMBDA_EXPANSION.md#normal-resolvedmethodname-source-admission)。

[普通静态方法解析汇编服务](docs/METHOD_HANDLE_METHODS.md)现已通过真实 `ServiceLoader` 调用方、共享 RMN、fresh VMInfo、8 个 OS 线程和异常／pending Context 验证，并修复了应用加载器来源映射。260 对象、15 段根引用的新原版镜像通过完整 PE 独立重链接；实际 Main 越过原方法解析缺口，资源清理全部通过，新的停止点是 `PreviewFeatures.isPreviewEnabled()` 原生接口。完整 MethodHandle 调用、Main 帮助输出、客户端与世界仍未完成。

[PreviewFeatures 汇编查询](docs/PREVIEW_FEATURES.md)已通过默认／启用两种独立配置的 216 次原版 API 调用，配置来自只读 VM 启动选项，原 Java 类初始化与缓存逻辑保持不变。262 对象、15 段根引用的镜像通过完整 PE 独立重链接；实际 Main 越过该接口，推进到 `Class.getEnclosingMethod0()`，资源清理全部通过。Main 初始化、帮助输出、客户端和世界仍未完成；这也不代表已支持 preview classfile。

[EnclosingMethod 汇编接口](docs/CLASS_ENCLOSING_METHOD.md)已从原始 Class 属性重建 enclosing class、方法名和描述符，并通过 119 次原 API 调用、四线程及真实小堆 OOM 验证，保留原 native Frame 和 Java 包装方法。264 对象镜像通过完整 PE 独立重链接；实际 Main 越过该接口，推进到 `Class.getDeclaringClass0()`，资源清理全部通过。Main 初始化、方法体、帮助输出、客户端和世界仍未完成。

[DeclaringClass 汇编接口](docs/CLASS_DECLARING_CLASS.md)已按原 `InnerClasses` 双向身份核对生成声明类目录，164 次原 API 调用、四线程及真实堆耗尽检查通过。266 对象镜像通过完整 PE 独立重链接；实际 Main 越过该接口，推进到 class52050/CP53 的捕获 `Set → Predicate` Lambda，资源清理全部通过。原版输入没有 ICCE 坏例，其 AOT 异常分支尚未执行验证；额外类名查询仍有未实现依赖。Main 初始化、帮助输出、客户端和世界仍未完成。

[方法枚举](docs/NORMAL_METHODS.md)、[原常量池读取](docs/NORMAL_CONSTANT_POOL.md)和[有界反射调用](docs/METHOD_INVOKE_STATIC.md)的独立汇编候选已通过原 Java API、JDK 对照、OS 线程与显式 GC 验证，并连同标准输出接入新 35 包的来源验证。派生启动试验已越过这些反射缺口，推进到 JDK jimage 资源读取；完整 Main 仍未完成。[资源映射联合组件](docs/JIMAGE_NATIVE_MAP.md)已实际完成原库与类初始化、真实 CPU 能力查询、原 ByteBuffer 构造和映射 getInt，8 OS 线程的 512 次调用、4 轮静止 GC、JDK 对照与完整关闭均通过独立复跑。[原 Java 批量读取](docs/JIMAGE_JAVA_BULK.md)也通过了缺口对照和接入汇编实现后的 0 至 64 KiB、目标偏移与位置检查。[Inflater 数组接口](docs/INFLATER_NORMAL.md)已有独立内核验证；原构造／end 的三声明前缀也通过了真实 System123 和三后台线程清理。

Windows 文件元数据内核通过 JDK 对照，窗口调用桥通过无窗口契约测试；图形运行时和创建世界仍在实现。多核线程内核已有并发测试，游戏性能提升需要在完整启动后测量；自动／并发收集未实现。[Lambda 通用展开](docs/NORMAL_LAMBDA_EXPANSION.md)已在独立候选中执行原严格 Builder；当前单站点派生镜像的接线已通过机器验证，正式共享流程及当前游戏路径执行仍待验收。

v145 新增[正常 BootLoader 模块发布](docs/NORMAL_BOOTLOADER_MODULE.md)，正式原生初始化链已验收相应前缀。[ClassLoader 汇编实现](docs/CLASS_LOADER_ASSERTIONS.md)已作为第 23 包通过独立源选择、原 Java 冷初始化、八线程、真实堆耗尽及正常根图 GC 检查。动态模块／类加载、后续 VM 初始化和游戏启动仍未完成。

[可选并行汇编](docs/PARALLEL_DIAGNOSTIC_ASSEMBLY.md)已接通开发启动验证流程：23 组样本约 434 MB 初始化汇编拆成 48 个完整源单元，八个工作者的汇编阶段为 4.843 秒。该数字只衡量构建阶段；完整来源与链接校验另行执行，不代表游戏运行性能。[新增三组正式验证](docs/NATIVE_RUNTIME_26.md)覆盖四个引用操作、库名映射和受限库加载，包括原 Java 构造器、八线程及真实资源清理。

[捕获引用的 Lambda](docs/REFERENCE_CAPTURE_LAMBDAS.md)已通过独立组件验证；[四维字段命名空间](docs/UNSAFE_FIELD_NAMESPACE_SOURCE_API.md)守卫也已修正。[公开实例方法引用接口](docs/NORMAL_LAMBDA_INSTANCE_SOURCE_API.md)随后补上 class52041/CP90 的 `Set → Consumer`，四组实际组件验证合计 142 次报告调用，包含错误顺序、已有异常保护、闭包保活／释放和四个 OS 线程隔离。新的 266 对象镜像通过完整 PE 独立重链接；实际 Main 越过 CP90，25.469 秒后退出 86，全部资源清理通过，新停止点为同类 CP110 的 `PropertySource.getPropertyNames → Function`，尚缺其普通接口分派入口。[长期追加接口](docs/NORMAL_LAMBDA_APPEND_SOURCE_API.md)另已批量生成 1,796 个新站点，适配器、十组运行时元数据和容量／根引用整合已通过机器检查；完整批次尚未链接；独立的 `BiPredicate` 原类准入已通过完整来源及两组机器检查，尚未并入当前来源版本。Main 初始化、帮助输出、客户端和世界仍未完成。

后续 267 对象镜像已通过完整 PE 独立重链接，并加入按原接收者覆盖关系生成的 `PropertySource.getPropertyNames` 接口分派。独立 Function 组件通过 146 次报告调用和两次 pending 保护调用，包含四个真实 OS 线程及十六个新函数对象；实际功能接收者为 PropertiesPropertySource，其余三条分派行保留来源／机器证明。实际 Main 越过 CP110 工厂，停止于同方法 CP118 的 `Set.addAll → Consumer`，观察流程 35.031 秒、退出 86，资源清理和输入一致性检查通过。新的 27 类追加已通过字节码和调用适配器 COFF 校验，运行时元数据与整图接入仍在进行；这些结果均未记作游戏启动完成。详见[实例引用验证记录](docs/NORMAL_LAMBDA_INSTANCE_SOURCE_API.md#actual-function-execution-and-the-next-main-stop)。

首个目标版本为 Java 版 1.21.1，完成原版后再推进模组兼容。类加载器身份、变换链和优化失效边界提前纳入设计。启动器提供“启动游戏”入口，输入准备、翻译和构建由启动流程调用。

- [架构设计](docs/DESIGN.md)
- [自动翻译与原生启动进度](docs/AUTOMATIC_TRANSLATION.md)
- [实现与验证记录](docs/IMPLEMENTATION.md)
- [汇编进程入口](docs/NATIVE_VM_ENTRY.md)
- [窄字段原子操作](docs/NARROW_FIELD_ATOMICS.md) · [监视器等待](docs/MONITOR_WAIT.md)
- [Windows 文件查询](docs/WINDOWS_PATH_ATTRIBUTES.md) · [图形后端设计](docs/CLIENT_WINDOW_WIN64.md)

源码、构建脚本及自编测试位于本仓库。通过输入工具取得的游戏与 JDK 输入，以及编译产物，存放在本地被忽略的 `.boom`、`target` 和 `dist` 目录。

<details>
<summary>前期开发记录</summary>

v120 开发中：[汇编进程入口](docs/NATIVE_VM_ENTRY.md)已实际完成主线程构造，并在原生 EXE 中把原始 System.initPhase1 执行到 Signal.handle0；绑定数据和启动控制流均由汇编承担，PE 未导入 CLR／JVM／CRT，堆／注册表／帧清理通过。VM 线程 ID 原子地址域通过 32,768 次并发更新、销毁竞争和错误检查，新服务端批次完整 ASM／COFF 校验通过。原始 Java ThreadIdentifiers／Unsafe 链已实际分配并写入子线程 ID 2，主线程仍为 1、下一 ID 为 3；完整子线程构造停在 AccessController.getStackAccessControlContext。线程启动／退出、完整 System、游戏与世界仍未完成。

v119 开发中：[正常布局 Thread 与主线程引导](docs/NORMAL_THREAD_BOOTSTRAP.md)已接入第十组汇编提供者。修复既有 18 个运行时入口的导出后，原始 Thread 类初始化与 yield0 入口实际执行通过；8,192 次并发注册、18 个真实目标地址和 24,576 次调用通过。新增汇编引导已实际执行完整、未剪枝的原始 Thread／两个 ThreadGroup／ACC 构造器及嵌套 FieldHolder，核对主线程 ID 1、线程组关系和 RUNNABLE 状态。保留真实主线程继续执行原始 System.initPhase1，组合路径到达 Signal.handle0；堆／注册表清理成功且无锁遗留。开发宿主仍提供明确的 VM 绑定配置，普通线程启动／退出、完整 System 与游戏尚未完成。

v118 开发中：[正常 String 信号名称查询](docs/NORMAL_SIGNAL_LOOKUP.md)已接入第九组汇编提供者，实际 System.initPhase1 越过 findSignal0，推进至 handle0(IJ)J。[规范 Signal.class 锁](docs/NORMAL_CLASS_MONITORS.md)在原始 System 路径通过实际竞争、等待及释放验证，停止时无监视器遗留。信号传输绑定支持正常 TracePool ABI3，隔离运行时重建仅改变一个汇编源；501,044 条源帧元数据、19 项错误／生命周期检查及八工作者 16,384 次调用通过，测试回调仍为明确夹具。完整信号 Java 分发、Thread 引导、System 与游戏尚未完成。批量预选对照没有消除同前缀的迭代器停止，保留为默认关闭的开发实验。

v117 开发中：[正常 Class 监视器包装](docs/NORMAL_CLASS_MONITORS.md)已由自研后端统一生成并完成服务端重建。381 个原始静态同步包装使用规范 Class 对象，原始 Java 方法体保持逐字相同；完整服务端 ASM／COFF 和新增包装校验通过，Rust 202 项检查通过。新版服务端复用 943 项已有 Java 方法选择，实际 System.initPhase1 推进至 Signal.findSignal0；原先两侧旧批次也均自动到达此原生缺口。原始输出流专项保留五轮完成记录和 1,074 项 Java 准入，仍未完成；后续优先通过实际 System 路径验证规范 Class 锁。客户端重建、完整 System 和游戏仍未验收。

当前开发检查点 v116：自动后端已生成服务端 498,179／客户端 562,769 个普通 Java 方法的汇编，并完成实际 COFF 来源校验；这是方法生成覆盖，不能换算为游戏总体进度。完整 System、Minecraft 入口、世界及游戏侧多核／GPU／内存优化仍未完成，启动器继续只通过启动流程进行准备和编译。

v116 开发中：两侧上一轮 System 诊断各自动推进三轮，Java 准入增至 692，新的实际缺口为 ScopedMemoryAccess.registerNatives。[作用域内存注册](docs/NORMAL_SCOPED_MEMORY_BOOTSTRAP.md)与[正常异常回溯](docs/NORMAL_THROWABLE_BACKTRACE.md)两个新绑定已通过两侧来源／汇编／COFF 与原始 Java 执行测试：各八工作者冷初始化、8,192 次注册及 512 次原始 Java 异常构造／抛出和真实回溯；System 已越过注册进入缓冲区方法自动选择。完整会话关闭握手、公开栈帧物化、隐式异常工厂和游戏启动仍未完成。

v115 开发中：[正常文件与字符表示引导](docs/NORMAL_FILE_BOOTSTRAP.md)统一接入两个流、FileDescriptor 和 StringUTF16 字节序查询的六项原始 native。两侧来源／汇编／COFF、内核及原始入口测试通过；独立测试执行了四个原始类的冷初始化、三份标准描述符的原始 Java 构造与各 24,576 次并发调用，前置顺序与原始 System 一致。其他冷初始化顺序仍暴露正常 Class 监视器桥接缺口。实际 System 诊断已越过文件引导，正在自动选择字符编码器方法。现有五组提供者通过当前来源模型重新校验后复用原 ASM／COFF，旧包保持不变。[正常 Throwable 回溯内核](docs/NORMAL_THROWABLE_BACKTRACE.md)也已通过两侧布局／帧夹具测试，尚未绑定到源 native。完整异常、文件读写、System 和游戏仍未验收。

[native 栈帧数据扩展与入口适配](docs/NATIVE_FRAME_OVERLAY.md)已在两侧通过链接和实际冷反射回调验证。[构造器转换、正常堆拆箱及调用内核](docs/CONSTRUCTOR_INVOCATION.md)通过 456 项 JVM 参数对照；服务器进一步执行了 13 个原始 JDK 构造器现场，包括 175 项允许转换、281 项拒绝转换、实际冷初始化及八工作者 512 次并发构造。开发宿主仅提供 FFI 和明确夹具，游戏方法、转换、初始化和分配均执行汇编。

v114 已接入正常 Constructor 的原始 clazz／slot 选择与两个原始 `newInstance0` 入口。服务器 67,407／客户端 75,305 项构造器记录由同一规则自动建立目标索引，两侧通过来源、汇编、COFF 和接入闭包校验；服务器两个 native 入口通过了 13 个原始构造器、456 组参数对照及八工作者 512 次并发构造。实际 System 启动已进入 GBK 原始构造器的自动选择，正在继续推进。完整异常包装、System 和游戏启动仍未完成。

v111 的[正常布局构造器枚举](docs/NORMAL_CONSTRUCTORS.md)在两侧均通过 15 种类型、48 项构造器的 JVM 元数据对照，七个原始 getter、18 项错误检查及八工作者 512 次并发枚举测试。应用加载器／模块为明确夹具，未将元数据覆盖算作对应目标类构造或初始化已经执行。基础 Java ASM／COFF 未重生成。以下版本段落保留各检查点当时的范围。

实际 System 诊断增加原始反射前置初始化，修复诊断准备顺序造成的空引用；两侧各经四轮实际执行，Java 自动准入从 566 增至 634，均推进至未提供的 `Reflection.getClassAccessFlags(Class)`。这是原始类标志服务缺口；普通字节码翻译与完整运行时覆盖分别统计。以下版本段落保留各自检查点当时的范围。

v110 实现[独立汇编运行时提供者包](docs/RUNTIME_PROVIDER_PACKS.md)。新增 native 家族可单独生成、汇编、校验并接入现有批次；v109 两侧的 Java ASM／COFF 不重跑字节码生成，也不改写旧批次证明。首批 CDS 五项与 Object／System 身份散列两项已通过原版方法、错误路径和八工作者并发测试，Python 180 项测试通过。启动诊断已自动准备并使用提供者，两侧 System.initPhase1 均推进至反射构造器枚举 `Class.getDeclaredConstructors0`。完整 System、Minecraft、世界及游戏侧多核／GPU／内存优化仍未完成。

用户提出的[批量自动翻译方案](docs/AUTOMATIC_COMPLETION.md)采用通用字节码后端、共享语义规则和增量提供者：相同机制补一次，自动匹配所有已支持现场。Lambda／Record 的统一展开及完整玩家启动流程仍待实现；不能承诺剩余工作仅为少量兼容补丁。以下版本段落保留各检查点当时的验证范围。

v108 接入[正常 bootstrap 名字查找与初始化入口](docs/NORMAL_CLASS_LOOKUP.md)：共享规则生成两个源 native、约 3.5 万个名字及 16,913 个初始化入口。两侧全表查找、44 项原版公开 forName 的 JVM 对照、8 工作者冷初始化与 4,096 次并发查询通过；全表测试使用明确的模块准备输入，完整模块引导仍待完成。实际 System.initPhase1 经两轮自动准入 GBK 类的初始化依赖，越过 Class.forName0，新的语义前沿为 Reflection.getCallerClass。游戏启动、世界与游戏侧性能优化继续未完成。

v107 接入[Unsafe 堆内存与原子家族规则](docs/NORMAL_UNSAFE_MEMORY.md)：同一规则批量生成 42 项源 native，真实汇编服务提供字段／数组读写、volatile 和 CAS／exchange。两侧各通过 4,272 组 JVM 标量对照、24,576 次争用原子更新及原始 Java AtomicInteger 的 4,096 次并发自增。System.initPhase1 各经七轮自动选入 141 个已有 Java 方法，越过 CAS 后停在 Class.forName0 的正常类加载语义。堆外和静态基址等域仍保留缺口，完整 System、游戏启动及游戏侧性能优化仍未完成。

v106 接入[正常 Unsafe 字段定位与接收者地址映射](docs/NORMAL_UNSAFE_FIELDS.md)：一个共享汇编服务统一生成原始字段表，保留加载器和声明身份。两侧各通过 26,743 条字段查询、512 个地址夹具、16,384 次并发查询及原始 AtomicInteger 初始化／构造／getter。实际 System.initPhase1 经六轮自动选择越过字段定位，当前停在 Unsafe.compareAndSetInt；完整阶段、游戏启动及游戏侧性能优化仍未完成。

新增[正常调用栈与调用者查询](docs/NORMAL_CALLER.md)：批量 Java 方法统一生成汇编帧，直接核对原始注解和字节码位置；两侧完整来源／COFF 校验通过。内核夹具通过并发查询与实际大帧测试；原始启动进入 Reflection 初始化依赖后停在 CDS，原始调用者查询尚未执行完成，整版游戏尚未启动。

完善[规则驱动自动翻译方案](docs/AUTOMATIC_COMPLETION.md)：依据 v108 真实剩余请求，明确前置 Lambda／Record 展开、派生类型目录、增量任务图和验收顺序；一次规则覆盖全部匹配现场。现有批量后端和 [MASM 对象缓存](docs/ASSEMBLY_OBJECT_CACHE.md)继续复用，统一展开执行层及完整汇编运行时仍待实现，设计不计作游戏启动进展。

v104 接入[原始浮点位转换](docs/NORMAL_RAW_BITCASTS.md)：4 个 Float／Double native 共用纯整数汇编服务，保留 NaN 载荷和正负零。两侧各通过 8,236 组位模式、24,708 次顺序与 65,536 次并发调用。实际 System.initPhase1 越过该缺口，并自动选入 Character 的已有 Java 汇编，随后停在 Unsafe.objectFieldOffset1；完整 System、游戏启动和游戏性能优化仍未完成。

v103 接入[正常布局 Runtime 资源查询](docs/NORMAL_RUNTIME_RESOURCES.md)：两侧原始 Runtime 初始化与私有构造器通过，4 项原生接口读取实际堆容量／占用及 Windows 处理器亲和性。两侧各通过 32,768 次并发查询、3 种亲和性 JVM 对照、显式回收计数与 15 项错误检查。System.initPhase1 已越过 maxMemory，当前停在 Float.floatToRawIntBits；完整阶段、游戏启动和游戏性能优化仍未完成。

v102 接入[原始 VM 注册与时间调整服务](docs/NORMAL_VM_REGISTRATION.md)：两侧原始 VM 初始化器、8 线程注册／时间调用及旧 ABI 回归通过。跨批次核对源码后复用 226 个已执行类中的 Java 方法选择记录；旧批次对照从四轮减少到一轮且保留原缺口。新批次已越过 VM.initialize，实际停在 Runtime.maxMemory；完整 System 阶段、游戏与世界仍未启动。

v101 接入[正常布局 Unsafe 基础服务](docs/NORMAL_UNSAFE_BOOTSTRAP.md)：两侧原始 Unsafe／UnsafeConstants 初始化器已实际执行通过，完成注册、数组布局查询、平台常量注入和汇编内存屏障。两侧各通过 8 线程冷初始化及 16,384 次并发调用。System.initPhase1 经四轮实际选择越过 Unsafe，目前停在 VM.initialize 的原生注册缺口；完整 System 阶段、游戏启动、世界创建和游戏性能优化仍未完成。

v100 新增[实际启动路径自动选择](docs/DIAGNOSTIC_STARTUP.md)：复用已验证汇编，按真正执行到的目标自动选入已有 Java 方法，并明确停在尚需实现的运行时接口。无需为每个普通 Java 方法人工添加桥接；不能从没有 Java 方法体的原生声明中自动推导平台语义。

v99 已通过共享规则接入[Class 基础引导](docs/NORMAL_CLASS_BOOTSTRAP.md)，在两侧实际运行原始 Class 初始化器和七个包装类初始化器，支持基础类型镜像及默认断言查询。Class 完整原生注册、模块／System 引导和完整游戏仍未完成；没有更新可启动发布状态。

BoomMinecraft 的主路线是**自研 Java 字节码到汇编的编译器**。首版目标保持 Minecraft Java 版 1.21.1：先验证受限语言子集，逐步覆盖完整原版，再实现模组兼容。

最新开发进展 v97：正常源布局的两项 `SystemProps.Raw` 属性 native 已批量接通汇编服务，两侧原始 Raw 构造器、getter 和正常 String[] 已实际执行。每侧通过 39 项 JVM 平台属性对照、13 对 VM 配置、41 次原始 Java 调用、8 个测试工作者的 8,200 次并发调用，以及 OOM／显式回收后恢复。完整批量校验通过；异常池未绑定时的空地址读取也已修复，但正常批量映像的完整 Throwable 物化仍待接入，详见[属性协议与范围](docs/NORMAL_PROPERTIES.md)。此前 Class／String.intern 验证继续保留。完整 System、游戏启动、世界与自动回收仍未完成，dist 保持 v70。

已发布检查点仍为 `program-v70`。游戏运行时最近的功能检查点 `program-v81` 已加入 ClassValue 的按类引用缓存桥接和 Shutdown 汇编退出绑定，原始缓存读取与退出监视器路径已实际执行并完成 JVM 对照、多线程和隔离子进程验证。此前的实例字段原子操作、字符复制、类名缓存和启动类查找保持已有验证范围。旧执行链接器的系统启动发现前沿仍在 ModuleLayer.modules；批量后端已能生成其原始 Java 方法的候选汇编，**完整系统阶段、Minecraft 启动与世界创建仍未完成**。启动器继续只有启动入口。

当前主线为[全量批量翻译流水线](docs/TRANSLATION_PIPELINE.md)。`boom prepare-jdk-classes` 提供原始默认系统模块类；`boom plan-translation` 索引锁定输入；`boom lower-translation` 生成可校验、复用或重建的符号 IR；`boom compile-translation` 统一校验操作数、解析成员和候选布局，按完整方法拆成约 8 MiB 汇编体的单元，并行生成 MASM 与真实 AMD64 COFF。失败按原因汇总，其他方法继续编译，不再为每个普通 Java 方法人工添加桥接。**批量对象尚未完成运行时适配与最终链接**；生成方法数不能当作游戏完成进度，8 个编译工作线程也不算游戏运行中的多核优化。

v85 实测：服务器 498,179 个方法生成汇编，832/832 单元汇编成功，耗时 105.776 秒；客户端 562,769 个方法生成汇编，904/904 单元成功，耗时 103.796 秒。来源、完整覆盖、COFF 与拆分前后方法体字节保持校验通过。剩余缺少定义的方法为 727/1,001；在相同旧输入方法中，分别比 v84 多通过 1,076/2,522 个，没有汇编生成回归。成功生成的方法仍有待实现的运行时绑定，两侧输入大量重叠，不能相加或据此推算游戏启动进度。

v86 已将源字符串批量接到真实汇编工厂：两侧分别生成 1,041,357/1,068,081 个解析接口，去重为 358,555/374,760 条内容，采用原始 String Java 字段布局。完整常量模块通过独立来源、数据和 COFF 校验，并在汇编堆上逐项与 JVM 对照；原版 String.value()、String.isEmpty() 的两个翻译方法体已实际执行。尚未完成一般 String.intern、String 类初始化或整个游戏运行时；[实现与验证记录](docs/IMPLEMENTATION.md) 保留确切范围。

v87 增加按源层次与布局生成的类型、对象形状和继承字段地址模块，汇编运行时提供大表索引。两侧分别生成 109,803/123,477 个类型描述符、101,598/117,324 个字段解析函数；104,059/117,018 种对象或数组物理形状与 305,429/338,217 个字段地址已实际验证。另通过八种原版包装类构造器及取值方法体的 JVM 对照；完整类初始化、静态状态、分派、反射与游戏启动仍未完成。物理形状测试不等于执行对应类的 Java 构造器或初始化器。

v88 新增静态存储和类初始化生成器：两侧为 53,589/60,195 个有效类生成状态描述符，覆盖 92,116/119,182 个静态字段；初值为零，ConstantValue 在实际初始化时赋值。自动依赖选择已从批量汇编中链接并运行六个 JDK 枚举与四个常量类，验证原始构造器、初始化器、34 个常量和静态图的根保持。完整批次仍未最终链接，新链路的 System 类初始化目前停在尚未绑定的 registerNatives；不代表 Minecraft 已启动。

v89 接入[自动翻译与兼容收敛程序](docs/AUTOMATIC_TRANSLATION.md)：一个开发命令完成批量生成、汇编、独立校验、缓存检查与兼容清单。通用虚调用／接口选择规则已自动生成服务器 321,711、客户端 358,825 个适配器，分别复用 107,909/119,555 张选择表；新增单元全部汇编且独立来源校验通过。候选对象未解析符号从 373,848/418,531 降为 52,499/60,127，剩余协议按影响范围归组。实际执行测试验证选定 ByteBuffer 原始 getter 的汇编分派；没有把全输入的接口选择表校验当成全部接口执行，也没有将这些结果当成游戏启动。

新增[协议展开层设计与真实输入预检](docs/AUTOMATIC_COMPLETION.md#下一层先展开机制再批量编译2026-11-25)，规划 Lambda、拼接和 Record 的通用展开。v98 已实际实现[正常 String 拼接规则](docs/NORMAL_STRING_CONCAT.md)，为服务端／客户端自动生成 9,991／10,387 个真实汇编适配器，并完成内核与准备夹具中的适配器执行验证。完整原始引导仍未执行；其他协议展开及方法级增量机器码缓存仍待实现，结构预检不计作执行完成。

v90 继续按共享协议批量生成数组 clone：服务器 2,691、客户端 3,050 个现场全部通过源类型、MASM、COFF 和实际执行验证，覆盖 1,291/1,589 种符号数组类型。协变类型、浅拷贝、8 线程复制、OOM 和静止回收检查通过，六个原始 JDK 枚举的 `values()` 也已走通自动生成入口。候选未解析符号降为 49,809/57,078；新增断点续验可复用相同编译器、输入锁和 IR 的产物。System 启动、Minecraft 和世界仍未完成。

v91 已实际执行原始 System 类初始化：生成四个源原生声明的入口，由原始 `<clinit>` 调用真实汇编注册逻辑，原子发布时钟与数组复制三个服务。两侧 600 组数组复制 JVM 对照、8 线程冷初始化／时钟与重叠复制通过。通用闭包选择器支持指定类／方法，并一次收集下一阶段已发现的缺口。**完整 System initPhase1/2/3、Minecraft 和世界仍未运行**；类初始化成功不是完整游戏启动。

v92 将同一批量规则扩展到 System 的三个标准流 setter，直接更新源 `in/out/err` 静态根，并检查源类型与堆归属。两侧分别验证 180／239 种具体接收者形状、8 线程 8,192 次无分配发布，以及原始 ByteArrayInputStream 构造、读取、重置方法和同步监视器回收。输入流类初始化、输出流构造及文件／控制台 I/O 尚未执行；完整游戏仍未启动。

v93 让通用入口闭包自动展开已生成的虚调用／接口表，纳入完整接收者行和目标方法；未绑定 native 与未知动态目标继续明确报告。选定 ByteBuffer 调用已通过两侧自动选择、独立校验和 8 线程执行。新增函数、类描述符和分派数据的位置索引，同一 System 直接扫描耗时 7.838 秒；全行扫描选入 327,096 个 Java 方法及 219,613 个调用现场，用时 597.487 秒，前沿逐项与优化前一致。25,532 个候选前沿归为 396 组，Class／Lambda／字符串拼接／record 四类规则涉及 23,310 个现场。保守展开包含可选实现，分组不是启动必经任务数量；完整游戏仍未启动。

当前自研后端已经实现：

```text
真实 .class 文件
  → 自研常量池与方法解析
  → 自研类型验证、数值指令解码与控制流检查
  → 生成可读的 x86-64 MASM 汇编
  → ml64 汇编为 COFF 对象文件
  → link 链接为原生 DLL
  → 汇编运行时 / 独立汇编 EXE / 开发测试宿主
```

这条链路不使用 GraalVM 生成代码，也不从 EXE 反汇编来冒充编译输出。执行生成的方法时不需要 JVM；JVM 仅作为对照结果的参考。

**完整 Minecraft 尚未编译成功。** 当前支持 `i32-v2`、I/J/F/D 数值、一维基本数组、单类对象子集、`program-v3` 的跨类具名对象与静态状态，`program-v4` 的汇编字符串字面量池、`program-v5` 的来源校验类镜像，`program-v6` 的动态字符串拼接与内容驻留，`program-v7` 的运行时类型检查与 getClass，`program-v8` 的封闭输入接口分派、默认方法和接口初始化依赖，`program-v9` 的应用类继承、字段映射、父类构造与引用数组协变检查，`program-v10` 的紧凑标量字段布局和汇编窄宽度读写，`program-v11` 的来源校验 java.base Java 方法执行，`program-v12` 的汇编 volatile 字段与排序，`program-v13` 的冻结启动断言策略，`program-v14` 的来源校验 VM 时钟绑定，`program-v15` 的模块身份服务，`program-v16` 的冻结启动模块层查询，`program-v17` 的标准 lambda、方法引用与无捕获对象复用，以及 `program-v18` 的汇编同步方法和对象监视器。仍缺完整类链接、完整 String 转换和反射、通用数组语义、安全点/栈映射、完整异常、标准库执行及图形集成。

新增 `program-v19`：冻结资源目录、`Class.getResourceAsStream` 汇编查找与校验，以及原始 JDK ByteArrayInputStream 执行。已从锁定原版 JAR 读取真实 `version.json`；这不代表主入口或完整 IO 已完成。

新增 `program-v20`：来源校验的 `Class.getPrimitiveClass` 汇编绑定，执行原始 JDK 九种包装类的 TYPE 初始化，基本类型和 void 共享实际 Class 镜像身份。完整 System 启动和一般反射仍待实现。

新增 `program-v21`：汇编 `System.arraycopy`，以及由原始 System 类初始化器调用的 native 注册表。覆盖基本数组、引用协变、重叠和部分复制失败；三个已注册方法实际经表分派。System 的属性、标准流和后续 Java 启动阶段仍未完成。

新增 `program-v22`：来源校验的两个 `String.join` 重载，连接与临时向量由汇编实现，CharSequence 和迭代器回调进入自研后端生成的方法。字符串可作为真正的 CharSequence 接收者参与分派；分派 ABI2 保留被调用方法的异常位置。完整原版仍未启动。

新增 `program-v23`：来源校验的 `String.valueOf(char/int/long/boolean)`。字符及十进制格式化复用汇编拼接服务，布尔值保留原始 JDK 字面量身份。分发版本通过 811 组 JVM 对照、1622 次原生执行及 8 个汇编工作者的 12294 条记录；服务器入口已推进到 CDS 归档初始化服务。

新增 `program-v24`：汇编实现冻结的无 CDS 归档配置，原始 CDS 类初始化器继续由自研后端执行。分发版本通过 460 组 JVM 对照、920 次原生执行和 8 个汇编工作者的 6147 条记录，核对初始化生成的数组内容、目标类初始化边界及预热后的零新增 guest 分配。尚不支持载入或生成 HotSpot 共享归档。

新增 `program-v25`：Integer.toString(int) 和 Long.toString(long) 使用汇编十进制格式化，并先执行原始包装类初始化器；String.valueOf 的整数委托也保留这项初始化义务。已通过 1162 组 JVM 对照、2324 次原生执行及 8 个汇编工作者的 36882 条记录。服务器依赖发现已推进到标准流所需的 System 启动阶段，完整原版仍未启动。

新增 `program-v26`：执行原始 FileDescriptor 初始化、SharedSecrets 登记和 Windows 标准句柄查询，汇编实现字段表登记及字节读写/刷新服务；补齐基于加载器、运行时包及双向属性的 nest 私有访问校验。已验证 1 MiB 文件数据和 6147 条八线程追加记录。完整 FileInputStream/FileOutputStream Java 链路及 System 应用启动仍未完成。

新增 `program-v27`：原始 SharedSecrets 延迟 getter 现在能够通过来源和控制流证明的 Class 常量触发原始初始化器。两个入口通过 230 组 JVM 对照、460 次原生执行及 12294 条八线程记录；检查单次初始化、私有描述符 getter、静态对象存活及 OOM 后的持久失败。完整流构造仍缺少各自的 initIDs 等绑定，不表示一般 MethodHandles 或完整游戏已可用。

新增 `program-v28`：以汇编实现输入流和输出流的 initIDs 字段登记，并实际执行两个原始 Java 类初始化器。绑定选择翻译后布局中的真实 fd 引用槽，服务读取该表，保留冷启动、并发和失败状态；完整流构造及 Java 读写包装仍待接通。

新增 `program-v29`：实际执行原始 Throwable 构造链、cause 和静态哨兵初始化，汇编捕获生成方法的真实堆栈。通过 1265 组 JVM 对照、70 份方法/文件/行号快照和 6147 条八线程记录。帧节点位于本机方法栈，嵌套调用复用上下文租约；完整异常传递、catch/finally 及 Java StackTraceElement 数组仍待接通。

新增 `program-v30`：接通 Context32、真实异常对象、athrow、顺序 catch、重抛、finally 和 monitorenter/monitorexit；VM 隐式异常使用原始 JDK 类型与字段，Java 创建的异常仍执行原始构造链。24 个入口通过 4422 次 JVM 差分、39 份真实堆栈对照和 12294 条八线程记录。验证初始化失败 cause 的静态根、等待者唤醒，以及堆完全耗尽时无分配捕获 OOM。外部 Context16 入口通过有边界的桥接保留兼容；Java StackTraceElement 数组、精确活动根与自动回收仍待实现，完整游戏尚未启动。

新增 `program-v31`：以汇编实现 Unicode 15.0 简单大小写比较、码点 indexOf 和 UTF-16 substring。全部 1114112 个码点的上下映射与锁定 Java 21 一致；15 个入口通过 8136 组 JVM 对照、16272 次原生调用及 6147 条八线程记录。预热后的比较不分配 guest 对象，截取保留完整范围与空字符串身份并通过 OOM 恢复检查。Locale 初始化发现已推进到 System.getProperties；完整 Locale 大小写转换与 System 启动仍未完成。

新增 `program-v32/v33`：VM 构造器入口用汇编分配真实对象、执行原始类初始化和构造链；原始 SystemProps.Raw 私有构造器现已实际执行。Windows 平台属性由汇编查询并生成其真实 String[]，39 项与 JVM 一致，另通过 29 组构造器对照和 6147 条八线程记录。缓存受堆预算和静态根保护，每次构造返回独立数组，OOM 后可以重试。完整 VM 属性、System 启动和游戏入口仍未完成。

新增 `program-v34`：来源校验的原版 `String.concat(String)` 由汇编执行。空后缀返回原对象且零分配；空接收者拼接非空后缀仅分配新 String、共享不可变字符数组；其他路径复制原始 UTF-16。12 个入口通过 2233 组 JVM 对照、4466 次原生对照与 6147 条八线程记录，另检查分配预算、满堆与分配中途 OOM、回收和恢复。System 属性初始化的下一处发现缺口为 `String.valueOf(Object)`；完整游戏仍未启动。

新增 `program-v35`：汇编实现 System 身份哈希和 Object 默认 hashCode，保留子类覆写、super、接口及同步方法选择，String 内容哈希不变。17 个入口通过 3712 组 Java 关系对照及 6147 条八线程记录；另验证 GC 前后稳定、数组/类镜像/模块身份和满堆零分配。当前实现依赖非移动堆；对象字符串转换和完整游戏仍未完成。

新增 `program-v36`：汇编实现 Integer/Long 的十六进制字符串转换，校验原始 shift=4 委托并执行实际类初始化。8580 组输出逐字符对照、848 组关系对照及 6147 条八线程记录通过，另覆盖分配预算、满堆和中途 OOM 后恢复。默认 Object.toString 仍需要 StringBuilder 的字符串存储接口，完整游戏尚未启动。

新增 `program-v37`：接通 UTF-16 字节序状态、可变 builder 到不可变 String 的复制边界、原始浮点位转换和受来源校验的 JDK Java 方法桥。Class.toString 的原版字节码已实际执行；2144 组 JVM 对照和 6147 条八线程记录通过。复制边界测试使用虚拟机准备的有效输入；原始 StringBuilder 构造/追加及完整游戏仍未完成。

新增 `program-v38`：汇编实现原始 Raw.vmProperties 的冻结配置接口，生成独立的键值 String[]，保留终止 null 键。原生映像路径、库路径、类路径及自定义属性参与缓存身份；热调用只分配一个结果数组。384 次分配预算和 6147 条八线程记录通过，并检查满堆及部分分配失败后的恢复。原版属性初始化的依赖发现已推进到 Class.descriptorString 反射依赖；完整 System 和游戏仍未完成。

新增 `program-v39`：原始 Class.componentType Java 方法实际翻译执行，私有 componentType 字段通过来源校验映射到 VM 镜像元数据；补充当前具名类型集合的 Class.isHidden 汇编查询。1632 组 JVM 对照、3264 次原生对照和 6147 条八线程记录通过，并验证满堆零分配、伪造镜像拒绝及目标类保持未初始化。完整 descriptorString 的依赖发现推进到 String.replace(char,char)，隐藏类定义和完整游戏仍未完成。

新增 `program-v40`：汇编实现 String.replace(char,char)，覆盖全部 65536 个 UTF-16 单元，合计 66217 组完整输出对照、4320 组数值/身份对照和 6147 条八线程记录。相同字符、未匹配和空输入路径保留原对象且零分配，发生替换时创建独立 String/字符数组；满堆及分配中途失败后恢复通过。另修复 String.concat 对堆末尾合法零长度字符数组的所有权误判。原版属性初始化的依赖发现继续推进到 Preconditions 的 String.format；完整游戏仍未启动。

新增 `program-v41`：数组 `clone` 的所有者按数组类型链接，汇编保留实际运行时类型，分配一个新数组并浅拷贝内容。8 种基本数组及 String/Class/Object 引用数组通过 1600 组 JVM 对照、32768 个原始浮点位模式和 6147 条八线程记录；空数组身份、协变类型、满堆异常和回收保活通过。原始 descriptorString 的依赖发现越过 Wrapper[].clone，推进到 String.format；Wrapper.values 的完整执行和游戏启动仍未完成。

新增 `program-v42`：补齐跨包 protected 父类构造访问，在编译时验证父类链、类可访问性和构造器接收者。原始 Enum 构造器、自定义枚举的 values/clone、匿名子类和两级跨包继承通过 1360 组 JVM 对照、2720 次原生对照及 6147 条八线程记录；四类非法访问同时被本后端和 JVM 拒绝。普通 protected 字段/方法与完整标准库仍待接通。

新增 `program-v43`：执行原始 VM 类初始化，汇编注册并实现 getNanoTimeAdjustment；20126 个精确算术向量、时钟区间检查、私有调用拒绝及 6147 条八线程记录通过。String.format 两个重载的原始方法桥已生成并核对，依赖发现越过 VM.initialize，推进到 CharacterData00 的多维字符数组；完整格式化和原版启动仍未完成。VM 启动级别保持 0，没有将原生注册记作 System 启动完成。

新增 `program-v44`：支持完整多维描述符、数组组件的 anewarray 和 multianewarray，分配与访问均由汇编执行。12 个入口通过 4080 组 JVM 对照、8160 次原生对照和 6147 条八线程记录；覆盖 255 维、部分维度、零长度后仍检查负长度、协变/浅克隆、部分 OOM 回收与恢复。原版依赖发现越过 CharacterData00 的多维描述符，推进到 String.toCharArray；完整原版仍未启动。

新增 `program-v45`：汇编实现来源校验 String.toCharArray，每次分配独立 char[]，空字符串、NUL 和代理项均保留语义。65961 组 UTF16 及 2240 组数值 JVM 对照通过。原始 Character.getType 的 56 个方法实际翻译执行，覆盖全部 1114112 个 Unicode 码位及 520 个整数边界/随机值，9 个原始字符数据类完成初始化，原始多维 charMap 与 JVM 一致；另外通过满堆、静止回收及 6147 条八线程冷启动记录。完整原版仍未启动，当前属性/格式化依赖停在实际 System 启动阶段。

新增 `program-v46`：为原始 System.initPhase1 建立独立 VM 调用上下文，并以汇编实现 private native setIn0/setOut0/setErr0，发布到实际的标准流静态根槽。支持 null、类型与堆所有权检查、无分配写入及静止回收。存储视图测试不等于标准流构造或 IO 完成；阶段 1 仍需继续覆盖 VersionProps 等依赖，普通应用和后续启动阶段的限制保持有效。

新增 `program-v47`：保留原始 startsWith(String)/endsWith(String) 包装方法，由自研后端编译；带偏移的比较使用汇编 SSE2，并处理标量尾部和空范围。71401 组 JVM 对照、142802 次原生调用及不可访问页边界检查通过，覆盖全部 UTF16 单元。原始 VersionProps 类初始化和构造器已实际编译执行，17 个静态字段与 JVM 对照通过。System 阶段 1 的依赖发现继续到 Signal.findSignal0；完整原版仍未启动。

新增信号名称查询服务：`signals.asm` 按锁定 JDK 的 Windows 表处理七个名称，完成 524288 组原始 UTF16 对照和 6147 条八线程查询，查询不分配游戏堆内存。本轮只验证原始 VM 服务和字符串生产方法，未执行 Signal 的 Java 方法或初始化器，也未安装或投递信号处理器。System 阶段 1 的依赖发现现停在 Signal.handle0；完整游戏仍未启动。

新增 Windows 信号传输层：`signal_control.asm` 实现注册与旧处理器恢复、原生计数队列、独立分发线程和关闭等待。在独立隐藏控制台中已验证真实 Ctrl-C/Ctrl-Break，4096 组 JVM 注册对照及八线程并发检查通过。原始 Signal.dispatch 和 Java 线程生命周期尚未接入，Signal.handle0 的游戏绑定仍拒绝编译，完整原版尚未启动。

新增汇编线程登记核心：原生创建的线程可执行自研后端生成的 Java 任务，保留各自当前引用、结果与异常，并在退出后显式释放记录。64 组任务与 JVM 对照通过，线程根冻结与回收边界完成验证。原始系统 ThreadGroup 的构造器和类初始化器也已实际执行；原始 Thread 的绑定、活动栈安全点和完整游戏启动仍未完成。

新增 `program-v51`：实际翻译执行原始 Thread 类初始化器，连接来源校验的 native 表，并将 `currentThread()` 调用接入汇编线程登记。八线程的 1536 次调用保持各自引用身份，未附着、已脱离及错误类型被拒绝。当前仅实现表中 18 项的 4 项；对象仍是 VM 引导阶段的预构造存储，原始 Thread 构造、start/run/exit、活动栈安全点和完整游戏启动均未完成。

新增 `program-v52`：原始 Unsafe 初始化器、构造器和 getUnsafe 已实际执行，VM 注入硬件常量，数组偏移使用本项目布局。保留原始 getAndAddLong/弱 CAS Java 循环，由汇编提供 long[] 和线程计数器的读取/CAS；1024 组 JVM 对照、6147 次八线程争用加一通过。原始 ThreadIdentifiers 初始化和编号分配也已执行，与 VM 共用计数器，6147 个并发编号无重复。当前只接入 68 项 native 声明中的 5 项，完整 Thread 生命周期和游戏启动仍未完成。

**游戏逻辑、游戏运行时和游戏侧优化全部使用汇编。** 翻译器使用 Rust，启动器使用 C#；它们不承担游戏逻辑的执行。运行时位于 `native/runtime`，现有 62 个 MASM 源文件，新增 Locale 相关小写转换、词边界状态机和 Unicode 上下文查询。Unicode 数据通知随分发文件提供。

新增 `program-v53`：原始 Thread.run/runWith、scopedValueBindings 和 Reference 初始化/reachabilityFence 已实际执行，Runnable 调用进入自研后端生成的方法。512 组 JVM 对照和 6147 次八线程调用通过。当前验证仍使用 VM 预构造的 Thread/FieldHolder 存储，完整线程构造、start0、exit 和游戏启动尚未完成。

新增 `program-v54`：通过明确的 VM 引导入口执行原始 Thread 构造器的附着路径，FieldHolder、系统 ThreadGroup 和引导访问上下文也经过原始 Java 构造器。主线程编号、名称、字段、当前身份与静止回收验证通过。该入口需要 `--vm-primordial-thread`，保留八个条件检查；普通 `new Thread` 仍走原始完整路径，不套用引导特例。一般线程构造、start0/exit 和完整游戏启动仍待完成。

新增 `program-v55`：汇编访问上下文服务连接保护域、影子帧和当前线程，补充调用者身份协议；栈/特权边界目前使用 VM 帧夹具验证。20 参数调用和字符串查找/原始 contains 通过 3815 组 JVM 对照。普通 Thread 构造已推进到 System 属性启动阶段，完整原版仍未启动。

新增 `program-v56`：连接 Signal.handle0/raise0 的活动 Windows 汇编传输，新增真实 SetErrorMode 调用。VM 协议和 Windows native 对照通过，原始 System 阶段 1 已推进到 Class.getClassLoader；Java 信号分发、完整 System 阶段与游戏启动仍未完成。

内存管理不照搬 HotSpot GC。必须保留 Java 对象的可达性与引用语义；当前汇编堆提供预算、紧凑字段布局及修改者静止时的显式标记清扫。安全点、精确活动根、自动回收与线程本地分配仍待实现，尚无整游戏内存或停顿改善的证据。

- [设计与阶段安排](docs/DESIGN.md)
- [实现与验证记录](docs/IMPLEMENTATION.md)

</details>

## 启动器

```powershell
python scripts/build-launcher.py --root . --output dist/launcher --target-dir .boom/launcher-cargo `
  --cargo "<cargo.exe>" --rustc "<rustc.exe>" --csc "<csc.exe>" --javac "<javac.exe>" `
  --assembler "<ml64.exe>" --linker "<link.exe>" --dumpbin "<dumpbin.exe>" `
  --sdk-lib "<Windows-SDK/Lib/version/um/x64>" --recipe native-config/assembly-runtime-build.json
.\dist\launcher\BoomLauncher.exe
```

将尖括号中的占位内容替换为本机已安装工具的绝对路径，SDK 路径指向对应版本的 `um/x64` 目录。

提供者工具清单改用 Python 会形成新的来源 epoch，即使清单项数仍为 117。旧 35 包和旧 Main 回执保留原有范围，当前源码树需重新完成对应验证后才能记为 current。

启动器只提供游戏设置、启动、停止和日志。翻译、编译、校验等工作属于启动流程，不提供编译或测试按钮。开发命令仅保留在下文。

**当前启动器不能启动完整游戏。** `play` 入口会在预检时明确报告缺少的执行能力，尚未实现完整自动构建及游戏启动，不会下载大量输入后伪装启动成功，也不会切换到 JVM。界面后续验证不使用 Computer Use；构建后的启动器支持 `--self-test --workspace <项目目录>`，可在不打开界面的情况下检查启动参数。

## 工具

使用 Windows x86-64、Rust 1.88 以上、Java 21 和 MSVC x64 工具。当前使用已有的 `D:\Dev\Java\jdk-21` 以及 `D:\Dev\VS2022` 下的 `ml64.exe`、`link.exe`。

**新工具统一放在 `D:\Dev`。** 项目缓存和编译结果放在被 Git 忽略的 `.boom` 中。MSVC 环境只设置在构建子进程中，不修改全局环境变量。

## 运行自研编译器

```powershell
cargo build --release --locked

New-Item -ItemType Directory -Force .boom/demo/classes | Out-Null
& 'D:\Dev\Java\jdk-21\bin\javac.exe' --release 21 -d .boom/demo/classes java/subset/dev/boom/subset/IntKernels.java

.\target\release\boom.exe compile-asm --class-file .boom/demo/classes/dev/boom/subset/IntKernels.class --method mix --output .boom/demo/mix --assemble
.\target\release\boom.exe execute-asm --manifest .boom/demo/mix/compilation.json --arg 7 --arg=-3
```

最后一条命令应返回 `{"result":-39}`。可直接打开 `.boom/demo/mix/method.asm` 检查生成的汇编。

`compile-asm` 总是写出汇编；增加 `--assemble` 后，才使用 MASM 和链接器生成 `method.obj` 与 `method.dll`。同时生成的 `compilation.json` 记录输入、汇编和 DLL 的身份。`execute-asm` 会检查产物哈希与参数数量。

重载方法需要通过 `--descriptor '(II)I'` 等描述符指定。编译结果包含选定静态入口和所需同类方法，还不是完整类或应用程序。

## 当前子集

支持零到四个 `int` 参数、返回 `int` 的静态方法，包含整数常量、局部变量、加减乘、取负、位运算、三种移位、条件跳转、循环、`iinc`、`switch`、同类非递归静态调用和对应的 `wide` 形式。

当前要求普通 `Object` 子类，没有字段、接口或 `<clinit>`，方法没有同步和异常处理。未支持的指令明确报错。除法、对象、数组、跨类或递归调用等不会被静默忽略或交给其他编译器兜底。

## 验证

```powershell
cargo fmt --all -- --check
cargo clippy --all-targets --locked -- -D warnings
cargo test --all-targets --locked
.\scripts\Test-AsmCompiler.ps1
.\scripts\Test-MinecraftAsm.ps1
.\scripts\Test-AssemblyRuntime.ps1
.\scripts\Test-ManagedCompiler.ps1
.\scripts\Test-AssemblyHeap.ps1
.\scripts\Test-AssemblyArrays.ps1
.\scripts\Test-ArrayCompiler.ps1
```

真实 JVM 与原生汇编产物的对照覆盖 16 个方法、1057 组输入，包含整数溢出、最小负数、负移位计数、分支、循环、两种 switch、同类调用、宽 `iinc` 和四参数 ABI；另检查 7 类未支持的方法被拒绝。测试驱动将每次原生执行放在独立进程中并设置超时。该运行器用于测试编译器生成的代码，不是安全沙箱。

原版输入测试还从未修改的 Minecraft 1.21.1 JAR 提取 6 个 `FastColor.ARGB32` 方法，经自研汇编链执行，72 组结果与 JVM 一致。该测试需要准备好的服务器输入锁，只证明这些方法的子集兼容。

新增数值后端覆盖 41 个样例方法、3784 组 JVM 差分；每组分别在正常与截断/FTZ/DAZ 调用环境下执行，共 7568 次原生调用，验证正确的浮点结果和调用方状态恢复。基本数组另有 16 个方法、784 组输入、1568 次原生执行通过。已锁定服务器输入中的 38 个方法（包括原版和依赖）还通过 1824 组差分。Rust 当前单元与集成检查共 133 项通过。

客户端输入的早期数值扫描有 43 个方法通过 2064 组对照。加入基本数组、对象和窄整数/void 描述符后，重新扫描 34575 个类、71559 个静态候选，153 个方法成功汇编链接；这 153 个方法并未全部做差分。原版角度插值使用有界有限角度测试，避免原方法本身对极大输入不收敛；具体范围保存在报告中。没有执行需要登录会话的客户端启动。

## 数值后端开发命令

`compile-managed` 编译 I/J/F/D 方法，采用 Context16/参数位数组 ABI，和 `compile-asm` 的直接四整数 ABI 不同。`execute-managed` 仅为诊断宿主，参数使用原始十六进制位；真正执行的算术、转换、调用与异常传播均在汇编 DLL 中。

```powershell
.\target\release\boom.exe compile-managed --class-file .boom/numeric-tests/<运行编号>/classes/dev/boom/subset/NumericKernels.class --method longDiv --output .boom/demo-numeric/longDiv --assemble
.\target\release\boom.exe execute-managed --manifest .boom/demo-numeric/longDiv/compilation.json --arg-bits 8000000000000000 --arg-bits ffffffffffffffff
.\target\release\boom.exe compile-set --lock .boom/locks/server.json --output .boom/parallel-compile/server-numeric-v1 --jobs 8 --assemble --numeric
.\scripts\Test-LockedNumeric.ps1
```

当前上下文可以传播未捕获的整数除零及基本数组异常类别和位置，未提供真实 Throwable 对象、捕获处理或 Java 栈展开。浮点取余和其他未支持指令继续明确拒绝。

基本数组模块通过 `boom_bind_heap` 绑定版本匹配的汇编堆，包含数组长度、元素类型、空值、边界和负长度检查。诊断用 `execute-managed` 会拒绝需要堆的模块和任意原生引用参数；使用专门的堆宿主测试或完全汇编引导程序运行它们。Java 方法执行中的自动 GC 尚未提供。

## 多核汇编运行时与离线编译

`native/runtime/parallel.asm` 使用 1 到 64 个工作者，原子分配 64 条一组的独立输入，调用线程参与执行并保持输出顺序。65,539 条输入在 1、2、4、8 工作者下全部一致，另检查参数、重叠缓冲和重复调用。尚未接入游戏 tick，不能据此宣称游戏 FPS 已提高。

构建启动器时还会生成开发用 `dist/native/boom-native-probe.exe`。这个独立 EXE 的入口、调度器和计算内核全是汇编，只导入 Windows `KERNEL32.dll`，无需 Rust、C#、JVM 或 CRT 执行宿主。

```powershell
.\dist\native\boom-native-probe.exe
.\target\release\boom.exe compile-set --lock .boom/locks/server.json --output .boom/parallel-compile/server --jobs 8 --assemble
```

批量编译已扫描 27,956 个类，在 438 个候选整数静态方法中生成并链接 23 个；其余明确记录拒绝原因。这是开发工具，不是玩家需要手动操作的启动步骤。

数值后端的同一次服务器扫描为 1057 个原始类型静态候选、38 个成功方法。`pool.asm` 的持久线程池避免每批创建线程，输入和输出维持索引顺序。四种数值/异常负载在 1、2、4、8 个工作者下各重复三次，累计 3,145,872 条记录逐字段一致；忙碌池拒绝竞争的运行与销毁。

```powershell
.\scripts\Test-ManagedParallel.ps1 -NumericRun .boom/numeric-tests/<通过的运行编号> -Persistent
.\scripts\Build-ManagedProbe.ps1
.\.boom\native-managed-probe\boom-managed-probe.exe
```

最后一个程序把数值方法、持久工作池、堆和显式 GC 链接成完全汇编的独立 EXE，仅导入 `KERNEL32.dll`。它是集成引导测试，**不是 Minecraft 客户端启动**。堆测试验证循环引用、8 线程 8000 次分配、预算、归零、合并和复用；尚未接入 Java 安全点和完整根映射。

```powershell
.\scripts\Test-ManagedParallel.ps1 -NumericRun .boom/array-compiler-tests/<通过的运行编号> -Persistent -ArrayKernels -Count 8195
.\scripts\Build-ManagedProbe.ps1 -ArrayKernel -Output .boom/native-array-probe
```

数组并行测试累计 491700 条任务，检查结果、异常来源和批次 GC；计时包含单列 GC 成本。数组引导 EXE 则完全以汇编执行翻译后的 Java 数组方法，顺序与 8 工作者各 65539 次，并检查不可达数组被回收，仍不代表完整游戏已能启动。

## Minecraft 输入工具

已保留 1.21.1 官方输入校验、依赖展开、类集合检查和 JVM 参考启动，供自研后端后续复用。

```powershell
.\scripts\Set-Toolchain.ps1
.\target\release\boom.exe prepare --side server --download
.\target\release\boom.exe verify --lock .boom/locks/server.json
.\target\release\boom.exe inspect --lock .boom/locks/server.json
```

原版文件、账号会话、工具下载包和大型构建结果不随源码提交。

`build-native`、`collect-metadata` 和相关世界测试脚本属于早期 **GraalVM 对照实验**，不计入自研字节码后端的完成度。相关结果与已知限制记录在实现文档中。

## 对象与线程数量调节

同类对象已支持 `new`、构造函数委托、实例方法和字段读写；引用字段在布局前部，基本值字段各占八字节。编译器验证未初始化对象不能提前使用或返回。当前仅链接一个具体类，拒绝跨类、继承、接口、静态/volatile 字段及类初始化，不能视为完整对象模型。

对象样例通过 14 个方法、572 组 JVM 对照和 1144 次原生执行。真实客户端依赖 Brigadier 的 `StringRange.at/between` 也直接翻译了原始 class，156 组输入、312 次执行和对象根保留/回收检查通过。

新增汇编调度器用实际批次测量 1/2/4/8 等线程数量，每个任务只运行一次。两次样本后，选择距离最快测量值不超过 10% 的最少线程数；小批次直接串行，内核变更或显式重置会重新测量。295020 条样例任务逐字段检查通过，另外有计数探针检查重跑和遗漏。当前计算密集样例选 8 个线程，两个分配密集样例选 1 个线程。它还未接入游戏 tick、区块或渲染。

```powershell
.\scripts\Test-ObjectCompiler.ps1
.\scripts\Test-LockedObjects.ps1
.\scripts\Test-ManagedParallel.ps1 -NumericRun .boom/object-compiler-tests/<通过的运行编号> -Persistent -ObjectKernels -Count 8195
.\scripts\Test-AdaptiveScheduler.ps1 -NumericRun .boom/numeric-tests/<通过的运行编号> -ObjectRun .boom/object-compiler-tests/<通过的运行编号>
.\scripts\Build-ManagedProbe.ps1 -ObjectKernel -Output .boom/native-object-probe
```

独立对象引导 EXE 的入口、翻译后的 Java、线程池、堆和 GC 全部是汇编，顺序及 8 线程各处理 65539 条任务，仅导入 KERNEL32。它是运行时集成测试，完整 Minecraft 仍不能启动。

同类引用数组现支持 `anewarray/aaload/aastore`、长度、参数/返回及字段，数组描述符保存具体元素布局，写入检查类型。7 个方法、272 组输入、544 次原生执行和根对象循环图检查通过；3 个引用数组负载在 1/2/4/8 线程下共 295020 条记录逐字段一致。另有独立汇编 EXE 顺序及 8 线程各运行 65539 条任务，验证临时对象/引用数组回收。尚不支持数组协变、多维数组、跨类元素或引用数组复制。

```powershell
.\scripts\Test-ReferenceArrays.ps1
.\scripts\Test-ManagedParallel.ps1 -NumericRun .boom/reference-array-tests/<通过的运行编号> -Persistent -ReferenceArrays -Count 8195
.\scripts\Build-ManagedProbe.ps1 -ReferenceKernel -Output .boom/native-reference-probe
```

## 跨类静态链接

`compile-program` 将显式 class 集合中选定静态入口的可达方法链接成同一个汇编模块，方法编号在程序内统一。`program-v3` 已把具名对象身份贯穿参数、返回、静态/实例字段、构造和实例调用，支持一维具名引用数组、基本静态状态与有界递归；使用字符串字面量/内建操作时启用 `program-v4`。当前普通可执行类必须直接继承 Object；类镜像元数据可保存完整层次，继承/接口执行分派、volatile 和完整异常仍拒绝。入口保持为普通静态方法。

`compile-locked-program` 从已校验的原版输入锁自动发现和提取静态调用所需的类，保留 JAR 条目、加载器范围与 SHA-256。只读取原版输入，不运行 JVM 或启动游戏。JVM 仍仅在差分脚本中作为参考。

```powershell
.\target\release\boom.exe compile-locked-program --lock .boom/locks/client.json --entry-class 'axy$b' --method a --descriptor '(II)I' --output .boom/locked-program-color --assemble
.\scripts\Test-ProgramCompiler.ps1
.\scripts\Test-LockedProgram.ps1
.\scripts\Test-ManagedParallel.ps1 -NumericRun .boom/program-tests/<通过编号> -Persistent -LinkedProgram -Count 8195
.\scripts\Build-ManagedProbe.ps1 -ProgramKernel -Output .boom/native-program-probe
```

基础跨类样例覆盖 13 个入口、755 组 JVM 对照、1510 次原生执行。独立汇编 EXE 已完成顺序及 8 线程测试，程序模式会导入 Windows 的 KERNEL32 和同步 API 集合。原版颜色调用闭包的 144 组对照仍保留；依赖 JDK 和继承/接口的原版路径尚未覆盖，完整游戏仍不能启动。

## 跨类具名对象执行

新增对象程序验证了 17 个编译入口、231 组 JVM 对照和 462 次原生调用，包含混合数值字段、跨类循环、实例调用、引用数组、构造失败后发布的对象、静态对象根及子图回收。首次 8 线程访问静态对象图的 4099 条记录一致；创建引用数组不会初始化元素类，错误接收者类型会被拒绝。

未修改的原版 Brigadier `StringRange` 通过自动发现工厂/构造闭包与跨类调用验证，共 300 组对照、600 次原生执行。独立汇编对象 EXE 顺序及 8 工作者各执行 65539 条记录并验证回收；这些都是后端验证，仍不是游戏启动。

```powershell
.\scripts\Test-ObjectProgram.ps1
.\scripts\Test-LockedObjectProgram.ps1
.\scripts\Test-ManagedParallel.ps1 -NumericRun .boom/object-program-tests/<通过编号> -ObjectProgram -Persistent -Count 8195
.\scripts\Build-ManagedProbe.ps1 -ObjectProgramKernel -Output .boom/native-object-program-probe
.\scripts\Inspect-VanillaEntrypoints.ps1
```

对象密集负载的固定多线程测试已检查 491700 条记录，但线程越多并不代表越快；共享堆的分配锁仍限制扩展。新分配路径在完成保留和记账后先释放锁，再清零当前分配者独占的载荷，保持“GC 只在修改者静止时运行”的约束。自适应汇编调度仍按实际工作批次选择线程预算。

## 基本类状态与初始化

新增 `classes.asm` 以汇编处理首次初始化的互斥、其他线程等待、同线程重入、成功发布与失败状态。首次非 Error 失败返回初始化错误状态，原有 Error 状态保留，后续访问报告类初始化失败；原始原因另保存在类描述符中。当前以 Context 状态码传播，尚未提供 Throwable 对象或 catch。

验证包含 8 个基本静态状态入口的 126 组 JVM 对照、25 个持久调用序列、4099 条多核首次访问，以及 16396 条并发失败记录。屏障检查确认 12 个线程中只有 1 个执行初始化，11 个实际等待；还检查浮点环境、常量准备、失败后的静态数组、堆绑定拒绝和深初始化链的栈保护。

统一数值后端现在限制同时活动的 Java 方法体为 128 帧，触发 StackOverflowError 状态并恢复深度。同类递归及跨类相互递归已开放，6 个递归入口的 159 组 JVM 对照、318 次原生调用和 16 次跨类溢出检查通过。该受限栈预算不等于 JVM 的线程栈大小；GC 安全点、栈映射和完整 Java 线程仍未完成。旧 `i32-v2` 模式仍拒绝递归。

```powershell
.\scripts\Test-ClassRuntime.ps1
.\scripts\Test-ClassState.ps1
.\scripts\Build-ManagedProbe.ps1 -StateKernel -Output .boom/native-state-probe
```

独立静态数组 EXE 用 8 个汇编工作者跑 3 批、每批 65539 条任务，跨批 GC 保留静态数组，初始化计数始终为 1。完整 Minecraft 仍不能启动。

## JDK 输入与具名类型

`prepare-jdk-base` 使用已有 JDK 的 `jimage` 从锁定的 `lib/modules` 提取 `java.base`，仅用于离线编译输入准备。提取前后核对镜像及提取工具，逐类记录来源、版本和 SHA-256；当前 JDK 提取 7607 个类。它不会执行 Minecraft，也不提供 JVM 游戏回退。

`plan-types` 已解析实际客户端/服务器主类的字段和方法描述符，并保留定义加载器、具体类名、父类、接口及数组维度。新 `types.asm` 使用只读类型描述符进行汇编赋值兼容判断，支持类/接口关系和数组协变；95 个类型的 9025 组关系与 JVM 一致，汇编线程池在 1/2/4/8 工作者下又验证 108300 条记录。

```powershell
.\target\release\boom.exe prepare-jdk-base --lock .boom/locks/client.json --output .boom/jdk-base/demo
.\target\release\boom.exe plan-types --lock .boom/locks/client.json --jdk-base .boom/jdk-base/demo/jdk-base.json --class net.minecraft.client.main.Main --class net.minecraft.server.Main --output .boom/type-plan/main.json
.\scripts\Test-TypeRuntime.ps1 -JdkBase .boom/jdk-base/demo/jdk-base.json
.\scripts\Test-RecursiveCompiler.ps1
```

完整继承类型元数据尚未接入通用对象分派；`program-v3` 先使用本程序范围内的精确类编号和布局身份执行直接 Object 子类。多维数组这里只验证类型关系，没有开放多维数组字节码执行。字符串字面量和基础类镜像已继续实现，原版主入口的字符串拼接和类型转换已继续实现，目前停在一般接口方法分派。JDK 提供器接入可执行链接、标准库方法执行及完整游戏启动仍待实现。

## 汇编字符串字面量

`program-v4` 解码 class 的 modified UTF-8 为 UTF-16，跨类按完整内容去重字面量；NUL、代理对和未配对代理字符均保留。`strings.asm` 分配不可变字符串和 char 数组，实现 length、isEmpty、charAt、hashCode、equals、compareTo、toString 及字面量 intern。字符串构造、拼接、字符大小写转换和完整反射尚未开放；这是自研汇编运行时的受限 bootstrap 实现，并未声称编译了 OpenJDK String 的全部方法。

已验证 19 个入口、574 组 JVM 对照、1146 次原生调用和 4099 条首次多核访问；另有 491700 条多核记录。String ConstantValue 在所属类初始化器体前准备，失败初始化留下的字符串和字面量缓存都保留为 GC 根。字符串池 ABI 2 绑定单个堆生命周期，已发布的字面量走汇编只读快路径。

```powershell
.\scripts\Test-StringProgram.ps1
.\scripts\Test-ManagedParallel.ps1 -NumericRun .boom/string-program-tests/<通过编号> -StringProgram -Persistent -Count 8195
.\scripts\Build-ManagedProbe.ps1 -StringKernel -Output .boom/native-string-probe
```

独立汇编 EXE 顺序运行后，以 8 个工作者执行 3 批、每批 65539 条记录，跨批 GC 保留驻留对象；仅导入 Windows 系统库。完整 Minecraft 仍未启动，目标模式继续推进实际主入口。

## 汇编类镜像

`program-v5` 为 class 常量提供真实、带定义加载器和来源摘要的类型元数据，执行中的镜像创建、名称查询、父类/数组组件和赋值关系查询全部由 `mirrors.asm` 与 `types.asm` 完成。支持 Class 引用和一维 Class[]，类常量不会编译或执行目标类初始化器。元数据中的继承关系不代表已开放继承对象执行。

13 个入口通过 816 组 JVM 差分、1632 次原生执行，8 工作者冷创建处理 4099 条记录。1/2/4/8 工作者另通过 491700 条记录，独立汇编 EXE 通过顺序及 8 线程三批执行与 GC。普通 `int.class` 的包装类 TYPE 字段初始化、动态反射、跨模块镜像统一和通用对象 getClass 尚未开放；基本类型镜像可通过数组组件查询验证。

```powershell
.\scripts\Test-MirrorProgram.ps1
.\scripts\Test-ManagedParallel.ps1 -NumericRun .boom/mirror-program-tests/<通过编号> -MirrorProgram -Persistent -Count 8195
.\scripts\Build-ManagedProbe.ps1 -MirrorKernel -Output .boom/native-mirror-probe
```

program-v5 阶段的原版编译检查停在客户端字节码 235 的 `invokedynamic`、服务器字节码 228 的 `checkcast`。完整游戏仍未启动，目标保持 active。

## 汇编动态字符串拼接

`program-v6` 支持 StringConcatFactory 的 `invokedynamic` 拼接，整数和 long 的十进制格式转换、boolean、char、String/null、UTF-16 配方及静态 String 常量全部由汇编执行。两次遍历先计算长度，再填充尚未发布的字符串；结果保持独立对象，只有显式 intern 才参与内容驻留。

字符串池 ABI3 使用可增长的堆内哈希表。驻留匹配未加载字面量时，直接将动态字符串发布为其字面量根；之后 ldc 和 intern 保持同一身份。表扩容重排和 GC 根也由汇编完成。当前仍使用强驻留根和静止显式 GC，尚无 Java 执行栈安全点、类卸载和一般 String 构造器。浮点格式、任意 Object.toString、其他动态引导方法仍拒绝。

16 个入口、1491 组 JVM 差分、2982 次原生执行及 4099 条冷并发驻留记录通过；另有 491700 条多线程记录、独立汇编 EXE 的三批执行和临时字符串回收检查。program-v6 阶段已越过该拼接，当时客户端停在字节码 529 的 File 类型转换，服务器停在字节码 228 的 Path 类型转换。完整 Minecraft 仍未启动。

```powershell
.\scripts\Test-ConcatProgram.ps1
.\scripts\Test-ManagedParallel.ps1 -NumericRun .boom/concat-program-tests/<通过编号> -ConcatProgram -Persistent -Count 8195
.\scripts\Build-ManagedProbe.ps1 -ConcatKernel -Output .boom/native-concat-probe
```

## 汇编运行时类型检查

`program-v7` 把已校验的堆类型标签映射到包含定义加载器身份的 TypeDesc，执行 checkcast、instanceof 和 Object.getClass。它支持现有对象、String、Class 镜像、八种基本数组及现有一维引用数组，并验证 payload/引用槽形状。null 转换保留 null，错误转换报告 ClassCastException；getClass 使用原有镜像池保持身份。

Object/接口等描述符保留元数据类型，分支合流保存可选引用类型集合，验证赋值时要求每个候选都合法。合流不会把整数或未初始化引用当作对象。通过接口引用调用 final Object.getClass 也已接通；封闭应用类的接口、继承与一维引用数组协变已接入；bootstrap/JDK 执行、Object[]/多维数组、完整异常对象、安全点及自动回收调度仍待实现。

16 个入口通过 1950 组 JVM 差分、3900 次原生调用；另有 4099 条首次并发 getClass、491700 条多线程记录以及独立汇编 EXE 验证。原版客户端与服务器均已越过此前的类型转换，目前停在接口调用 `bnl.a(Lbnj;)Z`。完整 Minecraft 尚未启动。

```powershell
.\scripts\Test-TypeChecks.ps1
.\scripts\Test-ManagedParallel.ps1 -NumericRun .boom/type-check-tests/<通过编号> -TypeChecks -Persistent -Count 8195
.\scripts\Build-ManagedProbe.ps1 -TypeKernel -Output .boom/native-typechecks-probe
```

## 紧凑对象布局（program-v10）

封闭应用类层次现在默认使用对象布局 ABI2：引用字段仍占 8 字节并组成可精确追踪的前缀，标量按 8/4/2/1 字节和自然对齐分组。boolean/byte 使用独立字节，生成的汇编按字段宽度读取和写入，不把相邻字段一起改写。旧的直接 Object 子类开发配置继续支持 ABI1。

`scripts/Test-PackedProgram.ps1` 对比同一组 class 字节码在保留的 v9 后端与新后端中的实际分配。8195 个继承对象图占用的分配器空间由 2097920 降至 1966800 字节（6.25%）；小字段较多的对象图由 4195840 降至 1966800 字节（53.125%）。统计包含对象头及分配对齐，固定堆的 OS 预留不随该数字缩小，尚不能推导整款游戏的内存或 FPS。

该测试还覆盖 462 组 JVM 对照、相邻字段 8 线程写入、存活图保留、完整回收、复用及 OOM 后显式回收再试。完整原版仍未启动，线程本地分配和自动回收调度也未完成。


## 异常开发检查

```powershell
.\scripts\Test-ExceptionRuntime.ps1
.\target\release\boom.exe plan-exceptions --lock .boom/locks/client.json --jdk-base <已准备的jdk-base.json> --class net.minecraft.client.main.Main --output .boom/exception-plan
```

异常表已保序解析，验证器已加入异常分支；独立汇编 Context32 服务可保存、匹配并消费已经物化的 Throwable 引用，测试覆盖并发状态隔离及显式 GC 根。`plan-exceptions` 只验证输入和输出只读规划；现有程序仍用 Context16，异常构造/物化、完整处理器代码生成、安全点和原版启动尚未接通。开发命令不会出现在启动器玩家界面。


## JDK 可执行提供器开发检查

```powershell
.\scripts\Test-BootstrapProgram.ps1
```

程序可自动读取锁定 java.base 中的可达 Java 字节码，并由自研后端生成汇编。当前用真实 Objects 和 OptionalInt/Long/Double 验证所选方法、私有字段、构造器、类初始化及跨加载器静态 GC 根；这不代表完整 JDK 已兼容。volatile/同步、Throwable、模块访问、反射、lambda/native 服务仍有缺失，完整原版尚未启动。启动器玩家界面仍只保留启动流程。


## volatile 与多线程内存顺序开发检查

```powershell
.\scripts\Test-VolatileProgram.ps1
```

静态及实例 volatile 字段已支持自然对齐读取和内存 XCHG 写入，包含紧凑窄字段和引用。纯汇编线程驱动验证发布、64 位撕裂、相邻字段及静态/实例排序；另用故意删除排序的隔离汇编副本检查测试敏感性。这是多核正确性验证，完整 Java 线程/监视器、安全点、自动回收和游戏多核性能仍未完成。

## 断言策略与 VM 时钟开发检查

```powershell
.\scripts\Test-AssertionProgram.ps1
.\scripts\Test-MirrorProgram.ps1
.\scripts\Test-ClockProgram.ps1
```

Class.desiredAssertionStatus 支持分别控制应用/系统的冻结启动默认值，并由汇编镜像查询；逐类/逐包覆盖与动态设置尚未开放。四种策略共 160 组 JVM 对照、320 次原生执行及 32780 条多核首次初始化记录通过；旧镜像 ABI1 的 816 组对照及 4099 条冷访问也通过。

System.currentTimeMillis/nanoTime 通过来源校验的 VM native 绑定调用汇编实现，时间换算覆盖 323 个独立算术向量，另通过 4000 条采样检查及 8195 条多核记录。这不代表完整 System Java 启动或 JDK 兼容。客户端发现边界已推进到 Class.getModule，服务器仍在 LambdaMetafactory；完整原版尚未启动。

内存管理不照搬 HotSpot；当前汇编堆是显式静止回收基线，已验证紧凑字段。后续先完成精确根和安全点，再接入线程本地分配与自动回收。经过生命周期证明的临时对象才可使用栈/任务区域，目标是降低分配成本、争用和停顿。详细范围见 [设计文档](docs/DESIGN.md)。

## 模块身份开发检查（program-v15）

```powershell
.\scripts\Test-ModuleProgram.ps1
```

Class.getModule 和 Module.getName/isNamed 已接入自研后端与汇编运行时，保留 java.base、每个定义加载器的未命名模块及数组组件身份。12 个入口通过 492 组 JVM 对照、984 次原生执行及 24585 条多核记录；包含直接首次并发创建、静止回收后的身份保留，以及断言 ABI2/VM 时钟共存。

此节的旧模块 ABI1 配置不请求层图；新的汇编层查询见 program-v16。访问边执行和动态加载仍未实现，完整原版尚未启动。

## 启动模块图开发检查（编译期）

```powershell
.\scripts\Test-BootModules.ps1
.\target\release\boom.exe prepare-jdk-modules --lock .boom/locks/client.json --output .boom/jdk-modules/<新目录>
.\target\release\boom.exe plan-boot-modules --lock .boom/locks/client.json --jdk-modules <jdk-modules.json> --output .boom/boot-module-plan
```

工具从锁定 JDK 镜像提取模块描述符，自行计算默认 classpath 应用的系统模块图。70 个描述符、43 个默认根、63 个模块身份及 3969 对可读关系与 JVM 参考一致；重复提取、缓存迁移与八类篡改/错误输入检查通过。program-v16 已使用该图进行汇编层查询；可读性约束尚未接入链接执行，完整原版仍不能启动。

## 启动模块层开发检查（program-v16）

```powershell
.\scripts\Test-LayerProgram.ps1
```

Module.getLayer 和 ModuleLayer.boot/empty/findModule 现由汇编执行；编译时需提供已核验的 --jdk-modules。结果由翻译后的原始 JDK Optional.ofNullable 包装，继续执行真实 JDK 方法。14 个入口、854 组 JVM 对照、1708 次原生调用及 40975 条多核记录通过，包含动态 UTF-16 名称、空引用、身份根与临时 Optional 回收。

客户端编译发现已推进到 gvq.<clinit> 的 LambdaMetafactory；服务器也停在 lambda 引导服务。动态层、完整模块访问控制和其他 JDK 类提供器仍待实现，完整原版尚未启动。


## 标准 lambda 与方法引用（program-v17）

```powershell
.\scripts\Test-LambdaProgram.ps1
```

原始调用点由自研后端展开为捕获字段、构造器、工厂和函数接口方法，运行时全部执行汇编。已验证 24 个入口、544 组 JVM 对照、1088 次原生调用和 73755 条 8 工作者记录；生成类来源、私有访问、接口静态引用、空值与回收后的捕获引用均有检查。

无捕获调用点复用一个静态根闭包。项目旧工厂与新工厂对相同输入各执行 24585 次调用，实际闭包分配从 24585 个降为 1 个；该结果仅描述此调用点。自动回收、安全点、线程本地分配、altMetafactory、通用 MethodHandle 和完整包装类启动仍未实现。完整 Minecraft 目前仍未启动；最新主入口发现停在客户端 Locale 字符串转换和服务器类资源读取，详见实现记录。


## 同步方法与对象监视器（program-v18）

```powershell
.\scripts\Test-MonitorProgram.ps1
```

同步方法的锁定、重入、竞争等待和释放全部由汇编完成，静态方法使用真实 Class 镜像作为锁。14 个入口通过 168 组 JVM 对照、336 次原生调用和 49170 条 8 工作者共享更新；分发程序另通过 491700 条重复争用。原始 JDK ByteArrayInputStream 的读取、跳过、复位和剩余长度查询已有执行验证。

监视器记录计入堆预算，空闲记录清除对象引用后复用，并在显式回收时释放。有持锁者或等待者时拒绝回收；其他 Java 修改者仍必须静止。这不等于安全点或自动 GC。monitor 字节码、wait/notify、中断及完整 Java Thread 语义尚未完成，类资源定位与完整游戏启动也仍待实现。
