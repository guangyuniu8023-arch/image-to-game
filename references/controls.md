# 控制设计：触屏默认 · 语义输入 · 输入模式

游戏最终都在手机上玩，**触屏就是默认形态，不做设备检测、不做文案分叉**：触屏控件常驻渲染，桌面浏览器可直接点按（`mousedown` 兜底，正好供 PC 验收），键盘绑到同一语义变量作为桌面附加便利。说明文案统一写触屏版。

本策略分两层：**语义输入 → 输入模式**。操控方案按**输入维度**推导，不按游戏类型查表——新类型在 [new-type.md](new-type.md) 模块 1 声明输入维度即可继承现成方案，不为单个类型定制一次性方案。

## 目录

- 第 1 层：语义输入（游戏逻辑与设备解耦）
- 第 2 层：输入模式推导（输入维度 → 模式 → 方案）
- 模式 A：虚拟键区实现规范
- 模式 B：陀螺仪 + 半屏回退实现规范
- 模式 C：直指（点选/拖拽）实现规范

## 第 1 层：语义输入（游戏逻辑与设备解耦）

游戏逻辑只消费**语义输入**——`moveX ∈ [-1,1]`、`action`（按下/松开两个事件）、`pointer`（点选/拖拽坐标）。键盘、虚拟键、陀螺仪、半屏按压都只是语义输入的**来源**，在输入合成处汇流（多来源取绝对值最大者）。禁止游戏逻辑直接读 `keyCode`/触摸事件，否则每加一种设备就要改一遍游戏逻辑。

```js
// 语义变量是唯一事实源:keys 由键盘/虚拟键/半屏按压共同写入,tilt 由陀螺仪写入
const moveX = clamp((keys.left ? -1 : 0) + (keys.right ? 1 : 0) + (tilt || 0), -1, 1); // 取合成值
```

## 第 2 层：输入模式推导（声明输入维度 → 落到模式 → 继承方案）

| 游戏需要的输入维度 | 模式 | 触屏方案 | 已验证类型 |
|---|---|---|---|
| 离散方向（左右）+ 瞬时动作（跳/打），动作需要"按住时长"语义 | **A 键区** | 虚拟键区：左下方向键、右下动作键（见下） | 横版过关 |
| 单轴连续量（倾斜/平移 ∈ [-1,1]） | **B 连续轴** | 陀螺仪倾斜为主 + 半屏按压回退（见下） | 竖版弹跳 |
| 点选/拖拽离散对象（棋子、卡牌、塔位） | **C 直指** | 原生 touch 点选/拖动，无需虚拟控件 | 消消乐 |

维度组合时各轴独立落模式（如"移动+瞄准"= A + 右半屏虚拟摇杆）。三个模式覆盖不了的新维度，先回 new-type.md 推演定义清楚输入维度再选方案，**不许为某个类型临时发明一次性方案**。

## 模式 A：虚拟键区实现规范

按键 ≥88px 放拇指热区（屏幕下 1/3），动作键大于方向键（如 116px vs 96px），半透明（opacity .45、按下 .7），容器 `touch-action:none` 防手势冲突（**数值来源**：88px = 触控目标下限惯例——iOS HIG 44pt / Android Material 48dp——在 540 宽舞台上的换算余量；116/96 配比与透明度档承自己验证的平台跳跃模板，用户实机验收通过；注意半透明指整键透明度，字形仍须深色实色+描边，白字+浅底会"隐形"，见 ui-kit.md 陷阱 2）；**多点触控**按 `touch.identifier` 跟踪，支持"按住方向同时跳"；按键映射到与键盘同一语义变量，**松开触发与 keyup 完全相同的逻辑**（如跳跃的可变跳高截断，见 game-patterns.md"跳跃手感三件套"）。控件常驻，桌面浏览器直接可点。

```js
function bindBtn(el, key) {
  const on  = e => { e.preventDefault(); el.classList.add("on"); keys[key] = true;
                     if (key === "jump") press.jump = true; };
  const off = e => { e.preventDefault(); el.classList.remove("on");
                     if (key === "jump" && keys.jump) onJumpRelease(); // 与 keyup 同一截断
                     keys[key] = false; };
  el.addEventListener("touchstart", on, {passive:false});
  el.addEventListener("touchend", off); el.addEventListener("touchcancel", off);
  el.addEventListener("mousedown", on); el.addEventListener("mouseup", off); // 桌面验收
}
// 备选:pointer 事件一套通吃(pointerdown/up/leave/cancel 四个都要绑,leave 防滑出卡键)
```

## 模式 B：陀螺仪 + 半屏回退实现规范

```js
// 首次用户手势时请求权限(iOS 13+ 必须手势内调用);拒绝/不支持 → 静默回退半屏按压
async function enableTilt() {
  if (typeof DeviceOrientationEvent?.requestPermission === "function") {
    try { if (await DeviceOrientationEvent.requestPermission() !== "granted") return; } catch (e) { return; }
  }
  window.addEventListener("deviceorientation", e => { tilt = clamp(e.gamma / 25, -1, 1); });
}
// 回退:左半屏按住 keys.left、右半屏按住 keys.right;输入合成见第 1 层
```

## 模式 C：直指（点选/拖拽）实现规范

不需要虚拟控件。`touchstart/touchmove/touchend` 直接映射棋盘点选与拖动；桌面 `mousedown/mousemove/mouseup` 走同一代码路径（坐标取自事件对象即可，天然兼容）。文案统一写"点选/拖动"，不写"鼠标"。

文案示例（模式 A 类型）："◀ ▶ 移动 · 按住跳键跳跃（长按更高）· 踩怪 +200"——桌面键盘照旧可用（←→/AD 移动 · 空格跳），但文案不必写。
