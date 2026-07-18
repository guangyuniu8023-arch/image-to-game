# UI 套件：风格定位 → 设计令牌 → 组件实现

游戏的标题页 / HUD / 结算卡不用 AI 生图（不可控、风格易散），用代码绘制（Canvas/CSS，矢量可控、任意主题化）或组件库位图。本文件含风格推导方法、令牌映射与两种实现路径的完整代码模式。

**第一原则：固定的只有可用性骨架**——触控热区 ≥44px、文字对比度 ≥4.5:1（大号字 ≥3:1）、九宫格/圆角不变形、按下态有反馈。**视觉组件不是骨架，是推导产物**。

## 目录

- 组件获取与选用
- 设计令牌
- UI 主题适配策略（骨架固定，皮肤推导）
- Canvas 集成（九宫格/按钮/Logo 字/矢量图标）
- DOM 集成（border-image/卡片/@font-face）
- 教训（踩过的坑）

## 组件获取与选用

1. 下载：`https://kenney.nl/assets/ui-pack` 页的 zip（CC0，含 License.txt，随项目保留一份）。
2. 每个游戏只需 7 个文件（约 40KB）：
   - `Red/Default/button_rectangle_depth_gloss.png` → `btn_red.png`（主按钮，192×64）
   - `Green/Default/button_rectangle_depth_flat.png` → `btn_green.png`（次按钮）
   - `Grey/Default/button_rectangle_depth_border.png` → `chip_grey.png`（HUD 胶囊）
   - `Yellow/Default/star.png` / `star_outline.png` → 星级评价
   - `Extra/Default/icon_play_dark.png` → 播放图标（可选，也可用代码画三角）
   - `Font/Kenney Future.ttf` → `kenney.ttf`（数字/英文显示字体）
3. 这些 PNG 是纯色索引图，只有几百字节——**体积小不是损坏**，用 `file` 验证尺寸即可。

## 设计令牌

所有 UI 从令牌取值，且**主色取自角色**（用 extract_palette.py），换主题整套 UI 自动跟换：

| 令牌 | 值（汪汪主题） | 用途 |
|---|---|---|
| 主色 | `#E53935`（围巾红） | 标题条、主按钮、强调 |
| 主色深 | `#B33A2B` / `#8E2F23` | 描边、厚度层 |
| 底色 | `#FFF8EC`（奶油） | 卡片、chip |
| 描边/文字 | `#6D4C41` / `#4E342E`（深棕） | 全部描边、正文 |
| 辅助 | `#7CB342`（草绿） | 次要按钮 |

规则三条：**颜色全部来自令牌；组件统一圆角/描边宽/底部实色投影（`0 5px 0 深色`）；图标统一矢量风格**。

## UI 主题适配策略（风格定位 → 令牌 → 组件——UI 必须"从角色里长出来"）

**第 0 步：UI 风格定位（先于取色，决定组件形态与质感）**。从主题推导 UI 视觉语言族，再决定组件怎么实现：

| 主题气质 | UI 风格族 | 组件实现路径 |
|---|---|---|
| 美式 Q 版/粗线条卡通（汪汪式） | 粗描边卡通 | Kenney 位图 + 重着色（见下） |
| 梦幻/二次元/清透（星光少女式） | **玻璃拟态**：半透深底 + 1px 细边 + 微发光 + 渐变 | **代码绘制**（Canvas/CSS，配方见下） |
| 像素/复古 | 硬边像素块 | 代码绘制（关抗锯齿，integer 缩放） |
| 手绘/纸感 | 纸纹 + 铅笔线 | AI 素材 + 代码混合 |

**真实教训（v1 被驳回）**：给星空二次元主题只把 Kenney 按钮重着色成冰蓝——组件还是美式粗胖卡通，用户一眼看穿"只换了颜色"。**视觉语言不换，换色就是换皮**。Kenney 只是"美式粗卡通"一个风格族的选项，不是默认解。

四步（风格定位之后执行）：

1. **令牌映射（从调色板到 UI 角色）**：extract_palette.py 产出的调色板按饱和度分工——最饱和色 → 主色（主按钮/标题条/强调）；次饱和色 → 辅助色（次按钮）；中性浅 → 底色；中性深 → 描边/正文。GDD 配色令牌表照此填，禁止直接抄上一个项目。**陷阱（实战反馈）**：立绘的强调色（眼睛/发梢）往往只占约 1% 像素，median-cut 会被白发/皮肤等大面积中性色淹没，得出"全是中性色"的错误结论——**先按 S>0.3 过滤出饱和像素单独聚类，再选主色/辅助色**。
2. **UI 位图重着色（仅位图族；代码绘制族直接按令牌绘制，跳过本步）**：Kenney 纯色索引 PNG 是固定位图——主题色定了之后，必须把按钮/chip 位图重着色到主题色相，而不是复制红/绿原图。算法（Pillow 现写即可）：转 HSV → 主色像素区 hue 替换为目标色相 → 回存 PNG。四条细则（全部来自实战）：
   - 主色像素区判定 **S>0.2**；gloss 高光层是低饱和白色，**保留不染**；
   - 锚定公式：`S' = S·(S_t/S̄)`、`V' = V·(V_t/V̄)`（S_t/V_t = 目标令牌色，均值在着色区上取），着色区均值精确落在令牌色上；
   - **灰色件（chip_grey）没有 hue 可替换，会静默空转**——走"强制染色"分支：全像素设为目标 hue、S 按比例提升、纯白高光保持 S=0；
   - **重着色后必须重命名**（btn_primary/btn_secondary）或留 mapping 注释——btn_red.png 变成粉色后文件名说谎，下个项目复制必拿错。
3. **字体气质**：默认 Kenney Future（圆润卡通，适配大多数主题）；主题域明显不搭（写实/恐怖/硬朗科幻）时，按主题域另选一款 CC0 字体并在 GDD 注明来源与理由。
4. **HUD 图标用主题素材**：HUD 计数图标直接贴本游戏的收集物素材图（星光少女→星星棋子、汪汪→骨头），不用通用符号（★/●）；星级评价等通用组件除外。**至少给主计数器（分数/收集数）配主题图标**；HUD 原本无图标时，动作是"新增"而非"替换"。

反例（真实事故）：三个不同主题的游戏共用同一套红/绿按钮 + 同款 HUD 符号——世界素材主题化了，界面却没跟上，玩家一眼看出"换皮"。

**首次实战验证**（星光少女消消乐，2026-07-19）：银发少女立绘 → 主色冰蓝 `#5BA4E0`（眼/发梢饱和族，S>0.3 过滤后聚类得到）、辅助珊瑚粉 `#D95577`、chip 淡紫强制染色；bot 回归 WIN ✓、截图同框协调 ✓。本节四步细则即由该实战修订产出。

**二次实战（同日，v1 被用户驳回后重做）**：弃 Kenney 位图，全 UI 改 Canvas 代码绘制玻璃拟态——玻璃面板 / 冰蓝渐变发光主按钮 / 幽灵次按钮 / 小号幽灵 HUD 按钮，bot 回归 WIN ✓，两轮审美迭代后验收。配方：

```js
// 玻璃面板:半透深底 + 1px 细边 + 微光
ctx.fillStyle = "rgba(10,16,40,.55)"; rr(x, y, w, h, 10); ctx.fill();
ctx.strokeStyle = "rgba(150,190,255,.35)"; ctx.lineWidth = 1; ctx.stroke();
// 主按钮:纵向渐变(上亮下暗) + 外发光 + 白字(带文字阴影)
ctx.shadowColor = "#5BA4E0"; ctx.shadowBlur = 16;
const g = ctx.createLinearGradient(0, y, 0, y + h);
g.addColorStop(0, "#7AC8F5"); g.addColorStop(1, "#4A90D9");
// 次按钮(幽灵):透明底 + 1px rgba(150,190,255,.5) + 冰蓝字 #9CC8F0,无发光
// HUD 小按钮:高 36px 幽灵款,命中区外扩 6px 保 44px 热区;按下态提亮 15%
```

## Canvas 集成（2D 游戏）

```js
const uiImgs = {};
for (const n of ["btn_red","btn_green","chip_grey","star","star_o","play"]) {
  uiImgs[n] = new Image(); uiImgs[n].src = n + ".png";
}
const uiReady = n => uiImgs[n].complete && uiImgs[n].naturalWidth > 0;

/* 九宫格：四角不动、边与中心拉伸，任意宽不变形（chip/变宽按钮用） */
function draw9(img, x, y, w, h, s) {
  const iw = img.naturalWidth, ih = img.naturalHeight;
  ctx.drawImage(img, 0,0,s,s, x,y,s,s);                 ctx.drawImage(img, iw-s,0,s,s, x+w-s,y,s,s);
  ctx.drawImage(img, 0,ih-s,s,s, x,y+h-s,s,s);          ctx.drawImage(img, iw-s,ih-s,s,s, x+w-s,y+h-s,s,s);
  ctx.drawImage(img, s,0,iw-2*s,s, x+s,y,w-2*s,s);      ctx.drawImage(img, s,ih-s,iw-2*s,s, x+s,y+h-s,w-2*s,s);
  ctx.drawImage(img, 0,s,s,ih-2*s, x,y+s,s,h-2*s);      ctx.drawImage(img, iw-s,s,s,ih-2*s, x+w-s,y+s,s,h-2*s);
  ctx.drawImage(img, s,s,iw-2*s,ih-2*s, x+s,y+s,w-2*s,h-2*s);
}
/* 按钮：原生 192×64 等比缩放（w/h=3）不需九宫格；uiReady 失败回退代码画圆角矩形 */
/* Logo 字三层：厚度层(偏移+深色) → 粗描边(lineJoin=round) → 填充 */
/* 图标：心/骨头用 path 画矢量，不用 emoji（各平台样式不统一） */
```

CSS 里 `@font-face { font-family: Kenney; src: url("kenney.ttf"); }` 后，Canvas 用 `"900 22px Kenney, sans-serif"` 显示数字。

## DOM 集成（3D/其他）

```css
@font-face { font-family: Kenney; src: url("kenney.ttf"); }
.btn  { border-image: url("btn_red.png") 24 fill / 24px; border-style: solid; border-width: 12px; }
.chip { border-image: url("chip_grey.png") 20 fill / 20px; border-style: solid; border-width: 10px; }
/* 卡片不需要 PNG：CSS 圆角 + 棕描边 + 红色标题条 + 底部实色投影即可 */
```

## 教训

1. **emoji 当图标不可控**（❤ 在 iOS/安卓/桌面样式各异）——心、骨头、星星一律 SVG/path 矢量或素材图。
2. **白字 + 半透明浅底 = 隐形**：触控虚拟键曾因此"消失"。移动端控件用深色字 + 实色底 + 描边。
3. **标题字不要纯白描边**：卡通 Logo = 填充 + 主题色粗描边 + 深色厚度层，三层缺一不可。
4. UI 素材也要过"回退注入"纪律：`uiReady` 检查失败就代码回退，绝不白屏。
