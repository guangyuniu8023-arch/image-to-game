# 3D 跑酷类型包（神庙逃亡/地铁跑酷式）

已实战验证的设计基线与实现模式。机器人 4×120s 零受击存活。

## 目录

- 技术栈与架构
- 设计基线（数值全部验证过）
- 程序化建模模式（场景）
- 程序化角色：IP 特征复刻（核心）
- 卡通渲染三件套（美术升级）
- 竖屏锁定（3D 版）
- 验证方法
- 已知坑

## 技术栈与架构

- three.js **r147 UMD**，下载打包进项目本地，不依赖 CDN（r160+ 已移除 UMD 构建，别用新版）
- **逻辑层与渲染层严格分离**：逻辑层纯数据（障碍= {lane,z,type,len}），零 THREE 依赖 → 机器人测试用吸收 Proxy 桩掉 THREE 即可在 node 跑
- 世界模拟：玩家/相机不动，障碍与远景向 +z 移动；地面是静态平面，只滚动纹理 `offset.y`

## 设计基线（数值全部验证过）

| 项 | 值 |
|---|---|
| 跑道 | 3 条，x = -2.2 / 0 / 2.2，玩家 z=0 |
| 相机 | (0, 4.1, 7.8)，lookAt (0, 1.35, -10)，x 跟随玩家 0.55 倍 |
| 速度 | 12 起，+0.45/s，上限 30；受击 0.45× 减速 0.5s |
| 跳跃 | vy=8.5，g=25 → 高 1.45、滞空 0.68s |
| 滑铲 | 0.65s，判定高 1.0；空中按滑铲 vy=-12 快速下砸 |
| 换道 | lane 索引 + x 插值 dt×12，带侧倾 |
| 障碍 | 护栏（高 1.0，跳）、横梁（底 1.55，滑）、火车（满高长 10-15，换道） |
| 刷怪 | 每排占 1-2 条道、**永不占满 3 条**；排间距 max(16, speed×1.15)（≥1 秒反应窗） |
| 收集物 | 5 连排：直线 y=0.8 或弧线 y=1.6-\|i-2\|×0.45 |
| 生命 | 3，受伤无敌 1.5s（visible 闪烁） |

## 程序化建模模式（场景）

- **轨道**：256² 画布纹理手绘（道砟色块 + 枕木横条 + 每道两条钢轨，按 `laneU=(x+4.4)/8.8` 定位），RepeatWrapping×30 铺满 400 长平面，`offset.y += speed×dt/13.33` 模拟前进——比回收路段简单得多
- **远景回收池**：26 个树（球+圆柱）/房子（盒+锥顶）+ 8 云（画布纹理 sprite），z>25 传送回 -220 并随机 x
- **障碍建造器**：火车（车身/车顶/底盘/车窗条/车头/挡风玻璃 6 个盒）、护栏（双柱 + 黄黑斜纹画布纹理板）、横梁（双柱 + 梁 + 骨头挂牌）
- **网格生命周期**：`allMeshes` 注册表，syncWorld 每帧按数据集合增删网格——防止已回收障碍的"僵尸网格"泄漏

## 程序化角色：IP 特征复刻（核心）

**何时用**：2D 抠图 sprite（纸片人）在 3D 世界里违和时——尤其跑酷相机在背后，正面 sprite 像"坐着倒滑"。

**方法**：读图提取 IP 特征（主色、标志配饰、轮廓）→ 几何体拼装 → 程序化动画。**特征＞还原度**：配饰和配色对了就"像"，不追求解剖正确。

小狗案例（约 25 个几何体）：
- 奶油身体（球 scale 0.9/0.85/1.25）、头、口鼻、黑鼻、眼
- 长垂耳：扁球 scale(0.5, 1.35, 0.65)
- 红围巾：torus 项圈 + 3 节渐窄飘带（box）
- 卷尾：扁球拉长上翘
- 4 条腿：髋关节 Group 枢轴（圆柱+球爪），摆动绕 hip.rotation.x

动画（全部 sin 驱动）：
- 对角腿成对摆动（幅度 0.9，频率随速度）：legs[0]/[3] 同相、legs[1]/[2] 反相
- 次级运动相位滞后：耳朵 `sin(ph-0.7)`、围巾逐节 `sin(ph×0.6 - i×0.9)`——这是"活"的关键
- 身体颠簸 `|sin(ph)|×0.08`；换道 rotation.z 侧倾 + rotation.y 微转
- 跳跃：收腿（前 -0.6 后 +0.5）+ scale.y 1.08 拉伸；滑铲：scale.y 0.55

## 卡通渲染三件套（美术升级）

素色几何体"丑"的根源是光秃秃，解法是三件套，全部加上后素模变绘本风：

1. **描边**（inverted hull）：一个共享材质 + 一个辅助函数，给每个网格套上放大的背面壳：
   ```js
   const outlineMat = new THREE.MeshBasicMaterial({ color: 0x2a2320, side: THREE.BackSide });
   function outline(m, th = 1.045) {
     const o = new THREE.Mesh(m.geometry, outlineMat);
     o.scale.set(th, th, th); o.raycast = () => {}; m.add(o); return m;
   }
   ```
   角色用 `traverse` 收集全部件后统一 `outline(m, 1.05)`。全场景共用同一个 outlineMat，省材质。
2. **阴影**：`renderer.shadowMap.enabled = true` + `PCFSoftShadowMap`；一盏 DirectionalLight 开 castShadow，正交视锥覆盖赛道（left/right ±18、top 25、bottom -40、mapSize 1024）；地面和轨道 receiveShadow。有落地影物体才不"飘"。
3. **纹理**：256² 画布纹理给素面加细节——草地（底色+斑点+小花，RepeatWrapping）、房子窗户立面（BoxGeometry 材质数组按面贴）；天空用 AI 生成的大图贴 `PlaneGeometry(420,120)` + `MeshBasicMaterial({map, fog:false})` 放远处 (0,30,-195)。

## 竖屏锁定（3D 版）

游戏区永远竖屏比例：画布和 HUD/面板全部包进 `#stage` 容器（`position:fixed; overflow:hidden`），布局函数计算舞台矩形，横屏窗口时居中 9:16：

```js
function layout() {
  const MAX_A = 0.75;                        // 允许的最宽宽高比
  let w = innerWidth, h = innerHeight;
  if (w / h > MAX_A) w = Math.round(h * 9 / 16);
  const st = document.getElementById("stage");
  st.style.width = w + "px"; st.style.height = h + "px";
  st.style.left = (innerWidth - w) / 2 + "px"; st.style.top = (innerHeight - h) / 2 + "px";
  if (renderer) { camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h); }
}
// 启动时 initScene() 后调 layout()；addEventListener("resize", layout)
// DOM：<div id="stage"><canvas><div id="hud"><div id="panel"></div>，三者 position:absolute
```

## 资源加载门（3D 版）

纹理走 LoadingManager、DOM 图片（UI/标题图）用 Image 计数，**两路合并进度**，全部就绪才开局；加载中标题页显示进度条：

```js
const loadMgr = new THREE.LoadingManager();
const texLoader = new THREE.TextureLoader(loadMgr);   // 所有纹理统一用这个 loader
let assetsReady = false, texDone = 0, texTotal = 1, imgDone = 0;
const domAssets = ["puppy.png", "btn_red.png", /* ...全部 DOM 侧图片 */];
const imgTotal = domAssets.length;
function updateLoadingUI() {
  const done = texDone + imgDone, total = texTotal + imgTotal;
  assetsReady = done >= total;
  /* 更新 #loadbar 宽度与 #loadtxt 文本；assetsReady 且标题页 → 重绘完整标题 */
}
loadMgr.onProgress = (u, d, t) => { texDone = d; texTotal = t; updateLoadingUI(); };
loadMgr.onLoad = () => updateLoadingUI();
for (const src of domAssets) { const im = new Image(); im.onload = im.onerror = () => { imgDone++; updateLoadingUI(); }; im.src = src; }
function anyKey() { if (!assetsReady) return; /* ...原逻辑 */ }
```

注意：`new Image()` 不设 src 时 `complete` 为 true（测试时别用它模拟"未加载"）；机器人桩里让 Image 的 src setter 立即触发 onload。

## 验证方法

- **机器人** `scripts/runner_bot.js`：找最近一排 → 算 blocked lanes → 护栏/横梁提前 0.45×速度 跳/滑、火车提前换道。120s 存活即证明刷怪公平
- **WebGL 无头截图**：`chromium --headless=new --enable-unsafe-swiftshader --screenshot=...`
- **快进注入**：与平台跳跃相同（同步 update(1/60)×N）

## 已知坑

1. 逻辑层若读 mesh.position 等 Proxy 桩属性会 NaN/抛错——所以逻辑/渲染必须分离，逻辑只碰纯数据
2. `node ... | head` 会 SIGPIPE，导致 `&&` 链后续命令静默不执行
3. 远景雾（Fog 60-200）遮 distant pop-in；草地配色要柔（高饱和亮绿很刺眼）
4. 换道输入要"按一次换一次"（keydown 消费制），不能按住连续换
