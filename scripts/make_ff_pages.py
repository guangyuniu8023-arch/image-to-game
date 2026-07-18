#!/usr/bin/env python3
"""生成"同步快进"测试页：页面加载即自动开局并同步快进 N 秒游戏逻辑，
使无头浏览器截图不依赖等待时序——截图即第 N 秒的游戏画面。

用法: python3 make_ff_pages.py <index.html> <输出目录> <秒数列表，逗号分隔>
示例: python3 make_ff_pages.py index.html /tmp/fftest 6,22,29
之后: 在输出目录起 http 服务，用 chromium --headless=new --screenshot 截图。

原理: 在 </body> 前注入一段脚本，同步循环调用游戏的 update(1/60)，
      页面首帧渲染时游戏已经进行到第 N 秒。机器人操作与 bot_harness.js 相同。
"""
import os
import shutil
import sys

BOT = """
let __hold = 0;
function __gA(){const a=Math.floor((player.x+player.w+12)/TILE),f=Math.floor((player.y+player.h+8)/TILE);for(let r=f;r<ROWS;r++)if(solid(tileAt(a,r)))return true;return false}
function __wA(){const a=Math.floor((player.x+player.w+8)/TILE),t=Math.floor((player.y+8)/TILE),b=Math.floor((player.y+player.h-4)/TILE);for(let r=t;r<=b;r++)if(solid(tileAt(a,r)))return true;return false}
function __eA(){return enemies.some(e=>e.alive&&e.x>player.x&&e.x-player.x<78&&Math.abs(e.y-player.y)<70)}
function __ff(sec){
  newGame();
  for(let i=0;i<60*sec;i++){
    keys.ArrowRight = true;
    if(player.onGround && (__wA()||!__gA()||__eA())){ press.jump = true; __hold = 16; }
    keys.Space = __hold-- > 0;
    update(1/60);
  }
  keys.ArrowRight = false; keys.Space = false;
}
__ff(SEC);
"""


def main() -> None:
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    src, outdir, secs = sys.argv[1], sys.argv[2], sys.argv[3]
    html = open(src, encoding="utf-8").read()
    assert "</body>" in html, "HTML 缺少 </body> 闭合标签，无法注入快进脚本——请先补全"

    os.makedirs(outdir, exist_ok=True)
    # 复制项目全部资源（精灵图等）
    proj = os.path.dirname(os.path.abspath(src))
    for name in os.listdir(proj):
        if name == ".git" or name.startswith("ff_"):
            continue
        p = os.path.join(proj, name)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(outdir, name))

    for sec in secs.split(","):
        sec = sec.strip()
        out = html.replace("</body>", "<script>" + BOT.replace("SEC", sec) + "</scr" + "ipt>\n</body>")
        assert "__ff" in out
        with open(os.path.join(outdir, f"ff_{sec}.html"), "w", encoding="utf-8") as f:
            f.write(out)
        print(f"OK ff_{sec}.html（首帧即第 {sec} 秒画面）")


if __name__ == "__main__":
    main()
