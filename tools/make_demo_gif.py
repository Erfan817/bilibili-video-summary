#!/usr/bin/env python3
"""把一段 CLI 会话文本渲染成终端风格的 GIF, 用作 README 顶部动图。

为什么用脚本而不是录屏: 可复现、体积小、改文案重跑即可, 也不用装录屏工具。

用法:
    python tools/make_demo_gif.py                     # 用内置示例会话
    python tools/make_demo_gif.py session.txt -o assets/demo.gif
    python tools/make_demo_gif.py --cols 92 --font-size 15

依赖: Pillow(已随项目安装)。
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# 终端配色(接近 Windows Terminal 的 Campbell)
BG = (12, 12, 12)
BAR = (38, 38, 38)
FG = (204, 204, 204)
GREEN = (19, 161, 14)
CYAN = (58, 150, 221)
YELLOW = (193, 156, 0)
GREY = (118, 118, 118)
CURSOR = (220, 220, 220)

DEFAULT_SESSION = """\
$ bvs BV1PE411h7b4 --topic "传销 骗局 心理学" --srt

title : 真正的传销到底有多可怕，测试一下你能坚持多久
bvid  : BV1PE411h7b4  p=1  cid=126052143  dur=244s
owner : 无际视频
下载音频流: id=30216 bw=49666 ...
loading model: D:\\.workbuddy\\models\\faster-whisper-small ...
model ready in 1.3s
  seg 20 @ 00:00:48
  seg 40 @ 00:01:24
  seg 60 @ 00:01:54
DONE segments=96 audio=243.6s elapsed=33.3s

完成 -> ./outputs/真正的传销到底有多可怕，测试一下你能坚持多久
  transcript.txt + transcript.srt
  summary.md / summary.json
  同音字校正: 0 行自动替换, 0 行待审查(见 summary.md)
"""


def _color_for(line):
    s = line.strip()
    if s.startswith('$'):
        return GREEN
    if s.startswith(('title', 'bvid', 'owner')):
        return CYAN
    if s.startswith(('下载', 'loading', '  seg', 'DONE')):
        return GREY
    if s.startswith(('完成', '  transcript', '  summary', '  frames')):
        return YELLOW
    return FG


def _load_font(size):
    """优先找带中文字形的等宽/黑体字体。"""
    cands = [
        r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\msyh.ttf',
        r'C:\Windows\Fonts\simsun.ttc',
        '/System/Library/Fonts/PingFang.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
    ]
    for c in cands:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render(session, out, cols=86, font_size=15, hold_frames=18,
           frames_per_line=2, title='bvs — B 站视频一键转写'):
    lines = [l.rstrip() for l in session.splitlines()]
    font = _load_font(font_size)
    cw = font_size * 0.62          # 等宽近似字宽
    lh = int(font_size * 1.55)     # 行高
    pad = 14
    bar_h = 30
    width = int(cw * cols) + pad * 2
    height = bar_h + pad * 2 + lh * (len(lines) + 1)

    def draw_frame(visible, cursor_on):
        img = Image.new('RGB', (width, height), BG)
        d = ImageDraw.Draw(img)
        # 标题栏 + 三个圆点
        d.rectangle([0, 0, width, bar_h], fill=BAR)
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            cx = 16 + i * 18
            d.ellipse([cx - 5, bar_h // 2 - 5, cx + 5, bar_h // 2 + 5], fill=c)
        d.text((72, bar_h // 2 - font_size // 2), title, font=font, fill=GREY)

        y = bar_h + pad
        for i, line in enumerate(lines[:visible]):
            # 标题行和命令行加粗感: 用亮一点的色 + 前缀
            d.text((pad, y), line[:cols], font=font, fill=_color_for(line))
            y += lh
        # 光标
        if cursor_on and visible <= len(lines):
            cy = bar_h + pad + lh * min(visible, len(lines) - 1) if visible else bar_h + pad
            cx = pad
            if visible:
                cx = pad + int(cw * len(lines[visible - 1][:cols]))
                cy = bar_h + pad + lh * (visible - 1)
            d.rectangle([cx, cy + 2, cx + max(6, int(cw * 0.6)), cy + lh - 3],
                        fill=CURSOR)
        return img

    frames = []
    # 逐行揭示
    for n in range(0, len(lines) + 1):
        for k in range(frames_per_line):
            frames.append(draw_frame(n, cursor_on=(k % 2 == 0)))
    # 结尾停留(光标闪烁)
    for k in range(hold_frames):
        frames.append(draw_frame(len(lines), cursor_on=(k % 2 == 0)))

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=180, loop=0, optimize=True)
    return out, len(frames), os.path.getsize(out)


def main(argv=None):
    p = argparse.ArgumentParser(description='把 CLI 会话渲染成终端 GIF')
    p.add_argument('session', nargs='?', help='会话文本文件(缺省用内置示例)')
    p.add_argument('-o', '--out', default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'assets', 'demo.gif'))
    p.add_argument('--cols', type=int, default=86)
    p.add_argument('--font-size', type=int, default=15)
    args = p.parse_args(argv)

    if args.session:
        with open(args.session, encoding='utf-8') as f:
            session = f.read()
    else:
        session = DEFAULT_SESSION

    out, n, size = render(session, args.out, args.cols, args.font_size)
    print('wrote %s  frames=%d  %.0f KB' % (out, n, size / 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
