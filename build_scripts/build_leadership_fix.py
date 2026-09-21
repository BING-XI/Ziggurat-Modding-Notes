#!/usr/bin/env python3
r"""
AoW1 bugfix -- Leadership no longer goes PERMANENTLY dead after a unit is stacked with another leader.

THE BUG (root cause doc: Modding Resources/Leadership_Disable_Bug_RootCause.md)
  A unit or hero that earns Leadership *while standing in another leader's aura* never receives its
  own inherent ability record -- only the enabled bit. When the aura later goes away, the aura
  garbage-collector deletes that record AND clears the bit, so the unit loses Leadership for good.
  Separating it does not bring it back.

  Two defects compound:

  A) GRANT MASKED -- `TAbilityOwner.UpdateDefaultAbilities` @0x5574F518 (the medal/rank + hero chassis
     grant) skips the grant when the recipient already looks equal-or-better:
         5574F549  mov edx,ebx / mov eax,edi        ; edi = rank/chassis TEMPLATE
         5574F54D  mov ecx,[eax] / call [ecx+0x84]  ; template level   <-- SITE 1
         5574F557  mov edx,ebx / mov eax,esi        ; esi = the UNIT
         5574F55B  mov ecx,[eax] / call [ecx+0x84]  ; unit level       <-- SITE 2
         5574F563  cmp ebp,eax / jle skip
     VMT +0x84 is `TAbilityOwner.GetAbLevel` @0x5574FD44, which calls the ability's GetLevel
     (VMT +0x70) -- the EFFECTIVE level, max(own, aura-borrowed). A unit inside a level-1 aura
     therefore reports 1, the template also reports 1, `1 <= 1` -> the inherent record is never
     copied. (Note the data copy is conditional but `SetAbilityEnabled(id,1)` @0x5574F597 is not, so
     the unit is left showing Leadership with no level behind it.)

  B) AURA GC EATS IT -- `TLeadershipAbility.ResetExternalSource` @0x557662E4 treats `data[+0x0c]==0`
     ("no own level") as proof the record is merely borrowed, and does SetAb(id,0) + RemoveAbilityData.
     The masked unit's only record is the aura one, so leaving the aura erases bit and record.

  Nothing re-grants afterwards: `TUnit.NewDay` @0x55782C98 does do a full rebuild but is DAY-1 GATED
  (`cmp dword [AoWHSMap+0x174],1` @0x55782CA9), and `TUnit.SetExperience` only re-grants on a RANK
  CHANGE -- which never comes again at gold medal. Heroes are vulnerable identically (THero.GetAbSet
  and VMT+0x84 both read the hero's own store, exactly the terms compared above).

THE FIX -- compare INHERENT levels, not effective ones
  The engine already has the right accessor and simply does not use it here:
  `TMultiLevelAbility.GetInherentLevel` @0x55765200 (ability VMT +0x94) returns only data[+0x0c].
  We repoint BOTH call sites to `cave_abinherent`, a mirror of TAbilityOwner.GetAbLevel that dispatches
  to VMT +0x94 instead of +0x70.

  Each site is `mov ecx,[eax]` + `call dword [ecx+0x84]` = exactly 8 bytes, replaced by
  `call cave_abinherent` (5) + 3 NOPs. Register contract is identical to GetAbLevel: in EAX = owner,
  EDX = ability id; out EAX = level; EBX/ESI/EDI/EBP preserved (the loop uses all four).

  WHY THIS IS SAFE FOR EVERY OTHER ABILITY. UpdateDefaultAbilities loops over ALL ability ids, so the
  comparison change is global -- but it is a no-op for anything that is not multi-level: the base
  `TAbility.GetLevel` @0x5574E9B0 and `TAbility.GetInherentLevel` @0x5574E954 BOTH `return 0`, so
  plain abilities compare 0 vs 0 either way. For genuinely multi-level abilities the new behaviour is
  strictly better: a unit with inherent 1 + borrowed 3 that is granted a level-2 template now upgrades
  to 2 instead of being skipped. Templates carry no borrowed level, so the template side is unchanged
  either way (compared via the same cave for symmetry).

  Defect (B) is deliberately left alone: once (A) stops discarding the inherent record, the `own==0`
  test correctly identifies genuinely-borrowed records, which is what it was written for.

POSITION INDEPENDENCE
  The cave needs the AoWHSSet global (0x558FA044) to reach the ability registry. New cave bytes carry
  no .reloc entries, so it computes the LOAD DELTA with the standard call/pop trick and addresses the
  global as [delta + link-time VA]. Everything else is rel32 or register-indirect.

VALIDATION IN-GAME
  Gold-medal a Leadership-capable unit WHILE it is stacked under a Leadership hero, then split it off:
  the ability must survive. Also confirm the vanilla-correct path (rank up alone) still yields exactly
  one level, and that a genuine aura recipient still loses its borrowed Leadership on leaving.

LAYERING
  Patch addresses and cave are disjoint from build_leadership4.py and build_leadership_aura.py, so
  the three are functionally independent and may be applied or reverted in any order.

REVERT -- use --undo, never a snapshot
  --undo is surgical: it restores the two 8-byte call sites and zeroes cave_abinherent, touching no
  backup, so it stays correct however many later features are stacked on the DLL. It verifies before
  writing -- every byte must read as either ours or vanilla -- and aborts on anything foreign.

  The `<game dir>\backups\AoWEPACK.dpl.pre-leadershipfix` snapshot is NOT a revert path and never was
  a safe one: it is a WHOLE-FILE copy, so restoring it destroys every feature applied to AoWEPACK.dpl
  after this one. There is no snapshot layer left in any case (both stacks were purged, 2026-08-08 /
  2026-09-09). The pristine reference is the vanilla game root's own AoWEPACK.dpl (or
  Modding Resources/AoWEPACK_original_backup.dpl, byte-identical to it).

Idempotent, verify-before-write, free-space asserted, dry-run by default / --apply / --undo.
"""
import shutil, subprocess, sys, struct, os
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

DLL_BASE   = 0x55700000
SITE1      = 0x5574F54D          # template-level call  (mov ecx,[eax]; call [ecx+0x84])
SITE2      = 0x5574F55B          # unit-level call
SITE_ORIG  = bytes.fromhex("8b08ff91 84000000".replace(" ", ""))   # 8 bytes
AOWHSSET   = 0x558FA044          # AoWE.AoWHSSet  (registry at +0x80)
GETABILITY = 0x557501C0          # TAbilityControl.GetAbility (EAX=control, EDX=id -> EAX=ability)
INH_SLOT   = 0x94                # ability VMT: GetInherentLevel  (vs +0x70 GetLevel)
CAVE       = 0x5580F100          # free zeroed run (0x5580EFBB+); clear of build_leadership4's block

# cave_abinherent: mirror of TAbilityOwner.GetAbLevel @0x5574FD44 but dispatching VMT +0x94.
#   in : EAX = ability owner, EDX = ability id
#   out: EAX = INHERENT level (0 when there is no data record / not a multi-level ability)
#   preserves EBX/ESI (pushed) and never touches EDI/EBP -- matches GetAbLevel's contract.
_pro_src = """
    push ebx
    push esi
    mov  esi, edx
    mov  ebx, eax
"""
_pro = bytes(ks.asm(_pro_src, CAVE)[0])
LINK_N = CAVE + len(_pro) + 5     # link-time address of the `pop eax` (call/pop anchor)

cave_src = _pro_src + f"""
    call _n
_n:
    pop  eax
    sub  eax, 0x{LINK_N:X}
    mov  eax, [eax + 0x{AOWHSSET:X}]
    mov  eax, [eax + 0x80]
    mov  edx, esi
    call 0x{GETABILITY:X}
    mov  edx, ebx
    mov  ecx, [eax]
    call dword ptr [ecx + 0x{INH_SLOT:X}]
    pop  esi
    pop  ebx
    ret
"""
cave = bytes(ks.asm(cave_src, CAVE)[0])
assert cave[len(_pro)+5] == 0x58, "call/pop anchor mismatch (expected `pop eax` at LINK_N)"

APPLY = "--apply" in sys.argv
UNDO  = "--undo"  in sys.argv
NOOP  = "noop"                   # undo() sentinel: already vanilla, nothing was written
if APPLY and UNDO: sys.exit("[x] --apply and --undo are mutually exclusive")

def kill_game():
    """Standing authorization: the game/editor lock the binaries. Just kill them."""
    import os as _os
    # ⚠ SCRATCH GUARD (2026-09-03): AOW_GAME_DIR set => not the real install; never kill
    # the user's running game. See the note in build_minddecay_oos.py.
    if _os.environ.get("AOW_GAME_DIR"):
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match '^(AoW|AoWCompat|AoWDevEd|AoWEd)$' }"
         " | Stop-Process -Force"],
        capture_output=True)

def undo(path, data, secs, va2off, patches):
    """Surgical revert: restore each site's vanilla bytes and zero the cave. Touches no backup.

    The `patches` table already encodes the undo -- every entry's `orig` is the vanilla run for a
    hook site and all-zeroes for a cave zone, so reverting is just writing `orig` everywhere.
    """
    cur = {va: bytes(data[va2off(secs, va):va2off(secs, va)+len(new)]) for va, _o, new, _d in patches}
    if all(cur[va] == orig for va, orig, _n, _d in patches):
        print("[= ] not applied -- nothing to undo"); return NOOP
    ok = True
    for va, orig, new, desc in patches:
        if cur[va] not in (orig, new):
            ok = False
            print(f"[!] {va:08X} is foreign -- refusing to touch it ({desc})\n"
                  f"     ours   {new.hex(' ')}\n     vanilla {orig.hex(' ')}\n     got    {cur[va].hex(' ')}")
    if not ok: print("[x] foreign bytes -- nothing written"); return False
    kill_game()
    for va, orig, _new, desc in patches:
        o = va2off(secs, va); data[o:o+len(orig)] = orig
        print(f"[u ] {va:08X} restored: {desc}")
    try: open(path, "wb").write(data)
    except PermissionError: print("[x] LOCKED -- close AoW binaries (AoW.exe/AoWCompat.exe/AoWDevEd.exe)"); return False
    return True

def process(path, base, suffix=".pre-leadershipfix"):
    data = bytearray(open(path, "rb").read()); secs = load_sections(data); va2off = mkva2off(base)
    def rd(va, n): o = va2off(secs, va); return bytes(data[o:o+n])

    patch1 = b"\xE8" + rel32(SITE1, CAVE) + b"\x90\x90\x90"
    patch2 = b"\xE8" + rel32(SITE2, CAVE) + b"\x90\x90\x90"
    patches = [
        (CAVE,  bytes(len(cave)), cave,   "cave_abinherent (GetAbLevel -> GetInherentLevel)"),
        (SITE1, SITE_ORIG, patch1, f"UpdateDefaultAbilities {SITE1:08X}: template level -> inherent"),
        (SITE2, SITE_ORIG, patch2, f"UpdateDefaultAbilities {SITE2:08X}: unit level -> inherent"),
    ]

    print(f"[cave ] cave_abinherent @ {CAVE:08X} ({len(cave)} B)")
    for ins in cs.disasm(cave, CAVE):
        print(f"  {ins.address:08X} {ins.bytes.hex(' '):<22}{ins.mnemonic} {ins.op_str}")
    print(f"[hook ] {SITE1:08X} and {SITE2:08X}: 8-byte `mov ecx,[eax]; call [ecx+0x84]` -> call cave + 3 nop")

    if UNDO:
        return undo(path, data, secs, va2off, patches)

    live = rd(CAVE, len(cave))
    if live != cave and any(b != 0 for b in live):
        print(f"[x] cave zone {CAVE:08X} not free:\n     {live.hex(' ')}"); return False
    if all(rd(va, len(new)) == new for va, _o, new, _d in patches):
        print("[= ] already applied"); return True
    ok = True
    for va, orig, new, desc in patches:
        cur = rd(va, len(new))
        if cur != orig and cur != new:
            ok = False; print(f"[!] {va:08X} ({desc})\n     exp {orig.hex(' ')}\n     got {cur.hex(' ')}")
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
if UNDO:
    if ok is True:
        print("\n[done] UNDONE -- both call sites restored, cave_abinherent zeroed. No backup touched.")
    elif ok != NOOP:
        print("\n[!] not reverted")
elif APPLY:
    print("\n[done] Applied. Revert: re-run with --undo (surgical, touches no backup)."
          if ok else "\n[!] not applied")
else:
    print("\n[dry-run] Re-run with --apply to write, or --undo to revert. Close all AoW binaries first.")
