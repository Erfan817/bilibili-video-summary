# 示例输出

下面是 `bvs` 对真实 B 站视频跑出来的产物（节选，用于展示输出形态）。

## 一条命令

```bash
$ bvs BV1PE411h7b4 --topic "传销 骗局 心理学" --srt

title : 真正的传销到底有多可怕，测试一下你能坚持多久
bvid  : BV1PE411h7b4  p=1  cid=126052143  dur=244s
owner : 无际视频
下载音频流: id=30216 bw=49666 ...
loading model: D:\.workbuddy\models\faster-whisper-small ...
model ready in 1.3s
  seg 20 @ 00:00:48
  seg 40 @ 00:01:24
  seg 60 @ 00:01:54
  seg 80 @ 00:02:16
DONE segments=96 audio=243.6s elapsed=33.3s

完成 -> ./outputs/真正的传销到底有多可怕，测试一下你能坚持多久
  transcript.txt + transcript.srt
  summary.md / summary.json
```

## 产出物

```
outputs/真正的传销到底有多可怕，测试一下你能坚持多久/
├── transcript.txt      # 带时间戳逐句稿
├── transcript.srt      # SRT 字幕（--srt）
├── summary.md          # 结构化总结骨架（元信息 + 逐句稿引用 + 校正审查清单）
└── summary.json        # 机器可读结果（喂给下游脚本 / MCP）
```

中间产物（`audio.m4s` / `video.m4s` / `playurl.json`）默认跑完即删，加 `--keep` 保留。

## transcript.txt（节选）

```
[00:00:00] 有陷入 注定是孤独的。
[00:00:04] 这是合法的猫。
[00:00:06] 这是合法的猫。
[00:00:09] 还要我说多少遍。
[00:00:10] 是哪里不合法?
[00:00:12] 你们一个问自己一个问题。
[00:00:31] 你们自己说这个社会没有给你太多的机会。
[00:00:34] 你知道没有人会真正的理解你。
[00:00:37] 每次打电话回家报喜不报忧
[00:00:40] 装得很坚强
```

> 注意：这是**未做人工复核的原始 ASR 结果**。`这是合法的猫`（应为「吗」）
> 这类同音错误正是 `corrections.json` 与「审查清单」机制要处理的对象。

## transcript.srt

```
1
00:00:00,560 --> 00:00:04,040
有陷入 注定是孤独的。

2
00:00:04,040 --> 00:00:05,330
这是合法的猫。
```

> 装上 `zhconv` 后，`bvs` 还会自动做**繁→简归一**——Whisper 中文转写常混出
> 繁体字（实测「打電話 / 報喜不報憂」→「打电话 / 报喜不报忧」）。

## summary.json

```json
{
  "tool": "bilibili-video-summary",
  "version": "1.0.0",
  "title": "真正的传销到底有多可怕，测试一下你能坚持多久",
  "bvid": "BV1PE411h7b4",
  "owner": "无际视频",
  "duration": 244,
  "page": 1,
  "source": "whisper",
  "files": {
    "transcript": "transcript.txt",
    "summary_md": "summary.md",
    "summary_json": "summary.json",
    "srt": "transcript.srt"
  },
  "frames": null
}
```

## 画面模式（`--frames`）

```bash
$ bvs BV1h5m7BXEf8 --frames --srt
stream: id=32 852x480 bw=687966 codec=avc1.64001F
downloaded: 11.2 MB
mode=scene  decode: 852x480 avg_rate=30000/1001
decoded=4087  covered=136.3s  kept=60  (max=60)
-> ./outputs/<标题>/frames_index.txt
```

产出 `frames/*.jpg` + `frames_index.txt`：

```
    0.0s  mae=999.00  changed=100.0%  f00000_0000.0s.jpg
    4.0s  mae= 12.44  changed= 58.3%  f00001_0004.0s.jpg
   25.0s  mae= 31.02  changed= 71.1%  f00017_0025.0s.jpg
```

`frames/` 里的图直接逐帧看（多模态 agent 或人眼），把 PPT / 板书 / 图表内容
补进笔记 —— 这是纯音频转写永远拿不到的信息。
