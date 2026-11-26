# 正式 Reference provider 冷源执行

`scripts/test-reference-referent-formal.py` 用于验证正式 `normal-reference-referent-v1` pack 的四个原 native 和原 Java 入口。它不接受历史 native candidate，不替换开发 stop，不补写接收者或类初始化字段，也不使用独立 scratch ASM／COFF。

## 源选择与执行规则

构建链由公共 `scripts/formal-provider-selection.py` 完成：核对同批正式 26 份 provider 的 source／COFF／receipt，常规 source selector 选择 Java 和 provider 依赖，原生汇编／链接后执行完整独立 source verifier。Reference 脚本只提供自己的普通 Java 入口、观察符号及执行断言。

测试显式请求已验证原 Java Object／Weak／Soft／Phantom 构造器及 get／refersTo／refersToImpl／clear 等 11 个入口；普通类根仅为 Object、WeakReference、SoftReference。Reference、PhantomReference、FinalReference 三个所需类不允许作为手工 class root 或 admitted class，必须出现在正常 provider 依赖选择中。其引用静态字段和类描述符中的失败根均必须位于标准 `boom_probe_static_roots` 区域；不提升 private failure-root 符号为 PUBLIC。

新进程中先检查三个描述符处于冷状态，再执行原构造与委派。结束时核对原 Reference／Phantom 初始化已完成，Reference 原初始化器已在正常静态根中发布 processPendingLock。FinalReference 仍只提供非法 private-native 类型负例，不将该对象分配计为其构造器验证。

执行器复用此前独立实际通过的 `test-reference-referent.py` 中的线性化和 JDK 对照工具。原 Java／native 操作、8 OS 线程的 16 轮 2048 次调用、四轮静止 GC、根向量完整快照与压缩的核心 AST 保持一致；新增内容为正式 pack 加载、冷类／标准根检查和正式组件结果范围。公共执行块 AST SHA256 为 `878a284cdb8de749e2e6badeb8770038076e7561a5f12ce3c6e8607795347c96`。

只为实际链接的 PUBLIC 根符号增加观察导出。未选择的 Properties、intern、线程等模块不因测试而额外纳入；每份实际 span 的物理数／非空数／摘要、全部非空 oop 集合包含断言、附加测试句柄、根向量去重前后数和摘要继续记录。所有工人 join 后才回收，原根槽和 referent 均不由宿主写入。

若普通 Java 依赖未选入，失败保存实际诊断 pool 的 row／context 和原 source manifest；后续只允许依据该实际源缺口，将相同原类的已有 Java Code 经正常准入加入新选择。禁止改虚表、改初始化状态或手工补齐三个必需类的描述符。

## 本次正式组件结果

输入为 `.boom/pending-native-three-families-v145-three-families-26-9e4944c57a424d038bb7679b56009811.json`，其逐 pack 输入已验证、整体状态仍为 `pending_runtime_acceptance`。Reference 正式 pack 为该 namespace 下 `new-families/normal-reference-referent-v1/provider.json`，SHA256 为 `c827778521bccf8c0d8a5a46680d7ec2b4a0c752811ad8268cf9b42ff38a0178`。

`.boom/reference-referent/formal-v146-cold-a` 的首个正常选择和实际 worker 均完成。源码闭包只有 13 类、22 个原 Java 方法，`admitted_classes` 为空；三个必需描述符和四个 native 均由正常选择处理，没有后补 Java source、scratch metadata 或 stop 替换，也没有修改原 Java、COFF、虚表或初始化状态。

标准静态／失败根 bank 有 54 个槽。三个描述符进入测试时均为冷状态 0；Reference 和 PhantomReference 的原初始化结束为 2，FinalReference 仍为 0，因为它只参与非法接收者类型检查。三个失败根位于正常 bank 的第 5、6、8 槽；原 Reference.processPendingLock 位于第 7 槽，由原初始化器从 0 发布为真实对象，四轮 GC 后仍在正常根中。宿主没有写这些槽。

原 Weak／Soft／Phantom 构造器、get／refersTo／clear 委派及四个有帧 native 全部执行。身份／null／重复清除、16 个非法接收者样例、外堆比较参数、private-native 类型前提、已有错误保留与回收后 stale 接收者拒绝均通过。8 个不同 OS 线程的 16 轮 2048 次操作具有有效线性化证书；锁定 JDK 对照、四轮真实 GC 和最终堆销毁通过。

本次实际链接的根 span 是普通静态／失败根、String literal、Class、Class name，共 1,046,782 个物理槽，8 个非空源值。没有为测试增加 Properties、intern、access、signal、thread 根模块。紧缩根向量继续逐值检查完整性，附加测试句柄分别记录；四轮释放对象数为 27、0、1、1，原根 bank 前后摘要相同，继承 referent、清除后的独立强目标及最终回收结果均符合预期。

## 证据与复验

- 实际执行：`.boom/reference-referent/formal-v146-cold-a/execution.json`，SHA256 `d6f9d944ee745d7355d14e66e48cc7a311724dc76a8647b94b49e4ca5366eb4e`。
- 完整源码选择证明：同目录 `source-selection/selection-verification.json`，SHA256 `a6b4ffb9345126e724501d77f0cc80a452d83e3875952bb0f47f516ef7740a89`。worker 在加载映像前又执行完整公共 `verify`，核对封存输入。
- 公共 helper 的 `source-selection/images.json`：SHA256 `e8bda73c8a5f532f71cc43d00ac1100a6c7216816c0668fa5b449a9984d2c8a7`，封存 26 个引用、当前 source／frame／runtime、全部实际链接输入、实际 optional exports 和 harness 摘要。
- `source-selection/linearization-52322b1ca2794b3fbc50d98949cc41ac.json`：SHA256 `cee069d58430df1cfcabd4b1ab924734b69660d1d58850953c7310ba46f743fb`。
- `source-selection/quiescent-GC-bcb32c07cf8a467880e13cd2eca8e9e2.json`：SHA256 `2966736d1b937e15d003e0bcbd91a701ea7c3ca095b533db311afa1c9067a0b7`。

用同一正式输入在全新目录重放：

```powershell
& D:/Dev/Python312/python.exe scripts/test-reference-referent-formal.py `
  --state .boom/pending-native-three-families-v145-three-families-26-9e4944c57a424d038bb7679b56009811.json `
  --output .boom/reference-referent/formal-review-cold `
  --workers 8 --code-mib 8
```

前置完整输入／全局索引和 worker 的独立复核都必须自然完成，不按短超时强行继续。若后续批次出现真实普通 Java gap，`failure.json` 和旧目录保留；`--follow-failure <failure.json>` 只允许按该已观测原类的完整已有 Java Code 加入新的正常选择。

本次证明只覆盖正式 Reference 组件，不替代 26 份 provider 的整体运行时验收，也不包含整个 System 冷启动、完整弱引用 GC 或 Minecraft 启动。非移动、静止 GC、原版未变换输入边界继续适用。
