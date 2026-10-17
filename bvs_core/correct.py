"""同音字校正引擎。

从 corrections.json(众包表)加载, 按 confidence 分级处理:
  * high     -> 自动替换(这些是错得稳定的多字误识别)
  * context  -> 只列进审查清单, 不自动替换

设计原则(来自 SKILL.md 踩坑记录): 机械替换会误伤('奇异'在数学语境下本来
就对), 所以**可疑处标记而非直接替换**。CLI 无 agent 也能用 —— 自动替换
high 项, 同时把 context 项逐行列进审查清单, 交给后续人工/AI 复核。
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CORRECTIONS = os.path.join(_HERE, 'corrections.json')


class CorrectionError(Exception):
    pass


# 常见"只在繁体里出现"的字, 用于没装 zhconv 时给提示
TRADITIONAL_HINT = set('打電話報憂裝堅強為什麼這裡個沒有們後說會時國學還對來過樣'
                       '實際聽點發現經濟關於問題讓給時間內容')


def has_zhconv():
    """是否装了 zhconv(纯 Python 的繁简转换库)。"""
    try:
        import zhconv  # noqa: F401
        return True
    except ImportError:
        return False


def simplify(text):
    """繁体 -> 简体归一化。

    Whisper 中文转写时常混出繁体字(实测"打電話/報喜不報憂")。只在
    `initial_prompt` 里要求简体只能减轻、不能根治, 所以这里做一次确定性归一。

    没装 zhconv 时原样返回(不报错) —— 它是可选依赖。
    """
    try:
        import zhconv
    except ImportError:
        return text
    return zhconv.convert(text, 'zh-cn')


def normalize_lines(lines, enable=True):
    """对逐句稿做繁简归一。返回 (新行列表, 被改动的行数)。"""
    if not enable or not has_zhconv():
        return list(lines), 0
    out = []
    changed = 0
    for line in lines:
        new = simplify(line)
        if new != line:
            changed += 1
        out.append(new)
    return out, changed


def looks_traditional(lines):
    """粗判文本里是否疑似有繁体字(用于提示装 zhconv)。"""
    for line in lines:
        for ch in line:
            if ch in TRADITIONAL_HINT:
                return True
    return False


def load_corrections(path=DEFAULT_CORRECTIONS):
    """加载校正表, 返回 [(from_variants, to, confidence, note), ...]。"""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    items = []
    for cat in data.get('categories', []):
        for c in cat.get('corrections', []):
            frm = c.get('from') or []
            if not isinstance(frm, list):
                frm = [frm]
            frm = [str(x).strip() for x in frm if str(x).strip()]
            if not frm or not c.get('to'):
                continue
            items.append((frm, str(c['to']), c.get('confidence', 'context'),
                          c.get('note', '')))
    return items


def _replace(text, variants, to):
    """最长优先整体替换; 返回 (新文本, 命中的变体列表, 替换次数)。"""
    variants = sorted(set(variants), key=len, reverse=True)
    pattern = re.compile('|'.join(re.escape(v) for v in variants))
    matched = []
    count = [0]

    def _repl(m):
        count[0] += 1
        if m.group(0) not in matched:
            matched.append(m.group(0))
        return to

    return pattern.sub(_repl, text), matched, count[0]


def apply_high(lines, items):
    """只对 high 项自动替换。返回 (新行列表, 替换报告)。"""
    highs = [(f, t, n) for f, t, conf, n in items if conf == 'high']
    new_lines = []
    report = []  # (行号, 命中的变体摘要, 替换次数)
    for idx, line in enumerate(lines, 1):
        text = line
        changes = []
        for variants, to, note in highs:
            text, matched, n = _replace(text, variants, to)
            if n:
                changes.append('%s->%s x%d' % ('/'.join(matched), to, n))
        new_lines.append(text)
        if changes:
            report.append((idx, '; '.join(changes)))
    return new_lines, report


def collect_context(lines, items):
    """把含 context 项的原始行收集进审查清单(不修改)。"""
    ctxs = [(f, t, n) for f, t, conf, n in items if conf == 'context']
    review = []  # (行号, 原文, 命中项)
    for idx, line in enumerate(lines, 1):
        hits = []
        for variants, to, note in ctxs:
            for v in variants:
                if v in line:
                    hits.append('%s->%s' % (v, to))
                    break
        if hits:
            review.append((idx, line.strip(), '; '.join(hits)))
    return review


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    import argparse
    p = argparse.ArgumentParser(description='同音字校正')
    p.add_argument('input', help='transcript.txt 路径')
    p.add_argument('--output', '-o', help='输出路径(默认 <input>.corrected)')
    p.add_argument('--table', help='校正表 JSON 路径(默认 corrections.json)')
    p.add_argument('--no-context', action='store_true',
                   help='不输出 context 审查清单')
    p.add_argument('--no-simplify', action='store_true',
                   help='跳过繁->简归一(默认装了 zhconv 就做)')
    args = p.parse_args(argv)

    items = load_corrections(args.table) if args.table else load_corrections()
    with open(args.input, encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f]

    lines, n_simplified = normalize_lines(lines, enable=not args.no_simplify)
    new_lines, report = apply_high(lines, items)
    review = [] if args.no_context else collect_context(lines, items)

    out = args.output or args.input + '.corrected'
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines) + '\n')
    print('wrote %s  (simplified %d lines, auto-fixed %d lines, '
          'context-review %d lines)' % (out, n_simplified, len(report),
                                        len(review)))
    if not has_zhconv() and looks_traditional(lines):
        print('  提示: 检出疑似繁体字。装 zhconv 可自动归一: '
              'pip install zhconv')
    for ln, chg in report:
        print('  L%d  %s' % (ln, chg))
    if review:
        print('\n-- context 审查清单(未自动替换, 需人/AI 逐句判断) --')
        for ln, text, hits in review:
            print('  L%d [%s] %s' % (ln, hits, text[:60]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
