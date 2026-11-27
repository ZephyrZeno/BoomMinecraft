# 原生入口的信号与工作线程退出顺序

资源接入后的 Main 初始化启动了三个受管理工作线程。首次实际运行停在尚未实现的
`Unsafe.allocateMemory0`，线程最终均退出并回收，但原入口更早执行 Signal close 时返回 170。
该错误被保留，后续 Parker、Object.wait、Reference、资源 owner 和堆清理被正确跳过。
这份失败记录保持原样，不记作清理完成。

原 `boom_signal_native_bind` 拒绝在信号租约、全局跟踪帧或 dump 仍活动时解绑。
Signal close 与受管理工作线程退出之间存在生命周期顺序冲突；
首次报告没有分别记录 transport close 和 native unbind 的返回值，因此不能从报告单独证明某一条 busy 分支。
没有发现固定要求两个工作线程的检查。

`scripts/main-signal-shutdown-source.py` 生成最小的原生入口差分：

1. 保持原 Signal close 与全部观察指令的字节不变，将整个块移到受管理线程 join／reap 后。
2. Signal 自身仍负责 join／detach dispatcher，再执行原解绑检查。
3. 之后真实调用一次幂等线程池 close：成功不清除旧错误，任何非零结果仍保留到原错误槽。

Signal dispatcher 直接 attach 到注册表，不在 TLCP 的受管理 token 槽中。
TLCP close 可先回收其自身工作线程；成功后在锁内封闭新 start，start 在锁内外均核对该状态。
第二次 close 是实际调用，没有通过改计数、清除 170 或写入关闭标志制造成功。
原来的 20 秒 join 期限、全部忙碌与失败保护、原 Main Context32、Java 方法体、字段和根保持不变。
逆变换必须恢复父入口的完整源码字节。

## 验证

8 项源码测试检查原模板与实际入口的逆变换、完整块移动、真实第二次调用、
原等待和错误保护、重复应用以及源码／合同篡改拒绝。
修复镜像只重新汇编一个入口对象，另外 204 个对象原字节复用；
新入口与独立重新汇编的完整 COFF 相同，库、导出以及名称／序号导入的集合和重数保持不变。
再次完整链接后，626,245,120 字节 PE 与实际运行文件逐字节相同。

修复后的独立进程实际仍停在相同的 native 113555、诊断行 51631，没有改变原程序的失败点。
三个工作线程均执行原退出并回收，Signal、Parker、Object.wait 和 Reference 均关闭；
Reference 三个 stop token 全部消费，最终状态为 6，worker failure 和 held monitor 为零。
根快照为 2,770 个非空项，堆／注册表／Java 帧清理标志为 7。

[JIMAGE 资源 owner](MAIN_JIMAGE_OWNER.md)也在同次进程中实际完成了原 unload 原生调用一次，
库引用由 1 降到 0，owner 租约由 2 降到 0，JMAP 节点／租约由 1 降到 0，
文件和映射计数均为零。独立清理 Context 结束时没有异常、活动深度或遗留 VM plan；
原 Main 四个 QWORD 保持不变，两个报告的 Main 观察一致。

这是原生初始化前缀及退出生命周期的执行验证。Main 类初始化未返回，Main 方法体、帮助输出、
完整游戏和世界仍未完成；没有运行自动或并发收集，也没有据此宣称游戏性能提升。

| 本地忽略证据 | SHA256 |
| --- | --- |
| 首次失败：`v211-current35-jimage-overlay-f/overlay-execution.json` | `ef7afe3b34e23bc816911b647ed117e46d963d51f89ac5602ad5be292463454f` |
| 修复执行：`v223-current35-signal-cleanup-repair-a/overlay-execution.json` | `b78452c84c8e8d14a2b4471424c6751b82e373ccfc59b9a48af1f99b221a7f14` |
| 原报告 576／ABI14 | `bd37908635a0ed47577bc47c76de1f3f413cb7a7103282cabce7222c3350eafe` |
| 资源报告 256／ABI1 | `9231c8185d15e36d60de24a2176dbc328be806961dbaaed6a351c192a9358895` |
| 完整 PE 重新链接复核 | `4abd0bf0e2a153ce951165d3a29557729658f43dabcd4a6b68eb318fd37ef68c` |

以上目录均位于 `.boom/vm-entry-images`。完整来源范围见 [35 包入口记录](NATIVE_RUNTIME_35.md)。
