# 正常对象布局的 SystemProps.Raw 属性协议

这项规则将原始 `jdk/internal/util/SystemProps$Raw.platformProperties()`、`vmProperties()` 的 native 声明接到真实汇编服务。它为服务器、客户端的全部匹配调用统一生成入口、元数据和绑定；Java 方法继续由自研后端翻译。首个目标仍为 Minecraft Java 1.21.1。

## 来源与对象

- 输入为锁定的 JDK 21.0.13+3 原始 java.base。39 个平台属性槽及其索引来自原始 ConstantValue，拒绝其他版本的字段或索引。
- `batch_properties.rs` 根据源 String 字段布局、正常 String[] 类型描述符和源 Raw 类状态生成一个汇编单元。
- 两项静态 native 的包装入口先通过 `boom_class_ensure32` 准备源 Raw 类，再调用对应汇编服务。Raw 没有 Java `<clinit>`；原有 40 项静态整数常量按源规则准备，原始构造器和 `propDefault(int)` 保持原代码。
- 字符串为正常源 String 对象，其 value 是真实 byte[]，保留 Latin1／UTF-16 coder、Java hash 和正常堆标记。数组使用源 `[Ljava/lang/String;` 的类型身份；不使用旧开发宿主的 opaque String 或引用数组身份。

String 工厂属于 VM 的对象创建服务，不执行 Java String 构造器或类初始化。这里只证明正常字段和身份，并未完成 String 的全部引导。

## ABI2 与共享服务

原平台属性 Pool80、VM 属性 Pool64 的 ABI1 路径保留供开发回归使用。新 Pool112 的公共字段为 heapCell16、StringPool24、String[] descriptor32；扩展区：

| 偏移 | 内容 |
| ---: | --- |
| 80 | 汇编数组创建回调 `(ctx, pool, count)` |
| 88 | 汇编 UTF-16 复制回调 `(ctx, pool, buffer, length)` |
| 96 | 汇编固定文本回调 `(ctx, pool, literalID)` |
| 104 | 同一生成映像的正常 String 汇编工厂 |

`java_properties.asm` 实现前三项回调；后者由既有字符串模块提供。运行时 DLL 通过函数指针调用源映像中的工厂，不要求 DLL 反向导入某个程序的符号。

`system_properties.asm` 继续执行真实 Windows 查询，包括目录、用户、系统、区域和编码。需要临时宽字符缓冲时使用原生内存，经过正常 String 工厂复制后释放；该缓冲不成为游戏对象。

平台快照由汇编原子发布并通过地址等待协调。每次调用都返回新的 String[]，允许调用者修改数组而不破坏私有快照。VM 属性每次也返回新数组，按 key/value 对排列，并保留终止 null key。

VM 默认配置包括 13 对属性，使用 BoomMinecraft Assembly VM 的实际身份。classpath 与 natives 取自锁定输入；`java.home` 当前取生成映像输出目录。最终启动打包仍需准备这个 home 下所需的资源，不能把这张属性表当成模块引导或最终安装布局已经完成。

## 根与错误

一块连续根区包含平台快照根和固定文本的 String／临时 byte[] 根。服务器／客户端的配置文本不同，因此根数可能不同。每个池绑定单一堆，拒绝混用。

冷构建 OOM 必须撤回快照、所有者和发布状态；发布后的克隆 OOM 保留已有快照。VM OOM 返回待处理错误，不返回伪造的空数组。显式静止回收后允许重试。当前没有自动 GC、活动帧根扫描或安全点承诺。

原始 `propDefault(-1)` 的执行暴露了 `unwind.asm` 在异常池未绑定时直接读取空地址的问题。物化入口增加 Context、VM160 magic／ABI 和绑定状态检查；无法物化时返回失败，保留已有 kind、PC、method 与 pending 对象。正常批量上下文的数组越界仍以待处理 kind 5 传播，**没有生成或伪造 Throwable**。完整源布局 Throwable 物化、捕获和类初始化失败语义仍需接入。

## 校验与执行范围

`verify-batch-properties.py` 从原始源索引重建槽、native 声明和默认配置，再核对正常类型、文本／hash、根区、精确 MASM 和实际 COFF。它接入 schema 13 的完整批量校验器。闭包选择器会自动加入 native、所属类初始化依赖和属性模块；独立闭包校验器继续证明选定 Java 函数及类描述符未改写。

`Test-BatchProperties.ps1` 分开记录两类执行：

1. 开发内核 fixture：通过既有正常字符串映像调用服务，不计作原始构造器执行。
2. 实际批量产物：选择原始 Object／Raw 构造器和原始 getter，通过真实 native 包装入口执行，核对平台属性、配置、字段、类型和错误。

每侧执行包括 39 项 JVM 平台属性对照、13 对 VM 配置、41 次原始 Java 调用、8 个测试工作者的 8,200 次并发调用、数组隔离、UTF-16 特殊字符、11 项错误检查，以及冷／热 OOM 后的静止回收与恢复。构建工作者和开发宿主的并发调用不算游戏多核优化。

完整批量生成／校验、原始构造器执行、System 启动、游戏启动分别记录。当前这项规则不证明 System.initPhase1/2/3、Minecraft 客户端、创建世界、模组、图形／音频或完整内存管理已经完成。启动器界面保持仅启动游戏。
