# 学习宇宙 1.4 · 源码与视觉设计记录

## 原型诊断

1.3 的 Body.paint 把最亮区域放在球心左上方，且球面边缘明显变暗，读起来像受光物体。学科沿用一个更大的球，无法从形态看出一条活动与几十条活动的差别。日期、表单、列表和详情按钮同时挤占画布。改版沿用原有活动 ID、Qt 场景索引和档案的数据投影，分开设计发光点源、聚合云气、远景和操作层。

## 实际研究的代码

- **Physics Atlas。** 本次找到本地原始组件 `src/components/LectureOutlineGraph.astro`、`src/scripts/lecture-outline-graph.ts` 与 `src/styles/lecture-book.css`。主工作副本 TypeScript 文件 SHA-256 为 `b852a57c9d02d988ea07e4f1f4f25fa9f415938afe02b4bac22777b2fb403bce`。Astro 根据 group/section 的 ID 与父键生成可访问的按钮和链接。arrange 将章节排在圆周、小节放入扇区，fit 按对象范围适配视口，zoom 按指针换算新偏移。invalidate 合并绘制请求，draw 在密集缩放下隐藏低层标签。CSS 区分节点层级与选择轮廓。对照此前取得的已发布脚本，借鉴父键导航、镜头锚点和按需显示标签。已检查两份本地组件，均为只读访问；没有推断本地源码与部署字节完全一致。[线上力学导航](https://physics-atlas.netlify.app/mechanics/)
- **Stellarium。** 读取 `StelSkyDrawer.cpp` 的 drawPointSource。投影后根据半径和亮度分别计算点源与大光晕，光晕在超过屏幕尺度阈值后加法混合，闪烁受气氛等条件控制，点源数据批量入缓冲。学习活动没有物理星等，采用固定色相、受限核宽，关闭持续闪烁。仓库标注 GPL-2.0。[锁定源码](https://github.com/Stellarium/stellarium/blob/4fb7ca7096edc1a5386d61fd3a3fb0af1785efb0/src/core/StelSkyDrawer.cpp)
- **Celestia。** 点源 fragment shader 按像素到中心的距离计算截断锥形衰减，glow pass 独立计算眼睛点扩散函数的长尾，并裁掉可见半径之外的片元。galaxyrenderer.cpp 将像素角尺度与到星系的距离结合估算最小可见细节。本项目用居中的白热核心和同心色晕近似视觉效果，未模拟辐射度。着色器文件头为 GPL-2.0-or-later。[点源](https://github.com/CelestiaProject/Celestia/blob/451d4afd0834aa54600c9892c6775c79f7338a0c/shaders/psfstarpoint_frag.glsl) · [光晕](https://github.com/CelestiaProject/Celestia/blob/451d4afd0834aa54600c9892c6775c79f7338a0c/shaders/psfstarglow_frag.glsl)
- **Three.js。** 实际读取 WebGPU TSL 星系示例、WebGL point sprites、selective bloom 和 UnrealBloomPass。星系示例将分支角与半径、时间关联，在径向颜色间插值，并用点精灵局部坐标获得亮核。UnrealBloomPass 对五层分辨率目标应用可分离高斯模糊后组合，选择性辉光示例最后混合基础画面与辉光。Qt 桌面静态记录使用缓存发光纹理即可避免全屏后处理。MIT。[星系示例](https://github.com/mrdoob/three.js/blob/ec673e424405242249dc4b3e72a9a1eb78a1036b/examples/webgpu_tsl_galaxy.html) · [后处理](https://github.com/mrdoob/three.js/blob/ec673e424405242249dc4b3e72a9a1eb78a1036b/examples/jsm/postprocessing/UnrealBloomPass.js)
- **Galaxy Renderer TypeScript。** Galaxy、GalaxyRenderer 与 VertexBufferStars 将椭圆参数、角偏移、扰动及粒子类型分开。顶点程序按类型计算位置、尺寸、颜色；片元程序分别控制恒星和尘埃透明度。学习记录只生成真实数据点，旋臂云气独立烘焙。GitHub 元数据未给出许可证，本次仅分析，无代码或资产复用。[粒子着色器](https://github.com/beltoforion/Galaxy-Renderer-Typescript/blob/cb08f6be4d8b6d964c7394713632b57033909e4a/src/VertexBufferStars.ts)
- **pyqtgraph。** 复核 ScatterPlotItem 的 SymbolAtlas、pointsAt 和 _maskAt。缓存符号和将命中区域与光晕大小分开，对于高 DPI 的细小目标都有价值。本版按颜色缓存恒星纹理，场景保留独立拾取范围。MIT。[Qt 渲染实现](https://github.com/pyqtgraph/pyqtgraph/blob/3fbfd734ce866b1084b472ed14989929ff8a96a6/pyqtgraph/graphicsItems/ScatterPlotItem.py)

本次没有复制第三方源码、贴图或字体。两张背景资产均由仓库内的 Python 工具根据固定种子生成，运行时仅加载压缩图像。

## 三种可运行设计

同样的 112 次模拟活动、四个标签。原型可拖拽、缩放、点选，数字键 1–3 切换设计。`python tools/sky_prototypes.py` 启动；加 `--capture <目录>` 重现截图。Windows 原生后端九次抓图中位数如下。

|方案|空间组织与视觉含义|交互观察|重绘|
|---|---|---|---:|
|[旋臂深空](../screenshots/sky-design/astronomy.png)|学科成为倾斜的旋臂星群，实际活动是独立亮点，可见科目和疏密|能从整体进入局部，需要文字说明聚合抽样|8.40 ms|
|[章节星座](../screenshots/sky-design/branches.png)|树形分支明确，疏朗、图解感强|依赖人为分支，线条易被理解为知识关系|2.73 ms|
|[历时轨道](../screenshots/sky-design/chronograph.png)|日期映射到相位，记录形成轨迹|同一日期范围内活动集中会重叠，更适合专门的年历|2.78 ms|

最终以旋臂为主，使用第二种方案的层级聚焦。日期演化沿用独立时间轴以保留精确的自然日边界。低负载模式减少背景尘点、关闭视差和相机插值。天文色彩表现适度扩张到聚合层，叶节点仍使用活动与日志的真实属性。

## 渲染与交互取舍

- 原有 Qt Graphics View 可索引、裁剪和拾取，性能验证支持继续使用。选择原生缓存纹理和绘制时合成，避免为一个视图添加浏览器、GPU 着色器编译和新安装依赖。
- 固定种子多尺度噪声生成尘埃云、暗带和有色星云，纹理在打包前烘焙。背景按窗口大小缓存，镜头变化只平移有限距离；不参与拾取、活动统计或日期回放。
- 聚合层的双旋臂成员使用完整标签内的稳定槽位。单条活动显示在核区；每组超过 160 条时从不同时间段抽取实际活动进行概览，标注抽样以及真实总数。进入主题后可选择其中每一条记录。相邻筛选会改变样本集合，保留下来的活动位置稳定。
- 选择恒星时显示四段角标，有日志时显示短弧。选中后提供半透明活动面板。搜索在停止输入 230 毫秒后应用，唯一结果自动聚焦，多结果提供列表，回车定位第一个。窗口默认由画布覆盖；可进一步 F11 全屏，Esc 按当前上下文收起详情、退出全屏或返回。
- 计时核心和数据表结构沿用上一版。热路径没有持续粒子循环。镜头动画只运行约 240 毫秒，历史演化由用户主动播放。实测数据和运行环境见[验证结果](../../TEST-RESULTS.md)。
