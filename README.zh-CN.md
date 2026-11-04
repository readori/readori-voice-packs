# Readori 语音包

[English](README.md)

本仓库为 [Readori](https://readori.com) 阅读 App 制作、校验并发布**离线语音包**。一个语音包就是一个
ZIP 文件，里面是 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 文本转语音模型，加上 App 列出
音色所需的元数据。语音合成完全在设备上进行。

本仓库只负责「制作」语音包：不存放模型文件，也不保存任何 Apple 或 App Store Connect 凭据。

- `registry/models.yaml`：唯一事实来源，记录有哪些上游模型、各自的许可证，以及如何制成语音包。
- `tools/readori_voicepack/`：Python 工具（`python -m readori_voicepack <命令>`）。
- 本仓库不运行 CI：检查与制作统一在公开 CI 仓库 [readori/test-env-setup](https://github.com/readori/test-env-setup) 执行（`.github/workflows/readori-voice-packs.yml`）。
- `catalog/v1/index.json`：供 App 读取的已发布语音包清单。

## 许可证政策

只发布**允许商用且允许再分发**的模型。

| 规则 | 说明 |
|---|---|
| 允许的许可证 | Apache-2.0、MIT、BSD-2-Clause、BSD-3-Clause、CC0-1.0、CC-BY-4.0、CC-BY-SA-4.0 |
| 署名 | CC-BY 系列必须在登记表里写明署名文字 |
| 训练数据 | 必须记录数据集许可证，且同样允许商用 |
| 证据 | 每条已批准的登记都要引用上游模型卡 / README，至少一个 https 链接（`license.evidence`，`{url, quote}` 列表）；完整调研见 [docs/LICENSE_EVIDENCE.md](docs/LICENSE_EVIDENCE.md) |
| 训练数据 | `license.dataset.spdx` 为允许的许可证（另含 CC-BY-3.0、Unlicense）、`mixed`（带 `parts`，每项为允许许可证或 `undisclosed`）或 `undisclosed`（必须写 note，且模型本身的许可证仍须明确） |
| GPL 数据组件 | `license.components` 记录随包组件（`name`、`spdx`、`url`、`sourceURL`、`role: data\|code`）。GPL-3.0-or-later / GPL-3.0-only **只**接受 `role: data`（espeak-ng-data）；不能作为模型许可证，也不能是代码 |
| 未知 / 非商用 / 仅研究用途 | 不作为官方包制作；`unknown` 按「不允许」处理（未知而非已知禁止的模型可进入[社区分级](#社区分级)） |
| 每个语音包内 | 上游许可证原文，以及 `readori-attribution.txt`（模型名、作者、许可证、来源链接、改动说明） |
| 含 `espeak-ng-data` 的包 | 另含 `COPYING.espeak-ng`（GPL-3.0 全文），且 `readori-attribution.txt` 写明 https://github.com/espeak-ng/espeak-ng 与 GPL 声明 |

`COPYING.espeak-ng` 优先取上游 `espeak-ng-data` 目录内的 COPYING；没有时用 `registry/license-texts/GPL-3.0.txt`。
两者都不是真正的 GPL-3.0 全文时，构建失败。

含 espeak-ng-data 的语音包里，GPL 数据文件与模型并列存放；GPL 只约束这些数据文件。

## 社区分级

部分模型的许可证**未知**（上游没有任何声明，但也没有禁止使用）。它们不属于 `approved`，维护者可将其登记为
`status: community`。Readori 只是**收集**这些模型，**不推荐**；由用户**自行添加使用**。

- 模型及其训练数据的许可证**未经核实**。每个社区包都会明示：其 sidecar 与索引条目带有 `"tier": "community"`、
  `"recommended": false`、`"license": {"verified": false}` 以及三语 `notice`（en / zh-Hans / zh-Hant）；
  `readori-attribution.txt` 与包内 `LICENSE`（`registry/license-texts/COMMUNITY-NOTICE.txt`）开头是同一句声明。
- 社区包**只通过 GitHub Releases 发布**，不会作为 Apple 托管资产包，也不会进入 App Store。`ba-manifest`
  会拒绝社区包，工作流的 Apple 作业也会跳过它们。
- 权利人可在本仓库提交 issue 申请移除，该包随即下架。
- **任何分级都不接受：** 许可证或训练数据已知为非商用 / 仅研究用途的模型、禁止再分发的模型，以及游戏角色声音
  （`gameCharacterVoice: true`）。这由代码（`evaluate_gate`）强制，而不只是登记表的约定。
- 选择方式：`registry-check --select all-community`（或显式 id）。`all-approved` 永远不含社区包。
- App 端预期行为：与官方包分开列出，绝不预选、绝不标为推荐，并且必须由用户明确操作才能添加，同时展示 `notice` 文案。

## 登记表状态

`registry/models.yaml` 收录 sherpa-onnx `tts-models` 发布的调研结果：`approved` 通过闸门，`candidate` 仍需决定或补证据，`community` 为上文所述的“许可证未核实”分级（见 `communityNote`），`excluded` 不能发布（见 `excludedReason`）；`priority: 1` 为首批构建。`upstream.sha256: TODO` 表示尚未锁定：先用 `allow_unpinned` 构建一次，再把打印出的哈希写回；`pinnedFrom: github-digest` 表示哈希来自 GitHub 发布资产摘要。`minAppVersion: TODO` 只阻止发布（`--for-publish`），不阻止构建。`preset` 中值为 `TODO` 的项在构建时从真实压缩包自动识别。

闸门写在代码里（`registry-check`，并在 `fetch`、`build` 中再次检查），并有单元测试覆盖。只有
`status: approved` 且满足以上全部条件的模型才会进入制作流程。工具代码使用 Apache-2.0
（见 [LICENSE](LICENSE)）；**每个模型保留各自的许可证**。

## 语音包格式

语音包是一个 ZIP，文件直接放在**根目录**（没有外层文件夹，也没有目录条目）：

```
readori-tts-model.json     清单（App 以 SherpaOnnxModelManifest 解码）
readori-voices.json        音色目录：名称、语言、实测声学指标
readori-attribution.txt    模型、作者、许可证、来源、改动说明
LICENSE（或同类文件）       上游许可证原文，由 manifest.licenseFile 引用
model.onnx、tokens.txt     模型文件（文件名随模型而定）
espeak-ng-data/、lexicon*.txt、voices.bin、*.fst、dict/ ……   按模型需要
```

清单字段与 App 的 `SherpaOnnxModelManifest` 完全一致（`type`、`displayName`、`model`、`tokens`、
`dataDir`、`lexicon`、`lexicons`、`voices`、`language`、`speakerCount`、`defaultSpeaker`、`ruleFsts`、
`ruleFars`、`dictDir`、`licenseFile`、`sourceURL`、`profile`、`modelBytes`、`modelSHA256`、
`voiceCatalog`、`voiceCatalogVersion`、`voiceCatalogSHA256`、`speakerFile`），另外多两个键：
`packId` 与 `packVersion`。App 用 Swift `Codable` 解码，未知键会被忽略，因此不影响导入；这两个键由
`pack` 和 `index` 使用。

App 目前只支持 `vits` 与 `kokoro` 两类模型。其他类型可以在登记表里标记 `appSupported: false`，
只记录，不制作。

`validate` 复刻了 App 导入器的规则：清单中引用的文件必须存在于包内，路径必须规范且安全（不含
`..`、绝对路径、`:`），`speakerCount` 在 1…512，`defaultSpeaker` 在范围内，音色目录可解码且内部一致，
`modelBytes` / `modelSHA256` / `voiceCatalogSHA256` 与实际文件相符，ZIP 不超过 1.5 GiB、条目不超过
10000 个（音色目录不超过 8 MiB）。

## 命令

```
python -m readori_voicepack registry-check [--select all-approved|all-community|id,id] [--matrix] [--json] [--require-pinned] [--for-publish]
python -m readori_voicepack fetch <id> [--allow-unpinned]
python -m readori_voicepack build <id> [--archive 文件] [--allow-unpinned] [--display-lang en|zh-Hans|zh-Hant]
python -m readori_voicepack validate <目录|zip> [--app-only]
python -m readori_voicepack smoke <目录>
python -m readori_voicepack audit <目录> [--max-speakers N] [--min-speakers N] [--keep-unusable]
python -m readori_voicepack catalog-init --speaker-count N --catalog-id ID [--language ..] [--speaker-file ..]
python -m readori_voicepack pack <目录> [--out dist]
python -m readori_voicepack index --repo owner/name [--sidecars dist]
python -m readori_voicepack ba-manifest <目录> [--registry 文件] [--sidecar 文件]
python -m readori_voicepack build-local <来源> --accept-upstream-license [--out 目录] [--skip-smoke]
```

| 命令 | 作用 |
|---|---|
| `registry-check` | 校验 `registry/models.yaml`，列出哪些条目通过许可证闸门 |
| `fetch` | 通过 HTTPS 下载上游压缩包并校验大小与 sha256；未固定哈希的条目会打印计算结果并停止，除非加 `--allow-unpinned` |
| `build` | 安全解包（检查路径穿越、链接、大小上限），生成清单，复制许可证文件，写 `readori-attribution.txt`，计算各类哈希，最后自动校验 |
| `validate` | App 导入器规则（见上）加上 Readori 的收录检查 |
| `smoke` | 用 sherpa-onnx 合成一句对应语言的样例；检查采样数 > 0、时长 0.3–30 秒、无 NaN |
| `audit` | 对每个音色合成同一段文字，把 RMS、峰值、LUFS、基频、频谱质心写回音色目录（只写测量值，不猜性别与口音）。音频为空或 NaN 的音色默认从目录中移除（App 接受部分目录，`speakerCount` 不变）；`--keep-unusable` 则保留并以退出码 1 结束 |
| `catalog-init` | 生成只含已知事实的音色目录 |
| `pack` | 生成确定性 ZIP（条目排序、固定时间戳）和带 sha256 的 `.zip.json` 附属文件 |
| `index` | 把发布结果合并进 `catalog/v1/index.json` |
| `ba-manifest` | 生成 Apple Background Assets 清单草稿（**尚未验证**，见下）；拒绝社区包和自行构建的包（分级取自登记表条目或 `--sidecar`） |
| `build-local` | 用你自行获取的压缩包构建自用 ZIP，见 [本地自行构建](#本地自行构建) |

## 本地自行构建

如果你从上游来源自行获取了 sherpa-onnx 的 `vits` 或 `kokoro` 模型压缩包，可以在自己的电脑上把它转换成
Readori App 可导入的 ZIP。Readori **不会**审核、构建或分发这类包：下载什么由你决定，你必须自行阅读并接受
上游许可证，并对遵守该许可证负责。

```
python -m readori_voicepack build-local <来源> --accept-upstream-license [--out 目录] [--name ID] [--type vits|kokoro] [--language BCP47] [--speaker-count N] [--default-speaker N] [--display-name 文本] [--sha256 十六进制] [--skip-smoke]

# 来源可以是 https 链接，或本地的 .tar.bz2 / .tar.gz / .zip 文件，例如
python -m readori_voicepack build-local https://example.com/models/vits-example.tar.bz2 --accept-upstream-license
```

- 不加 `--accept-upstream-license` 命令会直接停止。链接通过 HTTPS 下载并有大小上限；会打印压缩包的
  sha256，加 `--sha256` 时还会校验。
- 解包、布局识别、音色目录生成与 `validate` 检查和 `build` 相同（不经过登记表许可证闸门）。如果已安装
  `sherpa-onnx`，会先合成一句测试语音（`--skip-smoke` 可关闭）。
- 上游的 `LICENSE` / `COPYING` 文件原样保留。`readori-attribution.txt` 开头写明该包为用户自行构建、
  未经 Readori 审核（中英文各一行）。
- 输出（默认 `build/local/`）：`<id>-v1.zip` 和 `.zip.json` 附属文件，标注 `"tier": "local"`、
  `"recommended": false`、`"license": {"verified": false, "selfBuilt": true}`。本地包永远不会发布：
  `index` 与 `ba-manifest` 会拒绝它们。
- 如果来源与登记表中的某个模型相同，只会打印其状态和一行许可证概要作为提示，不会阻止构建。

使用方法：在 App 阅读界面打开语音朗读设置，进入「离线语音模型」，点「导入离线模型 ZIP」选择该文件（需账号可使用离线语音功能）。

## 新增模型

1. 在 `registry/models.yaml` 增加一条 `status: candidate` 的登记，填写上游链接、许可证（SPDX、链接、原文
   证据、`commercialUse`、`redistribution`）以及数据集许可证。可参照已批准的条目书写；`tests/test_registry.py` 与 `tests/test_gpl_components.py` 记录了可接受的字段。
2. 运行一次 `python -m readori_voicepack fetch <id> --allow-unpinned`，把打印出的 sha256 和字节数写回登记。
3. 核对许可证证据后把状态改为 `approved`；如果无法发布，改为 `status: excluded` 并写明 `excludedReason`。
4. 提交 Pull Request。维护者在 [readori/test-env-setup](https://github.com/readori/test-env-setup) 运行 **Readori Voice Packs**，`mode=check`、`source_ref` 填 PR 分支：
   代码检查、单元测试和 `registry-check`（不下载模型）。
5. 合并后用同一个工作流选 `mode=build` 并填入语音包 id。勾选 `publish`（只允许 `main`）时会创建
   GitHub Release `pack/<id>/v<packVersion>` 并更新 `catalog/v1/index.json`。语音包内容有变化时请递增
   `packVersion`。

## 本地运行

```
python -m venv .venv && . .venv/bin/activate        # Windows：.venv\Scripts\activate
pip install -e ".[dev]"                             # 测试与代码检查
pip install -e ".[audio]"                           # smoke / audit（固定 sherpa-onnx==1.13.6）
pytest && ruff check .
python -m readori_voicepack registry-check
```

需要 Python 3.11 或更新版本。下载的压缩包缓存在 `.cache/`，制作结果在 `build/packs/`，成品 ZIP 在
`dist/`，这些目录都不会提交。

## 分发方式

- **iOS 16–25**：从 GitHub Releases 下载 ZIP（`catalog/v1/index.json` 提供链接、大小与 sha256），并用与手动导入
  ZIP 相同的导入器安装。
- **iOS 26 及以上**：使用 Apple 托管的 Background Assets 资产包。由维护者构建 `.aar`（工作流会在带 Xcode 26 的
  macOS 上生成草稿），再单独上传到 App Store Connect；本仓库不保存任何 Apple 相关凭据。

Background Assets 清单生成器是**未经 Xcode 验证的草稿**。使用前请在 macOS 上运行
`xcrun ba-package template`，把键名、`downloadPolicy` 结构、`fileSelectors` 写法以及 `assetPackID` 允许的字符
与 `readori_voicepack/bamanifest.py` 对照。工作流会把该模板作为 artifact 输出，便于比对。

## 接入

在 Readori 自定义朗读引擎（需要 Readori Pro）中使用其他声音的指南与引擎模板。以下内容均不由 Readori 内置或托管。

- [integrations/cosyvoice](integrations/cosyvoice/README.zh-CN.md)：自托管方言语音服务（CosyVoice3），支持粤语、闽南话、四川话等。
- [integrations/microsoft](integrations/microsoft/README.zh-CN.md)：通过官方 Azure Speech 服务使用微软语音，使用你自己的密钥。

## 目录结构

```
registry/models.yaml          上游模型登记表（许可证闸门的输入）
registry/voice-catalogs/      登记表引用的、经过整理的音色目录
registry/license-texts/       上游压缩包缺少许可证文本时使用的文本（含 espeak-ng-data 用的 GPL-3.0）
docs/LICENSE_EVIDENCE.md     每条登记背后的许可证调研
docs/NC_REFERENCE.md         非商用参考档：只列出、不构建不托管（由 `nc-reference` 生成）
tools/readori_voicepack/      命令行工具包
tests/                        pytest，离线运行，使用极小的假模型
catalog/v1/index.json         已发布语音包清单（由 readori/test-env-setup 的 CI 更新）
```

## 安全说明

- 上游压缩包和模型卡都视为不可信数据：逐条检查压缩包成员路径，拒绝链接与特殊文件，并限制条目数量与解压后大小。
- 工作流遵循最小权限（默认 `contents: read`，只有发布与清单作业拥有写权限），不会在 Pull Request 上触发，
  也不会打印令牌。
