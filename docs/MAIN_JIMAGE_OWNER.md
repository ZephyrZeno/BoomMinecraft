# 正式进程的汇编 JIMAGE 资源 owner

`scripts/main-jimage-owner-source.py` 从锁定输入生成纯 MASM 的资源 owner 和明确的原生进程差分。
它用于把已独立验证的 [JIMAGE 映射](JIMAGE_NATIVE_MAP.md)接到正式 Main；
生成器本身不翻译 Java、不执行 VM、不登记新提供者，也不提升运行验收状态。
游戏执行期间的资源管理代码位于 `native/probe/main_jimage_owner.asm.tpl`。

## 输入与资源路径

生成器重新核对当前提供者状态、命名模块 batch、Frame 原始声明及真实系统目录。
`java.home` 同时取自锁定 VM profile 和原属性字符串表，两者必须逐 UTF-16 单元一致。
资源 key 为原 `java.home\lib\modules`，模块长度取自锁定 image；
`jimage`、`nio`、`net` 的字符串编号以及原 `NativeLibraries.unload` 方法编号均由输入推导。
模板不包含某台机器的路径或固定方法编号。

可选 `--stage-modules` 仅在项目 `.boom` 内的准确目标路径 create-new 复制输入。
已有文件只接受完全相同的大小与 SHA256，保留源和目标的前后摘要，不覆盖现有内容。
当前真实 VM profile 原本指向项目批次目录，因而需要在该隔离目录准备 `lib/modules`；
没有改写原属性、Java Code 或其他启动器的目录。

```powershell
D:\Dev\Python312\python.exe -B scripts/main-jimage-owner-source.py --state .boom/formal-native-transitions/v204-combined117-b/pending-state.json --output .boom/main-jimage-owner-review-a --stage-modules
D:\Dev\Python312\python.exe -m unittest tests.main_jimage_owner_source -v
```

使用全新输出目录。上述命令只准备源码，不能据此判断游戏已经启动。

## 生命周期与进程差分

- `boom_main_jimage_prepare`：在任何 Java 引导前初始化 Owner128，打开真实只读映射并保留启动租约，再打开 JMAP80。
- `boom_main_jimage_unload_modules`：工作线程全部 join 后、注册表和堆仍在时，通过原 unload 原生入口释放实际自有库引用。冷库不进入 Java；清理使用单独 Context32，原 Main Context32 只读并逐 QWORD 比较。
- `boom_main_jimage_resources_close`：仅在堆实际销毁成功后 drain JMAP，释放启动租约，再关闭原映射 owner。忙碌或失败时保留对应资源，不报告关闭成功。
- `boom_main_jimage_write_report`：以 create-new 写出独立 256 字节报告，原 576 字节启动报告和 ABI 保留。

生成器记录六处可逆文本编辑：四个实际 hook、EXTERN 声明，以及 trace 释放失败时跳到报告并保留 VM 内存的额外清理保护。
逆序还原六处编辑必须恢复原进程源码的完整字节。Java 方法体、类状态和根格不在这些编辑范围内。
这段代码没有触发自动或并发回收。

## 已完成的验证范围

7 项来源测试覆盖完整 UTF-16 路径与代理对、动态编号、错误来源绑定、未知模板参数、
六处差分的严格反向恢复、缺失清理锚点及原 Context 的只读约束。
实际运行发布路径下的生成器通过原始声明／Frame 核对；两次 MASM 汇编的完整非调试 COFF
与已测 b 版逐项相同，包括代码、数据、节标志、符号辅助记录、全部重定位和 unwind。

纯原生资源测试实际执行五类情况：正常打开与重复调用、仍有额外租约时拒绝关闭并允许释放后重试、
文件不存在、坏 image header、期望长度不符。最终文件／映射句柄、租约和节点均为零；
每项测试的 Win32 进程句柄数量前后相等。实际汇编写出的 256 字节报告与内存完全一致，重复写入被拒绝。
主 agent 使用仅改变输出目录的测试副本独立复跑了全部情况。

这些测试提取的是原 JMAP 的五个纯原生生命周期函数，逐函数与已验证完整对象比对全部实际指令、
重定位、符号位置／类型、节标志及 unwind。测试没有伪造 Java 回调，也没有执行原 `getNativeMap` 服务。
完整 owner 的 unload 分支最初只完成汇编与 COFF 比对。
随后[修复 Signal 退出顺序的原生入口](SIGNAL_SHUTDOWN_ORDER.md)已实际完成联合执行：
原 unload 调用一次、库引用 1→0、owner 租约 2→0、JMAP 节点／租约 1→0、文件和映射均归零，
原 Main Context 四个 QWORD 保持不变。该入口停在尚未实现的 `Unsafe.allocateMemory0`，
Main 方法体及帮助输出仍未执行。原五类资源测试的回执不改写成这次联合运行。

本地证据均位于忽略的 `.boom`：

| 证据 | SHA256 |
| --- | --- |
| 发布生成器源码／Frame／完整 COFF 复核：`current35-main-jimage-owner-published-v215-a/root-machine-verification.json` | `59a7c1ef411926f1d284938b5307596d72ff23e1432c1278ad2bf3a92770c6d0` |
| 主 agent 独立资源实测：`current35-main-jimage-owner-v208-b/root-native-resource-test-v212-a/verification.json` | `ca8089279200c1f0caab831c4e3c0eaa3b71165d8f53c511c67bc18c9ecce8b2` |

当前 [35 包标准入口](NATIVE_RUNTIME_35.md)仍以其自身的实际运行收据为准。
