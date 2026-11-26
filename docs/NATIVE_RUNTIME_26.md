# 第 26 组运行时输入与原生前沿

2026-11-27，在原 23 组已验证输入上加入三个正常源绑定，合计新增九个 native。游戏执行仍为自研后端生成的汇编及汇编运行时；Python／PowerShell 用于构建和验证。

| family | 原始 native | 运行时池 | Java 回调 |
| --- | --- | --- | --- |
| normal-reference-referent-v1 | Reference.get0、refersTo0、clear0；PhantomReference.refersTo0 | RGET48/2 | 无 |
| normal-native-libraries-v1 | findBuiltinLib、load、unload、findEntry0 | 32 字节／ABI1 | String、Boolean、两个错误构造器和原 Throwable 包装 |
| normal-library-name-v1 | System.mapLibraryName | 112 字节／ABI2 | String、错误构造器及原 Throwable 包装 |

原 Java 字节码、ASM／COFF、运行时 DLL 和原 accepted23 目录均未修改。新帧缓存与 23 个旧包在当前工具身份下重新验证，复用原 ASM／COFF 字节；三个新包分别生成、实际汇编并独立核对。输入准备为 275.172 秒，不包含后续组件执行和完整主进程校验。

生产选择器现在实际处理 `required_base_modules=properties`：选择原 Raw 类状态／失败根、链接原 COFF，并导出原根区。校验器核对 109 格／872 字节根前缀、私有字符串根位置和实际计数；没有只信任 manifest 声明。NativeLibraries 仅在实际选入时链接同 SDK 的 ws2_32.lib，封存路径与散列。五项 Winsock 导入按该 SDK 的真实短导入对象解析名字或 ordinal，再与 PE 精确比对；未泛化允许任意 ws2_32 调用。

## 三个组件的正式执行

- [Reference 正常冷源验证](REFERENCE_REFERENT_FORMAL.md)：13 类、22 个原 Java 方法，三项所需类型由正常选择进入，54 格静态／失败根。原构造器、四个普通有帧 native、八个 OS 线程的 2,048 次操作、四轮真实 GC 与 JDK 对照通过。没有替换 stop、修改虚表或预设类初始化状态。
- [无属性 native 的库名映射](FORMAL_MAP_LIBRARY_NAME.md)：实际 `selected_property_natives={}`，原 properties 模块和 Raw 状态／失败根仍进入镜像。八线程冷初始化、14 个正常输入、四个原异常回溯、1,120 次并发映射及 19 项 JDK 对照通过。属性根区当时没有活对象，如实不宣称其活对象保留测试。旧 oracle 摘要误判保留，由仅修摘要核对／输出目录的新入口完整复跑。
- [NativeLibraries 正式组件](NATIVE_LIBRARY_FORMAL.md)：原始四个 primordial 构造器与编译生成的 192/1 池创建真实主线程；原 Object.getClass 和 NativeLibraryImpl 构造器建立正常接收者。八个原 Thread(String) 对象由测试 OS 线程附着，八份库接收者共享一份实际 HMODULE 引用，最后释放。原 Properties API、Boolean 回调、Winsock 清理及堆／注册表／trace 清理通过。测试没有调用这些工人的 Thread.start，也没有完成整个 Java loadLibrary 调用链。

三份执行 SHA256 分别为：

```text
Reference       d6f9d944ee745d7355d14e66e48cc7a311724dc76a8647b94b49e4ca5366eb4e
mapLibraryName  da65a9a7cd4bbda27b611a59fc0f6a09135ed62b0c8d7b389c8f0b2ef44f38ba
NativeLibraries 8c50003485c955b9e6365d2f6df4c3a1d77f78fc6a308af605882bd9875e052c
```

## 实际原生主进程

新源选择在 `.boom/diagnostic-startup/v146-native-three-families-9c5d0bc2e4db4866b30ad467ceb39e8c/round-000`，包含 4,701 类、45,776 个原 Java 方法、117,287 个完整源函数、10,591 格静态／失败根。源许可中的新增方法仍只计为编译选择，不计为已执行。504,119,255 字节初始化 ASM 完成并行汇编后，独立完整校验自然退出 0，耗时 615.281 秒。

原生镜像 `.boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1` 已真实运行。原始 System Phase1 返回，Phase2 越过 Reference 接口，主线程在尚未提供的 WinNTFileSystem.canonicalize0（40674）停止，观察到原调用方法 39321、PC 27。Phase2 未返回，VM 级别仍为 1。

两个后台原 Thread.exit 与 OS 记录回收完成，工作者失败、停止时监视器持有数均为零，堆／注册表／Java 帧清理标志为 7。停止前活对象数为 8,139；没有将其记作自动 GC 或游戏启动。

```text
source proof af58f582032bca130111da68c70a850aab51c236e7f5378d44a34732f5fad93f
native proof 9eb333a156975c154c1636fe8fc9dffe80645a3bf950c51cadb98bc8f47c7c21
execution    400fe92c4cdfe4ac68a8eb1479960377e42036bbc78062ce620f5aae2e8d282d
report448   168baddbac8aea42546caba8a8634932ef16d76464002ed1bd04306f6e217ea3
```

正式组件与主进程输入共 508 项实际文件经主 agent 散列核对后，另行发布 `.boom/accepted-native-three-families-v146-26.json`，SHA256 为 `266376873d79bf6b74797d0f0cf5797b5d69f37519bdeeea4b9d4ed623913381`。原 pending 状态保留。`accepted` 表示本页列出的源绑定、组件和原生前缀范围，不表示全部 native 已穷尽执行。

376 项 Python 测试通过，包括真实 SDK 链接、五项导入解析、根区破坏拒绝及旧无 properties 模块兼容；日志为 `.boom/python-tests-v146-formal26-integration.log`。完整 System、Minecraft 入口、世界创建、完整弱引用 GC 与游戏侧性能验收仍未完成。
