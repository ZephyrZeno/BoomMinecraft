# Windows NIO 结果字段登记

`native/providers/windows_nio_dispatcher_ids.asm.inc` 实现纯 MASM 的
`WindowsNativeDispatcher.initIDs` 登记服务。
它通过原 `boom_class_ensure32` 完成七个结果类的初始化，核对原类型布局、UFMP 字段名称／种类／宽度及 FMAP，
最后在短锁内发布二十个正常字段地址函数指针。缓存不保存 Java oop，不直接修改 Java 字段或类状态。
类初始化期间不持有发布锁，失败或已有 pending Context 时不清除错误后重试。

此处原生语义按锁定的 OpenJDK `jdk-21.0.13+3` 来源投影：
[WindowsNativeDispatcher.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/windows/native/libnio/fs/WindowsNativeDispatcher.c#L87)
的正文是七次类查找和二十次字段查找；
[JNI 实现](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/hotspot/share/prims/jni.cpp)要求正常类初始化。
这一步没有实现 Windows 文件查询 API。

目标为 FirstFile、FirstStream、VolumeInformation、DiskFreeSpace、Account、AclInformation、CompletionStatus。
七类及全部字段原已在当前专用服务器 Main 来源中，无需添加 Java Code 或重跑完整 source V。
正常 Frame、原类文件、字段映射和实际 COFF 数据互相核对；私有 FieldID 表示为原字段地址函数，
不要求沿用 HotSpot 内部指针表示。

## 正式源码工具

`scripts/windows-nio-dispatcher-source.py` 从类文件、原始 C 顺序和实际布局／Frame 投影完整模型。
`scripts/windows-nio-dispatcher-candidate.py` 提供 `build`／`verify`，显式接受 state、source、parent、
pinned、assembler 和全新 output。它生成正常 native 入口与登记服务两个对象，
再独立重汇编，比较全部非调试代码／数据、节标志、完整符号辅助记录、重定位及 unwind。
工具仍是未登记候选，没有修改原 35 包运行验收状态或原 runtime DLL。
研究、负例和原版入口的一次性 Python 驱动均留在忽略的 `.boom`，不进入 Git。

主 agent 已从发布路径独立构建、重新投影全部模型并重汇编两对象。
生成 ASM 与已实际执行版本逐字节相同，old／published／各自 canonical 四份完整 COFF 等价；
除生成器自身输入路径外，类／字段／Frame 模型语义相同。
本地发布验证 SHA256 为 `1f6c28eb443d3c3c0c4c3fc9ed6d295d9e53aa7459aab96096dd6568ccc029d0`，
`root-equivalence.json` 的 SHA256 为 `dec1289cb12b9430c4949bb19bbdc7547fed706d9f984cef70b59adcbe676d64`。

登记池为 WNID224／ABI1：state0 表示未发布，state1 表示二十项完成，lock 独立位于偏移 24。
接口只接受实际登记池和操作 0；错误 pool 返回参数错误，未知操作或布局不符返回明确不支持。
Context kind 或 VM plan 已存在时，完整四个 QWORD 保留。

## 实际组件验证

独立冷进程实际执行原 System phase1、primordial／FLS 和资源引导，
经原正常 Frame 首次进入 WindowsNativeDispatcher，原 Java `<clinit>` 加载 net／nio。
owner 与七个结果类均从 state0 进入 state2，缓存二十项等于实际源字段地址函数。
随后用正常布局对象实际调用全部二十个地址函数，结果与源物理偏移相同。

四个 kind／VM plan pending 用例保持完整 Context，八个不同 OS 线程共 256 次原 Frame 调用逐次核对缓存，
错误 pool／operation 也按约定拒绝。最后原库卸载、注册表、帧、堆、RW 和 JIMAGE 清理均成功，输入摘要不变。
这不是执行 Minecraft Main；首次组件调用器把地址函数参数顺序写反的失败记录保留，修正仅涉及测试调用器。

本地完整组件回执：
`.boom/windows-nio-initids-component-v242-a/execution-b/execution.json`，SHA256
`55b0625e404d9bd6f275fd73f978aeb79e4924759c601a54ec36aaef07279639`。
七个来源／Frame／代码与 unwind 篡改负例均被原模型重建或规范机器码比较拒绝。

## 实际专用服务器入口

主 agent 随后实际运行新 212 对象镜像：只替换原索引 94 的剩余 native 停止对象，增加两个对象；
其余 209 个对象，包括进程入口，保持原字节。没有新 IAT 导入，完整 PE 独立重链接逐字节相同。
运行前后显式封存两个实际 ASM 来源；该元数据补充没有重编或改写 PE。

原 `net/minecraft/server/Main --help` 初始化已越过 `initIDs`，
新停止为 `GetFileAttributesEx0(JJ)V`，原方法 138204、诊断行 53887，Context 为 138203／PC11。
System 三阶段到 VM4，三工作线程退出并回收、清理标志为 7；
RW 实际分配／释放各两次，4,096 字节和全部租约／元数据最终清零；
原库卸载三次，文件和映射清零，三份报告的 Context 一致。

Main 类初始化尚未返回，Main 方法体、帮助输出、客户端窗口和完整游戏均未执行。
不能把独立字段登记、服务端初始化或后续 69 个 native 的静态分组作为启动完成。

| 本地证据 | SHA256 |
| --- | --- |
| 最终 212 对象来源／机器码验证 | `c31887cee01a78a037a4c0403feb5d3fdb1d7d90b754c9fbac08078a62b2a95d` |
| 独立完整 PE 比对 | `fe7e331d3a0caacbe431e9aeccb42b178cbc90e4bd99420b0fb82d54e285c29e` |
| 实际进程 `overlay-execution.json` | `ad93b1a253938afa221f25ce3174df87ed8ecd5b04c70dfa19616660b5efa423` |
