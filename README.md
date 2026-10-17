# bilibili-video-summary

[![CI](https://github.com/Erfan817/bilibili-video-summary/actions/workflows/ci.yml/badge.svg)](https://github.com/Erfan817/bilibili-video-summary/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Local](https://img.shields.io/badge/transcribe-100%25%20local-brightgreen.svg)](#特点)

**一条命令，把 B 站视频变成逐句稿。** 纯本地 Whisper 转写，不烧 token、不上传音频；按需还能**看懂画面**——PPT 表格、板书、真题选项这些只存在于画面上的信息，音频转写永远拿不到。

```bash
$ bvs BV1PE411h7b4 --srt
```

![demo](assets/demo.gif)

**中文** | [English](README.en.md)

---

## 30 秒上手

```bash
pip install faster-whisper numpy Pillow   # 核心依赖，不需要 ffmpeg
pip install -e .                          # 装上 bvs 命令

bvs BV1PE411h7b4                          # 出 transcript.txt
bvs https://b23.tv/xxxx --srt             # 短链 + SRT 字幕
bvs BV1xx411c7mD --frames --frames-mode dense   # 网课/PPT：加画面模式
```

一条命令跑完全链路：**解析链接 → 取元信息 → 下音频 → 本地转写 → 同音字校正 → 出稿 → 清理中间产物**。
不依赖任何 agent，`transcript.txt` 直接落地。

---

## 三种用法，同一套内核

| 用法 | 适合 | 入口 |
|---|---|---|
| **一键 CLI** | 人要一份逐句稿，不想装 agent | `bvs <链接>` |
| **Agent 技能** | 要「结论先行的结构化总结」+ 读图融合 | [`SKILL.md`](SKILL.md) |
| **MCP server** | 让你的 IDE / agent 直接调这个能力 | [`mcp_server.py`](mcp_server.py) |

> 分工：**CLI 出素材**（逐句稿 / SRT / 关键帧 / 元信息），**agent 出结论**（提炼、成文、读图）。
> 这正是从「技能」到「工具」的分水岭——没有 agent，链路照样闭环。

---

## 它比同类多做了什么

| 能力 | 说明 |
|---|---|
| **B 站 AI 字幕快路径** | 给了 cookie 且该视频有 AI 字幕时，**直接取字幕秒出稿**，完全跳过 Whisper；没有再回退本地转写 |
| **多平台（yt-dlp 后端）** | 非 B 站链接（YouTube 等）自动走 yt-dlp，同一套转写/校正/产出 |
| **画面上限解锁** | `--cookie` 解锁未登录只能拿到的 480p 上限，PPT 小字更清楚 |
| **同音字校正众包表** | 校正规则抽成 `corrections.json`，**按置信度分级**，欢迎 PR（见下） |
| **无 agent 也能校正** | `high` 项自动替换，`context` 项**只标记不替换**，逐行列进审查清单 |
| **繁→简自动归一** | Whisper 常混出繁体字（「打電話 / 報喜不報憂」），`zhconv` 归一解决 |
| **防重复劳动** | 已有产物自动跳过（`--force` 重来），`--json` 给下游/MCP 消费 |

---

## 安装

### 依赖

```bash
pip install faster-whisper numpy Pillow
pip install -e .          # 得到全局 bvs 命令
```

- Python 3.10+
- **不需要 ffmpeg** —— faster-whisper 自带 PyAV 解码，转写和抽帧都用不上
- `zhconv`（繁→简归一，随核心依赖一起装）
- 可选：`pip install yt-dlp`（多平台）、`pip install "mcp[cli]"`（MCP server）

### 模型

用环境变量指向本地已落盘的 faster-whisper 模型目录：

```bash
export WHISPER_MODEL_DIR=/path/to/faster-whisper-small
```

不设则回退到模型名 `small`（由 faster-whisper 自动下载）。

> ⚠️ **Windows 注意**：走 HuggingFace 自动下载会拿到 0 字节软链，ctranslate2 会报
> `File model.bin is incomplete`。建议先手动把模型落盘再指过来（见[踩坑记录](#踩坑记录)）。

---

## CLI 用法

```
bvs <BV号|av号|bilibili链接|b23.tv短链|其他平台链接> [选项]
```

| 选项 | 默认 | 说明 |
|---|---|---|
| `--p N` | 1 | 分 P 序号 |
| `-o, --out DIR` | `./outputs/<标题>` | 输出目录 |
| `--model NAME\|DIR` | `$WHISPER_MODEL_DIR` 或 `small` | 模型名或本地目录 |
| `--lang zh\|en\|auto` | `zh` | `auto` 交给模型自动检测 |
| `--topic 关键词` | 视频标题 | 喂给 `initial_prompt`，显著降低术语错误 |
| `--cookie FILE\|STR` | — | cookies.txt 路径或 `SESSDATA=..; ..`，用于字幕快路径 + 高清流 |
| `--no-subtitle` | 关 | 禁用字幕快路径，强制本地转写 |
| `--srt` | 关 | 额外输出 SRT 字幕 |
| `--frames` | 关 | 画面模式：下载视频流 + 抽关键帧 |
| `--frames-mode scene\|dense` | `scene` | 对谈用 `scene`，**课件/PPT 必须用 `dense`** |
| `--dense-interval S` / `--max-frames N` | 8 / 60 | dense 采样间隔 / 候选帧上限 |
| `--no-correct` | 关 | 跳过同音字校正 |
| `--no-simplify` | 关 | 跳过繁→简归一（默认装了 zhconv 就做） |
| `--keep` | 关 | 保留中间产物（默认跑完即删） |
| `--force` | 关 | 忽略已有产物，重新下载/转写 |
| `--json` | 关 | 输出机器可读结果（脚本 / MCP 用） |
| `--threads N` | CPU 核数一半 | Whisper 线程数 |

### 产出物

```
outputs/<标题>/
├── transcript.txt      # 带时间戳逐句稿
├── transcript.srt      # SRT 字幕（--srt）
├── summary.md          # 元信息 + 逐句稿引用 + 同音字审查清单
├── summary.json        # 机器可读结果
├── frames/             # 关键帧（--frames）
└── frames_index.txt    # 帧时间戳 + 变化指标
```

点这里看[示例输出](examples/README.md)。

---

## 工作流程

```
B 站链接 ──┬─→ 有 cookie 且有 AI 字幕？ ─→ 取字幕（秒出）────────┐
           │                                                      │
           └─→ 下音频流 ─→ 本地 Whisper ─→ 同音字校正 ────────────┼─→ transcript.txt / .srt
                                                                  │   summary.md / summary.json
   开启 --frames：下视频流 ─→ 抽帧 ─→ frames/ + frames_index.txt ─┘
```

### 画面模式该不该开

| 视频类型 | 画面信息量 | 建议 |
|---|---|---|
| 网课 / PPT / 板书 | 极高 | **开**（`--frames-mode dense`） |
| 代码演示 / IDE 操作 | 高 | **开** |
| 图表、数据、公式推导 | 高 | **开** |
| 纯对谈 / 播客 | 低 | 不开，白烧算力 |
| 无口播的画面流 | — | **开**，画面是唯一信息源 |

---

## 同音字校正（欢迎 PR）

Whisper 对中文的误识别很有规律。校正规则抽成了 [`bvs_core/corrections.json`](bvs_core/corrections.json)，
**加词条就是一个 PR**：

```json
{
  "from": ["维德根斯坦", "维德克斯坦", "维德根兰"],
  "to": "维特根斯坦",
  "confidence": "high",
  "note": "哲学家"
}
```

### 为什么分两级

机械替换会误伤——**「奇异」在数学语境下本来就是对的**。所以：

| confidence | 行为 | 例子 |
|---|---|---|
| `high` | **自动替换**（错得稳定的多字误识别） | 维德根斯坦 → 维特根斯坦 |
| `context` | **只标记，不替换**，逐行列进审查清单 | 奇异 → 歧义（需人/AI 判断） |

CLI 输出会带审查清单，把「看起来对、实际错」的风险交回给人：

```
wrote transcript.txt.corrected  (auto-fixed 2 lines, context-review 1 lines)
  L1  加瓦->Java x1
  L3  维德根斯坦->维特根斯坦 x1

-- context 审查清单(未自动替换, 需人/AI 逐句判断) --
  L2 [奇异->歧义] [00:00:05] 这个矩阵是奇异的大家别担心
```

> 也可以单独跑：`python -m bvs_core.correct transcript.txt`
>
> **提交词条前请确认**：`high` 只放「错得稳定、不会误伤」的多字词；拿不准的一律用 `context`。

---

## 实测数据

8 线程 CPU / int8 量化 / small 模型：

### 转写耗时

| 音频时长 | 模型加载 | 转写 | 合计 | 30216 音轨体积 |
|---|---|---|---|---|
| 9 分钟 | ~10s | 60~90s | ~2 分钟 | ~3 MB |
| 4 分钟 | ~1.3s | 33s | ~35s | 1.2 MB |
| 55 分钟 | ~10s | ~7.5 分钟 | ~8 分钟 | 25.7 MB |

### 抽帧（课件类，20 分钟视频）

| 项 | 值 |
|---|---|
| 视频流体积 | 12.4 MB（480p，静态 PPT 码率极低） |
| 解码 | 36425 帧约 30 秒 |
| dense 抽帧 | 8 秒间隔 → 70 帧候选，其中 22 帧为真正的内容切换 |
| 单帧体积 | JPEG(q85) 约 40~110 KB |

> **清晰度结论**：480p（852×480）对 PPT 课件**完全够用**——表格正文和手写批注都清晰可读，不必为 1080p 折腾 cookie。

---

## 踩坑记录

1. **视频流按分辨率挑，不是按带宽最小** —— 静态 PPT 的 480p 只有 85 kbps，和 360p 差不了几 MB，但分辨率决定小字能不能读。
2. **抽帧必须双指标** —— 只用 MAE 会把人物微表情全抓进来（实测 316 秒出 182 张，等于没筛）。加上「变化像素比例」后降到 71 张。
3. **课件类必须用 dense 模式** —— PPT 一行行往外蹦时整屏变化很小，scene 模式的阈值一高就全漏。
4. **变化大 ≠ 信息多** —— 过场动画、留白转场同样触发高 MAE，最终必须靠读图人工筛。
5. **文件不完整会解码报错**（`InvalidDataError`）—— 截断下载时要用 try/except 包住 decode 循环，保住已解出的帧。
6. **必须显式关掉 PyAV 容器** —— 否则 Windows 上 `video.m4s` 句柄不释放，跑完清理会静默失败，残留上百 MB。
7. **画面能抓到 ASR 的硬错误** —— 实测转写把 POP3 端口识别成「120」，画面写的是 **110**。数字和缩写靠音频分辨不出来。
8. **别用 `| tail` 包住后台转写命令** —— 管道全缓冲会让后台任务看起来像卡死。查进度用 `wc -l transcript.txt`。
9. **HF 模型下载会拿到 0 字节软链** —— 必须手动落盘（`HF_HUB_DISABLE_XET=1` + `HF_ENDPOINT=https://hf-mirror.com`）。
10. **Whisper 会在中文里混出繁体字**（实测「打電話 / 報喜不報憂」）—— 光在 `initial_prompt` 里要求简体**不够**，要确定性修复得装 `zhconv`（纯 Python、几十 KB）。装上后 `bvs` 自动做繁→简归一，没装则在检出繁体时提示你装。
11. **未登录最高只有 480p，且字幕接口返回空数组** —— 两者都要 cookie 才能解决（`--cookie`）。
12. **B 站搜索接口容易 412** —— 风控会拦；`bili.py` 会把 412 翻译成人话并提示加 cookie。

---

## 为什么不用 B 站字幕接口

`api.bilibili.com/x/player/v2` 返回的 `subtitle.subtitles` 在**未登录时几乎都是空数组**
（`need_login_subtitle: true`）——AI 字幕需要登录 cookie。评论接口也已要求 wbi 签名。

所以本项目的默认路径是**直接下音频本地 ASR**，最稳；有 cookie 时才把字幕当快路径用。

---

## 目录结构

```
bilibili-video-summary/
├── bvs.py                       # 一键 CLI 入口
├── bvs_core/
│   ├── bili.py                  # 链接解析 / 元信息 / 流挑选 / cookie / 下载 / 字幕
│   ├── transcribe.py            # 本地 Whisper 转写（+ SRT）
│   ├── frames.py                # 抽帧（scene / dense 双模式）
│   ├── correct.py               # 同音字校正引擎（high / context 分级）
│   ├── corrections.json         # 众包校正表（欢迎 PR）
│   └── pipeline.py              # 全链路编排 + CLI 参数
├── scripts/                     # 技能脚本（薄封装，用法见 SKILL.md）
│   ├── fetch_media.py
│   ├── transcribe.py
│   └── extract_frames.py
├── mcp_server.py                # MCP server（可选）
├── tools/make_demo_gif.py       # 生成 README 动图（可复现，不用录屏）
├── tests/                       # 单元测试（纯标准库，无网络）
├── examples/                    # 示例输出
├── SKILL.md                     # Agent 技能完整流程 / 参数 / 实测
└── assets/demo.gif              # README 顶部动图
```

### 跑测试

```bash
python -m unittest discover -s tests -v
```

---

## 相关项目

同类工具调研（2026-09）：

- [JefferyHcool/BiliNote](https://github.com/JefferyHcool/BiliNote) — 视频笔记领域星标最高的项目
- [ysyecust/lecture-to-notes](https://github.com/ysyecust/lecture-to-notes) — Claude Code skill，密集采样 + 面板几何测量
- [drpwchen/lecture-to-notes](https://github.com/drpwchen/lecture-to-notes) — 六级流水线 + 同步 HTML 查看器
- [asdhabdua/bilibili-video-notes-skill](https://github.com/asdhabdua/bilibili-video-notes-skill) — 抽帧 + OCR + 视觉打分 → DOCX

---

## License

MIT
