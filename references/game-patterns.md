# 平台跳跃游戏实现模式（原生 Canvas + JS，无引擎）

照抄结构、替换主题。所有代码已在真实项目验证。

## 目录

- 文件与代码结构
- 瓦片地图与 AABB 分离轴碰撞
- 跳跃手感三件套
- 敌人巡逻 AI
- 相机与视差背景
- 跑步序列帧动画
- 竖屏锁定布局
- 触控按钮
- WebAudio 合成音效

## 文件与代码结构

单个 `index.html` + 一张精灵图。多个 `<script>` 块按顺序：基础常量 → 关卡数据/构建 → 音效/输入 → 物理碰撞 → 更新逻辑 → 渲染 → 主循环。多块共享全局词法作用域，可直接跨块引用，但禁止重复声明同名。

精灵绘制（锚定脚底中心，朝向翻转 + 压扁拉伸）：

```js
ctx.save();
ctx.translate(x + w/2, y + h);          // 脚底中心
ctx.scale(face, 1);                     // 朝左镜像
ctx.scale(1 + squash, 1 - squash);      // squash>0 压扁(落地)，<0 拉长(起跳)
ctx.drawImage(img, -dw/2, -dh, dw, dh);
ctx.restore();
```

## 瓦片地图与 AABB 分离轴碰撞

```js
const TILE = 45, ROWS = 12;
const T = { EMPTY:0, GROUND:1, BRICK:2, Q:3, USED:4, PIPE:5, STAIR:6, PLAT:7 };
const solid = t => t >= 1 && t <= 6;   // PLAT 是单向板，单独处理
```

先 X 后 Y 分轴移动解算；Y 轴下落时单向板只在 `prevBottom <= 板顶 + 10` 时生效；上升撞头返回砖块坐标用于激活 ? 砖：

```js
function moveY(e, dt, onBump) {
  const prevBottom = e.y + e.h;
  e.y += e.vy * dt; e.onGround = false;
  eachTile(e.x+1, e.y, e.w-2, e.h, (c, r, t) => {
    const oneWay = t === T.PLAT;
    if (!solid(t) && !oneWay) return;
    if (e.vy >= 0) {
      const top = r * TILE;
      if (oneWay && prevBottom > top + 10) return;
      if (e.y + e.h > top) { e.y = top - e.h; e.vy = 0; e.onGround = true; }
    } else if (solid(t)) {
      const bot = (r + 1) * TILE;
      if (e.y < bot) { e.y = bot; e.vy = 0; onBump && onBump(c, r, t); }
    }
  });
}
```

## 跳跃手感三件套

```js
p.coyote = p.onGround ? 0.09 : Math.max(0, p.coyote - dt);   // 土狼时间
p.buffer = Math.max(0, p.buffer - dt);
if (press.jump) { p.buffer = 0.12; press.jump = false; }     // 跳跃缓冲
if (p.buffer > 0 && p.coyote > 0) { p.vy = -JUMP_V; p.buffer = p.coyote = 0; }
// 松键截断（可变跳高）：首选在 keyup/松键事件里执行，且只执行一次：
//   onKeyUp(jump) { if (p.vy < 0) p.vy *= 0.55; }
// 若写在 update 轮询，条件必须带速度阈值（vy < -220），截断一两次后自然失效；
// 严禁 "vy < 0" 配轮询——每帧重复连乘会把跳跃直接"砍头"（实测：机器人上不了坑后浮台、卡死循环）。
if (!jumpHeld && p.vy < -220) p.vy *= 0.55;
```

加分项：起跳瞬间 `squash=-0.25`（拉长）、落地按下落速度 `squash=min(0.3, v/3200)`（压扁）、`squash *= Math.pow(0.001, dt)` 回弹；落地/跑动扬尘粒子。

## 敌人巡逻 AI

撞墙掉头 + 到平台边缘掉头（探测脚下一格前方有无地面）：

```js
e.vx = e.dir * 72;
const wall = moveX(e, dt);          // 返回撞击方向，0 无
moveY(e, dt, null);
if (wall) e.dir = -wall;
else if (e.onGround) {
  const aheadC = Math.floor((e.x + (e.dir > 0 ? e.w + 4 : -4)) / TILE);
  const footR = Math.floor((e.y + e.h + 6) / TILE);
  const t = tileAt(aheadC, footR);
  if (!solid(t) && t !== T.PLAT && footR < ROWS) e.dir *= -1;
}
```

## 相机与视差背景

```js
camX = clamp(camX, 0, LEVEL_W - VIEW_W);   // VIEW_W = 可见世界宽度
```

云/山/灌木不做世界实体，直接画在屏幕空间，按不同速率随相机平移并取模循环，间距 `M/数量` 保证无缝：

```js
const M = LEVEL_W * 0.3 + 1200, n = 16, off = camX * 0.3;   // 云层 0.3 倍速
for (let i = 0; i < n; i++) {
  const x = ((i * (M/n) - off) % M + M) % M - 200;
  cloud(x, y(i), s(i));
}
```

## 资源加载门（必须）

素材总量常达 10MB 级，手机网络下要加载十几秒。**没有加载门，玩家开局就看到占位圆圈/素模**（桌面本地截图永远测不出这个问题）。模式：

```js
// 1. 全部图片登记进 ASSETS（声明完所有 Image 之后）
const ASSETS = [puppyImg, boneImg, /* ...所有素材与 UI 图 */];
const assetsDone = () => ASSETS.filter(im => im.complete).length;  // 加载失败也 complete，走各自回退
// 2. 初始 state = "loading"；输入处理天然拦截（loading 不在任何分支）
// 3. 每帧在界面绘制分支里检查，全部 complete 才进标题页；否则画进度条
if (G.state === "loading") {
  const done = assetsDone();
  if (done >= ASSETS.length) { G.state = "title"; } 
  else { /* 画 Logo + 进度条 + "加载中 done / total" */ return; }
}
```

## 跑步序列帧动画

2D 有左右移动的游戏必备（素材生成见 [assets.md](assets.md) 的"角色序列帧"）。**只有奔跑状态播帧，其他状态静态；帧图没加载好就回退静态图**：

```js
const runImgs = [new Image(), new Image(), new Image(), new Image()];
for (let i = 0; i < 4; i++) runImgs[i].src = "puppy_run" + (i + 1) + ".png";

// update()：相位随速度推进（全速约每帧 0.08s，一个循环约 0.32s）
if (Math.abs(p.vx) > 40 && p.onGround) p.runPh += dt * Math.abs(p.vx) / 26;

// drawPlayer()：状态驱动选帧，帧未就绪回退静态图
const running = p.onGround && Math.abs(p.vx) > 40;
const f = running ? runImgs[Math.floor(p.runPh) % 4] : null;
const im = (f && imgReady(f)) ? f : puppyImg;
// 之后按"锚定脚底中心 + 保持原图宽高比"正常绘制 im
```

验证动画时的坑：快进结束后**必须保持按键输入**（如 `keys.ArrowRight = true`），否则截图瞬间角色已减速停下，拍到的永远是静止帧。

## 竖屏锁定布局

所有游戏竖屏锁定：任何窗口都是 9:16 竖屏画面，横屏窗口时居中留边（世界高度恒定 WH=540，ZOOM 1.2）：

```js
function layout() {
  [W, H, ZOOM] = [540, 960, 1.2];         // 不再判断横竖屏
  VIEW_W = W / ZOOM; OFFY = H - WH * ZOOM; // 世界贴底，上方留天空
  cv.width = W; cv.height = H;
  cv.style.width = "min(100vw, calc(100vh * 9 / 16))";  // 横屏窗口自动居中
}
// 画布外层包一个 flex 居中容器，body 用深色底
// render(): 天空/HUD/界面用画布坐标；世界内容包在
// ctx.translate(0, OFFY); ctx.scale(ZOOM, ZOOM); 里
```

相机、瓦片裁剪一律用 `VIEW_W` 而不是 W。`addEventListener("resize", layout)` 支持旋转屏幕。

## 触控按钮

```html
<div class="tbtn" id="btnJ">跳</div>
<style>@media (pointer: coarse) { .tbtn { display: flex; } }</style>
```

pointerdown/up/leave/cancel 四个事件都要绑；按下写入与键盘相同的 `keys`/`press`，游戏逻辑零改动。

## WebAudio 合成音效

```js
function beep(freq, dur, type="square", vol=0.15, slide=0) {
  const ac = new (window.AudioContext || window.webkitAudioContext)();
  const o = ac.createOscillator(), g = ac.createGain();
  o.type = type; o.frequency.setValueAtTime(freq, ac.currentTime);
  if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(30, freq + slide), ac.currentTime + dur);
  g.gain.setValueAtTime(vol, ac.currentTime);
  g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + dur);
  o.connect(g); g.connect(ac.destination); o.start(); o.stop(ac.currentTime + dur);
}
```

配方：跳跃 `beep(320,.18,"square",.12,500)`；收集 900→1350 两个正弦连音；踩敌 `beep(220,.15,"square",.18,-160)`；顶砖 `beep(140,.08)`；死亡 `beep(500,.5,"sawtooth",.12,-420)`；通关 523/659/784/1047 四音琶音（间隔 130ms）。注意 AudioContext 必须在首次用户手势后创建。

## 触屏输入通用策略（移动端优先，所有游戏必须）

游戏最终都在手机上玩：触屏可玩是硬要求。本策略分三层：**设备检测 → 语义输入 → 输入模式**。操控方案按**输入维度**推导，不按游戏类型查表——新类型只声明输入维度即可继承现成方案，不为单个类型定制。

### 第 1 层：设备检测（环境守卫，bot 桩环境无 `navigator`/`location`，一律 `typeof` 守卫）

```js
const IS_TOUCH = (typeof window !== "undefined" && "ontouchstart" in window)
              || (typeof navigator !== "undefined" && navigator.maxTouchPoints > 0)
              || (typeof location !== "undefined" && /[?&]touch=1/.test(location.search)); // 桌面调试触屏布局
// 文案：IS_TOUCH ? 触屏版 : 键盘+触屏版；桌面端虚拟键 display:none
```

说明文案按设备自适应：**触屏设备只显示触屏说明，桌面端显示键盘+触屏两套**。

### 第 2 层：语义输入层（游戏逻辑与设备解耦）

游戏逻辑只消费**语义输入**——`moveX ∈ [-1,1]`、`action`（按下/松开两个事件）、`pointer`（点选/拖拽坐标）。键盘、虚拟键、陀螺仪、半屏按压都只是语义输入的**来源**，在输入合成处汇流（多来源取绝对值最大者）。禁止游戏逻辑直接读 `keyCode`/触摸事件，否则每加一种设备就要改一遍游戏逻辑。

### 第 3 层：输入模式推导（声明输入维度 → 落到模式 → 继承方案）

| 游戏需要的输入维度 | 模式 | 触屏方案 | 已验证类型 |
|---|---|---|---|
| 离散方向（左右）+ 瞬时动作（跳/打），动作需要"按住时长"语义 | **A 键区** | 虚拟键区：左下方向键、右下动作键（见下） | 横版过关 |
| 单轴连续量（倾斜/平移 ∈ [-1,1]） | **B 连续轴** | 陀螺仪倾斜为主 + 半屏按压回退（见下） | 竖版弹跳 |
| 点选/拖拽离散对象（棋子、卡牌、塔位） | **C 直指** | 原生 touch 点选/拖动，无需虚拟控件；"鼠标"措辞仅桌面显示 | 消消乐 |

维度组合时各轴独立落模式（如"移动+瞄准"= A + 右半屏虚拟摇杆）。三个模式覆盖不了的新维度，先回 new-type.md 推演定义清楚输入维度再选方案，**不许为某个类型临时发明一次性方案**。

### 模式 A：虚拟键区实现规范

按键 ≥88px 放拇指热区（屏幕下 1/3），动作键大于方向键（如 116px vs 96px），半透明（opacity .45、按下 .7），容器 `touch-action:none` 防手势冲突；**多点触控**按 `touch.identifier` 跟踪，支持"按住方向同时跳"；按键映射到与键盘同一语义变量，**松开触发与 keyup 完全相同的逻辑**（如跳跃的可变跳高截断，见"跳跃手感三件套"）；桌面端隐藏、键盘照常。

```js
function bindBtn(el, key) {
  const on  = e => { e.preventDefault(); el.classList.add("on"); keys[key] = true;
                     if (key === "jump") press.jump = true; };
  const off = e => { e.preventDefault(); el.classList.remove("on");
                     if (key === "jump" && keys.jump) onJumpRelease(); // 与 keyup 同一截断
                     keys[key] = false; };
  el.addEventListener("touchstart", on, {passive:false});
  el.addEventListener("touchend", off); el.addEventListener("touchcancel", off);
  el.addEventListener("mousedown", on); el.addEventListener("mouseup", off); // 桌面调试
}
```

### 模式 B：陀螺仪 + 半屏回退实现规范

```js
// 首次用户手势时请求权限（iOS 13+ 必须手势内调用）；拒绝/不支持 → 静默回退半屏按压
async function enableTilt() {
  if (typeof DeviceOrientationEvent?.requestPermission === "function") {
    try { if (await DeviceOrientationEvent.requestPermission() !== "granted") return; } catch (e) { return; }
  }
  window.addEventListener("deviceorientation", e => { tilt = clamp(e.gamma / 25, -1, 1); });
}
// 输入合成：moveX = (keys.left?-1:0) + (keys.right?1:0)，再与 tilt 取绝对值最大者
```

文案示例（模式 A 类型）：触屏设备"◀ ▶ 移动 · 按住跳键跳跃（长按更高）· 踩怪 +200"；桌面"←→/AD 移动 · 空格/W/↑ 跳 · R 重开 · 触屏可用虚拟键"。
