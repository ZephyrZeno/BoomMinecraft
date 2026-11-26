# 正常 Class 镜像与引导绑定

交付路径使用原始 Class 字段布局。represented type 不占用 Java 字段，而保存在镜像缓存和反向索引；Class 对象自身的运行时类型仍为 Class。Class 私有构造器不执行，它在原 JDK 中也不用于 VM 镜像创建。

创建镜像不初始化所表示的 Java 类，也不把 Class 的 Java 初始化器标成完成。名字、反射和 ClassValue 缓存初始为 null，后续由真实服务或原始 Java 代码填写。数组镜像先取得组件镜像，再发布 componentType；所有入口共享规范对象。

v95 提供 `initClassName` 实例 native。原始 Java `Class.getName()` 继续读原始 volatile name 字段；首次缺失时调用汇编工厂，以 CAS 发布正常源布局 String。整数、void、普通类和多维数组的名字统一从已验证类型元数据生成；相同名字跨加载器共享规范字符串，hidden／动态生成类仍须自己的来源契约。

名字与锁定输入中的相同字符串常量共享对象：生成器按完整 UTF16 内容关联原字面量池，不能只比较散列。未出现在原字面量池中的名字由独立的规范名字池提供。两个池使用同一汇编 String 工厂，堆身份必须与 Class 镜像一致，已有异常不会触发绑定、分配或发布。名字池也有规范与构造中引用的显式根。v96 的[正常 String 驻留服务](NORMAL_STRING_INTERN.md)已接入两个池，先驻留的调用者可以直接成为后续名字的规范对象；动态表采用强保留，弱驻留与类卸载仍未实现。

加载器与模块分别绑定规范对象。bootstrap 加载器为 null；其他加载器缺失时明确返回引导服务未就绪。仅 java.base 的早期镜像可在模块定义前暂缺 module，模块绑定后修补已创建镜像。结束早期阶段必须确认 java.base 已绑定；其他模块缺失时仍拒绝创建，不使用默认模块替代。

Pool144：magic/ABI 0/4，锁 8，类型容量 12，Class 根 16，Row48 24，Class 布局 32，类型表 40，堆单元 48，加载器根 56，模块根 64，反向槽 72，反向掩码 80，加载器数 84，模块数 88，早期阶段标志 92，classLoader/module/componentType 偏移 96/100/104，Class 类型 ID 108，加载器/模块类型描述符 112/120，模块所属加载器 ID 表 128，Module.loader 偏移 136，保留 140。

Row48：类型描述符 0，组件/父类型 ID 8/12，加载器/模块 ID 16/20，早期 java.base／hidden 标志 24，原始类访问位 28，主版本 32，保留 36/40。不存在的关系使用 FFFFFFFF。反向槽 16 字节：镜像指针 0，类型 ID 8，保留 12。

NamePool64：magic/ABI 0/4，源 Class.name 偏移 8，类型容量 12，类型到规范名字的 DWORD 索引 16，名字 String 工厂池 24，正常 String 布局 32，同映像汇编 String 工厂入口 40，原字面量池 48，规范名字到字面量 ID 的 DWORD 索引 56。字面量索引不存在时使用 FFFFFFFF。Class Pool144 和镜像 ABI 保持独立，不把名字元数据塞进 Java 对象。`boom_java_class_name_roots` 与原镜像根、原字面量根一起参与静止回收。

所有游戏执行代码使用 MASM。离线生成器和开发宿主可使用 Rust/Python/C#；测试必须区分 VM 准备的对象、原始 Java 方法执行、类初始化和 System 启动。模块绑定测试若只分配对象形状，不得记作执行模块构造或完成模块引导。

依据：[OpenJDK Class 镜像建立与模块补写](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/classfile/javaClasses.cpp)、[java.base 模块补写](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/classfile/moduleEntry.cpp)。v99 的[Class 基础引导](NORMAL_CLASS_BOOTSTRAP.md)已确认十项已有 AOT 绑定，并实际执行原始 Class 初始化器；其余 native 与完整模块引导继续保留缺口。

名字缓存依据同一 [OpenJDK java_lang_Class::name](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/classfile/javaClasses.cpp) 和 [JVM_InitClassName](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/prims/jvm.cpp)：该路径以外部类名驻留字符串并填写 name 字段。本文记录的是自研汇编实现的来源契约，不是把现有 JVM 的执行结果作为交付运行时。
