#!/usr/bin/env bash
# selfcheck.sh — skill 防回退自检（每次推送 skill 改动前必跑，全绿才许推）
#
# 为什么有这个脚本：skill 自进化（变体积累/泛化/新工具）只加不改，但脚本、
# 模板、机器人会被编辑——回退只可能从这里进来。本脚本把"旧能力还活着"
# 变成一条命令：机器人回归（模板+参考项目）+ 工具合成夹具冒烟 + 文档断链检查。
# 源码仓库有 templates/ 时硬验现有模板；不带模板的 .skill 分发包明确 SKIP。
# 参考项目（match3/doodlejump 等无模板的类型）默认取仓库同级目录，缺失则 SKIP 不判负。
set -u
cd "$(dirname "$0")/.."
FAIL=0
ok()   { echo "  ✓ $1"; }
bad()  { echo "  ✗ $1"; FAIL=1; }
skip() { echo "  - $1（SKIP）"; }

echo "== A. 机器人回归（类型能力硬门槛）=="
if [ -d templates ]; then
  if node scripts/bot_platformer.js templates/platformer-2d/index.html 2>&1 | grep -q "WIN: true"; then
    ok "platformer-2d 模板 bot WIN"
  else bad "platformer-2d 模板 bot 未通关"; fi

  if node scripts/runner_bot.js templates/runner-3d/index.html 120 >/dev/null 2>&1; then
    ok "runner-3d 模板 bot 存活"
  else bad "runner-3d 模板 bot 失败"; fi
else
  skip "templates/ 未随 .skill 分发，仓库模板机器人未检"
fi

for proj in ../match3 ../match3-timed ../doodlejump; do
  name=$(basename "$proj")
  if [ ! -f "$proj/index.html" ]; then skip "${name}（参考项目不在同级，未检）"; continue; fi
  case "$name" in
    doodlejump)
      w=0
      for i in 1 2 3; do
        node scripts/bot_doodle.js "$proj/index.html" 2>&1 | grep -q "WIN: true" && w=$((w+1))
      done
      [ "$w" = 3 ] && ok "$name bot 3×WIN" || bad "$name bot 3 次仅 $w 次 WIN";;
    *)
      node scripts/bot_match3.js "$proj/index.html" 2>&1 | grep -q "WIN: true" \
        && ok "$name bot WIN" || bad "$name bot 未通关";;
  esac
done

echo "== B. 工具冒烟（合成夹具，即造即测）=="
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
B_RES=$(python3 - "$TMP" <<'PYEOF'
import sys, subprocess, json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

tmp = Path(sys.argv[1]); S = "scripts"
res = []

def capsule(off):
    """200x100：深色底 + 亮胶囊(行30..70) + 白字(行40+off..60+off)"""
    a = np.full((100, 200, 3), (30, 34, 60), np.uint8)
    a[30:71, 40:160] = (120, 180, 230)
    a[40+off:61+off, 80:120] = (255, 255, 255)
    p = tmp / f"cap{off}.png"; Image.fromarray(a).save(p); return p

p1 = capsule(0)
r = subprocess.run(["python3", f"{S}/audit_ui_align.py", str(p1), "--region", "t=0,0,200,100"], capture_output=True)
res.append(("audit_ui_align 居中→PASS", r.returncode == 0))
p2 = capsule(-8)
r = subprocess.run(["python3", f"{S}/audit_ui_align.py", str(p2), "--region", "t=0,0,200,100"], capture_output=True)
res.append(("audit_ui_align 偏8px→FAIL", r.returncode != 0))

for i, c in enumerate([(220, 80, 80, 255), (80, 200, 120, 255), (90, 120, 230, 255)]):
    Image.new("RGBA", (40, 40), c).save(tmp / f"a{i}.png")
r = subprocess.run(["python3", f"{S}/make_contact_sheet.py", str(tmp/"a0.png"),
                    str(tmp/"a1.png"), str(tmp/"a2.png"), "-o", str(tmp/"cs.png")], capture_output=True)
res.append(("make_contact_sheet 出图", r.returncode == 0 and (tmp/"cs.png").exists()))
r = subprocess.run(["python3", f"{S}/make_contact_sheet.py", str(tmp/"a0.png"), str(tmp/"a1.png"), "-o", str(tmp/"cs2.png"), "--silhouette"], capture_output=True)
res.append(("make_contact_sheet --silhouette", r.returncode == 0 and (tmp/"cs2.png").exists()))

r = subprocess.run(["python3", f"{S}/extract_palette.py", str(tmp/"a2.png")], capture_output=True)
res.append(("extract_palette 取色", r.returncode == 0))

spr = np.zeros((100, 100, 4), np.uint8)
spr[30:70, 30:70] = (200, 60, 60, 255); spr[85:90, 85:90] = (20, 20, 20, 255)
Image.fromarray(spr).save(tmp/"spr.png")
r = subprocess.run(["python3", f"{S}/clean_sprite.py", str(tmp/"spr.png"), str(tmp/"spr_c.png")], capture_output=True)
def wm_gone():
    if r.returncode != 0 or not (tmp/"spr_c.png").exists(): return False
    o = np.array(Image.open(tmp/"spr_c.png")).astype(int)
    wm = (np.abs(o[..., 0] - 20) < 12) & (o[..., 3] > 10)   # 水印色残存的不透明像素
    return wm.sum() == 0 and (o[..., 3] > 10).sum() > 500   # 主体还在
res.append(("clean_sprite 去角落水印", wm_gone()))

sheet = np.zeros((100, 100, 4), np.uint8)
for i, (x, y) in enumerate([(0, 0), (50, 0), (0, 50), (50, 50)]):
    sheet[y:y+50, x:x+50] = (60*i+40, 100, 200, 255)
Image.fromarray(sheet).save(tmp/"sheet.png")
r = subprocess.run(["python3", f"{S}/slice_sheet.py", str(tmp/"sheet.png"), str(tmp/"fr")], capture_output=True)
res.append(("slice_sheet 切4帧", r.returncode == 0 and all((tmp/f"fr{i}.png").exists() for i in range(1, 5))))

wb = np.full((60, 60, 3), 255, np.uint8); wb[15:45, 15:45] = (200, 40, 40)
Image.fromarray(wb).save(tmp/"wb.png")
r = subprocess.run(["python3", f"{S}/remove_bg.py", str(tmp/"wb.png"), str(tmp/"wb_o.png")], capture_output=True)
good = r.returncode == 0 and (tmp/"wb_o.png").exists() and \
    (lambda o: o[..., 3].max() == 255 and o[0, 0, 3] == 0)(np.array(Image.open(tmp/"wb_o.png")))
res.append(("remove_bg 抠白底", good))

# Sprite 流水线：批准 Seed → 整条 → 共享缩放/root → socket preview → 硬审计
# Deliberately use a much higher-resolution Seed than the generated strip.
# This guards against treating unrelated source DPI as shared visual scale.
seed = np.zeros((256, 192, 4), np.uint8)
seed[32:240, 48:144] = (235, 90, 90, 255)
Image.fromarray(seed).save(tmp/"seed.png")
r = subprocess.run([
    "python3", f"{S}/build_sprite_edit_canvas.py", "--seed", str(tmp/"seed.png"),
    "--out", str(tmp/"edit.png"), "--frames", "4", "--slot-width", "64",
    "--slot-height", "64", "--canvas-width", "256", "--canvas-height", "128",
    "--resample", "nearest"
], capture_output=True)
res.append(("build_sprite_edit_canvas Seed编排", r.returncode == 0 and (tmp/"edit.png").exists()))

strip = np.zeros((80, 320, 4), np.uint8)
for i, (w, h, color) in enumerate([(24, 52, 70), (30, 48, 105), (34, 55, 140), (28, 50, 175)]):
    x0 = i * 80 + (80 - w) // 2
    strip[72-h:72, x0:x0+w] = (color, 120, 230, 255)
# Simulate a small disconnected piece of the neighboring frame bleeding into slot 03.
strip[12:17, 2*80+73:78] = (210, 90, 180, 255)
Image.fromarray(strip).save(tmp/"strip.png")
sockets = {"sockets": {"ball": [[96, 120], [40, 32], [40, 25], [40, 30]]}}
(tmp/"sockets.json").write_text(json.dumps(sockets), encoding="utf-8")
r = subprocess.run([
    "python3", f"{S}/normalize_sprite_strip.py", "--input", str(tmp/"strip.png"),
    "--out-dir", str(tmp/"norm"), "--frames", "4", "--frame-width", "96",
    "--frame-height", "96", "--anchor", str(tmp/"seed.png"), "--lock-frame1",
    "--resample", "nearest", "--socket-map", str(tmp/"sockets.json"),
    "--component-min-ratio", "0.02"
], capture_output=True)
norm_ok = r.returncode == 0 and (tmp/"norm/sprite-meta.json").exists()
if norm_ok:
    heights = []
    for frame in sorted((tmp/"norm").glob("[0-9][0-9].png")):
        alpha = np.array(Image.open(frame).convert("RGBA").getchannel("A")) > 8
        box = Image.fromarray((alpha * 255).astype(np.uint8)).getbbox()
        heights.append(0 if box is None else box[3] - box[1])
        _, components = ndimage.label(alpha)
        norm_ok = norm_ok and components == 1
    norm_ok = norm_ok and min(heights) >= 60 and max(heights) - min(heights) <= 16
res.append(("normalize_sprite_strip 跨分辨率Seed归一化+socket", norm_ok))
r = subprocess.run([
    "python3", f"{S}/render_sprite_preview_sheet.py", "--frames-dir", str(tmp/"norm"),
    "--meta", str(tmp/"norm/sprite-meta.json"), "--out", str(tmp/"sprite-preview.png")
], capture_output=True)
res.append(("render_sprite_preview_sheet 锚点预览", r.returncode == 0 and (tmp/"sprite-preview.png").exists()))
r = subprocess.run([
    "python3", f"{S}/audit_sprite_frames.py", "--frames-dir", str(tmp/"norm"),
    "--expected", "4", "--meta", str(tmp/"norm/sprite-meta.json"),
    "--anchor", str(tmp/"seed.png"), "--min-distinct", "3"
], capture_output=True)
res.append(("audit_sprite_frames 帧硬门", r.returncode == 0))

for n, p in res:
    print(("OK__" if p else "BAD__") + n)
PYEOF
)
while IFS= read -r line; do
  case "$line" in OK__*) ok "${line#OK__}";; BAD__*) bad "${line#BAD__}";; esac
done <<< "$B_RES"
B_COUNT=$(printf '%s\n' "$B_RES" | grep -c "__")
[ "$B_COUNT" -ge 11 ] || bad "工具冒烟段异常中断（仅 $B_COUNT/11 项有结果，python 可能有未捕获异常）"

if node scripts/run_bot_guard.js --timeout-ms 1000 -- node -e 'process.exit(0)' >/dev/null 2>&1; then
  ok "run_bot_guard 保留成功退出码"
else
  bad "run_bot_guard 成功命令异常"
fi
GUARD_OUT=$(node scripts/run_bot_guard.js --timeout-ms 250 -- node -e 'setInterval(()=>{},1000)' 2>&1)
GUARD_RC=$?
if [ "$GUARD_RC" = 124 ] && printf '%s' "$GUARD_OUT" | grep -q "BOT_TIMEOUT"; then
  ok "run_bot_guard 250ms 截断死循环"
else
  bad "run_bot_guard 未快速截断（rc=$GUARD_RC）"
fi

if node scripts/cdp_shot.js --self-test 2>&1 | grep -q "PASS"; then
  ok "cdp_shot 严格布尔就绪判定"
else
  bad "cdp_shot 严格就绪自检失败"
fi

echo "== C. 文档断链检查 =="
C_RES=$(python3 - <<'PYEOF'
import re
from pathlib import Path
broken = []
files = [Path("SKILL.md")] + sorted(Path("references").glob("*.md"))
for f in files:
    text = f.read_text(encoding="utf-8")
    for m in re.finditer(r"\]\(([^)\s]+)\)", text):
        link = m.group(1).split("#")[0]
        if not link or link.startswith(("http://", "https://")): continue
        if not (f.parent / link).resolve().exists():
            broken.append(f"{f}: 断链 {link}")
    for m in re.finditer(r"scripts/[A-Za-z0-9_]+\.(?:py|js|sh)", text):
        if not Path(m.group(0)).exists():
            broken.append(f"{f}: 脚本不存在 {m.group(0)}")
if broken:
    print("BAD__" + "；".join(broken[:5]) + (f" 等 {len(broken)} 处" if len(broken) > 5 else ""))
else:
    print("OK__文档引用零断链（SKILL.md + references/）")
PYEOF
)
case "$C_RES" in OK__*) ok "${C_RES#OK__}";; *) bad "${C_RES#BAD__}";; esac

echo "== D. GDD 语义路由检查 =="
D_RES=$(python3 - <<'PYEOF'
from pathlib import Path

problems = []
docs = [Path("SKILL.md")] + sorted(Path("references").glob("*.md"))
if Path("README.md").exists():
    docs.insert(1, Path("README.md"))
scripts = sorted(Path("scripts").glob("*.js")) + sorted(Path("scripts").glob("*.py"))
texts = {p: p.read_text(encoding="utf-8") for p in docs + scripts}

forbidden = {
    "references/gdd.md": "旧通用 gdd 路径",
    "game-patterns.md": "旧平台实现文件名",
    "bot_harness.js": "旧通用机器人名",
    "make_ff_pages.py": "旧通用快进名",
    "GDD 第 5 步": "旧五步 GDD 引用",
    "new-type.md 的消消乐范例": "已删除的新类型示例",
    "idle/move/action/hurt/win/lose": "把候选状态当默认动作清单",
    "待机 + 接取/持有/蓄力/发射/受击等必要动作": "固定的驱动者动作清单",
    "2D 模板：主角 + 跑步帧": "把平台跳跃素材契约误当全部 2D 模板默认清单",
}
for p, text in texts.items():
    for token, label in forbidden.items():
        if token in text:
            problems.append(f"{p}: {label} {token}")

for p in [Path("references/platformer-2d.md"), Path("references/runner-3d.md"),
          Path("references/match3.md"), Path("references/doodle-jump.md")]:
    if "八模块覆盖映射" not in texts[p]:
        problems.append(f"{p}: 缺八模块覆盖映射")

required = {
    Path("references/gdd-strategy.md"): ["GDD.md", "ASSET_LEDGER.md", "### 8.", "动画决策表", "四道必要性门",
                                        "M / S / P", "生产白名单", "Sprite Contract", "交互 socket"],
    Path("references/assets.md"): ["阶段 A：GDD 设计参考", "阶段 B：素材生产与验收",
                                    "动画决策表", "生产白名单", "四道必要性门", "Seed Frame 批准门", "build_sprite_edit_canvas.py",
                                    "normalize_sprite_strip.py", "render_sprite_preview_sheet.py",
                                    "audit_sprite_frames.py"],
    Path("references/ui-kit.md"): ["阶段 A：GDD 设计参考", "阶段 B：UI 生产、集成与验收"],
    Path("references/verification.md"): ["动作时间线证据", "audit_sprite_frames.py", "物理事件帧",
                                         "生产白名单", "冗余动作检查", "机器人时间与防卡死合同",
                                         "固定 `dt`", "scripts/run_bot_guard.js", "布尔值 `true`", "真正截图前", "简单 H5 快速验证档"],
    Path("SKILL.md"): ["## 类型注册表", "scripts/bot_platformer.js", "scripts/bot_match3.js", "scripts/bot_doodle.js", "scripts/runner_bot.js",
                       "动画最小充分集", "动画决策表", "生产白名单", "白名单动作节拍预览",
                       "简单单循环 H5", "scripts/run_bot_guard.js", "所选模板的素材接口",
                       "不得仅按“2D / 3D”", "不得为凑模板接口新增动作", "新增模板"],
}
for p, tokens in required.items():
    for token in tokens:
        if token not in texts[p]:
            problems.append(f"{p}: 缺必需语义 {token}")

if problems:
    print("BAD__" + "；".join(problems[:8]) + (f" 等 {len(problems)} 处" if len(problems) > 8 else ""))
else:
    print("OK__通用策略、类型包、生产边界与验证路由一致")
PYEOF
)
case "$D_RES" in OK__*) ok "${D_RES#OK__}";; *) bad "${D_RES#BAD__}";; esac

echo "================================"
if [ "$FAIL" = 0 ]; then echo "SELFCHECK: PASS"; else echo "SELFCHECK: FAIL（禁止推送，先修）"; fi
exit $FAIL
