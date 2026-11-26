# Windows 文件元数据汇编内核

`native/runtime/win32_path_attributes.asm` 提供只读 Windows 路径查询，供后续原始 Java NIO 绑定使用。它尚未接入正式启动镜像，也没有代替 Java 方法或完成 Minecraft 启动。

入口 `boom_win32_path_attributes` 使用 Windows x64 ABI：RCX 是调用者持有的规范化、以 NUL 结尾的 UTF-16 路径；EDX 位 0 表示跟随链接，位 1 表示要求句柄查询；R8 指向 48 字节结果区。返回 0 表示成功，否则返回原始 Win32 错误码并保持结果区不变。

结果依次包含 `DWORD attributes, reparseTag`，四个 `QWORD creationTime, accessTime, writeTime, size`，以及 `DWORD kinds, reserved`。时间保留 Windows FILETIME，大小保留 64 位。类型位为普通文件 1、目录 2、符号链接 4、其他 8；目录联接可以同时具有目录和其他标记。所有逻辑为 MASM，外部依赖为 Windows 系统 API。

同一文件另提供 `boom_win32_raw_file_attributes(RCX=path, RDX=result36)`，直接取得原始 36 字节 `WIN32_FILE_ATTRIBUTE_DATA` 并保留重解析标记，供 `GetFileAttributesEx0` 的声明契约使用。它与带有类型分类和链接跟随策略的 48 字节查询是两个入口；客体缓冲区的来源和范围由上层适配器检查。

测试使用 `D:\Dev\Python312\python.exe scripts/test-win32-path-attributes.py --config <锁定输入配置>`，只在 `.boom/win32-path-attributes-tests` 创建隔离文件。JVM 仅作为开发结果对照，不属于交付运行时。

2026-11-26 的验证覆盖 13 个真实路径和 4 种查询模式，共 52 次与锁定 JDK 的对照。其中包含原始 `lib/modules`、UTF-16 长路径、4 GiB 以上稀疏文件、目录联接、本地 Unix 套接字及负 Unix 时间。8 个操作系统线程完成 800 次并发调用；另测 768 次，句柄数保持 196。9 个共享冲突分支使用测试专用的首个 API 错误注入，后续目录条目查询由实际 Windows API 完成。普通符号链接因主机缺少创建权限未测。

接入 Java NIO 仍需验证客体 NativeBuffer 的地址归属和长度、原始字段布局、原始 native 声明及 WindowsException 传播。该内核不自行接收任意 Java long 作为可信本机指针。
