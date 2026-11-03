# Readori + Microsoft Azure Speech（官方服务）

[English](README.md)

本指南说明如何通过微软官方的商业服务 **Azure Speech** 文本转语音，用**你自己的 Azure 账号和密钥**，
在 Readori 里使用**微软神经语音**朗读。Readori 不提供密钥，也不提供共享账号。

> **关于旧的内置「Microsoft Edge TTS」引擎。** 早期版本的 Readori 内置过同名引擎。它已被**移除**：
> 它调用的是非官方的 Edge 朗读端点，而不是商业的 Azure Speech API，存在服务条款和稳定性风险。
> **Azure Speech 是在 Readori 里使用微软语音的受支持方式。** 本仓库不提供针对该非官方端点的模板、代理或操作说明。

本目录文件：`readori-engine-azure.json`（单个引擎对象，用**粘贴 JSON**导入）。

## 1. 创建 Azure Speech 资源

1. 用 Azure 账号登录 [Azure 门户](https://portal.azure.com)
   （可[免费创建账号](https://azure.microsoft.com/pricing/purchase-options/azure-account)）。
2. 创建 **Speech** 资源（Azure AI / Foundry Tools）。选一个离你近的**区域**和定价层。
3. 打开资源的 **密钥和终结点**：复制 **密钥 1**，记下**区域**（例如 `eastus`、`westeurope`、`eastasia`）。

来源：[文本转语音 REST API：先决条件](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech)。

### 免费层（F0）与限制

- Azure Speech 免费（F0）层在[定价页](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/)
  上列为**每月 50 万个神经文本转语音字符免费**（2026-11-03 读取；定价页会变，请自行再确认）。
- F0 的实时文本转语音限制为**每 60 秒 20 次事务**（不可调整），单次请求最多生成 10 分钟音频
  （[配额和限制](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits)）。
  **Readori 每个句子发一次请求**，所以在 F0 上连续朗读可能触发 `429 Too Many Requests`，出现卡顿或跳句。
  长时间朗读请使用标准（S0）层（默认每秒 30 次事务；按字符计费，见定价页）。
- 有些 `429` 是某个区域里某个声音的容量限制，不是配额；可以换区域或换声音。（同一配额页面。）
- 一个订阅是否能创建多个 F0 资源：**未验证**。

## 2. Readori 发送的请求

| 项目 | 值（均来自 [REST 参考](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech)） |
|---|---|
| 端点 | `https://<region>.tts.speech.microsoft.com/cognitiveservices/v1` |
| 方法 | `POST` |
| `Ocp-Apim-Subscription-Key` | 你的资源密钥 |
| `Content-Type` | `application/ssml+xml` |
| `X-Microsoft-OutputFormat` | `audio-24khz-48kbitrate-mono-mp3`（24 kHz 单声道 MP3，在文档列出的流式格式中；Readori 从字节识别 MP3） |
| `User-Agent` | 小于 255 个字符的应用名（文档标为必填）；模板发送 `Readori` |
| 请求体 | 含声音名称的 SSML |

模板里的请求体：

```xml
<speak version='1.0' xml:lang='zh-CN'><voice name='{{voice}}'><prosody rate='{{(speakSpeed - 5) * 10}}%'>{{String(speakText).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}</prosody></voice></speak>
```

- `{{voice}}` 是你在 App 里选的声音（选择之前取 `voices` 的第一项）。
- `String(speakText).replace(...)` 表达式会转义句子里的 `&`、`<`、`>`，书里的文字不会破坏 SSML。
- `rate` 由 Readori 的 0–10 语速（`{{speakSpeed}}`，5 为正常）按 `(speakSpeed - 5) * 10` 百分比计算：0 得 `-50%`，
  5 得 `0%`，10 得 `50%`。SSML 接受 `-50%`、`50%` 这样的百分比值，语速范围为 0.5 到 2 倍
  （[SSML：prosody](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice)）。
  模板引擎的算术支持来自对 App 源码的阅读，请在真机上测试一次。如果不想改变语速，删掉 `<prosody ...>` 与 `</prosody>` 标签。
- 模板里固定为 `xml:lang='zh-CN'`。声音由名称决定；当声音的语言区域与 `xml:lang` 不一致（例如 `en-US-JennyNeural`）时，
  Azure 是否接受，文档中**未验证**。如果某个声音返回 `400` 或没有声音，请复制该引擎并把 `xml:lang`
  改为该声音的区域（如 `en-US`、`zh-HK`）。

## 3. 声音（名称来自 Microsoft Learn）

来自[语言和声音支持](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts)
（2026-11-03 读取；列表会变化，部分声音只在个别区域提供）：

| 区域设置 | 模板中的声音 |
|---|---|
| zh-CN 普通话 | `zh-CN-XiaoxiaoNeural`、`zh-CN-YunxiNeural`、`zh-CN-YunjianNeural`、`zh-CN-XiaoyiNeural` |
| zh-CN-sichuan 西南官话 | `zh-CN-sichuan-YunxiNeural`（公共预览） |
| zh-CN-shandong 冀鲁官话 | `zh-CN-shandong-YunxiangNeural` |
| zh-CN-liaoning 东北官话 | `zh-CN-liaoning-XiaobeiNeural`、`zh-CN-liaoning-YunbiaoNeural`（公共预览） |
| zh-CN-henan 中原官话 | `zh-CN-henan-YundengNeural` |
| zh-CN-shaanxi 中原官话 | `zh-CN-shaanxi-XiaoniNeural`（公共预览） |
| zh-HK 粤语（繁体） | `zh-HK-HiuMaanNeural`、`zh-HK-WanLungNeural`、`zh-HK-HiuGaaiNeural` |
| zh-TW 台湾普通话 | `zh-TW-HsiaoChenNeural`、`zh-TW-YunJheNeural`、`zh-TW-HsiaoYuNeural` |
| en-US | `en-US-JennyNeural`、`en-US-GuyNeural`、`en-US-AriaNeural`、`en-US-AndrewNeural` |

微软还列出但未放入模板的：`zh-CN-guangxi-YunqiNeural`（广西口音，预览）、`yue-CN-XiaoMinNeural` / `yue-CN-YunSongNeural`
（粤语，简体）、`wuu-CN-XiaotongNeural` / `wuu-CN-YunzheNeural`（吴语）。其他声音把名称追加到 `voices` 即可。
方言声音不支持音素、自定义词典和口型（viseme）；「公共预览」声音只在部分区域提供
（见[区域表](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions?tabs=tts)）。
上海一带的口音对应吴语（`wuu-CN`）声音；闽南语只作为 `zh-CN-XiaoxiaoDialectsNeural` 的次要区域设置（`nan-CN`）出现，
本指南未测试。表中没有天津话声音；[CosyVoice 接入](../cosyvoice/README.zh-CN.md)覆盖更多方言。

## 4. 导入 Readori

1. 用文本编辑器打开 `readori-engine-azure.json`，把 URL 里的 **`<region>`**（例如 `eastus`）和请求头里的
   **`<YOUR_KEY>`** 换成你自己的值。保留单引号，并保持 JSON 合法。
2. 在 Readori：**阅读器 → 听书（朗读）设置 → 自定义引擎 → 粘贴 JSON**，粘贴内容（需要 **Readori Pro**）。
   选中该引擎，再选择声音。
3. **删除或妥善保管改好的文件**：它现在包含你的密钥。

## 5. 你的密钥、隐私与 HTTPS

- 密钥是**你自己的**。Readori 不提供、不代理，也不会在服务器上看到它；它从你的设备直接发往 `*.tts.speech.microsoft.com`。
- 在当前版本的 App 中，自定义引擎的请求头（密钥所在）保存在 iOS **钥匙串**里，而不是普通的应用偏好设置。
  本指南不作更多承诺：密钥同样存在于你导入的 JSON 文件及该文件的任何备份里。
- 端点是 **HTTPS**，App 要求携带密钥的请求头必须走 HTTPS。不要改成 `http://`（App 拒绝在明文 HTTP 上发送密钥）。
- **你朗读的文字会发送给微软**进行合成，适用你的 Azure 协议和微软的条款。不要用于不允许发送到云服务的文本。
- 付费层超出免费额度的用量由微软向你计费。请在 Azure 里设置预算提醒。

## 6. 常见问题

| 现象 | 可能原因 |
|---|---|
| `401` | 密钥错误，或密钥所属区域与 `<region>` 不一致 |
| `400` | SSML 格式错误（编辑时破坏了引号）、声音名称未知，或该声音在你的区域不可用 |
| `415` | `Content-Type` 不是 `application/ssml+xml` |
| `429` | F0 速率限制（每分钟 20 次）或区域容量；放慢速度、换区域 / 声音，或改用 S0 |
| `502` / `503` | 服务问题或请求头无效；重试 |
| 某个声音没有声音 | 试试第 2 节里的 `xml:lang` 修改，或换区域 |
| 语速没有变化 | 请原样保留 `<prosody>` 标签和 `(speakSpeed - 5) * 10` 表达式 |
