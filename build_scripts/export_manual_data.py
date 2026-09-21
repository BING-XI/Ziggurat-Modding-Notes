#!/usr/bin/env python3
r"""
Freeze the workbook's contribution into `Modding Resources/manual_data.json`.

WHY
  `Ziggurat Engine Notes.xlsx` was the manual's source for eight sheets (653 rows) and is a
  FROZEN historical document -- it must not be edited (CLAUDE.md), yet parts of it are wrong.
  The renderer had grown a 26-key `MISC_OVERRIDES` table to patch rows the document gets
  wrong, so the real pipeline was:

      frozen stale workbook -> hand-corrections in Python -> rendered manual

  This extracts the workbook's output ONCE, with the overrides already applied, into a JSON
  the builder reads instead. After that the workbook is not an input at all and the data has
  a maintainable home: edit the JSON, not a spreadsheet you are forbidden to touch.

HOW, and why it is faithful
  It calls the builder's OWN `x_*` parsers and serialises what they return, rather than
  re-reading the sheets. So the extraction cannot disagree with what the manual used to
  render -- the same functions produced both. `x_misc` applies MISC_OVERRIDES internally, so
  the corrections are baked into the export and the override table can then be deleted.

  ⚠ This is a ONE-SHOT. Run it once, verify the page renders identically, then maintain the
  JSON by hand. Re-running it later would overwrite hand edits with the stale workbook again.
  It refuses to overwrite an existing file without --force for exactly that reason.

USAGE
  python build_scripts/export_manual_data.py            # write it
  python build_scripts/export_manual_data.py --force    # overwrite an existing export
"""
import argparse
import json
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
WORKSHOP = os.path.join(GAME, "Modding Resources")
BUILDER = os.path.join(GAME, "build_ziggurat_manual.py")
OUT = os.path.join(WORKSHOP, "manual_data.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if os.path.exists(OUT) and not a.force:
        sys.exit("%s already exists. This is a ONE-SHOT extraction and re-running it would\n"
                 "overwrite hand-maintained data with the stale workbook. Pass --force only\n"
                 "if you mean that." % OUT)

    # import the builder without running main()
    sys.argv = ["build_ziggurat_manual.py"]
    g = runpy.run_path(BUILDER, run_name="zm_export")
    import openpyxl
    xlsx = g["XLSX"]
    if not os.path.isfile(xlsx):
        sys.exit("workbook not found: %s" % xlsx)
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    wb_rich = openpyxl.load_workbook(xlsx, rich_text=True)

    # ⚠ openpyxl's CellRichText is a LIST SUBCLASS, so json.dump serialises it structurally
    # and the value comes back as a list -- which the renderer then prints as a Python repr
    # ("['All three pairs of opposition spheres...', ...]" appeared verbatim in the page).
    # Flatten anything that is not a plain container to the string the renderer used to get.
    try:
        from openpyxl.cell.rich_text import CellRichText
    except ImportError:                                     # older openpyxl
        CellRichText = ()

    def plain(v):
        if CellRichText and isinstance(v, CellRichText):
            return str(v)
        if isinstance(v, dict):
            return {k: plain(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [plain(x) for x in v]
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        return str(v)

    spells, removed, spellnote = g["x_spells"](wb)
    data = {
        "_comment": ("Extracted from Ziggurat Engine Notes.xlsx on 2026-09-11 by "
                     "build_scripts/export_manual_data.py, with MISC_OVERRIDES already "
                     "applied. THIS FILE IS NOW THE SOURCE - edit it, not the workbook, "
                     "which is a frozen historical document."),
        "units": g["x_units"](wb, wb_rich),
        "abil": g["x_abil"](wb),
        "spells": spells,
        "removed": removed,
        "spellnote": spellnote,
        "lvlup": g["x_lvlup"](wb),
        "race": g["x_race"](wb),
        "build": g["x_build"](wb),
        "misc": g["x_misc"](wb),
        "move": g["x_move"](wb),
    }
    data = {k: plain(v) for k, v in data.items()}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=False)
    print("wrote %s (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024.0))
    for k, v in data.items():
        if isinstance(v, list):
            print("   %-10s %d" % (k, len(v)))


if __name__ == "__main__":
    main()
