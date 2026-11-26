# 架构与边界

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

## 手机端

本地 HTML/CSS 提供移动端界面，Java Activity 只向随包资源提供有限的设置、计时与导出命令。Manifest 未声明网络权限。前台服务独立于 Activity，使用 elapsedRealtime 和同样的阶段边界规则。手机锁屏仍应计入学习，活动阶段使用有超时的部分唤醒锁，暂停和结束释放。Android 内存回收或强行停止后恢复已提交记录，下一次手动开启新一轮。厂商对后台服务的具体限制需真机检查。[Android 时钟文档](https://developer.android.com/reference/android/os/SystemClock) · [Android 前台服务](https://developer.android.com/develop/background-work/services/fgs/service-types)

## Learning Harness 接口位置

`Engine.start / tick / pause / resume / stop` 可直接由 Python 调用。不可变的 `Entry(kind, at, duration)` 通过返回值提供阶段时长与边界事件，可在未来接入时复用。CSV 保留周期 ID、日历日期及分类时长。本次实现不启动额外服务，不访问 Learning Harness 目录。
