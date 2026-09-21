#!/usr/bin/env python3
r"""
AoW1 mod -- Leadership aura refreshes INSTANTLY after a hero buys a Leadership level.

Original idea and implementation: **a fellow modder** (their `patch_leadership_aura_refresh_v1.py`,
2026-07-19, written against their own `AoWEPACK.dll` build). This is that logic re-verified against
our DLL and adapted to this project's conventions -- see "ADAPTED FROM" at the bottom for exactly
what changed and why.

PROBLEM
  After buying a Leadership level in the hero level-up UI, the party's units do not get the new aura
  bonus until the army next updates (a move, or the next turn). The level is applied immediately; the
  aura is stale until something happens to re-run the formation pass.

FIX
  `THeroUpgradeTE.Execute` @0x55785450 applies the stat deltas and the ability grant, then clears the
  upgrade-pending flag. Its tail is:

      557854DE  mov  eax, edi                  ; EDI = the hero
      557854E0  call TAbilityOwner.UpdateDefaultAbilities   <-- WE REPOINT THIS
      557854E5  mov  byte [edi+0x54], 0        ; clear upgrade-pending  (c6 47 54 00)
      557854E9  mov  eax, ebx / pop edi / pop esi / pop ebx / ret

  We repoint that call to `cave_auraup`, which runs the original call and then recomputes the aura
  immediately:

      army = [hero+0x4]                          ; the unit's container
      if army && IsClass(army, TArmy):           ; vanilla's own guard - see below
          TArmy.UpdateFormation(army)

  `TArmy.UpdateFormation` @0x5578D034 (EAX=army) is the engine's sole aura recomputer -- the exact
  routine that runs on move/turn -- so behaviour is identical, just immediate.

WHY THE GUARD
  A unit's container is not always an army. Vanilla uses precisely this test, e.g.
  `TAbstractUnit.MovedTo+0xce` @0x557803EF:
      mov esi,[ebx+4] / mov edx,[0x557130AC] / call @IsClass / test al,al / je skip
  and again in `TAbstractUnit.UpdateMoraleValue+0x5f` @0x5577F0B2. Verified in OUR DLL:
  `[0x557130AC]` -> VMT `0x557130EC`, Delphi class name **"TArmy"**.

  The hook site is the LAST thing `Execute` does before clearing the flag, and the TE's ability grant
  runs through that very `UpdateDefaultAbilities` call (`EDX = [esi+0x1c]`, the TE's ability owner),
  so hooking here catches the stat deltas AND the ability/level grant in one place.

MP-SAFE
  `THeroUpgradeTE` is a network-distributed token event -- it executes on every peer with identical
  data -- and `UpdateFormation` is deterministic (no RNG). So every peer recomputes the same aura.

REGISTER CONTRACT
  Entered in place of `call UpdateDefaultAbilities`, so EAX/EDX still hold the original arguments and
  the cave forwards them untouched by calling UDA first. Afterwards the caller does `mov eax,ebx` and
  pops EDI/ESI/EBX, so EBX/ESI/EDI must survive: the cave pushes/pops EBX and never touches ESI/EDI.

POSITION INDEPENDENCE
  The classref global read is delta-fixed with the standard call/pop trick; every call out is rel32.
  Note we read the classref *global* (`[delta + 0x557130AC]`) and use the dword stored there -- that
  slot is relocated by the loader, so its value is already a runtime VMT pointer and needs no fixup.

LAYERING
  Independent of build_leadership4.py and build_leadership_fix.py (distinct addresses and cave), so
  the three may be applied or reverted in any order. Composes with the bug fix: that one changes
  UpdateDefaultAbilities' *internals*, this one wraps a *call* to it.

REVERT -- use --undo, never a snapshot
  --undo is surgical: it repoints the hooked call back at TAbilityOwner.UpdateDefaultAbilities and
  zeroes cave_auraup, touching no backup, so it stays correct however many later features are stacked
  on the DLL. It verifies before writing -- every byte must read as either ours or vanilla -- and
  aborts on anything foreign.

  The .pre-leadershipaura snapshot is NOT a revert path and never was a safe one: it is a WHOLE-FILE
  copy, so restoring it destroys every feature applied to AoWEPACK.dpl after this one. There is no
  snapshot layer left in any case (both stacks were purged, 2026-08-08 / 2026-09-09). The pristine
  reference is the vanilla game root's own AoWEPACK.dpl (or Modding Resources/AoWEPACK_original_backup.dpl,
  byte-identical to it).

ADAPTED FROM the original, with these changes (all forced by our build differing from theirs):
  1. CAVE MOVED 0x5580E120 -> 0x5580F140. Their address is NOT free in our DLL: it holds live code
     from `build_assassin.py` (`mov edx,0x70 ... call [ecx+0xa8] ... mov edx,0x3f` = the
     Monster-Slaying / marker test). Applying theirs unmodified would have silently destroyed the
     slayer feature. Our free run starts at 0x5580F131 (after cave_abinherent).
  2. File is `AoWEPACK.dpl`, not `AoWEPACK.dll`, and is located via the project's relative resolver
     rather than the script's own directory.
  3. VA->file offset via real PE section mapping (`load_sections`/`va2off`) instead of the flat
     `FILE_DELTA = 0x55700C00`. That constant happens to be correct for CODE in this binary, but it
     silently produces garbage for any address outside CODE.
  4. Keystone-assembled from source instead of hand-emitted opcode bytes, with a two-pass assembly to
     resolve the call/pop anchor, plus an assert that the anchor really lands on `pop edx`.
  5. Project conventions: dry-run default / --apply / surgical --undo, idempotency check, free-space
     guard, snapshot at `<game dir>\backups\AoWEPACK.dpl.pre-leadershipaura`.
  Their sanity check that `mov byte [edi+0x54],0` directly follows the hook is KEPT (it pins the
  function version) -- and it passes on our DLL unchanged.

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

DLL_BASE  = 0x55700000
UDA       = 0x5574F518        # TAbilityOwner.UpdateDefaultAbilities
HOOK      = 0x557854E0        # the `call UDA` inside THeroUpgradeTE.Execute
NEXT_VA   = 0x557854E5        # must be `mov byte [edi+0x54],0` -- pins the function version
NEXT_BYTES = bytes.fromhex("c6475400")
CLASSREF  = 0x557130AC        # global holding the TArmy classref (verified: -> 0x557130EC "TArmy")
ISCLASS   = 0x557010C0        # VCL30.dpl!System.@IsClass  (EAX=obj, EDX=class -> AL)
UPD_FORM  = 0x5578D034        # TArmy.UpdateFormation (EAX=army)
CAVE      = 0x5580F140        # free zeroed run (0x5580F131+), clear of the other leadership caves

# cave_auraup: runs the original UpdateDefaultAbilities, then recomputes the stack's Leadership aura.
#   entry: EAX = hero, EDX = ability owner  (as set up by THeroUpgradeTE.Execute)
#   EDI   = hero (caller's register, untouched here)
#   preserves EBX/ESI/EDI; EAX/ECX/EDX are already caller-dead at this point.
def build(link_n):
    src = f"""
    call 0x{UDA:X}
    push ebx
    mov  ebx, [edi+4]
    test ebx, ebx
    jz   _skip
    call _n
_n:
    pop  edx
    sub  edx, 0x{link_n:X}
    mov  edx, [edx + 0x{CLASSREF:X}]
    mov  eax, ebx
    call 0x{ISCLASS:X}
    test al, al
    jz   _skip
    mov  eax, ebx
    call 0x{UPD_FORM:X}
_skip:
    pop  ebx
    ret
"""
    return bytes(ks.asm(src, CAVE)[0])

# two-pass: pass 1 locates the call/pop anchor (imm32 length is stable), pass 2 fixes it up
_tmp = build(CAVE)
_anchor = _tmp.index(b"\xE8\x00\x00\x00\x00") + 5      # offset of `pop edx`
LINK_N = CAVE + _anchor
cave = build(LINK_N)
assert cave[_anchor] == 0x5A, "call/pop anchor mismatch (expected `pop edx`)"
assert len(cave) == len(_tmp), "cave length changed between passes"

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
    """Surgical revert: repoint the hook back at UDA and zero the cave. Touches no backup.

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

def process(path, base, suffix=".pre-leadershipaura"):
    data = bytearray(open(path, "rb").read()); secs = load_sections(data); va2off = mkva2off(base)
    def rd(va, n): o = va2off(secs, va); return bytes(data[o:o+n])

    # pin the function version: the flag-clear must directly follow the hook
    if rd(NEXT_VA, 4) != NEXT_BYTES:
        print(f"[x] unexpected bytes after hook @{NEXT_VA:08X}: {rd(NEXT_VA,4).hex(' ')} "
              f"(expected {NEXT_BYTES.hex(' ')}) -- wrong build?"); return False

    patches = [
        (CAVE, bytes(len(cave)), cave, f"cave_auraup ({len(cave)} B)"),
        (HOOK, b"\xE8" + rel32(HOOK, UDA), b"\xE8" + rel32(HOOK, CAVE),
               f"THeroUpgradeTE.Execute {HOOK:08X}: UpdateDefaultAbilities -> cave_auraup"),
    ]

    print(f"[cave ] cave_auraup @ {CAVE:08X} ({len(cave)} B), anchor +0x{_anchor:X}")
    for ins in cs.disasm(cave, CAVE):
        print(f"  {ins.address:08X} {ins.bytes.hex(' '):<22}{ins.mnemonic} {ins.op_str}")

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
        print("\n[done] UNDONE -- hook repointed at UpdateDefaultAbilities, cave_auraup zeroed. No backup touched.")
    elif ok != NOOP:
        print("\n[!] not reverted")
elif APPLY:
    print("\n[done] Applied. Revert: re-run with --undo (surgical, touches no backup)."
          if ok else "\n[!] not applied")
else:
    print("\n[dry-run] Re-run with --apply to write, or --undo to revert. Close all AoW binaries first.")
