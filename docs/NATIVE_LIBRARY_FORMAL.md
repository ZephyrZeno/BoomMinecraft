# NativeLibraries 正式包组件验证

`scripts/test-native-library-formal.py` 面向当前 26 包输入中的 `normal-native-libraries-v1`。原 `NativeLibraries` 三个 native 和 `NativeLibrary.findEntry0` 均通过正式源 wrapper 调用；原 Java 方法 ID、字段偏移、Code 哈希从锁定类文件和当前正常布局取得。

执行器支持公共 `formal-provider-selection.py` 的全新选择，也支持独立重新验证已有完整 26 包源选择。后者保留其全部原 Java、元数据、COFF 和诊断 stop。在独立目录中额外汇编 `vm-entry-source.binding_model(closure, False)` / `assembly(model)` 的构造器入口，检查实际 COFF 定义和导入，并严格核对整个 canonical LINK 参数序列。额外镜像封存原全部 COFF、编译器输入、构造器模型、执行器源码，以及同一 Windows SDK 的库路径和摘要。

`boom_vm_bootstrap_main` 使用编译生成的 192 字节 ABI1 绑定池和原四个 primordial 构造器，创建实际主 `Thread`、两个 `ThreadGroup` 和 ACC，并建立真实 FLS 附着。测试不调用 `boom_process_entry` 或 `System.initPhase1`。宿主不会写类初始化状态、`Thread` 字段或 `NativeLibraryImpl` 字段。

名字通过原 `String(char[])` 构造器建立；`fromClass` 来自原 `Object.getClass`，库 receiver 执行原 `NativeLibraryImpl(Class,String,boolean)` 构造器。工人 `Thread(String)` 对象也由原 Java 构造器建立，再使用各自源码生成的 tid 附着到八个测试 OS 线程；这里不计为执行了 `Thread.start`。

验证目标包括 builtin 名称、null filename 的原 `InternalError` 和消息、重复 receiver、未附着调用者、unknown module、错误 HMODULE、已有异常的保留；八个 receiver 同时加载时共享一份实际模块 pin，最后一份卸载释放它。net 的 false/true 配置经原 `Properties` 构造器、`setProperty`、`System.setProperties` 发布，再由实际 `Boolean.getBoolean` 回调读取，检查真实 Winsock 使用和最终 `WSANOTINITIALISED`。结束时检查模块 pin、registry、源 frame TLS 与正常 heap 清理。

同 SDK `ws2_32.lib` 中五个 API 的 short-import 元数据决定 PE 的预期导入 token；SDK 使用的 ordinal 不被假定为函数名。输入和额外镜像的验证始终保留当前 provider/source 验证，不接受旧 candidate、scratch 描述符或 stop 替换。

## 运行

默认输出为忽略目录 `.boom/native-library-source/formal-*`。提供当前 pending26 state；只有源码和 COFF 的验收不要求状态提前写成 accepted。

```powershell
D:\Dev\Python312\python.exe scripts/test-native-library-formal.py `
  --state <pending26-state.json> `
  --output .boom/native-library-source/formal-cold-001
```

已有完整源选择可用 `--selection <round-directory>`；执行器仍会重新运行完整独立验证，并确认全部原测试方法与实际正式包已经选入。原源码选择和历史执行回执保持原样。

失败保留完整输出目录、worker 日志和可解析时的 `first-failure.json`，其中包含原 source row。遇到未选 Java，只能在新目录通过原方法/整类正常准入重建选择，不能改写 stop 或类状态。

## 范围

本执行器属于 Python/ctypes 开发测试宿主；实际 Java、native、线程 registry、模块 pin 和 Winsock 逻辑均由 ASM 执行。它验证 builtin net/nio 的限定协议，不宣称完整 `NativeLibraries.loadLibrary` Java 链、外部 JNI 库、标准 `JavaVM`/`JNIEnv` 或完整游戏启动。坏 JNI 版本注入仍属于此前独立故障实验，正式包测试不修改回调或版本。

原静态/failure 根、properties 根和新增构造器绑定根可读出观察。物理根跨度与本组件的资源释放检查不计为自动 GC 或完整栈根实现。

## 本轮真实结果

`.boom/native-library-source/formal-v146-main-reuse-attempt001/result.json` 已由独立 worker 自然 exit0 产生，SHA256 为 `8c50003485c955b9e6365d2f6df4c3a1d77f78fc6a308af605882bd9875e052c`。复用的 v146 原主选择包含 4,701 类和 45,776 个 Java 方法；执行前两次完整独立源验证均通过。额外构造器对象为 4,731 字节，原所有 source COFF 保持原样，额外镜像完整输入回执位于同目录的 `extra-image/extra-image.json`。

正式四 native、原构造器和 API、null typed InternalError 消息、重复/未附着/unknown/错误 handle/已有异常、八个真实 OS 线程共享一 pin，以及 false/true 两次 net 属性回调和实际 Winsock 卸载均已通过。八个工人使用原 Java 构造器生成的 tid 2–9。最终 pin 为零，registry、源 frame TLS、heap 清理通过。

三个主类在新 DLL 中均从 cold0 开始，其原 failure 根位于正常静态根 bank 的 cell 7805、7816、7820。观察到十个原/新增根 bank，包括 10,591 个静态/failure 单元、109 个 properties 单元和五个构造器 VM 绑定根；本测试没有执行或声明自动 GC。此结果是正式包组件验收，不单独把 26 输入改写为 accepted，也不扩展到完整 Java 加载链或游戏启动。
