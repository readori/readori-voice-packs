# Readori + CosyVoice3：自托管方言语音

[English](README.md)

本目录让你在**自己的机器**上运行一个方言语音合成服务（粤语、闽南话、四川话、东北话、上海话、天津话等），
使用开源模型 [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) 的 **Fun-CosyVoice3-0.5B-2512**，
并在 Readori 里作为「自定义朗读引擎」使用。

Readori 不托管、不内置、不分发 CosyVoice。你自己在电脑或云 GPU 上安装；App 只会把一个句子一个句子地发到你填写的地址。

| 文件 | 说明 |
|---|---|
| `readori_cosyvoice_server.py` | 封装官方 CosyVoice Python API 的 FastAPI 服务 |
| `readori_cosyvoice_core.py` | 纯逻辑模块（请求解析、语速映射、WAV 头、配置），有单元测试 |
| `requirements.txt` | Web 层依赖，以及本封装验证过的上游提交 |
| `readori-engines.json` | Readori 引擎**数组**（每种方言一个，外加一个可选声音的引擎），用于「导入文件 / URL」 |
| `readori-engine-sichuan.json` | **单个**引擎对象，用于「粘贴 JSON」 |

## 1. 环境要求

- **NVIDIA 显卡**，系统为 Linux、Windows 的 **WSL2**，或租用云 GPU。上游（README 与模型卡）**没有给出显存数字**，
  其 Docker 示例使用 `--runtime=nvidia`；0.5B 参数的模型不大，但建议先按至少 8 GB 显存准备
  （**未验证**：请以你的显卡实测为准）。CPU 只能用于测试，速度远远不够朗读。
- Python 3.10（上游使用 conda 环境）与 git。
- 首次约 15 分钟（主要是下载模型）。
- 手机上需要 Readori **Pro**（自定义引擎是 Pro 功能）。
- 一段简短的**参考人声录音**（见第 3 步）。

## 2. 安装 CosyVoice 并下载模型

按上游说明操作，下面的命令来自其 README。本封装针对上游提交
`074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc`（2026-05-25）验证；上游只有 `v2.0` 与 `flow_cache` 两个标签。

```bash
conda create -n cosyvoice -y python=3.10
conda activate cosyvoice
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
cd CosyVoice
git checkout 074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
git submodule update --init --recursive
pip install -r requirements.txt          # 上游 README 在此加了阿里云镜像参数
sudo apt-get install sox libsox-dev      # Ubuntu；仅在遇到 sox 报错时需要
```

下载模型（任选一个来源）：

```python
# ModelScope
from modelscope import snapshot_download
snapshot_download('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', local_dir='pretrained_models/Fun-CosyVoice3-0.5B')
# 或 Hugging Face
# from huggingface_hub import snapshot_download
# snapshot_download('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', local_dir='pretrained_models/Fun-CosyVoice3-0.5B')
```

然后在同一个环境里安装本封装的 Web 层依赖：

```bash
pip install -r /path/to/readori-voice-packs/integrations/cosyvoice/requirements.txt
```

## 3. 提供参考（prompt）录音

CosyVoice3 的方言 / 指令模式需要一段说话人的参考录音。本仓库**不附带任何人声样本**，没有录音服务无法启动。

> **请使用你自己的声音，或你拥有权利并获得明确同意的声音。** 未经本人许可，不要使用他人（名人、同事、有声书朗读者等）的录音。
> 你需要为自己生成的内容负责。

录一段简短、干净、单人的录音（无音乐、无噪声），保存为采样率**不低于 16 kHz** 的 WAV 文件（需要重采样时上游加载函数会断言这一点）。
不需要文字稿：本封装使用的两种调用（`inference_instruct2`、`inference_cross_lingual`）只需要 wav。

## 4. 启动服务

```bash
python readori_cosyvoice_server.py \
  --cosyvoice-dir ~/CosyVoice \
  --model-dir ~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B \
  --prompt-wav ~/my_voice.wav \
  --host 0.0.0.0 --port 9880
```

| 参数（环境变量） | 默认值 | 含义 |
|---|---|---|
| `--cosyvoice-dir`（`READORI_COSYVOICE_DIR`） | `CosyVoice` | 你的上游仓库目录，会加入 `sys.path` |
| `--model-dir`（`READORI_COSYVOICE_MODEL_DIR`） | `pretrained_models/Fun-CosyVoice3-0.5B` | 模型目录 |
| `--prompt-wav`（`READORI_COSYVOICE_PROMPT_WAV`） | 必填 | 你的参考 wav |
| `--host`（`READORI_COSYVOICE_HOST`） | `127.0.0.1` | 手机要访问需设为 `0.0.0.0`（或局域网 IP） |
| `--port`（`READORI_COSYVOICE_PORT`） | `9880` | |
| `--token`（`READORI_COSYVOICE_TOKEN`） | 无 | 可选 Bearer 令牌（见第 6 节） |
| `--max-chars`（`READORI_COSYVOICE_MAX_CHARS`） | `600` | 单次请求最大字数 |
| `--device`（`READORI_COSYVOICE_DEVICE`） | `auto` | `auto`、`cpu`、`cuda`、`cuda:N`（通过 `CUDA_VISIBLE_DEVICES` 实现，上游没有设备参数） |
| `--dialects`（`READORI_COSYVOICE_DIALECTS`） | 7 个默认方言 | 逗号分隔，可选：mandarin、cantonese、minnan、sichuan、dongbei、shanghai、tianjin、shandong、shaanxi、shanxi、ningxia、gansu |

在本机测试：

```bash
curl -s http://127.0.0.1:9880/healthz
curl -s http://127.0.0.1:9880/v1/voices
curl -s -X POST http://127.0.0.1:9880/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"fun-cosyvoice3","input":"好少咯，一般系放嗰啲国庆啊，中秋嗰啲可能会咯。","voice":"cantonese","speed":5,"response_format":"wav"}' \
  -o out.wav
```

播放 `out.wav`。再从局域网内另一台设备测试（替换 IP）：`curl http://192.168.1.10:9880/healthz`。

### 接口

- `GET /healthz`：`{"status":"ok","model_loaded":true}`。
- `GET /v1/voices`：本服务启用的方言 id。
- `POST /v1/audio/speech`：OpenAI 兼容请求体 `{model, input, voice, speed, response_format}`。
  - `voice` 为方言 id（不区分大小写）；为空则取第一个已启用的（`mandarin`）。
  - `response_format`：只支持 `wav`（16 位单声道 PCM，标准 RIFF 头，采样率为模型采样率）。
  - `speed`：**0–10 的整数**是 Readori 刻度（`{{speakSpeed}}`）：0 为 0.5 倍，5 为 1.0 倍，10 为 2.0 倍，之间分段线性。
    **小数**（`1.0`、`1.25`，字符串形式也可）是 OpenAI 刻度 0.25–4.0，本模型会限制在 0.5–2.0。
    因为裸写的 `1` 会被当作 Readori 刻度，OpenAI 客户端想要 1 倍请发送 `1.0`。
  - 输入受 `--max-chars` 限制；`<|endofprompt|>` 之类的模型控制符会从文本中剔除。
  - 错误为 JSON `{"error":{"message","type","code"}}` 加 4xx/5xx 状态码（400 请求错误、401 令牌错误、413 过长、
    503 忙或加载中、500 合成失败）。
- 同一时间只合成一条（加锁）；多余请求最多等待 20 秒，然后返回 `503 busy`。
- 服务**从不记录正文**，只记录方言、字数、语速、音频时长和耗时。（上游 CosyVoice 使用 Python 根日志器输出日志；
  本服务把根日志器保持在 WARNING。如果你在意文本隐私，请自行检查日志。）

### 方言映射（上游指令文本）

每种方言使用上游 `cosyvoice/utils/common.py` 中 `instruct_list` 的指令文本（固定提交的第 28–43 行），
通过 `inference_instruct2(text, instruct, prompt_wav)` 调用：

| id | 指令文本 |
|---|---|
| cantonese | `You are a helpful assistant. 请用广东话表达。<\|endofprompt\|>`（上游 `example.py` 里也有） |
| minnan | `... 请用闽南话表达。` |
| sichuan | `... 请用四川话表达。` |
| dongbei | `... 请用东北话表达。` |
| shanghai | `... 请用上海话表达。` |
| tianjin | `... 请用天津话表达。` |
| shandong / shaanxi / shanxi / ningxia / gansu | `... 请用山东话 / 陕西话 / 山西话 / 宁夏话 / 甘肃话表达。` |
| mandarin | 无方言指令；按上游示例使用 `inference_cross_lingual("You are a helpful assistant.<\|endofprompt\|>" + text, prompt_wav)` |

以上指令均以 `<|endofprompt|>` 结尾。上游 README 列出的方言为 "Guangdong, Minnan, Sichuan, Dongbei, Shan3xi, Shan1xi,
Shanghai, Tianjin, Shandong, Ningxia, Gansu, etc."。不同方言、不同文本的效果差异较大，请以你自己的听感为准。

## 5. 导入 Readori

1. 编辑 `readori-engines.json`，把占位主机 `192.168.1.10` 替换为你服务器的局域网 IP（查找替换；没改端口就保留 `:9880`）。
2. 把文件放到手机上（AirDrop、「文件」、iCloud Drive），或放到手机能访问的地址。
3. 在 Readori 打开一本书，进入 **阅读器 → 听书（朗读）设置 → 自定义引擎**，选择**导入文件**（或从 URL 导入）。
   只导入单个引擎时用**粘贴 JSON**，内容取自 `readori-engine-sichuan.json`。此功能需要 **Readori Pro**。
4. 选中刚添加的引擎（例如「CosyVoice 自托管 · 四川话」），开始朗读。

每种方言是一个独立引擎，方言写死在请求体里。文件里最后一个引擎（「方言可选 (voice picker)」）发送的是 `{{voice}}`，
并在 `voices` 中列出全部方言，可在 App 的声音选择里切换方言。

App 每个句子发送的请求：

```
POST http://192.168.1.10:9880/v1/audio/speech
{"input":"<句子>","model":"fun-cosyvoice3","response_format":"wav","speed":"5","voice":"sichuan"}
```

`{{speakText}}` 由 App 做 JSON 转义；`{{speakSpeed}}` 是 App 语速滑块对应的 0–10 整数。

## 6. 网络说明

- 手机与服务器必须在**同一 Wi-Fi / 局域网**（或通过 Tailscale 之类的 VPN 互通）。访客网络或「AP 隔离」会导致无法连接。
- App 第一次访问局域网设备时，iOS 会弹出**本地网络**权限提示：请选择允许。之前拒绝过的话：iOS 设置 → Readori → 本地网络。
- 在服务器防火墙放行端口（Windows 防火墙、`ufw allow 9880/tcp`、云安全组）。WSL2 需要启用镜像网络，或在 Windows 上做端口转发。
- **明文 `http://` 下不能用令牌。** Readori 拒绝在 `http://` 上发送名为 `Authorization`、`token`、`api-key`、`cookie`、
  `secret` 之类的请求头，所以局域网方案不使用令牌。请只在你信任的网络里运行。
- **远程访问需要 HTTPS 加令牌。** 在前面放一个 TLS 反向代理，并用 `--token` 启动服务。最小的 [Caddy](https://caddyserver.com/)
  配置（需要一个指向本机的真实域名；证书必须是 iOS 信任的）：

  ```
  tts.example.com {
      reverse_proxy 127.0.0.1:9880
  }
  ```

  服务用 `--host 127.0.0.1 --token 你的足够长的随机令牌` 启动。在引擎文件里把 URL 改为
  `https://tts.example.com/v1/audio/speech,{...}`，并设置
  `"header": "{\"Content-Type\":\"application/json\",\"Authorization\":\"Bearer 你的足够长的随机令牌\"}"`。

## 7. 延迟与 15 秒限制

App 对每个**句子**请求最多等待 **15 秒**，超时就放弃并跳到下一句。本封装是非流式的：整句合成完才返回音频。
上游宣传模型的流式延迟「低至 150ms」，但这个简单服务并不是流式的。

- 请使用 GPU，并让服务器**靠近**手机（同一局域网）。服务会在日志里输出 `rtf`（每秒音频所需的合成秒数），需要明显小于 1；
  启动后的第一次请求会更慢。
- 冷启动：模型只在启动时加载一次（可能需要一分钟以上），加载完成后 `/healthz` 才会应答。
- 同一时间只合成一句。App 会预取下一句，如果 GPU 明显慢于实时，就会出现卡顿。
- 较大的 `speed` 由上游通过拉伸输出实现（仅非流式模式支持），极端值音质可能变差，建议先试 4–7。

## 8. 许可

- CosyVoice **代码与 Fun-CosyVoice3-0.5B-2512 权重均为 Apache-2.0**（上游仓库与模型卡）。
- 上游**没有公开训练数据**。你的使用方式（个人阅读、公开分发音频、商用）是否合适，请自行评估。
- 本封装与本仓库一致，采用 **Apache-2.0**。
- Readori 不托管、不分发 CosyVoice；你从上游自行下载。
- 你提供的声音以及生成的音频，责任由你自己承担；见第 3 节。

## 9. 常见问题

| 现象 | 可能原因 / 处理 |
|---|---|
| 服务退出：prompt wav 必填 / 找不到 / 采样率 | 用 `--prompt-wav` 指定不低于 16 kHz 的 WAV |
| 服务退出："cannot import the official CosyVoice package" | `--cosyvoice-dir` 必须是 git 仓库（含 `third_party/Matcha-TTS` 子模块） |
| 服务退出："is a CosyVoice2 model" | 模型目录不是 Fun-CosyVoice3-0.5B-2512 |
| 电脑上 `curl` 正常但手机不行 | 服务绑定在 `127.0.0.1`（改用 `--host 0.0.0.0`）、防火墙、不在同一 Wi-Fi、AP 隔离 |
| 允许本地网络后 App 仍无声 / 报错 | 在 iOS 设置里为 Readori 开启本地网络 |
| `400 unsupported_format` | 只支持 `wav` |
| `400 invalid_speed` | 整数必须是 0–10；OpenAI 刻度请用 `1.0` 这样的小数 |
| `413 input_too_long` | 调大 `--max-chars`，或在 App 里用更短的句子 |
| `503 busy` / App 跳句 | GPU 慢于实时或被共用；换更快的 GPU |
| App 里请求构建失败 | 编辑后保持 `url` 为合法单行 JSON；不要给 `http://` 地址添加令牌头 |
| CUDA 显存不足 | 关闭其他占用 GPU 的程序；`--device cpu` 仅用于测试 |
| 某方言听起来像普通话 | 方言效果不一；试试声音选择引擎、更短或更口语化的文本 |
