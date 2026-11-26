# 独立汇编运行时提供者包

v112 增加[类标志查询](CLASS_FLAGS.md)，现在是四个家族、十项额外源 native，与基础批次 82 项分开统计，有效视图为 92 项。新增两个接口在两侧均通过原始 native 桥接、JVM 对照、错误检查及并发执行测试；完整 System 和游戏仍未完成。下文首批 CDS／身份散列测试保留原来的 v110 范围。

v111 增加 [normal-constructors-v1](NORMAL_CONSTRUCTORS.md)。构造器池为 160 字节，包含原始输入自动生成的全部构造器元数据；其类初始化回调与尚缺的 native 栈帧明确记录。

这层已实现：在来源不变的 Java 批次之外，单独生成、汇编和校验新增 native 服务。v110 使用 v109 的两侧 Java ASM／COFF 和原始编译器身份，不修改基础批次的 summary、方法记录或分派表中的 `native_binding_provided`。

游戏执行部分是 `native/providers/*.asm.inc` 与生成的汇编桥接；Python、PowerShell 和 JSON 只负责构建及验证。没有 JVM／GraalVM 回退。玩家启动器继续只有启动入口；这里的命令供开发与最终启动流程内部调用，不增加编译按钮。完整启动器和原版游戏验收仍未完成。

## 包的身份与依赖

每个 `provider.json` 绑定基础批次摘要与完整校验报告的散列、原始输入／IR、类／方法计划、原始声明加载器与类散列、Context32、正常布局 ABI、规则及工具身份、源汇编、实际 COFF 和汇编器身份。一个家族可以包含多个原始声明类；Object 默认散列和 System 身份散列由同一个服务处理。

`verify-runtime-provider-pack.py` 独立读取原始 class 字节重建 native 声明及 ID，核对精确访问标志、描述符和操作，再重建桥接文本并检查 COFF 的真实定义／导入。服务体绑定本项目已经审查、测试的汇编源码。包还记录所调用运行时内核的源码身份，链接端对照真实 DLL 的构建记录；非移动身份散列不会误接到其他堆实现。

提供者生成工具身份和基础 Java 编译器身份分开记录。增加 native 服务不把旧 Java 产物冒称为新编译器输出。输入、变换链、布局或 ABI 不匹配时拒绝复用；同一个声明不能由两个包或基础实现重复提供。包只扩展缺少的实现，不替换已经提供的方法。

## 选择、链接与初始化

选择器维护“原始基础批次＋已验证提供者”的视图。遇到包成员时选择对应 COFF，并保留声明类及所有显式依赖的原始描述符／初始化器。桥接先执行声明类初始化，再进入服务；重入初始化仍由原有汇编类状态机处理。尚未提供的 native 或协议继续进入诊断停止，禁止生成默认返回桩。

数据和函数沿用稳定的源符号。完整共享分派表没有因包接入而删行或改目标；已有方法指针现在可以解析到新增的源 native 实现。提供者的全部可用身份和实际选中的包／成员分别记录，链接证明重建该选择关系并拒绝冲突。

基础 Java 方法不会重新执行字节码代码生成，其 ASM／COFF 保持原样。开发诊断为了选取子闭包，仍会把原样选中的 Java 汇编合并后重新汇编；这一步单独标为 `selected_diagnostic_Java_reassembled=true`，不宣称所有 Java 汇编工作都被省去。实际使用的原始 Java 汇编单元按基础批次摘要核对完整内容散列。

## 首批家族

`cds-no-archive-v1` 提供三个原始私有状态查询、`getRandomSeedForDumping` 和 `initializeFromArchive`，共五项。当前执行策略没有映射共享归档、没有转储归档／类列表。服务报告真实的关闭状态，非转储种子为零；归档初始化验证正常 Class 镜像，并保留目标类原本的冷状态或已初始化状态。普通 Java 的后备初始化继续执行。

这与 [CDS 的原始 Java 约定](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/jdk/internal/misc/CDS.java)和[非转储种子的 VM 行为](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/jvm.cpp)相符。归档恢复、生成归档、日志记录等其余声明没有因这项策略而被伪造为成功。

`object-identity-v1` 提供原始 Object.hashCode 与 System.identityHashCode，共两项。汇编先验证非移动 Heap ABI1 中完整、存活、具备正常类型的引用，再调用现有身份混合内核；不修改对象 Java 字段，不为查询分配游戏对象。Object 的 null 接收者产生 NPE，System 的 null 参数返回零。对象移动前必须改用保留身份的堆协议，并重新验证该提供者。

身份散列与内容散列分别处理。包不替换 String 等类型的 Java hashCode 重写；[System 的身份散列契约](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object))要求绕过这类重写。散列值不需要与另一个 VM 或另一次执行完全相同，碰撞仍被允许。

## 开发入口

```powershell
./scripts/Build-RuntimeProviderPack.ps1 -Batch <已校验基础批次> -Plan <对应计划> -Family cds-no-archive-v1
./scripts/Build-RuntimeProviderPack.ps1 -Batch <已校验基础批次> -Plan <对应计划> -Family object-identity-v1
```

默认产物写入项目忽略的 `.boom/runtime-providers/<家族>/<新运行目录>`，已有证据不覆盖。构建输出包含独立的 `verification.json`；加载时还会重新核对包，而不是只读取 `verified=true`。

`Invoke-DiagnosticStartup.ps1` 的默认启动准备阶段自动构建已注册的 CDS、身份散列、构造器枚举和[类标志查询](CLASS_FLAGS.md)四种家族；也可用开发参数 `-ProviderPack` 指定已验证包。每轮诊断沿用同一组包。改变包时使用新的诊断目录与来源核对后的 Java 选择种子；恢复同一目录则要求包路径、内容和校验身份保持一致。

## 验证边界

CDS 测试选择并执行原始 Class、CDS 初始化器、三个原始查询方法及 Optional 后备初始化；八个工作者争用冷 CDS 初始化。检查归档调用保留冷类、已初始化的静态对象身份、错误参数及并发零分配查询。JVM 开发对照使用 `-Xshare:off`，仅作独立策略对照。

身份测试执行原始 Object 构造器、两个 native 桥接和原始 String.hashCode 重写，另准备正常 VM 数组形状。检查跨 API 的身份一致性、内容改变不影响身份、null／非法引用、错误传播和并发稳定性。JVM 对照只比较关系，不比较不同 VM 的具体散列值。

这些都是开发诊断映像，尚未成为完整原版闭包。包验证、内核测试、初始化测试、真正的 System 启动路径和整版游戏验收分别记录；不能由 native 数量或新包构建成功推断游戏已经可启动。Lambda／Record 展开、完整异常、线程、I/O、模块、活动根、安全点及游戏多核／GPU／内存优化仍有后续工作。

v110 两侧测试均通过：CDS 各执行 32,768 次并发源 native 调用、十项错误检查及原始 Optional 初始化；身份散列各执行 16,384 次并发调用、十二项错误检查、256 次原始 Object 构造及原始 String.hashCode。数组仅为 VM 正常形状夹具，不宣称执行了数组分配字节码。Python 180 项测试通过。

真正的 System.initPhase1 各经三轮执行，从 516 项原始 Java 准入增至 526 项，停在未提供的反射构造器枚举 `Class.getDeclaredConstructors0`，没有将该停止当作兼容成功。单独的默认准备链路完成原始 CDS 类根初始化；这一验收仍是诊断映像。原始 Reflection 初始化／getCallerClass 的完整执行暂未验证。基础批次原有 82 项 native 与包中七项分开统计，有效视图为 89 项，基础批次保持原样。
