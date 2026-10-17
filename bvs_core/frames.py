"""关键帧抽取(scene 场景检测 / dense 密集采样)。

设计要点(来自 SKILL.md 实测结论, 勿随意改):
  * 视频流必须按**分辨率**挑(不能按带宽最小) —— 静态 PPT 480p 仅 85kbps
  * scene 模式用双指标: MAE(64x64 灰度平均绝对差) + 变化像素比例。只用 MAE
    会把人物微表情全抓进来(实测 316 秒出 182 张, 等于没筛)
  * **dense 模式才是课件类的正解**: PPT 一行行往外蹦时整屏变化很小, scene
    阈值一高就全漏; dense 按固定间隔取样 + 极低阈值去重
  * 文件不完整解码会抛 InvalidDataError —— 必须 try/except 保住已解出的帧
"""
import io
import json
import os
import sys

import numpy as np
import av
from PIL import Image

from . import bili


def build_args(argv=None):
    import argparse
    p = argparse.ArgumentParser(description='抽帧: scene(对谈/默认) / dense(课件)')
    p.add_argument('base', help='工作目录, 里面要有 video.m4s 或 playurl.json')
    p.add_argument('--max-frames', type=int, default=60)
    p.add_argument('--mode', choices=['scene', 'dense'], default='scene')
    p.add_argument('--dense-interval', type=float, default=8.0)
    p.add_argument('--mae-thresh', type=float, default=25.0)
    p.add_argument('--ratio-thresh', type=float, default=0.55)
    p.add_argument('--dense-mae-thresh', type=float, default=2.0)
    p.add_argument('--jpeg-quality', type=int, default=85)
    p.add_argument('--cookie', help='cookie 文件或字符串(下载高清流用)')
    return p.parse_args(argv)


def _sig(img):
    return np.asarray(img.convert('L').resize((64, 64)), dtype=np.float32)


def extract_frames(base, mode='scene', max_frames=60, dense_interval=8.0,
                   mae_thresh=25.0, ratio_thresh=0.55, dense_mae_thresh=2.0,
                   jpeg_quality=85, cookie=None, log=print):
    """从 <base>/video.m4s(缺则按 playurl.json 下载)抽帧。

    产出 <base>/frames/*.jpg + <base>/frames_index.txt。
    返回候选帧列表。
    """
    vpath = os.path.join(base, 'video.m4s')
    if not os.path.exists(vpath):
        pj = os.path.join(base, 'playurl.json')
        with io.open(pj, encoding='utf-8-sig') as f:
            dash = json.load(f)['data']['dash']
        if not dash.get('video'):
            print('no video stream in playurl.json')
            return []
        pick = bili.pick_video(dash['video'])
        log('stream: id=%s %sx%s bw=%s codec=%s' % (
            pick['id'], pick.get('width'), pick.get('height'),
            pick.get('bandwidth'), pick.get('codecs')))
        n = bili.download(pick['baseUrl'], vpath, cookie)
        log('downloaded: %.1f MB' % (n / 1048576))

    fdir = os.path.join(base, 'frames')
    os.makedirs(fdir, exist_ok=True)

    if mode == 'dense':
        cand_step, keep_mae, keep_ratio = dense_interval, dense_mae_thresh, 1.1
    else:
        cand_step, keep_mae, keep_ratio = 1.0, mae_thresh, ratio_thresh

    container = av.open(vpath)
    stream = container.streams.video[0]
    log('mode=%s  decode: %sx%s avg_rate=%s' % (
        mode, stream.width, stream.height, stream.average_rate))

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
        s = _sig(img)
        if last_sig is None:
            mae, ratio, keep = 999.0, 1.0, True
        else:
            diff = np.abs(s - last_sig)
            mae = float(diff.mean())
            ratio = float((diff > 20).mean())
            keep = (mae >= keep_mae) or (ratio >= keep_ratio)
        if keep:
            fn = 'f%05d_%06.1fs.jpg' % (len(cand), t)
            img.save(os.path.join(fdir, fn), quality=jpeg_quality)
            cand.append({'t': t, 'mae': mae, 'ratio': ratio, 'file': fn})
            last_sig = s
    # 关掉容器, 释放文件句柄(否则 Windows 上后续删除 video.m4s 会被锁)
    try:
        container.close()
    except Exception:
        pass

    if len(cand) > max_frames:
        cand.sort(key=lambda c: (c['ratio'], c['mae']), reverse=True)
        for c in cand[max_frames:]:
            p = os.path.join(fdir, c['file'])
            if os.path.exists(p):
                os.remove(p)
        cand = cand[:max_frames]
    cand.sort(key=lambda c: c['t'])

    with io.open(os.path.join(base, 'frames_index.txt'), 'w',
                 encoding='utf-8') as f:
        for c in cand:
            f.write('%7.1fs  mae=%6.2f  changed=%5.1f%%  %s\n' % (
                c['t'], c['mae'], c['ratio'] * 100, c['file']))

    log('decoded=%d  covered=%.1fs  kept=%d  (max=%d)' % (
        decoded, tmax, len(cand), max_frames))
    log('-> %s' % os.path.join(base, 'frames_index.txt'))
    return cand


def main(argv=None):
    args = build_args(argv)
    extract_frames(os.path.abspath(args.base), args.mode, args.max_frames,
                   args.dense_interval, args.mae_thresh, args.ratio_thresh,
                   args.dense_mae_thresh, args.jpeg_quality, args.cookie)
    return 0


if __name__ == '__main__':
    sys.exit(main())
