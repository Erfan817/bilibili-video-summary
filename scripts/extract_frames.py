"""按需开启: 从 B 站视频流抽关键帧, 供多模态读图使用。

用法:
    # 对谈 / 播客类 —— 场景检测(默认)
    python extract_frames.py <工作目录>

    # 课件 / PPT / 板书类 —— 密集采样(必须用这个模式)
    python extract_frames.py <工作目录> --mode dense --dense-interval 8

参数:
    --max-frames N        候选帧上限(默认 60), 超出按变化幅度排序取前 N
    --mode scene|dense    抽帧策略(默认 scene)
    --dense-interval S    dense 模式的候选采样间隔, 秒(默认 8)
    --mae-thresh F        scene 模式 MAE 阈值(默认 25)
    --ratio-thresh F      scene 模式变化像素比例阈值(默认 0.55)
    --dense-mae-thresh F  dense 模式去重阈值(默认 2.0, 只扔掉像素级相同的帧)

产出:
    <工作目录>/frames/*.jpg       关键帧, 文件名含时间戳
    <工作目录>/frames_index.txt   时间戳 + 变化指标索引

设计要点(实测结论, 勿随意改):
  * 视频流必须按 **分辨率** 挑, 不能按带宽最小 —— 静态画面码率极低(实测 480p 仅
    85kbps, 20 分钟才 12MB), 为省几 MB 换糊掉的小字是亏的
  * scene 模式用双指标: MAE(64x64 灰度平均绝对差) + 变化像素比例。只用 MAE 会把
    人物微表情全抓进来(实测 316 秒出 182 张, 等于没筛)
  * **dense 模式才是课件类的正解**: PPT 一行行往外蹦时整屏变化很小, scene 阈值一高
    就全漏。dense 按固定间隔取样 + 极低阈值去重
  * 文件不完整解码会抛 InvalidDataError —— 必须 try/except 保住已解出的帧
"""
import argparse, io, json, os, sys
import numpy as np
import av
from PIL import Image

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      'Chrome/120 Safari/537.36')


def build_args():
    p = argparse.ArgumentParser()
    p.add_argument('base', help='工作目录, 里面要有 playurl.json 或 video.m4s')
    p.add_argument('--max-frames', type=int, default=60)
    p.add_argument('--mode', choices=['scene', 'dense'], default='scene')
    p.add_argument('--dense-interval', type=float, default=8.0)
    p.add_argument('--mae-thresh', type=float, default=25.0)
    p.add_argument('--ratio-thresh', type=float, default=0.55)
    p.add_argument('--dense-mae-thresh', type=float, default=2.0)
    p.add_argument('--jpeg-quality', type=int, default=85)
    return p.parse_args()


def pick_video_stream(videos):
    """分辨率优先, 同分辨率取带宽最小的。"""
    avc = [t for t in videos if (t.get('codecs') or '').startswith('avc1')]
    pool = avc or videos
    return max(pool, key=lambda t: ((t.get('width') or 0) * (t.get('height') or 0),
                                    -(t.get('bandwidth') or 0)))


def download(url, path):
    import urllib.request
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Referer': 'https://www.bilibili.com/',
        'Origin': 'https://www.bilibili.com', 'Range': 'bytes=0-',
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


def sig(img):
    return np.asarray(img.convert('L').resize((64, 64)), dtype=np.float32)


def main():
    args = build_args()
    base = os.path.abspath(args.base)

    vpath = os.path.join(base, 'video.m4s')
    if not os.path.exists(vpath):
        pj = os.path.join(base, 'playurl.json')
        with io.open(pj, encoding='utf-8-sig') as f:
            dash = json.load(f)['data']['dash']
        if not dash.get('video'):
            print('no video stream in playurl.json'); sys.exit(1)
        pick = pick_video_stream(dash['video'])
        print('stream: id=%s %sx%s bw=%s codec=%s' % (
            pick['id'], pick['width'], pick['height'],
            pick.get('bandwidth'), pick.get('codecs')))
        n = download(pick['baseUrl'], vpath)
        print('downloaded: %.1f MB' % (n / 1048576))

    fdir = os.path.join(base, 'frames')
    os.makedirs(fdir, exist_ok=True)

    if args.mode == 'dense':
        cand_step, keep_mae, keep_ratio = args.dense_interval, args.dense_mae_thresh, 1.1
    else:
        cand_step, keep_mae, keep_ratio = 1.0, args.mae_thresh, args.ratio_thresh

    container = av.open(vpath)
    stream = container.streams.video[0]
    print('mode=%s  decode: %sx%s avg_rate=%s' % (
        args.mode, stream.width, stream.height, stream.average_rate))

    last_sig = None
    last_t = None
    cand = []
    decoded = 0
    tmax = 0.0

    gen = container.decode(stream)
    while True:
        try:
            frame = next(gen)
        except StopIteration:
            break
        except Exception as e:
            print('decode stopped early (%s) — 文件不完整时属正常' % type(e).__name__)
            break
        decoded += 1
        if frame.time is None:
            continue
        t = float(frame.time)
        tmax = max(tmax, t)
        if last_t is not None and t - last_t < cand_step:
            continue
        last_t = t
        img = frame.to_image()
        s = sig(img)
        if last_sig is None:
            mae, ratio, keep = 999.0, 1.0, True
        else:
            diff = np.abs(s - last_sig)
            mae = float(diff.mean())
            ratio = float((diff > 20).mean())
            keep = (mae >= keep_mae) or (ratio >= keep_ratio)
        if keep:
            fn = 'f%05d_%06.1fs.jpg' % (len(cand), t)
            img.save(os.path.join(fdir, fn), quality=args.jpeg_quality)
            cand.append({'t': t, 'mae': mae, 'ratio': ratio, 'file': fn})
            last_sig = s

    if len(cand) > args.max_frames:
        cand.sort(key=lambda c: (c['ratio'], c['mae']), reverse=True)
        for c in cand[args.max_frames:]:
            p = os.path.join(fdir, c['file'])
            if os.path.exists(p):
                os.remove(p)
        cand = cand[:args.max_frames]
    cand.sort(key=lambda c: c['t'])

    with io.open(os.path.join(base, 'frames_index.txt'), 'w', encoding='utf-8') as f:
        for c in cand:
            f.write('%7.1fs  mae=%6.2f  changed=%5.1f%%  %s\n' % (
                c['t'], c['mae'], c['ratio'] * 100, c['file']))

    print('decoded=%d  covered=%.1fs  kept=%d  (max=%d)' % (
        decoded, tmax, len(cand), args.max_frames))
    print('-> %s' % os.path.join(base, 'frames_index.txt'))
    print('下一步: 逐帧 Read 读图, 剔除人物镜头与转场, 只留有信息量的画面')


if __name__ == '__main__':
    main()
