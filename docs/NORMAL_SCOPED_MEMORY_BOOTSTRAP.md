# 正常 ScopedMemoryAccess 引导

v116a 的两侧来源／COFF 校验通过，但实际 System 均返回 VerifyError：数据中的 `OFFSET boom_scoped_close_unavailable` 是调用方导入跳板的地址，与运行时校验使用的真实导出地址不同。失败记录保留，不计为注册成功。v116b 的汇编服务改从 `__imp_boom_scoped_close_unavailable` 读取 IAT 中的规范地址，并以 CAS 发布到初始为零的目标单元，再调用原有注册内核。相同汇编代码的独立 IAT 测试通过八工作者 16,384 次并发调用及 10 项错误／异常保留检查；完整源入口仍另行验收。

接通文件／字节序绑定后，两侧原始 System.initPhase1 各经过三轮实际执行，自动 Java 准入由 641 增至 692，停在原始 `jdk/internal/misc/ScopedMemoryAccess.registerNatives()`。该入口是初始化缺口，完整 System 和 Minecraft 仍未启动。

`normal-scoped-memory-registration-v1` 重新读取锁定的 java.base 原始类，核对类身份、完整方法清单和仅有的两个 native：私有静态 `registerNatives()V`（0x10a）及实例 `closeScope0(MemorySessionImpl)Z`（0x100）。一个通用规则只接入前者；后者不计入已实现数量。

提供者生成可变的 SCNP32/1 注册池。汇编 `boom_scoped_native_register` 检查标识、版本、条目数、保留字段和关闭目标，再以原子操作发布状态 2；重复注册保持同一目标。原始 Java 初始化器继续取得 Unsafe、构造 singleton 并发布原始静态字段。初始化代码、getter 和内存访问 Java 方法均由自研后端生成汇编执行。

当前关闭目标明确指向 `boom_scoped_close_unavailable`，调用得到未满足链接错误；源 `closeScope0` 不提供正常执行绑定。完整关闭需要检查参与线程的作用域访问和会话引用，[OpenJDK 21 的实现](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/scopedMemoryAccess.cpp)对此执行线程握手。本项目的线程握手、栈根和安全点尚未完成，注册通过不能证明会话可以安全关闭，也不能当作完整 foreign memory 支持。

两侧已经通过原始声明重建、规范汇编与实际 COFF 导入／定义校验。`Test-NormalNativeSource.ps1 -Mode scoped-memory` 用于独立检查原始冷初始化、singleton Java 构造与 getter、错误表拒绝及并发注册；执行结果以独立测试记录为准。构建和来源校验不计作这些执行测试通过。

两侧原始入口执行验收已通过：八工作者争用冷初始化、原始 singleton 构造、通过原始 Buffer 初始化器调用 getter、10 项错误检查及各 8,192 次并发注册。实际 System 启动也已越过注册，进入缓冲区 limit 方法的自动选择。关闭会话仍未提供，以上结果不计作完整 System 或游戏启动。
