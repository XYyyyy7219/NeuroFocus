# 力学导航的实际实现

2026-11-28 检查本地 Astro 旧快照和公开 Git 仓库。公开 physics-atlas 的提交 ccf0a6399e57e798a6a956b6be71cacfbec2ce00 与 Mechanics 的 c3ecec85f7ad142d6ab44ca31291042ad44f40d1 仅列 README。本地旧目录有 KnowledgeMap.astro，但与线上力学入口的资源名称不同。本次以线上实际发布的可执行脚本和 CSS 为依据；没有取得对应版本的未压缩 Astro 组件或测量站点帧率。[力学入口](https://physics-atlas.netlify.app/mechanics/)

LectureOutlineGraph 的部署文件 SHA-256 为 36989cfcf524727c9d0ac31db0ca3a8a0178c726188b71126ed17287fdeaa7f4。函数 O 先计算章节点的环形目标位置，再把所属小节排进扇区。P 由 parent ID 找边并初始化物理模拟。k 把节点定位交给 DOM，Canvas 单独画边。A 合并同一动画帧内的重绘；F 根据视口更新布局，设备像素比上限为 2。N 搜索后保留命中分支及祖先，j 按边界框居中，I 以指针为中心缩放。拖动阈值为 5 像素，缩小视图隐藏密集的小节文字，支持减少动态效果。[部署脚本](https://physics-atlas.netlify.app/_astro/LectureOutlineGraph.astro_astro_type_script_index_0_lang.CfaMbUL1.js)

LectureCover 样式里的图节点用实色圆点、背景色描边和双层选中环，标签位于单独元素。封面轨道与导航节点采用不同样式。NeuroFocus 借鉴层次、选择边框和缩放聚焦，自行绘制偏心球体高光、光晕与背景纵深。用户活动会持续增加，每次重跑力模拟会改变熟悉的位置，故使用确定性排布。没有复制脚本、样式或资产，也没有更改 Physics Atlas。[样式](https://physics-atlas.netlify.app/_astro/LectureCover.C-5LqoLD.css)
