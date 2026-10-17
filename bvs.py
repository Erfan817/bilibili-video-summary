#!/usr/bin/env python3
"""bvs — B 站视频一键转写总结 CLI。

用法:
    python bvs.py <BV链接> [选项]
    bvs BV1xx411c7mD                  # 最简: 一条命令出 transcript
    bvs https://b23.tv/xxxx --srt     # 短链 + SRT 字幕
    bvs <链接> --frames               # 课件/代码类: 画面模式
    bvs <YouTube链接>                 # 其他平台自动走 yt-dlp

从'技能'到'工具'的分水岭: 不依赖任何 agent, 全链路封装在一条命令里。
"""
import sys

from bvs_core.pipeline import main

if __name__ == '__main__':
    sys.exit(main())
