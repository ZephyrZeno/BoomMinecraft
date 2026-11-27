# 原 Method.invoke0 的有界候选

当前代码为未注册的独立候选，覆盖锁定 JDK 21 的两个原 native 声明：
`DirectMethodHandleAccessor$NativeAccessor.invoke0` 和
`NativeMethodAccessorImpl.invoke0`。两项原签名均为
`(Method,Object,Object[])Object`，访问标志为 private static native。
候选未改变当前 107 工具清单、31 个正式 provider、runtime572、原 Java Code
或虚表，也未从宿主注入 Java 字段、缓存或预设类初始化状态。正常字段写入和类初始化
由原 Java 与普通 native 协议执行；本候选不是完整反射调用或 Minecraft 启动证明。

`method-invoke-source.py` 动态读取原 Method 的 clazz、slot、name、returnType、
parameterTypes、modifiers 字段及实际布局，槽号采用与正常方法枚举候选相同的
原 classfile method-table 命名空间。它核对原 class SHA、Code SHA、native frame、
String value/coder 布局、类型目录和普通 Class mirror。server 中的方法编号只属于
本批证据，不能成为跨 plan 的 schema 条件。该目录没有按枚举名或类名分支。

首个切片仅支持无参数、static、具有原 Java Code、返回引用或数组的方法。
static receiver 按原 C 语义忽略；参数数组可以是 null 或正常的空引用数组。
非空参数数组调用原 IllegalArgumentException(String) 构造器，消息为
`wrong number of arguments`。实例调用、primitive 返回、装箱、拆箱、参数拓宽、
virtual/interface 派发、native target、caller-sensitive target 均不在本切片范围，
保留明确的 Context20。无效普通对象或外堆指针由 heap/type 协议拒绝。

每个可调用项必须同时属于实际选入的 class 和 Java Code 集，并再次核对原 SHA。
已编译不代表已选入。普通 class ensure 在参数数量检查和 target 调用前执行；
类初始化异常直接传播。仅 target body 产生的实际 typed Throwable 会经原
InvocationTargetException(Throwable) 构造器包装，cause 身份保留；Context20、
源码诊断和结构错误不会变成 ITE。所有 Java upcall 使用原方法入口和普通 native
frame，内部调用保存并恢复 MXCSR。当前最小 native 依赖为正常 Throwable family；
普通 Method 生产组件和默认 Class/Enum API 还分别需要正常 Methods 和 CP 路径。

默认路由并不由 VM.initLevel 推导。锁定源码中的
`VM.isJavaLangInvokeInited()` 读取独立的 `javaLangInvokeInited` 布尔值；其唯一
Java 写入者位于 MethodHandleNatives 冷初始化链。真实 System1/2/3 → VM4 进程
只读观察为 false，MethodHandleNatives 仍为冷状态。未设置
`jdk.reflect.useDirectMethodHandle` 或 `jdk.reflect.useNativeAccessorOnly`。
因此本 runtime 当前自然路径可以到 NativeAccessor，但不代表完整 JDK 的 MH
初始化已经实现。Method.invoke 的 caller-sensitive、访问检查和 accessor Java
完整保留。即使原 values 方法无 annotations，Executable.declaredAnnotations
仍先调用 Class.getConstantPool；不能用空注解缓存略过这一真实前置。

组件复用 current107 的新正常 Method source/COFF 候选和实际 API 镜像。其 Java
闭包来自历史已验完整选择，并通过当前完整 named-batch 严格等价接口重新核对；
`historical_full_selection_reused=true`、`current_full_selection_reverified=false`。
不把此复用改称新的 current full-selection V。除两项 invoke0 原 stop 外，原闭包
Java、类状态和 COFF 原样保留。

历史闭包并未为目录中每个未选方法生成 lazy stop。组件据原 shard 的完整 method
行、class/Code SHA 和普通 diagnostic-closure 规则建立额外的独立命名空间诊断表。
其 helper 指令和数据仅重命名公开诊断符号，实际目标不变；它不新增 Java Code、
类根或成功入口。这张表不是旧 full-selection proof 的组成部分，当前 controller
不得据其自动准入。正式选择器将来必须显式生成、验证、消费同一类 pending 目标。

默认 API、直接 native 组件、JDK oracle 和静止回收的结果分别记录。JDK 仅在项目
忽略目录运行参考源码。运行中的普通 Java、native、异常构造、线程和收集器均为
MASM。显式收集只发生在所有外部工作线程 join 且没有活动 Java frame 后，使用
同一镜像的 source/native/primordial spans，并单列暂存测试 oop。它不证明自动或
并发 GC，不覆盖未来活动 frame、线程栈和任意 pending Context 的运行期根协议。

`source-bound-v159-e` 的独立源/frame/实际 COFF 回执为
`.boom/method-invoke/source-bound-v159-e/verification.json`，SHA256
`47500fd278c7172f88ef798b7bceba5247bc3d4b0e83a283b00aceb5427e4ba3`。
6768 个原静态零参数引用返回项来自原声明与 Code；规范 ASM 的非调试全部节、符号、
重定位及 unwind 与实际 COFF 相等，机器摘要为
`378a17b24c2b5cdb6b77908e1d16359207edaf77390824e669fd7fab00a69c02`。
实际选择能力表另绑定本次封存的原 Java 闭包，未选择项没有成功入口。

实际冷执行 `.boom/method-invoke/execution-v159-f/execution.json`，SHA256
`63dc22c6bd1aba1ae8ae7c0265b4572378760e5dfc38a9e8d93512d303d189c4`；
第二个独立 OS 进程在相同只读 DLL/COFF 输入上创建新的堆和原 primordial Thread，
回执 `.boom/method-invoke/execution-v159-g/execution.json`，SHA256
`a67d9a6b86307af0cb89041f6159e8074203ba54ac06901f18f307582ad6c792`。
两轮均实际通过：两个 invoke0 分别调用原 Optional.empty、Collections.emptyList、
System.getSecurityManager 和 StackWalker.Option.values；普通对象、null、实际 typed
数组、独立 clone 与原 Enum.name 对齐。原 Class.getDeclaredMethod → Method.copy
生产所有 Method，未宿主构造或修改 Method。

另验证 static receiver 忽略、空/null 参数数组、原 typed IAE、坏指针/错类、非 static
和 primitive 返回的显式 Context20，以及既有 pending Context 八个 DWORD 完整不变。
原 VM.getSavedProperties 在尚未执行 Phase1 的组件中自然抛出 ISE；两个 native 均调用
原 ITE 构造器，原 getTargetException 和 ITE override getCause 返回相同 cause，原
getMessage 为 `Not yet initialized`。每轮 8 个实际 OS 线程共 512 次原 Java target
调用，无 Thread.start 已通过的推论。四轮静止回收 freed 为 `[283,1,1,0]`，保根后
Method/返回图存活，释放独立暂存根后正常回收；每个物理 span 的 cell 数、非空数、
原样快照 SHA、去重前后数量和完整集合摘要均在回执中。

组件没有执行完整 Phase1，仅调用原 System.setJavaLangAccess API 准备默认 API 的
JLA。原 Class.getEnumConstantsShared 随后实际停在原 Class.getConstantPool native，
caller 为 Executable.declaredAnnotations 的 pc53；返回 Context B001，不是 API 成功。
停止后按 runtime572 现有 monitor_abort_owned 协议清理该线程的两个实际 monitor
acquisitions：只接受 fully unwound B001/depth0/no-pending，Context 逐字节不变；
这属于受控 VM abort，不当作 Java monitorexit。Thread/FLS detach、trace 释放和堆销毁
均成功。未用 host field、缓存、property 或初始化状态写入来越过默认 API。

两轮完整 JDK 对照分别是
`.boom/method-invoke/oracle-v159-c/result.json`，SHA256
`46222c7b02b7edc9423ae145a80dea04ae6cc4de04d208605f98743ab84b40f5`，及
`.boom/method-invoke/oracle-v159-d/result.json`，SHA256
`fb9fcb409aa30861ea67d942ee85622fc0fd221592c7888d960f9d38ea19347f`。
SDK 的 lib/modules 必须与原输入 catalog 的 size、SHA1、SHA256 全等；同时封存 java、
java.dll、jvm.dll、src.zip 和 release，并核对运行前后。参考 JVM 的两个私有 native
通过 8 个返回值对照、空参数/receiver 行为、8 个 arity 参考观测及两次 ITE cause 参考。
ASM 的 arity 实测为一次；ITE 的 ASM target 是原冷 VM 方法，JDK target 则是隔离参考
源码中的显式 throwing fixture，两者不混称相同 Java body。未设反射选路 property；
`--add-opens` 只用于隔离参考 JVM 观察私有 native，不进入生产参数。

默认路由只读进程证据保留在
`.boom/method-invoke/route-probe-v151-d/result.json`，SHA256
`2510bae27e315280ad33cf7f6e59b427ba5d93afe1a3367aab499171024ca19f`。
历史 7 个选择能力测试日志为 `.boom/method-invoke/unit-v159-a/tests.log`，SHA256
`d4096016f94b3e2f854d42c86eca1d620c32a0e1545d3bdfb4b98c0627fef27a`。

首败均保留：`execution-v159-a/link.log` 是 344 个未选 source 目标缺 lazy stop 的链接
失败；后续独立进程在旧 c/d 模型中发现未排序的 Java callback 列表/ID 列表，严格拒绝
source model，不进入 guest，e 对两列表统一确定排序且 COFF 语义不变。
`execution-v159-d/execution.json` 保留基类 Throwable.getCause 直调而非 ITE override
造成的测试 false；`execution-v159-e/execution.json` 保留未准备 JLA 的 Context4 和
监视器/堆清理拒绝。没有改 kernel 掩盖这些失败。最初 oracle-v159-a 是参考 JVM 的
独立历史观测；后续版本字符串检查曾在 JVM 执行前拒绝 vendor 的 `21.0.13.0.3`
命名，最终改为原 catalog 的完整三项物理摘要，未放宽映像身份。

可复验命令（必须使用新的隔离输出目录）：

```powershell
D:/Dev/Python312/python.exe scripts/method-invoke-candidate.py --state .boom/formal-native-transitions/manifest107-31-v157-a/pending-state.json --assembler D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe --output .boom/method-invoke/review-source
D:/Dev/Python312/python.exe scripts/test-method-invoke.py --candidate .boom/method-invoke/review-source/candidate.json --methods-images .boom/normal-methods/root-current107-execution-v159-a/images.json --allow-equivalent-batch --output .boom/method-invoke/review-execution
D:/Dev/Python312/python.exe scripts/test-method-invoke-oracle.py --execution .boom/method-invoke/review-execution/execution.json --output .boom/method-invoke/review-oracle
D:/Dev/Python312/python.exe -m unittest discover -s tests -p method_invoke_source.py
```

当前真实范围为未注册的两个原 invoke0 有界 native 组件；默认 Method.invoke、
Class.getEnumConstantsShared/EnumSet 和完整反射 API 仍未通过，CP 前置已如实保留。


冻结版本另加强 source candidate 的 schema/family/未注册状态检查，以及声明的 exports、
imports 必须与规范实际集合完全相等。9 个当前边界测试覆盖这些拒绝条件，日志
`.boom/method-invoke/unit-v159-b/tests.log`，SHA256
`42c7890a01328fff2d95981a049d35deae0520bf725b1d4bcf2e271e5c2d6c1c`。
新 source 为 `.boom/method-invoke/source-bound-v159-f/candidate.json`，当前 proof
`.boom/method-invoke/source-bound-v159-f/verification.json`，SHA256
`b1a1de6d6396a1a43e4db82c645b7f15be8cd2b956dbc5349f1bcae422cb7e84`。
全部 ASM 指令/数据和规范机器摘要继续与前述版本相同。

加强工具后的完整新链接/冷执行为
`.boom/method-invoke/execution-v159-h/execution.json`，SHA256
`ba3d98c70fdf7096d161cc3b833a5cd0d8514ea0dc1f21f3b92cdac625138900`；
第二个新 OS 进程为 `.boom/method-invoke/execution-v159-i/execution.json`，SHA256
`6626af0f61ac253ac84e5f4a5da32bbbe37fb45bdf2f03232ae732ea0225fd94`。
两轮均完整通过上述原 Java/native、8OS512 调用、4GC、typed 异常和受控 cleanup，
默认 API 的真实未完成边界仍为 Class.getConstantPool，不变成成功。
对应 JDK 聚合证明为 `.boom/method-invoke/oracle-v159-e/result.json`，SHA256
`3015df19dec0e2b92f464ad965695ce9f13a1f88e0d17a721e7fe75ec51b24ee`，以及
`.boom/method-invoke/oracle-v159-f/result.json`，SHA256
`eaeb5be0e73ab9e78d8cb99a4bfdec0c00ab32b9c68d84530643cc10104e3aaf`。

实际 executable COFF 字节变异测试先通过原 positive control，再仅复制并翻转
`.text$mn` 第一字节，更新副本 object 的摘要后调用原完整 source/COFF verifier。
它确实到达非调试指令/数据/relocation 比较并拒绝，未链接或执行变异对象。
当前工具为 `scripts/test-method-invoke-negative.py`；回执
`.boom/method-invoke/negative-v159-c/result.json`，SHA256
`5fcc775c29f4d5bf61390cb4b5ee6f12f57938e9f121c70aee4058b3dab00c15`。
第一轮只查 `.text` 的测试假设不适用实际 MASM `.text$mn` 节，已保留空输出目录
`negative-v159-a`，未修改原 kernel 或原 object。独立复验负例命令为：

```powershell
D:/Dev/Python312/python.exe scripts/test-method-invoke-negative.py --candidate .boom/method-invoke/review-source/candidate.json --output .boom/method-invoke/review-negative
```

Root 独立复验直接使用冻结 f candidate 和当前107的正常 Method 镜像，在新的
`.boom/method-invoke/root-execution-v168-a` 中重新做完整 source/frame/实际COFF
验证、链接和冷进程执行。回执 `execution.json` verified=true，SHA256
`65530511d0172eda9de368c89475ecd309f33b03fbcef3b939ad730a21280a2f`。
两个 native 的原 Java target、typed 异常、8OS512 调用、四轮静止 GC 和完整清理
均通过；默认原 Class API 仍精确停于 CP，不计 API 成功。
独立 JDK 对照 `.boom/method-invoke/root-oracle-v168-a/result.json` 同样通过，
SHA256 `ceb77c11809480fdd95346918447f7bc45cc51aa44f054a926a1add4404f47c4`。
Root 另行通过全部9项源选择／候选边界单测，并在提交前核对8份冻结源和9份
组件／oracle／负例证据的实际大小及 SHA256；仅此说明在复验后追加。
