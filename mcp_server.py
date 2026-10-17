"""MCP server: 把 bvs 全链路暴露成 MCP 工具, 供其他 agent / IDE 直接调用。

差异化亮点之一: 你的 Claude Code / Cursor / 任何支持 MCP 的客户端都能
`bvs.summarize_video(url)` 一键拿到 transcript + summary.json 路径。

运行:
    pip install "mcp[cli]"
    mcp run mcp_server.py            # MCP 官方 CLI 方式
    # 或
    python mcp_server.py             # 直接以 stdio 方式跑

未安装 mcp 时给出友好提示(该项目仍可正常当 CLI / 技能用)。
"""
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _summarize(url, **kwargs):
    """调用 bvs 全链路, 返回 JSON 结果。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [sys.executable, os.path.join(_HERE, 'bvs.py'), url,
               '--out', tmp, '--json']
        if kwargs.get('srt'):
            cmd.append('--srt')
        if kwargs.get('frames'):
            cmd.append('--frames')
        env = dict(os.environ)
        if kwargs.get('cookie'):
            env['BILI_COOKIE'] = kwargs['cookie']
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            return {'ok': False, 'error': proc.stderr.strip() or proc.stdout.strip()}
        try:
            return {'ok': True, 'result': json.loads(proc.stdout.strip().splitlines()[-1])}
        except Exception:
            return {'ok': True, 'stdout': proc.stdout[-2000:]}


def main():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print('需要安装 mcp: pip install "mcp[cli]"，再运行 mcp run mcp_server.py',
              file=sys.stderr)
        return 2

    mcp = FastMCP('bvs')

    @mcp.tool()
    def summarize_video(url: str, srt: bool = False, frames: bool = False,
                        cookie: str = '') -> str:
        """把 B 站(或任意平台)视频转写成结构化总结。

        Args:
            url: bilibili 链接 / BV 号 / b23.tv 短链 / 其他平台链接(yt-dlp)
            srt: 是否额外输出 SRT 字幕
            frames: 是否开启画面模式(下载视频流+抽关键帧, 较慢)
            cookie: 可选, 解锁高清流与 AI 字幕快路径(cookies.txt 路径或字符串)

        Returns:
            JSON 字符串: {ok, result:{title,bvid,source,transcript 路径,...}}
        """
        return json.dumps(_summarize(url, srt=srt, frames=frames, cookie=cookie),
                          ensure_ascii=False)

    mcp.run()


if __name__ == '__main__':
    sys.exit(main())
