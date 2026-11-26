# 自研原生库装载生命周期

原始 WindowsNativeDispatcher 初始化在登记引导模块之后会请求 `net` 和 `nio`。直接 Dispatcher 边界探针已命中 NativeLibraries.findBuiltinLib；严格 NIO 初始化记录仍有 Phase1 源方法选择缺口。独立汇编候选已验证已知 net／nio 的原始 native 装载与卸载，正式启动链合流仍待验收；文件查询和网络能力探测分别保留自身范围。

## 锁定的原始入口

| 类与方法 | 描述符 | 服务端计划 ID |
|---|---|---:|
| NativeLibraries.load | `(NativeLibraries$NativeLibraryImpl,String,boolean,boolean)boolean` | 111941 |
| NativeLibraries.unload | `(String,boolean,long)void` | 111942 |
| NativeLibraries.findBuiltinLib | `(String)String` | 111943 |
| NativeLibrary.findEntry0 | `(long,String)long` | 111987 |

类均在 `jdk/internal/loader`。load 的两个布尔参数是 `isBuiltin`、`throwExceptionIfFail`。实际绑定仍需从锁定 class 文件逐项核对完整 JVM 描述符、访问标志、字段、方法 ID 和摘要，不能仅依赖此表。

## 必须保留的语义

原始实现先定位 NativeLibraryImpl 的 `handle:J` 和 `jniVersion:I`。load 执行真实的装载回调并检查异常和接口版本，全部成功后才发布 jniVersion 和 handle。失败、未知模块以及尚未实现的接口必须保持明确失败，不能返回已加载的伪句柄。[锁定 OpenJDK 实现](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/NativeLibraries.c)

内建模块必须有真实的自研汇编代码及绑定清单。名称发现、地址查询、装载回调和卸载关联同一个拥有者映像。函数地址只来自经过验证的本项目映像和签名，不能将采用 Context/argv 的项目内部入口当作标准 JNI 函数地址交给任意调用方。外部 JNI 库兼容属于后续独立边界。

静态构建的 OnLoad 包装器执行模块初始化后报告 JNI 1.8；不能把动态函数体报告的 1.2 直接写入内建库字段。这个版本约定也不表示本项目已经覆盖整个 JNI 接口。[静态包装宏](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/jni_util.h)

`net` 的初始化必须执行原始 Boolean.getBoolean 对 `java.net.preferIPv4Stack` 的读取，实际探测 IPv4/IPv6，按原值限制 IPv6，并保存平台能力。Windows 的复用端口结果依锁定平台实现处理。不能把探测夹具中的固定属性值当作游戏运行值。[网络初始化](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libnet/net_util.c)

Winsock 必须在真实拥有者的有效生命周期内保持初始化。现有 inet_address 可用性探测会在探测结束时平衡 WSACleanup；需要单独的模块拥有状态，不能据此声称 net 库已装载。卸载和 VM 关闭必须只释放本项目持有的那份资源。[Windows 生命周期与能力探测](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/windows/native/libnet/net_util_md.c)

`nio` 的装载体检查当前线程可取得所需版本的 VM 接口。自研后端可以把这项检查降到自身的线程登记和原生调用上下文，但必须验证真实附着状态，不能从无关的 FFI 线程直接返回成功。[NIO 初始化](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libnio/nio_util.c)

## 接入与验收

实现分为汇编生命周期内核、原始有帧 native 适配器和 source-bound 模块描述。模块描述记录真实映像、导出、装载回调、原始 Java 回调、字段映射及资源所有权；原始 Java 继续管理库名集合、调用顺序和异常传播。

测试应验证原始 findBuiltinLib→load→字段发布链，Boolean 属性的真实取值、不同 OS 线程的装载竞争、已有异常保留、未知或错误名称、错误句柄/版本、回调失败后的未发布状态，以及有资源在用时的关闭拒绝。应在返回成功后用实际 socket 调用证明 Winsock 仍有效，并在最终关闭后核对本项目的资源计数。

生命周期内核测试、原始 Java 装载链和正式初始化进程分别记验收结果。只有最后一项覆盖 Minecraft 所需的实际启动路径，才能推进游戏启动结论。

## 已验证的 net 平台资源拥有层

`native/providers/builtin_net_platform.asm.inc` 实现独立 MASM `NETM80/2` 拥有层。成功启动后保留一份实际 Winsock 引用，八个 OS 线程竞争启动只调用一次 WSAStartup。调用者持有租约期间关闭返回忙状态；关闭一个拥有者不影响另一个拥有者的真实 socket 调用。两个偏好值、实际 IPv4／IPv6 探测和十六次重新启动均通过。

状态区分关闭、就绪和失败但仍持有资源。探测 socket 关闭失败时保留真实句柄；再次启动和取得租约均拒绝。显式关闭先重试句柄，成功后再执行 WSACleanup；清理失败仍保留失败状态，直到后续关闭真正完成。不能把残留的 Winsock 引用视作初始化成功。

`scripts/test-builtin-net-platform.py` 同时构建生产导入测试 DLL 和独立故障测试 DLL。后者仅在测试链接时重绑三个调用，注入连续两次 closesocket 失败和一次 WSACleanup 失败。测试核对中间真实句柄仍有效、未提前清理、另一个拥有者仍可用，最终三份实际探测 socket 全部关闭，进程恢复 WSANOTINITIALISED。生产 COFF 保持七个直接 Win32／Winsock 导入。

主 agent 独立重复测试记录在 `.boom/builtin-net-platform-tests/root-v145-failure-recovery/result.json`，SHA256 为 `b1fd2a8074c19d9ea067886f3de66e0bd953bd209f583d78f790907fed8e4e51`。这层尚未连接原始 Boolean 属性读取、线程附着检查、JNI_OnLoad 或 NativeLibraries 字段发布；它不能记作原生库装载或游戏启动完成。

## 已验证的 nio 内部模块检查

`native/providers/builtin_module_context.asm.inc` 使用正式 Thread provider 的同一个注册表单元，经实际 FLS 查询当前线程，并核对堆归属、源 Thread 类型及虚拟线程边界。未附着、已脱离、错误类型或已有异常均不能通过。内部 nio 函数体只检查锁定源码需要的 1.2 版本条件；静态包装器在该函数体成功后才返回 1.8。

`scripts/test-builtin-module-context.py` 已通过八个 OS 线程的真实附着／脱离、与主线程同时九条记录、原始 Thread.currentThread native 的身份一致性和异常保留检查。主 agent 独立复跑记录在 `.boom/builtin-module-context-tests/root-v145-independent/result.json`，SHA256 为 `896d374463878e155cfba0633caed3b08d6da41e1427211f96a3a6aab0fe3fb5`。

本测试的 Thread 接收者使用明确的源布局存储夹具，未执行 Java 构造器。这个内部 ABI 不提供 JavaVM／JNIEnv 函数表或标准 JNI 函数地址；版本返回值不代表完整 JNI 兼容。原始 NativeLibraries 装载、Java 属性回调和字段发布仍待单独接入。

## 原始 NativeLibraries native 候选

`native_library_lifecycle.asm.inc` 及配套生成器绑定原始 findBuiltinLib、load、unload 和 findEntry0 声明与源 native 帧。已知 net／nio 描述关联实际拥有者映像；GetModuleHandleEx 取得的真实 HMODULE 引用由本模块跟踪，最后一次卸载时平衡 FreeLibrary。回调在 SRW 锁外执行，其他装载者等待实际状态变化；相同 OS 线程的递归转换明确拒绝。

实际 nio 回调通过源线程附着检查，成功核对版本后才发布原始 NativeLibraryImpl.handle／jniVersion。八个 OS 线程同时持有八个源布局接收者，共用一份实际模块引用，最终引用数归零。未附着者不能复用已就绪模块；未知模块、错误句柄、未提供的标准 JNI 地址及已有异常分别检查。这里不提供 JavaVM／JNIEnv 函数表或外部 JNI 装载。

net 正向测试使用原始 Properties 初始化器、构造器和 setProperty，再调用原始 System.setProperties 发布属性；Boolean.getBoolean 在实际回调中读取 false／true，两种结果均影响真实 Winsock 拥有者与 IPv6 能力。System.setProperties（43941）由原批次精确抽取 wrapper／body，18 个字节码 PC、全部原分支及异常表均保留；System.props 仍位于原静态根 bank，没有由测试宿主直接写该槽。

独立错误版本测试将测试 DLL 的 nio 回调改为返回 1.2，实际构造原始 UnsatisfiedLinkError 及消息，两份源字段不发布，模块引用归零。生产候选回调不受该注入影响。

主 agent 独立复跑记录在 `.boom/native-library-lifecycle/root-independent-positive/execution.json` 与 `.boom/native-library-lifecycle/root-independent-bad-version/execution.json`。生成器与 API 提取器为 `scripts/native-library-lifecycle-candidate.py`、`scripts/native-library-api-source.py`，执行检查为 `scripts/test-native-library-lifecycle.py`。

Thread 和 NativeLibraryImpl 接收者仍是明确的源布局存储夹具，未执行其 Java 构造器；属性准备属于 Java API 夹具。以上结果不表示完整 Phase1、NativeLibraries 的 Java 冷初始化、正式 family 注册或 Minecraft 启动已经完成。

## 独立正常 source 模型

`native-library-source.py`、`native-library-helpers-source.py` 和 `native-library-source-candidate.py` 已将生产所需的数据与模板从 NIO 测试选择中分离。四个 native、字段位置、源 native 帧以及 String／Boolean／两个错误构造器的 Java Code 身份均按传入批次动态取得；模型不要求 NIO candidate，不包含 Properties／System.setProperties 测试准备。

helpers 的函数 AST 与已执行候选一致，生成 ASM 的摘要固定核对。所需 Thread family、正常元数据与 Properties 模块、四个原 Java 回调和显式 Java upcall 标志均由模型声明。Source／ASM／COFF 独立证明在 `.boom/native-library-source/source-bound-v145-a/verification.json`，SHA256 为 `95356010e0b23153088fb437117a66c80e9422a1749ad7c5164a18c200bef732`。

该独立模型尚未正式登记、链接或执行。System.mapLibraryName 也需自己的正常 family，普通 Java 装载链仍会在尚未接入的接口处明确停止。
