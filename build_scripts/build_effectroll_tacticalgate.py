#!/usr/bin/env python3
r"""
AoW1 mod -- restrict the combat-log EFFECT-ROLL emitter to genuine tactical combat.

WHY
  build_effectroll.py repointed the six resistance-roll sites inside
  AoWE.TAbstractUnit.ExecuteDamageEffectsRole @0x55781BA4 to stubs at 0x5580F785.. that
  call HitRole and then EMIT a combat-log line via the shared emitter @0x5580F605.

  That emitter's only activity guard is:
      SizeOfImage >= 0x20E000        (i.e. "this is the combat-log-enabled AoW.exe/AoWCompat,
                                       not AoWDevEd" -- protects the 0x60D000 read below)
      [0x60D000] == 'CLG1'           (the .clog ring magic -- ALWAYS present once combatlog is
                                       applied, NOT a "combat is happening" signal)
      wr - rd < 63                   (ring-not-full)

  None of those is "am I in tactical combat". So the emitter ALSO runs:
    * on the STRATEGIC map, when a Death / Divine / Pestilence storm (altar or cast) resolves a
      debuff -- because build_stormeffectroll.py routes the strategic debuff through
      ExecuteDamageEffectsRole, whose HitRole sites are now these emitting stubs; and
    * during AUTO-RESOLVE (TFastCombatUnit.fcExecute) -- which is exactly where a freeze was once
      localised (see build_effectroll.py's --revert note, 2026-07-22).

  Running the tactical-only string/ring machinery in those contexts is the suspected cause of the
  Death-altar exception "during TStructureTE" (terrain changed to Wasteland, then the per-unit
  effect roll faulted) and the subsequent turn-processing freeze: TArmy.IncommingStorm @0x557904B4
  brackets its per-unit loop in BeginUpdate/EndUpdate, so an exception there leaves the army's
  change-notify lock held and every later order stalls.

WHAT
  A 5-byte jmp hook at the emitter entry (0x5580F605) to a tiny position-independent cave that
  reproduces the emitter's OWN SizeOfImage guard first (so it never reads 0x60D00C in AoWDevEd,
  where the .clog section does not exist), then requires RING_TACTICAL (0x60D00C) == 1 before
  letting the emitter run. Off the tactical path it returns immediately -- HitRole has already run
  in the calling stub, so the EFFECT still lands / resists exactly as before; only the log line is
  skipped. In live tactical combat (RING_TACTICAL == 1) the emitter runs unchanged, so the combat
  log still shows the resistance rolls it was built for.

  This does NOT touch build_effectroll.py's cave or the six roll sites, and does NOT touch
  build_lightning_ignites.py (which reads the "stunned" stub at 0x5580F79D) -- the stub addresses
  and every roll site are left byte-for-byte where they are. It only intercepts the emitter's
  entry.

CAVE (0x55810500, position-independent: only EXE absolutes 0x40003C / 0x60D00C -- AoW.exe is
      fixed-base -- plus a rel32 jmp back into the DLL; no call/pop anchor, no DLL data ref):
      pushad
      mov  eax, [0x40003C]                 ; e_lfanew of the hosting exe
      cmp  dword [eax+0x400050], 0x20E000  ; SizeOfImage >= 0x20E000 ? (combat-log exe)
      jb   L_cont                          ; not the combat-log exe -> let the emitter self-bail
      cmp  dword [0x60D00C], 1             ; RING_TACTICAL -- tactical combat map active?
      jne  L_skip                          ; no -> skip logging entirely
    L_cont:
      popad                                ; restore, then replay the displaced emitter prologue
      pushad
      push ebp
      mov  ebp, esp
      sub  esp, 0x20
      jmp  0x5580F60C                      ; resume at the instruction after `sub esp,0x20`
    L_skip:
      popad
      ret                                  ; return to the calling stub; HitRole already ran

⚠ FORWARD HAZARD: this hook lives inside build_effectroll.py's cave region. If build_effectroll.py
  is ever re-applied it rewrites 0x5580F605 (restoring the raw `pushad`) and silently drops this
  gate -- re-run this script afterwards. The two do not otherwise collide.

Backups to <game>/backups/AoWEPACK.dpl.pre-effectrollgate. Dry-run by default; --apply to write;
--undo to remove surgically (restore the 5 displaced bytes, zero the cave). Idempotent,
verify-before-write. Close AoW.exe / AoWCompat.exe / AoWDevEd.exe first.
"""
import os, sys, struct, shutil

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-effectrollgate")

IMAGE_BASE = 0x55700000
HOOK_VA    = 0x5580F605                       # combat-log effect emitter entry (build_effectroll.py)
HOOK_ORIG  = bytes.fromhex("6055 89e5 83".replace(" ", ""))   # pushad;push ebp;mov ebp,esp;<sub..>
RESUME_VA  = 0x5580F60C                       # after `sub esp,0x20`
CAVE_VA    = 0x55810500                       # verified zero + unclaimed (combatdiag ends 0x558104xx)
CAVE_LIMIT = 0x40                             # reserve 0x55810500..0x5581053F
RING_TACTICAL = 0x60D00C
EXE_LFANEW    = 0x40003C
EXE_SIZEOFIMG_OFF = 0x400050                  # [ [0x40003C] + 0x400050 ] = SizeOfImage
SIZEOFIMG_MIN = 0x20E000

APPLY  = "--apply" in sys.argv
UNDO   = "--undo" in sys.argv


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    o, out = e + 24 + opt, []
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from("<IIII", d, o + 8)
        out.append((va, vs, raw, rs)); o += 40
    return out


def va2off(d, va):
    rva = va - IMAGE_BASE
    for va0, vs, raw, rs in sections(d):
        if va0 <= rva < va0 + max(vs, rs):
            return raw + (rva - va0)
    sys.exit("ABORT: VA %08X outside every section" % va)


def build_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    asm = f"""
        pushad
        mov  eax, [0x{EXE_LFANEW:X}]
        cmp  dword ptr [eax + 0x{EXE_SIZEOFIMG_OFF:X}], 0x{SIZEOFIMG_MIN:X}
        jb   L_cont
        cmp  dword ptr [0x{RING_TACTICAL:X}], 1
        jne  L_skip
    L_cont:
        popad
        pushad
        push ebp
        mov  ebp, esp
        sub  esp, 0x20
        jmp  0x{RESUME_VA:X}
    L_skip:
        popad
        ret
    """
    enc, _ = ks.asm(asm, CAVE_VA)
    return bytes(enc)


def make_hook():
    rel = CAVE_VA - (HOOK_VA + 5)
    return b"\xE9" + struct.pack("<i", rel)


def disasm(blob, va):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob, va):
        print(f"   {ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")


def main():
    data = bytearray(open(DLL, "rb").read())
    cave = build_cave()
    hook = make_hook()
    if len(cave) > CAVE_LIMIT:
        sys.exit(f"ABORT: cave {len(cave)}B exceeds reserve {CAVE_LIMIT}B")

    ho = va2off(data, HOOK_VA)
    co = va2off(data, CAVE_VA)
    cur_hook = bytes(data[ho:ho + 5])
    cur_cave = bytes(data[co:co + len(cave)])

    applied = (cur_hook == hook and cur_cave == cave)
    pristine = (cur_hook == HOOK_ORIG and all(b == 0 for b in data[co:co + CAVE_LIMIT]))

    print(f"[effectroll tactical-gate]  hook @{HOOK_VA:08X}  cave @{CAVE_VA:08X} ({len(cave)}B)")
    disasm(cave, CAVE_VA)
    print(f"   state: {'APPLIED' if applied else 'PRISTINE' if pristine else 'UNKNOWN'}")

    if UNDO:
        if pristine:
            print("[= ] already pristine -- nothing to undo"); return
        if not applied:
            sys.exit("ABORT: state is neither cleanly applied nor pristine -- refusing to undo")
        if not APPLY:
            print("[dry] --undo would restore 5 bytes @%08X and zero the cave. Add --apply." % HOOK_VA)
            return
        data[ho:ho + 5] = HOOK_ORIG
        data[co:co + CAVE_LIMIT] = b"\x00" * CAVE_LIMIT
        open(DLL, "wb").write(data)
        print("[done] reverted")
        return

    if applied:
        print("[= ] already applied and up to date -- nothing to do"); return
    if not pristine:
        sys.exit(f"ABORT: hook site not pristine (got {cur_hook.hex(' ')}, "
                 f"expected {HOOK_ORIG.hex(' ')}) or cave not free -- refusing to write")
    if not APPLY:
        print("[dry] assembles, fits, hook site + cave verified free. Re-run with --apply."); return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    if not os.path.exists(BACKUP):
        shutil.copy2(DLL, BACKUP); print(f"[bak] {BACKUP}")
    data[co:co + len(cave)] = cave
    data[ho:ho + 5] = hook
    try:
        open(DLL, "wb").write(data)
    except PermissionError:
        sys.exit("[x] LOCKED -- close AoW.exe / AoWCompat.exe / AoWDevEd.exe first")
    print(f"[w ] cave @{CAVE_VA:08X}\n[w ] hook @{HOOK_VA:08X} {hook.hex(' ')}\n[done] applied")


if __name__ == "__main__":
    main()
