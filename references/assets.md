# 素材流水线：让全套素材"从图片里长出来"

目标：用户给什么图，游戏素材就是什么主题、什么画风。全部以原图做风格参考 AI 生成，风格天然统一。

## 目录

- 素材清单（平台跳跃）
- 角色图驱动策略（特征提取→定制→验收）
- 素材设计规范（2D 平台跳跃）
- 主题映射表
- 五步流水线
- Prompt 模式
- 角色序列帧（2D 左右移动游戏通用）
- 回退注入模式
- 失败处理

## 角色图驱动策略：让素材"是这个角色的世界"

目标：玩家一眼觉得全套素材与角色图是"一家的"，而不是通用素材库。四步：

1. **角色特征提取表**（看角色图必填，结论写进 GDD）：
   - 形态类别：两足竖高 / 四足横宽 / 其他 → 决定主角尺寸基线（见 gdd.md 与"素材设计规范"）
   - 画风：赛璐璐动漫 / kawaii 绘本 / 像素 / 扁平矢量 / 厚涂写实 → 决定风格锚点写法（见下表）
   - 主色 + 点缀色：`extract_palette.py` 取色 → UI 令牌与全套素材配色倾向
   - **标志性元素**：配饰/道具/图案（心形腰包、耳机、武器、宠物）→ 收集物与终点建筑的定制线索
   - 性格/世界观暗示：服装风格、年代感、身份 → 敌人/障碍/背景的主题线索
2. **主题定制**：默认按"主题映射表"；但只要角色有明显的标志性元素，收集物/终点建筑**优先换成角色元素**（例：心形腰包 → 爱心收集物），并在 GDD 写明替换理由——默认映射项只在无线索时使用。
3. **每条 prompt 必含四件**：物件本体 + 视角（见"素材设计规范"）+ 风格锚点（按画风从下表换写法）+ 1-2 个角色特征引用（如 "in the world of an orange twin-tails anime girl, heart motifs"）；并始终带角色图参考 URL。
4. **一致性验收**：全套素材与角色图**并排拼一张 contact sheet** 目检——描边粗细、上色方式、明暗方向、配色家族一致，像"这个角色世界里的东西"；单件跑偏只重新生成那一件。

**风格锚点速查**（替换"Prompt 模式"的默认锚点，全套统一用一个）：

| 画风 | 锚点写法 |
|---|---|
| 赛璐璐动漫 | Japanese anime cel-shading, clean line art, vibrant flat colors |
| kawaii 绘本（默认） | kawaii children's book illustration style, thick dark brown outline, soft flat colors |
| 像素 | 16-bit pixel art, limited palette, crisp pixels, no anti-aliasing |
| 扁平矢量 | flat vector illustration, geometric shapes, bold solid colors |
| 厚涂/写实 | painterly concept art, soft brush strokes, cinematic lighting |

## 素材清单（平台跳跃）

| 素材 | 文件 | 生成方式 |
|---|---|---|
| 主角（2D 游戏） | puppy.png | remove_bg.py 抠图（不用 AI 生成，保真） |
| 主角（3D 游戏） | 代码 | 纸片 sprite 违和时，改用程序化几何体复刻 IP 特征，见 [runner-3d.md](runner-3d.md) |
| 收集物 | bone.png | AI 透明底 1:1 |
| 敌人 | cat.png | AI 透明底 1:1 |
| 障碍物 | hydrant.png | AI 透明底 1:1 |
| 终点建筑 | doghouse.png | AI 透明底 1:1 |
| 地形砖 ×6 | tile_grass/dirt/brick/q/used/stair.png | AI 透明底 1:1 |
| 背景 | bg.png | AI 不透明 3:2 1K |

地形砖清单：草地砖（地表）、素泥土砖（地下）、砖块、? 砖、顶过的砖、台阶石。

## 素材设计规范（2D 平台跳跃）

**尺寸一律锚定 TILE=45**（游戏内尺寸按下表绘制，不靠 AI 自己把握大小；AI 只负责画风与内容）：

| 素材 | 游戏内尺寸 | 规则 |
|---|---|---|
| 主角（两足/竖高） | 高 ≈88px（2 格） | 碰撞盒 ≈34×84，锚脚底中心 |
| 主角（四足/横宽） | 高 ≈62px（1.4 格） | 碰撞盒 34×50，锚脚底中心 |
| 收集物 | 30-36px（0.7-0.8 格） | 锚中心 + 旋转/脉动；太小看不见、太大像障碍 |
| 敌人 | 高 38-46px（0.85-1 格） | 必须比主角矮——"可踩"的视觉前提 |
| 障碍物 | 宽 ≈1 格、高 2-3 格 | 贴图比碰撞体每边大 4-6px 更自然 |
| 地形砖 | 45×45 整格 | 平铺无缝；草皮/泥土/砖同族同描边 |
| 终点建筑 | 高 ≈150px（3-4 格） | 全程最大单体素材，承担视觉终点 |
| 背景 | 3:2、地平线在下 1/3 | 低对比不抢戏；禁假平台（见"失败处理"） |

**视角统一**：角色/敌人 side view facing right（移动方向）；收集物/障碍/建筑 front view；全套只用一个风格锚点。

**风格一致性验收**：全套生成后拼一张 contact sheet 目检——描边粗细一致、平涂上色、明暗方向统一、饱和度同区间；单件跑偏只重新生成那一件（见"失败处理"）。

**内容占比**：透明素材内容包围盒 ≥80%，裁到内容边缘（留白过多 → 游戏内视觉缩水）。

**序列帧**：与静态主角同内容高度、同画风；帧间脚底对齐不漂移；循环 A→B→C→A（详见后文）。

## 主题映射表

| 主角 | 收集物 | 敌人 | 障碍物 | 终点 |
|---|---|---|---|---|
| 狗 | 骨头 | 生气猫 | 消防栓 | 狗屋 |
| 猫 | 鱼干 | 凶狗 | 毛线球 | 猫窝 |
| 兔子 | 胡萝卜 | 狐狸 | 栅栏 | 兔窝 |
| 人/其他 | 星星/相关物 | 史莱姆 | 石柱 | 房子/城堡 |

## 五步流水线

1. **抠主角**：`python3 scripts/remove_bg.py <原图> <主角.png>`
2. **取主色**：`python3 scripts/extract_palette.py <主角.png>`，主色用于 UI 点缀配色参考。
3. **传参考图**：`image_generation_tool.py image-to-url --image-path <主角.png>` 拿公开 URL。
4. **批量生成**（每个素材一条命令，可并行但注意用绝对路径）：
   ```bash
   image_generation_tool.py generate \
     --description "<物件描述>, kawaii children's book illustration style, thick dark brown outline, soft flat colors, matching the art style of the reference image, isolated single object" \
     --ratio "1:1" --background "transparent" --reference-image "<URL>" --output <素材.png>
   ```
   背景图用：`--ratio "3:2" --resolution "1K" --background "opaque"`，描述结尾加 `no platforms, no blocks, no bricks, no floating islands, no characters, no animals, no text, no watermark`。
5. **清理**：`python3 scripts/clean_sprite.py <原素材.png> <成品.png>` 去水印碎块+裁剪；背景图（不透明）直接裁掉底部 9% 条带去水印。处理完**必须目检**。

## Prompt 模式

- 风格锚点固定写法：`kawaii children's book illustration style, thick dark brown outline, soft flat colors, matching the art style of the reference image`
- 物件：一句话说清本体 + 视角（front view）+ `isolated single object`
- 用户图是别的画风（像素/写实/扁平）就换风格锚点，保持全套一致
- 透明底只支持 1:1 / 3:2 / 2:3 的 1K PNG

## 角色序列帧（2D 左右移动游戏通用）

**凡是 2D 且角色会左右移动的游戏，奔跑状态必须有序列帧（每状态 4 帧）**；跳跃/站立/受伤等其他状态用静态图即可。2 帧会明显顿挫，4 帧才流畅。

**循环结构必须是 A→B→C→A：最后一帧与第一帧完全相同**（中间两帧是运动过渡），否则播到末尾跳回开头时会"咯噔"一下。第 4 帧不要靠 AI 画"一样的"，直接用代码复制第 1 帧（确定性）；AI 只需产出 3 个不同姿势。

**一张 2×2 图出 4 帧**（一张图内一致性远好于分 4 次生成，且只调一次 API）：

1. **生成**（以抠图主角为风格参考）：
   ```bash
   image_generation_tool.py generate \
     --description "2x2 sprite sheet of <主角描述> running, 4 cells arranged in an even 2x2 grid with equal spacing, each cell contains the same character in side view facing right in a different run-cycle pose: top-left full stride, top-right gathered mid-air, bottom-left opposite stride, bottom-right pushing off the ground, <风格锚点>, each fully inside its own grid cell, no overlapping, no grid lines, no text, no watermark" \
     --ratio "1:1" --background "transparent" --reference-image "<URL>" --output sheet.png
   ```
2. **去水印**：`clean_sprite.py sheet.png sheet_clean.png`。注意它会按内容包围盒**整体裁剪**，之后必须按清理后的新尺寸切。
3. **切帧**：`slice_sheet.py sheet_clean.png <主角>_run --order tl,tr,br,bl`（按运动链指定格子顺序，如"伸展跨步→收腿腾空→落地发力"），得 `<主角>_run1..4.png`。
4. **首尾闭环**：选出运动链的 3 帧作为 run1/2/3 后，`cp run1 run4`——第 4 帧是第 1 帧的复制品，保证循环无跳变。
5. **拼接目检 4 帧**（必须）：整体裁剪后象限中线可能偏移，角色被切断就调整 --order 或重新生成。

播放代码模式见 [game-patterns.md](game-patterns.md) 的"跑步序列帧动画"。

## 回退注入模式

每个素材加载后先检查、失败走代码手绘，游戏永不白屏：

```js
const boneImg = new Image(); boneImg.src = "bone.png";
const imgReady = im => im.complete && im.naturalWidth > 0;
function drawBoneShape(x, y, s) {
  if (imgReady(boneImg)) { /* drawImage 按原图宽高比绘制 */ return; }
  /* …程序化手绘回退… */
}
```

绘制时保持原图宽高比：`h = w * (im.naturalHeight / im.naturalWidth)`；角色/敌人锚定脚底中心；地形砖按 TILE×TILE 绘制。**标题页/结算页等展示位同样必须等比，禁止写死宽高硬拉伸**（竖高立绘硬拉进横宽框会直接压扁）。抠图/清理后目检内容包围盒：留白过多会让"按图高绘制"的角色视觉缩水，必须裁到内容边缘。

## 素材体积纪律

AI 生成的 PNG 单张常在 1MB 上下，全套素材很容易到 10MB 级——手机网络下加载要十几秒，加载门的等待会直接被玩家感知。约束：素材总量控制在 ~5MB 内；不透明大图（背景、地形砖）优先导出时压尺寸/转 JPG 或 WebP；透明小件保持 PNG。单张纹理单边压到 ≤1024（AI 常出 1536+，3D 里每张大图都是数 MB 显存，手机会丢 WebGL 上下文整屏变底色）。

## 失败处理

- HTTP 424（服务暂时不可用）：sleep 20-30s 重试；2K 反复失败就降 1K。
- 背景画出"假平台/假砖块"误导玩家：重新生成，prompt 加 no platforms / no blocks。
- 抠图后为空：容差调小；背景太复杂就换 AI 生成主角（描述尽量贴合原图特征）。
- 单个素材风格跑偏：只重新生成那一个，prompt 里补一句与其他素材一致的具体特征。
