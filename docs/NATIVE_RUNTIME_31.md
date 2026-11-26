# 31 包正常入口与原 Main 日志初始化前缀

当前 107 工具来源已重新完整校验 65 槽 batch、全部 31 包和新的原 Main 源选择，并实际重建／验证／执行标准原生入口。原 System.initPhase1／2／3 均返回，VM 级别到达 4；ASM 构造正常 String[] `['--help']`，原 Main 类的日志初始化实际执行后停在尚未提供的 `Class.getDeclaredMethods0(Z)[Method;`。Main 方法体未调用，帮助输出未完成，完整游戏和世界仍未启动。

当前源选择为 `.boom/diagnostic-startup/v161-main-cp-source-a/round-000`，包含 8652 类、71771 个原 Java 方法、192724 个汇编函数及 26929 格静态／初始化失败根。独立源校验自然退出 0，用时 870.015 秒。[新增原始源依赖](VM_ADDITIONAL_SOURCE_ROOTS.md)保留真实 ConstantPool、Tag、Option 等布局和初始化器，不把源预选计作执行。

原生目录为 `.boom/vm-entry-images/v161-main-cp-original31-a`，实际 stop 是源行 107300、native 方法 41459、原 Java caller 41471／PC19。ABI14、完整根快照 2534 个非空项、Parker 开关、IO 空闲、两个后台 worker 退出／回收及清理标志 7 均与先前有界运行一致。没有穷尽执行全部 native，没有自动／并发 GC 或完整游戏成功标志。

```text
source proof  ba0cb2612c0a8a285014cb8cad96d0124713ca5471c6c4a673a8f224afb1d676
native proof  689d00d36d82ccbfa5c929a1dc049636074cfd8d7711775a40b443b7afbaacd6
execution     f66c26295418686618830e558811ea74b1d3fc275ad0367ea717be1a1a6d8850
ABI14 report  8b21a3b662e59415f4fc3047785bf9cd9fa01c9b712b6cb91c4b9c2cd7a74454
```

新的有界状态 `.boom/accepted-main-prefix-v167-31.json`，SHA256 为 `7105962aef19b42a88d20bc633dc44c4dfe81289f62c1f3269d5c65f823218cf`。发布前两遍检查 440 个实际产物，归档 30 份源工具／内核；验收范围仍为这些输入下的 System 三阶段、argv、日志前缀、根传递和退出清理。原 pending31 与旧 accepted31 的字节均未修改。

## 先前 105 工具来源的独立历史

下述旧运行使用 105 工具来源下完整验证的 65 槽 batch 和原 31 包。旧证据保留，不作为新工具来源的运行收据。

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

实际执行回执另存回原源选择的辅助输出，并发布明确标注恢复过程的 `result.json`，原 failed journal 的字节未变。自动 Java 补全现在严格接受 Report512／544／576 与各自 ABI12／13／14 的组合，继续从封存二进制中的首个／主线程源行验证目标。7种报告格式均覆盖伪摘要、错 ABI／长度、交换源行和修改诊断表的拒绝检查。此次 stop 是缺 native 语义，不新增 Java 执行许可；60666 个源预选方法仍不计作实际执行。
