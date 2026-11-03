# Readori voice packs

[简体中文](README.zh-CN.md)

This repository builds, checks and publishes the **offline voice packs** used by the
[Readori](https://readori.com) reading app. A voice pack is a single ZIP file that contains a
[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) text-to-speech model plus the metadata the
app needs to list its voices. Packs run entirely on the device.

The repository only *makes* packs. It never contains models, and it holds no Apple or App Store
Connect credentials.

- `registry/models.yaml` is the single source of truth: which upstream models exist, under which
  license, and how to turn them into a pack.
- `tools/readori_voicepack/` is the Python tooling (`python -m readori_voicepack <command>`).
- `.github/workflows/build-pack.yml` builds and (optionally) publishes packs.
- `catalog/v1/index.json` lists the published packs for the app.

## License policy

Only models that are **licensed for commercial use and for redistribution** are published.

| Rule | Detail |
|---|---|
| Allowed licenses | Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, CC0-1.0, CC-BY-4.0, CC-BY-SA-4.0 |
| Attribution | CC-BY-* models need an explicit attribution text in the registry |
| Training data | the dataset license must be recorded and must also allow commercial use |
| Evidence | every approved entry cites the upstream model card / README with at least one https link (`license.evidence`, a list of `{url, quote}`); the full research is in [docs/LICENSE_EVIDENCE.md](docs/LICENSE_EVIDENCE.md) |
| Training data | `license.dataset.spdx` is an allowed license (also CC-BY-3.0, Unlicense), `mixed` (with `parts`, each allowed or `undisclosed`) or `undisclosed` (with a note; the model license itself must still be explicit) |
| GPL data components | `license.components` lists bundled parts (`name`, `spdx`, `url`, `sourceURL`, `role: data\|code`). GPL-3.0-or-later / GPL-3.0-only is accepted **only** for `role: data` (espeak-ng-data); never as the model license and never as code |
| Unknown / non-commercial / research-only | never built; `unknown` is treated as "no" |
| In every pack | the upstream license text and `readori-attribution.txt` (model, author, license, source URL, changes) |
| Packs with `espeak-ng-data` | also `COPYING.espeak-ng` (GPL-3.0 text) and a GPL statement in `readori-attribution.txt` naming https://github.com/espeak-ng/espeak-ng |

`COPYING.espeak-ng` is taken from the COPYING file inside the upstream `espeak-ng-data` directory
when present, otherwise from `registry/license-texts/GPL-3.0.txt`. If neither holds a real GPL-3.0
text, the build fails.

The gate is enforced in code (`registry-check`, and again inside `fetch` and `build`) and covered
by unit tests. A model enters a build only when `status: approved` and every condition above
holds. The tooling here is Apache-2.0 (see [LICENSE](LICENSE)); **each model keeps its own license**.
Packs that bundle espeak-ng-data contain GPL data files next to the model; the GPL applies to those
files only.

## Registry status

`registry/models.yaml` holds the research results for the sherpa-onnx `tts-models` release.
`status: approved` entries pass the gate, `candidate` entries still need a decision or evidence,
`excluded` entries cannot be published (`excludedReason`). `priority: 1` marks the first build
batch. `upstream.sha256: TODO` means "not pinned yet": build once with `allow_unpinned`, then copy
the printed hash into the registry. `pinnedFrom: github-digest` means the hash was taken from the
GitHub release asset digest. `minAppVersion: TODO` only blocks publishing (`--for-publish`).
Preset values of `TODO` are detected from the real archive at build time.

## Pack format

A pack is a ZIP with the files at the **root** (no wrapper folder, no directory entries):

```
readori-tts-model.json     manifest (decoded by the app as SherpaOnnxModelManifest)
readori-voices.json        voice catalog: names, languages, measured acoustics
readori-attribution.txt    model, author, license, source, modifications
LICENSE (or similar)       upstream license text, referenced by manifest.licenseFile
COPYING.espeak-ng          GPL-3.0 text (only packs that contain espeak-ng-data)
model.onnx, tokens.txt     the model (names depend on the model)
espeak-ng-data/, lexicon*.txt, voices.bin, *.fst, dict/ ...   as the model requires
```

The manifest uses exactly the field names of the app's `SherpaOnnxModelManifest`
(`type`, `displayName`, `model`, `tokens`, `dataDir`, `lexicon`, `lexicons`, `voices`, `language`,
`speakerCount`, `defaultSpeaker`, `ruleFsts`, `ruleFars`, `dictDir`, `licenseFile`, `sourceURL`,
`profile`, `modelBytes`, `modelSHA256`, `voiceCatalog`, `voiceCatalogVersion`,
`voiceCatalogSHA256`, `speakerFile`). Two extra keys are added: `packId` and `packVersion`.
The app decodes the manifest with Swift `Codable`, which ignores unknown keys, so they are
harmless; they are used by `pack` and `index`.

The app supports model types `vits` and `kokoro` only. Other types can be recorded in the
registry with `appSupported: false`; they are never built.

`validate` re-implements the app importer rules: required files resolve inside the pack, paths are
normalised and safe (no `..`, no absolute paths, no `:`), `speakerCount` is 1...512,
`defaultSpeaker` is in range, the catalog decodes and is consistent, `modelBytes` /
`modelSHA256` / `voiceCatalogSHA256` match, the ZIP is at most 1.5 GiB, and it has at most
10,000 entries (catalog at most 8 MiB).

## Commands

```
python -m readori_voicepack registry-check [--select all-approved|id,id] [--matrix] [--json] [--require-pinned] [--for-publish]
python -m readori_voicepack fetch <id> [--allow-unpinned]
python -m readori_voicepack build <id> [--archive FILE] [--allow-unpinned] [--display-lang en|zh-Hans|zh-Hant]
python -m readori_voicepack validate <dir|zip> [--app-only]
python -m readori_voicepack smoke <dir>
python -m readori_voicepack audit <dir> [--max-speakers N] [--min-speakers N] [--keep-unusable]
python -m readori_voicepack catalog-init --speaker-count N --catalog-id ID [--language ..] [--speaker-file ..]
python -m readori_voicepack pack <dir> [--out dist]
python -m readori_voicepack index --repo owner/name [--sidecars dist]
python -m readori_voicepack ba-manifest <dir>
```

| Command | What it does |
|---|---|
| `registry-check` | validates `registry/models.yaml` and prints which entries pass the license gate |
| `fetch` | downloads the upstream archive over HTTPS and checks bytes and sha256; an unpinned entry prints the computed hash and stops unless `--allow-unpinned` |
| `build` | safely unpacks (path traversal, links and size limits checked), generates the manifest, copies license files, writes `readori-attribution.txt`, computes the hashes, then validates |
| `validate` | the app importer rules (see above) plus curation checks |
| `smoke` | synthesises one sentence in the model's language with sherpa-onnx; checks samples > 0, 0.3-30 s, no NaN |
| `audit` | synthesises the same text for every speaker and writes RMS, peak, LUFS, F0 and spectral centroid back to the catalog (measurements only; gender and accent are never guessed). Speakers whose audio is empty or NaN are removed from the catalog by default (the app accepts partial catalogs; `speakerCount` is unchanged); `--keep-unusable` keeps them and exits 1 |
| `catalog-init` | writes a facts-only catalog |
| `pack` | writes a deterministic ZIP (sorted entries, fixed timestamps) and a `.zip.json` sidecar with its sha256 |
| `index` | merges release sidecars into `catalog/v1/index.json` |
| `ba-manifest` | drafts an Apple Background Assets manifest (**unverified**, see below) |

## Add a model

1. Add an entry to `registry/models.yaml` with `status: candidate`. Fill in the upstream URL, the
   license (SPDX id, URL, evidence links with quotes, `commercialUse`, `redistribution`), the dataset
   license and any bundled `components`. Copy the shape of an existing approved entry; the tests in
   `tests/test_registry.py` and `tests/test_gpl_components.py` document the accepted fields.
2. Run `python -m readori_voicepack fetch <id> --allow-unpinned` once and copy the printed sha256 and
   bytes into the entry.
3. Review the license evidence, then change the status to `approved`. If the model cannot be
   published, set `status: excluded` and write `excludedReason`.
4. Open a pull request. CI runs lint, the unit tests and `registry-check` (no downloads).
5. After merge, run the **build-pack** workflow (Actions tab, "Run workflow") with the pack id.
   With `publish` enabled it creates the GitHub Release `pack/<id>/v<packVersion>` and updates
   `catalog/v1/index.json`. Bump `packVersion` when the content of a pack changes.

## Run locally

```
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"                             # tests and lint
pip install -e ".[audio]"                           # smoke / audit (pins sherpa-onnx==1.13.6)
pytest && ruff check .
python -m readori_voicepack registry-check
```

Python 3.11 or newer. Fetched archives are cached in `.cache/`, built packs go to `build/packs/`,
finished ZIPs to `dist/`. None of these are committed.

## Distribution

- **iOS 16-25**: the ZIP is downloaded from GitHub Releases (`catalog/v1/index.json` gives the
  URL, size and sha256) and installed with the same importer as a ZIP the user imports by hand.
- **iOS 26 and later**: Apple-hosted Background Assets asset packs. The maintainer builds the
  `.aar` (the workflow produces drafts on macOS with Xcode 26) and uploads it to App Store Connect
  separately; nothing Apple-related is stored here.

The Background Assets manifest generator is a **draft written without Xcode**. Before using it,
run `xcrun ba-package template` on macOS and compare the key names, the `downloadPolicy` shape,
the `fileSelectors` form and the allowed characters of `assetPackID` with
`readori_voicepack/bamanifest.py`. The workflow dumps that template as an artifact for the
comparison.

## Repository layout

```
registry/models.yaml          upstream model registry (license gate input)
registry/voice-catalogs/      curated voice catalogs referenced by registry entries
registry/license-texts/       license texts used when an upstream archive has none (GPL-3.0 for espeak-ng-data)
docs/LICENSE_EVIDENCE.md     license research behind every registry entry
tools/readori_voicepack/      the CLI package
tests/                        pytest, offline, tiny fake models
catalog/v1/index.json         published packs (updated by the workflow)
.github/workflows/ci.yml      lint + tests + registry check
.github/workflows/build-pack.yml   manual build / publish
```

## Safety notes

- Upstream archives and model cards are untrusted data: every archive member path is checked, links
  and special files are rejected, and entry count and expanded size are bounded.
- Workflows use least privilege (`contents: read`; write only in the publish and index jobs), do not
  run for pull requests, and never print tokens.
