# 相同原始 batch 的当前工具完整复验

`extend-runtime-provider-set.py` 保留原有的直接父级派生约束，并增加显式的
`--batch NEW --equivalent-batch-verification-sha256 SHA256` 路径，用于工具来源改变、
原 Java／类型／布局／模块数据完全相同的 named batch。目标必须先独立执行完整
batch verifier；参数绑定新完整回执，当前严格 named resolver 仍重新验证来源。

旧完整回执必须仍绑定原 summary、derivation、parent 和模块源图。两边整个 summary
只允许唯一 JCLS ASM／COFF 的产物位置变化；原 Java 单元、代码与对象摘要、类型
容量、模块槽、profile 和其他元数据必须相同。两边完整回执的每个覆盖项和执行标志
也必须相同，仅允许 named 派生来源记录变化。原 parent／模块图／append／声明变化
证明均不得变化。

JCLS ASM 字节必须完全相同；实际机器 COFF 按现有完整核验器比较指令、unwind、
数据、section flags、索引符号与 relocation，rdata／BSS 符号移动和新增根字节均必须
为零。旧回执保持原样。后续所有旧 provider cache 仍由当前源模型重新构造和校验，
新 family 仍实际汇编，最终输出仍是 `pending_runtime_acceptance`，不会继承游戏执行成功。

7项边界测试覆盖新完整摘要、当前 resolver 拒绝、原 Java／profile／类型容量、覆盖
标志、旧来源绑定、原模块图、ASM 字节和 COFF 符号／根布局变化。根独立对真实
`v148-jdwp-production-b` → `v149-jdwp-tool105-a` 执行新检查通过，回执为
`.boom/equivalent-named-transition-root-v154-a.json`。这是已有两个完整 batch 的
真实等价检查；尚未将未来的工具清单切换或新增反射 family 记作通过。
