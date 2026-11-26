# 正常堆上的 Windows NIO 查询候选

开发候选将原始 Unsafe 缓冲区分配、char[] 复制、受跟踪的本机内存读写和 Windows 元数据查询连接到自研汇编服务。原始 String、WindowsFileAttributes 构造和分类方法继续执行编译出的 Java 汇编。所有本机地址访问要求属于本候选持有的分配，并在范围检查和生存期保护下完成。

`nio_owned_buffers.asm.inc` 使用全局共享锁保护分配链的生存期，再按地址顺序锁定输入、输出所在的分配块。同一块只加锁一次；查询期间释放操作必须等待。不同缓冲区的查询可以同时进入实际 Win32 API。原始 WindowsException 构造器在释放锁后调用，保留真实错误码。

`nio_dispatcher_ids.asm.inc` 登记原始 WindowsNativeDispatcher 所需的二十项字段映射。`reference_referent_read.asm.inc` 在当前非移动、静止点回收契约下读取实际继承的 referent 字段，并检查对象与结果的堆归属。`win32_library_name.asm.inc` 生成 Windows 库名，使用正常 String 布局并通过锁定 JDK 对照。

## 执行证据

已在隔离候选中实际执行原始 Unsafe 单例初始化、分配/释放、String/char[]、WindowsFileAttributes.fromFileAttributeData 和 isRegularFile。锁定 lib/modules 返回普通文件，真实目录返回非普通文件；缺失路径经真实 WindowsException 返回系统错误 2/3。SoftReference 构造和 get0、清除后的读取、错误对象与外堆对象也分别测试。

并发测试阻塞第一条真实文件查询，同时确认另一分配块的实际目录查询已完成。它还覆盖 query/free 租约、同块路径和结果，以及八个系统线程的四百次反向双块查询。正常查询、原始异常和失败后剩余本机分配为零均有记录。这些结果说明查询能重叠，尚无游戏帧率测量。

v145 的 `formal-selection` 模式已在同一正式 22 包输入上完成源码重选、独立闭包验证及上述实际执行。它直接使用已验证的 UFL2 字段池、正常 JCLS 模块表和正式 BootLoader provider；实际链接响应中 JCLS 对象恰好一次，没有使用旧字段或模块候选替换。旧诊断模式的执行回归同时通过。

首份正式记录在 `.boom/nio-file-formal-v145-843059c86002430db66798e01269045e/provider-1/execution-e4e3b758ba3f4d29937d0e6c20ac8d42.json`，SHA256 为 `3c74bb1e0c93ea4ea86a8f57040ba6b16fe90a8f450e57a5f3281815ea2d8bec`。它包含 5,138 个选入 Java 方法和 1,162 个类的独立选择；选入数量不代表这些方法均已执行。

## 当前边界

独立原生查询及原始 Java 后段的成功分别记录。严格的 VM 初始化顺序会在 System.initPhase1 未完成时立即停止。正式 22 包记录已越过原先的 DirectConstructorHandleAccessor$NativeAccessor.newInstance0，停在已生成但未选入的原始 CharsetEncoder.isLegalReplacement（55380）；源码扩选继续进行。

Files 边界样本显式记录使用了源布局 filesystem/provider 接收者存储夹具，没有执行原始文件系统构造器或默认文件系统启动。正常顺序下的 Phase1、完整 Files 入口、Dispatcher 初始化和默认文件系统分别保留未完成标志。

此前直接 Dispatcher 边界探针曾到达 NativeLibraries.findBuiltinLib，但不能把 Phase1 失败后继续执行的结果当作完整正常启动进度。完整 Files.isRegularFile 入口、Dispatcher 初始化和 Minecraft 启动仍未完成。原生库的后续协议见[装载生命周期](NATIVE_LIBRARY_LIFECYCLE.md)。

开发命令位于 `scripts/nio-file-native-candidate.py` 和 `scripts/test-nio-file-native-candidate.py`，参数可用 `--help` 查看。它们使用 `.boom` 的锁定输入、选择证明及候选产物，没有接入玩家界面。
