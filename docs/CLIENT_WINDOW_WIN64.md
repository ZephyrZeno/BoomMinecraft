# Minecraft 1.21.1 的 Windows 汇编窗口后端

首个图形里程碑是在原版客户端的渲染线程上，创建符合原版参数的窗口和 OpenGL 上下文，绘制原版内容并完成第一次缓冲交换。窗口管理、LWJGL 调用封送、事件分发、内存管理和渲染调度均由项目的 x64 汇编实现。Windows 和显卡驱动提供窗口、WGL 和 OpenGL 系统接口。

当前实现验证了一个调用契约。原版 `GLFW.nglfwCreateWindow` 的已生成汇编可调用 `JNI.invokePPPP(IIJJJJ)J` 的自研适配器。其生产规格仍指向上游 `glfw.dll` 的命名导出，GLFW 内部尚未汇编化。无窗口测试实际执行的是本地测试 DLL，类状态、调用帧追踪和异常服务来自测试夹具。真实窗口、驱动上下文和首帧均待验证。[汇编适配器](../native/providers/lwjgl_window_call.asm.inc) · [来源验证与生成](../scripts/lwjgl-window-provider.py) · [无窗口集成测试](../scripts/test-lwjgl-window-provider.py)

## 原版走到首次呈现的路径

下表的 PC 是方法内的原始 Java 字节码偏移。使用 Mojang 1.21.1 客户端映射还原了类名。这里追踪正常桌面窗口的渲染循环，配置、显示器、输入设备和资源加载会影响条件调用。

| 阶段 | 直接从锁定字节码得到的调用 | 汇编后端的责任 |
| --- | --- | --- |
| 初始化 | `Main.main` 在 PC 1492 建立渲染线程身份，1504 调用 `Minecraft.<init>`。`Minecraft.<init>` 在 731 调 `RenderSystem.initBackendSystem`，进入 `GLX._initGlfw`。后者先检查已有错误，在 18 安装错误回调，在 22 调用 `glfwInit`。 | 建立库状态、线程身份、错误码和错误描述的所有权。实现 GLFW 回调的 Win64 到托管帧入口。原版在建窗前就会安装回调。 |
| 选择显示器 | `Minecraft.<init>` 在 743 创建 `VirtualScreen`。`ScreenManager.<init>` 在 26 设置显示器变化回调、在 30 枚举显示器，对每个返回项创建 `Monitor`。`Window.<init>` 在 147 查询主显示器。 | 用 `EnumDisplayMonitors`、`GetMonitorInfoW` 和 `EnumDisplaySettingsExW` 建立显示器与模式表。为原版提供稳定的显示器指针、实际像素尺寸、刷新率和正确生命周期。 |
| 创建窗口 | `Minecraft.<init>` 767 → `VirtualScreen.a` 15 → `Window.<init>`。窗口构造在 203 重设 hints，在 210–242 写入六项，再于 278 调用 `glfwCreateWindow`。六项指定 OpenGL、原生上下文、主版本 3、次版本 2、core profile 和向前兼容。 | 保存每次创建使用的 hints。用 `RegisterClassExW`、`CreateWindowExW` 和 `GetDC` 建立 `HWND/HDC`。窗口记录管理这些句柄及 `HGLRC`，向原版返回稳定的项目内窗口指针。标题需从原版 UTF-8 转为 UTF-16。 |
| 建立图形上下文 | `Window.<init>` 在 425 调 `glfwMakeContextCurrent`，428 调 `GL.createCapabilities`，432 开始查询纹理能力，447 设置窗口尺寸约束，455 查询帧缓冲尺寸。 | 使用临时 WGL 上下文发现扩展，选择可双缓冲的像素格式，对最终窗口的 DC 设置一次像素格式，再用 `wglCreateContextAttribsARB` 请求上述 3.2 core/forward 配置。绑定到渲染线程，并验证驱动实际返回的版本和 profile。失败要保留原因并销毁已取得的句柄。[微软像素格式约束](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-setpixelformat) · [Khronos WGL 上下文规范](https://registry.khronos.org/OpenGL/extensions/ARB/WGL_ARB_create_context.txt) |
| 窗口与输入 | `Window.<init>` 在 468、482、496、510、524 安装帧缓冲、位置、窗口大小、焦点和光标进出回调。`Minecraft.<init>` 在 882、908 配置鼠标与键盘，在 2190 应用垂直同步选项。 | 按签名保存回调，替换时返回旧值。将 Win32 消息转换为 GLFW 的坐标、键值、修饰键、Unicode 字符和滚轮单位。窗口大小、客户端区域、帧缓冲像素及 DPI 分开维护。处理关闭请求、显示器变化和回调重入。[微软消息泵](https://learn.microsoft.com/en-us/windows/win32/winmsg/using-messages-and-message-queues) · [Windows DPI 变化](https://learn.microsoft.com/en-us/windows/win32/hidpi/wm-dpichanged) |
| 绘制并交换 | `Main.main` 1599 → `Minecraft.run` 92 → `runTick(boolean)`。后者在 330 清理缓冲，在 415 的渲染分支调用 `GameRenderer`，524 将渲染目标输出到屏幕，570 调 `Window.updateDisplay`。它在 4 调 `RenderSystem.flipFrame`，后者在 0 和 16 轮询事件，在 13 交换缓冲。 | 在绑定的渲染线程执行原版 GL 命令，之后用 `SwapBuffers(HDC)` 呈现。消息泵按原版顺序驱动。`wglSwapIntervalEXT` 按驱动能力处理同步选项。保留窗口销毁、解除上下文绑定与 DC 回收顺序。[微软 SwapBuffers](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-swapbuffers) · [Khronos 交换间隔扩展](https://registry.khronos.org/OpenGL/extensions/EXT/WGL_EXT_swap_control.txt) |

## GLFW 调用清单

扫描官方客户端 JAR 全部类文件的显式调用指令，并按常量池的 owner `org/lwjgl/glfw/GLFW` 和方法名去重，得到 **9 个调用类、70 个调用点、47 个方法名**。下表省略共同前缀 `glfw`。方法名相同的不同重载共享一项。实现仍需按完整描述符区分。

| 功能 | 客户端字节码直接调用的方法名 | 启动时机或分支 |
| --- | --- | --- |
| 初始化、错误和时钟 | `Init`、`GetError`、`SetErrorCallback`、`GetPlatform`、`GetTime` | 初始化前后即可查询错误。单调时钟可用 `QueryPerformanceCounter/Frequency`。平台探测决定图标等分支。 |
| 显示器 | `SetMonitorCallback`、`GetMonitors`、`GetPrimaryMonitor`、`GetMonitorPos`、`GetVideoModes`、`GetVideoMode` | 默认窗口启动也会枚举显示器。每显示器的模式查询取决于实际枚举结果。 |
| 建窗与上下文 | `DefaultWindowHints`、`WindowHint`、`CreateWindow`、`MakeContextCurrent`、`GetCurrentContext` | 前四项在窗口构造主路径。`GetCurrentContext` 出现在 GLX 版本查询路径。 |
| 窗口状态 | `GetWindowMonitor`、`GetWindowPos`、`SetWindowMonitor`、`GetFramebufferSize`、`SetWindowSizeLimits`、`SetWindowTitle`、`SetWindowIcon` | `GetWindowPos` 在未取得显示器的构造分支。`SetWindowMonitor` 依据全屏状态切换。图标更新取决于平台与资源，标题更新由上层触发。 |
| 回调注册 | `SetFramebufferSizeCallback`、`SetWindowPosCallback`、`SetWindowSizeCallback`、`SetWindowFocusCallback`、`SetCursorEnterCallback`、`SetCursorPosCallback`、`SetMouseButtonCallback`、`SetScrollCallback`、`SetDropCallback`、`SetKeyCallback`、`SetCharModsCallback` | 原版在开始渲染循环前配置这些入口。用户是否产生对应事件是另一项运行条件。 |
| 事件与呈现 | `WindowShouldClose`、`PollEvents`、`SwapBuffers`、`SwapInterval`、`WaitEventsTimeout` | 原版轮询与交换构成呈现路径。等待超时位于帧率限制分支，可用带单调时钟截止时间的消息等待。 |
| 用户输入与剪贴板 | `GetKey`、`GetKeyName`、`SetCursorPos`、`SetInputMode`、`GetClipboardString`、`SetClipboardString` | 受输入设备、按键显示、抓取光标、设置和用户操作影响。另在 `InputConstants.<clinit>` 发现反射查找字符串 `glfwRawMouseMotionSupported`。 |
| 释放 | `DestroyWindow`、`Terminate` | 关闭及清理路径，须与注册回调、窗口记录、显示器数组和上下文的生命周期配对。 |

在窗口构造的六项 hints 中，原版保留了 GLFW 默认的可见性。Win32 实现应在最终窗口就绪时按 hints 设置显示状态。全屏切换还会沿 `Window.updateFullscreen` 的 PC 22 回到 `updateDisplay`，需要保留其重入顺序。[GLFW 窗口属性与可见性](https://www.glfw.org/docs/latest/window_guide.html)

窗口过程处理 `WM_SIZE`、`WM_MOVE`、`WM_SETFOCUS/WM_KILLFOCUS`、`WM_DPICHANGED` 和 `WM_CLOSE`。用 `GetClientRect` 取得实际客户端尺寸，在 `WM_GETMINMAXINFO` 应用尺寸约束。关闭消息设置原版可查询的关闭标志。事件泵用 `PeekMessageW`、`TranslateMessage`、`DispatchMessageW` 驱动，限帧等待可用 `MsgWaitForMultipleObjectsEx`。键盘和字符输入分开派发，原始鼠标移动按注册状态处理 `WM_INPUT`。[微软客户端区域](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getclientrect) · [微软消息等待](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-msgwaitformultipleobjectsex) · [Windows 原始输入](https://learn.microsoft.com/en-us/windows/win32/inputdev/raw-input)

**原始函数表还有 117 个地址的初始化要求。** 锁定的 `GLFW$Functions.<clinit>` 对 117 个不同导出名逐一调用 `APIUtil.apiGetFunctionAddress` 并写入静态 long 字段。`glfwCreateWindow` 在 PC 313 被解析、316 写入字段 28。缺少地址时会进入 `requiredFunctionMissing`，默认配置抛出 `NullPointerException`。这 117 次查找都发生在函数表初始化时，首帧实际调用的数量须另外采集。完整交付要让原始解析器找到具有对应语义的项目汇编入口。集成进度应分别记录可解析、可执行、原版路径实测三项。保留原版检查和缺失错误。[LWJGL 3.3.3 的 GLFW 生成源码](https://github.com/LWJGL/lwjgl3/blob/3.3.3/modules/lwjgl/glfw/src/generated/java/org/lwjgl/glfw/GLFW.java)

## 接入和验收顺序

1. **地址与内存。** 为各导出建立自研汇编过程和按完整描述符查询的表，并接入原版类初始化。先落实字符串、临时栈、原生数组和回调的生命周期。窗口创建适配器接收六个托管参数，最后一个是目标地址。另一条实际路径 `JNI.invokePPPV(J[I[IJ)V` 接收 Java 数组。`GetFramebufferSize` 和 `GetWindowPos` 需要对空数组引用、缓冲区长度和结果回写遵守原包装器语义。[LWJGL 窗口调用的原始 C 签名](https://github.com/LWJGL/lwjgl3/blob/3.3.3/modules/lwjgl/core/src/generated/c/org_lwjgl_system_JNI.c#L887-L890)
2. **窗口与 OpenGL 能力。** 保留渲染线程对窗口消息和当前上下文的所有权。原版 `GL.createCapabilities` 首先查 `glGetError`、`glGetString` 和 `glGetIntegerv`，再按版本查扩展及其他函数。Windows 的 `GL$1` 会使用 WGL 查询与系统库导出。汇编后端须同样区分系统 GL 导出与当前驱动的扩展地址，并按实际像素格式和上下文维护函数地址生命周期。这里还要替换 LWJGL 的原生 GL/JNI 胶水。[微软 wglGetProcAddress](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-wglgetprocaddress) · [Khronos 像素格式扩展](https://registry.khronos.org/OpenGL/extensions/ARB/WGL_ARB_pixel_format.txt)
3. **首帧和多核。** 工作线程可并行准备资源和 CPU 数据，按原版顺序交回渲染线程上传、绘制并交换。无需账号的测试先覆盖结构体布局、句柄所有权、回调顺序、模拟消息及资源回收。真实验收需采集来自原版入口的窗口创建、上下文版本、原版绘制和首次成功交换四项，并检查进程实际加载的图形模块。图形部分全部使用项目汇编后，再将它记入全汇编交付。账号和真实客户端窗口验证仍待单独执行。

复核输入使用官方客户端 JAR 的 SHA-1 `30c73b1c5da787909b2f73340419fdf13b9def88`、官方客户端映射 `2244b6f072256667bcd9a73df124d6c58de77992` 以及 1.21.1 元数据 `9aa86ea608c3ec777dcdc09e6c5a06c85b53599e`。重扫调用点可使用现有 classfile 解析器的 `Source.code`、`stream` 和 `Source.member`，对原始调用指令解析目标 owner、方法名、描述符及 PC。此清单涵盖显式 GLFW 调用、上述反射查找和指定首帧链路。着色器、资源加载和其他子系统的完整运行覆盖仍需端到端验证。[项目 classfile 解析器](../scripts/verify-translation-ir.py)
