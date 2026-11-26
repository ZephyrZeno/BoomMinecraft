# Windows canonical 路径原语和原 native 绑定

`native/runtime/windows_canonical_path.asm` 提供独立 WinAPI 原语；`native/providers/windows_canonical.asm.inc`、`scripts/windows-canonical-source.py` 和 `scripts/windows-canonical-candidate.py` 将它绑定到锁定原版 `java/io/WinNTFileSystem` 的两个 native。交付执行为 MASM，Python 只核对源码、构建和测试，JDK 只作 oracle。

## 锁定声明、布局和原语

源模型从 bootstrap `jdk:java.base` 原 classfile 核对类、字段和方法清单，动态取得 `canonicalize0(String)String`、`getDriveDirectory(int)String` 的 private instance native 声明、类号、方法号、源摘要和当前普通 native frame。两项原 access 均为 `0x102`，帧要求 native 标志 32 且不带开发 stub 标志 128。本 server 的方法号分别为 40674、40671，类号 4445；这些数字只记录本批证据，不作跨批次 schema 常量。当前 classfile 没有 `canonicalizeWithPrefix0`；C 文件中残留的同名导出不注册。

JDK 源固定为 `jdk-21.0.13+3`。八份 native／Java 源位于 `.boom/windows-path-canonicalization/pinned-sources/jdk-21.0.13+3`，SHA256 全部封存在候选 metadata；`WinNTFileSystem.java` 来自锁定 `src.zip`。算法依据原 `wcanonicalize` 的全路径展开、逐 prefix `FindFirstFileW` 大小写／8.3 修正和不存在后缀追加；没有改为打开文件后解析符号链接目标。

两个公开 Win64 ABI 是：

```text
DWORD boom_windows_canonical_path(WORD *input, DWORD units,
    WORD *out, DWORD capacity, DWORD *outUnits)
DWORD boom_windows_drive_directory(DWORD drive,
    WORD *out, DWORD capacity, DWORD *outUnits)
```

`capacity` 包含终止 NUL；成功返回 0，`outUnits < capacity`，输出以 NUL 结束且计数不含 NUL。失败返回非零，`outUnits=0`，输出完全不动。首个嵌 NUL 结束 native 输入，最大有效输入／输出为 32767 个 UTF-16 单元；语义预算沿用原 1024 或输入长度加当前目录长度的规则。`0xffffffff` 表示没有 Win32 错误码的逻辑失败，8 表示原语私有分配失败，122 只表示调用者输出容量不足。

原语实际导入 9 个 WinAPI：GetProcessHeap、HeapAlloc、HeapFree、GetFullPathNameW、GetCurrentDirectoryW、GetDriveTypeW、FindFirstFileW、FindClose、GetLastError。canonical 原语每次私有分配一个 262176 字节工作区并释放；drive 原语使用调用栈缓冲区。无项目全局路径锁，也没有跨调用路径缓存。调用期间进程 CWD 必须保持稳定。逐 prefix 查询的 9 个不报告错误为 2、3、5、18、53、65、67、267、1231，保留原不存在后缀。drive 接受 1..26，以 `GetDriveTypeW` 和 `GetFullPathNameW(X:.)` 模拟原 `_wgetdcwd` 的 MAX_PATH 限制，返回值去掉 ASCII `X:`；不可用或无效 drive 在源绑定中正常返回 null。

原语固定 SHA256 为 `934ef9f40acd8249d8e8061d90516909ffd4a3ffa7eb993b9d63af44467649ec`。producer 只删除独立 `.asm` 的 option／EXTERN／END 外壳，原指令、常量、数据、私有标签和 PUBLIC 均原样保留。候选分别汇编原文件和去壳文件，核对实际 `.text*`、`.rdata*`、`.data*` 字节以及 COFF 导入／PUBLIC 定义相同；没有复制改写原算法。

## 正常 String 和异常依赖

独立服务为 `boom_provider_windows_canonical_service`，独立只读 pool 为 `boom_provider_windows_canonical_pool`，112 字节、PROP ABI 2。原 String 的 `value`、`coder`、`hash`、`hashIsZero` 字段偏移从当前布局动态取得，再和正常 String 工厂元数据交叉检查。输入执行原 String.length／toCharArray，输出经同映像正常 ASM String 工厂分配；没有 NIO Dispatcher 字段表或原生缓冲区依赖。

源模型显式需要 `runtime_metadata`、`properties` 基础模块，`normal-winnt-filesystem-v1`、`normal-throwable-v1` provider，以及原 String.length、String.toCharArray、IOException(String)、Throwable.fillInStackTrace() 的 Java Code。typed IOException 使用原构造链和正常 Throwable 回溯 wrapper。没有增加无关 IllegalArgumentException。

wrapper 每次私有分配 65536 字节输出缓冲区，并在成功、typed 错误和普通 null 返回前释放。公开计数 `boom_windows_canonical_owned_buffers` 只用于观察当前持有数。真实 Win32 错误保留原语返回码，使用 `FormatMessageW(0x1200, language=0, capacity=256)`，按锁定原 `jni_util_md.c` 先去 LF、再去 CR、再去 ASCII 句点。逻辑失败采用稳定 `Bad pathname`。原语或 wrapper 的 native 分配失败为 Context kind 3；尚未证明原 JDK 所有 malloc 点的 OOM 行为逐点一致，尤其原 `currentDir` 分配失败可能只返回 null。独立低层 OOM 注入不冒充 wrapper 所有分配点注入。

## 顺序错误消息的已知兼容边界

首次绑定执行 `.boom/windows-path-canonicalization/binding-execution-v146-a` 完成 15 次调用后，在原 JDK 顺序 oracle 的 `MiXeD\bad*` 消息上停止：紧接不存在的 `MiXeD\trailing.` 时，JDK C 代码借用了先前线程 `GetLastError`，返回本机“系统找不到指定的文件。”，而本绑定返回 `Bad pathname`。后一条 `bad?` 又返回 `Bad pathname`。成功路径与 IOException 类型一致；这次失败没有被删掉或记为完全通过。

`first-failure.json`、`execution-tool-at-first-mismatch.py` 和首次顺序 oracle 输出均留在 a 目录。后续同时保留完整有序 oracle 和每 case 启动独立 JVM 的点对点 oracle。SourceModel POLICY 和执行结果均明确 `logical_failure_reuses_cross_call_GetLastError_history=false`、`complete_JNI_error_message_sequence_compatibility=false`。本实现没有虚拟化 JNI 线程边界上的 Win32 LastError；runtime 的 trace、分配等内部 WinAPI 也可能改变该 TLS 值，因此不宣称任意跨调用历史的 JNI 错误消息逐序列相同。

这一限制只适用于没有自身 Win32 错误码的逻辑失败。实际报告的 Win32 错误仍按确切返回码生成消息。测试中的 `MiXeD\bad:name` 原语返回 123，wrapper 的 typed IOException 消息与同机 FormatMessage 和锁定 JDK 完整一致；没有把它简化为 `Bad pathname`。`MiXeD\bad<file` 则按 JDK 实测正常返回路径，未按宿主假设改判为错误。

## 原 source 映像中的执行范围

绑定测试消费完整独立校验且实际执行过的正式 26 source 基线：

- source：`.boom/diagnostic-startup/v146-native-three-families-9c5d0bc2e4db4866b30ad467ceb39e8c/round-000`，`selection-verification.json` SHA256 `af58f582032bca130111da68c70a850aab51c236e7f5378d44a34732f5fad93f`。
- 原主进程：`.boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1`，`verification.json` SHA256 `9eb333a156975c154c1636fe8fc9dffe80645a3bf950c51cadb98bc8f47c7c21`。

执行器分别核对 source proof／closure 绑定和 native manifest／proof／execution 绑定，要求原主进程 cleanup=7、worker failure=0。新目录仅移除上述两个 native 的开发 stop，加入独立候选 COFF 和观察导出，其余原 Java、COFF、虚表、类描述符和基线文件保持不变；重链前后复核全部原链接输入。runtime572 不变，也不改正式 26 registry、TOOL_FILES 或 provider。

测试执行原 String 初始化器，用原 String(char[]) 构造输入；以原 Properties 构造器／setProperty 和原 System.setProperties 发布最小属性 API 夹具，没有宿主直接写 System.props。执行原 WinNTFileSystem 初始化器；供两个 native 使用的测试 receiver 是明确的正常源布局存储夹具，没有执行该测试 receiver 的构造器。原初始化链可能构造自身正式 File／filesystem 单例，因此也不声称全局没有任何 filesystem 构造器执行。

原 Java `canonicalize` 的 drive-only 提前返回分支可独立测试。一般路径还会执行原 Blocker 初始化器；本 API 夹具没有运行完整 System Phase1，原 `SharedSecrets.getJavaLangAccess()` 为 null，原 `Blocker.<clinit>` 产生 `InternalError("JavaLangAccess not setup")`，在原 PC 37 athrow。首次实际失败和当时执行器快照保存在 `.boom/windows-path-canonicalization/binding-execution-v146-c/first-Java-entry-failure.json`、`execution-tool-at-first-Java-entry-failure.py`。没有写 JavaLangAccess、改初始化状态或绕过 Blocker 来记作一般 Java canonicalize 成功。

17 条 native 路径包含相对／绝对、实际大小写、`.`／`..`、不存在后缀、中文／非 BMP、嵌 NUL、孤代理项、通配符、尾点和真实 Win32 错误。29 个 drive 输入为 -1..27。8 个不同 OS 线程经屏障同时启动，完成 1600 次真实 native canonical 调用，验证输出、帧深度、计数归零和最终正常堆销毁；这证明并发正确性，不据此声称提速。额外直接调用同映像原语，逐条记录返回码，并检查失败不改调用者输出和真实错误的 FormatMessage 一致性。

## 证据和重放

独立原语结果：`.boom/windows-path-canonicalization/primitive-tests/root-v146-e/result.json`，SHA256 `0ac994a554f12412c753c9c8a048352180eaaa8529b8981c153c1b47bfab7785`。它覆盖 27 路径、29 drive、8 OS 线程的 1792 次调用、1819 次真实私有分配／释放及 live=0、独立 OOM 注入和输出未变。观察变体与生产原语的实际 text 相同。前 a..d 的工具／fixture 失败保留，原语未因此改写。

source／frame／ASM／COFF 候选：`.boom/windows-path-canonicalization/source-bound-v146-b/candidate.json`，SHA256 `004eb006cd273d134d1a6f1413c2573757b4211db9b56b68543e05e73002746e`；`verification.json` SHA256 `07e6250062bd1a6586ec56ae66742bbe49fef267a4683bccfb8a304c9e61f12d`。

首个两 native／17 路径／29 drive／8 OS 1600 调用全部通过的回执为 `.boom/windows-path-canonicalization/binding-execution-v146-b/execution-0dafcb2aadb54511840bac4729169edd.json`，SHA256 `826e24bc36609609218c0857860f6da6ca4dd0aeb22f358ff09b7069223a845d`。完整顺序消息差异单独封存于同目录 `ordered-JNI-message-differences.json`，SHA256 `730218b8dec08b81c5c8d6924e4b6e9b20d43f8cb3a9eecde43a9907ddd92916`。

最终扩展执行 `.boom/windows-path-canonicalization/binding-execution-v146-e` 在同样完整 native／drive／并发检查之外，完成实际原语返回码与输出不变审计、原 Java drive-only 四条恒等分支，以及一般 Java 路径的真实 Blocker 失败边界记录：

- `execution-c11e3853c9074a48adf6fc12e84e4058.json` SHA256：`78ec3da4208fd1309b577b67259376c750a5eff72a9359aef53ea6de4829bb4f`。
- `images.json` SHA256：`c344227fb5fec4a98168c0fb3539eab9bce39f56a303525ab23a5028d61e3a39`。
- `primitive-codes-and-source-results.json` SHA256：`c0f35365864ce3c6d7c5bd660021bc4119e28fa2c7bd76b3e100bb37f8425330`。17 条返回码中 14 条成功、两条逻辑失败、一条实际 Win32 123；失败输出逐单元保持原值。
- `ordered-JNI-message-differences.json` SHA256：`fee2a50809c87239e4fef5aaf6c32637fb90ea15ed621dc6d99f90408053966e`。完整有序 oracle 仍只有已说明的 `bad*` 消息差异，逐 case 独立 JVM oracle 全部一致。
- `source-Java-entry-boundary.json` SHA256：`9e5e9065a52d8afe6f08257fcbc8c556c194f8be87cd8f78154e30d172a5f959`。记录当前原 Blocker class／Code 摘要、动态方法号及原 athrow PC；`source_Java_canonicalize_to_native_path_passed=false`。

中间 d 目录的执行前测试工具失败也保留：新增原链接输入复核误把只读 WinSDK 库路径当作必须位于 `.boom` 的 provider 产物。e 改为核对所有原输入的原 artifact 摘要，包含项目内对象和项目外 SDK 库，未改变原生产输入或原语。e 同时在 oracle 前后核对锁定 JDK `lib/modules` 的 size／SHA256，完整保留 catalog 的三摘要元数据。

可用下列命令在两个全新目录重放：

```powershell
& D:/Dev/Python312/python.exe scripts/windows-canonical-candidate.py `
  --state .boom/pending-native-three-families-v145-three-families-26-9e4944c57a424d038bb7679b56009811.json `
  --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe `
  --output .boom/windows-path-canonicalization/review-source

& D:/Dev/Python312/python.exe scripts/test-windows-canonical.py `
  --candidate .boom/windows-path-canonicalization/review-source/candidate.json `
  --selection .boom/diagnostic-startup/v146-native-three-families-9c5d0bc2e4db4866b30ad467ceb39e8c/round-000 `
  --native-manifest .boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1/vm-entry.json `
  --native-execution .boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1/execution.json `
  --output .boom/windows-path-canonicalization/review-binding
```

主 agent 在另外两个全新目录独立重建并复跑了冻结实现，结果为：

- `.boom/windows-path-canonicalization/root-review-source-v146-a/verification.json` SHA256 `466b67308a583e15385f420dc2203a0a5e521e1eddb66102ed5570c60cd9a9c8`。
- `.boom/windows-path-canonicalization/root-review-binding-v146-a/execution-c9bbbb31a74f42e39b441699a58c7ecc.json` SHA256 `456af0a968983075218f07f9ef15d48df80024d950800bebec4ca226725a68af`。

17 条 native 路径、29 个 drive、八线程 1600 次调用、实际 Win32 错误消息、失败不改输出和正常堆销毁均通过。原 Java 一般路径仍准确记录上述 Blocker／JavaLangAccess 边界，边界文件与 e 的 SHA256 相同；未写入类或静态状态来绕过它。

当前为未注册的两项 native 子集候选。没有声称完整 System 冷启动、一般 Java canonicalize 经 Blocker 的成功、全部 WinNTFileSystem／NIO、任意 JNI 错误消息历史、完整 VM 或 Minecraft 启动。非移动堆和显式静止回收边界继续适用；本测试未证明完整 GC。
