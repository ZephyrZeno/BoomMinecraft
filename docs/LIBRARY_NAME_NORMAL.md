# 正常 System.mapLibraryName 源绑定

`native/providers/library_name_normal.asm.inc` 与 `scripts/library-name-source.py` 将已验证的 Windows `System.mapLibraryName(String)` 从 NIO 组件分离。交付执行仍是 MASM；Python 只做源码核对、构建和测试，JDK 只作结果对照。

## 原声明、布局和依赖

模型按原 `java.base` 的 bootstrap 类文件取得 public static native 声明、方法编号、源 native 帧及 Java Code 身份，核对方法／字段清单。String 的 `value`、`coder`、`hash`、`hashIsZero` 字段位置从当前正常布局动态取得，并与正式 String 工厂元数据交叉核对。方法号、类号和字段偏移都不作为跨批次 schema 常量。

本 server 批次的 native 编号为 43956，正常 Java 依赖是 String.length（43339）、String.toCharArray（43414）、IllegalArgumentException(String)（41919）和 Throwable.fillInStackTrace()（44421）。后者是原异常构造器通过虚调用实际需要的方法。模型显式依赖 `normal-throwable-v1`，以及 `runtime_metadata`、`properties` 基础模块。正式选择器必须实际纳入这些依赖；只在 manifest 中声明不足以提供运行时对象。

独立服务名为 `boom_provider_library_name_service`，独立只读 pool 为 `boom_provider_library_name_pool`，大小 112 字节、ABI 2。它引用正式 `boom_java_properties_string_pool`、堆单元和同映像 ASM String 工厂，不包含属性查询表、Dispatcher 的 20 字段表或原生缓冲区。调用结果通过正常源布局工厂建立新 String；没有增加静态或 GC 根。堆仍限定为非移动、显式静止回收，没有自动 GC 证明。

独立核只重命名旧 `win32_library_name.asm.inc` 的服务、私有标签和源符号别名。生成器逐名归一核对，再以同一 ml64 分别汇编两份核，实际 `.text` 字节完全相同，SHA256 为 `4c6c153a93c98577bd3703b45c5776be7ad269efc39b84213cea0f5abe40c7d9`。独立 provider COFF 有 22 个导入，没有 NIO Dispatcher 或原生缓冲区导入。

## 正常源映像中的实际执行

独立执行使用已经完成正式 23 family 冷测试的原版源码选择：

- `.boom/class-loader-assertions/formal-execution-v145-23-23a1a5d3dc5646749ab64939274c821d/source-selection`
- 基线执行回执 `.boom/class-loader-assertions/formal-execution-v145-23-exports-23a1a5d3dc5646749ab64939274c821d/result.json`

测试在新目录重链，调用正常有帧的 `boom_m43956` 入口，而不是只调用核服务。它执行原 String 初始化器，用原 String(char[]) 构造输入，再执行原 length／toCharArray。未消费 NIO candidate，也未链接 NIO 原生缓冲区 provider。

首次执行已经通过 14 个正常名称，241 单元错误路径从原 Throwable(String) 的 PC 24 停到尚未链接的原 Throwable.fillInStackTrace()。该失败和当时四个新源文件的快照保存在：

- `.boom/library-name/execution-v145-a/first-failure.json`
- `.boom/library-name/execution-v145-a/source-snapshot-at-first-failure`

后续只在 `.boom/library-name/execution-v145-b` 补入同批已验证的原 Throwable.fillInStackTrace() wrapper／body，以及已接受的正式 `normal-throwable-v1` COFF。该 Java 方法原 Code 为 **29 字节、15 个字节码 PC、0 个异常表项**；全部原分支、监视器处理和指令保留，没有重跑 Java 代码生成。`source-stacktrace.json` 记录源 class／Code、原 shard／ASM／COFF、全部 PC 和抽取结果摘要。

重链只移除原 mapLibraryName native 和该 Java 方法的两个开发 stop。原虚表、其余 stop、原 Java ASM／COFF、基线映像和正式 23 清单均未修改；正常回溯 native 由该同批正式 provider 提供。没有注入类初始化状态或 Java 静态字段。

实际输入中包含正式 `properties/0000.obj`，SHA256 为 `03626e0cb0558594f54d6a32b1d9148b3503d851a5202a719a1390be164f548c`。执行核对独立 pool 与平台属性 pool 地址不同，但 String metadata 指针等于同一映像内的正式 `boom_java_properties_string_pool`。未创建替代 String 元数据或额外持久根。

## 验证结果与回执

正常输入有 14 组，覆盖空名称、net／nio、中文、非 BMP 字符、嵌 NUL、孤高／低代理项及混合代理项；240 UTF-16 单元包含普通字符、120 个非 BMP 字符、NUL 和孤代理项。所有结果是新的正常 String，完整保留输入单元并追加 `.dll`。

4 组 241 单元输入分别是普通字符、120 个非 BMP 字符加一个字符、NUL、孤高代理项。它们实际执行原 IllegalArgumentException(String) 构造链，产生正确源异常类型与 `name too long` 消息。测试按原继承字段声明和布局只读观察 Throwable.detailMessage，再由原 String.toCharArray 读取消息；没有把未选入的 Throwable.getMessage 记作已执行。以上 18 组均与锁定 Windows JDK 的实际调用对照。null 保留源 NPE 边界；外堆、错误源类型和已有异常分别验证。

8 个真实 OS 线程经屏障同时开始，共完成 1120 次正常映射。线程 ID 各不相同，所有结果和 guest 深度检查通过，最终正常堆销毁成功。这里证明并发正确性，没有据此声称性能提速。

独立 source／native frame／ASM／COFF 证明：

- `.boom/library-name/source-bound-v145-b/candidate.json`
- `.boom/library-name/source-bound-v145-b/verification.json`
- verification SHA256：`154426430417afca10ab377ee2051bec49609bba5bed90692d9311b6a9dd6cfa`

实际执行回执：

- `.boom/library-name/execution-v145-b/execution-be9e6ad96438495ba4399b761c8c12a3.json`
- execution SHA256：`e81cbd96e1461ea0a1bd77ed848bf9c04db40f1cfe204470bf14e7f3aeba2fb5`
- `.boom/library-name/execution-v145-b/images.json` 记录全部原链接输入、两处 stop 替换、Java 增量和正式 Throwable COFF；SHA256 为 `d185a24dc89afb2a8ec45ab26d808d616b9086e1f1943dacf8d575210d37e499`。

主 agent 在新目录独立重链并重复执行全部检查，回执为 `.boom/library-name/root-independent-v145-b/execution-eb69b85aa0c94137948852944b19e377.json`，SHA256 为 `523d63d8c8e9477740dbf4229511239cd5ded2684b3279ed7e75832e770837e1`。

可在新目录复验源模型：

```powershell
& D:/Dev/Python312/python.exe scripts/library-name-candidate.py `
  --state .boom/pending-native-class-loader-v145-23-23a1a5d3dc5646749ab64939274c821d.json `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --output .boom/library-name/review-source
```

使用该新候选和上述已验证基线执行，测试工具将重链到自己的新目录：

```powershell
& D:/Dev/Python312/python.exe scripts/test-library-name-candidate.py `
  --candidate .boom/library-name/review-source/candidate.json `
  --baseline-result .boom/class-loader-assertions/formal-execution-v145-23-exports-23a1a5d3dc5646749ab64939274c821d/result.json `
  --output .boom/library-name/review-execution
```

当前结果仍是独立正常 source 组件验证。该 family 尚未正式注册；完整 System 冷启动、Phase1／Phase2、原 Java NativeLibraries 装载链和 Minecraft 启动均未由这组测试完成。
