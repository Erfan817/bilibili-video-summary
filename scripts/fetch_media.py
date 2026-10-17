"""下载 B 站音视频流(技能脚本, 薄封装 bvs_core)。

用法(与 SKILL.md 保持一致):
    python fetch_media.py <工作目录>            # 音频 + 视频都下
    python fetch_media.py <工作目录> audio      # 只下音频
    python fetch_media.py <工作目录> video      # 只下视频

约定:
  * 音频取 id=30216(最小码率, ASR 够用), 取不到就按 bandwidth 挑最小的
  * 视频挑 avc1(H.264) 里带宽最小的 —— HEVC 体积更小但解码兼容性差
  * 工作目录里需要有 playurl.json
  * 可选环境变量 BILI_COOKIE 注入 cookie(解锁高清流)
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bvs_core import bili


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    base = os.path.abspath(argv[0] if argv else '.')
    what = argv[1] if len(argv) > 1 else 'both'
    cookie = bili.load_cookie(os.environ.get('BILI_COOKIE'))

    with io.open(os.path.join(base, 'playurl.json'), encoding='utf-8-sig') as f:
        dash = json.load(f)['data']['dash']

    if what in ('audio', 'both'):
        if not dash.get('audio'):
            print('no audio stream')
            return 1
        t = bili.pick_audio(dash['audio'])
        p = os.path.join(base, 'audio.m4s')
        if not os.path.exists(p):
            n = bili.download(t['baseUrl'], p, cookie)
            print('audio: id=%s bw=%s -> %.1f MB' % (t['id'], t.get('bandwidth'),
                                                     n / 1048576))
        else:
            print('audio: exists, skip')

    if what in ('video', 'both'):
        if not dash.get('video'):
            print('no video stream')
            return 1
        t = bili.pick_video(dash['video'])
        p = os.path.join(base, 'video.m4s')
        if not os.path.exists(p):
            n = bili.download(t['baseUrl'], p, cookie)
            print('video: id=%s %sx%s bw=%s codec=%s -> %.1f MB' % (
                t['id'], t.get('width'), t.get('height'), t.get('bandwidth'),
                t.get('codecs'), n / 1048576))
        else:
            print('video: exists, skip')
    return 0


if __name__ == '__main__':
    sys.exit(main())
