"""把音频转写成带时间戳的逐句稿。

用法:
    python transcribe.py <工作目录> "<视频主题>" [语言=zh]

要点:
  * 每转完一段就写盘并 flush —— 这样进度可以直接用 `wc -l transcript.txt` 看,
    不依赖 stdout(后台跑时管道会全缓冲, 看不到任何输出)
  * initial_prompt 填视频主题能显著降低术语错误
  * condition_on_previous_text=False 避免错误滚雪球
"""
import io, os, sys, time
from faster_whisper import WhisperModel

# 模型目录: 优先读环境变量 WHISPER_MODEL_DIR; 留空则回退到模型名 'small'
# (由 faster-whisper 自行下载)。注意 Windows 上走 HF 自动下载会拿到 0 字节软链,
# 建议先把模型手动落盘,再用这个变量指向它。
MODEL = os.environ.get('WHISPER_MODEL_DIR', '').strip() or 'small'
# 线程数: 环境变量 WHISPER_THREADS 可覆盖, 默认取 CPU 核数的一半
THREADS = int(os.environ.get('WHISPER_THREADS', '0')) or max(2, (os.cpu_count() or 4) // 2)


def ts(s):
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return '%02d:%02d:%02d' % (h, m, sec)


def main():
    base = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else '.')
    topic = sys.argv[2] if len(sys.argv) > 2 else ''
    lang = sys.argv[3] if len(sys.argv) > 3 else 'zh'

    audio = os.path.join(base, 'audio.m4s')
    out = os.path.join(base, 'transcript.txt')
    if not os.path.exists(audio):
        print('audio.m4s not found in %s' % base)
        sys.exit(1)

    t0 = time.time()
    print('loading model...', flush=True)
    model = WhisperModel(MODEL, device='cpu', compute_type='int8',
                         cpu_threads=THREADS)
    print('model ready in %.1fs' % (time.time() - t0), flush=True)

    prompt = ('以下是普通话视频内容，主题是%s。' % topic) if topic else None
    segments, info = model.transcribe(
        audio, language=lang, beam_size=5,
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=400),
        initial_prompt=prompt, condition_on_previous_text=False)

    n = 0
    with io.open(out, 'w', encoding='utf-8') as f:
        for seg in segments:
            f.write('[%s] %s\n' % (ts(seg.start), seg.text.strip()))
            f.flush()
            n += 1
            if n % 20 == 0:
                print('  seg %d @ %s' % (n, ts(seg.start)), flush=True)

    print('DONE segments=%d elapsed=%.1fs -> %s' % (n, time.time() - t0, out))


if __name__ == '__main__':
    main()
