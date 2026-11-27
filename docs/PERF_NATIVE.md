# Perf 汇编接入进度

原版 1.21.1 专用服务器初始化已在纯汇编派生镜像中越过
`jdk/internal/perf/Perf.registerNatives()` 和正常计数器创建，
下一实际停止点为 `java/util/zip/Inflater.initIDs()V`。
**Main 类初始化、Main 方法体、帮助输出、客户端窗口和世界仍未完成。**

这是尚未正式纳入提供者清单的原生候选验证记录。额外对象不属于原 35 包的完整来源证明；
原 Class、Code、Frame、候选机器码和派生镜像分别核对，不将旧来源回执改记为新实现已验收。

## 实现和已验证范围

候选从锁定 Azul 21.0.13+1 的原 `Perf.class` 提取七个 native 声明，
与 OpenJDK 21.0.13+3 的原生注册表交叉核对，两个版本的输入身份分别保留。
六项注册表全部验证后发布真实汇编函数指针，后续调用实际读取该缓存。
七个正常 Frame 中，两个时钟方法没有旧停止定义；派生镜像只删除其余五个完整停止过程。

当前汇编后端覆盖登记、QPC/QPF、正常 long 计数器和自身内存接口。
`createByteArray` 与其他进程的 attach 明确返回 Context20，未实现完整 PerfData 兼容。
异常路径也尚未验收：当前 C 候选在错误顺序测试组内观察到 Context7，未完成预期异常匹配；
该回执没有逐项保存组内结果，不能据此判定具体失败用例。失败和完整清理回执已保留。

Windows 性能计数器的频率和起点在 Java 执行前取得。
`highResCounter` 返回相对于该起点的 QPC 差值，重复登记或 owner open 不重置起点。
计数器使用已有 MainRW owner 实际分配的 1 MiB 区域，原 Java
`DirectByteBuffer(JI,Object,MemorySegment)` 构造器建立 ByteBuffer；宿主不写 Java 字段。
关闭顺序为工作者退出、资源卸载及文件服务 drain，然后释放 Perf 区域，
最后才进行根快照、Java 堆销毁和原 RW owner 关闭。

实际组件已通过原 `getPerf`、冷登记和重复登记、QPF 与 QPC 时间间隔检查、
原 ByteBuffer 的 nativeOrder、原 DirectLongBufferU get/put 和 DirectByteBuffer getLong 的别名读写。
另一次运行完成 21 组正常 long 用例，包括不同单位／可变性、long 两端值和 Unicode 名称，
随后在异常顺序用例停止。该运行的 Perf、Core 和 VM 清理全部通过。
尚未完成自身 attach/detach 的全部行为测试，不能把这些记录称为 28 或 35 组兼容测试全过。

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
C 修订只在两个 release 入口增加标志清零；源码逆变、七个 Frame 和独立完整 COFF 核对通过，
随后才得到上述正常初始化和完整关闭结果。非法参数的 Context7 问题仍单独保留。

| 本地验证证据 | SHA256 |
| --- | --- |
| JDK 两模式／35 组观察 | `f6bafa52bfabb062b52ccb88d57a0bf3c53e3c17720ef7b5c301747d2ebba2bf` |
| C 候选独立来源及第三次完整 COFF | `02d1a18f60d382fc5b598ed7966c7e33dc2470d0f3ffe4d6c9f80ceed4d6e13f` |
| 实际组件／登记、时钟及原 LongBuffer／关闭 | `6552ed1e3fad2c539d65cb38e6e1a9f33a3506de1edac9b90e10456d696b44c8` |
| 21 组正常用例后异常路径失败／完整清理 | `c5556544c403858453d0c5588740bda6e6a7f6f2f7722c22c32469b1ce5dc3af` |
| 221 对象来源及链接检查 | `d18dd7ee1672fd7c8994f78c70b4bac2a9b0804181f650c0608f749d65cea622` |
| 独立完整 PE 比对 | `c9b07e72f9071bf297128a2c8e2e1799cff848066336fd7be35c708282fd1542` |
| 实际原版初始化／三个报告／关闭 | `d07cf602d455fb395e676a6acf015c4bdbc75b6ba6323e1ef3ddb02507c6af46` |

全部原版输入、生成产物、PowerShell 和一次性 Python 驱动继续保留在本地忽略目录。
