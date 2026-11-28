# Focus Engine 2.0 验证

2026-11-28 在 Windows 11 x64 使用 Python 3.14.5、PySide6 Essentials 6.12.0、PyInstaller 6.22.3。正式打包脚本执行 unittest 全量测试，86 项通过，耗时 51.035 秒。下表说明证据范围。

| 验证 | 方法和结果 |
| --- | --- |
| 原有 70 项 | 计时精度、随机间隔、周期边界、存储故障、异常退出、标签与日历、档案与星图、文学文案等，在同一次构建中通过 |
| 12 项专注模式 / 存储测试 | 可注入时钟逐毫秒推进。番茄前 3 次短休、第 4 次长休，自定义 2 轮，提前结束保留有效时间；延迟抵达手动休息提示时准确停止；排队切换和自动下一轮的边界；Flowtime 超过一小时、暂停、提醒、建议档位、自主休息；自定义方案持久化及删除后查询；跨午夜、迁移备份、事务重试、唤醒 |
| 4 项新增 Qt 测试 | 实际控件执行新增、编辑、删除、动态参数切换，计时器与按钮一致，短休息及通知映射，Flowtime 和统计日期筛选，日志、星图及时间轴事件关联 |
| Windows 运行截图 | 原生 Qt Windows 平台、1.5 倍设备像素比，隔离临时库生成示例。五种模式共 10 张，覆盖浅色、深色、990 × 744 与 760 × 620 的主窗口。复核后为布尔设置增加文字，统一中文保存和取消按钮 |
| 冻结程序 | 启动发布目录的 NeuroFocus.exe --smoke-test，退出码 0。smoke.json 的 platform 为 windows，frozen、success、focus_engine、calendar、archive、tag_distribution、literature、immersive_sky、deep_sky、tray_available 均为 true |

## 复现

从仓库根目录在已安装构建依赖的 Windows Python 环境中运行：

```powershell
python -m unittest discover -s tests -v
python tools/focus_mode_acceptance.py --output build/focus-preview
.\build.ps1
Start-Process .\dist\NeuroFocus\NeuroFocus.exe -ArgumentList '--smoke-test','build/qa' -Wait
```

[截图索引](../design/focus-mode-ui.md) · [引擎与数据库口径](../design/focus-engine-v2.md)

长期计时与休眠边界通过模拟时钟加速验证。本次未让物理电脑实际休眠数小时，也未逐一人工试听所有音色或在多种显示器硬件上测试。运行截图取自原生 Qt 应用；发布 EXE 另行启动并验证。
