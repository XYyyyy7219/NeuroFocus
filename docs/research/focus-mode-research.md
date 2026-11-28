# 专注模式源码调研

2026-11-28 核对默认分支快照。六个仓库均可读取，查询时均未归档。下表的日期是 GitHub 记录的最近一次推送日期。选读依据是能否解释 NeuroFocus 的一个具体计时问题。

| 项目与版本 | 最近推送 | 许可证 | 筛选与阅读范围 |
| --- | --- | --- | --- |
| [Goodtime](https://github.com/adrcotfas/Goodtime/tree/4907ef09a9b3b3d49fd59d90ba94bbf4082039c2) | 2026-11-27 | GPL-3.0，所读文件头允许更高版本 | 深读 Kotlin 共享计时引擎、方案和恢复机制 |
| [Flowtime](https://github.com/Diego-Ivan/Flowtime/tree/9022a39997d9eb8c7421af824e8d885a2bc2e0a1) | 2025-04-28 | GPL-3.0，计时源码标明 or later | 深读 Vala / GTK 桌面程序的自由计时和按需休息 |
| [Super Productivity](https://github.com/super-productivity/super-productivity/tree/2d1937835dff74e724e6d454425002a5969b51e9) | 2026-11-27 | MIT | 核对元数据和源码目录。综合任务管理器涉及较多任务状态 |
| [Flowkeeper](https://github.com/flowkeeper-org/fk-desktop/tree/f6d2349f7f6352fde75df5bb2fe620787fdd63c2) | 2026-10-07 | GPL-3.0 | 核对元数据和源码目录。桌面番茄流程与 Goodtime 研究方向重叠 |
| [Stretchly](https://github.com/hovancik/stretchly/tree/b58211defee3f1e54b34ed97ef83452df5a90195) | 2026-11-26 | BSD-2-Clause | 核对元数据和源码目录。侧重定时休息提醒 |
| [ActivityWatch](https://github.com/ActivityWatch/activitywatch/tree/fc1ac55e0be7a00fae3d0c93ca76ffd3434b1837) | 2026-11-22 | MPL-2.0 | 核对元数据和源码目录。主动开始的学习活动已有本地事实数据，无需后台观察器 |

## Goodtime 的计时与恢复

`TimerManager.pause` 对倒计时记录距离终点的时间，对正向计时使用开始后的有效时间并扣除暂停。`next` 和 `nextInternal` 结合刚结束的阶段与组内进度选择下一阶段。`finish` 单独判断是否可以自动继续，回调到得太晚会放弃连开下一轮。在该快照中窗口是 30 分钟。NeuroFocus 复用原有毫秒切段器计算两类时间，仅允许在休息终点后 2 秒内自动续轮，涵盖常规界面刷新误差。更晚回到电脑时，可主动开始。[TimerManager.kt](https://github.com/adrcotfas/Goodtime/blob/4907ef09a9b3b3d49fd59d90ba94bbf4082039c2/shared/src/commonMain/kotlin/com/apps/adrcotfas/goodtime/bl/TimerManager.kt)

`TimerProfile` 把计时方向、阶段参数组织为数据；多个界面可以使用同一份定义。NeuroFocus 在会话开始时固定完整方案，并把快照和周期轮次写进 SQLite。正在学习时调整参数，不会改变档案里对这轮学习的解释。[TimerProfile.kt](https://github.com/adrcotfas/Goodtime/blob/4907ef09a9b3b3d49fd59d90ba94bbf4082039c2/shared/src/commonMain/kotlin/com/apps/adrcotfas/goodtime/data/model/TimerProfile.kt)

`restoreTimerState` 比较开机以来经过的时间与已存的起始值，识别重启，再利用保存的时间信息重建计时。NeuroFocus 的档案要求能解释每段已学时长。这里采用保守恢复：异常退出保留已提交进度，唤醒后等待用户继续，关机空白不补入学习记录。[TimerStateRestoration.kt](https://github.com/adrcotfas/Goodtime/blob/4907ef09a9b3b3d49fd59d90ba94bbf4082039c2/shared/src/commonMain/kotlin/com/apps/adrcotfas/goodtime/bl/TimerStateRestoration.kt)

## Flowtime 的自主休息

`Timer.next_mode` 先保存工作阶段，再以有效工作秒数乘上用户设置的百分比，得到初始休息秒数。`save_to_statistics` 分别处理上数的工作时间和倒数的休息时间。这个先结算再转换的顺序能保住用户提前休息时的进度。其 `timeout` 计算 UTC 时刻差并转换为整数秒；直接移用这一实现会把系统时间校正引入持续时间。NeuroFocus 的时长来自 Windows 清醒单调时钟，保留毫秒精度。[Timer.vala](https://github.com/Diego-Ivan/Flowtime/blob/9022a39997d9eb8c7421af824e8d885a2bc2e0a1/src/Services/Timer.vala)

`TimerPage` 绑定格式化时间，并在阶段及运行状态改变时更新标签和操作。自由专注最重要的操作是由使用者决定休息点。设计因此把“进入休息”放在暂停旁边，建议值可即时改写。四档建议更便于理解和编辑，也避免用精确到秒的建议造成虚假的精确感。[TimerPage.vala](https://github.com/Diego-Ivan/Flowtime/blob/9022a39997d9eb8c7421af824e8d885a2bc2e0a1/src/Widgets/TimerPage.vala)

## 项目内的取舍

原引擎已经有独立单调时钟、随机抽样、周期与微休息同刻到期的优先级、跨午夜拆分、五秒检查点及按会话归档。两个需要改变的假设是所有专注都有固定终点，以及轮后只会进入长休息。扩展现有 Engine、Profile 和 Controller 就能消除这两个假设。Qt、SQLite、声音合成及可执行文件的依赖保持原来规模。上游仅作源码研究，本次交付的代码、图标和截图均未复制上述项目的实现或资源。
