#!/usr/bin/env python3
r"""
AoW1 mod -- Turn Undead damage = (ability level) x (caster's RES), instead of the vanilla flat
level table.

VANILLA (TTurnUndeadAbility, AoWEPACK.dpl):
  The touch-attack's ATK and DAM are pure functions of the ability LEVEL (1..4):
    GetTouchAttack       @0x5576B1F4 : level 1->9  2->10 3->11 4->12
    GetTurnUndeadDamage  @0x5576B214 : level 1->4  2->8  3->12 4->16      (== level*4)
  The damage actually DEALT in combat is baked by CreateTurnUndeadCA @0x5576B528:
    ...
    5576B56C  call [attacker.vmt+0xb0]      ; GetAbilityLevel  -> level  (attacker = ESI)
    5576B57C  call [this.vmt+0x10c]         ; GetTouchAttack(level) -> CA attack   (LEFT UNCHANGED)
    5576B589  call 0x5576B214              ; GetTurnUndeadDamage(level) -> CA damage  <-- WE REPOINT THIS
    ...
    -> TDamageCA.GenerateEx (@0x55729C98) reads the CA damage as `movsx ecx, byte[ebp+0x10]`
       (a SIGNED byte), so the damage rating must stay in 0..127 or it flips negative. We clamp.

  At the 0x5576B589 call site the registers are:
    EDX = level (1..4)   ESI = attacker COMBAT object (the unit using the ability)   EAX = this(ability)
  and the caller needs ESI/EDI/EBP/EBX preserved afterwards (it does mov edx,esi / mov ecx,ebp / ...).

CHANGE:
  Repoint the 5-byte `call GetTurnUndeadDamage` @0x5576B589 to a small position-independent cave that
  returns  al = clamp( round(0.5 * level * casterRES), 0x7F ),  implemented as (level*RES + 1) >> 1.
  casterRES = ESI.GetResistance() via combat VMT+0x74 (TCombatUnit.GetResistance -> forwards to the
  strategic unit's GetResistance; takes no args; -> AL). Rounding is half-up; RES 0 -> 0 damage.

  ATK is deliberately NOT touched (still the level table 9..12), matching the request ("change its
  damage"). This affects the damage actually dealt in tactical AND auto/fast combat (both execute the
  real TTurnUndeadCA). It does NOT touch the two other GetTurnUndeadDamage callers:
    - GetCombatInfo @0x5576B257   (the ability's info-card ATK/DAM -- still shows the old level*4 number)
    - GetOffensiveStrength @0x5576AEDA (AI strength heuristic -- damage there is already capped at 5)
  nor the separate GetDamageValueEx/predictor preview path.

PART 2 -- DISPLAY SYNC (GetCombatInfo @0x5576B234): make the ability info-card's DAM match the dealt
damage. Problem: at its `call GetTurnUndeadDamage` @0x5576B257 the OWNER is no longer in a register
(passed in EDX, consumed by GetLevel). Solution: replace GetCombatInfo wholesale -- a 5-byte `jmp` at
its entry redirects to cave_combatinfo, which keeps the owner in EBP throughout and computes:
    attack = GetTouchAttack(level)                                  (unchanged, level table 9..12)
    damage = clamp((level * owner.GetResistance() + 1) >> 1, 0x7F)  (owner RES via strat VMT+0xcc; 0 if nil)
then writes the same TCombatInfo struct as vanilla (the two data constants word 0x0040 @0x5576B278 and
byte 0x02 @0x5576B27C are embedded, so the cave needs no absolute data reads). The tail of the original
function (from 0x5576B239) becomes dead code. owner.GetResistance (strat VMT+0xcc) yields the same value
as the combat path's ESI.GetResistance (combat VMT+0x74 forwards to it), so display == damage dealt.

Both caves are register/immediate-only + register-indirect virtual calls => position-independent (safe for
the DPL runtime rebase). Idempotent, verify-before-write, free-space asserted, dry-run by default /
--apply. Snapshot goes to `<game dir>\backups\AoWEPACK.dpl.pre-turnundead`.

Revert: there is no --undo flag here. Undo by hand -- restore each hook site's ORIG bytes and zero
both caves. A `.pre-*` restore is NOT a revert path: it is a whole-file copy that drops every feature
applied since, and there is no snapshot layer left at all.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never the game root (rule 2026-09-03)
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
def rel32(src, dst): return struct.pack("<i", dst-(src+5))

DLL_BASE  = 0x55700000
HOOK      = 0x5576B589                       # the `call GetTurnUndeadDamage` inside CreateTurnUndeadCA
HOOK_ORIG = bytes.fromhex("e886fcffff")      # call 0x5576B214 (rel -890)
CAVE      = 0x5580E2A0                        # free zeroed cave zone (just past the slayer cave_rng @..E287)
RES_VMT   = 0x74                              # combat-object VMT slot: GetResistance (no args -> AL)
DMG_CLAMP = 0x7F                              # signed-byte max (GenerateEx reads damage as movsx byte)
# 5% CONVERSION (2026-08-18): RESISTANCE is doubled game-wide, and this formula MULTIPLIES by it --
# it is not a doubling-invariant difference, so leaving it alone would double Turn Undead's damage
# output.  Compensate in the divisor: damage = round(0.5 * level * RES_original)
#   before:  (level * R      + 1) >> 1
#   after:   (level * 2R     + 2) >> 2      <- same result, RES now arriving pre-doubled
DMG_ROUND = 2                                 # rounding addend (was 1)
DMG_SHIFT = 2                                 # right shift    (was 1)
# DAM/HP DOUBLING (2026-08-24, decision D5 in Zig notes/DamHP_Double_Decisions.md): every damage
# source doubles.  Exact x2 with no rounding drift = keep (x+2)>>2 and DOUBLE THE RESULT:
#   damage = ((level * RES + 2) >> 2) * 2  == 2 * round(0.5 * level * RES_original)
# DMG_SCALE 1 = off (pre-doubling), 2 = append `add eax, eax` after the shr in BOTH caves.
DMG_SCALE = 2
_SCALE_LINE = "add  eax, eax" if DMG_SCALE == 2 else ""
# (max output: 4 * 20 -> (80+2)>>2 = 20, *2 = 40 -- comfortably under the 0x7F clamp)
# formula: DAM = clamp( round(0.5 * level * RES), 0x7F ) = clamp( (level*RES + 1) >> 1, 0x7F )

# cave_turnundead_dmg:
#   in : EDX=level(1..4)  ESI=attacker combat obj (caster)   [EAX=this ability, unused]
#   out: AL = clamp( (level * casterRES + 1) >> 1, 0x7F )   == round(0.5 * level * RES)
#   preserves ESI (and EDI/EBP/EBX untouched); clobbers EAX(ret)/ECX/EDX (caller reloads EDX/ECX).
cave_src = f"""
    push esi
    push edx
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x{RES_VMT:X}]
    movzx eax, al
    pop  edx
    movzx edx, dl
    imul eax, edx
    add  eax, {DMG_ROUND}
    shr  eax, {DMG_SHIFT}
    {_SCALE_LINE}
    cmp  eax, 0x{DMG_CLAMP:X}
    jle  _done
    mov  eax, 0x{DMG_CLAMP:X}
_done:
    pop  esi
    ret
"""
cave = bytes(ks.asm(cave_src, CAVE)[0])

# ---- PART 2: display sync (replace GetCombatInfo wholesale) ----
INFO_HOOK = 0x5576B234                         # GetCombatInfo entry
INFO_ORIG = bytes.fromhex("53 56 57 8b d9".replace(" ", ""))  # push ebx;push esi;push edi;mov ebx,ecx
CAVE2     = 0x5580E300                          # past the (now larger) combat cave @0x5580E2A0
RES_STRAT = 0xCC                                # strategic-unit VMT slot: GetResistance
INFO_TYPEWORD = 0x0040                          # word const written @ struct+3 (was [0x5576B278])
INFO_BYTE0    = 0x02                            # byte const written @ struct+0 (was [0x5576B27C])

# cave_combatinfo: full reimpl of GetCombatInfo(eax=this, edx=owner, ecx=outbuf).
#   ebx=outbuf  esi=this  ebp=owner(kept)  edi=level. Struct: +0=byte,+1=atk,+2=dmg,+3=typeword,+5=1.
cave2_src = f"""
    push ebx
    push esi
    push edi
    push ebp
    mov  ebx, ecx
    mov  esi, eax
    mov  ebp, edx
    mov  edx, ebp
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x70]
    mov  edi, eax
    mov  edx, edi
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x10c]
    mov  [ebx+1], al
    test ebp, ebp
    jz   _dmg0
    mov  eax, ebp
    mov  edx, [eax]
    call dword ptr [edx+0x{RES_STRAT:X}]
    movzx eax, al
    mov  edx, edi
    imul eax, edx
    add  eax, {DMG_ROUND}
    shr  eax, {DMG_SHIFT}
    {_SCALE_LINE}
    cmp  eax, 0x{DMG_CLAMP:X}
    jle  _dmgset
    mov  eax, 0x{DMG_CLAMP:X}
    jmp  _dmgset
_dmg0:
    xor  eax, eax
_dmgset:
    mov  [ebx+2], al
    mov  ax, 0x{INFO_TYPEWORD:X}
    mov  [ebx+3], ax
    mov  byte ptr [ebx+5], 1
    mov  al, 0x{INFO_BYTE0:X}
    mov  [ebx], al
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""
cave2 = bytes(ks.asm(cave2_src, CAVE2)[0])

# --- in-place re-tune: accept our OWN previously-installed body -------------------------------
# The free-space guard below only accepted a ZERO zone or the exact body about to be written.
# Re-tuning the formula produces a third state -- our body with the OLD round/shift -- which the
# guard reported as "cave zone not free", refusing to write.  CLAUDE.md's rule is to verify against
# EITHER the installed bytes OR the new ones.  (The 5% conversion hit this going (1,1) -> (2,2).)
import re as _re
def _with_formula(src_text, rnd, sh, scaled):
    t = _re.sub(r"(add\s+eax,\s*)\d+", lambda m: m.group(1) + str(rnd), src_text)
    t = _re.sub(r"(shr\s+eax,\s*)\d+", lambda m: m.group(1) + str(sh),  t)
    # normalise the x2 scale line away entirely (historical bodies had NO line there, not a nop),
    # then re-insert it after the shr for scaled variants
    t = _re.sub(r"[ \t]*(add\s+eax,\s*eax|nop)[ \t]*\n", "", t)
    if scaled:
        t = _re.sub(r"(shr\s+eax,\s*\d+\n)", lambda m: m.group(1) + "    add  eax, eax\n", t)
    return t
def _variants(src_text, va):
    out = []
    for rnd in (1, 2, 4, 8):
        for sh in (1, 2, 3):
            for scaled in (False, True):
                try: out.append(bytes(ks.asm(_with_formula(src_text, rnd, sh, scaled), va)[0]))
                except Exception: pass
    return out
CAVE_VARIANTS = {CAVE: _variants(cave_src, CAVE), CAVE2: _variants(cave2_src, CAVE2)}


APPLY = "--apply" in sys.argv
def process(path, base, suffix=".pre-turnundead"):
    data = bytearray(open(path, "rb").read()); secs = load_sections(data); va2off = mkva2off(base)
    def rd(va, n): o = va2off(secs, va); return bytes(data[o:o+n])

    new_call  = b"\xE8" + rel32(HOOK, CAVE)
    info_jmp  = b"\xE9" + rel32(INFO_HOOK, CAVE2)
    patches = [
        (CAVE,  bytes(len(cave)),  cave,  "cave_turnundead_dmg (combat: level * casterRES, clamped)"),
        (HOOK,  HOOK_ORIG, new_call, f"CreateTurnUndeadCA {HOOK:08X}: call GetTurnUndeadDamage -> cave"),
        (CAVE2, bytes(len(cave2)), cave2, "cave_combatinfo (display: info-card DAM = level * ownerRES)"),
        (INFO_HOOK, INFO_ORIG, info_jmp, f"GetCombatInfo {INFO_HOOK:08X}: entry jmp -> cave_combatinfo"),
    ]

    print(f"[part1] cave @ {CAVE:08X} ({len(cave)} B); hook @ {HOOK:08X} (call->cave, rel {rel32(HOOK,CAVE).hex()})")
    for ins in cs.disasm(cave, CAVE):
        print(f"  {ins.address:08X} {ins.bytes.hex(' '):<22}{ins.mnemonic} {ins.op_str}")
    print(f"[part2] cave @ {CAVE2:08X} ({len(cave2)} B); hook @ {INFO_HOOK:08X} (jmp->cave2, rel {rel32(INFO_HOOK,CAVE2).hex()})")
    for ins in cs.disasm(cave2, CAVE2):
        print(f"  {ins.address:08X} {ins.bytes.hex(' '):<22}{ins.mnemonic} {ins.op_str}")

    # free-space guard: never overwrite live bytes (both cave zones)
    for cva, cbytes in ((CAVE, cave), (CAVE2, cave2)):
        live = rd(cva, len(cbytes))
        # A re-tune can CHANGE THE BODY LENGTH (shr eax,1 is 2 bytes, shr eax,2 is 3), so compare
        # our variants by PREFIX and separately assert the bytes we grow into are still zero.
        _ours = [v for v in CAVE_VARIANTS.get(cva, []) if live[:len(v)] == v]
        if live != cbytes and any(b != 0 for b in live) and not _ours:
            print(f"[x] cave zone {cva:08X} not free:\n     {live.hex(' ')}"); return False
        if _ours and len(cbytes) > len(_ours[0]):
            grow = rd(cva + len(_ours[0]), len(cbytes) - len(_ours[0]))
            if any(b != 0 for b in grow):
                print("[x] cave %08X cannot grow %d B: bytes after our old body are not free"
                      % (cva, len(cbytes) - len(_ours[0]))); return False
    if all(rd(va, len(new)) == new for va, _o, new, _d in patches):
        print("[= ] already applied"); return True
    ok = True
    for va, orig, new, desc in patches:
        cur = rd(va, len(new))
        # accept our own previously-installed cave body too (prefix, since a re-tune may change
        # its length) -- otherwise the script cannot re-tune itself.  See CAVE_VARIANTS above.
        _mine = any(cur[:len(v)] == v for v in CAVE_VARIANTS.get(va, []))
        if cur != orig and cur != new and not _mine:
            ok = False
            print("[!] %08X (%s)" % (va, desc))
            print("     exp " + orig.hex(" "))
            print("     got " + cur.hex(" "))
    if not ok: print("[x] mismatch -- not written"); return False
    if not APPLY: print("[dry] originals verified, cave zone free"); return True
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bp = os.path.join(BACKUP_DIR, os.path.basename(path)+suffix)
    if not os.path.exists(bp): shutil.copy2(path, bp); print(f"[bak] {bp}")
    for va, orig, new, desc in patches:
        o = va2off(secs, va); data[o:o+len(new)] = new; print(f"[w ] {va:08X} {desc}")
    try: open(path, "wb").write(data)
    except PermissionError: print("[x] LOCKED -- close AoW binaries (AoW.exe/AoWCompat.exe/AoWDevEd.exe)"); return False
    return True

print()
ok = process(os.path.join(GAME, "AoWEPACK.dpl"), DLL_BASE)
print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first." if not APPLY
      else ("\n[done] Applied. Revert: no --undo here -- restore the ORIG hook byte-runs and zero both"
            "\n       caves by hand. A .pre-* restore is not a revert path." if ok else "\n[!] not applied"))
