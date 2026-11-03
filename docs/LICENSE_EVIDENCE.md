# LICENSE_EVIDENCE.md - tts-models licence research (R195 voice-pack factory)

Date: 2026-11-02. Scope: models in https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models relevant to English, Japanese, Korean, Chinese (Mandarin / Cantonese / other dialects). Companion file: `models.draft.yaml` (92 entries; every entry carries the same evidence in `license.evidence`).

## 0. Method, limits, disclosures

- Read-only research. Nothing downloaded except metadata/README/model-card/LICENSE text files from api.github.com, github.com, huggingface.co and k2-fsa.github.io. No model file was downloaded, nothing in the readori repo was changed.
- Upstream data: one GitHub API call for the `tts-models` release (646 assets) + the release's `checksum.txt`. sha256 comes from the asset `digest` field when GitHub provides it (566 of 646 assets), otherwise from `checksum.txt` (flagged per entry as unverified; CI must recompute and a human must confirm).
- Status rules: `approved` = App runtime supports the type (vits/kokoro) AND licence gate passes on the evidence for model + training data + base checkpoint. `candidate` = nothing prohibits it but it is blocked (unsupported type, or a licence question I could not resolve). `excluded` = non-commercial / no-derivatives / proprietary / undeclared. `unknown` is never approved (spec gate).
- DISCLOSURE (out-of-scope fetch): while trying to read the Lessac Blizzard 2013 dataset licence I made ONE request to `www.cstr.ed.ac.uk`, which is outside the authorised domain list. The page returned only a University of Edinburgh copyright header (no licence body); I discarded it, used nothing from it, and made no further requests to unauthorised domains. Consequently the Lessac licence is recorded as UNRESOLVED, not as a finding.
- Dataset licence evidence for LibriTTS / LibriTTS-R / VCTK / KSS / LJSpeech / AISHELL-3 comes from Hugging Face dataset cards (authorised domain), not from the original OpenSLR / Edinburgh pages.
- Web page / README / model-card text was treated as data. Quotes below are short excerpts kept as licence evidence.

## 1. Counts by language (entries, not unique voices; quality/precision variants are folded into `altAssets`)

| Language | approved | candidate | excluded |
|---|---:|---:|---:|
| English | 15 | 23 | 20 |
| Japanese | 0 | 0 | 1 |
| Korean | 0 | 0 | 2 |
| Japanese + Korean (Supertonic, multi) | 0 | 2 | 0 |
| Chinese (Mandarin) | 4 | 0 | 23 |
| Cantonese | 0 | 0 | 1 |
| Chinese dialect (Min Nan) | 0 | 0 | 1 |
| **Total** | **19** | **25** | **48** |

Note: `Japanese` / `Korean` rows are placeholders documenting that no compliant, App-runnable model exists; the Korean KSS entry is counted under Korean as excluded. Kokoro v1.0 is counted under English although it also carries 8 Mandarin voices.

## 2. Cross-cutting risks (read first)

1. **espeak-ng-data is GPL-3.0-or-later and 15 of 19 approved packs bundle it.** Evidence: espeak-ng README 'released under the GPL version 3 or later license' (https://github.com/espeak-ng/espeak-ng/blob/master/README.md); sherpa-onnx PR #4055 (merged 2026-10-20): 'That library is GPL, so it stays optional: sherpa-onnx is GPL-free after this PR.' Piper/Coqui/icefall-en/Kokoro packs need `dataDir: espeak-ng-data`. Approved packs WITHOUT it: `zh-melo-zh-en-v1`, `zh-aishell3-icefall-v1`, `zh-aishell3-vits-8k-v1`, `en-melo-v1` (lexicon front ends). Also relevant to the App itself: sherpa-onnx 1.13.2 (embedded) predates #4055, i.e. it still contains the GPL espeak-ng/piper-phonemize code - that is a question for LEAD/legal about the App binary, outside this research.
2. **sherpa-onnx 2.0.0 (Oct 2026) removed espeak-ng**: `data_dir` is 'deprecated and ignored' and models needing espeak phonemisation (Piper en, Coqui, Kokoro OOV fallback) need external phonemisation. The App is on 1.13.2 so it is unaffected today, but the pack set built around espeak data is a dead end for any future 2.x upgrade. Lexicon-based packs (Melo, AISHELL-3, Kokoro zh lexicons) and Supertonic do not have this problem.
3. **The `tts-models` tag is a rolling release.** Assets are replaced in place: kokoro-*-multi-lang-v1_0/v1_1 (4 assets) were re-uploaded 2026-10-26, vits-icefall-en_US-ljspeech-*, matcha-icefall-en_US-ljspeech, matcha-icefall-zh-baker on 2026-10-29. For 59 assets the GitHub digest differs from `checksum.txt` (e.g. kokoro-int8-multi-lang-v1_1: digest 259c9c8b... vs checksum.txt a1e94694...). The re-exported Kokoro models may differ from what the App's current builder was validated against (sherpa-onnx 2.0.1 notes: 'Keep the STFT convs of Kokoro in float32 when quantizing to int8 (#4087)'). Recommendation: pin by digest, fail on mismatch, and mirror the verified tarball into the readori-voice-packs release instead of building from a mutable upstream tag; smoke-test with sherpa-onnx 1.13.x.
3b. Older assets (melo zh_en, icefall aishell3, cantonese; created and updated within seconds in 2024) have no GitHub digest; their sha256 is from checksum.txt and is probably correct but unverified.
4. **Existing pack `yue-xiaomaiiwn-v1` (Cantonese) fails the gate**: no licence, README or provenance anywhere (HF mirror has no card; the original author repo is an empty placeholder). The App preset `cantonese` and `docs/Sherpa-onnx/Readori_TTS_Productization_CN.md` recommend it - LEAD must drop it or obtain a written licence.
5. **Lessac-derived Piper voices (10 voice entries plus lessac itself, 3 quality tiers) are blocked, not approved.** Piper fine-tuned most voices from the `lessac` checkpoint; the Lessac Blizzard 2013 licence is only a link in the model cards and I could not read its text within the authorised domains. If LEAD can confirm that it permits commercial use and redistribution of derived models, `en-piper-en-us-libritts-r-medium-v1` (904 voices), `en-piper-en-gb-vctk-medium-v1` (109 voices), aru (12), arctic (18), alba, sam, joe, jenny_dioco (custom attribution licence), northern_english_male (CC-BY-SA-4.0 share-alike) become approvable.
6. **Kokoro training data is partly synthetic audio from closed TTS providers.** The owner states the weights are Apache-2.0 and the data 'permissive/non-copyrighted'; the providers' terms of service cannot be verified. Residual risk is accepted by the owner's licence statement but not independently verifiable. Kokoro also used CC BY data (Koniwa tnc CC BY 3.0, SIWIS CC BY 4.0) -> attribution lines go into `readori-attribution.txt` for every Kokoro pack.
7. **Supertonic 3 is the only route to Japanese/Korean** and uses BigScience OpenRAIL-M (not in the gate's SPDX allow-list): commercial use and redistribution are allowed but use restrictions must be passed on in an enforceable legal agreement and output must not be shown unlabelled as human (Attachment A (e)). The App cannot run it today (type `supertonic` missing; manifest `type` enum is a Codable contract = STOP item). sherpa-onnx 1.13.2 already includes Supertonic 3 (CHANGELOG 1.13.2: 'Support Supertonic 3 TTS (#3605)'), so no library upgrade would be needed.
8. Chinese-language blockers: DataBaker BZNSYP (Piper xiao_ya, chaowen via fine-tune, Matcha baker) is non-commercial; the 13 `vits-zh-hf-*` assets are Hugging Face Space re-hosts (Genshin/Honkai/Overwatch-style game-character voices, or an unlicensed 'lkz99/tts_model' Space); MeloTTS and Kokoro are the only multi-ready Mandarin options besides AISHELL-3.

## 3. Approved (App-runnable, licence gate passes)

#### `zh-melo-zh-en-v1` - Mandarin / English - MeloTTS (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages zh-CN, en-US
- upstream: `vits-melo-tts-zh_en.tar.bz2`, 167,006,755 bytes, sha256 `e58351ed7149f290a54534538badd4077cdbe6fddc964b24d0bee870415d1514` (checksum.txt); asset updated 2024-11-03T12:31:05Z
- licence: `MIT`; commercialUse **true**, redistribution **true** ; attribution required
- training data: summary: NOT DISCLOSED by MyShell (model card gives no training-data section).; residualRisk: Training data provenance unknown; license of the weights is explicit MIT with commercial use statement.
- evidence: https://huggingface.co/myshell-ai/MeloTTS-Chinese  
  > 'This library is under MIT License, which means it is free for both commercial and non-commercial use.' (model card License section; front matter license: mit)
- evidence: https://huggingface.co/csukuangfj/vits-melo-tts-zh_en  
  > Converted copy ships its own LICENSE file (1053 bytes, MIT-sized) and README: 'Models in this directory are converted from https://github.com/myshell-ai/MeloTTS'
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html  
  > sherpa-onnx docs: 'This model is converted from https://huggingface.co/myshell-ai/MeloTTS-Chinese and it supports only 1 speaker.'
- notes: MIT notice must be kept in the pack (pack already contains LICENSE).
- risks: Training data undisclosed (explicit MIT grant only); English words only pronounced if present in lexicon.txt (sherpa docs)

#### `zh-aishell3-icefall-v1` - Mandarin - AISHELL-3 (174 voices)

- status: **approved**; type `vits`; appSupported `True`; languages zh-CN
- upstream: `vits-icefall-zh-aishell3.tar.bz2`, 31,559,701 bytes, sha256 `ab468db3a3308cdd861495e0db2f25d79418a0c00639f74944c7cdf5dd8c6ec1` (checksum.txt); asset updated 2024-04-08T01:43:46Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true** ; attribution required
- training data: name: AISHELL-3; license: Apache-2.0; summary: 85 hours, 218 speakers, Beijing Shell Shell Technology Co., Ltd.; url: https://arxiv.org/abs/2010.11567
- evidence: https://huggingface.co/datasets/AISHELL/AISHELL-3  
  > Official AISHELL org dataset card: license: apache-2.0; 'AISHELL-3 is a large-scale and high-fidelity multi-speaker Mandarin speech corpus ... can be used to train multi-speaker TTS systems.'
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html  
  > 'This model is trained on the aishell3 dataset using icefall. It supports only Chinese and it's a multi-speaker model and contains 174 speakers.'
- evidence: https://github.com/k2-fsa/icefall/blob/master/LICENSE  
  > icefall (training framework) is Apache License 2.0
- notes: No separate model card exists for the converted weights (csukuangfj/vits-icefall-zh-aishell3 repo is not public, HTTP 401); weights trained by k2-fsa team with Apache-2.0 icefall. Keep AISHELL-3 citation in readori-attribution.txt.
- risks: Low sample rate likely (icefall aishell3 recipe) - quality perception; Weights have no standalone license file; relies on Apache-2.0 of icefall + dataset

#### `zh-en-kokoro-v1-1-int8-v1` - Mandarin / English - Kokoro v1.1 int8 (103 voices)

- status: **approved**; type `kokoro`; appSupported `True`; languages zh-CN, en-US, en-GB
- upstream: `kokoro-int8-multi-lang-v1_1.tar.bz2`, 147,052,523 bytes, sha256 `259c9c8bc906d6078e4e0570421885dabb68b539c2f970fcbb890a58eeaf3e9c` (github-release-asset-digest); asset updated 2026-10-26T09:10:03Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true** ; attribution required
- training data: summary: 100 Chinese speakers from LongMaoData (permissive grant stated by model author); 3 crowdsourced synthetic English voices; base model Kokoro-82M v1.0 data (see Kokoro entry); residualRisk: Training audio partly synthetic from closed TTS providers (provider terms of service are not verifiable); the model owner asserts synthetic data is not copyrightable and licenses the weights Apache-2.0.
- attribution entries: Koniwa tnc - CC BY 3.0 - https://github.com/koniwa/koniwa | SIWIS - CC BY 4.0 - https://datashare.ed.ac.uk/handle/10283/2353
- base: hexgrad/Kokoro-82M (Apache-2.0)
- evidence: https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh  
  > license: apache-2.0; 'The Chinese data was freely and permissively granted to us by LongMaoData, a professional dataset company.'
- evidence: https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh  
  > English additions are 'crowdsourced synthetic English data' (Maple, Sol, Vale, ~1h each); base_model: hexgrad/Kokoro-82M
- evidence: https://huggingface.co/hexgrad/Kokoro-82M#creative-commons-attribution  
  > CC BY audio used in training: Koniwa 'tnc' (<1h, CC BY 3.0) and SIWIS (<11h, CC BY 4.0), added from v0.19 on.
- notes: Pack contains the Apache-2.0 LICENSE (11358 bytes in HF staging repo).
- risks: Upstream asset was RE-UPLOADED on 2026-10-26 (GitHub digest 259c9c... differs from checksum.txt a1e946...); new export may differ (sherpa-onnx 2.0.1 changelog: 'Keep the STFT convs of Kokoro in float32 when quantizing to int8 (#4087)') - must smoke-test against sherpa-onnx 1.13.x before building; Only 3 English voices in this model; Training data partly synthetic audio from closed TTS providers (owner asserts Apache-2.0)
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-kokoro-v1-0-int8-v1` - English / Mandarin - Kokoro v1.0 int8 (53 voices)

- status: **approved**; type `kokoro`; appSupported `True`; languages en-US, en-GB, zh-CN
- upstream: `kokoro-int8-multi-lang-v1_0.tar.bz2`, 132,353,410 bytes, sha256 `72c347230107ef8a31098ec4d468a605244beef5f1ed00db97efa13518800653` (github-release-asset-digest); asset updated 2026-10-26T09:08:43Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true** ; attribution required
- training data: summary: Public-domain / permissively licensed audio plus synthetic audio generated by closed TTS providers; CC BY components Koniwa tnc (CC BY 3.0) and SIWIS (CC BY 4.0); residualRisk: Training audio partly synthetic from closed TTS providers (provider terms of service are not verifiable); the model owner asserts synthetic data is not copyrightable and licenses the weights Apache-2.0.
- attribution entries: Koniwa tnc - CC BY 3.0 - https://github.com/koniwa/koniwa | SIWIS - CC BY 4.0 - https://datashare.ed.ac.uk/handle/10283/2353
- base: ONNX converted by taylorchu/kokoro-onnx v0.2.0 from hexgrad/Kokoro-82M v1.0 (sherpa docs)
- evidence: https://huggingface.co/hexgrad/Kokoro-82M  
  > license: apache-2.0 (model card front matter); 'With Apache-licensed weights, Kokoro can be deployed anywhere from production environments to personal projects.'
- evidence: https://huggingface.co/hexgrad/Kokoro-82M#training-details  
  > 'Kokoro was trained exclusively on permissive/non-copyrighted audio data and IPA phoneme labels' (public domain, Apache/MIT audio, synthetic audio from closed TTS models).
- evidence: https://huggingface.co/hexgrad/Kokoro-82M#creative-commons-attribution  
  > CC BY audio used in training: Koniwa 'tnc' (<1h, CC BY 3.0) and SIWIS (<11h, CC BY 4.0), added from v0.19 on.
- notes: Pack carries Apache-2.0 LICENSE (11358 bytes). kokoro-onnx converter repo license not independently verified (conversion only).
- risks: Asset re-uploaded 2026-10-26 (checksum.txt stale) - re-validate against sherpa-onnx 1.13.x; Contains non-supported-language voices (see hiddenSidRanges); Training audio partly synthetic from closed TTS providers (provider terms of service are not verifiable); the model owner asserts synthetic data is not copyrightable and licenses the weights Apache-2.0.
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-kokoro-v0-19-int8-v1` - English - Kokoro v0.19 int8 (11 voices)

- status: **approved**; type `kokoro`; appSupported `True`; languages en-US, en-GB
- upstream: `kokoro-int8-en-v0_19.tar.bz2`, 103,248,205 bytes, sha256 `c9f0dd393615805b0bab050c340834d5e684e732aec91c0e860cd30e982c08bd` (github-release-asset-digest); asset updated 2025-08-10T02:45:36Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true** ; attribution required
- training data: summary: Public-domain / permissively licensed audio plus synthetic audio generated by closed TTS providers; CC BY components Koniwa tnc (CC BY 3.0) and SIWIS (CC BY 4.0); residualRisk: Training audio partly synthetic from closed TTS providers (provider terms of service are not verifiable); the model owner asserts synthetic data is not copyrightable and licenses the weights Apache-2.0.
- attribution entries: Koniwa tnc - CC BY 3.0 - https://github.com/koniwa/koniwa | SIWIS - CC BY 4.0 - https://datashare.ed.ac.uk/handle/10283/2353
- evidence: https://huggingface.co/hexgrad/kLegacy  
  > Legacy repo hosting v0.19 weights: license: apache-2.0 (front matter via API)
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html  
  > 'kokoro-en-v0_19 (English, 11 speakers) ... The ONNX model is from https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files'; archive lists LICENSE (11K)
- evidence: https://huggingface.co/hexgrad/Kokoro-82M#releases  
  > v0.19: <100 hrs training data, 1 language & 10 voices
- notes: v0.19 data statement is the same permissive/synthetic policy; Koniwa/SIWIS CC BY added from v0.19 (22 Nov 2024).
- risks: Training audio partly synthetic from closed TTS providers (provider terms of service are not verifiable); the model owner asserts synthetic data is not copyrightable and licenses the weights Apache-2.0.; Superseded in quality by v1.0 (more voices); keep as small English-only option
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-coqui-vctk-vits-v1` - English - Coqui VCTK VITS (109 voices)

- status: **approved**; type `vits`; appSupported `True`; languages en-GB
- upstream: `vits-coqui-en-vctk.tar.bz2`, 122,412,029 bytes, sha256 `32da47c0def9cedaa6275df058e3b57d1863ae0a0f3646a5ec8adb7562d59ded` (checksum.txt); asset updated 2023-12-05T11:41:46Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true** ; attribution required
- training data: name: VCTK; license: CC-BY-4.0
- evidence: https://github.com/coqui-ai/TTS/blob/dev/TTS/.models.json  
  > tts_models/en/vctk/vits entry: "license": "apache 2.0" (author Eren @erogol; description: VITS trained on VCTK with 109 speakers)
- evidence: https://huggingface.co/datasets/CSTR-Edinburgh/vctk  
  > VCTK dataset card license: cc-by-4.0
- notes: License is a registry field of Coqui's model zoo (Coqui the company has wound down; no standalone LICENSE file shipped with the weights). Pack needs espeak-ng-data (Coqui VITS uses espeak phonemes).
- risks: No sherpa docs page for this model; espeak voice settings unknown - smoke test mandatory; License evidence is a JSON registry field, not a license file
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-coqui-ljspeech-vits-v1` - English - Coqui LJSpeech VITS (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-coqui-en-ljspeech.tar.bz2`, 115,418,583 bytes, sha256 `c545bc8f7c74b888de053f602d0bb8d9868a204aa352f0ff333553092ba19eac` (checksum.txt); asset updated 2023-12-05T11:41:22Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true**
- training data: name: LJ Speech; license: Unlicense
- evidence: https://github.com/coqui-ai/TTS/blob/dev/TTS/.models.json  
  > tts_models/en/ljspeech/vits entry: "license": "apache 2.0"; vits--neon entry: "license": "bsd-3-clause" (NeonGeckoCom)
- evidence: https://huggingface.co/datasets/keithito/lj_speech  
  > LJ Speech: unlicense
- risks: Single voice; low priority
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-icefall-ljspeech-medium-v1` - English - icefall LJSpeech medium (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-icefall-en_US-ljspeech-medium.tar.bz2`, 73,509,183 bytes, sha256 `5872080507e1d2b3c92f5c827be94928782724f1486ed4dcda5dc662c1478efd` (github-release-asset-digest); asset updated 2026-10-29T03:35:37Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true**
- training data: name: LJ Speech; license: Unlicense
- evidence: https://github.com/k2-fsa/icefall/blob/master/LICENSE  
  > icefall is Apache License 2.0 (trained by k2-fsa team)
- evidence: https://huggingface.co/datasets/keithito/lj_speech  
  > LJ Speech: unlicense (public domain)
- notes: No model card for the converted weights found; GitHub assets re-uploaded 2026-10-29.
- risks: Asset re-uploaded 2026-10-29 (checksum.txt stale); Single voice; low priority
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-icefall-ljspeech-low-v1` - English - icefall LJSpeech low (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-icefall-en_US-ljspeech-low.tar.bz2`, 31,722,454 bytes, sha256 `85dfae5a9c8143100a9106a90b0adb2f2c93682143759672b82c985e779d0d00` (github-release-asset-digest); asset updated 2026-10-29T03:35:44Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true**
- training data: name: LJ Speech; license: Unlicense
- evidence: https://github.com/k2-fsa/icefall/blob/master/LICENSE  
  > icefall is Apache License 2.0 (trained by k2-fsa team)
- evidence: https://huggingface.co/datasets/keithito/lj_speech  
  > LJ Speech: unlicense (public domain)
- notes: No model card for the converted weights found; GitHub assets re-uploaded 2026-10-29.
- risks: Asset re-uploaded 2026-10-29 (checksum.txt stale); Single voice; low priority
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-melo-v1` - English - MeloTTS (5 accents)

- status: **approved**; type `vits`; appSupported `True`; languages en-US, en-GB, en-AU, en-IN
- upstream: `vits-melo-tts-en.tar.bz2`, 162,758,237 bytes, sha256 `f87bc5752ea3ec34273a2cc0c5086854c18b6b89dfd0534b5248e86a14cedb5d` (checksum.txt); asset updated 2024-11-03T12:31:11Z
- licence: `MIT`; commercialUse **true**, redistribution **true** ; attribution required
- training data: summary: NOT DISCLOSED by MyShell; residualRisk: training data unknown
- evidence: https://huggingface.co/myshell-ai/MeloTTS-English  
  > 'This library is under MIT License, which means it is free for both commercial and non-commercial use.' (front matter license: mit)
- evidence: https://huggingface.co/csukuangfj/vits-melo-tts-zh_en  
  > README: 'there are 5 female speakers in the model For English TTS.'
- risks: Training data undisclosed (explicit MIT grant only); Speaker/accent order must be read from model metadata in CI; No sherpa docs page for this model

#### `en-piper-en-gb-cori-high-v1` - English (UK) - Piper cori (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages en-GB
- upstream: `vits-piper-en_GB-cori-high.tar.bz2`, 115,574,061 bytes, sha256 `42922f07738fcde2e49eed4e959635692f73b933de35a6b7c1010162ff566292` (github-release-asset-digest); asset updated 2025-06-30T02:22:38Z
- licence: `Public-Domain (no SPDX; CC0-equivalent dedication claimed by author)`; commercialUse **true**, redistribution **true**
- training data: name: LibriVox recordings (public domain); license: Public domain; base: scratch
- base: scratch
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_GB/cori/medium/MODEL_CARD  
  > MODEL_CARD: Speakers: 1 | License: public domain | UK English female voice. Single Speaker. Trained from scratch on medium quality settings for 640 epochs. I put together the dataset, which ended up with about 24 hours of recordings. All recordings came from LibriVox.org.
- evidence: https://huggingface.co/rhasspy/piper-voices  
  > Repo-level front matter: license: mit (applies to repo files; each voice dataset carries its own license in MODEL_CARD)
- notes: Licence rests on the MODEL_CARD declaration; the voice weights have no separate LICENSE file in the Piper voices repo.
- risks: Piper voice requires espeak-ng-data (GPL-3.0-or-later bundle)
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-piper-en-gb-cori-medium-v1` - English (UK) - Piper cori (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages en-GB
- upstream: `vits-piper-en_GB-cori-medium.tar.bz2`, 67,257,412 bytes, sha256 `49c9a5361bbdd95d7ca9687c4de11e5908481f65e7c7c368960df79949fdac2b` (github-release-asset-digest); asset updated 2025-06-30T02:22:22Z
- licence: `Public-Domain (no SPDX; CC0-equivalent dedication claimed by author)`; commercialUse **true**, redistribution **true**
- training data: name: LibriVox recordings (public domain); license: Public domain; base: scratch
- base: scratch
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_GB/cori/medium/MODEL_CARD  
  > MODEL_CARD: Speakers: 1 | License: public domain | UK English female voice. Single Speaker. Trained from scratch on medium quality settings for 640 epochs. I put together the dataset, which ended up with about 24 hours of recordings. All recordings came from LibriVox.org.
- evidence: https://huggingface.co/rhasspy/piper-voices  
  > Repo-level front matter: license: mit (applies to repo files; each voice dataset carries its own license in MODEL_CARD)
- notes: Licence rests on the MODEL_CARD declaration; the voice weights have no separate LICENSE file in the Piper voices repo.
- risks: Piper voice requires espeak-ng-data (GPL-3.0-or-later bundle)
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-piper-en-us-john-medium-v1` - English (US) - Piper john (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-piper-en_US-john-medium.tar.bz2`, 67,249,181 bytes, sha256 `d90362cfa48e429d3096f644785184446145b6e38216f2eaf4c0601b8aad5a36` (github-release-asset-digest); asset updated 2025-12-02T06:54:40Z
- licence: `Public-Domain (no SPDX; CC0-equivalent dedication claimed by author)`; commercialUse **true**, redistribution **true**
- training data: name: LibriVox recordings (public domain); license: Public domain; base: finetuned from Kristin (public domain scratch model)
- base: finetuned from Kristin (public domain scratch model)
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/john/medium/MODEL_CARD  
  > MODEL_CARD: Speakers: 1 | License: public domain | US English male voice. Single Speaker. Finetuned from Kristin (above) on medium quality settings for an additional 600 epochs. I put together the dataset, which ended up with about 12.5 hours of recordings. All recordings came from LibriVox.org.
- evidence: https://huggingface.co/rhasspy/piper-voices  
  > Repo-level front matter: license: mit (applies to repo files; each voice dataset carries its own license in MODEL_CARD)
- notes: Licence rests on the MODEL_CARD declaration; the voice weights have no separate LICENSE file in the Piper voices repo.
- risks: Piper voice requires espeak-ng-data (GPL-3.0-or-later bundle)
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-piper-en-us-kristin-medium-v1` - English (US) - Piper kristin (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-piper-en_US-kristin-medium.tar.bz2`, 67,259,230 bytes, sha256 `c2206f572df2956c50b1ae3367eebce3853c663e890cba8048cd62b1e4dbe6c7` (github-release-asset-digest); asset updated 2025-06-30T02:21:31Z
- licence: `Public-Domain (no SPDX; CC0-equivalent dedication claimed by author)`; commercialUse **true**, redistribution **true**
- training data: name: LibriVox recordings (public domain); license: Public domain; base: scratch
- base: scratch
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/kristin/medium/MODEL_CARD  
  > MODEL_CARD: Speakers: 1 | License: public domain | US English female voice. Single Speaker. Trained from scratch on medium quality settings for 2000 epochs. I put together the dataset, which ended up with about 11.5 hours of recordings. All recordings came from LibriVox.org.
- evidence: https://huggingface.co/rhasspy/piper-voices  
  > Repo-level front matter: license: mit (applies to repo files; each voice dataset carries its own license in MODEL_CARD)
- notes: Licence rests on the MODEL_CARD declaration; the voice weights have no separate LICENSE file in the Piper voices repo.
- risks: Piper voice requires espeak-ng-data (GPL-3.0-or-later bundle)
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-piper-en-us-libritts-high-v1` - English (US) - Piper libritts (904 voices)

- status: **approved**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-piper-en_US-libritts-high.tar.bz2`, 131,033,598 bytes, sha256 `d9d35056703fd38ed38e95c202a50f603fefdc8a92a7b6332c4f1a41616eac72` (github-release-asset-digest); asset updated 2025-12-02T06:55:21Z
- licence: `CC-BY-4.0`; commercialUse **true**, redistribution **true** ; attribution required
- training data: name: LibriTTS (OpenSLR 60); license: CC-BY-4.0; base: scratch; url: https://huggingface.co/datasets/mythicinfinity/libritts
- base: scratch
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/libritts/high/MODEL_CARD  
  > MODEL_CARD: Speakers: 904 | License: CC BY 4.0 | Trained from scratch on train-clean-360.
- evidence: https://huggingface.co/rhasspy/piper-voices  
  > Repo-level front matter: license: mit (applies to repo files; each voice dataset carries its own license in MODEL_CARD)
- notes: Licence rests on the MODEL_CARD declaration; the voice weights have no separate LICENSE file in the Piper voices repo.
- risks: Piper voice requires espeak-ng-data (GPL-3.0-or-later bundle); Large speaker set: audit + catalog needed
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-piper-en-us-ljspeech-high-v1` - English (US) - Piper ljspeech (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-piper-en_US-ljspeech-high.tar.bz2`, 115,817,679 bytes, sha256 `00c6408d2409050312193b0d40ae07fde28af7d3d45a56efcc55440db516b935` (github-release-asset-digest); asset updated 2025-07-26T03:18:44Z
- licence: `Public-Domain (no SPDX; CC0-equivalent dedication claimed by author)`; commercialUse **true**, redistribution **true**
- training data: name: LJ Speech; license: Public domain; base: scratch; url: https://huggingface.co/datasets/keithito/lj_speech
- base: scratch
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/medium/MODEL_CARD  
  > MODEL_CARD: Speakers: 1 | License: public domain | US English female voice. Single speaker. Trained from scratch for 1000 epochs on medium quality settings using the LJ Speech dataset. I reencoded the recordings to a bit rate of 22500 Hz so it would match other voices released for Piper TTS.
- evidence: https://huggingface.co/rhasspy/piper-voices  
  > Repo-level front matter: license: mit (applies to repo files; each voice dataset carries its own license in MODEL_CARD)
- notes: Licence rests on the MODEL_CARD declaration; the voice weights have no separate LICENSE file in the Piper voices repo.
- risks: Piper voice requires espeak-ng-data (GPL-3.0-or-later bundle)
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-piper-en-us-ljspeech-medium-v1` - English (US) - Piper ljspeech (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-piper-en_US-ljspeech-medium.tar.bz2`, 67,169,893 bytes, sha256 `3dfb4b759d8be032a4903a9538d128b0fda2a06ab1de6cbc2d93a97e2dd83dba` (github-release-asset-digest); asset updated 2025-07-26T03:06:49Z
- licence: `Public-Domain (no SPDX; CC0-equivalent dedication claimed by author)`; commercialUse **true**, redistribution **true**
- training data: name: LJ Speech; license: Public domain; base: scratch; url: https://huggingface.co/datasets/keithito/lj_speech
- base: scratch
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/medium/MODEL_CARD  
  > MODEL_CARD: Speakers: 1 | License: public domain | US English female voice. Single speaker. Trained from scratch for 1000 epochs on medium quality settings using the LJ Speech dataset. I reencoded the recordings to a bit rate of 22500 Hz so it would match other voices released for Piper TTS.
- evidence: https://huggingface.co/rhasspy/piper-voices  
  > Repo-level front matter: license: mit (applies to repo files; each voice dataset carries its own license in MODEL_CARD)
- notes: Licence rests on the MODEL_CARD declaration; the voice weights have no separate LICENSE file in the Piper voices repo.
- risks: Piper voice requires espeak-ng-data (GPL-3.0-or-later bundle)
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `en-piper-en-us-norman-medium-v1` - English (US) - Piper norman (1 voice)

- status: **approved**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-piper-en_US-norman-medium.tar.bz2`, 67,203,672 bytes, sha256 `1f32065d480abe9abc7c7f91442125d0b34c1cc065d1e600466cac408eabf3b8` (github-release-asset-digest); asset updated 2025-06-30T02:22:57Z
- licence: `Public-Domain (no SPDX; CC0-equivalent dedication claimed by author)`; commercialUse **true**, redistribution **true**
- training data: name: LibriVox recordings (public domain); license: Public domain; base: scratch
- base: scratch
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/norman/medium/MODEL_CARD  
  > MODEL_CARD: Speakers: 1 | License: public domain | US English male voice. Single Speaker. Trained from scratch on medium quality settings for 1200 epochs. I put together the dataset, which ended up with about 15.5 hours of recordings. All recordings came from LibriVox.org. I forgot to save the ckpt file on this one, sorry.
- evidence: https://huggingface.co/rhasspy/piper-voices  
  > Repo-level front matter: license: mit (applies to repo files; each voice dataset carries its own license in MODEL_CARD)
- notes: Licence rests on the MODEL_CARD declaration; the voice weights have no separate LICENSE file in the Piper voices repo.
- risks: Piper voice requires espeak-ng-data (GPL-3.0-or-later bundle)
- bundles: espeak-ng-data (GPL-3.0-or-later) - see section 2, item 1

#### `zh-aishell3-vits-8k-v1` - Mandarin - AISHELL-3 VITS (174 voices, legacy)

- status: **approved**; type `vits`; appSupported `True`; languages zh-CN
- upstream: `vits-zh-aishell3.tar.bz2`, 146,922,607 bytes, sha256 `c476bd76d7a25171014bdc1e3a38422f5af2045f43852d90dc4df67660482e20` (checksum.txt); asset updated 2024-04-08T01:42:55Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true** ; attribution required
- training data: name: AISHELL-3; license: Apache-2.0
- evidence: https://huggingface.co/jackyqs/vits-aishell3-175-chinese  
  > front matter license: apache-2.0; pretrained VITS on AISHELL-3 ('基于vits_chinese和aishell3 175人中文训练的预训练模型')
- evidence: https://huggingface.co/datasets/AISHELL/AISHELL-3  
  > AISHELL-3 dataset card: license apache-2.0
- evidence: https://github.com/PlayVoice/vits_chinese/blob/master/LICENSE  
  > vits_chinese code: MIT License (Copyright (c) 2022 PlayVoice)
- evidence: https://huggingface.co/csukuangfj/vits-zh-aishell3  
  > Converter README: G_AISHELL.pth is downloaded from https://huggingface.co/jackyqs/vits-aishell3-175-chinese
- risks: 8 kHz output - lower quality than the icefall variant; largely redundant with zh-aishell3-icefall-v1; rule.far is 172 MB (pack is ~147 MB compressed)

## 4. Candidates (not approved; blocker stated)

#### `en-vctk-vits-v1` - English - VCTK VITS (109 voices)

- status: **candidate**; type `vits`; appSupported `True`; languages en-GB
- upstream: `vits-vctk.tar.bz2`, 151,758,892 bytes, sha256 `4f0a02db66914b3760b144cebc004e65dd4d1aeef43379f2b058849e74002490` (checksum.txt); asset updated 2023-11-21T08:43:34Z
- licence: `MIT (code) + CC-BY-4.0 (data); weights unstated`; commercialUse **unknown**, redistribution **true** ; attribution required
- training data: name: VCTK; license: CC-BY-4.0; url: https://huggingface.co/datasets/CSTR-Edinburgh/vctk
- evidence: https://github.com/jaywalnut310/vits  
  > Repo LICENSE is MIT (Copyright 2021 Jaehyeon Kim); README: 'We also provide the pretrained models.'
- evidence: https://huggingface.co/datasets/CSTR-Edinburgh/vctk  
  > VCTK dataset card license: cc-by-4.0
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html  
  > 'This model is converted from pretrained_vctk.pth, which is trained by the vits author Jaehyeon Kim on the VCTK dataset ... 109 speakers.'
- evidence: https://huggingface.co/csukuangfj/vits-vctk  
  > Converter repo front matter declares license: apache-2.0 (converter's declaration, not the weight author's); lexicon from CMU-in-IPA.zip (umass), license not stated
- notes: No espeak-ng-data needed (lexicon front end), so no GPL bundle. Blockers: weights license not explicit, CMU-in-IPA lexicon license not stated.
- blocked by: Weights license not explicit (only the MIT code license of the VITS repo) and CMU-in-IPA lexicon license not stated.
- risks: Pretrained weights come from the VITS author's Google Drive link (repo jaywalnut310/vits is MIT licensed but the README only says 'We also provide the pretrained models'); no separate license statement for the weights.; OOV words depend on lexicon coverage

#### `en-ljs-vits-v1` - English - LJSpeech VITS (1 voice)

- status: **candidate**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-ljs.tar.bz2`, 109,037,061 bytes, sha256 `78f7df445fcd42d1dd6df2c78c66c2c2fee8b7abecc6ae255a5950097a6558bc` (checksum.txt); asset updated 2024-04-22T05:47:13Z
- licence: `MIT (code) + Unlicense (data); weights unstated`; commercialUse **unknown**, redistribution **true**
- training data: name: LJ Speech; license: Unlicense / public domain; url: https://huggingface.co/datasets/keithito/lj_speech
- evidence: https://github.com/jaywalnut310/vits  
  > Repo LICENSE is MIT; pretrained models provided via Google Drive link, no separate weights license.
- evidence: https://huggingface.co/datasets/keithito/lj_speech  
  > LJ Speech dataset card license: unlicense (public domain)
- evidence: https://huggingface.co/csukuangfj/vits-ljs  
  > Converter repo README: pretrained_ljs.pth 'is downloaded from https://huggingface.co/yo2266911/mb-vits-models/...' (third-party re-host); front matter license: apache-2.0 (converter's)
- blocked by: Weights license not explicit; weights re-hosted by a third party before conversion.
- risks: Pretrained weights come from the VITS author's Google Drive link (repo jaywalnut310/vits is MIT licensed but the README only says 'We also provide the pretrained models'); no separate license statement for the weights.; Weights re-hosted by a third party (yo2266911/mb-vits-models) before conversion

#### `en-inflect-micro-v2-v1` - English - Inflect Micro v2 (1 voice)

- status: **candidate**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-inflect-en-micro-v2.tar.bz2`, 42,956,555 bytes, sha256 `ed3c594d9c49b6c64ffe27f4b368ea8a700bcc27ff80610771408ee81cd96574` (github-release-asset-digest); asset updated 2026-07-27T12:15:15Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true**
- training data: summary: Fixed synthetic voice; training data provenance not documented in the card
- evidence: https://huggingface.co/owensong/Inflect-Micro-v2  
  > front matter license: apache-2.0; 'The release contains one fixed synthetic English voice.'
- blocked by: Training-data provenance of the synthetic voice is undocumented; unevaluated.
- risks: Brand-new community model, training data undocumented; single voice; quality not evaluated

#### `en-kitten-nano-v0-8-v1` - English - KittenTTS nano 0.8 (8 voices)

- status: **candidate**; type `kitten`; appSupported `False`; languages en-US
- upstream: `kitten-nano-en-v0_8-int8.tar.bz2`, 31,220,690 bytes, sha256 `6fa5be852612ce761094ba74ee6123b4fc4acfefa79bf64dc63acae4a83af2fd` (github-release-asset-digest); asset updated 2026-05-12T08:15:11Z
- licence: `Apache-2.0`; commercialUse **true**, redistribution **true**
- training data: summary: not documented in the cards read
- evidence: https://huggingface.co/KittenML/kitten-tts-nano-0.8  
  > front matter license: apache-2.0
- evidence: https://huggingface.co/KittenML/kitten-tts-mini-0.8  
  > front matter license: apache-2.0
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kitten.html  
  > 'This page lists pre-trained models from https://github.com/KittenML/KittenTTS.'
- blocked by: App runtime supports only vits/kokoro (SherpaOnnxTTSClient.swift:249-266); kitten needs a new type + manifest enum (STOP: Codable change)
- risks: appSupported=false: record only, do not publish

#### `en-matcha-icefall-ljspeech-v1` - English - Matcha LJSpeech (1 voice)

- status: **candidate**; type `matcha`; appSupported `False`; languages en-US
- upstream: `matcha-icefall-en_US-ljspeech.tar.bz2`, 76,757,969 bytes, sha256 `c2c7e2abb085603aa348065a86be886407c601f666bd47a31333755779eca653` (github-release-asset-digest); asset updated 2026-10-29T03:36:20Z
- licence: `Apache-2.0 (icefall) + Unlicense (data)`; commercialUse **true**, redistribution **true**
- training data: name: LJ Speech; license: Unlicense
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/matcha.html  
  > 'The dataset used to train the model is from https://keithito.com/LJ-Speech-Dataset/' (trained with icefall)
- evidence: https://huggingface.co/datasets/keithito/lj_speech  
  > LJ Speech: unlicense
- blocked by: type matcha is not supported by the App runtime
- risks: appSupported=false; asset re-uploaded 2026-10-29

#### `en-pocket-tts-v1` - English - Pocket TTS (voice-clone engine)

- status: **candidate**; type `pocket-tts`; appSupported `False`; languages en, fr, de, pt, it, es
- upstream: `sherpa-onnx-pocket-tts-int8-2026-01-26.tar.bz2`, 98,336,520 bytes, sha256 `2f3b88823cbbb9bf0b2477ec8ae7b3fec417b3a87b6bb5f256dba66f2ad967cb` (github-release-asset-digest); asset updated 2026-02-10T15:40:31Z
- licence: `CC-BY-4.0 (gated, with prohibited-use terms)`; commercialUse **unknown**, redistribution **unknown**
- training data: summary: not read (gated model card)
- evidence: https://huggingface.co/kyutai/pocket-tts  
  > front matter license: cc-by-4.0, gated: auto; extra_gated_prompt lists prohibited uses incl. 'voice impersonation or cloning without explicit and lawful consent'
- blocked by: type pocket-tts is not supported by the App runtime; gated model with use restrictions
- risks: appSupported=false; gated access terms must be reviewed before redistribution

#### `multi-supertonic-3-int8-v1` - Supertonic 3 int8 - Japanese / Korean / English + 28 languages (10 voices)

- status: **candidate**; type `supertonic`; appSupported `False`; languages en, ko, ja, ar, bg, cs...
- upstream: `sherpa-onnx-supertonic-3-tts-int8-2026-05-11.tar.bz2`, 128,774,318 bytes, sha256 `82fa96f91c4ef8abaae3a14a3f4153facf88bed821d1f7331cec2700f432c427` (github-release-asset-digest); asset updated 2026-05-13T01:37:35Z
- licence: `LicenseRef-BigScience-OpenRAIL-M (not in the allow-list)`; commercialUse **true**, redistribution **true** ; attribution required
- training data: summary: Not disclosed in the card read
- evidence: https://huggingface.co/Supertone/supertonic-3  
  > 'The accompanying model is released under the OpenRAIL-M License.' (sample code MIT); front matter license: openrail
- evidence: https://huggingface.co/Supertone/supertonic-3/blob/main/LICENSE  
  > Section II.2: 'perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to reproduce ... sublicense, and distribute ... the Model'
- evidence: https://huggingface.co/Supertone/supertonic-3/blob/main/LICENSE  
  > Section III.4.a: use-based restrictions 'MUST be included as an enforceable provision by You in any type of legal agreement (e.g. a license) governing the use and/or distribution of the Model'; Attachment A (e): output must not be placed in a context 'without expressly and intelligibly disclaiming that the content is machine generated'
- notes: OpenRAIL-M permits commercial use and redistribution but imposes pass-through use restrictions (Attachment A: no impersonation without consent, no deceptive unlabelled machine-generated content, no medical advice, etc.). Needs product/legal sign-off and an addition to Readori's terms; not in the SPDX allow-list of the gate.
- blocked by: appSupported=false: App runtime supports only vits/kokoro; needs a 'supertonic' type in the manifest (Codable enum = STOP) and generation-config 'lang' plumbing. sherpa-onnx 1.13.2 (the version the App embeds) already contains Supertonic 3 support (CHANGELOG: 1.13.2 'Support Supertonic 3 TTS (#3605)').
- risks: License not in allow-list: OpenRAIL-M needs explicit LEAD/legal decision; Use-restriction pass-through must be added to the App terms; Need to confirm the 1.13.2 C API exposes the per-call 'lang' extra used in the Python example; Japanese/Korean text quality on iOS int8 not evaluated

#### `multi-supertonic-2-int8-v1` - Supertonic 2 int8 - English / Korean / Spanish / Portuguese / French

- status: **candidate**; type `supertonic`; appSupported `False`; languages en, ko, es, pt, fr
- upstream: `sherpa-onnx-supertonic-tts-int8-2026-03-06.tar.bz2`, 84,692,981 bytes, sha256 `8c74359f63edd5045d47747f65331f0f6dbcbc91d7e898dd756d631295fe3259` (github-release-asset-digest); asset updated 2026-03-06T07:08:14Z
- licence: `LicenseRef-BigScience-OpenRAIL-M (not in the allow-list)`; commercialUse **true**, redistribution **true**
- training data: summary: not disclosed
- evidence: https://huggingface.co/Supertone/supertonic-2  
  > 'The accompanying model is released under the OpenRAIL-M License.' (front matter license: openrail; languages en ko es pt fr)
- blocked by: appSupported=false (supertonic type); superseded by Supertonic 3

### 4.1 Piper English voices blocked on the Lessac licence (or other open question)

| id | speakers | dataset licence (MODEL_CARD) | base checkpoint | blocker |
|---|---:|---|---|---|
| `en-piper-en-gb-alba-medium-v1` | 1 | CC-BY-4.0 | lessac | Blocked: Fine-tuned from the Piper 'lessac' medium checkpoint. Lessac ... |
| `en-piper-en-gb-aru-medium-v1` | 12 | CC-BY-4.0 | lessac | Blocked: Fine-tuned from the Piper 'lessac' medium checkpoint. Lessac ... |
| `en-piper-en-gb-jenny-dioco-medium-v1` | 1 | Dioco custom: attribution required, commercial use permitted | lessac | Blocked: Fine-tuned from the Piper 'lessac' medium checkpoint. Lessac ... |
| `en-piper-en-gb-northern-english-male-medium-v1` | 1 | CC-BY-SA-4.0 | lessac | Blocked: Fine-tuned from the Piper 'lessac' medium checkpoint. Lessac ... |
| `en-piper-en-gb-southern-english-female-low-v1` | 6 | unverified, family suggests CC-BY-SA-4.0 | ? | No model card for this voice; dataset licence inferred only from the s... |
| `en-piper-en-gb-southern-english-female-medium-v1` | 6 | unverified, family suggests CC-BY-SA-4.0 | ? | No model card for this voice; dataset licence inferred only from the s... |
| `en-piper-en-gb-southern-english-male-medium-v1` | 8 | unverified, family suggests CC-BY-SA-4.0 | ? | No model card for this voice; dataset licence inferred only from the s... |
| `en-piper-en-gb-vctk-medium-v1` | 109 | CC-BY-4.0 | lessac | Blocked: Fine-tuned from the Piper 'lessac' medium checkpoint. Lessac ... |
| `en-piper-en-us-arctic-medium-v1` | 18 | 'See LICENSE file' (CMU ARCTIC; LICENSE not read) | lessac | Blocked: Fine-tuned from the Piper 'lessac' medium checkpoint. Lessac ... |
| `en-piper-en-us-bryce-medium-v1` | 1 | Public domain (author's own voice) | finetuned from an UNRELEASED voice (2500 epochs) - base data unknown | Fine-tuned from an unreleased base voice with undocumented training da... |
| `en-piper-en-us-joe-medium-v1` | 1 | CC0-1.0 | lessac | Blocked: Fine-tuned from the Piper 'lessac' medium checkpoint. Lessac ... |
| `en-piper-en-us-lessac-high-v1` | 1 | Lessac Blizzard 2013 (license link only) | scratch | Blocked: Lessac Blizzard 2013 dataset license text could not be read w... |
| `en-piper-en-us-lessac-low-v1` | 1 | Lessac Blizzard 2013 (license link only) | scratch | Blocked: Lessac Blizzard 2013 dataset license text could not be read w... |
| `en-piper-en-us-lessac-medium-v1` | 1 | Lessac Blizzard 2013 (license link only) | scratch | Blocked: Lessac Blizzard 2013 dataset license text could not be read w... |
| `en-piper-en-us-libritts-r-medium-v1` | 904 | CC-BY-4.0 | lessac | Blocked: Fine-tuned from the Piper 'lessac' medium checkpoint. Lessac ... |
| `en-piper-en-us-reza-ibrahim-medium-v1` | 1 | CC0 (card) | lessac | Blocked: Fine-tuned from the Piper 'lessac' medium checkpoint. Lessac ... |
| `en-piper-en-us-sam-medium-v1` | 1 | Apache-2.0 | lessac | Blocked: Fine-tuned from the Piper 'lessac' medium checkpoint. Lessac ... |

Evidence per row is in `models.draft.yaml` (`license.evidence`, MODEL_CARD quote + link under https://huggingface.co/rhasspy/piper-voices/blob/main/en/...). Quality-tier siblings (low/medium/high) share the family card; I fetched the card for one tier per voice (and for lessac/ryan/ljspeech/cori/amy all tiers) - CI should re-check each tier.

## 5. Excluded

### 5.1 Excluded with full evidence blocks (existing pack, notable models)

#### `yue-xiaomaiiwn-v1` - Cantonese - VITS (1 voice)

- status: **excluded**; type `vits`; appSupported `True`; languages yue
- upstream: `vits-cantonese-hf-xiaomaiiwn.tar.bz2`, 107,995,442 bytes, sha256 `bf3013cd4be34f531b7e514e708d835584dd60c9ad6eaf467ac1402005c04e46` (checksum.txt); asset updated 2024-02-20T02:56:36Z
- licence: `UNKNOWN`; commercialUse **unknown**, redistribution **unknown**
- training data: summary: UNKNOWN - no training-data statement anywhere.
- evidence: https://huggingface.co/csukuangfj/vits-cantonese-hf-xiaomaiiwn  
  > Converted repo has NO README / model card / license (API returns no cardData, no license tag; README.md 404).
- evidence: https://huggingface.co/xiaomaiiwn/vits-cantonese  
  > Original author repo is an empty placeholder: only a 'model' folder and .gitattributes, no license.
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html  
  > sherpa-onnx docs contain no provenance or license for this model.
- excluded because: No license or provenance anywhere (name 'hf' = converted from a Hugging Face Space). Gate: unknown => rejected. NOTE: the App's existing preset 'cantonese' and docs/Sherpa-onnx/Readori_TTS_Productization_CN.md list it as a recommended first pack - this needs a LEAD decision (drop from catalog or obtain a written license from the author).

#### `en-mms-eng-v1` - English - Meta MMS (1 voice)

- status: **excluded**; type `vits`; appSupported `True`; languages en
- upstream: `vits-mms-eng.tar.bz2`, 107,737,708 bytes, sha256 `8712cb52f71ee00bde27b8c18058d97a794fccf873c4629fbea0de87d31366b4` (checksum.txt); asset updated 2023-12-14T06:11:25Z
- licence: `CC-BY-NC-4.0`; commercialUse **false**, redistribution **false**
- training data: summary: MMS data, NC
- evidence: https://huggingface.co/facebook/mms-tts-eng  
  > front matter license: cc-by-nc-4.0 (Hugging Face API tag license:cc-by-nc-4.0)
- excluded because: Non-commercial (CC-BY-NC-4.0). Same applies to every vits-mms-* asset (deu, fra, nan, rus, spa, tha, ukr).

#### `zh-nan-mms-v1` - Min Nan - Meta MMS (1 voice)

- status: **excluded**; type `vits`; appSupported `True`; languages nan
- upstream: `vits-mms-nan.tar.bz2`, 107,721,349 bytes, sha256 `3118914a92bb7a72e55dab81d9d9c605384682a1c13501adcf68885d6d37cf83` (checksum.txt); asset updated 2023-12-14T06:11:24Z
- licence: `CC-BY-NC-4.0 (inferred from MMS family)`; commercialUse **false**, redistribution **false**
- training data: summary: MMS data, NC
- evidence: https://huggingface.co/facebook/mms-tts-kor  
  > sibling MMS-TTS model card: license cc-by-nc-4.0 (the nan card itself was not fetched; every MMS-TTS card checked - eng, kor - is NC)
- excluded because: Non-commercial (MMS-TTS family is CC-BY-NC-4.0). Only Chinese-dialect (Southern Min) model in the release.

#### `en-glados-v1` - English - GLaDOS (1 voice)

- status: **excluded**; type `vits`; appSupported `True`; languages en-US
- upstream: `vits-piper-en_US-glados-high.tar.bz2`, 115,586,982 bytes, sha256 `dcb52d4be94200d42b4d97ebb82ec398be27039f4719207283fa5e7d931b1cf3` (github-release-asset-digest); asset updated 2025-06-30T02:24:11Z
- licence: `UNKNOWN / third-party character IP`; commercialUse **unknown**, redistribution **unknown**
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/all/English/vits-piper-en_US-glados-high.html  
  > 'This model is converted from https://github.com/rhasspy/piper/issues/187#issuecomment-1805709037' (a user-posted model of a video-game character voice)
- excluded because: Voice of a commercial video-game character (copyrighted source audio), user-uploaded, no license.

#### `zh-piper-chaowen-medium-v1` - Mandarin - Piper chaowen (1 voice)

- status: **excluded**; type `vits`; appSupported `True`; languages zh-CN
- upstream: `vits-piper-zh_CN-chaowen-medium.tar.bz2`, 60,443,846 bytes, sha256 `1b69bdcf10bb6331c7f8a7591940febeb175c6bb86caa3802d96531f8e4ad211` (github-release-asset-digest); asset updated 2026-04-27T09:20:39Z
- licence: `CC0 data but base model trained on non-commercial data`; commercialUse **false**, redistribution **false**
- training data: license: CC0 data but base model trained on non-commercial data
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/zh/zh_CN/chaowen/medium/MODEL_CARD  
  > Dataset: OHF-Voice/voice-datasets, License: CC0; 'Finetuned from Xiao Ya voice (medium quality)' (Xiao Ya = BZNSYP, non-commercial)
- excluded because: Fine-tuned from the Xiao Ya checkpoint, whose data (BZNSYP) is non-commercial; derived weights treated as NC.
- risks: Piper zh needs g2pW on the Python side (xiao_ya card note) - sherpa uses lexicon

#### `zh-piper-huayan-medium-v1` - Mandarin - Piper huayan (1 voice)

- status: **excluded**; type `vits`; appSupported `True`; languages zh-CN
- upstream: `vits-piper-zh_CN-huayan-medium.tar.bz2`, 67,255,926 bytes, sha256 `dbdfec42b91d9cee31cce9ff4b3e9c305eb6fbf60546d071f7e46273554cce6b` (checksum.txt); asset updated 2024-12-24T06:41:41Z
- licence: `UNKNOWN`; commercialUse **unknown**, redistribution **unknown**
- training data: license: UNKNOWN
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/zh/zh_CN/huayan/medium/MODEL_CARD  
  > Dataset URL https://github.com/PlayVoice/HuaYan_TTS - 'License: Unknown'; finetuned from lessac
- excluded because: Dataset licence explicitly 'Unknown'.
- risks: Piper zh needs g2pW on the Python side (xiao_ya card note) - sherpa uses lexicon

#### `zh-piper-xiao-ya-medium-v1` - Mandarin - Piper xiao ya (1 voice)

- status: **excluded**; type `vits`; appSupported `True`; languages zh-CN
- upstream: `vits-piper-zh_CN-xiao_ya-medium.tar.bz2`, 60,462,944 bytes, sha256 `9396a3dffbb95b037acaa18094500f58d0db9a7c4f2689554e2539717cf0db65` (github-release-asset-digest); asset updated 2026-04-27T09:20:23Z
- licence: `Non-commercial (BZNSYP / DataBaker licence)`; commercialUse **false**, redistribution **false**
- training data: license: Non-commercial (BZNSYP / DataBaker licence)
- evidence: https://huggingface.co/rhasspy/piper-voices/blob/main/zh/zh_CN/xiao_ya/medium/MODEL_CARD  
  > Dataset: BZNSYP - 'License: Non-commercial use (see https://www.data-baker.com/data/index/TNtts/)'; trained from scratch
- excluded because: Non-commercial dataset (DataBaker BZNSYP).
- risks: Piper zh needs g2pW on the Python side (xiao_ya card note) - sherpa uses lexicon

#### `zh-vits-zh-ll-v1` - Mandarin - community fine-tune (5 voices)

- status: **excluded**; type `vits`; appSupported `True`; languages zh-CN
- upstream: `sherpa-onnx-vits-zh-ll.tar.bz2`, 118,810,709 bytes, sha256 `f7393d1bbc59709d5f52ea76cd5bceeec62f6a29f9c1f79ff64b4c15ec841f3a` (checksum.txt); asset updated 2024-04-25T09:58:53Z
- licence: `UNKNOWN`; commercialUse **unknown**, redistribution **unknown**
- training data: summary: UNKNOWN
- evidence: https://huggingface.co/csukuangfj/sherpa-onnx-vits-zh-ll  
  > README: 'This model is contributed by the community and trained using https://github.com/Plachtaa/VITS-fast-fine-tuning' - no license, no dataset statement; model card has no license tag
- evidence: https://github.com/Plachtaa/VITS-fast-fine-tuning  
  > Training framework repo is Apache-2.0 (code only; says nothing about the data or base weights)
- excluded because: No licence or data provenance; produced with a fast-fine-tuning framework whose base weights/data are undocumented.

#### `zh-matcha-baker-v1` - Mandarin - Matcha Baker (1 voice)

- status: **excluded**; type `matcha`; appSupported `False`; languages zh-CN
- upstream: `matcha-icefall-zh-baker.tar.bz2`, 75,463,556 bytes, sha256 `8da2e113b85dfea37b11bcdc994506aa86b584ee3348c2065271fb6f75cb83b8` (github-release-asset-digest); asset updated 2026-10-29T04:01:29Z
- licence: `Non-commercial (DataBaker)`; commercialUse **false**, redistribution **false**
- training data: license: non-commercial
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/matcha.html  
  > sherpa docs: 'The dataset used to train the model is from https://en.data-baker.com/datasets/freeDatasets/. The dataset is for non-commercial use only.'
- excluded because: Non-commercial training data AND unsupported type (matcha).

#### `zh-matcha-zh-en-v1` - Mandarin / English - Matcha (1 voice)

- status: **excluded**; type `matcha`; appSupported `False`; languages zh-CN, en-US
- upstream: `matcha-icefall-zh-en.tar.bz2`, 79,033,838 bytes, sha256 `271b804af570400d3bcdcb53bf6e53cc9f75180ee763b9f13eb5eaf2b0d086ef` (github-release-asset-digest); asset updated 2026-01-28T07:53:05Z
- licence: `UNKNOWN`; commercialUse **unknown**, redistribution **unknown**
- training data: summary: UNKNOWN (recipe derived from Baker NC recipe)
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese-English/matcha-icefall-zh-en.html  
  > 'It is from https://modelscope.cn/models/dengcunqin/matcha_tts_zh_en_20251010' (code modified from icefall baker_zh recipe); no licence or dataset statement in docs (ModelScope page not in authorised domains)
- excluded because: Unknown licence/data and unsupported type (matcha).

#### `zh-zipvoice-distill-int8-zh-en-v1` - Mandarin / English - ZipVoice (zero-shot) distill-int8-zh-en-emilia

- status: **excluded**; type `zipvoice`; appSupported `False`; languages zh-CN, en-US
- upstream: `sherpa-onnx-zipvoice-distill-int8-zh-en-emilia.tar.bz2`, 109,162,785 bytes, sha256 `77219c8b40f4ee8d73a7f902305ff6c1128ef9b54461c41b4ca6ed890b6c2803` (github-release-asset-digest); asset updated 2025-12-11T09:47:31Z
- licence: `UNRESOLVED (Emilia dataset: card metadata conflicts)`; commercialUse **unknown**, redistribution **unknown**
- training data: name: Emilia; license: conflicting metadata (CC-BY-NC-4.0 vs CC-BY-4.0)
- evidence: https://huggingface.co/k2-fsa/ZipVoice  
  > Directory table: zipvoice / zipvoice_distill trained on 'Emilia' (amphion/Emilia-Dataset)
- evidence: https://huggingface.co/datasets/amphion/Emilia  
  > API card metadata: license cc-by-nc-4.0 (gated; README itself not readable without login)
- evidence: https://huggingface.co/datasets/amphion/Emilia-Dataset  
  > API card metadata: license cc-by-4.0 (gated; README not readable) - conflicts with the sibling repo
- excluded because: Unsupported type (zipvoice, zero-shot voice cloning) and training-data licence unresolved/possibly NC.

#### `zh-zipvoice-distill-zh-en-v1` - Mandarin / English - ZipVoice (zero-shot) distill-zh-en-emilia

- status: **excluded**; type `zipvoice`; appSupported `False`; languages zh-CN, en-US
- upstream: `sherpa-onnx-zipvoice-distill-zh-en-emilia.tar.bz2`, 634,815,977 bytes, sha256 `9bcb4076c78d9f31778b54189831d999dcca148f640b3f69a1b3c5975bc63599` (github-release-asset-digest); asset updated 2025-08-21T10:29:59Z
- licence: `UNRESOLVED (Emilia dataset: card metadata conflicts)`; commercialUse **unknown**, redistribution **unknown**
- training data: name: Emilia; license: conflicting metadata (CC-BY-NC-4.0 vs CC-BY-4.0)
- evidence: https://huggingface.co/k2-fsa/ZipVoice  
  > Directory table: zipvoice / zipvoice_distill trained on 'Emilia' (amphion/Emilia-Dataset)
- evidence: https://huggingface.co/datasets/amphion/Emilia  
  > API card metadata: license cc-by-nc-4.0 (gated; README itself not readable without login)
- evidence: https://huggingface.co/datasets/amphion/Emilia-Dataset  
  > API card metadata: license cc-by-4.0 (gated; README not readable) - conflicts with the sibling repo
- excluded because: Unsupported type (zipvoice, zero-shot voice cloning) and training-data licence unresolved/possibly NC.

#### `zh-zipvoice-distill-fp32-zh-en-v1` - Mandarin / English - ZipVoice (zero-shot) distill-fp32-zh-en-emilia

- status: **excluded**; type `zipvoice`; appSupported `False`; languages zh-CN, en-US
- upstream: `sherpa-onnx-zipvoice-distill-fp32-zh-en-emilia.tar.bz2`, 477,800,463 bytes, sha256 `3b6729d03bf4ba64deeec113048bdbbe55dbc30580b609be76342e0099fd23a8` (github-release-asset-digest); asset updated 2025-12-11T09:47:47Z
- licence: `UNRESOLVED (Emilia dataset: card metadata conflicts)`; commercialUse **unknown**, redistribution **unknown**
- training data: name: Emilia; license: conflicting metadata (CC-BY-NC-4.0 vs CC-BY-4.0)
- evidence: https://huggingface.co/k2-fsa/ZipVoice  
  > Directory table: zipvoice / zipvoice_distill trained on 'Emilia' (amphion/Emilia-Dataset)
- evidence: https://huggingface.co/datasets/amphion/Emilia  
  > API card metadata: license cc-by-nc-4.0 (gated; README itself not readable without login)
- evidence: https://huggingface.co/datasets/amphion/Emilia-Dataset  
  > API card metadata: license cc-by-4.0 (gated; README not readable) - conflicts with the sibling repo
- excluded because: Unsupported type (zipvoice, zero-shot voice cloning) and training-data licence unresolved/possibly NC.

#### `zh-zipvoice-zh-en-v1` - Mandarin / English - ZipVoice (zero-shot) zh-en-emilia

- status: **excluded**; type `zipvoice`; appSupported `False`; languages zh-CN, en-US
- upstream: `sherpa-onnx-zipvoice-zh-en-emilia.tar.bz2`, 634,731,511 bytes, sha256 `098feeb0566875751eb8776b87060b9889b32b17d3649504e4514ce2b6a85100` (github-release-asset-digest); asset updated 2025-08-21T11:40:33Z
- licence: `UNRESOLVED (Emilia dataset: card metadata conflicts)`; commercialUse **unknown**, redistribution **unknown**
- training data: name: Emilia; license: conflicting metadata (CC-BY-NC-4.0 vs CC-BY-4.0)
- evidence: https://huggingface.co/k2-fsa/ZipVoice  
  > Directory table: zipvoice / zipvoice_distill trained on 'Emilia' (amphion/Emilia-Dataset)
- evidence: https://huggingface.co/datasets/amphion/Emilia  
  > API card metadata: license cc-by-nc-4.0 (gated; README itself not readable without login)
- evidence: https://huggingface.co/datasets/amphion/Emilia-Dataset  
  > API card metadata: license cc-by-4.0 (gated; README not readable) - conflicts with the sibling repo
- excluded because: Unsupported type (zipvoice, zero-shot voice cloning) and training-data licence unresolved/possibly NC.

#### `ko-mimic3-kss-low-v1` - Korean - Mimic3 KSS low (1 voice)

- status: **excluded**; type `vits`; appSupported `True`; languages ko-KR
- upstream: `vits-mimic3-ko_KO-kss_low.tar.bz2`, 66,838,474 bytes, sha256 `f015d1d15a52ed00d6fe22757c5ef4a74283c53daf829c838fa5c22616ed789c` (checksum.txt); asset updated 2024-01-14T09:43:56Z
- licence: `CC0-1.0 (declared on the model) but trained on KSS (CC-BY-NC-SA-4.0)`; commercialUse **false**, redistribution **false**
- training data: name: KSS (Korean Single Speaker Speech); license: CC-BY-NC-SA-4.0
- evidence: https://github.com/MycroftAI/mimic3-voices/blob/master/voices/ko_KO/kss_low/README.md  
  > 'A single-speaker model for KSS based on the CSS10 dataset ... See LICENSE file for license.' (LICENSE file text is the CC0 legal code)
- evidence: https://huggingface.co/datasets/Bingsu/KSS_Dataset  
  > KSS dataset card front matter: license: cc-by-nc-sa-4.0; 'KSS Dataset is designed for the Korean text-to-speech task ... recorded by a professional female voice actoress'
- excluded because: Non-commercial + share-alike training data (KSS CC-BY-NC-SA-4.0); the CC0 label on the model cannot override the dataset terms. Also low quality.

#### `ja-none-in-tts-models` - Japanese - (no App-runnable model in tts-models)

- status: **excluded**; type `n/a`; appSupported `False`; languages ja
- licence: `n/a`; commercialUse **n/a**, redistribution **n/a**
- evidence: https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models  
  > Asset listing (646 assets) contains no vits-piper-ja_JP / vits-*-ja / jsut / jvs model; rhasspy/piper-voices has no ja or ko locale
- evidence: https://k2-fsa.github.io/sherpa/onnx/tts/all/Japanese/index.html  
  > sherpa-onnx docs Japanese section lists only 'supertonic-3-ja'
- excluded because: No Japanese model in the release that the App runtime (vits/kokoro) can run. Kokoro v1.0 voices.bin has 5 Japanese voices (jf_alpha, jf_gongitsune, jf_nezumi, jf_tebukuro, jm_kumo; sid 37-41) but sherpa-onnx documents only English+Chinese frontends for Kokoro ('we only add English and Chinese support for it'), so Japanese text cannot be phonemised. Paths: (1) Supertonic 3 (see multi-supertonic-3-int8-v1; needs App type support + OpenRAIL-M sign-off); (2) train/fine-tune own Piper/VITS Japanese voice on a dataset with a commercial-friendly licence (dataset licences NOT researched in depth here).

#### `ko-none-compliant-v1` - Korean - (no compliant App-runnable model in tts-models)

- status: **excluded**; type `n/a`; appSupported `False`; languages ko
- licence: `n/a`; commercialUse **n/a**, redistribution **n/a**
- evidence: https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models  
  > Korean assets in the release: vits-mimic3-ko_KO-kss_low (KSS, NC-SA) and Supertonic 2/3 (ko). MMS 'kor' is not in the release and is CC-BY-NC-4.0 anyway (facebook/mms-tts-kor)
- excluded because: The only Korean vits/kokoro-type asset (vits-mimic3-ko_KO-kss_low) is non-commercial/share-alike. Only compliant route: Supertonic 2/3 Korean voices (needs App 'supertonic' type + OpenRAIL-M sign-off).

### 5.2 Excluded Piper English voices

| id | dataset licence | reason |
|---|---|---|
| `en-piper-en-gb-alan-low-v1` | 'See URL' -> mimic3-voices en_UK/apope_low LICENSE: 'Copyright 2022 Mycroft AI All Rights Reserved' | Dataset LICENSE is 'All Rights Reserved'. |
| `en-piper-en-gb-alan-medium-v1` | 'See URL' -> mimic3-voices en_UK/apope_low LICENSE: 'Copyright 2022 Mycroft AI All Rights Reserved' | Dataset LICENSE is 'All Rights Reserved'. |
| `en-piper-en-gb-dii-high-v1` | CC-BY-NC-ND-4.0 (synthetic dataset by TigreGotico) | Non-commercial AND no-derivatives licence (CC-BY-NC-ND-4.0). |
| `en-piper-en-gb-miro-high-v1` | CC-BY-NC-ND-4.0 (synthetic dataset by TigreGotico) | Non-commercial AND no-derivatives licence (CC-BY-NC-ND-4.0). |
| `en-piper-en-gb-semaine-medium-v1` | CC-BY-NC-SA-4.0 | Non-commercial dataset licence (CC-BY-NC-SA-4.0). |
| `en-piper-en-us-amy-low-v1` | 'See URL' (https://github.com/MycroftAI/mimic3-voices - no amy voice directory found there) | Fine-tuned from the Ryan checkpoint (RyanSpeech, CC-BY-NC-SA-4.0): derived weights treated as non-commercial. |
| `en-piper-en-us-amy-medium-v1` | 'See URL' (https://github.com/MycroftAI/mimic3-voices - no amy voice directory found there) | Dataset license not determinable ('See URL' with no resolvable licence text). |
| `en-piper-en-us-danny-low-v1` | 'See URL' (mimic3-voices) | Fine-tuned from the Ryan checkpoint (RyanSpeech, CC-BY-NC-SA-4.0): derived weights treated as non-commercial. |
| `en-piper-en-us-hfc-female-medium-v1` | CC-BY-NC-SA-4.0 | Non-commercial dataset licence (CC-BY-NC-SA-4.0). |
| `en-piper-en-us-hfc-male-medium-v1` | CC-BY-NC-SA-4.0 | Non-commercial dataset licence (CC-BY-NC-SA-4.0). |
| `en-piper-en-us-kathleen-low-v1` | CC0-1.0 | Fine-tuned from the Ryan checkpoint (RyanSpeech, CC-BY-NC-SA-4.0): derived weights treated as non-commercial. |
| `en-piper-en-us-kusal-medium-v1` | 'See URL' (https://github.com/MycroftAI/mimic2) | Dataset license not determinable ('See URL' with no resolvable licence text). |
| `en-piper-en-us-l2arctic-medium-v1` | CC-BY-NC-4.0 | Non-commercial dataset licence (CC-BY-NC-4.0). |
| `en-piper-en-us-miro-high-v1` | CC-BY-NC-ND-4.0 (synthetic dataset by TigreGotico) | Non-commercial AND no-derivatives licence (CC-BY-NC-ND-4.0). |
| `en-piper-en-us-ryan-high-v1` | CC-BY-NC-SA-4.0 | Non-commercial dataset licence (CC-BY-NC-SA-4.0). |
| `en-piper-en-us-ryan-low-v1` | CC-BY-NC-SA-4.0 | Non-commercial dataset licence (CC-BY-NC-SA-4.0). |
| `en-piper-en-us-ryan-medium-v1` | CC-BY-NC-SA-4.0 | Non-commercial dataset licence (CC-BY-NC-SA-4.0). |
| `en-piper-en-gb-sweetbbak-amy-v1` | UNKNOWN | Provenance and licence unknown. |

### 5.3 Excluded Chinese `vits-zh-hf-*` Space re-hosts (13)

| id | upstream sha256 source | evidence | reason |
|---|---|---|---|
| `zh-vits-zh-hf-theresa-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Voices of commercial game characters (Genshin Impact / Honkai Impact 3rd): training audio is third-party copyrighted game content; the Space-level Apache label cannot license it. |
| `zh-vits-zh-hf-eula-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Voices of commercial game characters (Genshin Impact / Honkai Impact 3rd): training audio is third-party copyrighted game content; the Space-level Apache label cannot license it. |
| `zh-vits-zh-hf-keqing-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Provenance undocumented; model name indicates a game-character voice (copyrighted source audio); no licence. |
| `zh-vits-zh-hf-bronya-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Provenance undocumented; model name indicates a game-character voice (copyrighted source audio); no licence. |
| `zh-vits-zh-hf-doom-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Provenance undocumented; model name indicates a game-character voice (copyrighted source audio); no licence. |
| `zh-vits-zh-hf-echo-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Provenance undocumented; model name indicates a game-character voice (copyrighted source audio); no licence. |
| `zh-vits-zh-hf-abyssinvoker-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Provenance undocumented; model name indicates a game-character voice (copyrighted source audio); no licence. |
| `zh-vits-zh-hf-zenyatta-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Provenance undocumented; model name indicates a game-character voice (copyrighted source audio); no licence. |
| `zh-vits-zh-hf-fanchen-c-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Hugging Face Space re-host with no licence and no data provenance. |
| `zh-vits-zh-hf-fanchen-zhihuilaozhe-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Hugging Face Space re-host with no licence and no data provenance. |
| `zh-vits-zh-hf-fanchen-zhihuilaozhe-new-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Hugging Face Space re-host with no licence and no data provenance. |
| `zh-vits-zh-hf-fanchen-unity-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Hugging Face Space re-host with no licence and no data provenance. |
| `zh-vits-zh-hf-fanchen-wnj-v1` | checksum.txt | https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html | Hugging Face Space re-host with no licence and no data provenance. |

## 6. Japanese and Korean (honest status)

- **Japanese**: the release has NO Japanese vits/piper/kokoro model (no `ja_JP` Piper voices; rhasspy/piper-voices has no `ja` or `ko` locale). The sherpa-onnx docs list only `supertonic-3-ja` under Japanese. Kokoro v1.0's `voices.bin` contains 5 Japanese voices (sid 37-41: jf_alpha, jf_gongitsune, jf_nezumi, jf_tebukuro, jm_kumo) but sherpa-onnx only provides English and Chinese Kokoro frontends ('we only add English and Chinese support for it'); extra Kokoro languages added in 1.12.2 (#2303, `--kokoro-lang`) are espeak-based European languages shown in the PR (fr, en) and nothing indicates Japanese. => Japanese from Kokoro is not possible. Possible follow-up paths: (a) Supertonic 3 (ja, 10 voices, OpenRAIL-M, needs App support + sign-off); (b) train a Piper/VITS Japanese voice on a dataset with a commercial-friendly licence - I did NOT research JSUT/JVS/other Japanese dataset terms in depth (only a few Hugging Face metadata tags were seen, not authoritative), so no claim is made.
- **Korean**: only `vits-mimic3-ko_KO-kss_low` (KSS dataset, CC-BY-NC-SA-4.0 per its Hugging Face dataset card; the model's own LICENSE file is CC0 but cannot override dataset terms) -> excluded. MMS-TTS Korean is CC-BY-NC-4.0 and not in the release. Compliant route: Supertonic 2/3 Korean voices (same caveats as Japanese).
- **Chinese dialects**: Cantonese = the existing unlicensed pack (excluded); Min Nan = MMS (NC, excluded). No other dialect model exists in the release.

## 7. Unconfirmed items

- Lessac Blizzard 2013 licence text (blocks 10 Piper voices plus the three lessac tiers).
- Real tarball contents / file names for most packs (nothing downloaded): every `preset.*` marked TODO / 'not verified', and Melo's `model.onnx` vs `model.int8.onnx`, Kokoro `dict/` directory, kitten/pocket speaker files.
- sha256 of the old assets without GitHub digest (melo zh_en, icefall aishell3, cantonese, vits-vctk, coqui-*, mimic3, zh-hf-*): from checksum.txt only.
- Sample rate of `vits-icefall-zh-aishell3` (docs table is ambiguous; 8000 Hz suspected).
- Whether the 1.13.2 C API exposes Supertonic per-call `lang` (Python example uses `gen_config.extra['lang']`).
- Emilia dataset licence (two sibling HF repos report CC-BY-NC-4.0 and CC-BY-4.0; both gated, README unreadable) - irrelevant while ZipVoice is unsupported.
- MeloTTS and Inflect training-data provenance (undisclosed) and `kokoro-onnx` converter licence.
- Southern English female/male Piper voices (no model card).
