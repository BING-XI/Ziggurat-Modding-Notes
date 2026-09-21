#!/usr/bin/env python3
r"""
AoW1 mod -- Leadership becomes a real 4-level ability (Leadership I / II / III / IV).

VANILLA
  Leadership (id 0x2e) is `TLeadershipAbility : TMultiLevelAbility : TAbility` -- it already sits on
  the engine's multi-level framework (CanExpand / Expand / ExpandCost / GetSkillPoints, a per-level
  cost TIntegerList, and a per-owner data record whose +0x0c byte is the level). Three things keep it
  at one level:

    1. `TLeadershipAbility.Create` @0x5576616C calls the base ctor (which sets the cap [+0x28] = 4)
       and then immediately STOMPS it back to 1:
           55766187  mov dword [esi+0x28], 1      <-- the entire single-level cap
    2. The same ctor populates only cost index 1:
           55766195  mov ecx,0x14 / mov edx,1 / mov eax,[esi+0x2c] / call TIntegerList.Put
       so levels 2..4 have no defined skill-point cost.
    3. `TLeadershipAbility.GetLevelName` @0x557663D0 IGNORES its level argument and always returns the
       bare "Leadership" resource string, so higher levels would display no numeral.

  The cap is honoured everywhere via [+0x28]: CanExpand @0x557663A8 is `own < cap`; Expand increments
  up to the cap; ExpandCost reads cost[level+1]; GetSkillPoints sums cost[1..level].

CHANGE (4 levels, user-chosen curve and costs)
  Bonuses per level:  I +1/+1   II +2/+2   III +3/+3   IV +4/+4   (attack/defense)
  Skill cost per level: 10 flat each (10 / 10 / 10 / 10; 40 total to reach IV)
    -- TRUE VANILLA cost[1] = 10 (byte-checked in the root vanilla DLL 2026-09-10). The 20 this file
       used to claim as vanilla is an EARLIER, UNRECORDED Ziggurat edit of the now-dead ctor
       immediate at 0x55766195, made before the 4-level work. No build script claims that byte.

  NOTE these are RAW values on the post-5%-conversion doubled stat scale, where one point buys 5 pp
  of hit chance -- so the curve is a flat +5/+10/+15/+20 pp ramp. Owner's ruling 2026-09-10: vanilla
  Leadership was +1/+0 and the mod is +1/+1 .. +4/+4, so level II already matches vanilla's attack
  bonus and level I already exceeds its defence bonus.  Leadership is a D2 exception (NOT doubled by build_statdouble.py),
  so this table is the ONLY place its strength is set.
  Existing level-1 leaders therefore get weaker; the ceiling rises to +4/+4.

  Four patches + two caves:

  A. CAP  @0x5576618A : imm32 of `mov [esi+0x28],1`  ->  4.
  B. COSTS @0x557661A2: repoint the single `call TIntegerList.Put` to `cave_lscosts`, which performs
     Put(list, 1..MAX_LEVEL, COST_EACH). Without this, ExpandCost/GetSkillPoints read undefined
     indices for 2..4.
  C. BONUS TABLES: vanilla `GetAttack` @0x557661FC / `GetDefense` @0x55766210 do
         mov al, byte ptr [eax + 0x558E83E7]     (attack,  eax = level)
         mov al, byte ptr [eax + 0x558E83EB]     (defense)
     i.e. two 4-byte tables packed BACK TO BACK -- attack[4] would read defense[0]. (Vanilla data is
     ⚠ VANILLA LEADERSHIP WAS +1 ATK / +0 DEF, ONE LEVEL. Nothing else. Vanilla's
     MAX_LEVEL is 1 (`mov [esi+0x28],1` at 0x55766187, which this script raises to 4), so
     CanExpand never permitted level 2+ and only index 1 of each table was ever read.
     The raw bytes do continue -- attack [_,1,1,2] / defense [_,0,1,1] in the ROOT vanilla DLL --
     but indices 2..4 are DEAD DATA that never executed; do not quote them as a vanilla ramp.
     The [_,2,2,2]/[_,1,1,1] this comment once called vanilla are neither: they are the LIVE
     bytes, recorded from an already-patched file. Index 0 is never read either -- both getters
     early-return 0 when level==0.) We relocate BOTH tables into the cave block as 5-byte tables and repoint the two
     disp32 fields. Those two displacements each carry a .reloc entry (verified), so the loader keeps
     fixing them up after the rebase -- we only change the value, never remove the relocation.
  D. LEVEL NAMES: repoint the TLeadershipAbility VMT slot +0x10c (@0x55722114, the ONLY reference to
     GetLevelName -- verified by xref) to `cave_lsname`. That cave calls the ORIGINAL GetLevelName to
     produce the translated "Leadership", then appends " I"/" II"/" III"/" IV" with System.@LStrCat3,
     exactly mirroring how `TMarksmanshipAbility.GetLevelName` @0x557BBDEC and TVisionAbility do it.
     It REUSES the game's own suffix literals (Marksmanship's, refcount -1 constants at 0x557BBF18 /
     BF24 / BF30 / BF40 = " I" " II" " III" " IV") rather than fabricating new Delphi strings.
     `TMultiLevelAbility.GetName` calls vmt+0x10c with the CURRENT level and `ExpandName` calls it with
     level+1, so both the unit card and the hero level-up dialog pick this up for free.

POSITION INDEPENDENCE
  The .dpl rebases at runtime, so caves must not contain un-relocated absolute references. cave_lscosts
  is rel32-only. cave_lsname needs the address of the suffix-pointer table and of the literals, so it
  computes the LOAD DELTA with the standard call/pop trick (`call _n; pop ebp; sub ebp, <link addr of
  _n>`) and indexes `[ebp + idx*4 + SUF_TAB]`; the stored dwords are link-time VAs to which the same
  delta is added. All calls out (original GetLevelName, LStrCat3/LStrAsg/LStrClr, TIntegerList.Put) are
  rel32.

LAYERING / RE-TUNING
  Patch addresses and cave block are disjoint from build_leadership_fix.py and
  build_leadership_aura.py, so the three are functionally independent.

  ** TO RE-TUNE THE CURVE OR COSTS: just edit ATK_BONUS / DEF_BONUS / COST_EACH and re-run with
  --apply. NEVER revert first. ** The script rewrites its caves in place: the 16-byte suffix-VA block
  at DATA_TAB+0x10 is its own signature, so when that matches, the curve bytes in front of it are ours
  to overwrite whatever they hold. It prints `[~ ] ... re-tuning in place` with the old -> new curve,
  asserts the blob length is unchanged and that the 8 bytes past it are still zero, and takes a
  `<game dir>\backups\AoWEPACK.dpl.pre-leadership4` snapshot if none exists yet.

  ⚠ The .pre-leadership4 snapshot is NOT a usable revert path and never was a re-tune route: it is a
  WHOLE-FILE copy of a DLL that carries every other AoWEPACK feature, so restoring it silently
  destroys every one applied since. In-place rewriting is the only supported route. This script still
  lacks a true --undo (restore the 5 hook sites, zero the three cave zones); adding one is the right
  fix if a rollback is ever actually needed.

Idempotent, verify-before-write, free-space asserted, dry-run by default / --apply.
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

DLL_BASE = 0x55700000

# ---- vanilla addresses ----
CAP_SITE   = 0x55766187          # mov dword [esi+0x28], 1     (7 B: C7 46 28 01 00 00 00)
PUT_CALL   = 0x557661A2          # call TIntegerList.Put
PUT_FN     = 0x55702EB4          # EngineP.dpl!Engine.TIntegerList.Put  (EAX=list, EDX=idx, ECX=val)
ATK_DISP   = 0x55766207          # disp32 inside GetAttack   `mov al,[eax+0x558E83E7]`
DEF_DISP   = 0x5576621B          # disp32 inside GetDefense  `mov al,[eax+0x558E83EB]`
ATK_VAN    = 0x558E83E7
DEF_VAN    = 0x558E83EB
VMT_SLOT   = 0x55722114          # TLeadershipAbility VMT +0x10c (GetLevelName); vmt base 0x55722008
ORIG_NAME  = 0x557663D0          # TLeadershipAbility.GetLevelName
LSTRCAT3   = 0x55701190          # System.@LStrCat3  (EAX=dest, EDX=s1, ECX=s2)
LSTRASG    = 0x55701150          # System.@LStrAsg   (EAX=&dest, EDX=src)
LSTRCLR    = 0x55701140          # System.@LStrClr   (EAX=&str)
# the game's own " I" / " II" / " III" / " IV" literals (Marksmanship's; refcount -1 constants)
SUFFIX_VAS = (0x557BBF18, 0x557BBF24, 0x557BBF30, 0x557BBF40)

# ---- cave block (free zeroed run starts 0x5580EFBB, len 0xD895D -- verified by scan) ----
CAVE_COSTS = 0x5580EFC0
CAVE_NAME  = 0x5580F000
DATA_TAB   = 0x5580F0C0
ATK_TAB    = DATA_TAB + 0x00     # 5 bytes, index = level 0..4
DEF_TAB    = DATA_TAB + 0x08
SUF_TAB    = DATA_TAB + 0x10     # 4 dwords, link-time VAs of the suffix literals

# ---- user-chosen curve / cost ----
ATK_BONUS = (0, 1, 2, 3, 4)      # level 0 (unused; getters early-return), 1, 2, 3, 4
DEF_BONUS = (0, 1, 2, 3, 4)
# 2026-08-20 re-tune (user): was ATK (0,1,1,2,2) / DEF (0,0,1,1,2).  Leadership is a D2 exception in
# the 5% conversion -- it was deliberately NOT doubled -- so these are RAW table values on the new
# doubled stat scale, where one point buys 5 pp of hit chance.  The new curve is a flat ramp of
# +5/+10/+15/+20 pp per level for BOTH stats. Vanilla was a SINGLE level at +1 ATK / +0 DEF, so
# level II already matches its attack bonus and level I already exceeds its defence bonus -- the
# mod is strictly stronger at every level, not a re-expression of the same power.
MAX_LEVEL = 4
COST_EACH = 0x0A                 # 10 skill points per level, flat (user re-tune 2026-07-20, was 20)

# ---------------------------------------------------------------- cave_lscosts
# Entry from the ctor with EAX = the cost TIntegerList (EDX/ECX already set for the vanilla single
# Put, both re-set here). Writes cost[1..MAX_LEVEL] = COST_EACH. Preserves nothing the ctor needs
# beyond ESI/EBX (which it restores); the ctor only reads ESI/EBX afterwards.
costs_src = f"""
    push ebx
    push esi
    mov  ebx, eax
    mov  esi, 1
_loop:
    mov  eax, ebx
    mov  edx, esi
    mov  ecx, 0x{COST_EACH:X}
    call 0x{PUT_FN:X}
    inc  esi
    cmp  esi, {MAX_LEVEL}
    jle  _loop
    pop  esi
    pop  ebx
    ret
"""
cave_costs = bytes(ks.asm(costs_src, CAVE_COSTS)[0])

# ---------------------------------------------------------------- cave_lsname
# Replaces TLeadershipAbility.GetLevelName via the VMT.  (EAX=self, EDX=level, ECX=out:PAnsiString)
# tmp := original(self, level)            -> the translated "Leadership"
# if 1 <= level <= 4:  out := tmp + suffix[level-1]      else: out := tmp
# EBP holds the load delta for the whole body.
_pro_src = """
    push ebx
    push esi
    push edi
    push ebp
    mov  edi, ecx
    mov  esi, edx
    mov  ebx, eax
"""
_pro = bytes(ks.asm(_pro_src, CAVE_NAME)[0])
LINK_N = CAVE_NAME + len(_pro) + 5          # link-time address of the `pop ebp` (call/pop anchor)

name_src = _pro_src + f"""
    call _n
_n:
    pop  ebp
    sub  ebp, 0x{LINK_N:X}
    push 0
    mov  ecx, esp
    mov  edx, esi
    mov  eax, ebx
    call 0x{ORIG_NAME:X}
    cmp  esi, 1
    jl   _plain
    cmp  esi, {MAX_LEVEL}
    jg   _plain
    lea  edx, [esi-1]
    mov  ecx, [ebp + edx*4 + 0x{SUF_TAB:X}]
    add  ecx, ebp
    mov  edx, [esp]
    mov  eax, edi
    call 0x{LSTRCAT3:X}
    jmp  _done
_plain:
    mov  eax, edi
    mov  edx, [esp]
    call 0x{LSTRASG:X}
_done:
    mov  eax, esp
    call 0x{LSTRCLR:X}
    add  esp, 4
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""
cave_name = bytes(ks.asm(name_src, CAVE_NAME)[0])
assert cave_name[len(_pro)+5] == 0x5D, "call/pop anchor mismatch (expected `pop ebp` at LINK_N)"

# ---------------------------------------------------------------- data tables
tab_atk = bytes(ATK_BONUS) + b"\x00" * (8-len(ATK_BONUS))
tab_def = bytes(DEF_BONUS) + b"\x00" * (8-len(DEF_BONUS))
tab_suf = b"".join(struct.pack("<I", v) for v in SUFFIX_VAS)
data_blob = tab_atk + tab_def + tab_suf

APPLY = "--apply" in sys.argv
def process(path, base, suffix=".pre-leadership4"):
    data = bytearray(open(path, "rb").read()); secs = load_sections(data); va2off = mkva2off(base)
    def rd(va, n): o = va2off(secs, va); return bytes(data[o:o+n])

    patches = [
        (CAVE_COSTS, bytes(len(cave_costs)), cave_costs,
                     f"cave_lscosts (cost[1..{MAX_LEVEL}] = {COST_EACH})"),
        (CAVE_NAME,  bytes(len(cave_name)),  cave_name,  "cave_lsname (append ' I'..' IV')"),
        (DATA_TAB,   bytes(len(data_blob)),  data_blob,  "atk/def bonus tables + suffix ptr table"),
        (CAP_SITE, bytes.fromhex("c746280100 0000".replace(" ", "")),
                   bytes.fromhex("c7462804000000"),
                   f"cap {CAP_SITE:08X}: [esi+0x28] = 1 -> {MAX_LEVEL}"),
        (PUT_CALL, b"\xE8" + rel32(PUT_CALL, PUT_FN), b"\xE8" + rel32(PUT_CALL, CAVE_COSTS),
                   f"ctor {PUT_CALL:08X}: call TIntegerList.Put -> cave_lscosts"),
        (ATK_DISP, struct.pack("<I", ATK_VAN), struct.pack("<I", ATK_TAB),
                   f"GetAttack disp32 -> {ATK_TAB:08X} {tuple(ATK_BONUS[1:])}"),
        (DEF_DISP, struct.pack("<I", DEF_VAN), struct.pack("<I", DEF_TAB),
                   f"GetDefense disp32 -> {DEF_TAB:08X} {tuple(DEF_BONUS[1:])}"),
        (VMT_SLOT, struct.pack("<I", ORIG_NAME), struct.pack("<I", CAVE_NAME),
                   f"VMT+0x10c {VMT_SLOT:08X}: GetLevelName -> cave_lsname"),
    ]

    print(f"[curve] " + "  ".join(f"{'I'*i if i<4 else 'IV'}:+{ATK_BONUS[i]}/+{DEF_BONUS[i]}"
                                  for i in range(1, MAX_LEVEL+1)))
    print(f"[cost ] {COST_EACH} per level, {COST_EACH*MAX_LEVEL} total to reach level {MAX_LEVEL}")
    print(f"[cave ] cave_lscosts @ {CAVE_COSTS:08X} ({len(cave_costs)} B)")
    for ins in cs.disasm(cave_costs, CAVE_COSTS):
        print(f"  {ins.address:08X} {ins.bytes.hex(' '):<22}{ins.mnemonic} {ins.op_str}")
    print(f"[cave ] cave_lsname  @ {CAVE_NAME:08X} ({len(cave_name)} B)")
    for ins in cs.disasm(cave_name, CAVE_NAME):
        print(f"  {ins.address:08X} {ins.bytes.hex(' '):<22}{ins.mnemonic} {ins.op_str}")
    print(f"[data ] {DATA_TAB:08X} atk={tab_atk[:5].hex(' ')} def={tab_def[:5].hex(' ')} "
          f"suffixes={[hex(v) for v in SUFFIX_VAS]}")

    # Is this DATA_TAB zone one WE wrote?  The 16-byte suffix-VA block is an unambiguous signature:
    # four link-time VAs of the game's own " I".." IV" literals, in order.  Nothing else in the DLL
    # looks like that, so if it matches, the whole 32-byte blob is ours and the curve bytes in front
    # of it are ours to rewrite -- whatever value they currently hold.  This is what makes the script
    # RE-TUNABLE: without it the free-space guard sees a populated zone and refuses, and the patch
    # verifier sees a third state (our blob with the OLD curve) that is neither `orig` nor `new`.
    def ours(live):
        return len(live) == len(data_blob) and live[0x10:0x20] == tab_suf

    # free-space guard: never overwrite live bytes
    for cva, cbytes in ((CAVE_COSTS, cave_costs), (CAVE_NAME, cave_name), (DATA_TAB, data_blob)):
        live = rd(cva, len(cbytes))
        if live == cbytes or not any(b != 0 for b in live):
            continue
        if cva == DATA_TAB and ours(live):
            print(f"[~ ] {cva:08X} holds OUR table with a different curve -- re-tuning in place")
            print(f"     atk {list(live[0:5])} -> {list(ATK_BONUS)}")
            print(f"     def {list(live[8:13])} -> {list(DEF_BONUS)}")
            continue
        print(f"[x] cave zone {cva:08X} not free:\n     {live.hex(' ')}"); return False
    # the re-tune must not change the blob's length, so nothing can grow into live bytes
    assert len(data_blob) == 0x20, "data_blob changed size -- re-check the growth zone before writing"
    if any(b != 0 for b in rd(DATA_TAB + len(data_blob), 8)):
        print(f"[x] the 8 bytes after DATA_TAB are no longer zero -- refusing to write"); return False

    if all(rd(va, len(new)) == new for va, _o, new, _d in patches):
        print("[= ] already applied"); return True
    ok = True
    for va, orig, new, desc in patches:
        cur = rd(va, len(new))
        if cur == orig or cur == new:
            continue
        if va == DATA_TAB and ours(cur):
            continue
        ok = False; print(f"[!] {va:08X} ({desc})\n     exp {orig.hex(' ')}\n     got {cur.hex(' ')}")
    if not ok: print("[x] mismatch -- not written"); return False
    if not APPLY: print("[dry] originals verified, cave zones free"); return True
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
      else ("\n[done] Applied. Re-tune by editing the constants and re-running --apply (rewrites in place)."
            "\n       Revert: no --undo here -- restore the 5 hook sites and zero the three cave zones by"
            "\n       hand. A .pre-* restore is not a revert path." if ok else "\n[!] not applied"))
