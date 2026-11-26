# 正常源 String 的批量拼接展开

v98 将字符串拼接从结构预检推进到实际汇编生成。服务器 9,991 个、客户端 10,387 个原始现场由同一规则处理，各生成两个协议单元。游戏执行端仍为汇编；普通 Java 方法生成量保持 498,179／562,769，不能将协议现场数与方法数相加计算进度。

## 接入自动翻译

`Invoke-AutomaticTranslation.ps1` 无需新增开关。schema 14 的批量后端收集原始 `invokedynamic`，按源类、常量池和 bootstrap 参数生成展开计划。独立校验器重新读取锁定输入，核对计划、逐字汇编、实际 COFF、源方法依赖和运行时散列。缓存复用仍经过完整校验。

仅接受原始 `java.base` 最终类 `StringConcatFactory` 的两个精确 bootstrap 签名、静态句柄和正确加载器身份。支持 `makeConcat`、`makeConcatWithConstants`、UTF-16 recipe 和 String 静态常量，动态参数上限按 200 个参数槽计算。参数／标记数量不符、其他静态常量和未知 bootstrap 保留兼容缺口。

参考契约为 [JDK 21 StringConcatFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/StringConcatFactory.html)。本轮对已识别的源协议进行专门展开，尚未执行完整 MethodHandle 引擎或任意 bootstrap。

## 执行路径

1. 适配器保留原始 bootstrap 类的真实初始化依赖；待处理异常会立即返回。
2. 捕获参数到每次调用独立的栈帧。整数、long、boolean、char 和正常源 String 直接传给汇编内核。
3. 对象／数组、float、double 通过原始 `String.valueOf` 的翻译方法执行转换，保持动态参数顺序。原方法的入口包装器仍负责 String 类初始化。服务器／客户端分别有 305／312 个现场包含这些转换依赖。
4. `java_concat.asm` 两遍计算长度与编码，分配正常源 byte[] 和 String，复制内容并计算 Java hash。支持 null、Latin-1、UTF-16、未配对代理项和整数边界，不接入旧 opaque String 布局。

内核使用 Context32、Pool80 和 Row24。生成数据绑定源 String 的布局及四个字段偏移。当前池采用紧凑字符串配置；更改源布局、输入、变换链、配置或运行时必须使相关产物失效。原始类初始化、对象转换和异常依赖不会因适配器已生成而被删掉。

本轮输入来自锁定的原始 JDK，尚未接入模组变换。未来若变换链更改 bootstrap 或核心 String 行为，必须重新证明该专门规则适用，或禁用它走通用协议；仅清除缓存不构成语义兼容证明。

## 已实际验证

| 范围 | 结果 |
| --- | --- |
| 服务器／客户端完整批次 | Java 方法单元 877／951，另各有两个拼接单元；实际汇编及完整独立校验通过 |
| 汇编内核 | 619 组 JVM 文本差分，含 70,001 字符输入、200 参数槽、整数极值及 Unicode |
| 原始生成适配器 | 每侧抽取 128 个不同签名，384 组 JVM 差分 |
| 并发 | 内核和每侧适配器各 8 工作者、8,192 次调用 |
| 错误与内存 | 内核 12 项、每侧适配器 13 项检查，包含待处理上下文、未绑定堆、元数据、OOM、静止回收和重试 |
| Rust／Python 回归 | 189／101 项通过，fmt 和 clippy 通过 |

适配器执行测试使用明确标记的 **VM 已准备 bootstrap 类描述符夹具**，原函数和数据与完整批次逐字相同。夹具初始化入口报告不可用；测试验证适配器不会绕过初始化失败。它没有执行原始 StringConcatFactory 初始化、String 构造器／初始化器或原始对象／浮点转换。开发 C# 调用器和 JVM 只用于准备测试与对照，不随游戏运行。

源闭包扫描能够从拼接现场选入原始 bootstrap 描述符、初始化器和依赖，继续暴露尚未展开的接口调用。System.initPhase1 的直接扫描保持 2,698 个 Java 方法、765 个前沿，其中 605 个可由已有分派规则继续展开，160 个仍需兼容处理；这轮不宣称改善了该入口的缺口数。

## 尚未完成

Lambda、record、SwitchBootstraps、一般 MethodHandle／VarHandle、原生与平台服务仍需真实规则或汇编实现。非 String 静态常量转换和其他返回类型仍被拒绝。活动根、自动内存回收、完整异常物化、原始引导及完整游戏尚未完成。

所有并发结果均为测试工作者调用汇编的证据，不计作原版游戏侧多核优化完成。`game_started`、`world_created` 和 `full_game_ready` 继续为 false，发布目录仍为 v70。
