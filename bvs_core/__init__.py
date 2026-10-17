"""bvs_core — bilibili-video-summary 的核心实现。

被三层共用:
  * bvs.py              一键 CLI(技能 → 工具的分水岭)
  * scripts/*.py        技能脚本(薄封装, 保持 SKILL.md 用法不变)
  * mcp_server.py       MCP server(可选差异化)

只用标准库 urllib + faster-whisper + PyAV, 不需要 ffmpeg。
"""

__version__ = '1.0.0'
