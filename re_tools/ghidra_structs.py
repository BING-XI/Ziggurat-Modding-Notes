"""Derive VMT layouts for AoWEPACK.dpl classes from the binary itself.

The DPL is a Delphi package, so nearly every method is EXPORTED with its unit.class.method
name -- the same names Ghidra shows.  That means a VMT layout can be DERIVED, not
transcribed: locate the VMT via RTTI, read each slot, look the target up in the export
table, and the slot names itself.  Doc claims about VMT slots then become checkable in
bulk (the 2026-08-03 conflict pass found the docs' VMT tables were the least reliable
offset source in the project, so they are no longer treated as one).

Per class this reports, for every slot:
  * the derived method name (from the export table of the live DLL -- exports are not
    touched by any patch),
  * whether the slot is inherited from / overrides the parent (parent chain followed via
    vmtParent while it stays inside this module),
  * whether the LIVE DLL has repointed the slot (pristine vs live dword) -- i.e. a mod
    VMT hook -- and where it now points.

Usage:
    python ghidra_structs.py                # summary + doc-claim verification
    python ghidra_structs.py --full         # dump every slot table to stdout
    python ghidra_structs.py --md           # (re)write ../Ghidra_VMT_Layouts.md
    python ghidra_structs.py --json FILE    # machine-readable dump

Pristine reference: Modding Resources/AoWEPACK_original_backup.dpl (the same bytes the
Ghidra project holds).  Live: the installed AoWEPACK.dpl.
"""
import os
import re
import sys
import json
import struct
import argparse

TOOLS = os.path.dirname(os.path.abspath(__file__))
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(TOOLS, "..", ".."))
sys.path.insert(0, TOOLS)
from aowsyms import get_symbols  # noqa: E402

PRISTINE = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")
LIVE = os.path.join(GAME, "AoWEPACK.dpl")

# Classes worth a derived layout -- the inventory's most-referenced ones.  Missing names
# are reported, not fatal: some doc "classes" live in other modules (TMapField is
# HSEngine's) or do not exist under that name.
CLASSES = [
    "TAbilityOwner", "TAbstractUnit", "TAdjustableUnit", "TUnit", "THero",
    "TUnitResource", "THeroResource",
    "TAbility", "TMultiLevelAbility", "TDurationAbility", "TUnitEnchantmentAbility",
    "TRangedAttackAbility", "TTouchAbility", "TLeadershipAbility",
    "TSpell", "TCombatSpell",
    "TCombatObject", "TCombatUnit", "TCombatWall", "TCombatPredictor",
    "TStructure", "TCity", "TCityHS", "TExplorationSite", "TArena", "TDungeon",
    "TReflectingPool", "TTower",
    "TArmy", "TArmyHS", "TPlayer", "TPlayerMagicControl",
    "TAoWHexagon", "TAoWWaterHexagon", "TAoWMapField",
    "TItem", "THeroItems", "THeroInventory",
]

# ---- doc claims to bulk-verify: {class: {slot_offset: claimed_method}} -----------------
# Sources: the 2026-08-03 offset inventory (Investigation_Items.md, Investigation_Combat.md,
# Hex_Transition_System.md, Arena_Rework_Feasibility.md, Inioch_Structure_Raze_Framework.md,
# Slayer_Abilities_Design.md, unit-spellcasting docs, re_tools/abquery.py, dump_exe.py).
# A claim passes when its name matches the derived export name (loose, last-component).
CLAIMS = {
    "TAbstractUnit": {
        0x4C: "GetAbSet", 0x50: "SetAbilityEnabled", 0x54: "GetAbCount",
        0x68: "GetAbAttack", 0x6C: "GetAbDefense", 0x70: "GetAbResistance",
        0x74: "GetAbDamage", 0x84: "GetAbLevel", 0x88: "GetAbEnabled",
        0x8C: "GetAbilitySelectionTypes", 0x90: "Changed", 0x94: "ExpandAbility",
        0x98: "RemoveAbility",
        0xC0: "GetAttack", 0xC4: "GetDefense", 0xC8: "GetDamage", 0xCC: "GetResistance",
        0xD0: "GetHits", 0xD4: "GetMoves", 0xD8: "GetMovePoints", 0xDC: "SetMovePoints",
        0xE0: "GetHitPoints", 0xE4: "SetHitPoints", 0xE8: "GetMoveTypes",
        0xEC: "GetImmunityTypes", 0xF0: "GetProtectionTypes", 0xF8: "GetName",
        0xFC: "GetAlignment", 0x104: "GetTransportCapacity", 0x108: "GetTransporter",
        0x11C: "CreateEnchantment", 0x128: "GetCastingPointsMax",
        0x12C: "GetCastingPoints", 0x130: "SetCastingPoints", 0x134: "GetPowerGeneration",
        0x138: "NewDay", 0x13C: "NewTurn",
        0x144: "GetAbilityLevel", 0x148: "GetAbilityEnabled", 0x14C: "GetAbilitySet",
        0x1AC: "KillUnit",
    },
    "TUnit": {0x114: "GetUnitType", 0x174: "GetObtainValue"},
    "THero": {0x158: "GetAbilityCount"},
    "TCombatObject": {
        0x60: "GetEnabled", 0x6C: "GetAttack", 0x70: "GetDefense", 0x74: "GetResistance",
        0x7C: "GetImmunityTypes", 0x80: "GetProtectionTypes", 0x88: "GetHitPoints",
        0x90: "GetAlignment", 0x108: "DoDamage",
    },
    "TCombatUnit": {0x8C: "SetHitPoints", 0xA8: "GetAbilityEnabled", 0xB8: "GetAbilityOwner"},
    "TSpell": {0x68: "CanActivate", 0x6C: "Activate", 0x70: "CanActivateCombat",
               0x74: "ActivateCombat", 0x78: "CreateCA"},
    "TAbility": {0x58: "GetName", 0x70: "GetLevel", 0x74: "GetEnabled",
                 0x94: "GetInherentLevel", 0xC4: "CanExpand", 0xC8: "ExpandCost",
                 0xD0: "Expand", 0xAC: "NewTurn"},
    "TRangedAttackAbility": {0x110: "GetDamageRA", 0x114: "GetAttackRA",
                             0x11C: "GetDamageTypesRA"},
    "TStructure": {
        0x18: "ReadWrite", 0x74: "GetX", 0x78: "GetY", 0x7C: "GetLevel",
        0x12C: "GetTerrainTypeImage", 0x144: "GetDescription",
        0x14C: "SetRazed", 0x150: "GetRazed", 0x154: "GetRazeable", 0x158: "RazeEx",
        0x174: "NewDay", 0x178: "NewTurn", 0x19C: "BuildingDone",
        0x1A0: "ExecuteRebuild", 0x1B0: "ExecuteRaze", 0x1B8: "ValidateMap",
        0x1C0: "ExecuteAI", 0x1C4: "UpdateAITarget", 0x1E8: "Raze", 0x1EC: "CanRaze",
        0x1F0: "SetPlayer", 0x1FC: "ExecuteSearch", 0x200: "Search",
        0x204: "UpdateUnfog", 0x208: "UpdateExploration", 0x220: "UpdatePlayer",
    },
    "TAoWHexagon": {0x4C: "GetTerrain", 0xA4: "NeighbourTerrainChanged",
                    0x11C: "UpdateTransitions", 0x120: "UpdateTransition"},
    "TAoWWaterHexagon": {0x124: "ShowDynamic"},
}


# ---------------------------------------------------------------- file plumbing

def load(path):
    data = open(path, "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    optsz = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    secs = []
    for i in range(nsec):
        e = pe + 24 + optsz + i * 40
        nm = data[e:e + 8].rstrip(b"\0").decode("latin1")
        vsz, va, rsz, ptr = struct.unpack_from("<IIII", data, e + 8)
        secs.append((nm, base + va, max(vsz, rsz), ptr, rsz))
    return data, base, secs


def mk_va2off(secs):
    def f(va):
        for nm, sva, vsz, ptr, rsz in secs:
            if sva <= va < sva + vsz:
                off = ptr + (va - sva)
                return off if off < ptr + rsz else None
        return None
    return f


def mk_off2va(secs):
    def f(off):
        for nm, sva, vsz, ptr, rsz in secs:
            if ptr <= off < ptr + rsz:
                return sva + (off - ptr)
        return None
    return f


def code_range(secs):
    for nm, sva, vsz, ptr, rsz in secs:
        if nm == "CODE":
            return sva, sva + vsz
    raise SystemExit("no CODE section?")


# ---------------------------------------------------------------- RTTI walking

def find_vmts(data, va2off, off2list, name):
    """All (vmt, name_va) whose class-name ShortString is exactly `name`."""
    pat = bytes([len(name)]) + name.encode("latin1")
    out, start = [], 0
    while True:
        i = data.find(pat, start)
        if i < 0:
            break
        start = i + 1
        nxt = data[i + len(pat):i + len(pat) + 1]
        if nxt and (nxt.isalnum() or nxt == b"_"):
            continue                      # TUnit inside TUnitList etc.
        sva = off2list(i)
        if sva is None:
            continue
        needle = struct.pack("<I", sva)
        s2 = 0
        while True:
            j = data.find(needle, s2)
            if j < 0:
                break
            s2 = j + 1
            pva = off2list(j)
            if pva is None:
                continue
            vmt = pva + 0x20              # [VMT-0x20] -> class name
            # validity: vmtInstanceSize at VMT-0x1C must be a plausible object size.
            # (vmtSelfPtr at -0x40 is NOT reliable in this Delphi build -- do not re-add it.)
            o = va2off(vmt - 0x1C)
            if o is None:
                continue
            isz = struct.unpack_from("<I", data, o)[0]
            if 0 < isz < 0x10000:
                out.append(vmt)
    return out


def read_name(data, va2off, vmt):
    o = va2off(vmt - 0x20)
    if o is None:
        return "?"
    sva = struct.unpack_from("<I", data, o)[0]
    so = va2off(sva)
    if so is None:
        return "?"
    n = data[so]
    return data[so + 1:so + 1 + n].decode("latin1")


def walk_slots(data, va2off, vmt, code_lo, code_hi, cap=0x300):
    """Slot targets from +0 until the dword stops being a CODE address."""
    slots = []
    for off in range(0, cap, 4):
        o = va2off(vmt + off)
        if o is None:
            break
        v = struct.unpack_from("<I", data, o)[0]
        if not (code_lo <= v < code_hi):
            break
        slots.append(v)
    return slots


def parent_of(data, va2off, vmt):
    """Parent VMT, or None when the parent lives in another module."""
    o = va2off(vmt - 0x18)
    if o is None:
        return None
    ref = struct.unpack_from("<I", data, o)[0]
    if not ref:
        return None
    ro = va2off(ref)
    if ro is None:
        return None                       # import thunk -> external parent
    par = struct.unpack_from("<I", data, ro)[0]
    po = va2off(par - 0x40)
    if po is not None and struct.unpack_from("<I", data, po)[0] == par:
        return par
    return None


# ---------------------------------------------------------------- names

HASH_RE = re.compile(r"@[0-9A-Fa-f]{8}$")


def method_name(exports, va):
    n = exports.get(va)
    if not n:
        return None
    n = HASH_RE.sub("", n)
    return n


def last_part(name):
    return name.rsplit(".", 1)[-1].lstrip("@").lower() if name else ""


# ---------------------------------------------------------------- main

def derive():
    pris, base, secs = load(PRISTINE)
    live, base2, secs2 = load(LIVE)
    assert base == base2
    va2off = mk_va2off(secs)
    off2va = mk_off2va(secs)
    code_lo, code_hi = code_range(secs)
    _, _, exports, _ = get_symbols("AoWEPACK.dpl")

    out, missing = {}, []
    export_classes = {p.split(".")[-2] for p in map(lambda n: HASH_RE.sub("", n), exports.values())
                      if p.count(".") >= 2}
    for cls in CLASSES:
        vmts = find_vmts(pris, va2off, off2va, cls)
        if not vmts:
            hint = "exports mention it -- VMT search failed" if cls in export_classes \
                else "no exports either -- not in this module under that name"
            missing.append((cls, hint))
            continue
        vmt = vmts[0]
        slots = walk_slots(pris, va2off, vmt, code_lo, code_hi)
        par = parent_of(pris, va2off, vmt)
        pslots = walk_slots(pris, va2off, par, code_lo, code_hi) if par else []
        isz_o = va2off(vmt - 0x1C)
        rows = []
        for i, tgt in enumerate(slots):
            off = i * 4
            lo = va2off(vmt + off)
            lv = struct.unpack_from("<I", live, lo)[0]
            rows.append({
                "off": off,
                "target": tgt,
                "name": method_name(exports, tgt),
                "rel": ("new" if i >= len(pslots) else
                        "override" if pslots[i] != tgt else "inherit"),
                "live": None if lv == tgt else lv,
                "live_name": None if lv == tgt else method_name(exports, lv),
            })
        out[cls] = {
            "vmt": vmt,
            "instsize": struct.unpack_from("<I", pris, isz_o)[0],
            "parent": read_name(pris, va2off, par) if par else "(external)",
            "nslots": len(slots),
            "slots": rows,
            "dupes": len(vmts),
        }
    return out, missing


def verify(derived):
    results = []
    for cls, claims in CLAIMS.items():
        d = derived.get(cls)
        if not d:
            for off, want in claims.items():
                results.append((cls, off, want, None, "CLASS-MISSING"))
            continue
        bymap = {r["off"]: r for r in d["slots"]}
        for off, want in sorted(claims.items()):
            r = bymap.get(off)
            if r is None:
                results.append((cls, off, want, None, "PAST-VMT-END"))
                continue
            got = r["name"]
            if got is None:
                results.append((cls, off, want, got, "NO-EXPORT"))
            elif last_part(want) == last_part(got) or last_part(want) in last_part(got) \
                    or last_part(got) in last_part(want):
                results.append((cls, off, want, got, "PASS"))
            else:
                results.append((cls, off, want, got, "FAIL"))
    return results


def emit_md(derived, missing, results, path):
    with open(path, "w", encoding="utf8", newline="\n") as f:
        w = f.write
        w("# AoWEPACK.dpl VMT layouts -- GENERATED, do not hand-edit\n\n")
        w("Derived from the binary's own RTTI + export table by "
          "`re_tools/ghidra_structs.py`; regenerate with `python ghidra_structs.py --md`.\n"
          "See `Ghidra_Annotations.md` for what this is and why doc VMT tables are no "
          "longer a source.\n\n")
        w("`rel` = new / override / inherit vs the parent VMT. `LIVE->` marks slots the "
          "installed DLL repoints (mod VMT hooks).\n\n")
        for cls in sorted(derived):
            d = derived[cls]
            w(f"## {cls}  (VMT `{d['vmt']:08X}`, instsize `0x{d['instsize']:X}`, "
              f"parent {d['parent']}, {d['nslots']} slots)\n\n")
            w("| slot | method | rel |\n|---|---|---|\n")
            for r in d["slots"]:
                nm = r["name"] or "*(not exported)*"
                extra = ""
                if r["live"] is not None:
                    tgt = r["live_name"] or f"`{r['live']:08X}`"
                    extra = f" **LIVE-> {tgt}**"
                w(f"| `+0x{r['off']:03X}` | {nm}{extra} | {r['rel']} |\n")
            w("\n")
        if missing:
            w("## Not derivable here\n\n")
            for cls, why in missing:
                w(f"- **{cls}** -- {why}\n")
        w("\n## Doc-claim verification\n\n| class | slot | doc said | derived | verdict |\n"
          "|---|---|---|---|---|\n")
        for cls, off, want, got, st in results:
            w(f"| {cls} | `+0x{off:X}` | {want} | {got or '-'} | {st} |\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--json")
    args = ap.parse_args()

    derived, missing = derive()
    results = verify(derived)

    total_slots = sum(d["nslots"] for d in derived.values())
    named = sum(1 for d in derived.values() for r in d["slots"] if r["name"])
    repointed = [(c, r) for c, d in derived.items() for r in d["slots"] if r["live"] is not None]
    print(f"{len(derived)} classes derived, {len(missing)} missing; "
          f"{total_slots} slots, {named} named from exports "
          f"({100 * named // max(total_slots, 1)}%)")
    for cls, why in missing:
        print(f"  missing {cls}: {why}")

    print(f"\nLIVE VMT repoints (mod hooks): {len(repointed)}")
    for cls, r in repointed:
        tgt = r["live_name"] or f"{r['live']:08X}"
        print(f"  {cls:22s} +0x{r['off']:03X} {r['name'] or '?':30s} -> {tgt}")

    counts = {}
    for *_x, st in results:
        counts[st] = counts.get(st, 0) + 1
    print(f"\nclaim verification: {counts}")
    for cls, off, want, got, st in results:
        if st not in ("PASS",):
            print(f"  {st:12s} {cls:16s} +0x{off:03X}  doc: {want:26s} derived: {got}")

    if args.full:
        for cls, d in derived.items():
            print(f"\n=== {cls} VMT={d['vmt']:08X} instsize=0x{d['instsize']:X} "
                  f"parent={d['parent']} ===")
            for r in d["slots"]:
                live = f"  LIVE->{r['live_name'] or ('%08X' % r['live'])}" if r["live"] else ""
                print(f"  +0x{r['off']:03X} {r['rel']:8s} {r['name'] or '(not exported)'}{live}")

    if args.md:
        path = os.path.join(GAME, "Modding Resources", "Ghidra_VMT_Layouts.md")
        emit_md(derived, missing, results, path)
        print(f"\nwrote {path}")
    if args.json:
        with open(args.json, "w", encoding="utf8") as f:
            json.dump({"classes": derived, "missing": missing}, f, indent=1)
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
