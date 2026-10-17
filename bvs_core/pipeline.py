"""一键 CLI 全链路编排: 链接 -> transcript.txt (+ md / json / srt / 画面)。

无 agent 也能出 transcript —— 从'技能'到'工具'的分水岭。
"""
import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import time

from . import __version__, bili
from . import correct as correct_mod
from . import frames as frames_mod
from . import transcribe as transcribe_mod


def build_parser():
    p = argparse.ArgumentParser(
        prog='bvs',
        description='B 站(及其他平台)视频一键转写总结。示例: bvs BV1xx411c7mD')
    p.add_argument('link', help='BV 号 / av 号 / bilibili 链接 / b23.tv 短链')
    p.add_argument('--p', type=int, default=1, dest='page',
                   help='分P 序号, 默认 1')
    p.add_argument('--out', '-o', default=None,
                   help='输出目录(默认 ./outputs/<标题>)')
    p.add_argument('--model', default=None,
                   help='faster-whisper 模型名或本地目录(默认 $WHISPER_MODEL_DIR 或 small)')
    p.add_argument('--lang', default='zh', choices=['zh', 'en', 'auto'],
                   help='音频语言, 默认 zh; auto 由模型自动检测')
    p.add_argument('--topic', default='',
                   help='视频主题关键词(喂给 initial_prompt, 降低术语错误)')
    p.add_argument('--cookie', default=None,
                   help='cookie: 文件路径(Netscape cookies.txt)或 SESSDATA=..; .. 字符串')
    p.add_argument('--no-subtitle', action='store_true',
                   help='禁用字幕快路径(有 cookie 且存在 AI 字幕时默认优先用它)')
    p.add_argument('--srt', action='store_true', help='额外输出 SRT 字幕')
    p.add_argument('--frames', action='store_true', help='开启画面模式(下载视频流+抽帧)')
    p.add_argument('--frames-mode', choices=['scene', 'dense'], default='scene')
    p.add_argument('--dense-interval', type=float, default=8.0)
    p.add_argument('--max-frames', type=int, default=60)
    p.add_argument('--no-correct', action='store_true', help='跳过同音字校正')
    p.add_argument('--no-simplify', action='store_true',
                   help='跳过繁->简归一(默认装了 zhconv 就自动做)')
    p.add_argument('--keep', action='store_true', help='保留中间产物(audio/video/json)')
    p.add_argument('--force', action='store_true', help='重新下载/转写, 忽略已有产物')
    p.add_argument('--threads', type=int, default=None, help='Whisper 线程数')
    p.add_argument('--json', action='store_true', help='输出 JSON 结果(便于脚本/MCP 消费)')
    p.add_argument('--backend', choices=['auto', 'bili', 'ytdlp'], default='auto',
                   help='下载后端: auto(默认,b 站用内置, 其他平台用 yt-dlp)')
    p.add_argument('--version', action='version', version=__version__)
    p.add_argument('--quiet', action='store_true')
    return p


def _log(msg='', flush=True, **kw):
    print(msg, flush=flush, **kw)


def run(argv=None):
    """返回 0(成功) 或 1(失败); JSON 模式时把结果打到 stdout。"""
    args = build_parser().parse_args(argv)
    log = (lambda *a, **k: None) if args.quiet else _log
    cookie = bili.load_cookie(args.cookie)

    parsed = bili.parse_link(args.link)

    # ---- 外部平台 / yt-dlp 后端 -------------------------------------
    if parsed.get('external') or args.backend == 'ytdlp':
        return _run_external(args, parsed, log)

    # ---- b 站内置后端 ----------------------------------------------
    try:
        return _run_bili(args, parsed, cookie, log)
    except bili.BiliError as e:
        print('ERROR: %s' % e, file=sys.stderr)
        return 1


def _run_bili(args, parsed, cookie, log):
    if parsed.get('bvid'):
        info = bili.fetch_view(bvid=parsed['bvid'], cookie=cookie)
    else:
        info = bili.fetch_view(aid=parsed['aid'], cookie=cookie)
    bvid = info['bvid']
    cid = bili.page_cid(info, args.page)
    log('title : %s' % info['title'])
    log('bvid  : %s  p=%d  cid=%s  dur=%.0fs' % (
        bvid, args.page, cid, info['duration']))
    log('owner : %s' % info['owner'])
    if info.get('desc'):
        log('desc  : %s' % info['desc'][:100].replace('\n', ' '))

    # 输出目录
    out_dir = args.out or os.path.join(
        os.getcwd(), 'outputs', bili.safe_filename(info['title']))
    work = os.path.join(out_dir, '.work')
    os.makedirs(work, exist_ok=True)

    playurl = bili.fetch_playurl(bvid, cid, cookie)
    dash = playurl.get('dash') or {}
    # 存一份 playurl.json 到 work, 供 extract_frames 需要时重新下载视频流
    with io.open(os.path.join(work, 'playurl.json'), 'w', encoding='utf-8') as f:
        json.dump({'data': {'dash': dash}}, f, ensure_ascii=False)

    # ---- 字幕快路径: 有 cookie 且有 AI 字幕 ------------------------
    subtitle_body = None
    if cookie and not args.no_subtitle:
        subtitle_body = bili.fetch_subtitles(playurl, cookie)
        if subtitle_body:
            log('>> 字幕快路径: 命中 B 站 AI 字幕, 跳过本地 Whisper')

    transcript_txt = os.path.join(out_dir, 'transcript.txt')
    transcript_srt = os.path.join(out_dir, 'transcript.srt') if args.srt else None
    correction_report = []

    if subtitle_body:
        _write_subtitle(subtitle_body, transcript_txt, transcript_srt)
        source = 'subtitle'
    else:
        if not args.force and os.path.exists(transcript_txt):
            log('transcript.txt 已存在, 跳过转写(--force 重来)')
        else:
            audio_path = _ensure_audio(work, dash, cookie, log, args.force)
            if not audio_path:
                return 1
            transcribe_mod.transcribe_audio(
                audio_path, topic=args.topic or info['title'], lang=args.lang,
                model=args.model, threads=args.threads,
                out_txt=transcript_txt, out_srt=transcript_srt, log=log)
        source = 'whisper'

    # ---- 繁简归一 + 同音字校正 ---------------------------------------
    correction_report = {}
    if not args.no_correct or not args.no_simplify:
        correction_report = _apply_corrections(
            transcript_txt, log, do_correct=not args.no_correct,
            simplify=not args.no_simplify)

    # ---- 画面模式 ----------------------------------------------------
    frames_info = None
    if args.frames:
        frames_info = _run_frames(args, work, dash, cookie, log)

    # ---- 产出 md + json ----------------------------------------------
    _write_markdown(out_dir, info, args, source, frames_info, correction_report)
    summary = _write_summary_json(out_dir, info, args, source, frames_info)

    # ---- 清理 --------------------------------------------------------
    if not args.keep and os.path.isdir(work):
        try:
            shutil.rmtree(work)
        except OSError as e:
            print('WARN: 清理中间产物失败(%s), 请手动删除 %s' % (e, work),
                  file=sys.stderr)

    log('\n完成 -> %s' % out_dir)
    log('  transcript.txt%s' % (' + transcript.srt' if args.srt else ''))
    log('  summary.md / summary.json')
    if frames_info:
        log('  frames/ (关键画面, 逐帧看或交给多模态 agent)')
    if correction_report:
        parts = []
        if correction_report.get('simplified'):
            parts.append('繁->简 %d 行' % correction_report['simplified'])
        if correction_report.get('fixed'):
            parts.append('同音字替换 %d 行' % correction_report['fixed'])
        if correction_report.get('review'):
            parts.append('%d 行待审查(见 summary.md)' % correction_report['review'])
        if parts:
            log('  文本校正: ' + ', '.join(parts))

    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# 各步骤
# ---------------------------------------------------------------------------

def _ensure_audio(work, dash, cookie, log, force):
    audio_path = os.path.join(work, 'audio.m4s')
    if os.path.exists(audio_path) and not force:
        log('audio.m4s 已存在, 跳过下载(--force 重来)')
        return audio_path
    if not dash.get('audio'):
        print('ERROR: 未登录状态可能拿不到音频流, 试试 --cookie', file=sys.stderr)
        return None
    t = bili.pick_audio(dash['audio'])
    log('下载音频流: id=%s bw=%s ...' % (t['id'], t.get('bandwidth')))
    bili.download(t['baseUrl'], audio_path, cookie)
    return audio_path


def _run_frames(args, work, dash, cookie, log):
    # 视频流可能要重新下载到 work
    frames_mod.extract_frames(
        work, args.frames_mode, args.max_frames, args.dense_interval,
        cookie=cookie, log=log)
    idx = os.path.join(work, 'frames_index.txt')
    if not os.path.exists(idx):
        return None
    # 把 frames/ 移到输出目录
    src = os.path.join(work, 'frames')
    dst = os.path.join(os.path.dirname(work), 'frames')
    if os.path.isdir(src) and not os.path.isdir(dst):
        shutil.move(src, dst)
    shutil.copy(idx, os.path.join(os.path.dirname(work), 'frames_index.txt'))
    n = 0
    if os.path.isdir(dst):
        n = len([f for f in os.listdir(dst) if f.endswith('.jpg')])
    return {'frames': n}


def _write_subtitle(body, txt, srt):
    with io.open(txt, 'w', encoding='utf-8') as f:
        for seg in body:
            f.write('[%s] %s\n' % (bili.ts(seg['from']),
                                   (seg.get('content') or '').strip()))
    if srt:
        with io.open(srt, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(body, 1):
                f.write('%d\n%s --> %s\n%s\n\n' % (
                    i, transcribe_mod.srt_ts(seg['from']),
                    transcribe_mod.srt_ts(seg['to']),
                    (seg.get('content') or '').strip()))


def _apply_corrections(transcript_txt, log, do_correct=True, simplify=True):
    """繁->简归一 + 同音字校正。两个开关独立: 关掉校正仍可做归一。"""
    with io.open(transcript_txt, encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f]

    # 先做繁->简归一(Whisper 中文常混出繁体), 再做同音字替换
    lines, n_simplified = correct_mod.normalize_lines(lines, enable=simplify)
    if n_simplified:
        log('繁->简归一: %d 行' % n_simplified)
    elif simplify and not correct_mod.has_zhconv() \
            and correct_mod.looks_traditional(lines):
        log('提示: 检出疑似繁体字。装 zhconv 可自动归一: pip install zhconv')

    report, review = [], []
    if do_correct:
        items = correct_mod.load_corrections()
        lines, report = correct_mod.apply_high(lines, items)
        review = correct_mod.collect_context(lines, items)

    with io.open(transcript_txt, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    if report:
        log('同音字校正: 自动替换 %d 行' % len(report))
        for ln, chg in report[:20]:
            log('  L%d  %s' % (ln, chg))
    return {'fixed': len(report), 'review': len(review),
            'simplified': n_simplified, 'review_lines': review[:50]}


def _write_markdown(out_dir, info, args, source, frames_info, correction_report):
    lines = []
    lines.append('# %s' % info['title'])
    lines.append('')
    lines.append('> 自动生成(%s 转写)。基于自动转写 + 同音字校正(已做繁->简归一), '
                 '非原文。' % source)
    lines.append('')
    lines.append('| 项 | 值 |')
    lines.append('|---|---|')
    lines.append('| BV | [%s](https://www.bilibili.com/video/%s) |'
                 % (info['bvid'], info['bvid']))
    lines.append('| UP | %s |' % info['owner'])
    lines.append('| 时长 | %.0fs |' % info['duration'])
    lines.append('| 转写来源 | %s |' % ('B 站 AI 字幕' if source == 'subtitle' else '本地 Whisper'))
    if info.get('desc'):
        lines.append('')
        lines.append('## 简介')
        lines.append('')
        lines.append(info['desc'])
    lines.append('')
    lines.append('## 逐句稿')
    lines.append('')
    lines.append('见 [transcript.txt](transcript.txt)(带时间戳)。')
    if frames_info:
        lines.append('')
        lines.append('## 关键画面')
        lines.append('')
        lines.append('共 %d 帧, 见 [frames_index.txt](frames_index.txt), 画面在 [frames/](frames/)。' % frames_info['frames'])
    if correction_report and correction_report.get('review_lines'):
        lines.append('')
        lines.append('## 同音字审查清单(未自动替换, 请逐句判断)')
        lines.append('')
        lines.append('| 行 | 原文 | 命中 |')
        lines.append('|---|---|---|')
        for ln, text, hits in correction_report['review_lines']:
            lines.append('| %d | %s | %s |' % (ln, text[:40].replace('|', '/'), hits))
    lines.append('')
    lines.append('---')
    lines.append('*由 bilibili-video-summary 自动生成。*')
    with io.open(os.path.join(out_dir, 'summary.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _write_summary_json(out_dir, info, args, source, frames_info):
    summary = {
        'tool': 'bilibili-video-summary',
        'version': __version__,
        'title': info['title'],
        'bvid': info['bvid'],
        'owner': info['owner'],
        'duration': info['duration'],
        'page': args.page,
        'source': source,
        'files': {
            'transcript': 'transcript.txt',
            'summary_md': 'summary.md',
            'summary_json': 'summary.json',
            'srt': 'transcript.srt' if args.srt else None,
        },
        'frames': frames_info,
    }
    with io.open(os.path.join(out_dir, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


# ---------------------------------------------------------------------------
# yt-dlp 后端(多平台: YouTube 等)
# ---------------------------------------------------------------------------

def _run_external(args, parsed, log):
    url = parsed.get('url') or args.link
    out_dir = args.out or os.path.join(os.getcwd(), 'outputs', 'video')
    work = os.path.join(out_dir, '.work')
    os.makedirs(work, exist_ok=True)
    log('使用 yt-dlp 后端下载: %s' % url)

    import glob
    import subprocess
    cmd = ['yt-dlp', '-f', 'bestaudio/best', '-o',
           os.path.join(work, 'audio.%(ext)s'), url]
    log(' '.join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        print('ERROR: yt-dlp 失败(exit %d)。请确认已安装: pip install yt-dlp' % rc,
              file=sys.stderr)
        return 1
    cands = glob.glob(os.path.join(work, 'audio.*'))
    if not cands:
        print('ERROR: yt-dlp 未产出音频文件', file=sys.stderr)
        return 1
    audio_path = cands[0]

    transcript_txt = os.path.join(out_dir, 'transcript.txt')
    transcribe_mod.transcribe_audio(
        audio_path, topic=args.topic, lang=args.lang,
        model=args.model, threads=args.threads,
        out_txt=transcript_txt, out_srt=(os.path.join(out_dir, 'transcript.srt')
                                         if args.srt else None),
        log=log)

    correction_report = {}
    if not args.no_correct or not args.no_simplify:
        correction_report = _apply_corrections(
            transcript_txt, log, do_correct=not args.no_correct,
            simplify=not args.no_simplify)

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    log('完成 -> %s/transcript.txt' % out_dir)
    if args.json:
        print(json.dumps({'tool': 'bilibili-video-summary', 'version': __version__,
                          'url': url, 'source': 'ytdlp',
                          'transcript': os.path.join(out_dir, 'transcript.txt')},
                         ensure_ascii=False))
    return 0


def main(argv=None):
    return run(argv)


if __name__ == '__main__':
    sys.exit(main())
