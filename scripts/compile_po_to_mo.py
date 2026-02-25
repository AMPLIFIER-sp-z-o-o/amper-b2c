"""Pure-Python .po -> .mo compiler.

This repo targets Windows dev environments where GNU gettext tools (msgfmt)
may be missing. Django requires compiled .mo files at runtime, so this script
provides an alternative to `manage.py compilemessages`.

Usage:
  uv run python scripts/compile_po_to_mo.py

It compiles all `locale/*/LC_MESSAGES/*.po` files into matching `.mo` files.
"""

from __future__ import annotations

import ast
import glob
import os
import struct
from dataclasses import dataclass, field


@dataclass
class PoEntry:
    msgctxt: str | None = None
    msgid: str = ""
    msgid_plural: str | None = None
    msgstr: dict[int, str] = field(default_factory=dict)

    def key(self) -> str:
        if self.msgctxt:
            return f"{self.msgctxt}\x04{self.msgid}"
        return self.msgid

    def original(self) -> str:
        if self.msgid_plural is not None:
            return f"{self.msgid}\0{self.msgid_plural}"
        return self.msgid

    def translation(self) -> str:
        if self.msgid_plural is None:
            return self.msgstr.get(0, "")
        if not self.msgstr:
            return ""
        max_idx = max(self.msgstr.keys())
        return "\0".join(self.msgstr.get(i, "") for i in range(max_idx + 1))


def _unquote_po_string(s: str) -> str:
    s = s.strip()
    if not s.startswith('"'):
        return ""
    try:
        # PO files are UTF-8 text. We only need to interpret C-style escapes
        # (\n, \", \\). Using unicode_escape on UTF-8 bytes corrupts non-ASCII
        # characters (e.g. Polish diacritics) and can produce invalid .mo files.
        return ast.literal_eval(s)
    except Exception:
        return s[1:-1]


def parse_po(path: str) -> list[PoEntry]:
    entries: list[PoEntry] = []
    current = PoEntry()
    active_field: tuple[str, int | None] | None = None

    def commit():
        nonlocal current, active_field
        if current.msgid != "" or current.msgstr or current.msgctxt is not None:
            entries.append(current)
        current = PoEntry()
        active_field = None

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")

            if not line.strip():
                commit()
                continue

            if line.startswith("#"):
                continue

            if line.startswith("msgctxt"):
                # Some .po files omit the blank line separator between entries
                # (notably between the header and the first real msgid). If a
                # new entry starts, commit the previous one first.
                if active_field is not None and (current.msgid != "" or current.msgstr or current.msgctxt is not None):
                    commit()
                current.msgctxt = _unquote_po_string(line[len("msgctxt") :].strip())
                active_field = ("msgctxt", None)
                continue

            if line.startswith("msgid_plural"):
                current.msgid_plural = _unquote_po_string(line[len("msgid_plural") :].strip())
                active_field = ("msgid_plural", None)
                continue

            if line.startswith("msgid"):
                # New entry without a blank line separator.
                if active_field is not None and (current.msgid != "" or current.msgstr or current.msgctxt is not None):
                    commit()
                current.msgid = _unquote_po_string(line[len("msgid") :].strip())
                active_field = ("msgid", None)
                continue

            if line.startswith("msgstr["):
                idx_part = line.split("]", 1)[0]
                idx = int(idx_part[len("msgstr[") :])
                rest = line.split("]", 1)[1].strip()
                current.msgstr[idx] = _unquote_po_string(rest)
                active_field = ("msgstr", idx)
                continue

            if line.startswith("msgstr"):
                current.msgstr[0] = _unquote_po_string(line[len("msgstr") :].strip())
                active_field = ("msgstr", 0)
                continue

            # Continuation line
            if line.lstrip().startswith('"') and active_field is not None:
                part = _unquote_po_string(line.strip())
                field_name, idx = active_field
                if field_name == "msgctxt":
                    current.msgctxt = (current.msgctxt or "") + part
                elif field_name == "msgid":
                    current.msgid = current.msgid + part
                elif field_name == "msgid_plural":
                    current.msgid_plural = (current.msgid_plural or "") + part
                elif field_name == "msgstr" and idx is not None:
                    current.msgstr[idx] = current.msgstr.get(idx, "") + part
                continue

    commit()
    return entries


def write_mo(entries: list[PoEntry], mo_path: str) -> None:
    # Build catalog: original -> translation
    catalog: dict[str, str] = {}
    for e in entries:
        if e.msgid == "" and not e.msgctxt:
            # Header entry: keep as-is
            catalog[""] = e.translation()
            continue

        trans = e.translation()
        # IMPORTANT: skip empty translations.
        # If we store msgid -> "" in the .mo, gettext treats it as an explicit
        # translation to empty string (not as "missing"), which can blank out
        # UI text and even trip edge cases with Django lazy strings.
        if trans.replace("\0", "") == "":
            continue

        orig = e.original()
        if e.msgctxt:
            orig = f"{e.msgctxt}\x04{orig}"
        catalog[orig] = trans

    # Ensure header exists
    catalog.setdefault("", "")

    keys = sorted(catalog.keys())

    ids = [k.encode("utf-8") for k in keys]
    strs = [catalog[k].encode("utf-8") for k in keys]

    # The .mo format uses a table of (length, offset) for ids and strs.
    # Strings are NUL-terminated.
    keystart = 7 * 4
    n = len(keys)
    orig_tab_offset = keystart
    trans_tab_offset = orig_tab_offset + n * 8
    string_offset = trans_tab_offset + n * 8

    offsets_orig: list[tuple[int, int]] = []
    offsets_trans: list[tuple[int, int]] = []

    offset = string_offset
    for s in ids:
        offsets_orig.append((len(s), offset))
        offset += len(s) + 1
    for s in strs:
        offsets_trans.append((len(s), offset))
        offset += len(s) + 1

    output = []
    output.append(struct.pack("Iiiiiii", 0x950412DE, 0, n, orig_tab_offset, trans_tab_offset, 0, 0))

    for length, off in offsets_orig:
        output.append(struct.pack("II", length, off))
    for length, off in offsets_trans:
        output.append(struct.pack("II", length, off))

    for s in ids:
        output.append(s + b"\x00")
    for s in strs:
        output.append(s + b"\x00")

    os.makedirs(os.path.dirname(mo_path), exist_ok=True)
    with open(mo_path, "wb") as f:
        f.write(b"".join(output))


def main() -> int:
    po_files = glob.glob(os.path.join("locale", "*", "LC_MESSAGES", "*.po"))
    if not po_files:
        print("No .po files found under locale/*/LC_MESSAGES")
        return 0

    compiled = 0
    for po_path in po_files:
        mo_path = po_path[:-3] + ".mo"
        entries = parse_po(po_path)
        write_mo(entries, mo_path)
        compiled += 1

    print(f"Compiled {compiled} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
