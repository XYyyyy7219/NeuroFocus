# 时间轴研究

阅读 ActivityWatch/aw-webui 的 Vue/TypeScript 文件 src/visualizations/Calendar.vue，提交 db9da795f8d035401649eab900bd03808483cb49，MPL-2.0。调研时仓库可访问、未归档，该提交日期为 2026-11-26。[源码](https://github.com/ActivityWatch/aw-webui/blob/db9da795f8d035401649eab900bd03808483cb49/src/visualizations/Calendar.vue)

calendarOptions 在 timeGridDay 与 timeGridWeek 间共用事件流，calendarTimeBounds 可将时间轴缩到有活动的时段。events 将时间戳和持续秒数转换成区间，原始 bucket 路径排除十秒以内的事件，分类路径则保留正时长。NeuroFocus 保留短学习片段的统计精度，用选择列表辅助点击小色块，展开时才展示短休息。日历与档案使用现有 focus_spans；不引入 FullCalendar 或上游源码。
