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

echo "== A. 旧类型 bot 补充回归（不作为 GAME_READY 主证据）=="
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
python3 scripts/scaffold_gameplay_contract.py --self-test >/dev/null 2>&1 \
  && ok "gameplay contract 脚手架" || bad "gameplay contract 脚手架失败"
node scripts/run_bot_guard.js --timeout-ms 15000 -- node scripts/run_gameplay_runtime.js --self-test >/dev/null 2>&1 \
  && ok "通用 Chromium gameplay runner" || bad "通用 Chromium gameplay runner 失败"
python3 scripts/audit_pipeline_stage.py --self-test >/dev/null 2>&1 \
  && ok "pipeline 诊断 + 稳定失败签名" || bad "pipeline 诊断失败"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
if [ -d templates ]; then
  for template in platformer-2d runner-3d; do
    if python3 scripts/audit_gameplay_report.py --project "templates/$template" --contract-only >/dev/null 2>&1 \
        && python3 scripts/audit_visual_contract.py --project "templates/$template" >/dev/null 2>&1; then
      ok "$template 模板标准合同"
    else
      bad "$template 模板缺标准合同"
    fi
  done
fi
B_RES=$(python3 - "$TMP" <<'PYEOF'
import sys, subprocess, json, hashlib, shutil
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

# Sprite 流水线：Seed → 整条 → 共享缩放/root → socket preview → 诊断
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

# Requirement-derived visual contract + reference-character gate.
gate = tmp / "character-gate"
(gate / "input").mkdir(parents=True)
(gate / "assets").mkdir()
(gate / "evidence").mkdir()
(gate / "sprites/jump/frames").mkdir(parents=True)
for rel in ["input/character.png", "assets/seed.png", "evidence/visual-seed-charge.png",
            "evidence/action-beats.png", "assets/jump-strip.png",
            "sprites/jump/meta.json", "sprites/jump/preview.png",
            "sprites/jump/frames/01.png"]:
    (gate / rel).write_bytes(b"fixture")
(gate / "index.html").write_text("<!doctype html><title>fixture</title>", encoding="utf-8")
contract = {
    "version": 1, "source": "requirement-analysis",
    "viewport": {"width": 400, "height": 700},
    "reasoning": {
        "player_decision": "judge distance to the next target",
        "must_see": ["player", "target"],
        "reference_sensitive_states": ["charging"],
        "retarget_events": ["landed"]
    },
    "entities": {
        "player": {"role": "primary", "space": "world", "measurement": "visible-pixels", "min_visible_height_px": 80},
        "target": {"role": "decision-target", "space": "world", "measurement": "geometry"}
    },
    "policy": {
        "framing_subjects": ["player", "target"], "lock_states": ["charging"],
        "retarget_on": ["landed"], "settle_before_states": ["charging"],
        "rationale": "precision input needs a stable reference, then landing changes the target"
    },
    "cases": [
        {"name": "boot", "entry": "natural", "state": "ready", "behavior": "static",
         "required_visible": ["player"], "required_render_sources": {
             "player": {"seed": ["generated-seed"], "production": ["generated-seed"]}
         }, "max_frames": 1},
        {"name": "charge", "entry": "scripted", "state": "charging", "behavior": "locked",
         "required_visible": ["player", "target"], "required_render_sources": {
             "player": {"seed": ["generated-seed", "generated-sprite"],
                        "production": ["generated-seed", "generated-sprite"]}
         }, "max_frames": 4},
        {"name": "settle", "entry": "scripted", "state": "settled", "behavior": "transition",
         "before_state": "ready", "trigger_event": "landed",
         "transition_mode": "smooth", "transition_rationale": "preserve spatial continuity",
         "min_transition_samples": 3,
         "min_target_delta_px": 8, "min_camera_delta_px": 8,
         "required_target_axes": ["y"], "min_axis_target_delta_px": 8,
         "required_visible": ["player", "target"], "required_render_sources": {
             "player": {"seed": ["generated-seed", "generated-sprite"],
                        "production": ["generated-seed", "generated-sprite"]}
         }, "max_frames": 12}
    ],
    "baseline": {"primary_entity": "player", "capture_cases": ["charge"],
                 "max_primary_area_delta_ratio": 0.2, "max_group_area_delta_ratio": 0.2},
    "artifacts": ["index.html", "assets/seed.png"],
    "approval_artifacts": ["assets/seed.png"]
}
cp = gate / "VISUAL_CONTRACT.json"
cp.write_text(json.dumps(contract), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_visual_contract.py", "--project", str(gate)], capture_output=True)
res.append(("visual contract 需求推导合同→PASS", r.returncode == 0))
# Visual validation must not infer launch-page product policy from project state names.
# The default no-cover/no-title behavior belongs to Skill/GDD and explicit user
# overrides remain valid contracts.
contract["cases"][0]["state"] = "title"
cp.write_text(json.dumps(contract), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_visual_contract.py", "--project", str(gate)], capture_output=True)
res.append(("visual contract 不按启动状态名裁决产品策略→PASS", r.returncode == 0))
contract["cases"][0]["state"] = "ready"
contract["game_type_route"] = {"jump": "target-group"}
cp.write_text(json.dumps(contract), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_visual_contract.py", "--project", str(gate)], capture_output=True)
res.append(("visual contract 类型路由字段→FAIL", r.returncode != 0))
contract.pop("game_type_route")
cp.write_text(json.dumps(contract), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_visual_contract.py", "--project", str(gate)], capture_output=True)
res.append(("visual contract world/HUD空间+viewport→PASS", r.returncode == 0))
saved_viewport = contract.pop("viewport")
cp.write_text(json.dumps(contract), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_visual_contract.py", "--project", str(gate)], capture_output=True)
res.append(("visual contract 缺目标viewport→FAIL", r.returncode != 0))
contract["viewport"] = saved_viewport
saved_space = contract["entities"]["player"].pop("space")
cp.write_text(json.dumps(contract), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_visual_contract.py", "--project", str(gate)], capture_output=True)
res.append(("visual contract 缺实体space→FAIL", r.returncode != 0))
contract["entities"]["player"]["space"] = saved_space
cp.write_text(json.dumps(contract), encoding="utf-8")
saved_boot = contract["cases"].pop(0)
cp.write_text(json.dumps(contract), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_visual_contract.py", "--project", str(gate)], capture_output=True)
res.append(("visual contract 缺自然自动开局case→FAIL", r.returncode != 0))
contract["cases"].insert(0, saved_boot)
saved_axis = contract["cases"][2].pop("required_target_axes")
cp.write_text(json.dumps(contract), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_visual_contract.py", "--project", str(gate)], capture_output=True)
res.append(("visual contract 镜头过渡缺目标轴→FAIL", r.returncode != 0))
contract["cases"][2]["required_target_axes"] = saved_axis
saved_transition_mode = contract["cases"][2].pop("transition_mode")
cp.write_text(json.dumps(contract), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_visual_contract.py", "--project", str(gate)], capture_output=True)
res.append(("visual contract 缺过渡形态→FAIL", r.returncode != 0))
contract["cases"][2]["transition_mode"] = saved_transition_mode
saved_sources = contract["cases"][1]["required_render_sources"]["player"]["production"]
contract["cases"][1]["required_render_sources"]["player"]["production"] = ["fallback"]
cp.write_text(json.dumps(contract), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_visual_contract.py", "--project", str(gate)], capture_output=True)
res.append(("visual contract 正式主角回退渲染→FAIL", r.returncode != 0))
contract["cases"][1]["required_render_sources"]["player"]["production"] = saved_sources
cp.write_text(json.dumps(contract), encoding="utf-8")

digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = {
    "version": 2, "reference_character": True, "role": "A",
    "user_requested_code_only": False,
    "formal_visual_method": "reference-image-generation",
    "reference_images": ["input/character.png"],
    "generator": {"tool": "image_generation_tool.py", "reference_used": True},
    "seed": {
        "frame": "assets/seed.png", "composition_preview": "evidence/visual-seed-charge.png",
        "action_beat_preview": "evidence/action-beats.png",
        "action_beat_preview_method": "diagram-from-seed"
    },
    "planned_actions": [{"name": "jump", "role": "M", "beats": ["start", "air", "land"]}],
    "actions": []
}
mp = gate / "CHARACTER_PRODUCTION.json"
mp.write_text(json.dumps(manifest), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_character_production.py", "--project", str(gate),
                    "--phase", "draft"], capture_output=True)
res.append(("character record 生图前Draft→PASS", r.returncode == 0))
r = subprocess.run(["python3", f"{S}/audit_character_production.py", "--project", str(gate),
                    "--phase", "seed"], capture_output=True)
res.append(("character record Seed产物→PASS", r.returncode == 0))
manifest["formal_visual_method"] = "canvas"
mp.write_text(json.dumps(manifest), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_character_production.py", "--project", str(gate),
                    "--phase", "seed"], capture_output=True)
res.append(("character record Canvas正式主角→FAIL", r.returncode != 0))
manifest["formal_visual_method"] = "reference-image-generation"
mp.write_text(json.dumps(manifest), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_character_production.py", "--project", str(gate),
                    "--phase", "production"], capture_output=True)
res.append(("character record 白名单动作缺产物→FAIL", r.returncode != 0))
manifest["actions"] = [{
    "name": "jump", "strip": "assets/jump-strip.png",
    "frames_dir": "sprites/jump/frames", "meta": "sprites/jump/meta.json",
    "preview": "sprites/jump/preview.png"
}]
mp.write_text(json.dumps(manifest), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_character_production.py", "--project", str(gate),
                    "--phase", "production"], capture_output=True)
res.append(("character record Sprite全链产物→PASS", r.returncode == 0))
saved_preview = manifest["actions"][0].pop("preview")
mp.write_text(json.dumps(manifest), encoding="utf-8")
r = subprocess.run(["python3", f"{S}/audit_character_production.py", "--project", str(gate),
                    "--phase", "production"], capture_output=True)
res.append(("character record Sprite缺预览→FAIL", r.returncode != 0))
manifest["actions"][0]["preview"] = saved_preview
mp.write_text(json.dumps(manifest), encoding="utf-8")

# Real-browser fixture is consumed below when Chromium is available (Pi image has it).
runtime = tmp / "runtime-visual"
(runtime / "assets").mkdir(parents=True)
Image.new("RGBA", (80, 120), (220, 90, 120, 255)).save(runtime / "assets/seed.png")
runtime_contract = json.loads(json.dumps(contract))
(runtime / "VISUAL_CONTRACT.json").write_text(json.dumps(runtime_contract), encoding="utf-8")
(runtime / "index.html").write_text(r'''<!doctype html><html><body style="margin:0">
<canvas id="game" width="400" height="700"></canvas><script>
const canvas=document.getElementById('game'),ctx=canvas.getContext('2d');
function draw(){ctx.fillStyle='#102044';ctx.fillRect(0,0,400,700);ctx.fillStyle='#f26f8f';ctx.fillRect(80,400,80,100);ctx.fillStyle='#86c98a';ctx.fillRect(220,380,100,80);}
function sample(x,targetX,state,y=0,targetY=0,source='generated-sprite'){return {state,viewport:{width:400,height:700},camera:{x,y,zoom:1,targetX,targetY,targetZoom:1},entities:{player:{basis:'visible-pixels',render_source:source,bounds:{x:80,y:400,width:80,height:100}},target:{basis:'geometry',bounds:{x:220,y:380,width:100,height:80}}},hud:[{bounds:{x:0,y:0,width:400,height:60}}]};}
draw();window.__game={ready:true,visualAudit:{snapshot(){return {samples:[sample(0,0,'ready',0,0,'generated-seed')]};},runCase(name){draw();if(name==='charge')return {samples:[sample(100,100,'charging',0,0,'generated-seed'),sample(100,100,'charging',0,0,'generated-seed')]};if(name==='settle')return {events:['landed'],before:sample(0,0,'ready',0,0,'generated-seed'),samples:[sample(5,20,'ready',8,20,'generated-seed'),sample(12,20,'ready',15,20,'generated-seed'),sample(20,20,'settled',20,20,'generated-seed')]};throw new Error('unknown case');}}};
</script></body></html>''', encoding="utf-8")
(runtime / "evidence").mkdir()
(runtime / "evidence/retry-audit.json").write_text(json.dumps({
    "version": 1, "run_id": "retry-budget", "phase": "seed", "status": "FAIL", "attempt": 2,
    "contract_sha256": digest(runtime / "VISUAL_CONTRACT.json"), "problems": ["fixture"]
}), encoding="utf-8")

broken = tmp / "runtime-broken"
shutil.copytree(runtime, broken)
(broken / "index.html").write_text(
    "<!doctype html><script>throw new TypeError('fixture boot failure')</script>",
    encoding="utf-8",
)

snapped = tmp / "runtime-snapped"
shutil.copytree(runtime, snapped)
snap_source = (snapped / "index.html").read_text(encoding="utf-8")
snapped_source = snap_source.replace(
    "samples:[sample(5,20,'ready',8,20,'generated-seed'),sample(12,20,'ready',15,20,'generated-seed'),sample(20,20,'settled',20,20,'generated-seed')]",
    "samples:[sample(20,20,'settled',20,20,'generated-seed'),sample(20,20,'settled',20,20,'generated-seed'),sample(20,20,'settled',20,20,'generated-seed')]",
)
if snapped_source == snap_source:
    raise RuntimeError("snapped-camera fixture replacement did not match")
(snapped / "index.html").write_text(snapped_source, encoding="utf-8")

for n, p in res:
    print(("OK__" if p else "BAD__") + n)
PYEOF
)
while IFS= read -r line; do
  case "$line" in OK__*) ok "${line#OK__}";; BAD__*) bad "${line#BAD__}";; esac
done <<< "$B_RES"
B_COUNT=$(printf '%s\n' "$B_RES" | grep -c "__")
[ "$B_COUNT" -ge 22 ] || bad "工具冒烟段异常中断（仅 $B_COUNT/22 项有结果，python 可能有未捕获异常）"

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
if node scripts/audit_visual_runtime.js --self-test 2>&1 | grep -q "PASS"; then
  ok "audit_visual_runtime 自然启动/渲染源/真实镜头位移/基线夹具"
else
  bad "audit_visual_runtime 自检失败"
fi
if python3 scripts/audit_gameplay_report.py --self-test 2>&1 | grep -q "PASS"; then
  ok "audit_gameplay_report 单侧通过/多侧漏测拒绝/边界证据夹具"
else
  bad "audit_gameplay_report 自检失败"
fi
if python3 scripts/audit_delivery_bundle.py --self-test 2>&1 | grep -q "PASS"; then
  ok "audit_delivery_bundle build-id/Sprite/哈希夹具"
else
  bad "audit_delivery_bundle 自检失败"
fi
cp -R "$TMP/runtime-visual" "$TMP/runtime-retry"
RETRY_OUT=$(node scripts/audit_visual_runtime.js --project "$TMP/runtime-retry" --phase seed \
  --run-id retry-budget --out "$TMP/runtime-retry/evidence/retry-audit.json" 2>&1)
RETRY_RC=$?
if [ "$RETRY_RC" != 0 ] && printf '%s' "$RETRY_OUT" | grep -q "second-attempt report is terminal"; then
  ok "audit_visual_runtime 第3次不预约且保留第2次详细报告"
else
  bad "audit_visual_runtime 重试次数门失败（rc=${RETRY_RC}）"
fi

if command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1 \
    || [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ] \
    || [ -x "/Applications/Chromium.app/Contents/MacOS/Chromium" ]; then
  BROKEN_OUT=$(node scripts/run_bot_guard.js --timeout-ms 10000 -- \
      node scripts/audit_visual_runtime.js --project "$TMP/runtime-broken" --phase seed \
      --run-id broken-runtime --out "$TMP/runtime-broken/evidence/visual-seed-audit.json" 2>&1)
  BROKEN_RC=$?
  if [ "$BROKEN_RC" != 0 ] && printf '%s' "$BROKEN_OUT" | grep -q "page exception before visualAudit ready" \
      && printf '%s' "$BROKEN_OUT" | grep -q "fixture boot failure"; then
    ok "audit_visual_runtime 透传 ready 前页面异常"
  else
    bad "audit_visual_runtime 页面异常诊断失败（rc=$BROKEN_RC）"
  fi
  if node scripts/run_bot_guard.js --timeout-ms 10000 -- \
      node scripts/audit_visual_runtime.js --project "$TMP/runtime-visual" --phase seed \
      --run-id visual-runtime --out "$TMP/runtime-visual/evidence/visual-seed-audit.json" >/dev/null 2>&1; then
    ok "audit_visual_runtime 真实 Chromium Seed 门"
  else
    bad "audit_visual_runtime 真实 Chromium Seed 门失败"
  fi
  SNAPPED_OUT=$(node scripts/run_bot_guard.js --timeout-ms 10000 -- \
      node scripts/audit_visual_runtime.js --project "$TMP/runtime-snapped" --phase seed \
      --run-id snapped-runtime --out "$TMP/runtime-snapped/evidence/visual-seed-audit.json" 2>&1)
  SNAPPED_RC=$?
  if [ "$SNAPPED_RC" != 0 ] && printf '%s' "$SNAPPED_OUT" | grep -q "already settled"; then
    ok "audit_visual_runtime 真实 Chromium 拒绝用瞬移伪装平滑跟随"
  else
    bad "audit_visual_runtime 平滑跟随反瞬移门失败（rc=$SNAPPED_RC）"
  fi
  if node scripts/run_bot_guard.js --timeout-ms 10000 -- \
      node scripts/audit_visual_runtime.js --project "$TMP/runtime-visual" --phase production \
      --run-id visual-runtime \
      --baseline "$TMP/runtime-visual/evidence/visual-baseline.json" \
      --out "$TMP/runtime-visual/evidence/visual-production-audit.json" >/dev/null 2>&1; then
    ok "audit_visual_runtime 真实 Chromium Production/基线门"
  else
    bad "audit_visual_runtime 真实 Chromium Production/基线门失败"
  fi
  rm -f "$TMP/runtime-visual/evidence/visual-baseline.json"
  if node scripts/run_bot_guard.js --timeout-ms 10000 -- \
      node scripts/audit_visual_runtime.js --project "$TMP/runtime-visual" --phase production \
      --run-id visual-runtime \
      --out "$TMP/runtime-visual/evidence/visual-production-no-baseline.json" >/dev/null 2>&1; then
    ok "audit_visual_runtime Production 无基线单线运行"
  else
    bad "audit_visual_runtime Production 无基线被误阻断"
  fi
  if [ -d templates ]; then
    for template in platformer-2d runner-3d; do
      target="$TMP/template-runtime-$template"
      cp -R "templates/$template" "$target"
      mkdir -p "$target/evidence"
      if node scripts/run_bot_guard.js --timeout-ms 15000 -- \
          node scripts/run_gameplay_runtime.js --project "$target" \
          --out "$target/evidence/gameplay-audit.json" >/dev/null 2>&1 \
          && node scripts/run_bot_guard.js --timeout-ms 15000 -- \
          node scripts/audit_visual_runtime.js --project "$target" --phase production \
          --run-id "template-$template" \
          --out "$target/evidence/visual-production-audit.json" >/dev/null 2>&1; then
        ok "$template 模板真实 Chromium 玩法/视觉合同"
      else
        bad "$template 模板真实 Chromium 合同失败"
      fi
    done
  fi
else
  skip "Chromium 不在宿主 PATH，真实浏览器门留给 Pi 容器回归"
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
    "remove_bg.py 抠图（不用 AI 生成，保真）": "跳过 reference Seedream 主角生成",
    "程序化 IP 特征复刻和卡通渲染": "把程序化角色冒充正式 A/B 主角",
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
                                        "M / S / P", "生产白名单", "Sprite Contract", "交互 socket",
                                        "VISUAL_CONTRACT.json", "GAMEPLAY_CONTRACT.json", "visual-framing.md",
                                        "window.__game.visualAudit.snapshot", "window.__game.visualAudit.runCase",
                                        "window.__game.gameplayAudit.reset/step/snapshot", "输入可达性",
                                        "FAIL_SHORT", "不得直接赋值结果或终态"],
    Path("references/assets.md"): ["阶段 A：GDD 设计参考", "阶段 B：素材生产与验收",
                                    "动画决策表", "生产白名单", "四道必要性门", "Seed Frame 生成与可选确认", "build_sprite_edit_canvas.py",
                                    "normalize_sprite_strip.py", "render_sprite_preview_sheet.py",
                                    "audit_sprite_frames.py", "参考角色正式素材规则", "CHARACTER_PRODUCTION.json",
                                    "scripts/audit_character_production.py", "visual-framing.md", "audit_visual_runtime.js",
                                    "不是调用图片工具的前置许可证", "禁止因此拆成逐帧请求", "不得删除或拒绝交付",
                                    "首版动画预算", "动作 strip 默认使用工具的 1K 档",
                                    "在调用生图工具生成动作条之前", "--lock-frame1",
                                    "不得先写一个未来路径"],
    Path("references/visual-framing.md"): ["不提供“游戏类型 → 镜头类型”的选择表", "玩家的视觉决策",
                                            "组合式策略", "VISUAL_CONTRACT.json", "requirement-analysis",
                                            "window.__game.visualAudit", "visible-pixels", "运行时直接截图",
                                            "audit_visual_contract.py", "audit_visual_runtime.js",
                                            "限时视觉诊断", "space: \"world\" | \"hud\"",
                                            "viewport.width/height", "当前审计 phase 真实存在",
                                            "JavaScript 异常", "entry: \"natural\"",
                                            "required_render_sources", "min_target_delta_px", "result.before",
                                            "transition_mode", "min_transition_samples", "返回当前 HTML"],
    Path("references/ui-kit.md"): ["阶段 A：GDD 设计参考", "阶段 B：UI 生产、集成与验收"],
    Path("references/verification.md"): ["动作时间线证据", "audit_sprite_frames.py", "物理事件帧",
                                         "固定 `dt`", "scripts/run_bot_guard.js", "启动界面策略不作为",
                                         "CHARACTER_PRODUCTION.json", "scripts/audit_character_production.py",
                                         "VISUAL_CONTRACT.json", "audit_visual_runtime.js", "VLM 或人工只负责观感",
                                         "一次定向修复和一次复测", "禁止连续创建多个 `dbg*.js`",
                                         "GAMEPLAY_CONTRACT.json", "audit_gameplay_report.py",
                                         "DELIVERY_MANIFEST.json", "game-build", "GAME_READY", "GAME_CANDIDATE", "INCOMPLETE",
                                         "window.__game.ready === true", "首次生图前用", "run_gameplay_runtime.js",
                                         "window.__game.gameplayAudit.reset(seed, setup)", "禁止用 Node VM",
                                         "FAIL_SHORT", "actual, seed, dt, inputs, trace, terminal, assertions",
                                         "查表直接返回 expected", "--run-id", "仅蓄力无方向输入"],
    Path("SKILL.md"): ["## 类型注册表", "scripts/bot_platformer.js", "scripts/bot_match3.js", "scripts/bot_doodle.js", "scripts/runner_bot.js",
                       "GDD 先于素材", "单线生成，候选必交付", "动画最小充分集",
                       "scripts/run_bot_guard.js", "GAME_READY", "GAME_CANDIDATE", "INCOMPLETE",
                       "参考角色必须实际调用生图工具", "CHARACTER_PRODUCTION.json", "不是调用 Seedream 的前置许可证",
                       "镜头由需求推导", "默认不生成封面资产", "连续游玩后的真实镜头移动",
                       "build_sprite_edit_canvas.py", "normalize_sprite_strip.py", "render_sprite_preview_sheet.py",
                       "GDD.md", "ASSET_LEDGER.md", "GAMEPLAY_CONTRACT.json", "VISUAL_CONTRACT.json",
                       "审计是诊断，不是生产授权", "超时、工具失败或审计失败时保留工作区",
                       "GDD 写完后的第一个实现检查点", "window.__game.ready", "targetX/targetY/targetZoom",
                       "scripts/run_gameplay_runtime.js", "gameplayAudit.reset/step/snapshot", "假 `Image`",
                       "正式输入可达", "--lock-frame1", "不能都用 `OVER` 冒充"],
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
