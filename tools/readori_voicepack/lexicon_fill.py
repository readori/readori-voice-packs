"""Optional lexicon post-processing: fill traditional characters from their simplified forms.

Some sherpa-onnx lexicons (e.g. the community Cantonese VITS pack) list many single characters
with an EMPTY pronunciation, or lack common traditional characters altogether, so sherpa-onnx logs
"OOV" and skips them. ``lexiconFill: opencc-t2s`` copies the phones of the simplified counterpart
(OpenCC ``TSCharacters.txt``, first candidate) onto the traditional character, and drops the
remaining useless empty entries.

Rules (kept deliberately small and deterministic):

* an existing non-empty pronunciation is never overwritten;
* a fill needs a simplified character with a non-empty pronunciation whose phones are ALL tokens
  from ``tokens.txt``;
* every existing valid line is kept unchanged and in order; new lines are appended sorted by code
  point of the character.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .common import VoicePackError

LEXICON_FILL_OPENCC_T2S = "opencc-t2s"
LEXICON_FILL_VALUES = (LEXICON_FILL_OPENCC_T2S,)

OPENCC_DATA_DIR = "registry/lexicon-data/opencc"
OPENCC_TABLE_NAME = "TSCharacters.txt"
OPENCC_LICENSE_NAME = "LICENSE"
OPENCC_PACK_LICENSE_NAME = "LICENSE.opencc"
OPENCC_URL = "https://github.com/BYVoid/OpenCC"


@dataclass(frozen=True)
class FillResult:
    text: str
    filled: int
    dropped: int
    skipped: int  # mapped characters that could not be filled (no usable simplified phones)


def load_opencc_table(path: Path) -> dict[str, str]:
    """Parse ``TSCharacters.txt`` into ``{traditional: first simplified candidate}``.

    Only single-character keys and candidates are kept; identity mappings are dropped.
    """
    table: dict[str, str] = {}
    text = path.read_bytes().decode("utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, rest = line.partition("\t")
        candidates = rest.split()
        if not sep or not candidates or len(key) != 1:
            continue
        simplified = candidates[0]
        if len(simplified) != 1 or simplified == key:
            continue
        table[key] = simplified
    return table


def read_token_set(path: Path) -> set[str]:
    """Tokens of a ``tokens.txt`` (``<token> <id>`` per line; the token itself may be a space)."""
    if path.suffix.lower() != ".txt":
        raise VoicePackError(f"lexiconFill needs a tokens.txt file, got {path.name}")
    tokens: set[str] = set()
    for line in path.read_bytes().decode("utf-8").split("\n"):
        line = line.rstrip("\r")
        if not line:
            continue
        token, sep, _ = line.rpartition(" ")
        if sep:
            tokens.add(token)
    return tokens


def _split_entry(line: str) -> tuple[str, list[str]]:
    fields = line.rstrip("\r").split(" ")
    return fields[0], [f for f in fields[1:] if f]


def fill_lexicon_text(text: str, table: dict[str, str], tokens: set[str]) -> FillResult:
    """Apply the fill to a lexicon file's text; see the module docstring for the rules."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    kept: list[str] = []
    pron: dict[str, list[str]] = {}  # first non-empty pronunciation per word
    present: set[str] = set()
    empty_words: list[str] = []
    for line in lines:
        word, phones = _split_entry(line)
        if not word:
            kept.append(line)  # blank line: leave as is
            continue
        present.add(word)
        if not phones:
            empty_words.append(word)
            continue
        kept.append(line)
        pron.setdefault(word, phones)

    additions: list[str] = []
    skipped = 0
    for trad in sorted(table):
        if trad in pron:
            continue
        phones = pron.get(table[trad])
        if not phones or any(p not in tokens for p in phones):
            skipped += 1
            continue
        additions.append(f"{trad} {' '.join(phones)}")
    out = kept + additions
    filled_words = {line.partition(" ")[0] for line in additions}
    # "dropped" counts the empty entries that stay useless; those replaced by a fill are not counted.
    dropped = sum(1 for word in empty_words if word not in filled_words)
    return FillResult(
        text="\n".join(out) + "\n" if out else "",
        filled=len(additions),
        dropped=dropped,
        skipped=skipped,
    )


def fill_lexicon_file(lexicon: Path, table: dict[str, str], tokens: set[str]) -> FillResult:
    try:
        text = lexicon.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VoicePackError(f"lexiconFill: {lexicon.name} is not valid UTF-8: {exc}") from exc
    result = fill_lexicon_text(text, table, tokens)
    if result.filled or result.dropped or result.text != text:
        lexicon.write_bytes(result.text.encode("utf-8"))
    return result


def opencc_attribution_lines(filled: int, dropped: int) -> list[str]:
    """The "Modifications by Readori" bullet for a pack whose lexicon was filled."""
    return [
        f"  - Lexicon: filled {filled} traditional Chinese characters whose pronunciation was missing or",
        "    empty with the pronunciation of their simplified counterparts, using the OpenCC",
        f"    TSCharacters table ({OPENCC_URL}, Apache-2.0; the licence text is included as",
        f"    {OPENCC_PACK_LICENSE_NAME}); removed {dropped} lexicon entries that had an empty pronunciation.",
    ]


def apply_lexicon_fill(
    pack_dir: Path,
    lexicon_rels: list[str],
    tokens_rel: str,
    *,
    repo_root: Path,
) -> tuple[int, int, str]:
    """Fill every lexicon file in place; return ``(filled, dropped, note)``.

    Writes ``LICENSE.opencc`` into the pack when anything changed.
    """
    data_dir = repo_root / OPENCC_DATA_DIR
    table_path = data_dir / OPENCC_TABLE_NAME
    license_path = data_dir / OPENCC_LICENSE_NAME
    if not table_path.is_file() or not license_path.is_file():
        raise VoicePackError(f"lexiconFill: OpenCC data missing under {OPENCC_DATA_DIR}")
    table = load_opencc_table(table_path)
    tokens = read_token_set(pack_dir / tokens_rel)
    filled = dropped = 0
    for rel in sorted(set(lexicon_rels)):
        result = fill_lexicon_file(pack_dir / rel, table, tokens)
        filled += result.filled
        dropped += result.dropped
    if filled or dropped:
        (pack_dir / OPENCC_PACK_LICENSE_NAME).write_bytes(license_path.read_bytes())
    note = f"lexicon: filled {filled} traditional chars from OpenCC t2s; dropped {dropped} empty entries"
    return filled, dropped, note
