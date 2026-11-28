# 架构与边界

## Focus Engine 2.0

Windows 四种内置模式与自定义方案共享 Engine 的毫秒边界循环。Profile 描述计时方向、随机微休息、轮组和休息选择；Controller 决定运行时切换、恢复与自动续轮。每个会话保存创建时的完整快照。模式分布读取既有学习片段，并按档案的活动边界分组。设计细节、状态边界与新增表见[计时引擎](docs/design/focus-engine-v2.md)，界面示例见[模式界面设计](docs/design/focus-mode-ui.md)。

## 文学文案

`literature.py` 独立于 Qt，读取明确列入打包清单的 `literary_catalog.json`。私有条目、对内置条目的修改、各场景选定记录及近 16 条展示历史原子写入便携目录的 `data/literature.local.json`。沿用程序现有单实例锁。已有学习 SQLite 数据与文案互相独立，导出学习统计也不会带出摘录。

`reading_ui.py` 实现限行显示、阅读全文和文案管理。`Window` 按当前页、会话 ID、日期及偏好决定何时重新选文，计时脉冲复用已选内容。星图把文案放进已有顶部工具栏，F9 连同工具栏一起收起。完整数据契约、调度规则和导入步骤见[文学文案系统](docs/literature.md)。

## 学习宇宙 2.1

`history.activities` 从现有档案派生记录，`archive_ui` 在完整档案上分配槽位后应用筛选。`stellar` 管理稳定局部坐标、投影细节等级和有界纹理缓存。`universe.Sky` 负责父子镜头变换、视口标注和命中检测，`observatory` 管理搜索、观测面板和快捷键。此版本的视图状态在内存中保存，已有低动态偏好沿用设置文件。[设计与空间坐标](docs/design/deep-sky-2.1.md)

## 一次计时更新

Qt 定时器唤醒界面，控制器读取 Windows 单调时钟，再把自上次采样后真实经过的整数毫秒交给状态机。可见时最多每秒刷新四次，托盘和待机降低刷新频率。时长从时钟差值获得，GUI 更新稍晚时按每个时间边界切分经过的区间。

| 模块 | 职责 |
| --- | --- |
| neurofocus/engine.py | 确定性状态机、周期额度、随机间隔、时段与瞬时事件 |
| neurofocus/clock.py | Windows 清醒时长、含休眠的开机时钟和民用日期时间 |
| neurofocus/controller.py | 开始、暂停、恢复、事务缓冲、每轮方案快照 |
| neurofocus/storage.py | SQLite 事务、按本地午夜拆分、历史与 CSV |
| neurofocus/config.py | 范围及类型验证，同目录临时文件与原子替换 |
| neurofocus/sound.py | 合成渐入渐出的阶段音，在程序数据目录缓存并异步播放 |
| neurofocus/window.py、pages.py、widgets.py、visual.py | 主窗口、托盘、悬浮窗、设置、图表、配色及表盘 |
| NeuroFocus.py | 程序目录、数据目录、进程锁、入口和端到端冒烟检查 |

每一轮复制当前不可变设置。待机 → 专注 → 微休息 → 专注的循环使用每次独立抽取的随机间隔。当周期额度耗尽时优先完成本轮，同一时刻原本应出现的微休息不会触发。随后进入长休息或待机。长休息走完必定返回待机。暂停是当前阶段的标志，保留周期额度和阶段余量。

## 系统休眠与日历时间

QueryUnbiasedInterruptTime 给出排除 Windows 睡眠、休眠的累计时间。程序处理挂起广播，在收到挂起消息时结算并暂停；若错过广播，则比较两个系统时钟的偏差。检测到长于一秒的睡眠差时舍弃最后未能准确归属的采样间隙，并暂停到用户继续。手动调整系统日期只改变时段的日历归属。跨多个阶段的迟到更新会完整记账，只提示最新阶段。[Microsoft 时钟文档](https://learn.microsoft.com/en-us/windows/win32/api/realtimeapiset/nf-realtimeapiset-queryunbiasedinterrupttime)

## 持久化与异常退出

`sessions` 保存起止采样时间及状态。`days` 按“周期 ID + 本地日期”保存三类互斥时长、微休息触发次数和周期完成次数。周期额度单独跟踪。即使把微休息计入额度，也只把这段时长写进微休息统计。历史记录按周期聚合，周从周一开始，月使用自然月。

桌面端 SQLite 使用 WAL 与 FULL 同步。阶段切换、暂停、停止及正常退出会提交，活动期间通常每 5 秒提交一次。事务成功后才清空待写区间。写入中断则回滚，下一次提交复用缓冲。系统强杀可能损失最近一次成功检查点以后的时间。启动时，在同一数据目录取得进程锁后，将上次未结束的记录标为中断。

## Windows 标签与分类统计

`tags.py` 在单个 SQLite 写事务内从旧版 schema 0 迁移到版本 1。`tags` 保存稳定整数 ID、名称、颜色、归档状态和顺序。ID 0 对应内置「未分类」。`tag_choice` 记录下次启动选中的标签。`focus_spans` 以周期、日期、连续学习段编号和标签 ID 标识一个片段。迁移将原 `days.focus` 中的正时长按周期和日期导入未分类，旧记录的起止时间保留空值。数据库版本号与回填在同一事务中提交。

切换标签先由 Controller 用原标签结清待写时长，成功后才切换 ID 并开启新段。暂停后继续、微休息后恢复都会开启新段。检查点只把 focus 时长按本地午夜切分到片段表，与原有周期状态及每日汇总一并提交。持续学习时反复更新同一个片段的结束时间及累计毫秒数，避免每个界面刷新都产生一条记录。

`tag_ui.py` 提供标签管理和分页历史，`distribution.py` 用 Qt 绘制环图、条形和堆叠柱。分布、趋势与详情均按已提交的有效学习毫秒数计算，旧版每日汇总继续供原统计页使用。CSV 以周期、日期、标签聚合；JSON 的 `records` 使用相同口径，`focus_spans` 保留段明细，`tags` 包含归档标签。`started`、`ended` 为 Unix 毫秒，`ms` 为实际学习时长。

## Windows 学习日历

`calendar_data.py` 批量读取所选日期和标签的学习片段，按本地日期累加有效毫秒。第二个查询按关联周期汇总休息和完成数，多选同一周期的两个标签仍只计算该周期一次。旧版日汇总保留空的起止时间。

`calendar_ui.py` 在已有统计页中使用单个 Qt 画布显示可见周列。悬停直接读取范围汇总，点击后分页读取当天的片段。范围、筛选、本地日期或数据库写入发生变化时，刷新范围缓存。三个色阶阈值沿用现有配置文件。数据库结构保持版本 1。[设计说明](docs/design/study-calendar-design.md)

## Windows 学习档案

Controller 将真实阶段边界交给 Store，与同一检查点的有效学习毫秒一起提交；会话开始时保存计时参数快照。history 模块把原始片段投影为本地日期内连续同科目的活动。日志外键指向组首片段，星图使用相同键；同一周期跨午夜仍可从两天查看周期过程。archive_widgets 绘制时间轴、保存草稿，archive_ui 负责筛选与跨页定位。universe 负责原生 Qt 场景的绘制、相机和语义层级。[数据模型](docs/design/learning-data-model.md) · [页面联动](docs/design/learning-history-integration.md)

## Android 实现

本地 HTML/CSS 提供移动端界面，Java Activity 只向随包资源提供有限的设置、计时与导出命令。Manifest 未声明网络权限。前台服务独立于 Activity，使用 elapsedRealtime 和同样的阶段边界规则。手机锁屏仍应计入学习，活动阶段使用有超时的部分唤醒锁，暂停和结束释放。Android 内存回收或强行停止后恢复已提交记录，下一次手动开启新一轮。厂商对后台服务的具体限制需真机检查。[Android 时钟文档](https://developer.android.com/reference/android/os/SystemClock) · [Android 前台服务](https://developer.android.com/develop/background-work/services/fgs/service-types)

## Learning Harness 接口位置

`Engine.start / tick / pause / resume / stop` 可直接由 Python 调用。不可变的 `Entry(kind, at, duration)` 通过返回值提供阶段时长与边界事件，可在未来接入时复用。CSV 保留周期 ID、日历日期及分类时长。本次实现不启动额外服务，不访问 Learning Harness 目录。
