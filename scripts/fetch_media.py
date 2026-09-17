"""下载 B 站音视频流。

用法:
    python fetch_media.py <工作目录>            # 音频 + 视频都下
    python fetch_media.py <工作目录> audio      # 只下音频
    python fetch_media.py <工作目录> video      # 只下视频

约定:
  * 音频取 id=30216(最小码率, ASR 够用), 取不到就按 bandwidth 挑最小的
  * 视频挑 avc1(H.264) 里 bandwidth 最小的 —— HEVC 体积更小但解码兼容性差
  * 工作目录里需要有 playurl.json
"""
import io, json, os, sys, urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      'Chrome/120 Safari/537.36')


def pick_audio(tracks):
    for t in tracks:
        if t.get('id') == 30216:
            return t
    return min(tracks, key=lambda t: t.get('bandwidth') or 10 ** 9)


def pick_video(tracks):
    """分辨率优先, 同分辨率取带宽最小的。

    注意: 选视频流**不能**只看带宽最小 —— 对课件/PPT 类视频, 分辨率决定小字
    能不能看清, 而静态画面的码率本来就极低(实测 480p 仅 85kbps, 20 分钟才 13MB),
    为省几 MB 牺牲分辨率是亏的。
    """
    avc = [t for t in tracks if (t.get('codecs') or '').startswith('avc1')]
    pool = avc or tracks
    return max(pool, key=lambda t: ((t.get('width') or 0) * (t.get('height') or 0),
                                    -(t.get('bandwidth') or 0)))


def download(url, path):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Referer': 'https://www.bilibili.com/',
        'Origin': 'https://www.bilibili.com',
        'Range': 'bytes=0-',
    })
    total = 0
    with urllib.request.urlopen(req, timeout=120) as r, open(path, 'wb') as f:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b)
            total += len(b)
    return total


def main():
    base = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.')
    what = sys.argv[2] if len(sys.argv) > 2 else 'both'

    with io.open(os.path.join(base, 'playurl.json'), encoding='utf-8-sig') as f:
        dash = json.load(f)['data']['dash']

    if what in ('audio', 'both'):
        if not dash.get('audio'):
            print('no audio stream'); sys.exit(1)
        t = pick_audio(dash['audio'])
        p = os.path.join(base, 'audio.m4s')
        if not os.path.exists(p):
            n = download(t['baseUrl'], p)
            print('audio: id=%s bw=%s -> %.1f MB' % (t['id'], t.get('bandwidth'), n / 1048576))
        else:
            print('audio: exists, skip')

    if what in ('video', 'both'):
        if not dash.get('video'):
            print('no video stream'); sys.exit(1)
        t = pick_video(dash['video'])
        p = os.path.join(base, 'video.m4s')
        if not os.path.exists(p):
            n = download(t['baseUrl'], p)
            print('video: id=%s %sx%s bw=%s codec=%s -> %.1f MB' % (
                t['id'], t.get('width'), t.get('height'),
                t.get('bandwidth'), t.get('codecs'), n / 1048576))
        else:
            print('video: exists, skip')


if __name__ == '__main__':
    main()
