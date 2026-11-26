# 按实际启动路径选择已有汇编

v100 增加开发诊断流程，复用 v99 已生成并校验的原始 Java 汇编，运行指定初始化入口，并根据实际到达的分派目标自动选入已有方法。它为补运行时规则提供执行证据，首个游戏目标仍为完整 Minecraft Java 1.21.1。

v110 增加[独立汇编提供者包](RUNTIME_PROVIDER_PACKS.md)自动准备。对 schema23 的正常调用栈批次，默认构建并独立校验 `cds-no-archive-v1`、`object-identity-v1`；也可以用开发参数 `-ProviderPack` 提供已校验包。包的原始声明、基础批次／编译器、工具、ABI 和实际 COFF 身份纳入每轮闭包验证。基础 Java 代码生成不重跑，开发诊断选取的 Java 子闭包仍重新汇编。

v110 两侧 `System.initPhase1` 均经过三轮实际执行，自动从原先 516 项 Java 方法准入增至 526 项，越过 CDS 与 Object.hashCode，停在 `Class.getDeclaredConstructors0(Z)[Ljava/lang/reflect/Constructor;`（41460）。该 native 没有 Java Code，诊断不替它创造语义。单独的自动准备验收还完成了原始 CDS 类初始化；它只证明请求的类根完成，不能记作 System 或游戏启动。两侧末轮各保留一个监视器持有，继续按独立进程退出回收，未强制解锁。

## 自动处理过程

1. 保留原始方法、初始化器、完整虚调用／接口表及所有接收者行。已选方法的直接依赖继续自动选择；表中的其他目标先使用明确的诊断停止入口。
2. 在独立进程、项目 `.boom` 工作目录和新堆中运行入口。执行到未选入目标时，汇编记录其类／Code 身份、目标符号及进入停止前的 Context 方法／PC 快照，再设置诊断停止种类 `0xB001`。该快照还不是完整调用栈证明。
3. 目标若已有生成的 Java 汇编，自动选入该声明类中已有的方法，重新链接后在新进程重试。原生声明、未展开协议和未适配运行时 ABI 继续停止，输出精确兼容请求。
4. 每轮独立校验原始函数、类状态、完整分派数据、异常表、实际 COFF 和诊断元数据。已完成轮次可在相同批次与入口下恢复，不重复生成整个 Java 语料。

注册与原生提供量不因诊断停止入口增加。所有映像保持 `diagnostic_only=true`、`source_closure_complete=false`、`game_started=false`；普通闭包校验器默认拒绝诊断映像。诊断停止绕过 Java catch，不能替代 Java 异常或作为交付的接口实现。

## 真实代码与运行时 ABI

选择器现会复制方法所需的原始异常处理表，保留类型、PC 和行数，并从原始单元逐字复核。停止记录与 Context32、Java 字段及正常对象布局分开；Row48／Pool96 仅供诊断。

可用符号来自真实 Runtime DLL 导出、数值内核、正常字符串／类型元数据及已提供的原生模块 COFF。发现例如旧 `boom_mirror_pool` 的未适配依赖时，整个相关方法过程进入 ABI 停止清单；不为它创建伪造池。涉及原生模块数据的已知依赖会选入对应真实模块。

PE 导出读取遵循 [Microsoft PE 格式](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format)。对象、运行时、原始批次、源码助手及 Code 散列均绑定到诊断报告。已有 IR／汇编被复用，方法级机器码缓存仍未实现。

## 本轮执行证据

- 服务器运行了原始 System 类初始化；客户端运行了 System、Float、Character 初始化，均未触发诊断停止。原始 Class.desiredAssertionStatus 的实际 bootstrap 加载器分支已运行；ClassLoader 的未使用分支继续保留停止入口。
- System.initPhase1 经三轮实际执行：首次到达 HashMap.put，第二轮到达属性 getter propDefault，自动选入对应类的已有方法后，第三轮到达未提供的 Unsafe.registerNatives。当前停止原因为需要正常布局 Unsafe 实现，阶段本身尚未完成。
- 两轮 HashMap.isEmpty 选择验证：首轮在实际 HashMap.size 目标停止，第二轮选入源方法后返回 true。该项使用 VM 准备的正常 HashMap 物理形状，没有执行其构造器或类初始化，属于显式夹具。
- 汇编停止机制通过待处理错误保留、外来行／错误元数据、Java catch 绕过、8 工作者 8,192 次调用，以及类初始化失败后重试的安全检查。

Python 115 项测试通过。停止机制另有 19 项原生检查和 8 工作者 8,192 次调用。运行时同时修复了未绑定／不兼容 VM 异常池下再次使用失败类的空指针崩溃；此路径保留原始 NoClassDefFoundError 种类，完整正常 Throwable 物化仍待实现。

v107 补充停止时监视器的记录：非 Java 异常的诊断停止会跳过字节码 finally，因此可能仍持有监视器。只有已经发布的诊断停止、有效堆头、非零持有计数且注册锁空闲时，开发宿主才能保留该快照并交给父进程结束后的 OS 回收；报告明确写出 `heap_cleanup_completed=false` 和 `owned_process_teardown_required=true`。宿主不强制解锁或假装执行了 Java 清理，并拒绝在同一进程继续运行。没有诊断停止的清理失败仍是失败。该机制只供每轮独立子进程的诊断，不是游戏内存管理。

## 开发命令

v101 已越过 v100 的 Unsafe 注册前沿：两侧原始 Unsafe／UnsafeConstants 初始化器通过，共用正常布局汇编服务实际提供 4 个源原生声明，其余 64 个仍未提供。两侧 System.initPhase1 均经四轮执行，自动准入 226 个已有 Java 方法，越过 String.toString 后停在 `jdk/internal/misc/VM.initialize()V`。该接口需要绑定实际时间调整服务，不能用空返回代替。完整阶段仍未完成。

v102 增加 `-SeedDiagnosticDirectory`：从已完成诊断重放实际 Java 准入证据，逐项核对新批次的输入／IR、类身份及原始 Code 摘要后复用选择记录。旧批次对照一轮仍停在缺失 VM 注册；新批次已提供两项 VM 服务，两侧均一轮推进至 Runtime.maxMemory。原生实现量不会因复用而增加，完整阶段仍未完成。

v103 接入 4 项正常 Runtime 资源查询，两侧一轮执行均越过 Runtime.maxMemory，新的实际前沿为 `Float.floatToRawIntBits(F)I`。原始 Java 汇编单元摘要与上一版保持一致；生成方法数不代表启动完成。

v104 接入 Float／Double 四项原始位转换 native。两侧实际执行均自动准入 Character 类中已有的 Java 方法，经两轮推进至 `Unsafe.objectFieldOffset1(Ljava/lang/Class;Ljava/lang/String;)J`。该声明没有 Java Code，字段偏移服务仍需实现；不能将诊断停止函数当成服务。

v106 接入正常 Unsafe 字段查询与实际接收者地址映射，已执行越过 `objectFieldOffset1`；后续 LinkedHashMap 迭代器、Properties 等五类已有 Java 方法由实际路径选择自动准入，不需要手写这些方法。两侧均经六轮执行停在 `Unsafe.compareAndSetInt(Ljava/lang/Object;JII)Z`，其原子内存语义尚未提供。完整阶段仍需继续执行验收。

v107 用类型化堆内存规则统一提供 42 项源 Unsafe native，实际 System.initPhase1 已越过 CAS。两侧各经七轮执行，在原有 375 项准入上自动加入 141 个已有 Java 方法，推进至 `Class.forName0(Ljava/lang/String;ZLjava/lang/ClassLoader;Ljava/lang/Class;)Ljava/lang/Class;`（源方法 41352）。这是尚未提供的正常类加载 native，不能从声明签名自动恢复实现。末轮记录一个持有中的监视器，由独立诊断进程退出回收；完整 System 阶段仍未完成。续跑结果的 `seed_evidence` 字段为空，原始来源证明保存在同目录 `seed.json`，归档状态单独引用该文件。

v108 接入[bootstrap 名字查找与初始化表](NORMAL_CLASS_LOOKUP.md)。两侧都重用 516 项已验证 Java 准入，经两轮实际执行自动加入 GBK 类（14804）的原始初始化描述符与依赖，越过 `Class.forName0` 后停在 `jdk/internal/reflect/Reflection.getCallerClass()Ljava/lang/Class;`（117014）。类别 5 的初始化请求可以自动收敛；它不提供新的原生语义。两个侧的末轮均保留一个停止时持有的监视器，由独立进程退出回收，完整阶段仍未完成。

v108 同时让续跑保留原始 seed 来源，并可从已完成的轮次发布终止报告。跨批次重用会检查真实初始化请求及原始源类身份；旧版遗漏 seed 元数据的结果只在递归重建来源证明一致后恢复。

诊断宿主在执行任何根之前统一检查冷准备状态；一个根通过原始依赖路径初始化另一个请求根是合法行为。检查没有提前标记任何类成功。v110 验证使用 `.boom/assembly-runtime-v109-frames-a` 与独立的两个汇编提供者包。

```powershell
./scripts/Invoke-DiagnosticStartup.ps1 `
  -Batch <已校验的原版批次> -Plan <同一输入的类计划> `
  -ClassRoot 'bootstrap:java/lang/System' `
  -Entry 'bootstrap:java/lang/System:initPhase1:()V'
```

`-ResumeDirectory` 复用已有且完成执行的诊断轮次；每轮仍使用新进程和新堆。`-ReceiverClass` 只供显式对象形状夹具。玩家界面保持启动入口，开发诊断命令不进入玩家界面。

恢复同一诊断目录时，提供者路径、清单内容与独立校验身份必须不变。改变提供者应使用新的运行目录，并通过 `-SeedDiagnosticDirectory` 核对、复用原始 Java／类准入来源。包准备发生在启动准备步骤，不向玩家增加编译按钮；完整玩家启动器集成仍未完成。

v111 增加构造器枚举提供者，默认准备三种家族。`-AllowAdditionalClassRoots` 允许复用同一来源的 Java 准入并增加新的实际初始化根；必须保留旧根及其顺序、保持方法入口不变，扩展信息单独记录，不能把新根当作已经执行。完整 VM 引导仍未实现；反射前置初始化及专项测试的命名模块夹具见[正常构造器记录](NORMAL_CONSTRUCTORS.md)。

诊断子进程发生普通运行时失败时，父进程保存 `runtime_failure`、退出码与 stderr 散列，并保留此前真正完成的诊断轮次及来源准入。它不合成失败轮次的 execution.json，不将普通异常升级为语义停止，也不放宽宿主的堆／监视器清理检查。失败进程不能继续执行，后续使用新目录和来源核对后的种子。

v117 增加 `snapshot-diagnostic-prefix.py` 与 `-SeedResultFile`。快照只读取从 round-000 开始连续完成的轮次，核对来源证明、批次及入口，按实际停止目标重新推导 Java／类准入，写入原诊断目录中的新文件。旧驱动可以继续运行，不改写它的 profile、result 或轮次。新启动仍使用既有种子校验器递归核对全部执行来源及新批次 Code，不复制堆或进程状态，也不复用原生实现。

服务端已用六个完成轮次生成快照，在新编译器批次下核对并复用 943 项已有 Java 方法选择，一轮实际执行推进到 `Signal.findSignal0(String)` 的未实现原生声明。该结果仍不是完整 System 或 Minecraft 启动。`-SeedResultFile` 和 `-SeedDiagnosticDirectory` 互斥，两种种子均不能与恢复同一目录混用。

可选的 `-SourceSelectionDirectory` 使用 `preselect-diagnostic-java.py` 批量选入同一批次、已通过来源校验的闭包中各声明类的可用 Java 方法。每个来源 ZIP、类身份、生成阶段及 Code 可用性均核对；每个类整体纳入额外方法预算，默认最多 16,384 项，可由 `-MaxPreselectedMethods` 调整。它不增加类初始化根、不提供 native，实际映像仍通过原有逐函数来源／COFF 校验。

批量选择保存在独立的 source-only-profile 文件及 `source_only_preselections` 记录中；由真实停止记录推导的 profile 和种子准入列表继续单独保存，不能把提前选入的方法算作已执行。首个真实来源候选一次增加了 15,304 项已有 Java 方法，基于 957 项执行证据推导的准入，七项边界／不改写检查通过。

输出流的同前缀对照已完成来源校验和实际执行：普通映像选入 4,935 个方法，批量预选映像选入 19,687 个方法，两者仍停在同一 `ImmutableCollections` 迭代器 hasNext 目标。扩大已有类的方法没有覆盖后来才引入的接收者类，未减少这次停止；没有据此宣称提速。已保留完整对照轮次并结束后续重复对照，继续推进较小映像及原生语义。功能保持默认关闭。这是构建流程实验，不是游戏侧多核优化。

这套程序自动处理已有翻译产物和可用规则；它尚不能从没有 Java 方法体的声明中创造平台语义。完整 System 启动、Minecraft、隔离世界、自动内存回收和实际游戏侧多核／GPU 优化继续未完成。
