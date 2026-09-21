# -*- coding: utf-8 -*-
r"""
build_turnundead_resroll.py — Turn Undead's stun/seize roll becomes an OPPOSED Resistance check.

    python build_scripts/build_turnundead_resroll.py            dry run + verify + disassembly
    python build_scripts/build_turnundead_resroll.py --apply     write it
    python build_scripts/build_turnundead_resroll.py --undo      restore both call sites, zero the cave
    python build_scripts/build_turnundead_resroll.py --dis       disassemble the installed caves

Implements §4a-ter of `Zig notes/TurnUndead_EvilCommand_Design.md`. Target: AoWEPACK.dpl only.

────────────────────────────────────────────────────────────────────────────────────────────
WHAT CHANGES
────────────────────────────────────────────────────────────────────────────────────────────
Turn Undead lands its stun through TWO rolls, not one:

  1. to-hit      HitRole(attackerATK − targetDEF)          — in CreateTurnUndeadCA
  2. damage roll ExecuteDamageRoleEx(param_4 = 1) ⇒ the DEFENDER's term is GetResistance,
                 and the ATTACKER's term was `GetTouchAttack(level)` — the flat level table
                 18/20/22/24 (Ziggurat-doubled from vanilla 9..12).

Roll 2's result is stored in `ca[+0x10]`, which is simultaneously the damage amount AND the
success flag the stun (and, in build_turnundead_evilcommand.py, the seize) gates on.

This script replaces the ATTACKER's term of roll 2 with

        casterRES × (4 + level) / 5        (= ×1 / ×1.2 / ×1.4 / ×1.6 for Turn Undead I–IV)

so roll 2 becomes a true opposed `casterRES − targetRES` check, with NO new gate and NO new
RNG draw. The level term is free: the level is already sitting in EDX at the call site.

Why this is worth doing: `touchAttack` is a vanilla 1..10-scale number being compared against a
DOUBLED Resistance stat, so against undead with RES ≥ 20 Turn Undead is floored at the 10 %
auto-max and effectively does nothing.

⚠ It also shifts the damage AMOUNT for non-evil casters, because `ExecuteDamageRole` uses the
same difference for its zero-threshold and for its ramp. That is a real balance change and
needs the user's feel check.

⚠ `GenerateEx` takes the attack argument as a **char** and sign-extends it, so a value above
127 would read negative. Not reachable at current clamps (hero RES caps at 40 ⇒ max 40×8/5 =
64) and vanilla `touchAttack` had the identical property. Deliberately NOT clamped, so that
the display path below computes bit-for-bit the same number.

────────────────────────────────────────────────────────────────────────────────────────────
THE TWO CALL SITES — the same six bytes, twice
────────────────────────────────────────────────────────────────────────────────────────────
Both are `ff 91 0c 01 00 00` = `call dword ptr [ecx+0x10C]` = GetTouchAttack(level), and both
are replaced by `E8 rel32` + one `nop`.

  A. COMBAT   0x5576B57C   inside AoWE.TTurnUndeadAbility.CreateTurnUndeadCA @0x5576B528.
                           Registers there: EBX = ability, ESI = attacker COMBAT object,
                           EBP = target combat object, EDI = the CA, EDX = level.
                           The host reloads EDX at 0x5576B583 and ECX at 0x5576B598, so the
                           cave may clobber EAX/ECX/EDX freely; EBX/ESI/EDI/EBP are untouched.
                           This is the same ABI the existing damage cave at 0x5580E2A0 already
                           uses successfully FROM THIS VERY CALL SITE.

  B. DISPLAY  0x5580E31B   inside build_turnundead_res.py's cave_combatinfo @0x5580E300, which
                           wholly replaces AoWE.TTurnUndeadAbility.GetCombatInfo. It writes the
                           info card's ATK from GetTouchAttack(level). Once the roll uses caster
                           RES the card must show caster RES too, or display and behaviour
                           diverge. Registers there: EBX = out buffer, ESI = this, EBP = OWNER
                           (a STRATEGIC unit, may be nil), EDI = level, EDX = level.

⚠⚠ SITE B EDITS SIX BYTES INSIDE ANOTHER SCRIPT'S CAVE. This is deliberate and is the cheapest
correct option; the alternative (rewriting cave_combatinfo whole) does not fit — the free run
after it is only EIGHT bytes (0x5580E368..0x5580E370, and 0x5580E370 is claimed by another
feature), while the new body needs ~20 more. Consequences, both loud rather than silent:

  * `build_turnundead_res.py` compares each of its cave bodies as a whole, so it REFUSES to
    write. That is verify-before-write working, not damage.
    ⚠ WHAT IT ACTUALLY PRINTS IS `[x] cave zone 5580E2A0 not free` — its FIRST cave, the damage
    one, which this patch does not touch at all. It aborts there and never reaches
    cave_combatinfo @0x5580E300, so you will not see 0x5580E300 named in its output even though
    that cave is edited here too.
    ⚠ MEASURED 2026-09-01 against `AoWEPACK.dpl.pre-turnundeadresroll`: it was ALREADY refusing,
    for BOTH of its caves, BEFORE this patch existed. Its variant generator re-assembles from
    source and today's keystone encodes `shr eax, 1` as the 2-byte `d1 e8`, while the installed
    body holds the 3-byte `c1 e8 01` — which is what `build_turnundead_double.py` produces,
    because that script patches the shift IMMEDIATE in place inside the original `shr eax, 2`
    (`c1 e8 02`) rather than re-assembling. So the two scripts have disagreed since the doubling
    shipped; this patch is not the cause and `--undo` here does not cure it.
  * `build_turnundead_double.py` is UNAFFECTED — its four immediates live at 0x5580E33A /
    0x5580E33C / 0x5580E33D / 0x5580E33F, well past the six bytes taken here, and it verifies
    only those opcodes.

NOTHING here reverts or restores `.pre-turnundead` (38 newer snapshots stack on it). Per the
project convention this is an in-place rewrite: verify-before-write accepts EITHER the
currently-installed bytes OR our own, the cave zone is asserted zero (or ours) before writing,
and the backup is a fresh feature-named one.

────────────────────────────────────────────────────────────────────────────────────────────
POSITION INDEPENDENCE / RNG
────────────────────────────────────────────────────────────────────────────────────────────
Both caves are register-only + register-indirect virtual calls + immediates. No absolute
address, no data reference, so the DPL's runtime rebase cannot touch them and no PIC anchor is
needed. Neither displaced run carries a `.reloc` entry (asserted before writing).

No RNG draw is added or moved: `ExecuteDamageRole` keeps making exactly the roll it already
made, with one of its two inputs changed. `rng_audit.py --owners` must show no new site.
"""
import os
import shutil
import struct
import subprocess
import sys

# The Windows console defaults to cp1252 and cannot encode U+26A0. Without this the script
# writes its bytes correctly and THEN dies with a UnicodeEncodeError while printing, which
# reads as a failed patch when it was a successful one.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

try:
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    sys.exit("needs keystone-engine and capstone:  py -m pip install keystone-engine capstone")

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-turnundeadresroll")
DLL_BASE = 0x55700000

# ================================================================== the knobs
# attacker term of roll 2 = casterRES * MULT_NUM(level) / MULT_DEN, rounded to nearest.
# MULT_NUM(level) = level + MULT_BIAS.  (bias 4, den 5)  =>  1 / 1.2 / 1.4 / 1.6 for I..IV.
MULT_BIAS = 4
MULT_DEN = 5
# ===========================================================================

RES_COMBAT = 0x74       # combat-object VMT: TCombatUnit.GetResistance   (no args -> AL)
RES_STRAT = 0xCC        # strategic-unit VMT: GetResistance              (no args -> AL)

# --- hook sites, with their exact expected bytes ----------------------------------
CALL_TOUCHATTACK = bytes.fromhex("ff910c010000")        # call dword ptr [ecx+0x10C]
COMBAT_INJ = 0x5576B57C          # in TTurnUndeadAbility.CreateTurnUndeadCA
INFO_INJ = 0x5580E31B            # in build_turnundead_res.py's cave_combatinfo

# --- cave placement ---------------------------------------------------------------
# 0x55831000: page-aligned, ABOVE every address claimed by any build script (the highest
# non-zero byte anywhere in the DLL's CODE section is 0x5582F044, and the highest cave any
# script claims is build_embrittle.py's 0x5582D000 zone). Verified 2026-09-01:
#     grep -rl "5583" "Modding Resources/build_scripts/"   -> three files, and every hit is a
#     BYTE STRING ("5583C4F8" = push ebp; add esp,-8), not an address.
# There is not one .reloc entry anywhere in 0x55830000..0x55840000.
# ⚠ A zero run is not proof a zone is unclaimed — read the scripts, not the zeros.
CAVE = 0x55831000
CAVE_ZONE_LEN = 0x100           # reservation incl. growth slack; asserted zero (or ours)

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

AOW_PROCS = ["AoW", "AoWCompat", "AoWDevEd", "AoWEd"]


def kill_aow():
    """Game files are locked while any AoW binary runs; AoWDevEd loads AoWEPACK.dpl too.
    Standing authorization to kill them — the game autosaves per turn and the editor prompts
    on its own next launch."""
    killed = [n for n in AOW_PROCS
              if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                                capture_output=True, text=True).returncode == 0]
    if killed:
        print("  killed running: " + ", ".join(killed))


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


# ------------------------------------------------------------------ cave_atk
def build_atk(va, bias=None, den=None):
    """COMBAT site. Returns EAX = round(casterRES * (bias+level) / den).

    In : EDX = ability level (1..4), ESI = the attacker's COMBAT object.
    Out: EAX. Clobbers EAX/ECX/EDX only — the caller reloads both.

    `xor edx,edx` before `div` is mandatory (div is EDX:EAX / r32).
    Max intermediate 255*8 + 2 = 2042: no overflow, no need for a wider form.
    """
    bias = MULT_BIAS if bias is None else bias
    den = MULT_DEN if den is None else den
    src = """
        push  edx
        mov   eax, esi
        mov   edx, dword ptr [eax]
        call  dword ptr [edx + 0x%X]
        movzx eax, al
        pop   edx
        movzx edx, dl
        add   edx, %d
        imul  eax, edx
        add   eax, %d
        mov   ecx, %d
        xor   edx, edx
        div   ecx
        ret
    """ % (RES_COMBAT, bias, den // 2, den)
    return asm(src, va)


# ----------------------------------------------------------------- cave_info
def build_info(va, bias=None, den=None):
    """DISPLAY site. Same arithmetic, but the Resistance comes off the STRATEGIC unit.

    In : EDX = ability level, EBP = the OWNER (a strategic unit, MAY BE NIL — cave_combatinfo
         itself tests `test ebp,ebp` a few instructions later, so nil is a real case here in a
         way it is not at the combat site).
    Out: EAX (cave_combatinfo immediately does `mov [ebx+1], al`).
         Clobbers EAX/ECX/EDX only; EBX/ESI/EDI/EBP are untouched.

    Owner nil ⇒ RES 0 ⇒ (0*(4+L)+2)/5 = 0, which is what the card showed for a nil owner
    before (it printed the level table, but a nil owner also forced DAM to 0, so a 0/0 card is
    the consistent reading).

    ⚠ NOT clamped, deliberately: the combat site is not clamped either, and both results are
    written into a byte. An asymmetric clamp is exactly how display and damage drift apart.
    """
    bias = MULT_BIAS if bias is None else bias
    den = MULT_DEN if den is None else den
    src = """
        xor   eax, eax
        test  ebp, ebp
        jz    no_owner
        push  edx
        mov   eax, ebp
        mov   edx, dword ptr [eax]
        call  dword ptr [edx + 0x%X]
        movzx eax, al
        pop   edx
    no_owner:
        movzx edx, dl
        add   edx, %d
        imul  eax, edx
        add   eax, %d
        mov   ecx, %d
        xor   edx, edx
        div   ecx
        ret
    """ % (RES_STRAT, bias, den // 2, den)
    return asm(src, va)


# ------------------------------------------------------------------ cave zone
def build_zone(bias=None, den=None):
    """Lay both caves out from CAVE, 16-byte aligned -> (blob, [(label, va, code), ...])."""
    blob = bytearray()
    parts = []
    for label, builder in (("cave_atk", build_atk), ("cave_info", build_info)):
        blob += bytes((-len(blob)) % 16)
        va = CAVE + len(blob)
        code = builder(va, bias, den)
        blob += code
        parts.append((label, va, code))
    assert len(blob) <= CAVE_ZONE_LEN, "zone overflow: %d > %d" % (len(blob), CAVE_ZONE_LEN)
    return bytes(blob), parts


ZONE, PARTS = build_zone()

# Every zone layout this script has ever written. Verify-before-write accepts any of them as a
# starting state, so a RE-TUNE of the multiplier is a rewrite IN PLACE and never a revert —
# which this project does not have a backup stack for. APPEND here, never replace.
PRIOR_ZONES = [build_zone(bias=b, den=d)[0]
               for b, d in ((2, 2), (0, 1), (4, 4), (4, 2), (8, 10))
               if (b, d) != (MULT_BIAS, MULT_DEN)]

CAVE_ATK = next(v for l, v, _ in PARTS if l == "cave_atk")
CAVE_INFO = next(v for l, v, _ in PARTS if l == "cave_info")


def call_hook(site, target):
    """6 displaced bytes -> `call rel32` + one nop."""
    return b"\xE8" + struct.pack("<i", target - (site + 5)) + b"\x90"


# ---- (VA, new bytes, original bytes, description) --------------------------------
PATCHES = [
    (CAVE, ZONE, bytes(len(ZONE)),
     "cave zone (%d B): %s" % (len(ZONE), ", ".join("%s@%08X" % (l, v) for l, v, _ in PARTS))),
    (COMBAT_INJ, call_hook(COMBAT_INJ, CAVE_ATK), CALL_TOUCHATTACK,
     "CreateTurnUndeadCA %08X: GetTouchAttack(level) -> casterRES*(%d+level)/%d"
     % (COMBAT_INJ, MULT_BIAS, MULT_DEN)),
    (INFO_INJ, call_hook(INFO_INJ, CAVE_INFO), CALL_TOUCHATTACK,
     "cave_combatinfo %08X: info-card ATK -> ownerRES*(%d+level)/%d"
     % (INFO_INJ, MULT_BIAS, MULT_DEN)),
]


# ============================================================== file plumbing
def va2off(d, va, base=DLL_BASE):
    """⚠ per-section, never one global delta — this DLL's DATA skews differently from CODE."""
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    tbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        s = tbl + 40 * i
        vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
        if base + rva <= va < base + rva + max(vsz, rsz):
            off = ro + (va - base - rva)
            assert off < ro + rsz, "%08X past raw data" % va
            return off
    raise AssertionError("VA %08X in no section" % va)


def reloc_set(d, base=DLL_BASE):
    """Every VA the loader fixes up. A displaced run holding one of these cannot be
    overwritten — the rebase would rewrite our bytes at load time."""
    out = set()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    tbl = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    for i in range(nsec):
        s = tbl + 40 * i
        if d[s:s + 6] == b".reloc":
            vsz, rva, rsz, ro = struct.unpack_from("<IIII", d, s + 8)
            p, end = ro, ro + rsz
            while p + 8 <= end:
                page, sz = struct.unpack_from("<II", d, p)
                if sz < 8 or p + sz > end:
                    break
                for k in range(p + 8, p + sz, 2):
                    e = struct.unpack_from("<H", d, k)[0]
                    if e >> 12:
                        out.add(base + page + (e & 0xFFF))
                p += sz
    return out


def read(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def state_of(d):
    """-> ('applied' | 'vanilla' | 'stale' | 'mixed', verdicts)."""
    verdicts = []
    for va, new, orig, desc in PATCHES:
        o = va2off(d, va)
        cur = bytes(d[o:o + len(new)])
        priors = PRIOR_ZONES if va == CAVE else ()
        verdicts.append((va, desc,
                         "applied" if cur == new else
                         "vanilla" if cur == orig else
                         "stale" if any(cur == p[:len(cur)] for p in priors) else "FOREIGN"))
    kinds = {v for _, _, v in verdicts}
    if kinds == {"applied"}:
        return "applied", verdicts
    if kinds == {"vanilla"}:
        return "vanilla", verdicts
    if kinds <= {"applied", "stale"}:
        return "stale", verdicts
    return "mixed", verdicts


def odds_table():
    """The roll-2 landing chance after a successful to-hit, on the LIVE 5 %/point slope.

    ExecuteDamageRole: r = RandInt(20); r < 2 -> 0; r >= 18 -> max; else a ramp against
    t = 10 - diff, returning 0 when r < t or t > 17.  So P(land) = clamp(diff*5 + 50, 10, 90) %.
    """
    rows = []
    for cres in (8, 12, 20, 30):
        for tres in (8, 12, 20):
            cells = []
            for lvl in (1, 2, 3, 4):
                atk = (cres * (MULT_BIAS + lvl) + MULT_DEN // 2) // MULT_DEN
                cells.append(max(10, min(90, (atk - tres) * 5 + 50)))
            rows.append((cres, tres, cells))
    return rows


# =================================================================== reporting
def show():
    d = read(DLL)
    st, verdicts = state_of(d)
    relocs = reloc_set(d)
    print("build_turnundead_resroll — roll 2 becomes casterRES*(%d+level)/%d vs targetRES"
          % (MULT_BIAS, MULT_DEN))
    print("target: %s" % DLL)
    print()
    for va, desc, v in verdicts:
        print("  %08X  %-8s  %s" % (va, v, desc))
    print()
    print("  state: %s   cave zone %08X..%08X (%d B used of %d reserved)"
          % (st.upper(), CAVE, CAVE + CAVE_ZONE_LEN, len(ZONE), CAVE_ZONE_LEN))
    bad = [hex(x) for va, new, _o, _d in PATCHES if va != CAVE
           for x in relocs if va <= x < va + len(new)]
    print("  .reloc coverage of every displaced run: %s" % (bad or "clean"))
    print()
    print("  odds the stun/seize roll lands after a successful to-hit (live 5 %/point slope):")
    print("     casterRES  vs tRES   L1   L2   L3   L4")
    for cres, tres, cells in odds_table():
        print("        %-8d %-7d %s" % (cres, tres, "  ".join("%3d%%" % c for c in cells)))
    return st


def disassemble():
    d = read(DLL)
    print()
    for label, va, code in PARTS:
        o = va2off(d, va)
        live = bytes(d[o:o + len(code)])
        # Review the bytes THIS BUILD produces. Before --apply the zone is all zeros and
        # disassembling it prints pages of `add [eax],al`, which makes the review useless.
        tag = "" if live == code else ("   (not yet applied)" if set(live) <= {0}
                                       else "   ⚠ LIVE DIFFERS — shown: THIS BUILD")
        print("; ---- %s @%08X (%d B)%s ----" % (label, va, len(code), tag))
        for ins in cs.disasm(code, va):
            print("  %08X  %-9s %-9s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic,
                                            ins.op_str))
        print()
    print("; ---- hook sites (bytes THIS BUILD writes) ----")
    for va, new, _orig, desc in PATCHES:
        if va == CAVE:
            continue
        for ins in cs.disasm(new, va):
            print("  %08X  %-9s %-9s %-14s ; %s" % (ins.address, ins.bytes.hex(" "),
                                                    ins.mnemonic, ins.op_str, desc))
            desc = ""


# ==================================================================== writing
def apply(undo=False):
    kill_aow()
    d = read(DLL)
    st, verdicts = state_of(d)
    foreign = [(va, desc) for va, desc, v in verdicts if v == "FOREIGN"]
    if foreign:
        for va, desc in foreign:
            print("  ABORT: %08X holds neither our bytes nor the expected original — %s"
                  % (va, desc))
        sys.exit("aborted: verify-before-write refused (another feature may own a site)")

    want = "vanilla" if undo else "applied"
    if st == want:
        print("  already %s — nothing to do" % want)
        return

    relocs = reloc_set(d)
    for va, new, _orig, _desc in PATCHES:
        if va == CAVE:
            continue
        clash = [x for x in relocs if va <= x < va + len(new)]
        assert not clash, "%08X displaces a .reloc entry %s" % (va, [hex(x) for x in clash])

    o = va2off(d, CAVE)
    zone = bytes(d[o:o + CAVE_ZONE_LEN])
    # all-zero (never applied) or one of OUR earlier layouts (rewrite in place). The tail past
    # the prior blob must still be zero, so a shrinking rewrite cannot strand a fragment and a
    # growing one cannot walk into someone else's zone.
    ok = (set(zone) <= {0}
          or zone[:len(ZONE)] == ZONE and set(zone[len(ZONE):]) <= {0}
          or any(zone[:len(p)] == p and set(zone[len(p):]) <= {0} for p in PRIOR_ZONES))
    assert ok, ("cave zone %08X holds bytes that are neither zero nor a layout this script "
                "shipped — someone else is there" % CAVE)

    # ⚠ BACKUP GATING — only ever snapshot a file PROVED not to carry this feature. The gate is
    # a POSITIVE test that every site still holds its original bytes, never "no backup exists".
    # On --undo the file is the patched state by definition, and on a re-tune it is this
    # script's own previous output; either would mint a `.pre-*` full of patched bytes that
    # then sits on disk looking authoritative.
    if not undo and st == "vanilla" and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("  backup -> %s (every site verified un-patched)" % os.path.basename(BACKUP))
    elif not undo and not os.path.exists(BACKUP):
        print("  no backup taken: the file is not un-patched at these sites "
              "(a .pre-* full of patched bytes is worse than none).")

    if undo:
        d[o:o + CAVE_ZONE_LEN] = bytes(CAVE_ZONE_LEN)          # surgical: zero our own cave
    for va, new, orig, _desc in PATCHES:
        if va == CAVE:
            if not undo:
                d[va2off(d, va):va2off(d, va) + len(new)] = new
            continue
        oo = va2off(d, va)
        d[oo:oo + len(new)] = orig if undo else new

    try:
        with open(DLL, "wb") as f:
            f.write(d)
    except PermissionError:
        sys.exit("  LOCKED — an AoW binary is still holding AoWEPACK.dpl. Re-run.")
    print("  AoWEPACK.dpl  %s  (2 call sites + cave zone)" % ("REVERTED" if undo else "PATCHED"))

    d2 = read(DLL)
    st2, _ = state_of(d2)
    assert st2 == want, "read-back says %s, expected %s" % (st2, want)
    print("  read-back verified: %s" % st2)

    print()
    if undo:
        print("  reverted. build_turnundead_res.py should verify clean again.")
        return
    print("  NEXT:")
    print("      python \"Modding Resources/re_tools/rng_audit.py\" --owners   # expect no new site")
    print()
    print("  NEEDS THE USER'S IN-GAME TEST — nothing below can be checked from the files:")
    print("   1. The Turn Undead info card's ATK now tracks the CASTER'S RESISTANCE and rises")
    print("      with ability level (RES 20: 16 / 20 / 24 / 28 at levels I..IV), instead of the")
    print("      flat 18/20/22/24.")
    print("   2. The stun still lands about as often as the card implies, against undead whose")
    print("      Resistance you can read.")
    print("   3. A high-RES caster now beats RES-20+ undead, which previously it could not.")
    print("   4. The DAMAGE a non-evil caster deals has shifted with it — check that it feels")
    print("      right, because roll 2's difference drives the damage ramp as well as the")
    print("      zero-threshold.")
    print("   5. build_turnundead_double.py still reports both of its caves in step.")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if args - {"--apply", "--undo", "--dis"}:
        sys.exit(__doc__.split("Implements")[0])
    if "--dis" in args:
        disassemble()
    elif "--undo" in args:
        show(); apply(undo=True)
    elif "--apply" in args:
        show(); apply()
    else:
        show()
        disassemble()
        print()
        print("(dry run — nothing written.  --apply to patch, --undo to revert)")
