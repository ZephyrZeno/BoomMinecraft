# 正常 ConstantPool 候选

`normal-constant-pool-source.py`、`normal-constant-pool-candidate.py` 和
`native/providers/normal_constant_pool.asm.inc` 为未注册的独立候选。
计划族名为 `normal-constant-pool-v1`，metadata key 为 `normal_constant_pool`。
不修改共享 runtime DLL、原 Java Code、类初始化状态或属性。

原 `Class.getConstantPool()` 返回正常 `jdk.internal.reflect.ConstantPool` 对象。
VM 原语正常初始化该 wrapper 类，随后分配对象；与锁定 HotSpot 相同，不调用其 Java
构造器，不以被表示的类作为初始化目标；CP 自身及其原 Java 依赖仍正常初始化。
`constantPoolOop` 源字段保存实际 owner Class mirror，
不是原生指针。这条普通引用由正常对象 reference prefix 扫描。
primitive/array Class 返回 null；缺少原始类数据的范围保留显式缺口。

首版支持14个原 native：Class 的 factory，以及 CP 的 size、tag、UTF8、String、
int/long/float/double、受明确访问证明限制的 class、class-ref/name-and-type 索引、
member/name-and-type 的字符串数组。实现按原 CP tag 和原索引读取，不特判 Logger。
`getClassAtIfLoaded0`、两个 methodAt 和两个 fieldAt 原声明未提供。
`IfLoaded` 不能由初始化状态、mirror 缓存或 AOT metadata 的存在推断。
原 Java 的注解解析、CP public facades 和 Tag 转换保留。

Class 查询只对锁定目录中同 module、同 loader 的 public 类型或同运行时包类型给出
正向访问证明；数组追到最终元素类型，primitive 元素数组可访问。
仅在目录中找到目标不能证明跨 module/loader 的解析与访问合法，未证明范围保留
`context20`，不伪造成 `Class` 返回值，也不把保守缺口当作 JDK 访问拒绝。
当前609,163个已定位 Class 引用中409,319个满足该规则，199,844个保留缺口；
另600个原引用没有可解析目标。全部原 CP 字节和原槽号仍保留。

native 的第二个 Object 参数与锁定 JVM 一样不使用；owner 由正常 wrapper 的源字段取得。
索引包含0及 long/double 的原始保留槽，tag0 为 INVALID；错误 tag 和越界通过原
`IllegalArgumentException(String)`、正常 Throwable 原语和原消息报告。
浮点值只复制原位模式，不经过构建宿主浮点运算。
UTF8 使用原 classfile MUTF8；String 采用本批 compact 配置，String 常量经现有 ASM interner。

ROM 只含原 CP metadata，不含原方法 Code 属性，也不执行 classfile。
当前原目录有53,660个池、8,935,136个槽和142,097,569字节原 CP 内容。
readonly 数据 COFF 的 `.rdata` 为216,217,345字节，只有三个导出、零 import、零重定位、
无 `.text`。其中每类型24字节目录保存 entry 起点、CP长度、状态及原字节区间；
每槽8字节保存原 byte offset 与可解析的类型 ID；最后是未改的原 CP 字节。
这是构建工具产生的只读数据，不是另一种游戏执行语言。

候选 manifest 的 `object` 是实际 ML64 生成的内核，`ROM_object` 是该纯数据 COFF。
两者必须同时进入链接响应文件。三个 ROM 导出是
`boom_constant_pool_directory`、`boom_constant_pool_entries`、`boom_constant_pool_bytes`。
验证器从锁定原 classfile 重建全部内容并逐字节核对数据 COFF，同时独立重汇编内核并
比较执行节、数据、节标志、符号与 auxiliary、重定位和 `.pdata/.xdata`。
String 工厂复用已验证 Methods 内核，只改 private helper/branch 标签。

`test-normal-constant-pool-candidate.py` 从当前 source-verified provider 集合建立新的原 Java
小闭包。未注册阶段显式选择原 `String.intern` native 作为正常 source 根，使 interner
模块及其真实根一起进入选择；不手工补池或根。CP descriptor、原 `<clinit>` 与原 public
getters 由正常选择纳入，不能复用缺少这些内容的旧 Main selection 冒充完整来源。
候选首版不依赖 Deflate 或压缩 ROM，不引入临时原生 buffer 生命周期。

第一次真实 API 冷组件在原 Reflection/Map 初始化到达未选入的
`Object.equals(Object)`，原失败和 producer 字节保留；没有补写类状态。
后续组件通过 `existing-source-selection.py` 复用已完整验证的大 Main 原源码选择。
该开发 helper 不改变原目录，实际执行一次完整 V，并记录实际读取的 batch、IR/shard、
原 source、工具及 COFF 文件，前后核对全部字节、原 canonical RSP 和库。
只读 envelope 校验该具体封存链与当前 source namespace；新 CP 内核与 ROM 分别独立
验真、封存和重链接，明确不属于原 full V 的覆盖范围。

CP 表绑定原 class SHA、loader、原始 input 和当前类型目录。动态定义、重定义或变换链
改变 CP 时需要重新生成目录；当前不宣称 live redefine/类卸载支持。
source-only pending state 不代表 runtime accepted；此组件不代表 Main、世界或完整游戏启动。

当前实际组件回执为
`.boom/normal-constant-pool/execution-v177-h/execution-image/execution.json`
（SHA256 `5bfeb83579d347a88ab269827935bc47b15024c0c1779cf506a0d39408b26468`）。
组件先通过正常 `boom_class_ensure32(String)` 执行原 String 初始化0→2，保留 CP 冷态；
早期未准备该 VM 前置的 String 转换失败及原 producer 另外保留。
随后八个真实 OS 线程并发完成原 CP 初始化，六个原类61个选定条目通过原 facades，
140项成功查询与4项类型异常消息逐项对照锁定 JDK；八个暖 OS 线程另执行256次调用。
未证明的原 Class 引用实际返回20，primitive/array 返回 null，原 Pattern 状态保持0。
两轮静止 GC 真实扫描12个跨度（包含109个 properties cell、4,096个 IO owner root 和
16,384个 park gate root），保根后回收792对象，释放15个 fixture CP wrapper 后再回收15；
最后 source trace 和 heap 均完成清理。OS 工人是测试线程，不宣称 Java `Thread.start`。

源码/机器证明来自
`.boom/normal-constant-pool/source-bound-v174-c/verification.json`；
原 Java/191原 COFF 的独立重验 envelope 为
`.boom/normal-constant-pool/existing-main-source-v170-a/source-envelope.json`。
这些都是当前107 source namespace 下的未注册候选证据，不代替后续正式 provider 登记和主进程验收。

Root 在新的 `.boom/normal-constant-pool/root-source-v181-a` 中独立重建原目录模型、
完整只读 ROM 和规范内核机器验证，proof SHA256 为
`7b406b8569830f08428f0df9c6b75f651925c990b16b8ffae6cceddf3646844a`。
随后沿封存的原 Main 源链重新链接，在新冷进程完整复跑原 Java API、JDK 对照、
冷／暖八线程、未证明 ClassAt 的20、12真实根跨度与两轮静止 GC。
独立回执 `.boom/normal-constant-pool/root-api-v181-a/execution-image/execution.json`
verified=true，SHA256 为
`d754a44d7514fd1eb3947883c37ff8601c815c5559ef249e197b1d9fb05e3376`。
Root 另行通过15项 parser、readonly COFF 和保守类访问模型测试。旧 b 版及其组合
Main 前缀保留为历史实验，不在原路径上更改收据或改称当前 c 模型证明。
