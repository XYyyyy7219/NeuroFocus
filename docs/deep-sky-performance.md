# Windows 深空观测实测

Windows 11 x64（构建 26300），Core i7-13700H，Intel Iris Xe 与 RTX 4060 Laptop，Python 3.14.5，PySide6 Essentials 6.12.0。窗口 1120 × 735 逻辑像素，实际截图 1680 × 1103。运行时采用 Qt 原生 Windows 平台和栅格视口。

每个规模使用新进程和临时 SQLite，填入跨年份、时长不同的活动、多个学科与主题、写过和未写日志的记录。五个科目中有一个改名并归档。各规模的进入时间是一次打开学习档案、切到星图和处理界面事件的时间。视口抓取是在低动态模式下连续九次重绘的中位数。内存是包含完整应用和 Qt 的当前工作集，使用 MiB。单次计时不代表所有机器或冷启动速度。

| 实际活动数 | 进入总览 | 总览抓图中位数 | 工作集 | 截图 |
| ---: | ---: | ---: | ---: | --- |
| 0 | 33.5 ms | 2.79 ms | 155.5 MiB | [空档案](screenshots/deep-sky/overview-0.png) |
| 1 | 39.1 ms | 3.13 ms | 155.0 MiB | [单星](screenshots/deep-sky/overview-1.png) |
| 10 | 42.5 ms | 3.05 ms | 157.8 MiB | [稀疏星群](screenshots/deep-sky/overview-10.png) |
| 100 | 51.8 ms | 4.84 ms | 156.7 MiB | [百次活动](screenshots/deep-sky/overview-100.png) |
| 1,000 | 61.6 ms | 7.64 ms | 160.4 MiB | [千次活动](screenshots/deep-sky/overview-1000.png) |
| 10,000 | 131.8 ms | 8.71 ms | 172.5 MiB | [万次活动](screenshots/deep-sky/overview-10000.png) |

## 交互及计时

在一万条记录中打开最大的主题，共 1,666 个可选活动。连续平移 2.403 秒，视口收到 33.3 次绘制事件/秒，进程 CPU 用时相当于 100.8% 的一个逻辑核，工作集 196.0 MiB。该读数包含事件循环与测试驱动，屏幕合成后的呈现帧率未测量。同期启动并提前结束真实计时器，数据库写入 2,399 毫秒，包围两次操作的单调时钟窗口为 2,402 毫秒，差 3 毫秒。长周期和休眠的边界行为另由模拟时钟回归覆盖。

静止 1.3 秒测得进程占用相当于一个逻辑核的 4.79%；最小化 1.1 秒测得 CPU 时间增量为零，视口重绘 0 次。短时采样受系统调度与 CPU 计数粒度影响。Windows GPU Engine 取得 511 个有效实例，但没有归属本测试进程的实例，无法报告应用独占 GPU 百分比。采样同时记录的全系统最忙实例在静止和平移时分别为 10.244% 与 10.160%，其中包含其他应用。未进行长时间整机耗电测试。

100 条资料组验证了普通模式的镜头过渡、搜索定位、标签筛选和日期回放。图像来自实际程序窗口。首轮截图暴露了密集概览中预览尺度过小、近景文字覆盖星面的问题。扩大嵌套坐标比例，并按投影半径退让文字后重新运行了六个规模。

[学科星系](screenshots/deep-sky/galaxy.png) · [主题星团](screenshots/deep-sky/cluster.png) · [远距 LOD 0](screenshots/deep-sky/lod-0.png) · [中距 LOD 1](screenshots/deep-sky/lod-1.png) · [近距 LOD 2](screenshots/deep-sky/lod-2.png) · [恒星观测 LOD 3](screenshots/deep-sky/observation.png)

在已安装项目依赖的 Windows 环境运行以下命令复测。输出目录包含截图和原始数字。测试只创建临时数据库。[本次原始读数](screenshots/deep-sky/measurements.json)

```powershell
$env:QT_QPA_PLATFORM = 'windows'
python tools/deep_sky_acceptance.py --output $env:TEMP\neurofocus-sky-qa
```
