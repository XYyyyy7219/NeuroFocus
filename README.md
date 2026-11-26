# NeuroFocus

中文离线专注计时器。默认一轮为 90 分钟，学习期间每隔随机 3～5 分钟休息 10 秒。专注周期结束后转入 20 分钟长休息，下一轮由使用者开始。程序不会预告下次微休息的时间。

## 平台和功能

Windows 11 x64 版支持托盘、悬浮小窗、置顶、可试听提示音和通知。Android 8.0 及以上版本提供适合触屏的界面和前台计时。两端各自在本地保存设置和学习记录，可按日、周、月查看实际专注时长，并导出 CSV。

| 文件或目录 | 内容 |
| --- | --- |
| [使用说明](使用说明.md) | 开始学习、收起窗口、统计、备份与导出 |
| [项目架构](ARCHITECTURE.md) | 计时、日历归属、本地存储与平台差异 |
| [测试结果](TEST-RESULTS.md) | 测试范围、实际结果和待验证项 |

## 从源码运行 Windows 版

在 Windows x64 安装 Python 3.14，从仓库根目录运行下列 PowerShell 命令。测试使用 Python 3.14.5。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe NeuroFocus.py
```

仅从源码运行时可使用 `requirements.txt`。源码启动的设置和数据库保存在入口文件旁边的 `data` 目录。

## 自动化测试与打包

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\build.ps1 -Python .\.venv\Scripts\python.exe
& .\dist\NeuroFocus\NeuroFocus.exe
```

脚本先执行全部单元测试，成功后生成自包含的 Windows 程序目录。运行时将 EXE 和 `_internal` 保存在同一个可写目录。主程序还提供 `--smoke-test <目录>`，使用独立临时数据库验证原生界面并写出截图、CSV 和 smoke.json。测试会短暂打开窗口后自行退出。

## 安卓构建

手机端使用本地 WebView 显示界面，Java 前台服务负责计时与声音。构建需要 JDK 21、Android SDK Platform 35、Build Tools 35.0.0 和 Python 3。源码中的 PowerShell 脚本直接调用官方 SDK 工具，无需 Gradle 或在线服务。下面示例中的 SDK 路径适用于标准 Android SDK 目录结构。

```powershell
.\android\build.ps1 -PlatformJar 'D:\Android\Sdk\platforms\android-35\android.jar' -BuildTools 'D:\Android\Sdk\build-tools\35.0.0' -Jdk 'C:\Program Files\Java\jdk-21'
```

脚本默认生成 `android/NeuroFocus-Android.apk`。用于测试安装的签名密钥保存在构建目录的 `local-test.p12`。保留同一签名密钥可覆盖安装并保留数据。

## 技术选型

Windows 界面使用 PySide6 Essentials。Qt Widgets 提供高分屏绘制、原生窗口事件、系统托盘和可访问名称，自绘表盘和其他控件可以使用一致的字体与颜色。目录式打包方便在便携目录中加载运行库。SQLite、CSV、时钟和声音合成均使用 Python 标准库。

Qt/PySide6 版本为 6.12.0，PyInstaller 为 6.22.3。上游组件说明见 [Qt for Python](https://doc.qt.io/qtforpython-6/)、[PySide 源代码](https://code.qt.io/cgit/pyside/pyside-setup.git/) 与 [PyInstaller](https://pyinstaller.org/)。
