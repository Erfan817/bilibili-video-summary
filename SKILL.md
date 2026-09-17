---
name: bilibili-video-summary
description: 把 B 站视频转成文字并做结构化总结,按需还能看懂画面里的 PPT/板书/图表,用于生成可复习的学习笔记。适用于用户发来 bilibili.com / b23.tv 视频链接并要求「总结一下视频内容」「视频讲了什么」「帮我提炼要点」,也用于网课/讲课类视频整理考点笔记。流程:取视频元信息 → 取音频/视频流 → 本地 Whisper 转写 → 校正同音字 →(可选,讲课类必开)抽帧读图理解画面 → 输出 Markdown 总结 + 逐句稿。不需要登录、不需要 cookie、不依赖第三方字幕站。
agent_created: true
---

# B 站视频转写与总结

## 为什么不走字幕接口

`api.bilibili.com/x/player/v2` 返回的 `subtitle.subtitles` 现在**几乎都是空数组**(`need_login_subtitle: true`)——AI 字幕需登录 cookie。评论接口 `/x/v2/reply` 也已要求 wbi 签名,裸调返回 `code -400`。
**所以直接下音频本地 ASR,最稳。**

## 环境(已就绪,勿重复安装)

### 通用要求

| 依赖 | 说明 |
|---|---|
| Python 3.10+ | 需要 `faster-whisper`、`numpy`、`Pillow` |
| Whisper 模型 | faster-whisper 模型目录。用环境变量 `WHISPER_MODEL_DIR` 指向它;不设则回退到模型名 `small`(自动下载) |
| 线程数 | 环境变量 `WHISPER_THREADS` 可覆盖,默认取 CPU 核数一半 |
| ffmpeg | **不需要** —— PyAV 自带解码,转写和抽帧都用不上 |

### 本机路径(作者机器配置,换台机器请自行替换)

| 项 | 路径 |
|---|---|
| Python venv | `D:\.workbuddy\binaries\python\envs\whisper\Scripts\python.exe` |
| Whisper 模型目录 | `D:\.workbuddy\models\faster-whisper-small`(已手动落盘,勿走 HF 自动下载) |

> 模型 487MB,别放进会话工作区。**Windows 上走 HF 自动下载会拿到 0 字节软链**,必须手动落盘再用 `WHISPER_MODEL_DIR` 指过去。

### 脚本

| 脚本 | 用法 |
|---|---|
| `scripts/fetch_media.py` | `<工作目录> [audio\|video\|both]` —— 下载音视频流 |
| `scripts/transcribe.py` | `<工作目录> "<视频主题>" [语言]` —— 本地 Whisper 转写 |
| `scripts/extract_frames.py` | `<工作目录> [--mode dense\|scene] [--max-frames N] ...` —— 抽帧 |

### 全流程速查

```bash
# 本机路径,换机器请替换
PY="D:/.workbuddy/binaries/python/envs/whisper/Scripts/python.exe"
S="D:/.workbuddy/skills/bilibili-video-summary/scripts"
export WHISPER_MODEL_DIR="D:/.workbuddy/models/faster-whisper-small"

cd <工作目录>
# 1) 取 view.json / playurl.json (PowerShell, 见步骤 1-2)
"$PY" "$S/fetch_media.py" . both                    # 2) 下音频+视频
"$PY" "$S/transcribe.py" . "视频主题关键词"           # 3) 转写(后台跑)
"$PY" "$S/extract_frames.py" . --mode dense --dense-interval 8 --max-frames 80   # 4) 抽帧
# 5) 逐帧 Read 读图 → 6) 写总结 → 7) 收尾清理
```

## 步骤

### 1. 取 bvid / aid / cid

```bash
# PowerShell 可用,curl 在本沙箱常被拦
$h=@{'User-Agent'='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36';'Referer'='https://www.bilibili.com/'}
Invoke-WebRequest -Uri 'https://api.bilibili.com/x/web-interface/view?bvid=BV号' -Headers $h -UseBasicParsing |
  Select-Object -ExpandProperty Content | Out-File -Encoding utf8 view.json
```

- 短链 `b23.tv` 先跟 302 拿到真实 BV 号。
- **坑**:PowerShell `Out-File -Encoding utf8` 会写 BOM,Python 读必须用 `encoding='utf-8-sig'`。
- 从 `data.cid` 拿 cid;分 P 视频取 `data.pages[n].cid`。

### 2. 取音频流地址

`https://api.bilibili.com/x/player/playurl?bvid=..&cid=..&fnval=16&fourk=1`

取 `data.dash.audio` 里 **id=30216**(43kbps,最小,ASR 够用)。带 `Referer`+`Origin`+`Range: bytes=0-` 下载 `baseUrl`,落地为 `audio.m4s`(9 分钟视频约 3MB)。

### 3. 转写

```python
import os
from faster_whisper import WhisperModel
model = WhisperModel(os.environ.get("WHISPER_MODEL_DIR") or "small",
                     device="cpu", compute_type="int8", cpu_threads=4)
segments, info = model.transcribe("audio.m4s", language="zh", beam_size=5,
    vad_filter=True, vad_parameters=dict(min_silence_duration_ms=400),
    initial_prompt="以下是普通话视频内容,主题是……",   # 填视频主题,显著降低术语错误
    condition_on_previous_text=False)
```

- 不需要 ffmpeg——faster-whisper 自带 PyAV 直接解码 m4s。
- small 模型 CPU 跑 9 分钟音频约 60~90 秒,质量够用。

### 4. 同音字校正(必做)

Whisper 对计算机黑话错得很有规律,总结前按上下文替换:

| 识别结果 | 正确 |
|---|---|
| 双飞 / 双肥 | 双非 |
| 加瓦 | Java |
| 运为 | 运维 |
| 既往 | 计网(计算机网络) |
| 考工 / 考供 / 靠工 | 考公 |
| 审考 | 省考 |
| 求招 | 秋招 |
| 硬接生 / 应接生 | 应届生 |
| 事业边 | 事业编 |
| 九二 | 985/211 |
| 二三本 / 二文 / 23本 | 二本三本 |
| 大產 | 大厂 |
| 卷金 | 卷进 |
| 研炒电网 | 烟草、电网 |
| 贵源 | 柜员 |
| 新制高 | 薪资高 |
| 江泽广 | 江浙广 |

### 人名/术语(科普、对谈、人文类视频高发)

Whisper 对中文学术人名的识别同样错得很有规律。遇到这类视频,先按表替换:

| 识别结果 | 正确 |
|---|---|
| 维德根斯坦 / 维德克斯坦 / 维德根兰 / 维特兰 / 韦德格斯坦 / 维德根坂 | 维特根斯坦 |
| 埃斯坦 | 爱因斯坦 |
| 格德尔 | 哥德尔 |
| 图林 | 图灵 |
| 福勒伊德 | 弗洛伊德 |
| 杨乐坤 | 杨立昆(Yann LeCun) |
| 索拉迪 | 苏格拉底 |
| 天狱 | 天域(节目名,音译) |
| 天公(空间站) | 天宫 |
| 清厚大学 | 清华大学 |
| 常庭教授 / 常聘教授 | 长聘教授 |
| 高刺分布 | 高斯分布 |
| 政態分布 / 正態分布 | 正态分布 |
| 可减严事实 / 科检验事实 / 可检验实施 | 可检验事实 |
| 陳書 / 陳數 / 陈数 | 陈述 |
| 超業 / 超厌 | 超验 |
| 莫会的知识 / 莫辉的知识 | 默会知识(tacit knowledge) |
| 奇异 | 歧义 |
| 权势 | 诠释 |
| 品用 / 屏用 / 平用 / 匹用 | 平庸 |
| 28定律 | 二八定律 |
| 咸侠 | 闲暇 |
| 萌萌肚肚 / 萌萌咚咚 | 懵懵懂懂 |
| 迁移军动 | 情不自禁 |
| 不能反映 | 不能繁衍 |
| 升娃 | 生娃 |
| 莫過於 | 莫过于 |

> **重要**:机械替换容易误伤——"奇异"在数学语境下本来就对,"权势"在其他语境也可能是对的。**必须逐句结合上下文判断**,不能无脑全局替换。做法:先按表批量替换,再通读一遍做修正。

## 转写耗时参考(8 线程 CPU / int8 / small)

| 音频时长 | 模型加载 | 转写 | 合计 | 30216 音轨体积 |
|---|---|---|---|---|
| 9 分钟 | ~10s | 60~90s | ~2 分钟 | ~3MB |
| 55 分钟 | ~10s | ~7.5 分钟 | ~8 分钟 | 25.7MB |

## 踩坑记录

1. **HF 模型下载会拿到 0 字节软链**:`snapshot_download` 在 Windows 上生成 symlink,`os.path.getsize` 读回 0,ctranslate2 报 `File model.bin is incomplete`。
   修法:读 `<model>/trees/<rev>.json`,`model.bin` 用 `lfs_sha256`、其余用 `blob_id` 去 `blobs/` 里 `copy2` 成实体文件。
   **用 `HF_HUB_DISABLE_XET=1` + `HF_ENDPOINT=https://hf-mirror.com`**(hf-mirror 可直连,PyPI 用 `https://pypi.tuna.tsinghua.edu.cn/simple`)。
2. **别往已有大 venv 里 pip install**:`envs/default` 依赖多,pip 回退求解跑了 10 分钟没结束。**新建空 venv 装 faster-whisper 只需约 1 分钟**(实际依赖:ctranslate2 / av / onnxruntime / huggingface-hub,共 25 个包)。
3. **模型别留在会话工作区**:487MB,会污染 workspace。落到一个固定的模型目录(本机用 `D:\.workbuddy\models\`,并用 `WHISPER_MODEL_DIR` 指过去),下载临时缓存用完即删。
4. **别用 `| tail -40` 包住后台转写命令**:管道会把 stdout 全缓冲,后台任务跑着的时候 `TaskOutput` 拿不到任何输出(看起来像卡死)。要进度就让输出直接落终端/文件;更省事的做法是**忽略 stdout,用 `wc -l transcript.txt` 查进度**——转写脚本本来就把每段写进文件并 flush,那才是最可靠的进度源。
5. 需要看时长和音轨前,先解析 `view.json` 的 `data.duration` 和 `playurl.json` 的 `data.dash.audio`。30216 不一定存在,取不到时按 `bandwidth` 升序挑最小的那条。

## 画面理解(按需开启,默认关闭)

音频转写**看不到任何画面**——PPT、板书、公式推导、代码、图表、书的封面全都拿不到。抽帧 + 多模态读图可以补上,但体积和算力都大得多,所以做成开关。

### 什么时候开

| 视频类型 | 画面信息量 | 建议 |
|---|---|---|
| 网课 / PPT / 板书 | 极高 | **开** |
| 代码演示 / IDE 操作 | 高 | **开** |
| 图表、数据、公式推导 | 高 | **开** |
| 纯对谈 / 播客 | 低 | 不开,白烧算力 |
| 无口播的画面流(纯演示) | — | **开**,此时画面是唯一信息源 |

判断依据:用户明确说"要看画面",或视频标题/简介指向讲课、教程、代码、实验。拿不准就问。

### 流程

1. 从 `playurl.json` 的 `data.dash.video` 挑 **avc1(H.264) 里 bandwidth 最小**的那条
   - **未登录状态最高只能拿到 480p**。看 PPT 上的小字可能不够清楚,需要 1080p 就得有登录 cookie
   - HEVC(hvc1) 体积更小但解码兼容性差,优先 avc1
2. 下载视频流 —— 体积约为音频的 **4~6 倍**(54 分钟 480p 约 130MB)
3. 跑 `scripts/extract_frames.py <工作目录> [候选帧上限]`
4. **逐帧 Read 读图**,人工筛出有信息量的画面,剔除人物镜头和过场动画
5. 按时间戳把画面内容并入总结(例如"12:30 屏幕上给出的框架图是……")

### 实测数据(2026-09-17,TIANYU2FM E157 下)

| 项 | 值 |
|---|---|
| 视频流 | id=32, 852x480, avc1, 331 kbps |
| 单帧体积 | JPEG(q85) 约 40~70KB |
| 场景检测效果 | 316 秒 → 单 MAE 判据 182 张(**等于没筛**)→ 双指标 71 张 → 上限截取 30 张 |
| 解码速度 | 9488 帧约 20 秒 |

**案例 2:课件类 —— 软考第 12 P「计算机网络基础」,20 分钟**

| 项 | 值 |
|---|---|
| 视频流 | id=32, 852x480, avc1, **仅 85 kbps** —— 静态 PPT 录屏压得极狠 |
| 体积 | 20 分钟视频流只有 **12.4 MB** |
| dense 抽帧 | `--mode dense --dense-interval 8 --max-frames 80` → 70 帧,其中 **mae≥7 的 22 帧**才是真正的内容切换 |
| 解码速度 | 36425 帧约 30 秒 |
| **清晰度结论** | **480p(852×480)对 PPT 课件完全够用** —— 表格里的中文正文、老师手写的红笔批注全部清晰可读。**不必为了 1080p 去折腾 cookie** |
| 画面独有价值 | 纯音频拿不到:OSI 七层表(含层次↔设备对应)、IP 地址 A~E 类范围、IPv6 六特点、端口号表、真题的完整选项 |

### 关键经验

- **必须用双指标**判画面切换:64×64 灰度签名的 MAE **加上**变化像素比例 `(diff>20).mean()`。
  只用 MAE 会把人物微表情、口型变化全抓进来。**ratio ≥ 0.55** 才是真正的画面切换,MAE ≥ 25 作辅助
- **变化大 ≠ 信息多**:过场动画、留白转场同样触发高 MAE。必须靠读图人工判,别指望自动筛选
- **文件不完整会解码报错**(`avcodec_send_packet() InvalidDataError`)。截断下载时要用 try/except 包住 decode 循环,保住已解出的帧
- **画面里可能有硬字幕**:实测这期视频底部烧录了中文硬字幕,可以直接读数与 ASR 互校,**专有名词尤其准**。有硬字幕时可用它来订正人名
- **课件类必用 dense 模式**:scene 模式阈值一高就会漏掉"PPT 一行行往外蹦"的渐进变化。用 `--mode dense --dense-interval 8 --dense-mae-thresh 2.0`,再由读图人工筛
- **画面能抓到 ASR 的硬错误**:实测转写把 POP3 端口识别成"120",画面写的是 **110**。数字、缩写、人名这类靠音频根本听不出来的错误,读图可以直接订正
- **视频流按分辨率挑,不是按带宽最小**:静态 PPT 的 480p 只有 85kbps,和 360p 差不了几 MB,但少掉的分辨率直接决定小字能不能读
- **验证顺序**:先抽 8MB 左右的片段跑通链路(能覆盖几分钟),确认可解码、可读图,再决定要不要拖完整视频
- 复用已有 `video.m4s` 时脚本打印的流信息可能和实际解码分辨率不符(它打印的是 pick 的结果),看 `decode:` 那行才准
- 依赖:`PyAV`(whisper venv 自带) + `Pillow`(`pip install pillow`,已装)。**不需要 ffmpeg**

### 同类项目的经验(2026-09-17 调研,部分未在本机验证)

同类项目:`ysyecust/lecture-to-notes`(229★,Claude Code skill)、`drpwchen/lecture-to-notes`(104★)、`asdhabdua/bilibili-video-notes-skill`(46★)、`le876/bilibili-obsidian-notes`(9★)。这个方向全是个人项目,最高 229★,没有大项目——需求太个人化。

**两个已知硬限制的解决路径(值得做,尚未验证):**

1. **突破 480p 上限**:未登录探测 B 站会返回 **HTTP 412**,**从浏览器读 cookie** 就能拿 HD 流(yt-dlp 的 `--cookies-from-browser` 思路可借用)。本地实现,不需要扫码登录那一套。
2. **硬字幕当纠错词典**:`ocr_hardsubs.py` 的思路 —— OCR 读出画面烧录字幕 → 与 Whisper 结果比对 → 生成纠错词典**反向修正转写**。能把手写同音字表这件事自动化(`rapidocr-onnxruntime` 纯 CPU,无需 GPU)。

**三条设计经验(同行踩坑总结,直接采纳):**

- **分清职责**:文字靠 OCR / 清晰截图,语义靠看图。别指望多模态在 480p 下精确转录小字。
- **同音字校正要克制**:`drpwchen` 做过两次自动纠正**都退役了**——自动替换会引入"看起来对、实际错"的内容。可疑处应该**标记而非直接替换**。
- **抽帧策略按内容类型分**:`ysyecust` 用**每 15 秒密集采样**而不用纯场景检测,理由是"幻灯片渐进显示会被场景检测漏掉"。所以——**PPT/板书类用密集采样,对谈类才用场景检测**(已实现:脚本的 `--mode dense`,实测见上)

## 输出物

- `<标题>.md` —— 结构化总结(结论先行 + 表格/清单)
- `transcript.txt` —— 带时间戳逐句稿
- 总结里注明「基于自动转写、已做同音字校正」,别假装是原文

## 收尾清理(用户明确要求,必做)

**总结交付后立刻删掉所有中间产物,只留交付物。**

| 删除 | 保留 |
|---|---|
| `audio.m4s` · `video.m4s` · `frames/` · `frames_index.txt` · `view.json` · `playurl.json` · 任何临时脚本 | `<标题>.md` 总结 · `transcript.txt` 逐句稿 · 用户另外要求的交付物(如核心考点截图) |

理由:音频/视频/帧和元信息都属于用完即弃,脚本流程已固化在本技能里可随时重建。工作目录不该残留体积,也不该堆一次性脚本。

清理后 `ls` 一遍确认剩余文件,再向用户报告删了什么、释放了多少空间。用户点名要留的截图(如关键考点表)属于交付物,**不删**。
