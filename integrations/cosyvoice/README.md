# Readori + CosyVoice3: a self-hosted dialect voice

[简体中文](README.zh-CN.md)

This folder lets you run **your own** text-to-speech server for dialects (Cantonese, Minnan,
Sichuan, Dongbei, Shanghai, Tianjin and more) with the open-source
[CosyVoice](https://github.com/FunAudioLLM/CosyVoice) model **Fun-CosyVoice3-0.5B-2512**, and
use it from the Readori app as a *custom TTS engine*.

Readori does not host, bundle or distribute CosyVoice. You install it yourself, on your own
computer or cloud GPU; the app only sends one sentence at a time to the address you give it.

| File | What it is |
|---|---|
| `readori_cosyvoice_server.py` | FastAPI server wrapping the official CosyVoice Python API |
| `readori_cosyvoice_core.py` | Pure helpers (request parsing, speed mapping, WAV header, config); unit tested |
| `requirements.txt` | Web-layer dependencies and the upstream commit this was verified against |
| `readori-engines.json` | An **array** of Readori engines (one per dialect + one with a voice picker) for "import file / URL" |
| `readori-engine-sichuan.json` | A **single** engine object, for "paste JSON" |

## 1. Requirements

- An **NVIDIA GPU** on Linux, Windows **WSL2**, or a rented cloud GPU. Upstream (README and model
  card) does **not** state a VRAM figure and its Docker example uses `--runtime=nvidia`; a
  0.5B-parameter model is small, but plan for at least 8 GB of VRAM as a starting point
  (**UNVERIFIED**: measure on your card). CPU works for testing only and is far too slow for reading.
- Python 3.10 (upstream uses a conda environment) and git.
- About 15 minutes the first time (downloading the model dominates).
- Readori **Pro** on the phone (custom engines are a Pro feature).
- A short **reference voice recording** (see step 3).

## 2. Install CosyVoice and download the model

Follow upstream; the commands below are from its README. This wrapper was verified against
upstream commit `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc` (2026-05-25; upstream only has the tags
`v2.0` and `flow_cache`).

```bash
conda create -n cosyvoice -y python=3.10
conda activate cosyvoice
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
cd CosyVoice
git checkout 074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
git submodule update --init --recursive
pip install -r requirements.txt          # upstream README adds an Aliyun mirror flag
sudo apt-get install sox libsox-dev      # Ubuntu; only if you hit sox errors
```

Download the model (either source):

```python
# ModelScope
from modelscope import snapshot_download
snapshot_download('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', local_dir='pretrained_models/Fun-CosyVoice3-0.5B')
# or Hugging Face
# from huggingface_hub import snapshot_download
# snapshot_download('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', local_dir='pretrained_models/Fun-CosyVoice3-0.5B')
```

Then, in the same environment, install the web layer of this wrapper:

```bash
pip install -r /path/to/readori-voice-packs/integrations/cosyvoice/requirements.txt
```

## 3. Provide the prompt (reference) wav

CosyVoice3's dialect and instruct modes need a reference recording of a speaker. This repository
**ships no voice sample**, and the server refuses to start without one.

> **Use your own voice, or a voice you have the rights and the explicit consent to use.** Do not
> use a recording of someone else (a celebrity, a coworker, an audiobook narrator) without their
> permission. You are responsible for what you generate.

Record a short, clean, single-speaker clip (no music, no noise), saved as a WAV file with a sample
rate of **at least 16 kHz** (upstream's loader asserts this when resampling is needed). No
transcript is needed: the two call modes used here (`inference_instruct2`,
`inference_cross_lingual`) take only the wav.

## 4. Start the server

```bash
python readori_cosyvoice_server.py \
  --cosyvoice-dir ~/CosyVoice \
  --model-dir ~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B \
  --prompt-wav ~/my_voice.wav \
  --host 0.0.0.0 --port 9880
```

| Flag (env var) | Default | Meaning |
|---|---|---|
| `--cosyvoice-dir` (`READORI_COSYVOICE_DIR`) | `CosyVoice` | Your upstream checkout, added to `sys.path` |
| `--model-dir` (`READORI_COSYVOICE_MODEL_DIR`) | `pretrained_models/Fun-CosyVoice3-0.5B` | Model directory |
| `--prompt-wav` (`READORI_COSYVOICE_PROMPT_WAV`) | required | Your reference wav |
| `--host` (`READORI_COSYVOICE_HOST`) | `127.0.0.1` | Use `0.0.0.0` (or the LAN IP) so the phone can connect |
| `--port` (`READORI_COSYVOICE_PORT`) | `9880` | |
| `--token` (`READORI_COSYVOICE_TOKEN`) | none | Optional bearer token (see section 6) |
| `--max-chars` (`READORI_COSYVOICE_MAX_CHARS`) | `600` | Longest accepted `input` |
| `--device` (`READORI_COSYVOICE_DEVICE`) | `auto` | `auto`, `cpu`, `cuda`, `cuda:N` (set through `CUDA_VISIBLE_DEVICES`; upstream has no device argument) |
| `--dialects` (`READORI_COSYVOICE_DIALECTS`) | the 7 defaults | Comma list from: mandarin, cantonese, minnan, sichuan, dongbei, shanghai, tianjin, shandong, shaanxi, shanxi, ningxia, gansu |

Test it from the same machine:

```bash
curl -s http://127.0.0.1:9880/healthz
curl -s http://127.0.0.1:9880/v1/voices
curl -s -X POST http://127.0.0.1:9880/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"fun-cosyvoice3","input":"好少咯，一般系放嗰啲国庆啊，中秋嗰啲可能会咯。","voice":"cantonese","speed":5,"response_format":"wav"}' \
  -o out.wav
```

Play `out.wav`. Then test from another device on the LAN (replace the IP): `curl http://192.168.1.10:9880/healthz`.

### API

- `GET /healthz`: `{"status":"ok","model_loaded":true}`.
- `GET /v1/voices`: the dialect ids this server enabled.
- `POST /v1/audio/speech`: OpenAI-compatible body `{model, input, voice, speed, response_format}`.
  - `voice` is a dialect id (case-insensitive); empty means the first enabled one (`mandarin`).
  - `response_format`: only `wav` (16-bit mono PCM, RIFF header, at the model's sample rate).
  - `speed`: an **integer 0-10** is the Readori scale (`{{speakSpeed}}`): 0 is 0.5x, 5 is 1.0x,
    10 is 2.0x, straight lines between them. A **decimal** (`1.0`, `1.25`, also as a string) is the
    OpenAI scale 0.25-4.0, clamped to 0.5-2.0 for this model. Because a bare `1` is read as the
    Readori scale, OpenAI clients that want 1x should send `1.0`.
  - Input is limited by `--max-chars`; model control tokens such as `<|endofprompt|>` are stripped
    from the text.
  - Errors are JSON `{"error":{"message","type","code"}}` with a 4xx/5xx status (400 bad request,
    401 bad token, 413 too long, 503 busy or loading, 500 synthesis failed).
- One synthesis runs at a time (a lock); extra requests wait up to 20 s, then get `503 busy`.
- The server **never logs the text**; it logs the voice, character count, speed, audio length and
  timings. (Upstream CosyVoice logs through Python's root logger; this server keeps the root logger
  at WARNING. Check your own logs if text privacy matters to you.)

### Dialect mapping (upstream instruct text)

Each dialect uses the instruct string from upstream `cosyvoice/utils/common.py` (`instruct_list`,
lines 28-43 at the pinned commit), passed to `inference_instruct2(text, instruct, prompt_wav)`:

| id | instruct text |
|---|---|
| cantonese | `You are a helpful assistant. 请用广东话表达。<\|endofprompt\|>` (also in upstream `example.py`) |
| minnan | `... 请用闽南话表达。` |
| sichuan | `... 请用四川话表达。` |
| dongbei | `... 请用东北话表达。` |
| shanghai | `... 请用上海话表达。` |
| tianjin | `... 请用天津话表达。` |
| shandong / shaanxi / shanxi / ningxia / gansu | `... 请用山东话 / 陕西话 / 山西话 / 宁夏话 / 甘肃话表达。` |
| mandarin | no dialect instruct; uses `inference_cross_lingual("You are a helpful assistant.<\|endofprompt\|>" + text, prompt_wav)` as in upstream's example |

All of the above end with `<|endofprompt|>`. The upstream README lists the dialects "Guangdong,
Minnan, Sichuan, Dongbei, Shan3xi, Shan1xi, Shanghai, Tianjin, Shandong, Ningxia, Gansu, etc."
Dialect quality varies by dialect and by text; judge it with your own ears.

## 5. Import into Readori

1. Edit `readori-engines.json` and replace the placeholder host `192.168.1.10` with your server's
   LAN IP (find/replace; keep `:9880` unless you changed the port).
2. Put the file on the phone (AirDrop, Files, iCloud Drive) or host it somewhere reachable.
3. In Readori open a book, then **Reader → Listen (read aloud) settings → Custom engines**, and choose
   **Import file** (or import from URL). To import a single engine, use **Paste JSON** with the
   content of `readori-engine-sichuan.json`. This needs **Readori Pro**.
4. Pick the engine you added (for example "CosyVoice 自托管 · 四川话") and start reading aloud.

Each dialect is its own engine with the dialect baked into the request body. The last engine in
the file ("方言可选 (voice picker)") sends `{{voice}}` instead, and lists every dialect in its
`voices`, so you can switch dialects from the app's voice picker.

The request the app sends, per sentence:

```
POST http://192.168.1.10:9880/v1/audio/speech
{"input":"<sentence>","model":"fun-cosyvoice3","response_format":"wav","speed":"5","voice":"sichuan"}
```

`{{speakText}}` is JSON-escaped by the app; `{{speakSpeed}}` is the 0-10 integer from the app's
speed slider.

## 6. Network notes

- The phone and the server must be on the **same Wi-Fi / LAN** (or reach each other through a VPN
  such as Tailscale). A guest network or "AP isolation" blocks this.
- The first time the app contacts a device on your LAN, iOS shows a **Local Network** permission
  prompt: allow it. If you declined earlier: iOS Settings → Readori → Local Network.
- Open the port in the server's firewall (Windows Defender Firewall, `ufw allow 9880/tcp`, cloud
  security group). On WSL2 either use mirrored networking or forward the port from Windows.
- **No token over plain `http://`.** Readori refuses to send any header named like
  `Authorization`, `token`, `api-key`, `cookie` or `secret` over `http://`, so the LAN setup uses
  no token. Keep the server on a network you trust.
- **Remote access needs HTTPS and a token.** Put a TLS reverse proxy in front and start the server
  with `--token`. A minimal [Caddy](https://caddyserver.com/) setup (needs a real domain pointing at
  the machine; the certificate must be one iOS trusts):

  ```
  tts.example.com {
      reverse_proxy 127.0.0.1:9880
  }
  ```

  Run the server with `--host 127.0.0.1 --token YOUR_LONG_RANDOM_TOKEN`. In the engine file change
  the URL to `https://tts.example.com/v1/audio/speech,{...}` and set
  `"header": "{\"Content-Type\":\"application/json\",\"Authorization\":\"Bearer YOUR_LONG_RANDOM_TOKEN\"}"`.

## 7. Latency and the 15-second limit

The app gives each **sentence** request **15 seconds** before it gives up and moves on. This
wrapper is non-streaming: the whole sentence is synthesized before any audio is returned. Upstream
advertises streaming latency "as low as 150ms" for the model, but that is not what this simple
server does.

- Use a GPU and keep the server **near** the phone (same LAN). The server logs `rtf`
  (synthesis seconds per audio second); you need it clearly below 1, and the first request after
  start is slower.
- Cold start: the model loads once at startup (can take a minute or more). `/healthz` answers only
  after loading.
- Only one sentence is synthesized at a time. The app prefetches the next sentence, so a GPU that
  is much slower than real time will stutter.
- Very fast `speed` values are applied by upstream by stretching the output (non-stream mode only);
  extremes can sound worse. Try 4-7 first.

## 8. Licences

- CosyVoice **code and the Fun-CosyVoice3-0.5B-2512 weights are Apache-2.0**
  (upstream repository and model card).
- Upstream does **not disclose its training data**. Whether your use (personal reading, public
  redistribution of audio, commercial use) is acceptable is your own evaluation.
- This wrapper is **Apache-2.0**, like the rest of this repository.
- Readori does not host or distribute CosyVoice; you download it from upstream.
- You alone are responsible for the voice you provide and the audio you produce; see section 3.

## 9. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Server exits: "prompt wav required / not found / sample rate" | Pass `--prompt-wav` with a WAV of at least 16 kHz |
| Server exits: "cannot import the official CosyVoice package" | `--cosyvoice-dir` must be the git checkout (with the `third_party/Matcha-TTS` submodule) |
| Server exits: "is a CosyVoice2 model" | The model directory is not Fun-CosyVoice3-0.5B-2512 |
| `curl` works on the PC but not the phone | Server bound to `127.0.0.1` (use `--host 0.0.0.0`), firewall, different Wi-Fi, AP isolation |
| App shows no sound / error after the Local Network prompt | Allow Local Network for Readori in iOS Settings |
| `400 unsupported_format` | Only `wav` is supported |
| `400 invalid_speed` | Integers must be 0-10; use `1.0` style decimals for the OpenAI scale |
| `413 input_too_long` | Raise `--max-chars` or use shorter sentences in the app |
| `503 busy` / app skips sentences | The GPU is slower than real time or shared; use a faster GPU |
| Request build fails in the app | Keep the `url` single-line JSON valid after editing; do not add a token header to an `http://` URL |
| CUDA out of memory | Close other GPU programs; try `--device cpu` only for testing |
| A dialect sounds like Mandarin | Dialect quality varies; try the voice picker, shorter or more colloquial text |
