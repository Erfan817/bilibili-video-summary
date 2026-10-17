"""本地 Whisper 转写(技能脚本, 薄封装 bvs_core)。

用法(与 SKILL.md 保持一致):
    python transcribe.py <工作目录> "<视频主题>" [语言=zh]

可选 --srt 额外输出 transcript.srt。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bvs_core import transcribe


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    base = os.path.abspath(argv[0] if argv else '.')
    topic = argv[1] if len(argv) > 1 else ''
    lang = argv[2] if len(argv) > 2 else 'zh'
    srt = '--srt' in argv
    audio = os.path.join(base, 'audio.m4s')
    if not os.path.exists(audio):
        import glob
        cands = glob.glob(os.path.join(base, 'audio.*'))
        if not cands:
            print('no audio file in %s' % base)
            return 1
        audio = cands[0]
    transcribe.transcribe_audio(
        audio, topic=topic, lang=lang,
        out_txt=os.path.join(base, 'transcript.txt'),
        out_srt=os.path.join(base, 'transcript.srt') if srt else None)
    return 0


if __name__ == '__main__':
    sys.exit(main())
