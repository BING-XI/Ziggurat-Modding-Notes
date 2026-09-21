# -*- coding: utf-8 -*-
r"""Live ATK / DAM / shots / range for the ranged AND touch attack families.

    import ranged_stats
    ranged_stats.stats("AoWEPACK.dpl")   -> {id: {"atk","dam","shots","band","hexes"}}
    ranged_stats.touch("AoWEPACK.dpl")   -> {id: {"atk","dam"}}  (strings; "-" where none)

Point it at the live DLL for Ziggurat's numbers and at `AoWEPACK_original_backup.dpl` for
vanilla's; the code layout is identical in both, which is what makes one address table serve
for each.

WHY THIS EXISTS. The design workbook's `Abil` sheet is a historical snapshot (see CLAUDE.md)
and its Ziggurat column predates the 2026-08 doubling, so every ranged row in the Ziggurat
Manual was wrong -- Archery read 3/2 against a live 6/5, the breaths 7/5 against 14/11. These
numbers move whenever anyone re-tunes an attack, so they are derived rather than transcribed.

FIELD IDENTIFICATION -- proven from the accessors, not assumed:

    GetAttackRA       @0x5576E65C   mov bl,[eax+0x2a]     ATTACK
    GetDamageRA       @0x5576E614   mov bl,[eax+0x29]     DAMAGE
    GetRangeRA        @0x5576E610   mov al,[eax+0x28]     RANGE BAND (1 short/2 medium/3 long)
    GetAttackRepeatRA @0x5576E6AC   mov al,[eax+0x2d]     SHOTS PER ATTACK
    GetDamageTypesRA  @0x5576E6B0   word [eax+0x2b]       damage TYPE set -- NOT a number

Three construction routes reach those fields, and they do not agree on where the values come
from, which is exactly why a naive scan misses some:

  * ranged ctor 0x5576ED48 -- ATTACK in CL; DAMAGE, SHOTS, RANGE are pushes 1, 2, 3
  * bolt   ctor 0x5576EDE8 -- ATTACK in ECX; DAMAGE is push 1; shots and range are fixed
                              (1 and 2) inside TBoltsAbility.Create
  * breath ctor 0x5576EE84 -- takes NO numbers at all. Fire, Cold, Black, Divine and Poison
                              Breath ALL inherit one shared ATK/DAM pair written by
                              TBreathAbility.Create, so re-tuning that byte moves five
                              abilities at once. Flame Throwing then overrides both in its
                              own Create.

⚠ The remaining pushes in a block are the damage-type element and a sound index. Reading one
of those as a number yields a plausible-looking value that is neither attack nor damage.

The two direct-write routes are enumerated explicitly below rather than scanned: there are
only two of them, they are not call sites, and naming them keeps this module honest about
the fact that five abilities share one byte.
"""
import io
import struct

IMAGE_BASE = 0x55700000

CTOR_RANGED = 0x5576ED48
CTOR_BOLT = 0x5576EDE8

# ability id -> (attack VA, damage VA) for the abilities whose values are written directly
# rather than passed to a ctor. Shots and band come from TBreathAbility.Create (both 1).
BREATH_SHARED = (0x5576EE6A, 0x5576EE6E)        # imm of mov byte [esi+0x2a]/[esi+0x29]
BREATH_IDS = (0x56, 0x57, 0x58, 0x59, 0x5A)     # Fire, Cold, Black, Divine, Poison Breath
# ⚠ Flame Throwing is ability 0x1E (record 40 = id + 10), NOT 0x28 -- 0x28 is Entangle, a
# touch ability with no business in a ranged table. Getting this wrong silently publishes
# Flame Throwing's numbers under Entangle's name.
DIRECT = {0x1E: (0x5576F23D, 0x5576F241)}       # Flame Throwing, overrides the shared pair


# TCombatRange band -> maximum range in HEXES, inclusive. NOT a formula -- three hard-coded
# immediates replicated at four independent sites in AoWTCPCK.dpl, each keyed on
# TAbility.GetCombatMode (VMT +0x84) = CombatRangeToCombatMode(GetRangeRA @+0x10C):
#   TCombatUnitSelectionControl.CalculateRangedPath  0x0041DD77 / 0x0041DDB3 / 0x0041DDBB
#     -- the player-facing gate: compares HSEngine.dHXtoRad against this and returns an empty
#        path (= no shot) when the target is further
#   TCAI.CheckUnit 0x004174AA/DA/E3, TCAI.EvalBattle 0x00418969/99/A2  -- the tactical AI
#   TTacticalCombatUnitHS.SelectAbility 0x0042315F/49/09               -- the cursor radius
# The RTTI enum is TCombatRange = (crTouch, crShort, crMedium, crLong) at VA 0x55715488.
# Corroboration: the workbook's VANILLA range column matches band x 4 on all 16 of its numeric
# rows, a hypothesis derived from the code and then checked against data it never saw.
# ⚠ It is a CEILING, not a promise -- manual combat retargets shots onto intervening units and
# walls, so "cannot shoot beyond N" is true where "can hit anything within N" is not.
# ⚠ Three of the four sites reach 4 through a fall-through `else`, which would also catch
# cmTouch/cmMelee/cmNone. Only ever feed this a ranged ability.
# ⚠ Auto-resolve uses a COMPLETELY different scale -- fcValidRoundDistance @0x5576ECF0 adds
# +1/+2/+4 rounds of closing for short/medium/long. The two systems share no number.
BAND_HEXES = {1: 4, 2: 8, 3: 12}

# Self Destruct is a touch ability that sits in the sheet's RANGED block, and it writes its
# ATK/DAM straight into the combat-info record rather than going through any ctor.
SELF_DESTRUCT = (0x41, 0x55768DEA, 0x55768DEE)      # id, atk imm, dam imm

# `GetTouchAttack` overrides: `mov al, imm8; ret`, so the immediate is always export + 1.
# The nine exports are the complete set (checked against .edata).
TOUCH_ATK = {
    0x94: 0x55770799,   # Charm
    0x1C: 0x55770665,   # Dominate
    0x28: 0x5576A811,   # Entangle
    0x1B: 0x5576A20D,   # Web
    0x23: 0x5576B84D,   # Invoke Death
    0x6A: 0x55769BE9,   # Possess
    0x1D: 0x55770979,   # Seduce
}
# ⚠ TTouchAbility.GetTouchAttack @0x557680CC is `mov al,0xF6` = -10, a FAIL SENTINEL meaning
# "this ability has no touch attack" -- three guards compare against -10 literally. Never
# publish it and never scale it. Dispel Magic inherits it and genuinely has no ATK or DAM.
TOUCH_SENTINEL = 0x557680CD

TURNUNDEAD_ATK = (0x5576B203, 0x5576B206, 0x5576B209, 0x5576B20C)   # per level I..IV
TURNUNDEAD_DAM = (0x5576B223, 0x5576B226, 0x5576B229, 0x5576B22C)   # per level I..IV
# ⚠ In the LIVE dll those four constants are DEAD for gameplay: build_turnundead_res.py
# redirected the execution call at TURNUNDEAD_CALL to a cave, and the info-card body is
# jumped over, so only the AI's GetOffensiveStrength still reads them. Damage is Resistance x
# level on both the card and the strike. In a PRISTINE dll they are the real per-level values.
# Rather than assume which file it has been handed, the reader TESTS the call target -- so it
# reports what the binary in front of it actually does.
TURNUNDEAD_CALL = 0x5576B589            # `call GetTurnUndeadDamage` in CreateTurnUndeadCA
TURNUNDEAD_DAMFN = 0x5576B214           # ... its vanilla target
HEAL_AMOUNT = 0x5576C098        # ⚠ a CAP on the HP deficit: min(N, maxHits - currentHits)


def _sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    o = struct.unpack_from("<H", d, pe + 20)[0]
    out = []
    for i in range(n):
        p = pe + 24 + o + i * 40
        nm = d[p:p + 8].rstrip(b"\0").decode("latin-1")
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, p + 8)
        out.append((nm, va, vsz, raw, rsz))
    return out


def _off(secs, va):
    rva = va - IMAGE_BASE
    for _nm, sva, vsz, raw, rsz in secs:
        if sva <= rva < sva + max(vsz, rsz):
            return raw + (rva - sva)
    return None


def stats(path):
    """{ability_id: {"atk", "dam", "shots", "band"}} for every ranged-family attack."""
    d = io.open(path, "rb").read()
    secs = _sections(d)
    out = {}

    for nm, va, _vsz, raw, rsz in secs:
        if nm not in ("CODE", ".text"):
            continue
        b = d[raw:raw + rsz]
        for i in range(len(b) - 5):
            if b[i] != 0xE8:
                continue
            tgt = IMAGE_BASE + va + i + 5 + struct.unpack_from("<i", b, i + 1)[0]
            if tgt not in (CTOR_RANGED, CTOR_BOLT):
                continue
            # `mov eax, <ability id>` sits immediately before the call
            if i < 5 or b[i - 5] != 0xB8:
                continue
            aid = struct.unpack_from("<I", b, i - 4)[0]
            # ATTACK: `mov ecx, imm32` (B9) or `mov cl, imm8` (B1) just before that
            j = i - 5
            if j >= 5 and b[j - 5] == 0xB9:
                atk = struct.unpack_from("<I", b, j - 4)[0]
            elif j >= 2 and b[j - 2] == 0xB1:
                atk = b[j - 1]
            else:
                continue
            # DAMAGE / SHOTS / RANGE are the ctor's pushes, and ORDER matters -- the first
            # push is damage, the third is the range band. ⚠ Take the LAST n pushes in the
            # window, not the first n: the window can reach back into the preceding
            # registration block, and scanning forward then attributes ITS pushes to this
            # call. That produced a damage of 0 for Black Bolts, the first block of its run.
            want = 3 if tgt == CTOR_BOLT else 4
            lo = max(0, i - 0x50)
            win, pushes, k = b[lo:i], [], 0
            while k < len(win) - 1:
                if win[k] == 0x6A:
                    pushes.append(win[k + 1])
                    k += 2
                else:
                    k += 1
            if len(pushes) < want:
                continue
            pushes = pushes[-want:]
            if tgt == CTOR_BOLT:
                # TBoltsAbility.Create fixes range band 2 and 1 shot; only damage is pushed.
                out[aid] = {"atk": atk, "dam": pushes[0], "shots": 1, "band": 2}
            elif len(pushes) >= 3:
                out[aid] = {"atk": atk, "dam": pushes[0],
                            "shots": pushes[1], "band": pushes[2]}

    # the five breaths share one pair; Flame Throwing overrides it
    a_off, d_off = _off(secs, BREATH_SHARED[0]), _off(secs, BREATH_SHARED[1])
    if a_off is not None and d_off is not None:
        shared = {"atk": d[a_off], "dam": d[d_off], "shots": 1, "band": 1}
        for aid in BREATH_IDS:
            out[aid] = dict(shared)
    for aid, (av, dv) in DIRECT.items():
        ao, do = _off(secs, av), _off(secs, dv)
        if ao is not None and do is not None:
            out[aid] = {"atk": d[ao], "dam": d[do], "shots": 1, "band": 1}

    sd_id, sd_a, sd_d = SELF_DESTRUCT
    ao, do = _off(secs, sd_a), _off(secs, sd_d)
    if ao is not None and do is not None:
        # a touch ability, so no band: the sheet prints the word "short" for its range
        out[sd_id] = {"atk": d[ao], "dam": d[do], "shots": 1, "band": None}

    for v in out.values():
        v["hexes"] = BAND_HEXES.get(v["band"])
    return out


def touch(path):
    """{ability_id: {"atk", "dam"}} for the touch family. Values are STRINGS, with "-" where
    the ability genuinely has none, so they drop straight into the manual's table cells."""
    d = io.open(path, "rb").read()
    secs = _sections(d)
    out = {}
    for aid, va in TOUCH_ATK.items():
        o = _off(secs, va)
        if o is not None:
            out[aid] = {"atk": str(d[o]), "dam": "-"}

    lv = [_off(secs, v) for v in TURNUNDEAD_ATK]
    if all(x is not None for x in lv):
        atk = "/".join(str(d[x]) for x in lv)
        co = _off(secs, TURNUNDEAD_CALL)
        hooked = True
        if co is not None and d[co] == 0xE8:
            tgt = TURNUNDEAD_CALL + 5 + struct.unpack_from("<i", d, co + 1)[0]
            hooked = tgt != TURNUNDEAD_DAMFN
        if hooked:
            dam = "Res x level"
        else:
            dv = [_off(secs, v) for v in TURNUNDEAD_DAM]
            dam = "/".join(str(d[x]) for x in dv) if all(x is not None for x in dv) else "-"
        out[0x26] = {"atk": atk, "dam": dam}

    o = _off(secs, HEAL_AMOUNT)
    if o is not None:
        out[0x2F] = {"atk": "-", "dam": "up to %d" % d[o]}
    return out


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ability_names
    names = ability_names.names()
    for f in sys.argv[1:]:
        print("== %s" % f)
        s = stats(f)
        for aid in sorted(s):
            v = s[aid]
            print("   0x%02X %-18s ATK %-3d DAM %-3d shots %d band %d"
                  % (aid, names.get(aid, "?")[:18], v["atk"], v["dam"], v["shots"], v["band"]))
        print("   (%d abilities)" % len(s))
