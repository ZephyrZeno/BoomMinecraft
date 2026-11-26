# 31 包正常入口与原 Main 日志初始化前缀

本轮正常原生进程使用当前 105 工具来源下重新完整验证的 65 槽 batch，以及全部 31 个提供器。原 System.initPhase1／2／3 均返回，VM 级别到达 4；ASM 构造正常 String[] `['--help']`，原 Main 类的日志初始化实际执行后停在尚未提供的 `Class.getDeclaredMethods0(Z)[Method;`。Main 方法体未调用，帮助输出未完成，完整游戏和世界仍未启动。

源选择 `.boom/diagnostic-startup/v150-server-main-5fe1492128ac4697b3a7c51336826a7e/round-000` 包含 8175 类、65348 个原 Java 方法、173820 个汇编函数及 25368 格静态／初始化失败根。完整独立源校验自然退出 0，用时 659.187 秒；数量只代表来源与链接范围，不能视为全部已执行。

原生目录为 `.boom/vm-entry-images/v151-main-digest-fixed-a`：

```text
source proof  7d07e76baf2d43fc4502b58a97a7d27da11b113dea641132acea02d4e22f37f1
native proof  a4588fa1e02d791e65fb6c9ceda3f037bb16081692d69db7d70e9a80092e5907
execution     1711f123a7a5ee1d6efdd7ba9e1b9481f3744a971c3e7fce90e113d4f1b162d7
ABI14 report  2fe4713293eda40670e09a681f6c3cc416053a03f109fc5e099499d696b478d1
```

原生诊断退出码 86，主线程源行 106165，native 方法 41459；原 Java caller 41471、PC19。原 Main 初始化未返回，`main_called=false`。所有原 Java Code、Logger／SPI／反射分支保留，没有用空方法表或跳过日志来产生成功。

Parker 在真实 primordial FLS／OWAI 打开后打开，在共享停止及所有 worker join 后、OWAI 关闭前关闭。实际报告 open／close 各 1，active／waiter／gate root 均 0；文件输入 handle／buffer／owner root 均 0。完整九源／primordial／native bank 的 ASM 快照产生 2534 个非空项，实际保存到私有向量。这里没有调用 collector；pending exception／活动帧的自动扫描与自动／并发回收未实现。

两个原后台 Thread.exit 与 OS 记录回收各 2，worker／signal failure、held monitor、registry lock 均 0；共享 Reference／Object.wait 停止关闭、清理标志 7 全通过。完整 native ABI14 解码器在原生清单中封存。

Scoped 状态 `.boom/accepted-main-prefix-v152-31.json` 的 SHA256 为 `1ce895f550b1b8a1c0f6587288db42dd7519e507aa58216740522c05599c3f6f`。发布前两遍检查 420 个实际产物，归档 29 份源工具／内核；仅验收当前输入、System 三阶段、argv、日志前缀、根传递及停止清理。没有穷尽执行所有 31 包 native，没有完整 Main／help／游戏成功标志。

最初外层 run 保留 failed journal：原游戏 JAR 的来源记录带额外 SHA1，原 native 清单比较器只生成 size／SHA256，导致误报输入变化。实际大小与两个摘要均一致。修复先验证全部原摘要再规范化 native 记录，并用新的 native 目录重建／独立校验／执行，复用已通过的源选择；未覆盖旧失败或重命名旧记录。回归验证接受未变的双摘要原始输入、拒绝伪 SHA1 与修改后的字节。原 pending31 与 accepted29 均保持原样。
