"""本地 Whisper 转写核心: audio 文件 -> transcript.txt (+ 可选 .srt)。

要点(来自 SKILL.md):
  * 每转完一段就写盘并 flush —— 进度用行数查, 不依赖 stdout(后台跑时管道会
    全缓冲, 看不到输出)
  * initial_prompt 填视频主题能显著降低术语错误
  * condition_on_previous_text=False 避免错误滚雪球
  * 不需要 ffmpeg —— faster-whisper 自带 PyAV 直接解码
"""
import os
import sys
import time

from faster_whisper import WhisperModel

# 模型目录: 优先读环境变量 WHISPER_MODEL_DIR; 留空回退模型名 'small'
# (Windows 上 HF 自动下载会拿到 0 字节软链, 建议手动落盘后指过来)
DEFAULT_MODEL = os.environ.get('WHISPER_MODEL_DIR', '').strip() or 'small'


def _threads():
    t = os.environ.get('WHISPER_THREADS', '').strip()
    if t and t.isdigit() and int(t) > 0:
        return int(t)
    return max(2, (os.cpu_count() or 4) // 2)


def ts(seconds):
    m, sec = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return '%02d:%02d:%02d' % (h, m, sec)


def srt_ts(seconds):
    """SRT 时间轴 mm:ss,mmm(毫秒三位)。"""
    ms = int(round(seconds * 1000))
    m, sec = divmod(ms, 60000)
    h, m = divmod(m, 60000)
    return '%02d:%02d:%02d,%03d' % (h, m, sec // 1000, sec % 1000)


def transcribe_audio(audio_path, topic='', lang='zh', model=DEFAULT_MODEL,
                     threads=None, out_txt=None, out_srt=None,
                     log=print):
    """转写一个音频文件。

    返回 (segments 数, 总耗时秒, 平均语速信息 dict)。
    每段写盘 flush, 进度可 `wc -l transcript.txt` 查看。
    """
    t0 = time.time()
    model = model or DEFAULT_MODEL
    log('loading model: %s ...' % model, flush=True)
    model = WhisperModel(model, device='cpu', compute_type='int8',
                         cpu_threads=threads or _threads())
    log('model ready in %.1fs' % (time.time() - t0), flush=True)

    # initial_prompt 同时做两件事: 给主题词降低术语错误 + 显式要求简体中文
    # (实测 Whisper 会在中文视频里混出繁体字, 如"打電話/報喜不報憂")
    if lang == 'zh':
        prompt = ('以下是简体中文普通话视频内容，主题是%s。'
                  '请全部用简体中文转写。' % topic) if topic else \
            '以下是简体中文普通话视频内容。请全部用简体中文转写。'
    elif topic and lang != 'auto':
        prompt = '视频主题是%s。' % topic
    else:
        # auto 检测时不要预设语言, 否则会把英文视频往中文偏
        prompt = None
    segments, info = model.transcribe(
        audio_path, language=(lang if lang != 'auto' else None), beam_size=5,
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=400),
        initial_prompt=prompt, condition_on_previous_text=False)

    n = 0
    if out_txt:
        ftxt = open(out_txt, 'w', encoding='utf-8')
    if out_srt:
        fsrt = open(out_srt, 'w', encoding='utf-8')
    for seg in segments:
        line = '[%s] %s' % (ts(seg.start), seg.text.strip())
        if out_txt:
            ftxt.write(line + '\n')
            ftxt.flush()
        if out_srt:
            fsrt.write('%d\n%s --> %s\n%s\n\n' % (
                n + 1, srt_ts(seg.start), srt_ts(seg.end), seg.text.strip()))
        n += 1
        if n % 20 == 0:
            log('  seg %d @ %s' % (n, ts(seg.start)), flush=True)
    if out_txt:
        ftxt.close()
    if out_srt:
        fsrt.close()

    dur = info.duration or 0
    log('DONE segments=%d audio=%.1fs elapsed=%.1fs' % (
        n, dur, time.time() - t0), flush=True)
    return {'segments': n, 'audio_duration': dur,
            'elapsed': time.time() - t0}


def main(argv=None):
    """CLI: python transcribe.py <工作目录> ["视频主题"] [语言] [--srt]"""
    argv = argv if argv is not None else sys.argv[1:]
    base = os.path.abspath(argv[0]) if argv else '.'
    topic = argv[1] if len(argv) > 1 else ''
    lang = argv[2] if len(argv) > 2 else 'zh'
    srt = '--srt' in argv or '-srt' in argv

    audio = os.path.join(base, 'audio.m4s')
    if not os.path.exists(audio):
        # 兼容 yt-dlp 后端落地成的 audio.<ext>
        import glob
        cands = glob.glob(os.path.join(base, 'audio.*'))
        if not cands:
            print('no audio file in %s' % base)
            return 1
        audio = cands[0]

    out_txt = os.path.join(base, 'transcript.txt')
    out_srt = os.path.join(base, 'transcript.srt') if srt else None
    transcribe_audio(audio, topic, lang, out_txt=out_txt, out_srt=out_srt)
    return 0


if __name__ == '__main__':
    sys.exit(main())
