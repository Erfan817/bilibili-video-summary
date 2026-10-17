"""bvs_core.correct 单元测试。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bvs_core import correct


class TestApplyHigh(unittest.TestCase):
    def test_replace_high(self):
        lines = ['大家好我是加瓦工程师', '今天聊聊双飞和大厂']
        items = [
            (['加瓦'], 'Java', 'high', ''),
            (['双飞', '双肥'], '双非', 'high', ''),
            (['大產'], '大厂', 'high', ''),
        ]
        new, report = correct.apply_high(lines, items)
        self.assertEqual(new[0], '大家好我是Java工程师')
        self.assertEqual(new[1], '今天聊聊双非和大厂')
        self.assertEqual(len(report), 2)

    def test_longest_first(self):
        lines = ['维德根斯坦说过']
        items = [(['维德根斯坦', '维德根兰'], '维特根斯坦', 'high', '')]
        new, report = correct.apply_high(lines, items)
        self.assertEqual(new[0], '维特根斯坦说过')
        self.assertEqual(report[0][1], '维德根斯坦->维特根斯坦 x1')

    def test_context_not_replaced(self):
        # '奇异' 在数学语境下是对的 —— 不自动替换
        lines = ['这个矩阵是奇异的', '他说的话有奇异']
        items = [(['奇异'], '歧义', 'context', '')]
        new, report = correct.apply_high(lines, items)
        self.assertEqual(new, lines)
        self.assertEqual(report, [])
        review = correct.collect_context(lines, items)
        self.assertEqual(len(review), 2)


class TestCollectContext(unittest.TestCase):
    def test_flag_lines(self):
        lines = ['奇异矩阵', '无关内容']
        items = [(['奇异'], '歧义', 'context', '')]
        review = correct.collect_context(lines, items)
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0][0], 1)
        self.assertIn('奇异', review[0][2])

    def test_multi_variant(self):
        lines = ['考工还是考公']
        items = [(['考工', '考供'], '考公', 'context', '')]
        review = correct.collect_context(lines, items)
        self.assertEqual(len(review), 1)


class TestLoadCorrections(unittest.TestCase):
    def test_table_loads(self):
        items = correct.load_corrections()
        self.assertGreater(len(items), 10)
        highs = [i for i in items if i[2] == 'high']
        ctxs = [i for i in items if i[2] == 'context']
        self.assertGreater(len(highs), 0)
        self.assertGreater(len(ctxs), 0)


class TestSimplify(unittest.TestCase):
    def test_normalize_lines(self):
        lines = ['每次打電話回家報喜不報憂', '这是简体']
        new, changed = correct.normalize_lines(lines)
        if correct.has_zhconv():
            self.assertIn('打电话', new[0])
            self.assertIn('报喜不报忧', new[0])
            self.assertEqual(changed, 1)
            self.assertEqual(new[1], '这是简体')
        else:
            # 没装 zhconv 时原样返回, 不报错
            self.assertEqual(new, lines)
            self.assertEqual(changed, 0)

    def test_normalize_disabled(self):
        lines = ['打電話']
        new, changed = correct.normalize_lines(lines, enable=False)
        self.assertEqual(new, lines)
        self.assertEqual(changed, 0)

    def test_simplify_without_zhconv_returns_text(self):
        if not correct.has_zhconv():
            self.assertEqual(correct.simplify('打電話'), '打電話')


if __name__ == '__main__':
    unittest.main()
