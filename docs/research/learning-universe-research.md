# 学习星图渲染研究

选择同样基于 Qt 的 pyqtgraph，仓库未归档，源码提交 3fbfd734ce866b1084b472ed14989929ff8a96a6，日期 2026-11-06。阅读 graphicsItems/ScatterPlotItem.py 以及根 LICENSE.txt（MIT）。SymbolAtlas 用符号、尺寸、画笔和画刷作键，把已绘符号排入一张像素图；_maskAt 把点或矩形展开成命中区域，结合屏幕尺寸判定命中；pointsAt 返回相应对象。[源码](https://github.com/pyqtgraph/pyqtgraph/blob/3fbfd734ce866b1084b472ed14989929ff8a96a6/pyqtgraph/graphicsItems/ScatterPlotItem.py)

该实现适合相似符号的大批量显示。我们的首屏主要展示学科，进入主题才需逐个活动的鼠标交互。优先减少同屏对象，并用 Qt 自带场景索引、裁剪和命中，无须安装 NumPy、WebEngine 或 OpenGL 组件。恒星高光固定在左上方，外环表示日志状态。对比力学网站的层级布局见同目录 Physics Atlas 分析。三个参考项目均独立阅读，本项目没有复制第三方实现。
