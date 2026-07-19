#!/usr/bin/env bash
# selfcheck.sh — skill 防回退自检（每次推送 skill 改动前必跑，全绿才许推）
#
# 为什么有这个脚本：skill 自进化（变体积累/泛化/新工具）只加不改，但脚本、
# 模板、机器人会被编辑——回退只可能从这里进来。本脚本把"旧能力还活着"
# 变成一条命令：机器人回归（模板+参考项目）+ 工具合成夹具冒烟 + 文档断链检查。
# 参考项目（match3/doodlejump 等无模板的类型）默认取仓库同级目录，缺失则 SKIP 不判负。
set -u
cd "$(dirname "$0")/.."
FAIL=0
ok()   { echo "  ✓ $1"; }
bad()  { echo "  ✗ $1"; FAIL=1; }
skip() { echo "  - $1（SKIP）"; }

echo "== A. 机器人回归（类型能力硬门槛）=="
if node scripts/bot_harness.js templates/platformer-2d/index.html 2>&1 | grep -q "WIN: true"; then
  ok "platformer-2d 模板 bot WIN"
else bad "platformer-2d 模板 bot 未通关"; fi

for proj in ../match3 ../match3-timed ../doodlejump; do
  name=$(basename "$proj")
  if [ ! -f "$proj/index.html" ]; then skip "$name（参考项目不在同级，未检）"; continue; fi
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

if node scripts/runner_bot.js templates/runner-3d/index.html 120 >/dev/null 2>&1; then
  ok "runner-3d 模板 bot 存活"
else bad "runner-3d 模板 bot 失败"; fi

echo "== B. 工具冒烟（合成夹具，即造即测）=="
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
B_RES=$(python3 - "$TMP" <<'PYEOF'
import sys, subprocess
from pathlib import Path
import numpy as np
from PIL import Image

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

for n, p in res:
    print(("OK__" if p else "BAD__") + n)
PYEOF
)
while IFS= read -r line; do
  case "$line" in OK__*) ok "${line#OK__}";; BAD__*) bad "${line#BAD__}";; esac
done <<< "$B_RES"
B_COUNT=$(printf '%s\n' "$B_RES" | grep -c "__")
[ "$B_COUNT" -ge 7 ] || bad "工具冒烟段异常中断（仅 $B_COUNT/7 项有结果，python 可能有未捕获异常）"

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

echo "================================"
if [ "$FAIL" = 0 ]; then echo "SELFCHECK: PASS"; else echo "SELFCHECK: FAIL（禁止推送，先修）"; fi
exit $FAIL
