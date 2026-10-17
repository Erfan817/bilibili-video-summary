"""抽帧(技能脚本, 薄封装 bvs_core)。

用法(与 SKILL.md 保持一致):
    # 对谈 / 播客类 —— 场景检测(默认)
    python extract_frames.py <工作目录>

    # 课件 / PPT / 板书类 —— 密集采样(必须用这个模式)
    python extract_frames.py <工作目录> --mode dense --dense-interval 8
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bvs_core import frames


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    args = frames.build_args(argv)
    frames.extract_frames(os.path.abspath(args.base), args.mode,
                          args.max_frames, args.dense_interval,
                          args.mae_thresh, args.ratio_thresh,
                          args.dense_mae_thresh, args.jpeg_quality,
                          args.cookie or os.environ.get('BILI_COOKIE'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
