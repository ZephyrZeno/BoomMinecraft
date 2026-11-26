# 正常 Class 静态同步方法

此前正常批次的静态 synchronized 包装仍引用旧 `boom_mirror_pool`。独立的输出流冷初始化曾实际到达 `Reflection.registerFieldsToFilter`，因这个 ABI 缺口停止。正常 Class 必须与类字面量、getClass、反射和类加载返回的对象保持同一身份。

自研后端增加链接环境能力 `normal_class_mirrors`；正常批次启用它，保留开发用旧对象 ABI 的原有路径。新静态同步包装先执行 Context32 类初始化，再调用 `boom_java_class_load(ctx, normalClassPool, typeId)`，使用该规范 Class 对象调用原有汇编 monitor enter／exit。实例同步方法继续锁定接收者，不额外触发类初始化。

类初始化失败在加锁前直接传播原始 Context，保留发生异常的方法和 PC。普通调用错误仍沿用 Context32 的错误处理。批次中的初始化调用适配只替换完整的旧 call 指令，避免把已经正确的 ensure32 改成 ensure3232。

服务端新批次已生成 498,179 个普通 Java 方法，727 项原有生成失败保持记录，所有实际 COFF 通过独立批次校验。新增的 `verify-normal-monitors.py` 从原始方法计划读取访问标志和 Code 身份，逐项检查全部 381 个静态同步包装，核对正常 Class 调用 ABI、错误传播、实际 ASM／COFF 散列，并与旧批次逐字比较原始 Java 方法体。381 项均通过，没有将方法体改成替代实现。

新编译器通过 202 项 Rust 测试、格式检查和 Clippy；新批次与原启动运行使用隔离的编译器文件和输出目录。服务端已构建八组新来源提供者并实际执行 System.initPhase1，推进至尚未实现的 Signal.findSignal0(String)。客户端尚未用此编译器重建。

`Test-FileBootstrapSource.ps1` 新增 OutputFirst／InputFirst 初始化次序。OutputFirst 的 `-VerifyClassMonitor` 模式先核对原始 Reflection.registerFieldsToFilter 的访问标志、Code 和实际正常 Class 包装，再让开发宿主持有其规范 Class 的汇编监视器，观察原始输出流冷初始化在该监视器节点等待，释放后验证源初始化结果及无遗留持有。原先 DescriptorFirst 的四类冷初始化、三份原始标准描述符构造和 24,576 次并发调用已在更新宿主下通过回归。

首轮 OutputFirst 竞争测试已观察到规范 Class 节点的等待者；解锁后遇到另一个未选入的原始 Java 目标，尚未将整项测试记为通过。独立的原始 FileOutputStream.initIDs 诊断保留了五轮完成记录及 1,074 项执行证据推导的 Java 准入，后续优先推进实际 System 路径。

v118 的 `Test-SystemSignalMonitor.ps1` 已在原始 System.initPhase1 路径通过实际竞争验证。测试仅先初始化既有四个源前置根；Signal 保持冷状态，加载规范 Signal.class 对象不触发其 Java 初始化。开发宿主持有该对象的汇编监视器后，原始 System 在线程上继续执行 Signal 初始化、构造与查询，并在原始静态同步 Signal.handle 上等待同一监视器节点。观察到一个等待者，释放后实际 Java 代码继续到明确缺失的 handle0 native；源同步包装正常解锁，监视器与调用栈均清理，堆销毁通过。

这一项证明了原始 System 路径中 Signal.handle 的规范 Class 身份、竞争与停止后的释放。它不表示其余 380 个包装均已实际执行，不把缺失 handle0 的诊断停止算作 System 完成，也不计作 Minecraft、世界或游戏侧多核优化完成。
