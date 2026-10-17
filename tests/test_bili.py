"""bvs_core.bili 单元测试(纯 stdlib, 无网络)。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bvs_core import bili


class TestParseLink(unittest.TestCase):
    def test_bare_bv(self):
        r = bili.parse_link('BV1xx411c7mD')
        self.assertEqual(r['bvid'], 'BV1xx411c7mD')
        self.assertEqual(r['page'], 1)

    def test_bare_av(self):
        r = bili.parse_link('av170001')
        self.assertEqual(r['aid'], '170001')

    def test_full_url(self):
        r = bili.parse_link('https://www.bilibili.com/video/BV1xx411c7mD/')
        self.assertEqual(r['bvid'], 'BV1xx411c7mD')
        self.assertEqual(r['page'], 1)

    def test_full_url_with_page(self):
        r = bili.parse_link('https://www.bilibili.com/video/BV1xx411c7mD/?p=3&vd_source=abc')
        self.assertEqual(r['bvid'], 'BV1xx411c7mD')
        self.assertEqual(r['page'], 3)

    def test_bv_with_query(self):
        r = bili.parse_link('https://b23.tv/BV1xx411c7mD?share_medium=android')
        self.assertTrue(r['bvid'] or r['url'])

    def test_external_url(self):
        r = bili.parse_link('https://www.youtube.com/watch?v=abc123')
        self.assertTrue(r.get('external'))
        self.assertEqual(r['page'], 1)

    def test_http_prefix_added(self):
        r = bili.parse_link('bilibili.com/video/BV1xx411c7mD')
        self.assertEqual(r['bvid'], 'BV1xx411c7mD')


class TestCookie(unittest.TestCase):
    def test_string_cookie(self):
        c = bili.load_cookie('SESSDATA=abc; bili_jct=xyz')
        self.assertIn('SESSDATA=abc', c)
        self.assertIn('bili_jct=xyz', c)

    def test_netscape_file(self):
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False,
                                         encoding='utf-8') as f:
            f.write('# Netscape HTTP Cookie File\n')
            f.write('.bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tabc123\n')
            f.write('.example.com\tTRUE\t/\tFALSE\t0\tfoo\tbar\n')
            f.write('b23.tv\tTRUE\t/\tFALSE\t0\txyz\ttoken\n')
            path = f.name
        try:
            c = bili.load_cookie(path)
            self.assertIn('SESSDATA=abc123', c)
            self.assertIn('xyz=token', c)
            self.assertNotIn('foo=bar', c)
        finally:
            os.unlink(path)

    def test_none(self):
        self.assertIsNone(bili.load_cookie(None))
        self.assertIsNone(bili.load_cookie(''))


class TestPicking(unittest.TestCase):
    def test_pick_audio_prefers_30216(self):
        tracks = [
            {'id': 30232, 'bandwidth': 130000},
            {'id': 30216, 'bandwidth': 66000},
        ]
        self.assertEqual(bili.pick_audio(tracks)['id'], 30216)

    def test_pick_audio_fallback_min_bandwidth(self):
        tracks = [
            {'id': 30232, 'bandwidth': 130000},
            {'id': 30280, 'bandwidth': 66000},
        ]
        self.assertEqual(bili.pick_audio(tracks)['id'], 30280)

    def test_pick_video_prefers_resolution_then_avc(self):
        tracks = [
            {'id': 32, 'width': 852, 'height': 480, 'codecs': 'hev1.1.6.L120.90', 'bandwidth': 90000},
            {'id': 16, 'width': 852, 'height': 480, 'codecs': 'avc1.64001E', 'bandwidth': 100000},
            {'id': 80, 'width': 1280, 'height': 720, 'codecs': 'avc1.64001E', 'bandwidth': 200000},
        ]
        pick = bili.pick_video(tracks)
        self.assertEqual(pick['id'], 80)  # 720p 优先

    def test_pick_video_same_res_prefers_avc(self):
        tracks = [
            {'id': 32, 'width': 852, 'height': 480, 'codecs': 'hev1.1.6.L120.90', 'bandwidth': 90000},
            {'id': 16, 'width': 852, 'height': 480, 'codecs': 'avc1.64001E', 'bandwidth': 100000},
        ]
        self.assertEqual(bili.pick_video(tracks)['id'], 16)  # avc 优先于 HEVC


class TestUtil(unittest.TestCase):
    def test_ts(self):
        self.assertEqual(bili.ts(0), '00:00:00')
        self.assertEqual(bili.ts(65), '00:01:05')
        self.assertEqual(bili.ts(3661), '01:01:01')

    def test_safe_filename(self):
        self.assertEqual(bili.safe_filename('a/b:c*d'), 'a_b_c_d')
        self.assertEqual(bili.safe_filename('  video  '), 'video')
        self.assertTrue(bili.safe_filename('').strip())

    def test_page_cid(self):
        info = {'cid': 100, 'pages': [{'cid': 10}, {'cid': 20}]}
        self.assertEqual(bili.page_cid(info, 1), 10)
        self.assertEqual(bili.page_cid(info, 2), 20)
        with self.assertRaises(bili.BiliError):
            bili.page_cid(info, 3)


if __name__ == '__main__':
    unittest.main()
