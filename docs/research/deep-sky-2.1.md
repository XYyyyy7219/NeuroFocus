# 深空观测的两个源码问题

本轮复核了 1.4 的实机截图、`Body.paint`、星群抽样与镜头代码。标签在场景坐标中绘制，其字号、偏移和光晕一起被放大。父层的活动预览和子层各自生成坐标，镜头进入时缺少可追踪的位置对应。旧光点资源只有径向亮度，放大后无法出现颗粒。任务附件只有文字，视觉基线取自仓库中上版的[Windows 实机图](../screenshots/sky-design/sky-112.png)。

## 新读取的实现

| 仓库与源码 | 读取结果 | 对此次实现的影响 |
| --- | --- | --- |
| dhairyaozaa/procedural-star-system，`31279ace74d542409d15e0dad6348f0a8aa5630c`，[src/shaders/star.js](https://github.com/dhairyaozaa/procedural-star-system/blob/31279ace74d542409d15e0dad6348f0a8aa5630c/src/shaders/star.js) | `starFragmentShader` 把六层 fBm 分别用于细颗粒与低频大尺度结构，频率逐层乘 2.1，振幅减半。边缘亮度由视线与法线控制。`coronaFragmentShader` 以另一组噪声调制边缘透明度和时间脉动。 | 分开处理表面与稀薄外层。静止学习档案无需随时间扰动，细节可以预先生成。代码计算了局部温度变量，但该变量没有进入此处最终色值，不能据此把任意数据标签解释成恒星温度。仓库未查到明确的复用许可，仅阅读实现。 |
| maplibre/maplibre-gl-js，`97126afc028b372172a36bd2006e334c927aadea`，[src/symbol/collision_index.ts](https://github.com/maplibre/maplibre-gl-js/blob/97126afc028b372172a36bd2006e334c927aadea/src/symbol/collision_index.ts) | `placeCollisionBox` 用投影后的锚点确定文字矩形，检查边界、可见性和已有碰撞占位。`insertCollisionBox` 是独立的提交步骤，放置失败的候选无需占用空间。 | 在 Qt 视口里先为控件、星体和高优先级文字留出矩形，通过检测后才加入标签。窗口里最多展示 30 个标签，直接检查矩形足够；密集星团用 Qt 场景索引只查询指针附近对象。根许可证包含 BSD 三条款，复用时需要保留版权和许可声明。[该版本许可证](https://github.com/maplibre/maplibre-gl-js/blob/97126afc028b372172a36bd2006e334c927aadea/LICENSE.txt) |

## 沿用的研究

Physics Atlas 力学导航的 `arrange`、`fit`、指针缩放及按需绘制，为此次父子空间和返回导航提供了直接参照。Stellarium 的 `drawPointSource` 和 Celestia 的点扩散着色器展示了按投影尺寸决定光晕和细节的做法。Three.js 的点精灵适合大批同型对象；多级 Bloom 则需要整屏处理。这里用固定尺寸的发光图像和有界缓存覆盖常用倍率，保留 Qt 自带的原生命中检测。上述源码位置、快照指纹及许可证见[上次逐文件研究](immersive-sky.md)。

新纹理由项目自己的工具生成。两次研究涉及的外部 Shader、地图引擎代码和美术资源均未随此版本分发。Physics Atlas 本轮仅作为既有研究参照。
