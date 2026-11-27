# RandomAccessFile 字段登记

`native/providers/random_access_file_init_ids.asm.inc` 实现原
`java/io/RandomAccessFile.initIDs()V` 的纯汇编登记服务。
原生语义依据锁定的
[OpenJDK 21.0.13+3 RandomAccessFile.c](https://github.com/openjdk/jdk21u/blob/jdk-21.0.13%2B3/src/java.base/share/native/libjava/RandomAccessFile.c)：
缓存 `fd:Ljava/io/FileDescriptor;` 一项 FieldID。原 JNI GetFieldID 要求声明类正常初始化，
不能用初始化被引用的 FileDescriptor 类代替。

服务执行正常 `boom_class_ensure32`，按原 Class、UFMP、FMAP 和物理布局核对字段，
缓存原 `boom_field_map26545` 地址函数，再通过已有 `boom_stream_fields_init` 发布独立流描述符。
此 FieldID 不保存 Java oop，不直接修改 Java 字段或类状态。
实际输入中的 `fd` 为 private final 实例引用；全部类文件与本机锁定 Azul 21.0.13+1 JMOD 逐字节核对，
该输入和上游 C 参考版本分别记录。

RFID128／ABI1 的 ready 在字段缓存和流描述符均发布后置为 1，正常字段函数位于偏移 64，
独立 SFPL32 位于偏移 80。声明字段的原 FMAP 包含 RAF 和 LogFile 两种接收者；
SFPL 的既有流 getter 只接受精确布局，后续支持继承对象时必须使用原 FMAPPROC。
已有 pending Context32 时完整保留，不在短发布锁中执行 Java 类初始化。

长期工具 `scripts/random-access-file-initids-source.py` 投影原始 C、类、Code、字段与实际 Frame 数据，
`scripts/random-access-file-initids-candidate.py` 显式接受 state、source、parent、pinned、
field-records-source、release、assembler 和新 output，生成 native／registry 两对象。
独立 verify 重新投影来源并重汇编，比较完整非调试代码、数据、节标志、符号辅助记录、重定位及 unwind。
候选仍未登记为原 35 包的完整验收结果，没有重建 runtime DLL、改变原 117 来源文件或增加 Java 根。
主 agent 已从正式路径独立重建，两个生成 ASM 与已实际执行的版本逐字节相同，
旧／发布／新 canonical 对象的完整非调试 COFF 相同；原 C、Code、Frame、字段、布局和缓存模型也分别核对。

## 实际组件与进程

独立 219 对象组件从真实 System phase1／线程本地绑定开始，
原 RAF 类和两个缓存均为冷状态。原 native Frame 经原始 14 字节 `<clinit>` 正常返回，
Class state2、登记 ready1、字段函数和 SFPL 发布值均与实际源码对象一致。
两个正常布局夹具分别通过原 FMAPPROC 得到正确地址；六种已有 pending Context 和三个错误参数检查通过。

八个不同 OS 线程分别执行原 Java Thread 构造器及 threadId getter，再经实际 attach／FLS 绑定，
共调用 128 次原 native Frame。全部 detach 后，十三个根区、查询槽、线程、帧、堆、JIMAGE 和 RW Owner 完成清理。
测试未向 Java 对象或 Class 状态写入宿主数据，也未执行 RAF 文件打开。

主 agent 的 218 对象 EXE 只替换原剩余 native 停止对象并增加两个对象，
其他 215 个对象及原进程入口／十三根区保持字节相同。三组完整 COFF 与独立完整 PE 重链接比较通过。
实际 `net/minecraft/server/Main --help` 初始化已越过 initIDs，
下一停止为 `RandomAccessFile.open0(Ljava/lang/String;I)V`，方法 40489、诊断行 104450，Context method112599／PC3。
进程自然退出 86、未超时，System 三阶段到 VM4；三工作者退出／回收、清理标志为 7，
RW 的 4,096 字节及全部租约／元数据归零，原库卸载三次，文件／映射归零，三份报告的 Context 一致。

**Main 类初始化、方法体、帮助输出、客户端和世界仍未完成。**
本轮没有实现 RAF 打开、读写、定位或截断。后续文件操作须接入真实 FileDescriptor 所有权和原 close 链；
不能仅创建新 HANDLE，再让旧关闭服务把未知句柄当作已清理。

| 本地证据 | SHA256 |
| --- | --- |
| 原 source／Frame 与两完整 COFF | `b653ee4210849b7a673bdad62ade5ad6084fcfb206f46514b6e2cf5967126abf` |
| 六项来源／机器码拒绝用例 | `93a7b10e12302f760b31e13360f1777d44c3cd052e9125a2651b2e137144420e` |
| 正式工具主 agent 独立重建 | `481e472a148d8daf98a3be05d9c6cc07b6c135ab83aa8145d6f8e31289309e30` |
| 旧／发布／新 canonical 两对象等价 | `6c827eae8321c496fa7e9e065d0c0cb2d04d23703b84f12bcb2b31bcc462806c` |
| 原类冷初始化与完整清理 | `0a4358a607116cf7bcb65b907e5c4a6d35d2bd5a7bc2937c4bbc819fe6b62aaf` |
| 八 OS 线程／128 原 Frame 与清理 | `b5516f469f95a2acfc9fa56be6ccb59646f9d2b4157cf1d5c6abbd5f481a4a1e` |
| 218 对象消费者验证 | `83ffc86bceab6319997d04dd8ceabda4ae965e8c51921c65eea125499caeaa85` |
| 独立完整 PE 比对 | `fd837a7fe0c5a585fd113297050f1d20ea0f28d4389e9091a32ed6c3eba91f4b` |
| 实际原生进程 | `c3bc8da320e15a988547e53f838d3a8c44a3a6d24d1a4015744878167d2e48a6` |

临时 Python、PowerShell、测试输入和编译产物均保留在本地忽略目录。
