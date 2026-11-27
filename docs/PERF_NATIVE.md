# Perf 汇编接入进度

原版 1.21.1 专用服务器初始化已在纯汇编派生镜像中越过
`jdk/internal/perf/Perf.registerNatives()` 和正常计数器创建，
下一实际停止点为 `java/util/zip/Inflater.initIDs()V`。
**Main 类初始化、Main 方法体、帮助输出、客户端窗口和世界仍未完成。**

长期生成／验证工具为 `scripts/perf-source.py`、`scripts/perf-candidate.py`，
游戏侧实现为 `native/providers/perf_self.asm.inc`，线协议见 `native-config/perf-self-abi.json`。
候选尚未正式纳入提供者清单，额外对象不属于原 35 包的完整来源证明；
原 Class、Code、Frame、候选机器码和派生镜像分别核对，不将旧来源回执改记为新实现已验收。

## 实现和已验证范围

候选从锁定 Azul 21.0.13+1 的原 `Perf.class` 提取七个 native 声明，
与 OpenJDK 21.0.13+3 的原生注册表交叉核对，两个版本的输入身份分别保留。
六项注册表全部验证后发布真实汇编函数指针，后续调用实际读取该缓存。
七个正常 Frame 中，两个时钟方法没有旧停止定义；派生镜像只删除其余五个完整停止过程。

当前汇编后端覆盖登记、QPC/QPF、正常 long 计数器和自身内存接口。
`createByteArray` 与其他进程的 attach 明确返回 Context20，未实现完整 PerfData 兼容。
旧 C 候选曾在错误顺序测试组内观察到 Context7。逐项诊断确认重复名称的消息构造传错池：
原属性工厂接口要求 PORP112／ABI2，C 版传入了其内部的 JSLP80／ABI1。
E 版只修正这一池引用，六组错误均得到真实 IAE／NPE 及预期消息。
来源工具同时核对实际被链接对象中的工厂头、内部字符串池和十条回调重定位。
旧失败和完整清理回执保留，不改记为成功。

Windows 性能计数器的频率和起点在 Java 执行前取得。
`highResCounter` 返回相对于该起点的 QPC 差值，重复登记或 owner open 不重置起点。
计数器使用已有 MainRW owner 实际分配的 1 MiB 区域，原 Java
`DirectByteBuffer(JI,Object,MemorySegment)` 构造器建立 ByteBuffer；宿主不写 Java 字段。
关闭顺序为工作者退出、资源卸载及文件服务 drain，然后释放 Perf 区域，
最后才进行根快照、Java 堆销毁和原 RW owner 关闭。

实际组件已通过原 `getPerf`、冷登记和重复登记、QPF 与 QPC 时间间隔检查、
原 ByteBuffer 的 nativeOrder、原 DirectLongBufferU get/put 和 DirectByteBuffer getLong 的别名读写。
另一次 C 版运行完成 21 组正常 long 用例，包括不同单位／可变性、long 两端值和 Unicode 名称，
随后在异常顺序用例停止。E 版另行验证六组错误和自身 attach／detach：两个新建的原 ByteBuffer
实际共享内存，position 为 0、limit 为区域容量、初始顺序为 BIG_ENDIAN，detach 后其他 buffer 和计数器仍可读。
C／E 的完整机器比较确认只改变一个工厂池重定位，代码、数据、符号、其他重定位及 unwind 保持一致。
因此 21 加 7 项已支持契约由分阶段证据覆盖，未宣称 E 版单次重跑全部 28 项。
另七项字节计数器用例明确返回 Context20，其他进程 attach 及已有 pending Context 的保留也通过检查。
上述组件运行的 Perf、Core 和 VM 清理全部通过。

独立 JDK 对照的 35 组稳定观察在 `-Xint` 和默认模式一致；绝对时钟值跨进程分别记录。
JDK 对照的自身区域为 65,536 字节，AOT 配置为 1 MiB，不宣称这项容量数值相等。
这些记录不代表完整游戏性能、多核加速或自动收集能力。

## 实际原版初始化

221 对象镜像仅替换父镜像的停止对象和进程入口，增加两个 Perf 汇编对象；
其余 217 个对象保持原字节，十三个原生根区的逻辑符号和数量保持一致。
新增系统导入仅为 `GetCurrentProcessId`、`QueryPerformanceCounter` 和 `QueryPerformanceFrequency`。
新对象完整比较代码、数据、节标志、符号辅助记录、全部重定位和 unwind；
独立重链接后的整个 PE 逐字节一致。

实际进程自然退出 86，未超时，三个报告通过协议和 Context 交叉核对。
下一缺失方法为 75476、类 7702、诊断行 132304，
停止时 Context method75621／PC38／depth0，无 pending Throwable 或 VM plan。
System 三阶段完成至 VM4，三个工作者退出并回收，清理标志为 7。
原生内存实际分配／释放均为 3 次，所有租约、活动分配、映射及文件在最终关闭后归零。

此前候选因借用标志未在 Core release 前清零而失败，保留了租约和 VM，未记作清理成功。
C 修订只在两个 release 入口增加标志清零；E 修订再修正一个属性工厂池引用。
七个 Frame 保持不变，各次源码逆变、完整 COFF 和实际行为分别核对。
E 版的原版初始化回归仍停在上述 Inflater 方法，三个报告和完整关闭通过。
主 agent 使用正式工具重新生成两对象，其汇编源码逐字节、完整 COFF 与实际运行的 E 版一致。

开发命令 `python scripts/perf-candidate.py build --help` 列出源状态、原 Class 选择、父镜像、
锁定原生源码、JDK release、ABI 和汇编工具参数。输出必须是新的 `.boom` 目录；
`verify` 会重新推导原始来源并独立汇编，既有候选不会因此获得完整原版或提供者验收。
工具来源版本变化后，旧状态应被拒绝，需先完成新的来源验证。

| 本地验证证据 | SHA256 |
| --- | --- |
| JDK 两模式／35 组观察 | `f6bafa52bfabb062b52ccb88d57a0bf3c53e3c17720ef7b5c301747d2ebba2bf` |
| C 候选独立来源及第三次完整 COFF | `02d1a18f60d382fc5b598ed7966c7e33dc2470d0f3ffe4d6c9f80ceed4d6e13f` |
| 实际组件／登记、时钟及原 LongBuffer／关闭 | `6552ed1e3fad2c539d65cb38e6e1a9f33a3506de1edac9b90e10456d696b44c8` |
| 21 组正常用例后异常路径失败／完整清理 | `c5556544c403858453d0c5588740bda6e6a7f6f2f7722c22c32469b1ce5dc3af` |
| 逐项诊断／实际 ABI1 错误与 ABI2 正常工厂 | `927411307f483f8ac5ad75bde1158d64a0e28a91253c94c417c94782849e4ff0` |
| C 到 E 完整机器差异／唯一池重定位 | `dde6dee63b71e6c84e286da4598d5f4adfe1b662602258fd688e4c86c2019921` |
| E 六组错误、自身内存及未支持边界／关闭 | `f6b856dd40b7876f75967cc9e639c9e1f89cf854e679e2ec4a0499ea6238b0c7` |
| 主 agent 正式工具重新生成与完整来源检查 | `7d95426340bf4ca9377cec15787b3d37b667f67cd9aaa92ddd608f9e3358fc78` |
| 正式工具新对象与实际 E 版完整等价 | `ca33deacd8452be159c494eaea356982e71e67f55ab2247721482ca488492983` |
| E 版 221 对象来源及链接检查 | `5362bd0ed9db1780f353fb4bd34df176003acc37a735adcda1006ca708248851` |
| E 版独立完整 PE 比对 | `730375a4a525345aec008ff4b09d44cf267da4535e3e2aae98f03fd2bb59a933` |
| E 版实际原版初始化／三个报告／关闭 | `d380852895aca1315cd58c97f0c17189ecdcf6a2ee6e785b02254a576fd79fd1` |

全部原版输入、生成产物、PowerShell 和一次性 Python 驱动继续保留在本地忽略目录。
