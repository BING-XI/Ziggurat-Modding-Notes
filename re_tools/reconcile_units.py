# -*- coding: utf-8 -*-
"""
reconcile_units.py — check the Ziggurat design workbook against the data the game actually ships.

    python reconcile_units.py            full report
    python reconcile_units.py --csv      machine-readable rows for pasting back into the sheet

Compares, per unit, the seven values the workbook records (ATK DAM DEF RES HP MV Gold) against
Release/Unitres.pfs, which is what the engine loads. The workbook is a design document and can
drift; the .pfs is the truth.

TAG MAP (verified 2026-08-07 against Man-at-Arms, Pikeman, Cavalier and Musketeer, all four
matching the workbook on every stat — note the order is NOT the workbook's):
    0x0E ATK   0x0F DEF   0x10 DAM   0x11 HP   0x12 MV   0x13 RES   0x14 level   0x1B gold cost
ATK 255 means "no melee attack", which is what the workbook records as an empty cell.

Abilities are deliberately NOT compared: the medal ability sets are mid-rework after the move
from two medal ranks to three, so differences there are expected rather than informative.
"""
import os, sys, importlib.util

TOOLS = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(TOOLS, "..", ".."))
MODDING = os.path.join(GAME, "Modding Resources")

STATS = ["ATK", "DAM", "DEF", "RES", "HP", "MV", "Gold"]
NO_MELEE = 255


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pfs = _load(os.path.join(TOOLS, "pfs.py"), "pfs")
mb = _load(os.path.join(MODDING, "build_ziggurat_manual.py"), "mb")

# name/race normalisation and the .pfs read both live in the manual builder now, so the two
# tools cannot disagree about what matches what.
norm_race, norm_name, squash = mb.norm_race, mb.norm_name, mb.squash


def read_pfs():
    """[{race, name, ATK..Gold, level, id}] — numbers as ints, no-melee as None."""
    out = []
    for d in mb.read_game_units():
        r = {"id": d["id"], "race": d["race"], "name": d["name"], "level": d["level"]}
        for st in STATS:
            r[st] = int(d[st]) if d[st] != "" else None
        out.append(r)
    return out


def read_sheet():
    """[{race, name, ATK..Gold}] — the Ziggurat side of the workbook."""
    import openpyxl
    wb = openpyxl.load_workbook(mb.XLSX, data_only=True)
    wbr = openpyxl.load_workbook(mb.XLSX, rich_text=True)
    out = []
    for g in mb.x_units(wb, wbr):
        for u in g["units"]:
            row = {"race": g["race"], "name": u["zname"] or u["vname"], "row": u["row"] + 1,
                   "cost": g.get("cost", "Gold")}
            for i, s in enumerate(STATS):
                row[s] = u["z"][i].strip()
            out.append(row)
    return out


def match(sheet, data):
    """Pair the two lists.

    MANY-TO-ONE is allowed on purpose: the workbook documents shared units (Battering Ram,
    Catapult, Shredder Bolt) once per race, while the engine stores a single raceless
    record. Consuming each game record on first use made every repeat look like a missing
    unit. Where several workbook rows land on one record with different numbers, that is a
    workbook self-contradiction and is reported separately.
    """
    by_rn, by_n, by_full, by_sq = {}, {}, {}, {}
    for d in data:
        by_rn.setdefault((norm_race(d["race"]), norm_name(d["name"])), []).append(d)
        by_n.setdefault(norm_name(d["name"]), []).append(d)
        # "Spirit"+"Puppet" is one unit the workbook calls "Spirit Puppet"
        by_full.setdefault(norm_name(d["race"] + " " + d["name"]), []).append(d)
        by_sq.setdefault(squash(d["name"]), []).append(d)

    pairs, only_sheet, hit = [], [], set()
    for s in sheet:
        n = norm_name(s["name"])
        cand = by_rn.get((norm_race(s["race"]), n)) or by_full.get(n) or []
        if not cand:
            byn = by_n.get(n, [])
            cand = byn if len(byn) == 1 else []     # ambiguous without a race: do not guess
        if not cand:
            # spacing-only differences ("First Born" / "Firstborn") are safe to join;
            # anything needing a real spelling change is only SUGGESTED, never assumed
            sq = by_sq.get(squash(s["name"]), [])
            cand = sq if len(sq) == 1 else []
        if cand:
            # Some names are not unique even within a race — the engine ships TWO Highman
            # Legionary records. Taking the first invented a disagreement against the one
            # the workbook was never describing, so pick whichever candidate actually fits.
            best = min(cand, key=lambda d: len(compare(s, d)))
            hit.add(best["id"])
            pairs.append((s, best))
        else:
            only_sheet.append(s)
    only_data = [d for d in data if d["id"] not in hit]

    dupes = {}
    for d in data:
        dupes.setdefault((d["race"], d["name"]), []).append(d)
    dupes = {k: v for k, v in dupes.items() if len(v) > 1}
    return pairs, only_sheet, only_data, dupes


def compare(s, d):
    """-> [(stat, sheet_value, data_value, kind)] for everything that disagrees."""
    bad = []
    for st in STATS:
        sv, dv = s[st], d[st]
        # For summon groups the workbook records the spell's mana/upkeep and never a gold
        # cost, so its gold column is legitimately empty — nothing to reconcile against
        # Unitres.pfs, which does carry a gold value for every unit.
        if st == "Gold" and s.get("cost") != "Gold":
            continue
        if st in ("ATK", "DAM") and dv == NO_MELEE:
            dv = None                       # engine's "no melee" == the workbook's blank cell
        if sv == "":
            if dv is not None:
                bad.append((st, "(blank)", dv, "missing-in-sheet"))
            continue
        if dv is None:
            bad.append((st, sv, "(no melee)", "melee-mismatch"))
            continue
        try:
            same = int(sv) == int(dv)
        except ValueError:
            same = sv == str(dv)            # e.g. "26/3"
        if not same:
            bad.append((st, sv, dv, "differs"))
    return bad


def main():
    as_csv = "--csv" in sys.argv
    sheet, data = read_sheet(), read_pfs()
    pairs, only_sheet, only_data, dupes = match(sheet, data)

    diffs = [(s, d, compare(s, d)) for s, d in pairs]
    diffs = [x for x in diffs if x[2]]
    real = [(s, d, [b for b in bs if b[3] == "differs"]) for s, d, bs in diffs]
    real = [x for x in real if x[2]]
    blanks = [(s, d, [b for b in bs if b[3] == "missing-in-sheet"]) for s, d, bs in diffs]
    blanks = [x for x in blanks if x[2]]
    melee = [(s, d, [b for b in bs if b[3] == "melee-mismatch"]) for s, d, bs in diffs]
    melee = [x for x in melee if x[2]]

    if as_csv:
        print("race,unit,sheet_row,stat,workbook,game")
        for s, d, bs in diffs:
            for st, sv, dv, _k in bs:
                print('%s,"%s",%s,%s,%s,%s' % (s["race"], s["name"], s["row"], st, sv, dv))
        return

    print("workbook units %d   |   Unitres.pfs units %d   |   matched %d"
          % (len(sheet), len(data), len(pairs)))
    print("=" * 78)

    print("\n1. STAT DISAGREEMENTS  (%d units)" % len(real))
    print("   The workbook and the shipped data both state a value, and they differ.")
    if not real:
        print("   none")
    for s, d, bs in sorted(real, key=lambda x: (x[0]["race"], x[0]["name"])):
        print("\n   %s / %s   (sheet row %d, unit id %d)"
              % (s["race"], s["name"], s["row"], d["id"]))
        for st, sv, dv, _k in bs:
            print("       %-5s workbook %-8s game %s" % (st, sv, dv))

    print("\n\n2. BLANK IN THE WORKBOOK, PRESENT IN THE GAME  (%d units)" % len(blanks))
    print("   Mostly ranged units: the workbook leaves melee blank, but the engine gives")
    print("   them a real melee attack rather than the 255 'no melee' marker.")
    for s, d, bs in sorted(blanks, key=lambda x: (x[0]["race"], x[0]["name"])):
        print("   %-13s %-22s %s" % (s["race"], s["name"],
              "  ".join("%s=%s" % (st, dv) for st, _sv, dv, _k in bs)))

    if melee:
        print("\n\n3. WORKBOOK GIVES A MELEE ATTACK, GAME SAYS NONE  (%d units)" % len(melee))
        for s, d, bs in sorted(melee, key=lambda x: (x[0]["race"], x[0]["name"])):
            print("   %-13s %-22s %s" % (s["race"], s["name"],
                  "  ".join("%s=%s" % (st, sv) for st, sv, _dv, _k in bs)))

    # several workbook rows describing one game record with different numbers
    seen = {}
    for s, d in pairs:
        sig = tuple(s[st] for st in STATS[:6])
        seen.setdefault(d["id"], []).append((s, sig))
    clash = {i: v for i, v in seen.items()
             if len(v) > 1 and len({sig for _s, sig in v}) > 1}
    if clash:
        print("\n\n3b. ONE GAME UNIT, CONFLICTING WORKBOOK ROWS  (%d)" % len(clash))
        print("    Shared units the workbook lists per race, with different stats each time.")
        for uid, v in clash.items():
            print("    unit id %d — %s" % (uid, v[0][0]["name"]))
            for s, sig in v:
                print("        row %-4d %-13s %s" % (s["row"], s["race"],
                      " ".join("%s=%s" % (a, b or "-") for a, b in zip(STATS[:6], sig))))

    if only_sheet:
        import difflib
        pool = {("%s %s" % (d["race"], d["name"])).strip(): d for d in only_data}
        print("\n\n4. IN THE WORKBOOK, NOT MATCHED IN THE GAME  (%d)" % len(only_sheet))
        print("   Likely spelling drift — suggestions are NOT applied, check each one.")
        for s in only_sheet:
            near = difflib.get_close_matches(s["name"], list(pool), n=1, cutoff=0.6)
            hint = ("  ->  likely '%s' (id %d)" % (near[0], pool[near[0]]["id"])) if near else ""
            print("   %-13s %-22s row %-4d%s" % (s["race"], s["name"], s["row"], hint))

    if dupes:
        print("\n\n4b. SAME-NAME RECORDS IN THE GAME  (%d names)" % len(dupes))
        print("    More than one record shares a race and name. These can be deliberate")
        print("    variants rather than leftovers -- the two Highman Legionaries differ by")
        print("    weapon, the newer one carrying a spear. The workbook can only describe")
        print("    one of each pair, so the other appears under Extra Racial Units.")
        for (race, name), v in sorted(dupes.items()):
            print("    %-13s %s" % (race or "-", name))
            for d in v:
                print("        id %-4d ATK=%-4s DAM=%-4s DEF=%-4s RES=%-3s HP=%-3s MV=%-3s Gold=%s"
                      % (d["id"], d["ATK"], d["DAM"], d["DEF"], d["RES"], d["HP"],
                         d["MV"], d["Gold"]))

    if only_data:
        print("\n\n5. IN THE GAME, ABSENT FROM THE WORKBOOK  (%d)" % len(only_data))
        print("   Units the engine ships that the manual does not document at all.")
        for d in sorted(only_data, key=lambda x: (x["race"], x["name"])):
            print("   %-13s %-22s id %-4d  ATK=%s DAM=%s DEF=%s RES=%s HP=%s MV=%s Gold=%s"
                  % (d["race"] or "-", d["name"], d["id"],
                     d["ATK"], d["DAM"], d["DEF"], d["RES"], d["HP"], d["MV"], d["Gold"]))

    n = sum(len(bs) for _s, _d, bs in real)
    print("\n" + "=" * 78)
    print("%d stat disagreements across %d units; %d units blank in the workbook; "
          "%d unmatched." % (n, len(real), len(blanks), len(only_sheet) + len(only_data)))


if __name__ == "__main__":
    main()
