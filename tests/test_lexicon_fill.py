"""preset.lexiconFill (opencc-t2s): tiny offline fixtures; one test parses the vendored table."""
from __future__ import annotations

from pathlib import Path

import pytest
from readori_voicepack import registry as reg
from readori_voicepack.build import build_pack
from readori_voicepack.common import ATTRIBUTION_NAME, VoicePackError
from readori_voicepack.lexicon_fill import (
    OPENCC_PACK_LICENSE_NAME,
    fill_lexicon_text,
    load_opencc_table,
    read_token_set,
)
from readori_voicepack.validate import validate_directory

from .conftest import make_entry, vits_files, write_tar_bz2

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKENS = {"a", "b", "c", "ː", "˥"}
TABLE = {"遠": "远", "齊": "齐", "來": "来", "傳": "传", "壞": "坏"}
OPENCC_LICENSE = "Apache License\nVersion 2.0, January 2004\n(fixture opencc licence)\n"


def _lines(text: str) -> list[str]:
    return text.splitlines()


def test_empty_and_missing_traditional_chars_are_filled():
    text = "远 a b\n遠 \n齐 c ː\n来 a ˥\n"
    result = fill_lexicon_text(text, TABLE, TOKENS)
    assert _lines(result.text) == ["远 a b", "齐 c ː", "来 a ˥", "來 a ˥", "遠 a b", "齊 c ː"]
    assert result.filled == 3
    assert result.dropped == 0  # the empty 遠 line was replaced by a fill, nothing useless remains


def test_existing_non_empty_entries_are_untouched_and_keep_order():
    text = "z a\n遠 c c\n远 a b\n來 b\n来 a\n"
    result = fill_lexicon_text(text, TABLE, TOKENS)
    out = _lines(result.text)
    assert out[:4] == ["z a", "遠 c c", "远 a b", "來 b"]
    assert "遠 a b" not in out  # never overwrite a non-empty pronunciation
    assert out[4:] == ["来 a"]
    assert result.filled == 0


def test_fill_skipped_when_simplified_has_no_valid_phones():
    # 远 has an unknown phone, 齐 is empty, 来 / 坏 are absent, 传 is fine
    text = "远 a zzz\n齐 \n传 b\n"
    result = fill_lexicon_text(text, TABLE, TOKENS)
    out = _lines(result.text)
    assert out == ["远 a zzz", "传 b", "傳 b"]
    assert result.filled == 1
    assert result.dropped == 1  # the empty 齐 line is useless
    assert result.skipped == 4  # 遠 (bad phone), 齊 (empty), 來 and 壞 (simplified absent)


def test_remaining_empty_entries_are_dropped_and_counted():
    text = "foo \nbar a\n壞 \n\n"
    result = fill_lexicon_text(text, TABLE, TOKENS)
    assert _lines(result.text) == ["bar a", ""]  # blank lines are not entries and stay
    assert result.filled == 0
    assert result.dropped == 2


def test_output_is_deterministic_and_sorted():
    text = "来 a\n传 b\n远 c\n齐 a\n"
    first = fill_lexicon_text(text, TABLE, TOKENS)
    again = fill_lexicon_text(first.text, TABLE, TOKENS)
    assert first.text == fill_lexicon_text(text, dict(reversed(list(TABLE.items()))), TOKENS).text
    added = _lines(first.text)[4:]
    assert [line[0] for line in added] == sorted(line[0] for line in added)
    assert again.text == first.text  # idempotent
    assert again.filled == 0


def test_load_opencc_table_parsing(tmp_path):
    path = tmp_path / "t.txt"
    path.write_text(
        "# comment\n\n遠\t远\n齊\t齐 齊\n㑮\t㑮 𫝈\n多\t多\n兩\t两 俩\nab\tx\n", encoding="utf-8", newline="\n"
    )
    assert load_opencc_table(path) == {"遠": "远", "齊": "齐", "兩": "两"}


def test_read_token_set(tmp_path):
    path = tmp_path / "tokens.txt"
    path.write_bytes("_ 0\n, 1\na e i ˥ 2\n   3\n".encode())
    assert read_token_set(path) == {"_", ",", "a e i ˥", "  "}
    with pytest.raises(VoicePackError):
        read_token_set(tmp_path / "tokens.json")


def test_vendored_opencc_table_parses():
    root = REPO_ROOT / "registry" / "lexicon-data" / "opencc"
    table = load_opencc_table(root / "TSCharacters.txt")
    assert table["來"] == "来"
    assert table["遠"] == "远"
    assert table["齊"] == "齐"
    assert len(table) > 3000
    assert "Apache License" in (root / "LICENSE").read_text(encoding="utf-8")
    provenance = (root / "PROVENANCE.txt").read_text(encoding="utf-8")
    assert "Apache-2.0" in provenance
    assert "BYVoid/OpenCC" in provenance


# --------------------------------------------------------------------------- registry


def test_registry_rejects_unknown_lexicon_fill_values():
    for bad in ("bogus", "OPENCC-T2S", None, True, ["opencc-t2s"]):
        entry = make_entry(preset={"lexiconFill": bad})
        errors = reg.validate_registry_doc({"schemaVersion": 1, "models": [entry]})
        assert any("lexiconFill" in e for e in errors), (bad, errors)


def test_registry_accepts_opencc_t2s():
    entry = make_entry(preset={"lexiconFill": "opencc-t2s"})
    assert reg.validate_registry_doc({"schemaVersion": 1, "models": [entry]}) == []


def test_shipped_registry_sets_lexicon_fill_only_on_cantonese():
    registry = reg.load_registry(REPO_ROOT / "registry" / "models.yaml")
    with_fill = {m["id"] for m in registry.models if "lexiconFill" in m["preset"]}
    assert with_fill == {"yue-cantonese-v1"}


# --------------------------------------------------------------------------- build


def _repo_with_opencc(root: Path) -> None:
    data = root / "registry" / "lexicon-data" / "opencc"
    data.mkdir(parents=True, exist_ok=True)
    (data / "TSCharacters.txt").write_text("# fixture\n遠\t远\n來\t来\n", encoding="utf-8", newline="\n")
    (data / "LICENSE").write_text(OPENCC_LICENSE, encoding="utf-8", newline="\n")


def _build(tmp_path: Path, preset_extra: dict, lexicon: bytes, out: str = "out"):
    files = vits_files()
    files["tokens.txt"] = "a 0\nb 1\n".encode()
    files["lexicon.txt"] = lexicon
    archive = write_tar_bz2(tmp_path / f"{out}.tar.bz2", files)
    entry = make_entry(preset=preset_extra)
    return build_pack(entry, archive, tmp_path / out, repo_root=tmp_path)


def test_build_fills_lexicon_and_documents_it(tmp_path):
    _repo_with_opencc(tmp_path)
    result = _build(tmp_path, {"lexiconFill": "opencc-t2s"}, "远 a b\n遠 \n单 \n".encode())
    lexicon = (result.pack_dir / "lexicon.txt").read_bytes().decode()
    assert lexicon == "远 a b\n遠 a b\n"
    assert "lexicon: filled 1 traditional chars from OpenCC t2s; dropped 1 empty entries" in result.notes
    assert (result.pack_dir / OPENCC_PACK_LICENSE_NAME).read_text(encoding="utf-8") == OPENCC_LICENSE
    attribution = (result.pack_dir / ATTRIBUTION_NAME).read_text(encoding="utf-8")
    modifications = attribution.split("Modifications by Readori", 1)[1]
    assert "OpenCC" in modifications
    assert "Apache-2.0" in modifications
    assert OPENCC_PACK_LICENSE_NAME in modifications
    assert validate_directory(result.pack_dir).ok


def test_build_without_key_changes_nothing(tmp_path):
    _repo_with_opencc(tmp_path)
    original = "远 a b\n遠 \n"
    result = _build(tmp_path, {}, original.encode())
    assert (result.pack_dir / "lexicon.txt").read_bytes().decode() == original
    assert not (result.pack_dir / OPENCC_PACK_LICENSE_NAME).exists()
    attribution = (result.pack_dir / ATTRIBUTION_NAME).read_text(encoding="utf-8")
    assert "OpenCC" not in attribution
    assert not any("OpenCC" in n for n in result.notes)


def test_build_is_deterministic_with_fill(tmp_path):
    _repo_with_opencc(tmp_path)
    lexicon = "远 a b\n来 b\n遠 \n".encode()
    first = _build(tmp_path, {"lexiconFill": "opencc-t2s"}, lexicon, out="one")
    second = _build(tmp_path, {"lexiconFill": "opencc-t2s"}, lexicon, out="two")
    for name in ("lexicon.txt", OPENCC_PACK_LICENSE_NAME, ATTRIBUTION_NAME):
        assert (first.pack_dir / name).read_bytes() == (second.pack_dir / name).read_bytes()


def test_build_fill_requires_vendored_data(tmp_path):
    with pytest.raises(VoicePackError, match="OpenCC data missing"):
        _build(tmp_path, {"lexiconFill": "opencc-t2s"}, "远 a b\n".encode())
