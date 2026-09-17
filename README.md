# bilibili-video-summary

给 B 站视频做结构化总结的 **agent skill**（也适用于 Claude Code / Codex 等支持 SKILL.md 的 agent）。

纯本地转写，不依赖任何云端服务。按需还能**看懂画面**——PPT 表格、板书、真题选项这些只存在于画面上的信息，音频转写永远拿不到。

---

## 它能做什么

| 场景 | 产出 |
|---|---|
| 对谈 / 播客 | 结构化总结 + 带时间戳的逐句稿 |
| 网课 / 讲课视频 | 考点笔记 + 关键画面截图（表格、板书、图表） |
| 代码演示 / 技术分享 | 要点提炼 + 屏幕内容摘录 |

**三个产出物**：
- `<标题>.md` —— 结论先行的结构化总结
- `transcript.txt` —— 带时间戳的逐句稿
- （可选）关键画面截图 —— 只在开启画面模式时产生

---

## 特点

- **纯本地**：音频/视频不出本机，隐私零风险
- **零成本**：本地 Whisper 转写，不烧 API token
- **不用登录、不用 cookie**：绕开 B 站字幕接口（现在几乎全是空数组）
- **同音字校正**：内置两套校正表，专门对付 Whisper 对中文黑话和学术人名的规律性误识别
- **按需看懂画面**：多模态读图，能把 PPT 表格、板书、真题选项还原进笔记
- **双抽帧模式**：对谈类用场景检测，课件类用密集采样
- **自动收尾**：交付后清理全部中间产物，工作目录不留垃圾

---

## 快速开始

### 依赖

```bash
pip install faster-whisper numpy Pillow
```

- Python 3.10+
- **不需要 ffmpeg** —— PyAV 自带解码，转写和抽帧都用不上

### 模型

用环境变量指向本地已落盘的 faster-whisper 模型目录：

```bash
export WHISPER_MODEL_DIR=/path/to/faster-whisper-small
```

不设则回退到模型名 `small`（由 faster-whisper 自动下载）。

> ⚠️ **Windows 注意**：走 HuggingFace 自动下载会拿到 0 字节软链，ctranslate2 会报 `File model.bin is incomplete`。建议先手动把模型落盘再指过来。

### 可选配置

```bash
export WHISPER_THREADS=8    # 默认取 CPU 核数一半
```

---

## 工作流程

```
1. 取视频元信息（bvid / cid）
2. 取音频流 → 下载 audio.m4s
3. 本地 Whisper 转写 → transcript.txt
4. 同音字校正（计算机黑话 + 学术人名）
5. [按需] 取视频流 → 抽帧 → 逐帧读图理解画面
6. 融合成结构化总结
7. 清理全部中间产物
```

### 不开画面模式时

```
B 站链接 → 音频流 → Whisper → 校正 → Markdown 总结
```

### 开启画面模式时

```
B 站链接 → 音频流 → Whisper ─┐
         → 视频流 → 抽帧 ────┼→ 时间戳对齐 → 图文笔记
                    ↓        │
              多模态读图 ────┘
```

---

## 脚本用法

```bash
S=/path/to/bilibili-video-summary/scripts

# 下载音频 / 视频流（工作目录里需有 playurl.json）
python "$S/fetch_media.py" <工作目录> both

# 转写
python "$S/transcribe.py" <工作目录> "视频主题关键词"

# 抽帧 —— 课件类用 dense，对谈类用 scene
python "$S/extract_frames.py" <工作目录> --mode dense --dense-interval 8 --max-frames 80
python "$S/extract_frames.py" <工作目录> --mode scene
```

### `extract_frames.py` 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--mode scene\|dense` | `scene` | 抽帧策略 |
| `--max-frames N` | 60 | 候选帧上限，超出按变化幅度排序截取 |
| `--dense-interval S` | 8 | dense 模式的采样间隔（秒） |
| `--mae-thresh F` | 25 | scene 模式 MAE 阈值 |
| `--ratio-thresh F` | 0.55 | scene 模式变化像素比例阈值 |
| `--dense-mae-thresh F` | 2.0 | dense 模式去重阈值 |

---

## 什么时候该开画面模式

| 视频类型 | 画面信息量 | 建议 |
|---|---|---|
| 网课 / PPT / 板书 | 极高 | **开** |
| 代码演示 / IDE 操作 | 高 | **开** |
| 图表、数据、公式推导 | 高 | **开** |
| 纯对谈 / 播客 | 低 | 不开，白烧算力 |
| 无口播的画面流 | — | **开**，画面是唯一信息源 |

---

## 实测数据

在 8 线程 CPU / int8 量化 / small 模型上测得：

### 转写耗时

| 音频时长 | 模型加载 | 转写 | 合计 |
|---|---|---|---|
| 9 分钟 | ~10s | 60~90s | ~2 分钟 |
| 55 分钟 | ~10s | ~7.5 分钟 | ~8 分钟 |

### 抽帧（课件类，20 分钟视频）

| 项 | 值 |
|---|---|
| 视频流体积 | 12.4 MB（480p，静态 PPT 码率极低） |
| 解码 | 36425 帧约 30 秒 |
| dense 抽帧 | 8 秒间隔 → 70 帧候选，其中 22 帧为真正的内容切换 |
| 单帧体积 | JPEG(q85) 约 40~110 KB |

> **清晰度结论**：480p（852×480）对 PPT 课件**完全够用** —— 表格正文和手写批注都清晰可读，不必为 1080p 折腾 cookie。

---

## 同音字校正

Whisper 对中文的误识别很有规律，本技能内置了两套校正表：

### 计算机 / 求职类黑话

| 识别结果 | 正确 |
|---|---|
| 双飞 / 双肥 | 双非 |
| 加瓦 | Java |
| 运为 | 运维 |
| 既往 | 计网 |
| 考工 / 考供 | 考公 |
| 求招 | 秋招 |
| 硬接生 | 应届生 |
| 大產 | 大厂 |

### 学术人名 / 术语（科普、对谈类高发）

| 识别结果 | 正确 |
|---|---|
| 维德根斯坦 / 维德克斯坦 / 维德根兰 | 维特根斯坦 |
| 埃斯坦 | 爱因斯坦 |
| 格德尔 | 哥德尔 |
| 杨乐坤 | 杨立昆（Yann LeCun） |
| 索拉迪 | 苏格拉底 |
| 高刺分布 | 高斯分布 |
| 可减严事实 / 科检验事实 | 可检验事实 |
| 莫会的知识 | 默会知识（tacit knowledge） |
| 陳書 / 陳數 | 陈述 |
| 超業 / 超厌 | 超验 |

> **重要**：机械替换会误伤——"奇异"在数学语境下本来就是对的。**必须逐句结合上下文判断**，不能无脑全局替换。

---

## 为什么不用 B 站字幕接口

`api.bilibili.com/x/player/v2` 返回的 `subtitle.subtitles` 现在**几乎都是空数组**（`need_login_subtitle: true`）——AI 字幕需要登录 cookie。评论接口也已要求 wbi 签名。

**所以直接下音频本地 ASR 最稳。**

---

## 关键经验（踩坑记录）

1. **视频流按分辨率挑，不是按带宽最小** —— 静态 PPT 的 480p 只有 85 kbps，和 360p 差不了几 MB，但分辨率决定小字能不能读。
2. **抽帧必须双指标** —— 只用 MAE 会把人物微表情全抓进来（实测 316 秒出 182 张，等于没筛）。加上"变化像素比例"后降到 71 张。
3. **课件类必须用 dense 模式** —— PPT 一行行往外蹦时整屏变化很小，scene 模式的阈值一高就全漏。
4. **变化大 ≠ 信息多** —— 过场动画、留白转场同样触发高 MAE，最终必须靠读图人工筛。
5. **文件不完整会解码报错**（`InvalidDataError`）—— 截断下载时要用 try/except 包住 decode 循环，保住已解出的帧。
6. **画面能抓到 ASR 的硬错误** —— 实测转写把 POP3 端口识别成"120"，画面写的是 **110**。数字和缩写靠音频分辨不出来。
7. **别用 `| tail` 包住后台转写命令** —— 管道全缓冲会让后台任务看起来像卡死。查进度用 `wc -l transcript.txt`。
8. **HF 模型下载会拿到 0 字节软链** —— 必须手动落盘。

---

## 目录结构

```
bilibili-video-summary/
├── SKILL.md                  # 完整流程 / 参数 / 踩坑 / 实测数据
└── scripts/
    ├── fetch_media.py        # 下载音频或视频流
    ├── transcribe.py         # 本地 Whisper 转写
    └── extract_frames.py     # 抽帧（scene / dense 双模式）
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
