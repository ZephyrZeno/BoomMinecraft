# AtomicLong 的 CX8 能力查询候选

该独立候选只实现原 `AtomicLong.VMSupportsCS8()Z`，尚未注册正式族或修改 runtime DLL。声明、方法号、类号和原生帧从当前已验来源动态读取；本批为 70380 / 7012。原 `<clinit>` 70417 的 Code 摘要保留，并验证其 PC 0 调原 native、PC 3 用原 `putstatic` 发布 `VM_SUPPORTS_LONG_CAS`。宿主不写该字段或类初始化状态。

锁定 `jdk-21.0.13+3` 的 [AtomicLong.java](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/classes/java/util/concurrent/atomic/AtomicLong.java) 与本地锁定 src.zip 完全相同。[AtomicLong.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/AtomicLong.c) 调 `JVM_SupportsCX8`，后者取 VM 的 CX8 支持结果。通用 x86 初始化从 CPUID.1:EDX[8] 建立特性位；[x86 构建定义](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/cpu/x86/globalDefinitions_x86.hpp) 启用 `SUPPORTS_NATIVE_CX8`，使本目标的原 getter 依赖 ISA 保证返回真。不能把这个构建条件描述成所有 x86 JVM 每次都动态查询。

汇编仍先执行 CPUID.0 核基本叶上界，再执行 CPUID.1 检查 EDX 第 8 位；合法目标返回真实检测的 1。缺少叶 1 或 CX8 时以 Context20 停止，不返回并声称等价的 Java false。ECX 第 13 位的 CMPXCHG16B 不参与该判断。内核保存 RBX，并有实际 x64 unwind；不分配内存、保存 Java oop 或提供 CAS 操作本身。

源候选构建与独立验证：

```powershell
D:/Dev/Python312/python.exe scripts/atomic-long-cas-candidate.py build --state .boom/formal-native-transitions/manifest107-31-v157-a/pending-state.json --output .boom/atomic-long-cas/source-bound-v188-a
D:/Dev/Python312/python.exe scripts/atomic-long-cas-candidate.py verify .boom/atomic-long-cas/source-bound-v188-a/candidate.json
D:/Dev/Python312/python.exe scripts/test-atomic-long-cas.py --candidate .boom/atomic-long-cas/source-bound-v188-a/candidate.json --output .boom/atomic-long-cas/execution-v188-a
D:/Dev/Python312/python.exe -m unittest discover -s tests -p atomic_long_cas.py -v
```

已有 `source-bound-v188-a/verification.json` 真通过原来源、Frame8 和规范 ASM 实际重汇编比较；机器合同包含全部非调试 section、flags、完整符号辅助记录、归一重定位和 unwind。`execution-v188-a/execution.json` 实际运行的独立内核与 provider 服务机器字节相同：8 个真实 OS 线程共 2048 次、64 次 RBX 守恒、错误池/操作及完整 pending Context32、锁定 JDK 私有 native 与原缓存字段对照均通过。另 8 个仅测试用的合成 CPUID 叶组合验证不存在叶、缺 CX8、仅有 CX16 等边界；这些替换对象不进入 provider。

该独立测试执行内核 ABI，不包含原 Java `<clinit>` 的 ASM 执行。原 Java 初始化与静态字段发布留给同源 NIO 派生组件验证；源预选、独立 JDK oracle、原生内核测试均不计为完整 Minecraft 或完整 JVM 启动。

主 agent 独立生成 `root-source-v191-a` 并再次完成源、原生帧和完整机器校验，回执 SHA256 为 `fb56385854b209daa47452a69f0e40bed82561110fa265dde539bbf7c2bfc27e`。全新 `root-execution-v191-a` 重跑全部硬件、并发、ABI、协议、合成叶边界和 JDK 对照通过，回执 SHA256 `fc17e5d4b2dbad7b19824b9cac95b341def7bf899a8abfa037bbb419999d4b9e`；7 项来源与实际 COFF 负测也独立通过。

额外 `root-jdk-reference-v191-a/verification.json` 的 SHA256 为 `1fb5782c22498441f5d45d80a4d67f0b221f32cbe93bc4d34d162f55c4a48454`。该复核在原 JDK 再次执行 reference 前后分别封存 java/javac、jvm.dll、modules 和 release，确认 21.0.13 版本及 modules 的原锁定 SHA256；native 与原 Java 缓存布尔值仍一致。此补充仅加强开发 oracle 的工具身份记录，原 Java 初始化执行范围保持上述限制。
