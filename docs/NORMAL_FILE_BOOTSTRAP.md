# 正常文件流与描述符引导

Minecraft 目标保持 Java 版 1.21.1。原始 System 启动诊断在接通反射构造器后，两侧各自动推进两轮，Java 准入由 636 增至 641，执行 GBK 原始构造器后到达 `java/io/FileInputStream.initIDs()`。这是实际执行前沿，完整 System、Minecraft 和世界仍未启动。

## 同一规则接入六个原始声明

`normal-file-bootstrap-v1` 从锁定的原始 java.base 类读取 native 声明和正常字段布局，统一提供：

- FileInputStream、FileOutputStream 的 `initIDs()`。
- FileDescriptor 的 `initIDs()`、`getHandle(int)`、`getAppend(int)`。
- StringUTF16 的 `isBigEndian()`，用于相同启动路径所需的字符表示引导。

输入／输出流注册各自原始 `fd:Ljava/io/FileDescriptor;` 引用字段。描述符注册原始 `fd:I`、`handle:J` 和 `append:Z` 标量字段，保留声明类、字段序号、访问标志、实际偏移、宽度与引用前缀边界。不是空的 initIDs 成功桩。

注册表复用本项目已有的纯汇编 `boom_stream_fields_init`、`boom_stream_descriptor` 和 `boom_fd_service`。新 `file_bootstrap.asm.inc` 通过 NFIO48/1 池路由六种操作；表由真实汇编原子发布，重复注册必须保持同一个来源表。两个流池各为 32 字节，字段表各为 32 字节；描述符池为 32 字节，字段表为 48 字节。

首次五项绑定的实际启动验证在两侧越过 FileInputStream.initIDs，进入 StringUTF16.isBigEndian 的共享依赖。第六项以汇编写入一个 DWORD 后观察首字节来查询本机字节序；Windows AMD64 结果为 little endian，不用开发宿主代替游戏判断。原始 StringUTF16 初始化器负责设置其 HI／LO_BYTE_SHIFT 字段。

Windows 标准描述符 0、1、2 查询对应的 `GetStdHandle`，其余整数返回 -1；append 查询返回 false。这与原始 [FileDescriptor Windows 实现](https://github.com/openjdk/jdk21u/blob/master/src/java.base/windows/native/libjava/FileDescriptor_md.c)及 [SET_HANDLE 映射](https://github.com/openjdk/jdk21u/blob/master/src/java.base/windows/native/libjava/io_util_md.h)一致。字段注册语义对应 [FileInputStream](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/native/libjava/FileInputStream.c) 和 [FileOutputStream](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/native/libjava/FileOutputStream.c) 的源初始化器。

本家族没有提供文件打开、读取、写入、同步或关闭的 Java native；这些操作继续保留明确缺口，不能从旧汇编内核存在推断其已接入正常启动。

## 已验证的范围

两侧均完成原始声明／字段重建、汇编与实际 COFF 导入／定义校验。内核执行测试分别通过三个注册表、八种描述符输入、11 项错误检查及八工作者 24,576 次并发调用。测试在真实汇编堆中使用正常来源布局的对象和明确的注册表夹具，Windows 句柄结果与同进程系统 API 对照。

上述内核测试没有调用六个 Java native 包装入口，也没有执行 FileDescriptor 或流的 Java 构造／初始化器。独立的 `Test-FileBootstrapSource.ps1` 则在两侧已经通过六个原始 native 入口、四个原始类的冷初始化、三份标准描述符的原始 Java 构造、八种描述符输入、UTF16 字节位移和各八工作者 24,576 次并发调用。测试没有预置 Module 或 FileDescriptor 对象；初始化顺序为 FileDescriptor → FileInputStream → FileOutputStream → StringUTF16，遵循原始 System.initPhase1 先取 FileDescriptor.in 再构造流的前置关系。

两次先前失败继续保留：五项版本停于未提供的字节序查询；六项版本先初始化输出流时，经 SharedSecrets 进入 Reflection.registerFieldsToFilter 的静态同步包装，暴露旧 boom_mirror_pool 与正常 Class 对象的 ABI 缺口。调整测试前置顺序没有修复这个桥接问题，其他冷初始化顺序尚未通过。以上检查也不计作完整 I/O、System、游戏启动或游戏侧多核优化。

## 校验调用链的复用

六组提供者的单进程校验可以共享刚读取并完整散列核对的 batch／plan 快照。调用结束前再次核对五项共享输入的真实散列，并检查 Python 快照未被修改。退出、异常或批次不匹配都清除上下文；后续进程和独立执行前校验重新读取来源。

构造器元数据及调用元数据共用同一次输入重建，避免在同一个调用中重复读取类型和来源层次。两侧 67,407／75,305 条构造器调用记录与优化前逐项相等。五项新增测试检查快照修改、磁盘变化、跨批次与嵌套上下文的拒绝；不使用持久 verified 标志恢复进程内状态。

`revalidate-runtime-provider-cache.py` 可把本项目原有的 ASM、COFF 和数据复制到新的缓存接受目录，保留生产者清单、原工具身份和原验证记录。当前校验器随后重新重建全部源契约、元数据、规范汇编和 COFF 导入／定义；所有检查和共享来源退出检查通过后，才写新验证记录并发布整组缓存。旧包及其证明不改写。两侧各五组现有提供者已经这样复用，十组 ASM／COFF 的字节和散列保持不变。旧 verified 标志不能单独发布新成功记录。

类加载器、变换链、原始类／字段、布局、注册池 ABI 或导入汇编内核发生变化时，相关结果必须重新校验。模组兼容和动态重定义尚未实现。
