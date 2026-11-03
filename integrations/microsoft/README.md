# Readori + Microsoft Azure Speech (official service)

[简体中文](README.zh-CN.md)

This guide shows how to read aloud in Readori with **Microsoft neural voices** through the
official, commercial **Azure Speech** text-to-speech service, using **your own Azure account and
key**. Readori does not provide a key or a shared account.

> **About the old "Microsoft Edge TTS" engine.** Earlier Readori builds had a built-in engine of
> that name. It was **removed**: it talked to an unofficial Edge read-aloud endpoint, not the
> commercial Azure Speech API, which is a terms-of-service and stability risk. **Azure Speech is the
> supported way to use Microsoft voices in Readori.** This repository does not provide templates,
> proxies or instructions for that unofficial endpoint.

Files here: `readori-engine-azure.json` (one engine object, import with **Paste JSON**).

## 1. Create an Azure Speech resource

1. Sign in to the [Azure portal](https://portal.azure.com) with an Azure account
   ([create one for free](https://azure.microsoft.com/pricing/purchase-options/azure-account)).
2. Create a **Speech** resource (Azure AI / Foundry Tools). Pick a **region** close to you and a
   pricing tier.
3. Open the resource, **Keys and Endpoint**: copy **KEY 1** and note the **region** (for example
   `eastus`, `westeurope`, `eastasia`).

Source: [Text to speech REST API: prerequisites](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech).

### Free tier (F0) and limits

- The Free (F0) tier of Azure Speech lists **0.5 million neural text-to-speech characters free per
  month** on the [pricing page](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/)
  (read on 2026-11-03; pricing pages change, so confirm before relying on it).
- On F0, real-time text to speech is limited to **20 transactions per 60 seconds** (not
  adjustable), and one request can produce at most 10 minutes of audio
  ([quotas and limits](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits)).
  **Readori sends one request per sentence**, so continuous reading on F0 can hit `429 Too Many
  Requests` and stutter or skip. For long reading sessions, use the Standard (S0) tier (30
  transactions per second by default; billed per character, see the pricing page).
- Some `429` errors are capacity limits for a specific voice in a region, not quota; try another
  region or voice. (Same quotas page.)
- Whether you may create more than one F0 resource per subscription: **UNVERIFIED**.

## 2. The request Readori sends

| Item | Value (all from the [REST reference](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech)) |
|---|---|
| Endpoint | `https://<region>.tts.speech.microsoft.com/cognitiveservices/v1` |
| Method | `POST` |
| `Ocp-Apim-Subscription-Key` | your resource key |
| `Content-Type` | `application/ssml+xml` |
| `X-Microsoft-OutputFormat` | `audio-24khz-48kbitrate-mono-mp3` (24 kHz mono MP3, in the documented streaming list; Readori detects MP3 from the bytes) |
| `User-Agent` | an application name under 255 characters (documented as required); the template sends `Readori` |
| Body | SSML with the voice name |

The body in the template:

```xml
<speak version='1.0' xml:lang='zh-CN'><voice name='{{voice}}'><prosody rate='{{(speakSpeed - 5) * 10}}%'>{{String(speakText).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}</prosody></voice></speak>
```

- `{{voice}}` is the voice picked in the app (the first entry of `voices` until you choose).
- The `String(speakText).replace(...)` expression XML-escapes `&`, `<` and `>` in the sentence, so
  book text cannot break the SSML.
- `rate` is computed from Readori's 0-10 speed (`{{speakSpeed}}`, 5 is normal) as
  `(speakSpeed - 5) * 10` percent: 0 gives `-50%`, 5 gives `0%`, 10 gives `50%`. SSML accepts
  percentage values such as `-50%` and `50%` and a rate range of 0.5x to 2x
  ([SSML: prosody](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice)).
  The template engine's arithmetic support is read from the app source; test it once on a device.
  If you would rather not change the speed, delete the `<prosody ...>` and `</prosody>` tags.
- `xml:lang='zh-CN'` is fixed in the template. The voice name selects the voice; whether Azure
  accepts a voice whose locale differs from `xml:lang` (for example `en-US-JennyNeural`) is
  **UNVERIFIED** in the documentation. If a voice gives `400` or no audio, copy the engine and set
  `xml:lang` to that voice's locale (for example `en-US`, `zh-HK`).

## 3. Voices (names from Microsoft Learn)

From [Language and voice support](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts)
(read on 2026-11-03; the list changes, and some voices exist only in some regions):

| Locale | Voices in the template |
|---|---|
| zh-CN Mandarin | `zh-CN-XiaoxiaoNeural`, `zh-CN-YunxiNeural`, `zh-CN-YunjianNeural`, `zh-CN-XiaoyiNeural` |
| zh-CN-sichuan Southwestern Mandarin | `zh-CN-sichuan-YunxiNeural` (public preview) |
| zh-CN-shandong Jilu Mandarin | `zh-CN-shandong-YunxiangNeural` |
| zh-CN-liaoning Northeastern Mandarin | `zh-CN-liaoning-XiaobeiNeural`, `zh-CN-liaoning-YunbiaoNeural` (public preview) |
| zh-CN-henan Zhongyuan Mandarin | `zh-CN-henan-YundengNeural` |
| zh-CN-shaanxi Zhongyuan Mandarin | `zh-CN-shaanxi-XiaoniNeural` (public preview) |
| zh-HK Cantonese (Traditional) | `zh-HK-HiuMaanNeural`, `zh-HK-WanLungNeural`, `zh-HK-HiuGaaiNeural` |
| zh-TW Taiwanese Mandarin | `zh-TW-HsiaoChenNeural`, `zh-TW-YunJheNeural`, `zh-TW-HsiaoYuNeural` |
| en-US | `en-US-JennyNeural`, `en-US-GuyNeural`, `en-US-AriaNeural`, `en-US-AndrewNeural` |

Also listed by Microsoft but not in the template: `zh-CN-guangxi-YunqiNeural` (Guangxi accent,
preview), `yue-CN-XiaoMinNeural` / `yue-CN-YunSongNeural` (Cantonese, Simplified),
`wuu-CN-XiaotongNeural` / `wuu-CN-YunzheNeural` (Wu Chinese). Add any other voice by appending its
name to `voices`. The dialect voices do not support phonemes, custom lexicons or visemes, and
"public preview" voices are limited to some regions (see the
[regions table](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions?tabs=tts)).
Shanghai-area speech is covered by the Wu Chinese (`wuu-CN`) voices. Minnan appears only as a
secondary locale (`nan-CN`) of `zh-CN-XiaoxiaoDialectsNeural`, which this guide did not test. There
is no Tianjin voice in the table; the [CosyVoice integration](../cosyvoice/README.md) covers more dialects.

## 4. Import into Readori

1. Open `readori-engine-azure.json` in a text editor and replace **`<region>`** in the URL (for
   example `eastus`) and **`<YOUR_KEY>`** in the header with your values. Keep the single quotes
   and the JSON valid.
2. In Readori: **Reader → Listen (read aloud) settings → Custom engines → Paste JSON** and paste the
   content (needs **Readori Pro**). Choose the engine, then pick a voice.
3. **Delete or protect the edited file**: it now contains your key.

## 5. Your key, privacy and HTTPS

- The key is **yours**. Readori does not supply, proxy or see it on a server; it is sent from your
  device straight to `*.tts.speech.microsoft.com`.
- In the current app, a custom engine's headers (where the key lives) are kept in the iOS
  **Keychain** rather than in plain app preferences. This guide claims nothing beyond that: the
  key is also in the JSON file you imported, and in any backup of that file.
- The endpoint is **HTTPS**, which the app requires for headers that carry a key. Do not change
  it to `http://` (the app refuses to send a key over plain HTTP).
- The **text you read aloud is sent to Microsoft** for synthesis, under your Azure agreement and
  Microsoft's terms. Do not use it for text you may not send to a cloud service.
- You are billed by Microsoft for usage beyond the free quota on a paid tier. Set a budget alert
  in Azure.

## 6. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401` | Wrong key, or the key belongs to a different region than `<region>` |
| `400` | Malformed SSML (edit broke the quotes), unknown voice name, or the voice is not available in your region |
| `415` | `Content-Type` is not `application/ssml+xml` |
| `429` | F0 rate limit (20 per minute) or regional capacity; slow down, switch region / voice, or use S0 |
| `502` / `503` | Service problem or invalid headers; retry |
| No sound for one voice | Try the `xml:lang` change from section 2, or another region |
| Speed has no effect | Keep the `<prosody>` tags and the `(speakSpeed - 5) * 10` expression exactly |
