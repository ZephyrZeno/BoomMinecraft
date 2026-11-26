# 公开 FileInputStream 构造链与 Cleaner 边界

`scripts/test-file-input-public.py` 在已实际通过 normal／observed 八项 I/O 测试的候选上，独立执行原 `FileInputStream(String)` 和 `FileInputStream(File)`。两入口各用全新进程，记录冷类、原方法／字段身份、FileCleanable 注册、逐字节读取、显式关闭和后台线程结果。当前公开构造／读取／关闭链已实际完成，整体 `verified` 仍为 **false**：Common-Cleaner 后台线程实际遇到未实现的 `Unsafe.park(ZJ)V`。

## 输入与构建

输入为主 agent 独立重建并完整复跑的八项候选：`.boom/file-input-stream/root-review-execution-v147-a/execution-7305ee5e54cf4dd4ada506146c3e4173.json`，SHA256 `3802862bd01ac58f00ad11caa0d5a7a6f343a692047848cdec0a560d141559cd`。它绑定原正式 26 source 选择、原主进程两层证明和相同 runtime572。新测试不消费正在构建的 28 source，也不修改共享 registry、TOOL_FILES、runtime、Thread provider 或已冻结的八项 I/O 源文件。

原 Java `FIS(String)`（本批 39415）、`FIS(File)`（39416）、`File(String)`（39310）、`FileCleanable.register`（39381）、`FD.unregisterCleanup`（39397）、`PhantomCleanable.clear`（116461）、`CleanerFactory.cleaner`（116434）以及全部 String／Properties／JLA API fixture 均已在原选择中。测试再次从原 classfile 取得声明、类／Code SHA，逐项核对 selected_methods；没有补 Java 方法、重新生成 Java、替换 stop 或改变虚表。

构建只在新目录重链已接受的八项候选 RSP，补原 PUBLIC 观察导出。普通字段、FileCleanable 中继承的 Reference.referent 和 PhantomCleanable.prev／next，均按当前声明身份和正常布局动态解析，核对宽度、reference-prefix 和边界。编号只记录本批证据，不作跨批次约束。

`--primordial` 额外调用既有 `vm-entry-source.py` 的 `M.binding_model(closure, False)`／`M.assembly`，生成已验证机制的原 Thread、ThreadGroup、AccessControlContext 构造绑定。新增两份测试 ASM／COFF 是正常 primordial 绑定和原生生命周期 owner；原 Java／候选 I/O COFF 不变。owner 使用现有 Reference／Object.wait 开停关和 Thread join／reap／detach／destroy API，并以 MASM 安装／清除原生控制回调，沿用 vm_process 的生命周期次序。它不执行完整 System Phase1，也不以宿主改写 Java 字段或 GC 根。

属性配置通过原 Properties 构造器／setProperty／System.setProperties；JLA 由原 System.setJavaLangAccess() helper 设置。公开测试从未用 FIS(FileDescriptor) 代替 String／File 构造器。

## 先前夹具缺准备的首败

`.boom/file-input-stream/public-v147-a` 的两个原公开构造器已打开文件，随后在 InnocuousThread／CleanerFactory 初始化中失败，保留 Context `[7,101,112685,...]`。同一部分构造对象的原 FIS.close 成功释放句柄，最终 handle／buffer／owner-root 为 0，trace 和堆已释放。首次工具快照、两个 first-failure.json 和 worker 日志均保留。

该 PC 不能直接确定错误来自 literal 或 Unsafe 查询。b 目录只读复核得到：

- 原 Thread／ThreadGroup Class literal 和原 `parent` String literal thunk 均正常返回。
- 原 Unsafe.objectFieldOffset 对四个 Thread 字段及 ThreadGroup.parent 全部成功，返回正常 UFL2 cookie。
- 独立调用原 Thread.currentThread 返回 0、kind 7。夹具没有绑定真实 primordial Thread；InnocuousThread 后续调用失败时仍保留之前 literal 的 PC 101。

因此 a／b 不算生产 UFMP 或 literal 缺实现。它们均保持 `verified=false`，没有修改 runtime／UFMP 或给原初始化状态打补丁。b 的 `readonly_failure_diagnostics` 保留全部值和 Context，工具快照也保留。

## 准备真实线程后的实际结果

c／d 使用正常源构造机制建立真实 primordial Thread／ThreadGroup／ACC，FLS 的原 Thread.currentThread 与该 main oop 相同，原生 Reference／Object.wait 域已打开。两个公开构造器分别在冷进程实际返回：

1. 原 FileCleanable 注册到新 FD.cleanup，实际类型为正常 FileCleanable；其继承 referent 等于 FD，保存的 handle 等于真实拥有 handle。
2. 原 FIS.read() 读取 fixture 全部字节并返回正确 EOF。
3. 原 FIS.close 经 FD.unregisterCleanup、PhantomCleanable.clear、Reference.clear0 和 FD.close0 完成：FD.cleanup 清空，原 cleanable.referent 为 0，源 handle 为 -1，八项候选 owner-root 清空。
4. 重复原 close 正常返回，没有宿主写这些引用槽或直接关闭 OS handle。

Common-Cleaner 的真实 OS worker 同时开始执行原 Java 任务。它停在实际 diagnostic row **52191**、`boom_m113401`，即锁定原 `jdk/internal/misc/Unsafe.park(ZJ)V`。该原 native 目前没有 Java Code 或正常实现；原调用者是 LockSupport 方法 70864、常量 49、opcode 182。Unsafe class 源 SHA 为 `4eedcb406551d3cb1e06208f310e98f820b3aa1cb1cc952e76bf7752e8a9d736`。

worker Context `[0xB001,11,70866,...]` 仍保留此前 LockSupport.<clinit> 的 literal PC，真实归因来自 diagnostic pool 的已发布 row，不能把它误报为 literal／字段查询失败。公有构造链成功与后台 park 缺口分别记录；整体结果不记通过。

d 两个进程的 worker started／task entered／uncaught callback／exit callback／exit callback success／reaped 都为 1，task returned 为 0，worker failure state 为 2。现有 stop／join／域关闭／registry detach／destroy 均完成；真实堆 monitor 计数为 0，所有文件句柄、私有缓冲区和 I/O owner-root 都为 0，trace／堆销毁成功。未运行自动清理动作，也没有伪造 park 返回成功。

c 的初版观察把 Thread pool `+192` 错标为 held_monitor；按该 provider 实际协议，它是 uncaught 回调计数。c 结果与当时工具快照原样保留；d 修正观察名称，并从真实堆 `+112` 读取 held_monitor=0。该修正没有改变任何执行中源码或 MASM。

## 证明与重放

- 最终聚合：`.boom/file-input-stream/public-v147-d/result.json`，SHA256 `97f3fe2650c3013bad6f3511bb648540148f018bc436bc55665c97c96d6f5d06`，`verified=false`。
- String 冷进程：同目录 `string-execution.json`，SHA256 `6e85a9cdef072b9aa99110af87243d40c059ce4b40232d8d862ab1b1492c5a71`。
- File 冷进程：同目录 `file-execution.json`，SHA256 `56029843ff20cdd66453c1cf6bb3441050973a2ecd16d1d49999e3606b53fa5d`。
- `public-images.json`，SHA256 `9adc050b013819a4085f8afebf70c8a70f8a8cee248eb9a3dcae0a55bfc4fe38`，封存旧输入、原 Java 模型、生成器和两份额外测试 ASM／COFF。

在全新目录重放当前真实边界：

```powershell
& D:/Dev/Python312/python.exe scripts/test-file-input-public.py `
  --accepted-result .boom/file-input-stream/root-review-execution-v147-a/execution-7305ee5e54cf4dd4ada506146c3e4173.json `
  --primordial --output .boom/file-input-stream/public-review
```

不加 `--primordial` 可重放 API 夹具未准备 main Thread 的首个边界。脚本保存自然执行结果，进程正常写出 JSON 不等于整体功能验收；应检查 `verified` 及独立 worker 诊断。

主 agent 使用自己的八项 I/O 独立执行回执，在全新目录
`.boom/file-input-stream/public-root-review-v147-a` 复跑两个冷进程。聚合
`result.json` SHA256 为 `6fd3c1eaafe64bc06002491fc15c3d4e00ddbaabf8d557a129286c598e7a3184`，
同样保持 `verified=false`。两个公开构造器、完整读取和原清理／关闭链均完成；
实际 worker 仍准确停在 row 52191 的 Unsafe.park，随后退出并回收，真实 monitor、
文件句柄、缓冲和 owner 根归零，堆正常销毁。

## 文件类型范围

当前八项 ASM 打开后只检查 `GetFileType(handle)==FILE_TYPE_DISK`。该 Win32 类型可能包括 volume 设备，不能等同额外路径黑名单或严格的普通文件判定。本轮只实际访问 `.boom` 隔离 fixture 的普通文件，没有测试任意 device／volume 路径，不对其作完成声明。此前“普通文件”的范围应理解为实测输入范围。

公开构造／注册／读取／显式关闭已执行，不替代 Common-Cleaner 完整工作、自动 Cleaner／弱 GC、正式 28／后续 provider 验收、完整 System／VM／Minecraft 启动。下一实际 native 边界为原 Unsafe.park，以及与之配套的 unpark 线程协议；本测试没有实现它们。
