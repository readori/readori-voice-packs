"""Command line interface: ``python -m readori_voicepack <command>``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from . import catalog as catalog_mod
from . import registry as reg
from .audit import run_audit
from .bamanifest import NOTES, build_ba_manifest
from .build import build_pack
from .common import MANIFEST_NAME, VoicePackError, loads_strict, sha256_file, write_json
from .fetch import cache_path, fetch_model, verify_archive
from .index import DEFAULT_INDEX, find_sidecars, update_index
from .pack import pack_directory
from .smoke import run_smoke
from .validate import validate_target

DEFAULT_REGISTRY = Path("registry/models.yaml")
DEFAULT_CACHE = Path(".cache")
DEFAULT_BUILD = Path("build/packs")
DEFAULT_DIST = Path("dist")


def _out(message: str = "", *, err: bool = False) -> None:
    print(message, file=sys.stderr if err else sys.stdout)


# --------------------------------------------------------------------------- commands


def cmd_registry_check(args: argparse.Namespace) -> int:
    registry = reg.load_registry(args.registry)
    results = reg.evaluate_all(
        registry, require_pinned=args.require_pinned, for_publish=args.for_publish
    )
    selected = reg.select_packs(results, args.select) if args.select else None
    human_to_err = bool(args.matrix)

    if args.matrix:
        chosen = (
            selected
            if selected is not None
            else [r for r in results if r.buildable and r.entry["status"] == "approved"]
        )
        print(json.dumps(reg.matrix_for(chosen), separators=(",", ":")))

    if args.json and not args.matrix:
        report = [
            {
                "id": r.entry["id"],
                "status": r.entry["status"],
                "buildable": r.buildable,
                "pinned": reg.is_pinned(r.entry),
                "reasons": r.reasons + r.catalog_problems,
            }
            for r in results
        ]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    _out(f"registry: {args.registry}  ({len(results)} models)", err=human_to_err)
    for r in results:
        verdict = "BUILDABLE" if r.buildable else "BLOCKED"
        pinned = "pinned" if reg.is_pinned(r.entry) else "unpinned"
        _out(f"  {r.entry['id']:<28} {r.entry['status']:<10} {verdict:<10} {pinned}", err=human_to_err)
        for reason in r.reasons + r.catalog_problems:
            _out(f"      - {reason}", err=human_to_err)
    buildable = sum(1 for r in results if r.buildable)
    _out(
        f"summary: {buildable} buildable, {len(results) - buildable} blocked "
        f"(approved={sum(1 for r in results if r.entry['status'] == 'approved')}, "
        f"community={sum(1 for r in results if r.entry['status'] == 'community')}, "
        f"candidate={sum(1 for r in results if r.entry['status'] == 'candidate')}, "
        f"excluded={sum(1 for r in results if r.entry['status'] == 'excluded')})",
        err=human_to_err,
    )
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    registry = reg.load_registry(args.registry)
    entry = reg.require_buildable(registry, args.id)
    result = fetch_model(
        entry, args.cache, allow_unpinned=args.allow_unpinned, force=args.force
    )
    _out(f"archive: {result.path}")
    _out(f"sha256:  {result.sha256}")
    _out(f"bytes:   {result.bytes}")
    _out(f"pinned:  {'yes' if result.pinned else 'no'}")
    return 0


def _resolve_archive(args: argparse.Namespace, entry: dict[str, Any]) -> tuple[Path, str]:
    archive = Path(args.archive) if args.archive else cache_path(
        args.cache, entry["id"], entry["upstream"]["url"]
    )
    if not archive.is_file():
        hint = "" if args.archive else f"; run 'fetch {entry['id']}' first"
        raise VoicePackError(f"upstream archive not found: {archive}{hint}")
    sha = sha256_file(archive)
    verify_archive(entry, sha, archive.stat().st_size, allow_unpinned=args.allow_unpinned)
    return archive, sha


def cmd_build(args: argparse.Namespace) -> int:
    registry = reg.load_registry(args.registry)
    entry = reg.require_buildable(registry, args.id)
    archive, archive_sha = _resolve_archive(args, entry)
    result = build_pack(
        entry,
        archive,
        args.out,
        repo_root=registry.root,
        archive_sha256=archive_sha,
        display_lang=args.display_lang,
    )
    check = validate_target(result.pack_dir, policy=True)
    for warning in check.warnings:
        _out(f"warning: {warning}", err=True)
    if not check.ok:
        raise VoicePackError(
            "built pack failed validation:\n  " + "\n  ".join(str(e) for e in check.errors)
        )
    m = result.manifest
    _out(f"pack dir:      {result.pack_dir}")
    _out(f"pack id:       {result.pack_id} v{result.pack_version}")
    _out(f"type:          {m['type']}")
    _out(f"speakers:      {m['speakerCount']} (default {m['defaultSpeaker']})")
    _out(f"modelBytes:    {m['modelBytes']}")
    _out(f"modelSHA256:   {m['modelSHA256']}")
    _out(f"catalogSHA256: {m.get('voiceCatalogSHA256', 'none')}")
    for note in result.notes:
        _out(f"note: {note}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    result = validate_target(args.target, policy=not args.app_only)
    _out(f"target: {args.target}")
    if result.manifest:
        m = result.manifest
        _out(f"pack:   {m.get('packId', '-')} v{m.get('packVersion', '-')}  type={m.get('type')}")
    for key in ("entries", "uncompressedBytes", "zipBytes", "speakerCount", "defaultSpeaker"):
        if key in result.info:
            _out(f"{key}: {result.info[key]}")
    for warning in result.warnings:
        _out(f"WARN  {warning}")
    for error in result.errors:
        _out(f"FAIL  {error}")
    _out("RESULT: PASS" if result.ok else "RESULT: FAIL")
    return 0 if result.ok else 1


def _maybe_entry(registry_path: Path, pack_id: str | None) -> dict[str, Any] | None:
    if not pack_id or not Path(registry_path).is_file():
        return None
    registry = reg.load_registry(registry_path)
    try:
        return registry.by_id(pack_id)
    except VoicePackError:
        return None


def _pack_id_of(directory: Path) -> str | None:
    path = directory / MANIFEST_NAME
    if not path.is_file():
        return None
    return loads_strict(path.read_text(encoding="utf-8")).get("packId")


def cmd_smoke(args: argparse.Namespace) -> int:
    entry = _maybe_entry(args.registry, _pack_id_of(args.dir))
    sample = (entry or {}).get("preset", {}).get("sampleText")
    result = run_smoke(args.dir, text=args.text, sid=args.sid, sample_text=sample)
    _out(f"sid={result.sid} samples={result.samples} rate={result.sample_rate} "
         f"duration={result.duration:.2f}s")
    _out(f"text: {result.text}")
    for problem in result.problems:
        _out(f"FAIL  {problem}")
    _out("RESULT: PASS" if result.ok else "RESULT: FAIL")
    return 0 if result.ok else 1


def cmd_audit(args: argparse.Namespace) -> int:
    manifest = loads_strict((args.dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    count = int(manifest.get("speakerCount", 1))
    if count < args.min_speakers:
        _out(f"audit skipped: speakerCount {count} < --min-speakers {args.min_speakers}")
        return 0
    result = run_audit(
        args.dir,
        text=args.text,
        speed=args.speed,
        threads=args.threads,
        max_speakers=args.max_speakers,
        keep_wavs=args.keep_wavs,
        drop_unusable=not args.keep_unusable,
        progress=_out,
    )
    for problem in result.problems:
        _out(f"WARN  {problem}")
    _out(f"audited {result.audited} speakers; catalog sha256 {result.catalog_sha256}")
    if result.unusable_sids:
        _out(f"dropped unusable sids from the catalog (speakerCount unchanged): {result.unusable_sids}")
    return 0 if (not result.skipped or not args.keep_unusable) else 1


def cmd_catalog_init(args: argparse.Namespace) -> int:
    count, default = args.speaker_count, args.default_speaker
    catalog_id, profile, language = args.catalog_id, args.profile, args.language
    if args.from_registry:
        entry = reg.load_registry(args.registry).by_id(args.from_registry)
        preset = entry["preset"]
        count = count if count is not None else preset.get("speakerCount")
        default = default if default is not None else preset.get("defaultSpeaker", 0)
        catalog_id = catalog_id or f"readori.{entry['id']}"
        profile = profile or preset.get("profile")
        language = language or preset.get("language") or ",".join(entry["languages"])
    if count is None or not catalog_id:
        raise VoicePackError("--speaker-count and --catalog-id are required (or use --from-registry)")
    names = catalog_mod.read_speaker_names(args.speaker_file) if args.speaker_file else None
    catalog = catalog_mod.init_catalog(
        catalog_id=catalog_id,
        speaker_count=count,
        default_speaker=default or 0,
        profile=profile,
        language=language,
        speaker_names=names,
    )
    write_json(args.output, catalog)
    _out(f"Wrote {args.output} ({len(catalog['speakers'])} speakers)")
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    entry = _maybe_entry(args.registry, _pack_id_of(args.dir))
    result = pack_directory(args.dir, args.out, entry=entry)
    _out(f"zip:     {result.zip_path}")
    _out(f"sidecar: {result.sidecar_path}")
    _out(f"entries: {result.entries}")
    _out(f"bytes:   {result.bytes}")
    _out(f"sha256:  {result.sha256}")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    sidecars = find_sidecars(args.sidecars)
    if not sidecars:
        raise VoicePackError(f"no *.zip.json sidecars found under {args.sidecars}")
    doc = update_index(args.index, sidecars, args.repo)
    _out(f"updated {args.index}: {len(doc['packs'])} packs")
    return 0


def cmd_ba_manifest(args: argparse.Namespace) -> int:
    sidecar = None
    if args.sidecar:
        if not args.sidecar.is_file():
            raise VoicePackError(f"sidecar not found: {args.sidecar}")
        sidecar = loads_strict(args.sidecar.read_text(encoding="utf-8"))
    entry = _maybe_entry(args.registry, _pack_id_of(args.dir))
    manifest = build_ba_manifest(args.dir, entry=entry, sidecar=sidecar)
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"{manifest['assetPackID']}.manifest.json"
    write_json(target, manifest)
    (args.out / f"{manifest['assetPackID']}.manifest.NOTES.txt").write_text(
        NOTES, encoding="utf-8", newline="\n"
    )
    _out(f"wrote {target} (DRAFT - verify with `xcrun ba-package template` on macOS)")
    return 0


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="readori_voicepack", description="Readori offline voice-pack factory"
    )
    parser.add_argument("--version", action="version", version=f"readori-voicepack {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(func=func)
        return p

    def registry_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)

    p = add("registry-check", cmd_registry_check, "validate registry/models.yaml and the license gate")
    registry_arg(p)
    p.add_argument(
        "--select",
        help="comma-separated ids, 'all-approved' or 'all-community'; fails if one is blocked",
    )
    p.add_argument("--matrix", action="store_true", help="print a GitHub Actions matrix as JSON")
    p.add_argument("--json", action="store_true", help="print the gate report as JSON")
    p.add_argument("--require-pinned", action="store_true", help="block entries without sha256/bytes")
    p.add_argument(
        "--for-publish",
        action="store_true",
        help="also require a concrete minAppVersion (a build does not)",
    )

    p = add("fetch", cmd_fetch, "download an upstream archive and verify bytes / sha256")
    p.add_argument("id")
    registry_arg(p)
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--allow-unpinned", action="store_true")
    p.add_argument("--force", action="store_true", help="download again even if cached")

    p = add("build", cmd_build, "build a pack directory and readori-tts-model.json")
    p.add_argument("id")
    registry_arg(p)
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--out", type=Path, default=DEFAULT_BUILD)
    p.add_argument("--archive", type=Path, help="use this local archive instead of the cache")
    p.add_argument("--allow-unpinned", action="store_true")
    p.add_argument("--display-lang", default="en", choices=("en", "zh-Hans", "zh-Hant"))

    p = add("validate", cmd_validate, "validate a pack directory or ZIP with the app importer rules")
    p.add_argument("target", type=Path)
    p.add_argument("--app-only", action="store_true", help="skip Readori curation policy checks")

    p = add("smoke", cmd_smoke, "synthesise one sentence with sherpa-onnx")
    p.add_argument("dir", type=Path)
    registry_arg(p)
    p.add_argument("--sid", type=int)
    p.add_argument("--text")

    p = add("audit", cmd_audit, "per-speaker acoustic audit; writes the catalog back")
    p.add_argument("dir", type=Path)
    p.add_argument("--text")
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--max-speakers", type=int, help="debug: audit only the first N speakers")
    p.add_argument("--min-speakers", type=int, default=1, help="skip packs with fewer speakers")
    p.add_argument("--keep-wavs", type=Path)
    p.add_argument(
        "--keep-unusable",
        action="store_true",
        help="keep speakers whose audio is empty / NaN in the catalog and exit 1 "
        "(default: drop them from the catalog; speakerCount is unchanged)",
    )

    p = add("catalog-init", cmd_catalog_init, "write a facts-only readori-voices.json")
    registry_arg(p)
    p.add_argument("--from-registry", metavar="ID")
    p.add_argument("--speaker-count", type=int)
    p.add_argument("--default-speaker", type=int)
    p.add_argument("--catalog-id")
    p.add_argument("--profile")
    p.add_argument("--language", help="comma-separated BCP-47 tags")
    p.add_argument("--speaker-file", type=Path, help="newline-delimited upstream speaker names")
    p.add_argument("--output", type=Path, default=Path("readori-voices.json"))

    p = add("pack", cmd_pack, "write a deterministic ZIP and its release sidecar")
    p.add_argument("dir", type=Path)
    registry_arg(p)
    p.add_argument("--out", type=Path, default=DEFAULT_DIST)

    p = add("index", cmd_index, "update catalog/v1/index.json from release sidecars")
    p.add_argument("--sidecars", type=Path, default=DEFAULT_DIST)
    p.add_argument("--repo", required=True, help="owner/name of the GitHub repository")
    p.add_argument("--index", type=Path, default=DEFAULT_INDEX)

    p = add("ba-manifest", cmd_ba_manifest, "draft an Apple Background Assets manifest (unverified)")
    p.add_argument("dir", type=Path)
    registry_arg(p)
    p.add_argument("--sidecar", type=Path, help="release sidecar (*.zip.json); a community tier is refused")
    p.add_argument("--out", type=Path, default=Path("build/ba"))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except VoicePackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
