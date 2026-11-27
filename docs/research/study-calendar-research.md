# 学习日历源码调研

2026-11-27。通过 GitHub 搜索发现 react-activity-calendar，再对候选仓库查询仓库元数据、默认分支最近提交和文件树。下表日期是所查提交日期，仅作为维护活动线索。有效仓库查询时均未归档。对五个实现下载了指定提交的源码与许可证并阅读，没有运行上游应用。

| 项目与锁定版本 | 最近提交 | 技术、许可与取舍 |
|---|---|---|
| [react-calendar-heatmap](https://github.com/kevinsqi/react-calendar-heatmap/tree/a64475c0afb326799cc9fcb7d0ac2220f0ab125f) | 2025-02-23 | JavaScript / React，MIT。较小的单组件适合检查方格和事件映射。 |
| [Cal-Heatmap](https://github.com/wa0x6e/cal-heatmap/tree/279e4eea42e962daf710ec721871cd5ffca97907) | 2024-03-03 | TypeScript，MIT，许可证文件为 LICENCE。域模板灵活，网页比例尺依赖对桌面计时器偏重。另一个候选地址 cal-heatmap/cal-heatmap 在官方 API 返回 404。 |
| [React Activity Calendar](https://github.com/grubersjoe/react-activity-calendar/tree/4931c8f7d85c98de10358f6f5a841c50bd4ff228) | 2026-10-05 | TypeScript / React，MIT。日期、标签定位、主题均有单独模块和测试，适合作为架构参考。 |
| [ActivityWatch](https://github.com/ActivityWatch/activitywatch/tree/fc1ac55e0be7a00fae3d0c93ca76ffd3434b1837) 与 [aw-webui](https://github.com/ActivityWatch/aw-webui/tree/db9da795f8d035401649eab900bd03808483cb49) | 2026-11-22、11-26 | 总仓主要语言 Python，界面主要语言 TypeScript，均标为 MPL-2.0。实际分析的是 Web UI 的 Vue 日历组件。 |
| [Super Productivity](https://github.com/super-productivity/super-productivity/tree/c266994548f6d60a34f095f0569a4d53672c591c) | 2026-11-27 | TypeScript / Angular，MIT。桌面生产力应用中已有工作日志与热图，适合比较学习时长的统计含义。 |

## 源码观察与工程判断

- **日期预处理。** React Activity Calendar 的 `src/lib/calendar.ts` 先在 `fillHoles` 里将事件映射到日期并补齐观测区间，再由 `groupByWeeks` 在第一周左侧补占位。`src/lib/calendar.test.ts` 与数据处理独立于绘制。输入为空时依靠生成空数据的路径。NeuroFocus 直接按显示范围计算自然日位置，空历史也能翻月或查看未来日期。[日期实现](https://github.com/grubersjoe/react-activity-calendar/blob/4931c8f7d85c98de10358f6f5a841c50bd4ff228/src/lib/calendar.ts)
- **月份与主题。** 同项目 `src/lib/label.ts:getMonthLabels` 根据每周第一个有效日期找月份切换，并用最少三周的启发式隐藏首尾标签。非常短的自定义范围可能缺少月份。这里用月初所在列和实际绘制宽度判断间距，始终显示起始日期范围。`src/lib/theme.ts:resolveColorScale` 区分整套颜色与插值配色。桌面端用两套固定五阶色，避免主题切换改变阈值。[月份](https://github.com/grubersjoe/react-activity-calendar/blob/4931c8f7d85c98de10358f6f5a841c50bd4ff228/src/lib/label.ts) · [颜色](https://github.com/grubersjoe/react-activity-calendar/blob/4931c8f7d85c98de10358f6f5a841c50bd4ff228/src/lib/theme.ts)
- **按格交互。** react-calendar-heatmap 的 `src/index.js` 预先生成索引到日期值、CSS 类与 tooltip 属性的映射；`renderWeek`、方格的 mouse-over/click 处理复用对应值。`src/helpers.js:shiftDate` 按日历日期加天。桌面端采用画布命中测试与批量查询结果，实现悬停零数据库读取。[组件源码](https://github.com/kevinsqi/react-calendar-heatmap/blob/a64475c0afb326799cc9fcb7d0ac2220f0ab125f/src/index.js)
- **排列与色标分离。** Cal-Heatmap 的 `src/templates/day.ts` 由域类型决定行列，年域遍历日期并在周编号变化时前进一列。`src/helpers/ScaleHelper.ts:normalizedScale` 将数值交给 Observable Plot 映射颜色或透明度。这里只有周一开列一种布局，用日期差除以七，不依赖跨年周编号，三个有序整数即可完成分级。[日期模板](https://github.com/wa0x6e/cal-heatmap/blob/279e4eea42e962daf710ec721871cd5ffca97907/src/templates/day.ts)
- **工作日志与筛选。** Super Productivity 的 `activity-heatmap.component.ts` 将每日任务数、时长映射到 dayMap，按当前数据最大值归一化，再以时间 80%、任务数 20% 分级。`_buildWeeksGrid` 按配置回退到周首，区间外填空。相对尺度适合观察任务活跃度；在这里筛选标签后重新缩放会妨碍科目比较。学科使用稳定 ID，不另建一套任务分类。[工作日志热图](https://github.com/super-productivity/super-productivity/blob/c266994548f6d60a34f095f0569a4d53672c591c/src/app/features/metric/activity-heatmap/activity-heatmap.component.ts)
- **从日期下钻。** aw-webui 的 `src/visualizations/Calendar.vue` 把 bucket 事件转换成 FullCalendar 事件，并过滤时长不超过 10 秒的条目；`src/util/calendar.ts` 服务于时间视图。事件适配层值得借鉴，但学习计时已有排除暂停的精确片段，连 1 毫秒也应参与汇总。只在选择一天时读取明细，旧版日合计保留缺失起止时间。[事件适配](https://github.com/ActivityWatch/aw-webui/blob/db9da795f8d035401649eab900bd03808483cb49/src/visualizations/Calendar.vue)

## 许可与复用记录

以上使用固定提交核查 MIT 文本和 aw-webui 的 MPL-2.0 文本。直接复制的上游代码、样式、素材和新增运行依赖均为零。日期运算、SQLite 查询、PySide6 交互均为本项目实现；仓库原有标签和环图组件内部复用。本次无须将上游许可证引入项目或为 NeuroFocus 指定新的分发许可。若将来复制 MIT 代码须保留版权与许可通知；采用 MPL 文件须单独核对文件级义务。
