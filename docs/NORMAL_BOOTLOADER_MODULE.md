# 正常 BootLoader 模块发布

原始 `BootLoader.<clinit>` 创建 unnamed Module、赋给 `UNNAMED_MODULE`，经原始 Java 启用 native access 后，调用私有 native `setBootLoaderUnnamedModule0(Module)`。`normal-boot-unnamed-module-v1` 用汇编将这个对象发布到正常 JCLS 模块根表。

实现直接使用 Java 创建的对象，核对来源字段布局、原始静态根、初始化线程以及正常 Module 字段。空参数、不同对象、错误池或已有异常均单独处理。发布通过 `boom_java_class_bind_module` 完成，同一对象重复登记保持幂等；不额外分配 Module，也不手动改写类初始化状态。

## 稳定模块编号与批次派生

编译器在来源已分配的模块编号末尾追加 bootstrap unnamed 槽，已存在时复用。v145 的新槽为 63，模块数从 63 变为 64，连续 GC 根数从 110011 变为 110012；`java.base` 和应用 unnamed 模块的旧编号不变。

`refresh-boot-unnamed-batch.py` 只重建 JCLS 数据单元，保留完整父批次的验证结果、原始 Properties 目录声明和所有普通 Java 方法产物。完整独立验证重新核对新索引、精确汇编、COFF、来源与父批次关系。缺少子证明、修改覆盖数、错误派生范围或新增执行成功声明均拒绝。

## 已完成验证

- 完整派生批次保留 53,660 个原始类和 498,179 个已生成 Java 方法，普通 Java COFF 未重编。
- 正式 provider 的源码、精确汇编、实际 COFF 及原始 native 帧均独立验证。
- 原始 BootLoader 冷初始化返回，五个 Java 静态字段完成赋值；Java 静态字段与新增 JCLS 根持有同一个 Module，表中恰好一份。
- 八个不同 OS 线程并发进行冷初始化，全部在发布后返回，只产生一个 Module；退出时 guest 帧深度均为零。
- 同一对象重复调用、不同引用、空参数和已有异常的边界检查通过。

正式执行记录在 `.boom/boot-unnamed-normal/execution-formal-v145-843059c86002430db66798e01269045e/result.json`，SHA256 为 `4fb5cd368a19843c067d2129baa266a08dd1c6dc357bfcf1c2e9877021f878e6`。批次完整验证 SHA256 为 `b1abda904b5f3109b9c59e83ff49d23726fc97a553bf96167c91cacfe40485ef`。

## 验证范围

该冷初始化测试的 System 准备阶段仍停在独立缺口 `m42389`，因此不能记为 System Phase1 或整版启动完成。另一个保留原 Java 目标文件的开发进程已实际返回 Phase1、进入 Phase2，并在加入此汇编服务后推进到 `ClassLoader.registerNatives`；它没有重新完成整个链接选择证明。

22 个正式 provider 的共同输入已通过摘要与依赖一致性检查，完整原生启动链、Thread.join／Timer 和 NIO 使用同一输入继续独立验收。共同输入文件不代表它们已经共同执行成功。完整 Minecraft、世界创建以及游戏侧性能验证仍未完成。
