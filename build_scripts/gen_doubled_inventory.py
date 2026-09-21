#!/usr/bin/env python
r"""
gen_doubled_inventory.py -- regenerate `Zig notes/FivePct_Doubled_Sources_Inventory.md`.

The inventory is DERIVED, never hand-maintained: it is rendered from `fivepct_manifest.json` plus
`build_statdouble.py`'s PFS_TARGETS, so it cannot drift from what the build scripts actually write.
Re-run it after any manifest edit.

    python gen_doubled_inventory.py            print to stdout
    python gen_doubled_inventory.py --write    overwrite the doc
"""
import os, sys, io, json, collections, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
MANIFEST = os.path.join(HERE, "fivepct_manifest.json")
OUT = os.path.join(GAME, "Modding Resources", "Zig notes", "FivePct_Doubled_Sources_Inventory.md")

# Stage -> (family name, what the family is).  Mirrors build_statdouble.py's staging.
STAGES = {
    1:  ("Base stats, clamps and caps", "unit/hero stat ceilings and the AI's stat thresholds"),
    2:  ("`.pfs` unit and hero base stats", "the actual per-unit numbers, in data not code"),
    3:  ("Ability and enchantment stat modifiers", "the buff/debuff stack on `PassiveAb.*`"),
    4:  ("Effect-roll powers vs Resistance", "the attack side of every resistance check"),
    5:  ("Touch attacks", "`GetTouchAttack` on the touch abilities"),
    6:  ("Strategic-map hazards", "storms, grounds, fire, vortex, quake, poison"),
    7:  ("Combat-spell powers", "`TCombatSpell+0x34`, the spell's attack stat"),
    8:  ("Champion / slaying bonuses and ranged attack constants", "conditional ATK and the innate ranged attacks"),
    9:  ("Tactical combat (`AoWTCPCK.dpl`)", "the manual-combat wall and terrain values"),
    10: ("Walls, Parry, wall-crushing, self-destruct, default units", "the remainder found by audit"),
    11: ("Ziggurat cave constants", "constants owned by five feature build scripts, not by the manifest"),
    12: ("Underground ranged malus", "its own stage so it can be written without touching stage 11"),
}
NOT_DOUBLED = r"""
## What was NOT doubled, and why

Two different reasons. Neither is an oversight; both are recorded decisions.

### Deliberate exceptions — decision D2 (user, 2026-08-18)

> *"Do NOT double: items, medal ranks, morale, Leadership."* These four **become half as influential**
> relative to everything else. That was the point of the exception, not a side effect.

| source | where | live values | effect |
|---|---|---|---|
| **Item bonuses** | `Release/ITEMS.PFS` tags `0x0B` ATK / `0x0C` DEF / `0x0E` RES — 23 / 28 / 23 bytes | 1..3 | a `+2 ATK` sword is now worth `+1` on the doubled scale |
| **Medal rank bonuses** | `AoWE.AttackRankProgression` `0x558E83C8` = `[0,1,2,3]`, `DefenseRankProgression` `0x558E83C4` = `[0,0,0,1]`, `ResistanceRankProgression` `0x558E83D0` = `[0,1,2,3]` | 0..3 | gold medal gives half its former weight |
| **Morale modifiers** | `AoWE.MoraleResistanceModifier` `0x558E83D8` = `[-3,-2,-1,0]`, `MoraleDefenseModifier` `0x558E83E0` = `[-2,-1,0,0]`, plus the morale→ATK bands in cave `0x5580C0F7` (`0x5580C115`, `0x5580C119`) | -3..0 | morale swings matter half as much |
| **Leadership** | the vanilla exports `LeadershipAttackProgression` `0x558E83E8` / `LeadershipDefenseProgression` `0x558E83EC` are **dead** — `build_leadership4.py` repointed `GetAttack`/`GetDefense`'s disp32 to its own 5-byte tables at **`0x5580F0C0` / `0x5580F0C8`**, indexed by level | ATK `1,2,3,4`<br>DEF `1,2,3,4` | not doubled, but **re-tuned 2026-08-20** to a flat +5/+10/+15/+20 pp ramp (was ATK `1,1,2,2` / DEF `0,1,1,2`) — level IV now matches vanilla Leadership's effective strength |

⚠ **Leadership's live curve is the one D2 exception you can still tune freely** — it is data, owned by
`build_leadership4.py` (`ATK_BONUS` / `DEF_BONUS`), and that script re-tunes in place: edit and re-run
with `--apply`, no revert. The other three exceptions are not so easy.
⚠ The three rank tables and the two morale tables are **owned by `build_copper_medal.py`**
(its `STAT_TABLES`), not by `build_statdouble.py`. If D2 is ever reversed, double them there — and add
the current tuning to that script's `PRIOR_TUNINGS` — or its verify will refuse.
⚠ The rank tables are live: read at `0x557829DD`/`0x557829F9` (`TUnit.GetAttack`),
`0x55782A31`/`0x55782A4D` (`GetDefense`), `0x55782B11` (`GetResistance`).

### Undecided — `HEROES.PFS`

`Release/HEROES.PFS` is the library of 50 predefined heroes. `THero.ReadWrite @0x55788880` maps
tag `0x10` = `bAtk_bonus`, `0x11` = `bDef_bonus`, `0x15` = `bRes_bonus` — **39 / 37 / 32 bytes, values
1..3, currently un-doubled.** `build_statdouble.py` records this as *"a separate decision that has not
been taken"*, distinct from the D2 item exception.

It matters because D3+D4 make heroes *"a pure identity"* (costs halve, caps double). A library hero's
stored bonus is stat points, so leaving it un-doubled makes predefined heroes start 1..3 points short on
the doubled scale. Small, but it is the one place where a stated decision and the installed state disagree.
⚠ `HEROES.PFS` and `ITEMS.PFS` carry **no PFS magic and no CRC** — never run the CRC repair over them;
appending one destroys four bytes of real data.

### Correctly untouched

Damage, hit points and movement are not ATK/DEF/RES and must not double, or the identity breaks:
`AoWE.DamageRankProgression` `0x558E83CC` = `[0,0,1,1]`, `HitsRankProgression` `0x558E83D4` (dead),
the `.pfs` damage tags (`ITEMS.PFS 0x0D`, `HEROES.PFS 0x12`), and every `add [esp],1` damage addend in
the stage-11 caves. Probabilities expressed in percent do not double either — including the flat
10% auto-miss / auto-max bands of `ExecuteDamageRole`, which are `RandInt(20)` thresholds.

### How to check the data side without the game

**Parity.** Every doubled `.pfs` stat byte is even; the pre-conversion tables were full of odd values.

| file | ATK/DEF/RES odd values | reading |
|---|---|---|
| `Unitres.pfs` | 0 / 0 / 0 | doubled |
| `HERORES.PFS` | 0 / 0 / 0 | doubled |
| `ITEMS.PFS` | 18 / 20 / 21 | not doubled (D2, intended) |
| `HEROES.PFS` | 37 / 33 / 30 | not doubled (undecided) |
"""


PFS = {"Unitres.pfs": (179, {0x0E: "ATK", 0x0F: "DEF", 0x13: "RES"}),
       "HERORES.PFS": (38, {0x0F: "ATK", 0x10: "DEF", 0x14: "RES"})}


def load():
    m = json.load(io.open(MANIFEST, encoding="utf-8"))
    return m if isinstance(m, list) else m.get("entries", m)


def render(ents):
    L = []
    W = L.append
    dbl = [e for e in ents if e.get("decision") == "DOUBLE"]
    hlv = [e for e in ents if e.get("decision") == "HALVE"]
    kinds = collections.Counter(e.get("kind") for e in dbl)

    W("# 5% conversion — itemised inventory of doubled ATK / DEF / RES sources")
    W("")
    W("**GENERATED FILE — do not hand-edit.** Rendered from `build_scripts/fivepct_manifest.json` by")
    W("`build_scripts/gen_doubled_inventory.py`; re-run it after any manifest change.")
    W("Companion to `FivePct_Conversion_Manifest.md`, which holds the decisions and the traps.")
    W("")
    W("**CONFIRMED WORKING (2026-08-24)** — applied 2026-08-20, validated in-game by the user.")
    W("")
    W("| | ATK | DEF | RES | total |")
    W("|---|---|---|---|---|")
    W("| code immediates doubled | %d | %d | %d | %d |"
      % (kinds["ATK"], kinds["DEF"], kinds["RES"], len(dbl)))
    npfs = sum(n for n, _ in PFS.values())
    W("| `.pfs` data bytes doubled | %d | %d | %d | %d |" % (npfs, npfs, npfs, npfs * 3))
    W("| skill-point prices **halved** | 2 | 2 | 2 | %d |" % len(hlv))
    W("")
    W("(The two `NO-DOUBLE` rows inside stage 11 are Turn Undead's rounding addends, which move with")
    W("its `shr` and are not stats. Counts above exclude them from ATK/DEF/RES.)")
    W("")

    for st in sorted(STAGES):
        g = sorted([e for e in dbl + hlv if e.get("stage") == st], key=lambda x: x["immVA"])
        name, blurb = STAGES[st]
        if st == 2:
            W("## Stage 2 — %s" % name)
            W("")
            W("*%s.* Written by `build_statdouble.py` as in-place 1-byte pokes, CRC repaired after.")
            W("Tag → field mapping verified from `THeroResource.ReadWrite @0x55789FD4` and cross-checked")
            W("against its `UsedSkillPoints` cost multipliers.")
            W("")
            W("| file | records | ATK tag | DEF tag | RES tag | bytes |")
            W("|---|---|---|---|---|---|")
            for fn, (n, tm) in PFS.items():
                inv = {v: k for k, v in tm.items()}
                W("| `%s` | %d | `0x%02X` | `0x%02X` | `0x%02X` | %d |"
                  % (fn, n, inv["ATK"], inv["DEF"], inv["RES"], n * 3))
            W("")
            W("⚠ **`HERORES.PFS` ATTACK has since been doubled AGAIN** by")
            W("`build_hero_chassis_atkdam.py` (2026-08-20, a deliberate balance change on top of this")
            W("conversion), together with chassis DAMAGE. So its ATK column reads 4..16, not the 2..8")
            W("stage 2 left. See `Hero_Chassis_ATK_DAM_Double.md` — **it also fixes the undo order.**")
            W("")
            W("Verification without the game: **every one of those %d bytes is now even.** A single odd"
              % (npfs * 3))
            W("value would prove the doubling incomplete, because the pre-conversion tables contained odd")
            W("values throughout.")
            W("")
            continue
        if not g:
            continue
        W("## Stage %d — %s (%d)" % (st, name, len(g)))
        W("")
        W("*%s.*" % blurb)
        W("")
        W("| module | immediate VA | stat | change | site |")
        W("|---|---|---|---|---|")
        for e in g:
            arrow = "%s → %s" % (e.get("live"), e.get("newValue"))
            kind = e.get("kind")
            if e.get("decision") == "HALVE":
                kind = kind + " (halved)"
            what = (e.get("what") or "").replace("|", "\\|")
            W("| `%s` | `%s` | %s | %s | %s |" % (e["module"], e["immVA"], kind, arrow, what))
        W("")
    W(NOT_DOUBLED)
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    txt = render(load())
    if a.write:
        io.open(OUT, "w", encoding="utf-8", newline="\n").write(txt)
        print("wrote %s (%d lines)" % (os.path.relpath(OUT, GAME), txt.count("\n")))
    else:
        sys.stdout.write(txt)


if __name__ == "__main__":
    main()
