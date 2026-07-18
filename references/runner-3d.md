# 3D 跑酷类型包（神庙逃亡/地铁跑酷式）

已实战验证的设计基线与实现模式。机器人 4×120s 零受击存活。

## 目录

- 技术栈与架构
- 设计基线（数值全部验证过）
- 场景美术：地面贴图与密度三层
- 外部 3D 素材库集成（GLB 模板化，推荐）
- 程序化建模模式（兜底）
- 程序化角色：IP 特征复刻（核心）
- 卡通渲染三件套（美术升级）
- 竖屏锁定（3D 版）
- 手机显存纪律与上下文丢失
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

## 场景美术：地面贴图与密度三层

"地面丑/场景空"是两类问题的叠加，分开治：

**地面贴图规范**（轨道/草地这类大平面画布纹理）：
- 画布 512² 起步（256² 细节必然糊）、repeat 宁少勿多（轨道 1×15、草地 8×20），重复感比分辨率更显廉价
- 配色从设计令牌取（暖棕道砟 #a5907a、草地 #93cd6d），忌高饱和纯绿/灰泥色
- 结构 = 底色 + 大块明暗色斑（破单调的关键）+ 中景细节（枕木/碎石/草簇）+ 高光点缀（钢轨高光、小花）

**密度三层**（"空旷"的解法是分层，不是堆数量）：
1. 远景带：树/房子/大灌木，x 8~26，约 40 个
2. **近轨点缀带**：草簇/小灌木/小石头，x 4.8~7.5，约 26 个——贴着跑道擦过，是速度感和丰富度的主要来源，小物件可省描边
3. 云：12 朵，大小 10~19、y 14~32 拉开层次
回收时按"带"重置 x（scenItems 存 `near` 标记），否则近轨带会被随机到远处。

## 外部 3D 素材库集成（GLB 模板化，推荐）

程序化几何体拼装适合"特征明确的主角"，但树/房/车等通件道具拼不过专业美术。**道具丑的第一反应应该是换素材库，不是调代码**。

**来源决策**（按优先级）：
1. **CC0 低模库**：Quaternius（quaternius.com，自然/建筑/载具包，CC0 无需署名）、Kenney kit 系列（kenney.nl，GLB 直出）。同包/同作者选全套——混来源画风必打架
2. 文生/图生 3D（Tripo/Meshy）：只用于库里没有的 IP 定制品，注意免费层许可（非商用或 CC BY 署名）
3. Sketchfab 等许可混杂站：逐件核实成本高，避免

**获取与转换管线**（kenney.nl 直链慢/断传损坏时的实战路径）：
- GitHub 搜 CC0 镜像仓库（api.github.com/search/repositories）→ `cdn.jsdelivr.net/gh/<owner>/<repo>@<branch>/<url编码路径>` 拉单件（快且稳）
- FBX → GLB：`npm i fbx2gltf` 自带 Linux 二进制；GLB 解析校验（JSON chunk 读材质名/贴图/尺寸）
- 选型必须目检：搭一个"全部模型排队"的测试页截一张图再定名单

**GLB 模板化模式**（游戏内集成）：
```js
const gltfLoader = new THREE.GLTFLoader(loadMgr);   // 必须挂同一个 LoadingManager → 加载门自动覆盖
// 每个 GLB 加载后预处理成模板，游戏中 clone(true) 实例化（几何/材质共享）
function prepModel(name, gltf) {
  const meshes = [];
  root.traverse(m => { if (m.isMesh) meshes.push(m); });   // 先收集！traverse 回调里 add 会死循环
  for (const m of meshes) {
    m.material = new THREE.MeshLambertMaterial({ color: src.color, name: src.name });  // 转平光统一画风
    m.castShadow = true; outline(m);                     // 描边在模板阶段做一次，克隆自带
  }
  // 归一化：树房按高=1、载具按宽=1（先旋正长轴再量），锚点移到"底部中心"，尺寸存 TPL[name].dims
}
```
- **克隆件动态换色前必须 `m.material = m.material.clone()`**，否则一改全改
- **长载具拼装**（火车=车头+N 节车厢+尾节）：模板记录各段长度，按碰撞盒总长 `g.scale.z = len/total` 贴合；碰撞语义不变
- **兜底**：`THREE.GLTFLoader` 缺失或加载失败 → 回退程序化建造器（`tplReady()` 门控）
- 手动给 GLB 配外部贴图（如调色板）：`t.flipY = false; t.encoding = THREE.sRGBEncoding`（r147），否则颠倒/发灰

## 程序化建模模式（场景，兜底）

模型库不可用时的兜底建造器，也是"机制原型"的快速验证手段：
- **轨道**：512² 画布纹理手绘（道砟色斑 + 枕木横条 + 每道两条钢轨，按 `laneU=(x+4.4)/8.8` 定位），RepeatWrapping 铺满 400 长平面，`offset.y += speed×dt/13.33` 模拟前进——比回收路段简单得多
- **远景回收池**：树（球+圆柱）/房子（盒+锥顶）+ 云（画布纹理 sprite），z>25 传送回 -220 并随机 x
- **障碍建造器**：火车（盒组）、护栏（双柱+斜纹板）、横梁（双柱+梁+挂牌）
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

## 手机显存纪律与上下文丢失

**症状识别**：整屏只剩底色（场景全消失）但 DOM HUD/面板数值正常 = WebGL 上下文丢失或渲染进程被杀，不是逻辑 bug。桌面无头截图测不出来，要靠机制预防。

**预防**（MSAA×高 pixelRatio 的帧缓冲是显存大头，其次大贴图）：
- `renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5))`——别用 2，视觉差别极小、显存省一半以上
- 单张纹理压到 ≤1024（AI 常出 1536+）：缩图后显存立省 3/4
- 不透明大图一律 JPG（天空 1.3MB PNG → 63KB JPG）；只有透明件保 PNG
- 描边壳翻倍网格数：小点缀件（草簇）不加描边

**兜底**（三层防御，缺一不可）：
1. `webglcontextlost` 监听 → 进兼容模式重载；
2. **渲染守卫**：主循环整体 try/catch，连续 3 帧异常 → 进兼容模式重载；
3. **看门狗**：资源就绪后 90 帧仍 `renderer.info.render.calls === 0`（静默不渲染：不抛错但画布透明只剩底色）→ 进兼容模式重载。

**兼容模式**（`localStorage.runner_safe=1`，渲染失败时自动写入并重载）：关 AA/阴影/描边、像素比 1。兼容模式仍失败 → 显示带 BUILD 号的错误页，**绝不静默蓝屏**。

**BUILD 版本号上屏**（标题页角标）：用户报"还是丑/还是崩"时，先让截图里的 BUILD 号说话——确认用户跑的是不是最新版（预览链接/缓存会让用户一直玩旧版）。

**"画布蓝屏但 DOM HUD 活着"的诊断顺序**：① GLB 数据体检（extensions/属性类型/interleaved，exotic 扩展在旧驱动上会崩）→ ② 连发模拟排逻辑/NaN → ③ 显存与上下文 → ④ 防御式降级。前三步都查不出时直接上 ④，别死磕远程复现。

## 验证方法

- **机器人** `scripts/runner_bot.js`：找最近一排 → 算 blocked lanes → 护栏/横梁提前 0.45×速度 跳/滑、火车提前换道。120s 存活即证明刷怪公平
- **WebGL 无头截图**：`chromium --headless=new --enable-unsafe-swiftshader --screenshot=...`
- **快进注入**：与平台跳跃相同（同步 update(1/60)×N）

## 已知坑

1. 逻辑层若读 mesh.position 等 Proxy 桩属性会 NaN/抛错——所以逻辑/渲染必须分离，逻辑只碰纯数据
2. `node ... | head` 会 SIGPIPE，导致 `&&` 链后续命令静默不执行
3. 远景雾（Fog 60-200）遮 distant pop-in；草地配色要柔（高饱和亮绿很刺眼）
4. 换道输入要"按一次换一次"（keydown 消费制），不能按住连续换
5. `traverse` 回调里给场景 add 节点（如描边壳）会触发无限递归栈溢出——先收集网格到数组，遍历结束后再统一 add
6. rAF 循环会把 `--virtual-time-budget` 瞬间烧完，截图永远在加载前——用 CDP 等 `document.title==="READY"` 再截
7. kenney.nl 直链下载慢且断传会产出"尺寸超原文件"的坏 zip（服务端不理 Range，续传=重复追加）——改走 GitHub 镜像 + jsdelivr 拉单件
