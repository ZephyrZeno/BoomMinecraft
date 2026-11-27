# 可写原生内存 owner

`native/kernels/native_memory_owner64.asm.inc` 实现独立的纯 MASM 内存 owner。
它是 [Main 原 `Unsafe.allocateMemory0` 缺口](SIGNAL_SHUTDOWN_ORDER.md)的底层组件，
现已通过[组合服务](UNSAFE_OWNED_MEMORY.md)接入独立 Main 派生镜像，并实际分配和清退区域。
完整游戏和 Main 方法体仍未启动；独立内核与原版入口的执行范围分别记录。
原 89 源汇编运行时、117 项工具来源和原 Java Code 未修改。

## 内核与生命周期

Win64 接口为 `boom_native_memory_init(Owner128*,128,capacity,budget)`、
`boom_native_memory_service(Job128*)`、`boom_native_memory_close(Owner128*)`。
owner 接受 1 至 4096 个记录槽，使用 VirtualAlloc／VirtualFree 管理独立 RW 区域；
核心没有 Java 方法编号、Context、oop 根或可变全局状态。

| Job 操作 | 行为 |
| --- | --- |
| allocate／resize／free | 零大小、精确块起点、预算、溢出和存活借用检查 |
| read／write plain | 已有区域内的 1／2／4／8 字节原始位模式 |
| fill／copy | 按共同对齐选择 8／4／2／1 字节访问，复制处理重叠 |
| copySwap | 2／4／8 字节元素交换字节序，支持重叠和原地操作 |
| borrow／release | 显式读／写借用、单调 token、释放前保留实际区域 |

地址未知时返回独立的 domain-miss，不触碰内存，让上层保留原堆、JIMAGE 只读域和线程计数器路由。
只有本 owner 登记的存活区域可读写；JIMAGE 的只读映射不会变成 RW 分配。
resize 分配失败保留原块；VirtualFree 失败时仍跟踪未释放区域，允许重试关闭。
close 有存活借用时返回 busy，不报告关闭成功；成功关闭后，测试用 VirtualQuery 核对实际 MEM_FREE。
原始地址在 OS 重用后的 ABA 不能靠内部 token 完全消除。

当前核心以 owner 锁串行保护元数据及物理操作；借用供上层的纯汇编数组／映射桥使用。
这里只支持 plain 操作，不包含 atomic、volatile、CAS 或游戏多核性能提升结论。
Java／堆用户结束后的 owner 关闭属于进程生命周期，不依赖 Java GC 清退这些区域。

## 构建与测试

```powershell
D:\Dev\Python312\python.exe -B scripts/native-memory-owner-candidate.py build --output .boom/native-memory-owner/review-core-a
```

构建工具要求全新输出，核对完整规范重汇编 COFF，包括节标志、完整符号辅助记录、全部重定位和 unwind，
并比较完整 PE 字节。候选未登记到运行时，不会执行游戏。

`tests/native_memory_owner.py` 提供有界实际 Win64 测试。
必须显式提供只读输入及其 SHA256；独立 JDK 向量也是可选、显式摘要绑定的输入，缺少时不宣称完成 JDK 对照。
测试不调用 JVM；另一个开发 oracle 先用锁定 JDK21.0.13.0.3 产生参考结果。

实际已通过：

- 9 类正常生命周期／范围／重叠／借用检查。
- 3 类确定的 OS 失败注入，包括 resize 回滚和关闭失败保留；没有消耗全机内存制造 OOM。
- 133 个适用于独立内核的 JDK 向量；另 107 个堆／Java 包装向量没有记入内核执行范围。
- 8 OS 线程的独立块分配／读写／调整／复制／释放，以及共享块读写和借用冲突后的重试。
- 真实只读映射地址拒写、句柄前后相同、关闭后原区域为 MEM_FREE。
- Windows 实际函数 unwind 查询，以及 MASM 探针的非易失寄存器和栈 ABI 检查。

故障测试仅改变 8 个实际 API 调用操作数的目标，新增测试私有故障包装。
生产核心的其余指令、函数、重定位、节标志和 unwind 均与测试变体逐项比对；
测试 DLL 不属于交付运行时。被改写执行字节、节标志或 PE 的坏候选均被规范机器码比较拒绝，未加载坏 DLL。

主 agent 已独立运行发布路径下的实际 builder 和完整 native 测试。
本地 `.boom/native-memory-owner/published-root-test-v229-a/verification.json`
的 SHA256 为 `676ce1c87c836136503b7f3b2f9b6c41ba405103847cae283c5e6480fa2c56e8`。
最初冻结核心的独立复跑为
`.boom/native-memory-owner-v224-a/root-test-v227-a/verification.json`，SHA256
`3b37d3c6faae1fab46ce6629fbead59908dbb51dc16853a057c4ac230dd137b9`。

## 上层接入范围

[组合服务](UNSAFE_OWNED_MEMORY.md)已为原六个声明绑定正常 Frame，组合 plain 类型读写、原堆、RO 映射和 RW owner。
heap byte[]／char[] 与原生地址之间的复制使用独立验证的真实块成员身份和物理字节边界。
原 Java 参数检查和控制流保留；RW volatile／CAS、部分 RO 复制域和完整游戏仍未完成。
