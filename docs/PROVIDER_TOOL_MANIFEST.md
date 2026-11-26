# Provider 工具清单候选

本批新增独立 helper、数据清单、测试及身份实验，不改当前生产 `runtime-provider-source.py`、registry、105项 TOOL_FILES、named65 proof 或任何旧产物。它只验证构建工具路径图和完整文件身份，不验证 Java native 语义、COFF、实际运行或游戏启动，也不接受任何旧 provider/named receipt。

## 数据与接口

`native-config/runtime-provider-tools.json` schema1 记录有序 tool_order、shared_files、31项 family-owned files、每族原 loader/source_id/owner 边界、model/verifier/kernel、源码审计、native INCLUDE、动态加载表及受限 API 作用域。当前清单保留原105项完整顺序，随后追加 `scripts/provider-tool-manifest.py` 与清单自身，共107项。原105项路径序列的 SHA256 固定为 `e9a87cfad93b62c64784041f3eb4a3451da1bea658d0f5ba880e6c718bab5780`；不能靠同时编辑清单中的 count/hash 绕过前缀约束。后续新增族在其后追加，不改 helper 中的族名分支。

helper 的 API 为 `load(root)`、`tool_files(root)`、`tools_identity(root)`、`snapshot(root)`、`verify_snapshot(expected,root)`。默认 root 是项目，独立测试可提供隔离镜像根。load 始终重新审计；tool_files 返回 tuple；tools_identity 返回与现 S 相同的“相对路径→完整文件 SHA256”字典。清单和 helper 本身都进入该字典，空白/注释变化也改变身份。JSON 不内嵌自身哈希，哈希在读文件之后计算，因此没有自引用哈希问题。

路径必须是固定 scripts/native/providers/native/kernels/native/runtime/native-config 域下的规范项目路径；拒绝重复JSON key、重复/大小写别名、绝对/drive/UNC/反斜线/traversal、越界目标、多个路径解析为同一文件、缺源文件及无所有者文件。105前缀及身份控制文件为旧根，新增 model/verifier/kernel 及其依赖必须从实际 producer/verifier 路由可达；不接受任意追加的无关源码。

family 名称没有写成 helper 的条件分支：它读取实际 framed FAMILIES 字面表、经典 producer 的 C加载分支、经典 verifier 的实际准入/加载分支，并与 registry 逐族交叉核对。缺/多 family、漏/换 model/kernel/verifier、源 owner/loader/source_id 不同均拒绝。schema 不把 loader 固定为 bootstrap，也不把 source_id 固定为 java.base；模组与后续 native 族沿用相同路径/身份规则。这个边界只声明工具来源，不能替代原 classfile/变换链/方法/字段/frame 的普通 source verifier。

Python 审计覆盖已使用的字面 module/importlib factory、普通本地 import、静态拼接 native 路径和 KERNELS；未知动态加载、未封存第三方 import、eval/exec 等形式拒绝。两个实际变体从同一 FAMILIES 表导出 model 列，要求显式 dynamic_loads 声明；NativeLibraries 从已源绑定元数据加载 helper 的路径也有独立 data_bound_imports 声明，目标同时必须出现在该模型的静态源码声明中。新加载形式必须显式扩契约并重做当前身份，不能通过自动猜测放行。这是可审查的静态构建来源图，并非任意 Python 程序的通用 I/O 证明或沙箱。

每个 native ASM/INC/TPL 还审计 INCLUDE 目标；未声明、未入身份或非规范目标拒绝。KERNELS 中真正嵌入的 provider `.asm.inc` 必须在工具清单内。模型的 runtime `.asm` 源另列 runtime_contract_sources，并由独立 snapshot 记录完整 SHA；正式 pack 仍必须按现协议验证 runtime_kernel_sha256 及原 runtime/COFF。这些文件没有因为不属于105工具命名空间而被视为可变或已验证。

当前唯一 API 作用域是 `verify-batch-assembly.py` 的 check/file_digest/coff_symbols。provider 只用 COFF 符号 API，不调用其完整 verify()；后者涉及的18个 batch/compiler verifier 不伪装成105清单已封存的闭包。helper 检查现使用者对该模块的属性访问，禁止在旧作用域下新增 verify() 调用；族的 model、primary verifier 或 loader 本身不能以缩窄 API 的方式隐藏依赖。该文件的全部字节仍在身份中，未使用函数或注释变化同样使旧身份失效。

## 缓存与重复成本

tools_identity 只缓存进程内已审计的来源图，最多保留4个根。每次成功调用仍重新读取整个有序工具集合的全部内容计算 SHA256，包含 manifest、registry、helper；不使用 mtime、size 或持久 receipt 命中。任一输入字节变化都会重新完整审计，前后再次全SHA一致后才存入缓存。已加载 helper 自身字节变化则直接拒绝，要求新进程，避免旧内存逻辑为新源码出具身份。返回值和图都与缓存深拷贝隔离。runtime 文件仍检查规范位置/存在，具体字节继续由其独立 runtime contract/快照验证。

真实开发工具测量 `.boom/provider-tool-manifest/performance-v150-b/result.json`，SHA256 `0ba9c0c208931f7d65f5e45656939292d56bc92fb54f841f01810c210868c23d`：旧105全SHA的10次均值0.012068s；候选107冷审计3次均值0.586774s；热调用重新全SHA的10次均值0.030578s。这里只测构建工具耗时，不是运行时或游戏性能结论。未缓存的早期版本每次0.566–0.592s，因此缓存解决的是重复AST审计成本。

## Named resolver 的首次接线边界

当前 named producer 的9项 TOOLS 包含完整 S 文件；该文件中追加一项 TOOL_FILES 就会使旧来源失效。当前 named/boot/候选路径实际使用 S 的 ART/ROOT、check、read、digest、checked、artifact、original_class、write 等正常 I/O 和校验函数，没有调用 S.TOOL_FILES/tools_identity。上述实现字节改变仍必须使 named proof 失效。

未来应由主 agent 一次修改 S，仅让工具列表/身份委托此 helper。helper 不能导入 S，也不执行任何新增 family 模型；只解析源码/JSON并返回数据。因此随后新增族的数据列表不会改变 S 的 I/O 实现。**这第一次接线必须将 helper 整文件加入 named 实现来源集合，使用新来源做真实独立验收；不能自动豁免或改写旧9项 proof。** 本批没有做这一步。只有新证明明确隔离了 named 不消费的 TOOL 枚举数据后，后续 manifest/registry/framed族数据变化才可保持 named 的实现来源集合不变；完整 provider 身份照常包含并重核它们，旧 pack 必须失效并重新验证。任何 S/helper/named 实现文件变化仍按完整字节失效，不能为了复用缓存忽略哈希。

旧 `rebase-runtime-provider-inputs.py` 当前只接受 TOOL_FILES 字面 tuple 的追加；本 helper 接线不属于那个旧规则，不能强走旧 rebase。这是首次生产切换时需要主 agent 明确处理的兼容边界。

主 agent 后续提供的正式迁移入口是 `extend-runtime-provider-set.py --batch NEW --equivalent-batch-verification-sha256 HASH`（ca2964b）：它要求当前严格 named full resolver/完整证明、old/new summary只差JCLS产物位置、覆盖项及原parent/graph/append一致、真实JCLS ASM/COFF/符号/root delta0，再重验全部旧包并真实汇编新族，结果仍为pending。本候选没有调用该入口；首轮 helper/S/named来源接线仍须先获得新full65证明，不能用此工具清单实验代替。

## 独立验证

33项实际单测通过，日志 `.boom/provider-tool-manifest/unit-v150-c/tests.log`，SHA256 `40845d787907c2b8a312c1b4e430103938ff53d9138e8bc494c1aeb70d33329d`。覆盖原105顺序、控制文件身份、JSON/路径/重复/缺族/漏model/kernel、隐式Python/native INCLUDE依赖、动态和数据绑定加载、过宽API、mod loader数据边界、全部字节失效、缓存每次全SHA、相同mtime与size的manifest/source内容变化、返回图污染及独立runtime合同变化。

独立身份实验 `.boom/provider-tool-manifest/identity-experiment-v150-c/result.json`，SHA256 `85772cf9f24ae30959e6fcc35c374742efef5faedb4268f0e85a14df4be552d9`，只在新的隔离源码镜像内把已测试Std2源码、ASM及数据路由追加为第32族，107→109项。S/helper和拟议 named9+helper 的完整实现字节保持相同；manifest/registry/framed数据及新2文件使旧 provider 身份实际拒绝。随后真正改变镜像 S.digest 的函数体，旧身份及 named实现投影都改变；改变 helper 字节直接拒绝旧内存实现。恢复原字节后重新严格核对，实际项目源未改。该实验没有执行新增 native、没有接受32-pack或named batch，也没有把投影相等宣称为实际旧 proof 已通过。

较早 standalone-v150-a、identity-experiment-v150-a/b 和 unit-v150-b 保留为未缓存或较窄审计阶段历史；最终证据使用上述c轮和性能b轮，没有覆盖旧文件。

```powershell
D:/Dev/Python312/python.exe -m unittest discover -s tests -p provider_tool_manifest.py -v
D:/Dev/Python312/python.exe scripts/provider-tool-manifest.py --output .boom/provider-tool-manifest/NEW/identity.json
D:/Dev/Python312/python.exe scripts/test-provider-tool-manifest.py --output .boom/provider-tool-manifest/NEW-experiment
```

输出目录须全新；第三条用于当前Std2尚未注册的独立候选环境。共享生产切换、首轮 named来源大验证和provider重新验收均由主 agent 后续负责。

根独立重新运行33项测试和两个 CLI 均通过。独立来源图回执
`.boom/provider-tool-manifest/root-review-v154-a/identity.json` 的 SHA256 为
`6bff72afdb0b5eb75d3101ab9811078ffb1293e5b3bc7bdb581fdb5cff7c468a`；
隔离追加实验 `.boom/provider-tool-manifest/root-experiment-v154-a/result.json` 为
`524bb64815f8a2a8ec4b824fd2604a62743b193ac4d665aa6d8291ccb676dfb7`。
这两项仍只验收独立工具图候选，生产接线边界不变。
