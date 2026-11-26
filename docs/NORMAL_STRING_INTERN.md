# 正常源布局 String 驻留

原始 String.intern 是实例 native，没有 Java Code。批量生成器核对锁定 java.base 中 final String 的来源、字段布局、native 签名和访问位，生成实例入口，实际执行由 `java_string_intern.asm` 完成。调用不额外初始化 String；VM 准备的源形状测试对象不等于执行原始 String 构造器。

对象使用原来的 value、coder、hash、hashIsZero 字段，value 为正常 byte[]，接受 Latin1 和 UTF16 两种编码。比较与散列按 UTF16 单元处理，不做 Unicode 规范化，不信任已有 hash 缓存。NUL、代理项、空内容以及超过字面量长度的动态 String 都进入同一个契约。不同内容即使散列相同也不能合并。

## 已知常量与 Class 名字

原字面量池及 Class 名字池的条目都已按完整 UTF16 排序。驻留服务先进行二分查找，使用相同的字面量发布状态：0 未解析、1 有构造者、2 已发布。未解析时以 CAS 取得状态，将调用者直接设为规范对象；遇到已有构造者时等待其完成。这样“先 intern，后 ldc／Class.getName”与反向次序共用对象身份，不创建第二个规范副本。

驻留不在静态池中出现的内容时才进入动态表。已知常量的查找和不同条目的首次发布不需要动态表锁。

## 动态表与内存边界

动态表为汇编堆中的引用前缀块：前 capacity 个 QWORD 为 String 引用，后 capacity 个 DWORD 为散列。一条显式根保留表，回收内核会沿引用前缀访问其 String 和 byte[]。开放寻址在 75% 装载率前扩容，从 64 槽翻倍，当前上限 1,048,576 槽。扩容先完成新表再替换根；失败保留原表，释放锁，报告 OOM。旧表在下一次显式静止回收中释放。

这版保留强引用。弱驻留、类卸载、活动线程根映射、同步点及自动回收仍未实现，不能从本模块推导完整内存管理已经完成。这里没有复制 JVM GC，也不能通过把动态表排除在根之外模拟弱驻留：悬空引用和堆地址复用必须由真正的引用处理协议解决。

动态表锁只保护查找、插入及扩容。输入内容检查与散列在锁外执行，竞争者使用 Windows 按地址等待，释放时唤醒一名竞争者；热的无竞争路径不调用等待 API。原生临界区内不调用用户 Java 或触发回收，现有 ABI 的 OOM 交由调用方在静止条件下处理。

## ABI 与来源

Pool96：magic/ABI 0/4，锁 8，动态项数 12，容量 16，保留 20，堆单元地址 24，正常 String 布局 32，value/coder/hash/hashIsZero 字段偏移 40/44/48/52，原字面量池 56，Class NamePool64 64，动态表根单元地址 72，Context 字节数 80，强保留策略 84，保留 88。一个池只属于绑定堆的生命周期，不能在销毁后带着旧根重绑。

调用为 `intern(Context32, argv, Pool96) -> String oop`，argv 第一个单元为接收者。已有错误／Throwable 不触发绑定、分配或发布。空接收者、异常形状、错误 coder、奇数 UTF16 字节长度、外堆引用分别在访问前检查。Context32 的实际 Java Throwable 物化仍由后续 VM 异常协议负责，内核状态检查不能冒充完整 Java 异常链。

语义依据 [Java SE 21 String.intern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#intern())。OpenJDK 的实际驻留表使用[弱句柄](https://github.com/openjdk/jdk21u/blob/master/src/hotspot/share/classfile/stringTable.cpp)，与当前明确声明的强保留策略不同。未来加入弱处理时必须保留同内容身份与常量／名字发布协议，同时让元数据及加载器变化正确失效。
