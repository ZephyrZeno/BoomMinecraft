# 正常 bootstrap 名字查找与初始化入口

v108 在批量后端接入 `Class.forName0` 与 `ClassLoader.findBootstrapClass` 的共享规则。输入来自锁定的 bootstrap 类、数组类型和原始类状态；翻译器和验证器生成／检查元数据，运行中的名字比较、Class 对象取得和初始化全部使用汇编。

## 来源与名字身份

`batch_class_lookup.rs` 核对两个原始 java.base native 的所有者、签名和 `0x10a` 标志。普通类与接口来自源目录；数组只使用当前类型全集中已提供的身份。基本类型名字不作为普通类插入；数组的名字保持 JVM 二进制名字格式。源名字存在但布局未提供时单列为不可执行，不能冒充类不存在。

索引按无符号 Java 字符串散列及 UTF-16 名字排序，运行时先二分找散列范围，再逐字符确认。散列相同不会合并类型；Latin1 和 UTF-16 源 String 都按相同字符序列匹配。正常 Class 镜像仍由已有 ClassPool144 提供，没有把表示类型 ID 塞进 Java 字段。

当前域是 **bootstrap 加载器**。非空加载器先验证真实源类型，再明确报告该域尚未提供；不会把任意自定义 ClassLoader 当成父优先加载器。新增加载器、定义类、变换链和数组类型注册仍需要各自的真实规则。当前类型全集之外的数组请求也保留未提供状态。该范围不能称为完整 ClassLoader 实现。

取得 Class 镜像还要求其所属模块已绑定。全表执行曾到达 java.xml 中的类，并如实返回“模块尚未绑定”；名字存在不等于所有上游引导都已完成。开发全表测试通过现有汇编对象分配与模块绑定接口，显式准备 21 个正常布局的 bootstrap Module 输入；名字和 loader 字段取自锁定来源。它没有执行 Module 的 Java 构造器或游戏模块引导，不能把这些测试输入当作完整模块系统的实现。实际 System 路径继续使用其真实引导状态。

名字与初始化遵循 [Java 21 Class.forName 契约](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader))；OpenJDK 的 [JVM 类查找入口](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/jvm.cpp)也区分 bootstrap 查找与经 Java 加载器解析。实现没有复制该 C++ 运行时或调用它作为回退。

## 初始化依赖也能自动推进

编译产物包含两个 MASM 单元：名字池与 native 适配器，以及完整源类初始化入口表。表项保留原始类描述符，`initialize=true` 时调用 `boom_class_ensure32`，执行原始 ConstantValue、依赖和 Java `<clinit>`；`false` 只取得镜像。数组请求始终保留组件的冷初始化状态。

诊断映像不提前连入整个 JDK 的所有初始化器。它保留全部可用名字，把入口表投影为“已选择的真实类描述符”或“未选择的源初始化请求”。后者仅是明确的诊断停止：记录源类摘要和完整类状态，类别为 5，不提供成功的替代类描述符。

`update-diagnostic-profile.py` 只在真正执行到此请求、并核对原始类状态后增加 `admitted_classes`。下一轮选择器自动加入其描述符和原始初始化依赖。这个准入不会标记类已初始化，也不会增加 native 实现计数。新的状态同样进入续跑、跨批次来源检查和独立 COFF 验证。

因此，补一套名字／初始化规则后，运行到的新类由程序继续选择，无须逐类添加手写桥接。缺少原生语义或不可用类状态仍保持失败。

## ABI 与内存

`java_class_lookup.asm` 使用 JCFN128/1 池；名字记录 32 字节，初始化记录 16 字节。池连接现有 ClassPool、String 字面量池、Class 引导注册池及同一堆生命周期。名字记录只有源元数据，没有 Java 对象根；新镜像继续由 ClassPool 的强根保存。

初始化描述符沿用现有 ABI2：初始化函数在偏移 16，源类 ID 在偏移 24。执行检查必须依据该布局，不能把名字记录或其他结构的字段位置套用到类描述符。内核冒烟检查包含真实 AtomicInteger 初始化，除了查询成功，还要求原始描述符从冷态发布为完成态。

输入为正常源 String，参数使用每个逻辑参数一个 QWORD 的托管 ABI。`forName0` 返回规范镜像，缺少普通类对应错误种类 16；bootstrap 查找不存在的普通类返回 null。当前没有接入这些错误的完整正常 Throwable 对象物化。已有待处理错误保持不变；错误布局／外来引用保留失败。

自动回收和活动栈根仍未完成，本规则沿用显式静止点内存契约。完整 System 引导、Minecraft 和世界创建继续独立验收。

## v108 实际执行范围

`Test-BatchClassLookup.ps1` 在每侧建立两个来源独立校验的诊断映像。首个映像实际执行名字查找，记录 Thread.State 未选择初始化入口的类别 5 请求；准入程序核对原始类状态后，第二个映像才加入该描述符与初始化依赖。没有提前设置完成标志。

服务器／客户端分别执行 34,945／34,954 项原始名字查找，并逐项核对规范 Class 的表示类型身份；两种 String 编码交替覆盖。同一集合通过 bootstrap 原生服务再次调用。该全表验证使用明确的 21 个 Module 测试输入，完整模块引导仍未执行。

每侧另通过 44 项原版公开 `Class.forName(String,boolean,ClassLoader)` 与 JVM 对照、8 工作者冷 Class 引导、8 工作者原始 Thread.State 初始化、六个真实枚举常量的原始 Java name／ordinal，以及 4,096 次无新堆分配的并发查找和 11 项错误检查。`initialize=false` 与数组查找保持组件冷态的检查通过。

bootstrap 服务测试直接调用其源 `_native` 入口，未执行 ClassLoader 包裹入口或初始化器；宿主也检查其描述符保持冷态。自定义加载器、未登记数组、完整异常对象、模块引导、自动回收和完整游戏均未因此完成。测试宿主为 C#，执行中的查找、初始化和原始 Java 方法都是生成或手写的汇编。

```powershell
./scripts/Test-BatchClassLookup.ps1 -Batch <schema-22-batch> -Plan <matching-plan> -Runtime .boom/assembly-runtime-v108b
```
