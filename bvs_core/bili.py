"""B 站 API 层: 链接解析 / 元信息 / 流挑选 / cookie 注入 / 下载 / 字幕。

被 bvs.py(一键 CLI)、scripts/*.py(技能脚本)、mcp_server.py 共用。
只用标准库 urllib, 不需要 ffmpeg。

设计要点(从 SKILL.md 踩坑记录固话而来):
  * 视频流按**分辨率**挑(不能只看带宽最小)—— 静态 PPT 480p 仅 85kbps, 省几 MB
    换糊掉的小字是亏的
  * 音频取 id=30216(最小码率, ASR 够用), 取不到按 bandwidth 升序挑最小
  * 未登录最高只能拿 480p; 有 cookie 可解锁 HD 流 + AI 字幕快路径
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      'Chrome/120 Safari/537.36')

BV_RE = re.compile(r'BV[0-9A-Za-z]{10}')
AV_RE = re.compile(r'av(\d+)', re.I)

API_VIEW = 'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'
API_PLAYURL = ('https://api.bilibili.com/x/player/playurl?bvid={bvid}'
               '&cid={cid}&fnval=16&fourk=1')
DEFAULT_TIMEOUT = 30


class BiliError(Exception):
    """B 站 API / 网络层错误, 带面向用户的中文信息。"""


# ---------------------------------------------------------------------------
# cookie 处理
# ---------------------------------------------------------------------------

def load_cookie(cookie):
    """把 cookie 参数归一化成 `name=value; name2=value2` 字符串。

    cookie 可以是:
      * None / 空      -> 返回 None(不注入)
      * 已存在的路径    -> 按 Netscape cookies.txt 格式解析(yt-dlp 同款)
      * "SESSDATA=..; bili_jct=.."  字符串 -> 原样规整后返回

    cookies.txt 每行 7 个 tab 分隔字段:
    domain  includeSubdomains  path  secure  expiry  name  value
    """
    if not cookie:
        return None
    if os.path.isfile(cookie):
        return _parse_netscape(cookie)
    s = cookie.strip()
    if not s:
        return None
    # 规整: 去掉多余空白, 确保分号后有一个空格, 便于拼进 header
    parts = [p.strip() for p in s.split(';') if p.strip()]
    return '; '.join(parts)


def _parse_netscape(path):
    pairs = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            fields = line.split('\t')
            if len(fields) < 7:
                continue
            domain, _inc, _path, _secure, _exp, name, value = fields[:7]
            if not name or not value:
                continue
            # 只关心 b 站相关域, 顺手保留 b23.tv
            if any(d in domain for d in ('.bilibili.com', '.b23.tv',
                                         'bilibili.com', 'b23.tv')):
                pairs.append('%s=%s' % (name, value))
    if not pairs:
        raise BiliError('cookie 文件 %s 里没有找到 bilibili 相关条目' % path)
    return '; '.join(pairs)


def _headers(extra=None, cookie=None):
    h = {'User-Agent': UA, 'Referer': 'https://www.bilibili.com/',
         'Origin': 'https://www.bilibili.com'}
    if cookie:
        h['Cookie'] = cookie
    if extra:
        h.update(extra)
    return h


# ---------------------------------------------------------------------------
# 链接解析
# ---------------------------------------------------------------------------

def parse_link(link):
    """把任意用户输入解析成 {'bvid'|'aid', 'page', 'url'}。

    支持:
      * 裸 BV 号        BV1xx411c7mD
      * 裸 av 号        av170001 / 170001
      * 完整视频页      https://www.bilibili.com/video/BV1xx411c7mD/?p=2
      * b23.tv 短链     https://b23.tv/xxxxx  (跟随 302, 不用第三方解链)
      * 其他平台链接    原样保留 url, 留给 yt-dlp 后端处理
    """
    link = (link or '').strip()
    if not link:
        raise BiliError('空的链接/BV 号')

    # 裸 BV 号
    m = BV_RE.search(link)
    if m and link == m.group(0):
        return {'bvid': m.group(0), 'page': 1, 'url': link}

    # 裸 av 号
    m = AV_RE.search(link)
    if m and (link == m.group(0) or link == m.group(1)):
        return {'aid': m.group(1), 'page': 1, 'url': link}

    # 需要网络解析的 URL
    url = _normalize_url(link)
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(h in host for h in ('bilibili.com', 'b23.tv')):
        return _parse_bili_url(url)
    # 其他平台 -> 交给 yt-dlp
    return {'url': url, 'page': 1, 'external': True}


def _normalize_url(link):
    if not re.match(r'^https?://', link, re.I):
        if BV_RE.match(link):
            return 'https://www.bilibili.com/video/%s/' % link
        if AV_RE.match(link):
            return 'https://www.bilibili.com/video/%s/' % link.upper()
        link = 'https://' + link
    return link


def _parse_bili_url(url):
    """解析 bilibili 视频页 / b23.tv 短链, 返回 bvid/aid + page。"""
    # b23.tv 短链: 直接跟随 302 拿最终地址
    if 'b23.tv' in urllib.parse.urlparse(url).netloc.lower():
        try:
            req = urllib.request.Request(url, headers=_headers())
            resp = urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT)
            url = resp.geturl()
        except urllib.error.HTTPError as e:
            # 302 链上的 location 也可能直接给我们目标页
            loc = e.headers.get('Location')
            if loc:
                url = urllib.parse.urljoin(url, loc)
            else:
                raise BiliError('b23.tv 短链解析失败: HTTP %s' % e.code)

    q = urllib.parse.urlparse(url)
    page = 1
    for k, v in urllib.parse.parse_qsl(q.query):
        if k == 'p':
            try:
                page = int(v)
            except ValueError:
                pass

    m = BV_RE.search(url)
    if m:
        return {'bvid': m.group(0), 'page': page, 'url': url}
    m = AV_RE.search(url)
    if m:
        return {'aid': m.group(1), 'page': page, 'url': url}
    raise BiliError('无法从链接里识别 BV/av 号: %s' % url)


# ---------------------------------------------------------------------------
# 元信息
# ---------------------------------------------------------------------------

def _get_json(url, cookie=None, extra_headers=None, timeout=DEFAULT_TIMEOUT):
    req = urllib.request.Request(url, headers=_headers(extra_headers, cookie))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 412:
            raise BiliError('B 站返回 412(疑似风控/未登录)。试加 --cookie 解锁。')
        raise BiliError('HTTP %s @ %s' % (e.code, url))
    except urllib.error.URLError as e:
        raise BiliError('网络错误: %s' % e.reason)

    # 兼容 PowerShell Out-File 写出的 BOM
    text = raw.decode('utf-8-sig', errors='replace')
    data = json.loads(text)
    if data.get('code') not in (0, None):
        raise BiliError('B 站 API 返回错误 code=%s msg=%s @ %s'
                        % (data.get('code'), data.get('message'), url))
    return data['data']


def fetch_view(bvid=None, aid=None, cookie=None):
    """取视频元信息: 标题/时长/cid/简介/分P 列表/UP主。"""
    if bvid:
        url = API_VIEW.format(bvid=bvid)
    elif aid:
        url = API_VIEW.replace('bvid={bvid}', 'aid={aid}').format(aid=aid)
    else:
        raise BiliError('fetch_view 需要 bvid 或 aid')
    d = _get_json(url, cookie)
    info = {
        'bvid': d.get('bvid'),
        'aid': str(d.get('aid', '')),
        'title': d.get('title', ''),
        'desc': d.get('desc', ''),
        'duration': d.get('duration', 0),
        'owner': (d.get('owner') or {}).get('name', ''),
        'pic': d.get('pic', ''),
        'cid': d.get('cid'),
        'pages': d.get('pages', []),
    }
    return info


def page_cid(info, page=1):
    """取指定分P 的 cid; 分P 索引越界时抛错。"""
    pages = info.get('pages') or []
    if page < 1 or page > len(pages):
        raise BiliError('分P p=%d 超出范围(共 %d P)' % (page, max(1, len(pages))))
    return pages[page - 1].get('cid') or info.get('cid')


def fetch_playurl(bvid, cid, cookie=None):
    """取音视频流列表 + 字幕信息。"""
    d = _get_json(API_PLAYURL.format(bvid=bvid, cid=cid), cookie)
    return d


# ---------------------------------------------------------------------------
# 流挑选
# ---------------------------------------------------------------------------

def pick_audio(tracks):
    """取 id=30216(最小码率, ASR 够用), 取不到按 bandwidth 升序挑最小。"""
    for t in tracks:
        if t.get('id') == 30216:
            return t
    return min(tracks, key=lambda t: t.get('bandwidth') or 10 ** 9)


def pick_video(tracks):
    """分辨率优先, 同分辨率取带宽最小; 优先 avc1(H.264, 解码兼容性最好)。

    注意: 不能只看带宽最小 —— 静态 PPT 的 480p 只有 85kbps, 和 360p 差不了几
    MB, 但分辨率直接决定小字能不能读。
    """
    avc = [t for t in tracks if (t.get('codecs') or '').startswith('avc1')]
    pool = avc or tracks
    return max(pool, key=lambda t: ((t.get('width') or 0) * (t.get('height') or 0),
                                    -(t.get('bandwidth') or 0)))


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------

def download(url, path, cookie=None, show_progress=True):
    """下载到本地, 支持 Range 续传(已有部分文件则断点续传)。

    返回实际写入的字节数。
    """
    existing = os.path.getsize(path) if os.path.exists(path) else 0
    headers = {'Range': 'bytes=%d-' % existing}
    req = urllib.request.Request(url, headers=_headers(headers, cookie))
    total = existing
    last_print = 0.0
    try:
        with urllib.request.urlopen(req, timeout=120) as r, \
                open(path, 'ab' if existing else 'wb') as f:
            while True:
                b = r.read(1 << 16)
                if not b:
                    break
                f.write(b)
                total += len(b)
                if show_progress:
                    now = time.time()
                    if now - last_print > 0.5:
                        print('  %.1f MB...' % (total / 1048576),
                              end='\r', flush=True)
                        last_print = now
    except urllib.error.HTTPError as e:
        if e.code in (416,):  # Range 越界 = 文件已完整
            return total
        raise BiliError('下载失败 HTTP %s' % e.code)
    if show_progress:
        print('', flush=True)
    return total


# ---------------------------------------------------------------------------
# 字幕(快路径)
# ---------------------------------------------------------------------------

def fetch_subtitles(playurl_data, cookie=None):
    """从 playurl 响应里取 AI 字幕正文。

    playurl_data['subtitle']['subtitles'] 无 cookie 时几乎总是 None/空数组;
    有 cookie 时许多视频会返回 AI 字幕(need_login_subtitle=false)。

    返回 [{'from': float, 'to': float, 'content': str}, ...]; 没有则返回 None。
    """
    subs = ((playurl_data.get('subtitle') or {}).get('subtitles') or [])
    if not subs:
        return None
    # 优先中文; 其次第一个
    subs = sorted(subs, key=lambda s: 0 if (s.get('lan') or '').startswith('zh') else 1)
    item = subs[0]
    url = item.get('subtitle_url') or item.get('ai_subtitle_url')
    if not url:
        return None
    if url.startswith('//'):
        url = 'https:' + url
    try:
        d = _get_json(url, cookie, timeout=30)
    except Exception:
        return None
    body = d.get('body') or []
    if not body:
        return None
    return body


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def ts(seconds):
    m, sec = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return '%02d:%02d:%02d' % (h, m, sec)


def safe_filename(name, maxlen=80):
    """把视频标题变成安全的目录/文件名。"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', '_', name or 'video').strip(' ._')
    return name[:maxlen] or 'video'
