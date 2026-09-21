#!/usr/bin/env python3
r"""
AoW1 mod -- INVISIBILITY IS A DEFENSIVE ADVANTAGE (replaces the True-Seeing attack BONUS with an
attacker PENALTY that True Seeing negates).

  v1 (build_trueseeing.py):  attacker has True Vision (0x29) AND target Invisible (0x36)  -> +3 / +1 ATK
  v2 (this script):          target Invisible (0x36) AND attacker LACKS True Vision (0x29) -> -3 / -1 ATK

Same outcome for a True-Seeing unit vs everyone else (a 3-point melee differential), but the baseline
moves: being invisible is now strictly GOOD (harder to hit) instead of strictly BAD (only ever made you
easier to hit, by a True-Seeing attacker). True Seeing's value becomes "cancels the penalty".

VANILLA PRECEDENT -- the engine already has three conditional attack penalties of exactly this shape,
all applied as plain UNCLAMPED signed subtractions, so we copy that idiom rather than invent one:
  * Parry (ability 0x71) @0x55767BE1: `sub dword ptr [ebx], 4` -- at our site 2, every strike.
  * Wall penalty @0x5576EB1A: `sub al, byte ptr [ebp+8]` -- at our site 3; the caller
    (fcExecuteCombatCommand @0x5576EB70) passes 2 iff TFastCombat.GetWallSituation()==2, i.e. -2 ranged
    attack when shooting a target behind a city wall.
  * Vertigo @0x557BAC5C / Poisoned @0x557B9E68 return -2 from GetAttack (ability attack is ShortInt).

SIGNEDNESS (why no clamp is needed) -- attack is carried as a SIGNED byte the whole way down and is
never stored in the CA at all; it is a transient stack argument:
  TDamageCA.Generate @0x55729C46 `movsx edx, byte ptr [ebp+0x10]` (GenerateEx @0x55729CC2 likewise)
    -> TCombatObject.ExecuteDamageRole @0x557269F0: `call [edx+0x70]` GetDefense, `movsx eax,al`
       @0x55726A24, then a 32-bit signed `sub eax,edx` @0x55726A2C
    -> ExecuteDamageRole @0x55725EAC: every compare signed; `T = 10-2*margin`, R<=1 auto-miss,
       R>=18 auto-max, so a hopeless margin saturates at the 10% floor. No zero special-case (its only
       `jle -> return 0` guard @0x55725EB3 is on DAMAGE, not attack), no div-by-zero, no index.
  So an underflowed 0xFE reads back as -2, NOT 254 -- there is no "wraps to always-hits" bug, because
  that would need a MOVZX and there is none on this path. Hence: no floor clamp, matching Parry.
  (A floor would also have to be skipped at site 2 anyway -- see below -- making the three sites behave
  differently for weak attackers. Uniform and unclamped is both safer to reason about and truer to the
  engine. DO NOT port this to the damage slot: damage <= 0 hits a hard `test/jle -> 0` @0x55725EB3.)

ATTACK SLOT SEMANTICS -- differs per site; the site-2 difference is the subtle one:
  CreateStrikeCA        BL            = ABSOLUTE attack (combat vmt+0x6c), pushed to the CA Setup.
  CreateRangedAttackCA  entry [ESP]   = ABSOLUTE attack (vmt+0x114 minus the wall penalty). NOTE this
                                        is [ESP] at the HOOK; cave_rng's own `push edi/push eax` are why
                                        it reaches the same byte as [esp+8], and we as [esp+4].
  CalculateStrikes      dword [EBX]   = a signed DELTA accumulator; the base is fetched separately and
                                        the delta added (`movsx eax,al; add eax,[ebx]` @0x55767CC7),
                                        folded 8-bit in TMeleeRound.CreateStrikeCA @0x55767EBA.
  A floor clamp would be outright WRONG at site 2: clamping the delta would wipe out other bonuses
  (Monster Slaying etc.) instead of flooring the attack.

VISIBILITY -- the penalty is deliberately quiet, like the slayers it sits beside:
  * NOT on the unit info card: TStrikeAbility.GetCombatInfo @0x55766F60 reads base stats (unit vmt+0xC0
    GetAttack / +0xC8 GetDamage), never the strike.
  * NOT known to the AI: TStrikeAbility.GetOffensiveStrength @0x55766BAC reads the same base stats, so
    the AI will keep attacking invisible units at full confidence.
  * DOES show in the combat log -- its tail hook @0x5580E740/0x5580E758 does `movsx eax, byte [ebp+0x10]`
    already, so a reduced attack prints as e.g. `A-2`, not 253.
  * DOES show in the melee-round DV at site 2 only: that delta also feeds per-strike CV (record+0x08 via
    0x55726038), summed by TMeleeRound.CalculateDV @0x55767F58. Vanilla Parry behaves the same way.

STRATEGY -- this REWRITES THE THREE CAVE BODIES that build_trueseeing.py already owns, in place, at the
same addresses. The chain plumbing it installed is unchanged and reused:
      cave_melee  exit @0x5580E0D5 -> cave_ts_melee  @0x5580E370   (attacker=EBP target=ESI ATK=BL)
      cave_melee3 exit @0x5580E183 -> cave_ts_melee3 @0x5580E3B0   (attacker=ESI target=EDI ATK=[EBX])
      ranged hook      @0x5576EB34 -> cave_ts_rng    @0x5580E400   (attacker=ESI target=[EBP-4])
Only the three cave bodies are written. NOTE we do NOT revert .pre-trueseeing first: that backup predates
combatlog / tierresearch / leadership*, so restoring it would silently undo them. Verify-before-write
accepts either the v1 (bonus) or v2 (penalty) body and overwrites; the trailing free space each cave
grows into is asserted zero.

Caves are register/immediate + VMT-indirect + rel32 only => position-independent (the .dpl rebases).
Idempotent, verify-before-write, backup <game dir>\backups\AoWEPACK.dpl.pre-invispenalty, dry-run
by default / --apply.
REVERT: NOT by snapshot. Restoring a whole-file .pre-* wipes every feature applied after it, and
there is no snapshot layer at all now (both stacks were purged, 2026-08-08 and 2026-09-09).
Re-tune by editing the constants and re-applying -- this script rewrites its caves IN PLACE and
never needs a restore.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]; n = struct.unpack_from("<H", data, e+6)[0]
    op = struct.unpack_from("<H", data, e+20)[0]; s = e+24+op; secs = []
    for i in range(n):
        vs, va, rs, raw = struct.unpack_from("<IIII", data, s+8); secs.append((va, vs, raw, rs)); s += 40
    return secs
def mkva2off(base):
    def f(secs, va):
        rva = va-base
        for va0, vs, raw, rs in secs:
            if va0 <= rva < va0+max(vs, rs): return raw+(rva-va0)
        raise ValueError(hex(va))
    return f

DLL_BASE = 0x55700000
TRUE_VISION = 0x29        # attacker: "True Seeing" -- negates the penalty
INVISIBLE   = 0x36        # target:   "Invisibility" -- triggers the penalty
GAE         = 0xA8        # combat-object VMT slot: GetAbilityEnabled(edx=id) -> AL

# ---- tuning knobs -----------------------------------------------------------------------------
# Each point of attack is worth 10 percentage points of hit chance: to-hit = clamp(50+10*(atk-def),10,90).
# So -3 melee is -30pp (e.g. a 50% attack becomes 20%) -- deliberately large; -1/-2 are the softer picks.
# Weighted toward ranged to match vanilla's own detection model: TrueVisionRange @0x55780F80 returns 1
# for units WITHOUT the ability, so in vanilla every unit already spots invisibles at range 1 -- True
# Vision buys range, not detection. An adjacent (melee) attacker seeing you fine is therefore vanilla-
# consistent; the distant shooter is the one who should struggle.
# 5% CONVERSION (2026-08-18): both doubled. These are pure ATTACK penalties -- `sub bl`,
# `sub dword [ebx]` and `sub byte [esp+4]` all target the attack accumulator, never damage --
# so both scale with the stat doubling. Was 1 / 3.
MELEE_PENALTY  = 2   # 2026-08-24: 2 -> 1 -> 2 again (user). Vanilla 1, doubled to 2 by the
                     # 5% conversion; briefly re-graded to 1, then restored the same day.
RANGED_PENALTY = 5   # 2026-08-24 re-grade: was 6 (vanilla 3, doubled)
# No floor clamp -- see SIGNEDNESS above. If you ever want one, it belongs at the two ABSOLUTE sites
# only, as `sub <slot>, N / jns _done / mov <slot>, 0` (floor 0) -- never at site 2.
# -----------------------------------------------------------------------------------------------

# --- cave addresses (owned by build_trueseeing.py; bodies rewritten here) ---
CAVE_TS_MELEE  = 0x5580E370; MELEE_DEST  = 0x557666CF; MELEE_LIMIT  = 0x5580E3B0
CAVE_TS_MELEE3 = 0x5580E3B0; MELEE3_DEST = 0x55767C89; MELEE3_LIMIT = 0x5580E400
CAVE_TS_RNG    = 0x5580E400; RNG_CAVE    = 0x5580E190; RNG_LIMIT    = 0x5580E440  # 0x..E440 = combat-log worker

# --- chain points: must already point at our caves (build_trueseeing.py applied) ---
CHAIN = [
    (0x5580E0D5, CAVE_TS_MELEE,  "cave_melee exit"),
    (0x5580E183, CAVE_TS_MELEE3, "cave_melee3 exit"),
    (0x5576EB34, CAVE_TS_RNG,    "ranged hook"),
]

# cave_ts_melee: EBP=attacker, ESI=target, BL=ABSOLUTE attack. clobbers eax/ecx/edx (dest trashes them).
# Target-first ordering: most targets are not invisible, so the common path is one virtual call.
ts_melee_src = f"""
    mov  edx, 0x{INVISIBLE:X}
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _done
    mov  edx, 0x{TRUE_VISION:X}
    mov  eax, ebp
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jnz  _done
    sub  bl, {MELEE_PENALTY}
_done:
    jmp  0x{MELEE_DEST:X}
"""

# cave_ts_melee3: ESI=attacker, EDI=target, dword[EBX]=attack DELTA (base added later) -> NO floor clamp.
ts_melee3_src = f"""
    mov  edx, 0x{INVISIBLE:X}
    mov  eax, edi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _done
    mov  edx, 0x{TRUE_VISION:X}
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jnz  _done
    sub  dword ptr [ebx], {MELEE_PENALTY}
_done:
    jmp  0x{MELEE3_DEST:X}
"""

# cave_ts_rng: runs BEFORE cave_rng. Entry state (the ranged hook) = AL holds the damage that vanilla's
# stolen `push eax` is about to push; entry [ESP] = the ABSOLUTE attack (already pushed @0x5576EB1D).
# Only EAX must be preserved -- cave_rng clobbers ECX/EDX itself, so they are dead here. After the single
# push, the attack sits at [ESP+4].
ts_rng_src = f"""
    push eax
    mov  eax, [ebp-4]
    mov  edx, 0x{INVISIBLE:X}
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _skip
    mov  eax, esi
    mov  edx, 0x{TRUE_VISION:X}
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jnz  _skip
    sub  byte ptr [esp+4], {RANGED_PENALTY}
_skip:
    pop  eax
    jmp  0x{RNG_CAVE:X}
"""

ts_melee  = bytes(ks.asm(ts_melee_src,  CAVE_TS_MELEE)[0])
ts_melee3 = bytes(ks.asm(ts_melee3_src, CAVE_TS_MELEE3)[0])
ts_rng    = bytes(ks.asm(ts_rng_src,    CAVE_TS_RNG)[0])

# --- accept ANY previously-installed penalty value, not just the current one -------------------
# Re-tuning a constant used to wedge this script: the accept-list held the v1 True-Seeing body and the
# NEWLY generated body, but the INSTALLED body is ours with the OLD constant -- neither. Regenerate our
# body across the plausible penalty range so a re-tune always recognises its own previous output.
# (The 5% conversion hit this going 1->2 / 3->6.)
import re as _re
def _with_penalty(src_text, val):
    return _re.sub(r"(sub\s+(?:bl|dword ptr \[ebx\]|byte ptr \[esp\+4\]),\s*)\d+",
                   lambda m: m.group(1) + str(val), src_text)
def _variants(src_text, va, lo=1, hi=12):
    out = []
    for v in range(lo, hi + 1):
        try: out.append(bytes(ks.asm(_with_penalty(src_text, v), va)[0]))
        except Exception: pass
    return out
OURS = {CAVE_TS_MELEE:  _variants(ts_melee_src,  CAVE_TS_MELEE),
        CAVE_TS_MELEE3: _variants(ts_melee3_src, CAVE_TS_MELEE3),
        CAVE_TS_RNG:    _variants(ts_rng_src,    CAVE_TS_RNG)}

CAVES = [("ts_melee",  CAVE_TS_MELEE,  ts_melee,  MELEE_LIMIT,  "-%d melee ATK vs invisible (round/opportunity)" % MELEE_PENALTY),
         ("ts_melee3", CAVE_TS_MELEE3, ts_melee3, MELEE3_LIMIT, "-%d melee ATK vs invisible (deliberate/retal)" % MELEE_PENALTY),
         ("ts_rng",    CAVE_TS_RNG,    ts_rng,    RNG_LIMIT,    "-%d ranged ATK vs invisible" % RANGED_PENALTY)]

# v1 (build_trueseeing.py) bodies -- the other state we accept at the cave sites and overwrite.
# Re-assembled from v1's own source rather than pasted as hex, so the fingerprints cannot be mistyped:
# ids swapped (attacker 0x29 first, target 0x36 second) and the branch polarity `jz` throughout.
# The three sources below are build_trueseeing.py's cave bodies verbatim (ids in the other order,
# `jz` polarity, no floor, and -- in the ranged one -- two needless pushes of ecx/edx, which is why its
# attack slot is [esp+0xc] where ours is [esp+4]).
_v1_melee = f"""
    mov  edx, 0x{TRUE_VISION:X}
    mov  eax, ebp
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _done
    mov  edx, 0x{INVISIBLE:X}
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _done
    add  bl, 3
_done:
    jmp  0x{MELEE_DEST:X}
"""
_v1_melee3 = f"""
    mov  edx, 0x{TRUE_VISION:X}
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _done
    mov  edx, 0x{INVISIBLE:X}
    mov  eax, edi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _done
    add  dword ptr [ebx], 3
_done:
    jmp  0x{MELEE3_DEST:X}
"""
_v1_rng = f"""
    push eax
    push ecx
    push edx
    mov  edx, 0x{TRUE_VISION:X}
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _skip
    mov  eax, [ebp-4]
    mov  edx, 0x{INVISIBLE:X}
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _skip
    add  byte ptr [esp+0xc], 1
_skip:
    pop  edx
    pop  ecx
    pop  eax
    jmp  0x{RNG_CAVE:X}
"""
V1 = {CAVE_TS_MELEE:  bytes(ks.asm(_v1_melee,  CAVE_TS_MELEE)[0]),
      CAVE_TS_MELEE3: bytes(ks.asm(_v1_melee3, CAVE_TS_MELEE3)[0]),
      CAVE_TS_RNG:    bytes(ks.asm(_v1_rng,    CAVE_TS_RNG)[0])}

def preserve_terminator(gen, cave_va, live, stock_dest, quiet=False):
    """Return `gen` with its trailing jmp retargeted to whatever the INSTALLED body jumps to.

    ⚠ Why this is required, not a nicety: every cave here ends `jmp <stock exit>`, but
    build_magebane.py splices itself into that exit (ts_melee now jumps to 0x558129C0, ts_melee3 to
    0x55812A00). The accept-list regenerates our body with the STOCK exit, so no variant could ever
    match the installed bytes and this script reported a FALSE `[x]` -- "holds neither the v1
    True-Seeing body nor ours" -- while the bytes were perfectly fine. Same fix, same shape, as
    build_assassin.py. A verifier that cries wolf is a defect.
    """
    if len(live) < len(gen):
        return gen
    off = len(gen) - 5
    if off < 0 or gen[off] != 0xE9 or live[off] != 0xE9:
        return gen                                  # not the shape we expect -- leave it alone
    live_t = cave_va + off + 5 + struct.unpack_from("<i", live, off + 1)[0]
    if live_t == stock_dest:
        return gen                                  # still stock: nothing chained onto us
    if not quiet:
        print("[chain] %08X exit kept at %08X (stock is %08X) -- a downstream cave is spliced in"
              % (cave_va, live_t, stock_dest))
    return gen[:off + 1] + struct.pack("<i", live_t - (cave_va + off + 5)) + gen[off + 5:]


APPLY = "--apply" in sys.argv
def process(path, base, suffix=".pre-invispenalty"):
    data = bytearray(open(path, "rb").read()); secs = load_sections(data); va2off = mkva2off(base)
    def rd(va, n): o = va2off(secs, va); return bytes(data[o:o+n])

    # Keep whatever exit is installed (see preserve_terminator). Must be applied to the bodies we
    # are about to write AND to every accept-variant, or a chained cave never matches.
    global ts_melee, ts_melee3, ts_rng, CAVES, OURS
    _dest = {CAVE_TS_MELEE: MELEE_DEST, CAVE_TS_MELEE3: MELEE3_DEST, CAVE_TS_RNG: RNG_CAVE}
    _live = {cva: rd(cva, max(len(cb), len(V1[cva]))) for _l, cva, cb, _lim, _d in CAVES}
    ts_melee  = preserve_terminator(ts_melee,  CAVE_TS_MELEE,  _live[CAVE_TS_MELEE],  MELEE_DEST)
    ts_melee3 = preserve_terminator(ts_melee3, CAVE_TS_MELEE3, _live[CAVE_TS_MELEE3], MELEE3_DEST)
    ts_rng    = preserve_terminator(ts_rng,    CAVE_TS_RNG,    _live[CAVE_TS_RNG],    RNG_CAVE)
    OURS = {cva: [preserve_terminator(v, cva, _live[cva], _dest[cva], True) for v in vs]
            for cva, vs in OURS.items()}
    CAVES = [(l, cva, {CAVE_TS_MELEE: ts_melee, CAVE_TS_MELEE3: ts_melee3,
                       CAVE_TS_RNG: ts_rng}[cva], lim, d)
             for l, cva, _cb, lim, d in CAVES]

    print(f"[cfg] melee -{MELEE_PENALTY} ATK / ranged -{RANGED_PENALTY} ATK vs Invisibility 0x{INVISIBLE:02X}, "
          f"negated by True Vision 0x{TRUE_VISION:02X}; unclamped (signed, like vanilla Parry)\n")
    for label, cva, cbytes, limit, desc in CAVES:
        print(f"[{label}] @ {cva:08X} ({len(cbytes)} B, room {limit-cva} B) -- {desc}")
        for ins in cs.disasm(cbytes, cva):
            print(f"  {ins.address:08X} {ins.bytes.hex(' '):<22}{ins.mnemonic} {ins.op_str}")
        print()

    # size guard
    for label, cva, cbytes, limit, _d in CAVES:
        if cva+len(cbytes) > limit:
            print(f"[x] {label} overflows its zone: needs {len(cbytes)} B, room {limit-cva} B"); return False

    # dependency + free-space guard: each cave site must hold the v1 body or ours, and any bytes we grow
    # into beyond the longer of the two must be zero.
    for label, cva, cbytes, limit, _d in CAVES:
        v1 = V1[cva]; span = max(len(cbytes), len(v1)); live = rd(cva, span)
        _ours = OURS[cva]
        if live[:len(v1)] != v1 and not any(live[:len(o)] == o for o in _ours):
            print(f"[x] {label} @ {cva:08X} holds neither the v1 True-Seeing body nor ours -- is "
                  f"build_trueseeing.py applied?\n     got {live[:len(v1)].hex(' ')}"); return False
        if not any(live[:len(o)] == o for o in _ours) and any(b != 0 for b in rd(cva+len(v1), max(0, len(cbytes)-len(v1)))):
            print(f"[x] {label} cannot grow: bytes after the v1 body are not free"); return False

    # the v1 chain plumbing must still route into our caves
    for va, dest, desc in CHAIN:
        want = b"\xE9"+struct.pack("<i", dest-(va+5))
        if rd(va, 5) != want:
            print(f"[x] {desc} @ {va:08X} does not jump to {dest:08X} -- build_trueseeing.py not applied?"
                  f"\n     exp {want.hex(' ')}\n     got {rd(va,5).hex(' ')}"); return False

    if all(rd(cva, len(cb)) == cb for _l, cva, cb, _lim, _d in CAVES):
        print("[= ] already applied"); return True
    if not APPLY:
        print("[dry] caves assemble and fit, chain plumbing verified, v1 bodies present"); return True
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bp = os.path.join(BACKUP_DIR, os.path.basename(path)+suffix)
    if not os.path.exists(bp): shutil.copy2(path, bp); print(f"[bak] {bp}")
    for label, cva, cbytes, _lim, desc in CAVES:
        o = va2off(secs, cva)
        pad = max(0, len(V1[cva])-len(cbytes))            # blank any v1 tail we did not overwrite
        data[o:o+len(cbytes)+pad] = cbytes + b"\x00"*pad
        print(f"[w ] {cva:08X} {label:<10} {desc}")
    try: open(path, "wb").write(data)
    except PermissionError: print("[x] LOCKED -- close AoW binaries"); return False
    return True

print()
ok = process(os.path.join(GAME, "AoWEPACK.dpl"), DLL_BASE)
print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first." if not APPLY
      else ("\n[done] Applied. Re-tune in place (this script rewrites its own caves); a .pre-* "
            "restore is not a revert path." if ok else "\n[!] not applied"))
