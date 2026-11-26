# 自研原生库装载生命周期

原始 WindowsNativeDispatcher 初始化在登记引导模块之后会请求 `net` 和 `nio`。直接 Dispatcher 边界探针已命中 NativeLibraries.findBuiltinLib；严格正常初始化顺序当前先停在 Phase1 的反射调用。以下装载协议尚待实现；已有文件查询和网络可用性内核不能单独充当装载成功。

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
