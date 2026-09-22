#!/usr/bin/env python3
r"""
AoW1 mod -- "turn1upgrade": map-placed heroes KEEP their unspent skill points and
get a level-up prompt on their owner's first turn.

FULL ANALYSIS: Modding Resources/Zig notes/01-combat-maths.md  section 5,
               "Hero skill points -- the budget, the price list, and the hero library"

================================================================================
THE PROBLEM
================================================================================
Set a leader to level 5 in the editor and it arrives in game with 60 unspent
skill points (5*10+10, THero.GetSkillPoints @0x557875C4).  The player never gets
to spend them: at the next level-up the dialog offers 10, not 70.

Vanilla confiscates them on day 1.  THero.NewDay @0x55786C3C:

    55786C4B  cmp dword ptr [map+0x174], 1     ; +0x174 is the DAY COUNTER -> day 1 only
    ...
    55786CB3  mov  eax, ebx
    55786CB5  call THero.GetSkillPoints
    55786CBA  mov  dword ptr [ebx+0x50], eax   ; <-- the confiscation

[hero+0x50] is a permanent write-off that GetSkillPoints subtracts.  The write is
self-referential -- writeoff' := (budget - used) - writeoff -- so the points still
spendable after day 1 are EXACTLY the value the map stored in tag 0x27, whatever
the hero's level.  The editor never writes that tag, so it is 0, so they all go.
0x55786CBA is the only writer of [hero+0x50] in the module.

Two vanilla exemptions exist and a PBEM game misses both:
  * engine[+0x70] != 0 (a CAMPAIGN is loaded) AND player[+0xA7] == 0 (human owner)
  * map[+0x149] != 0 (the "Customize leaders" setup checkbox) AND IsClass(TLeader)
The checkbox is hard-disabled by the setup form in play-by-email -- AoWz.exe
@0x00410D44 `cmp byte ptr [settings+0x3C], 2`, where session mode 2 is PBEM
(TAoWHSMap.SetupPlayerControl @0x55777F1C builds TPBEMPlayerControl for it).

================================================================================
WHY PRESERVING THE POINTS IS NOT ENOUGH ON ITS OWN
================================================================================
Nothing opens the spend UI just because a hero has points.  The prompt comes from
THero.ValidateHeroUpgrade @0x55787D54, called by THero.NewTurn @0x55787FE7 on the
owner's turn, and its condition is a LAG, not an event:

    if (hero.levelCache[+0x4C] < GetLevel())          ; GetLevel derives from XP [+0x48]
        hero.levelCache = GetLevel()
        raise THeroUpgradeEventLog(old -> new)        ; this IS the level-up dialog
        if (player[+0xA7] != 0) ExecuteUpgradeHeroAI  ; AI spends its own

So the trigger is free: knock the cached level one below the XP-derived level and
the next NewTurn raises the dialog, restores the cache, and GetSkillPoints then
reports the full untaxed budget.

================================================================================
WHAT THIS PATCH DOES
================================================================================
Replace the 10-byte confiscation block in THero.NewDay's day-1 branch with a call
to a cave that, instead of writing off the points:

    * leaves [hero+0x50] alone            -> unspent points survive
    * decrements [hero+0x4C] by one       -> turn-1 level-up prompt

Both inbound jumps land on the block's boundaries and never inside it
(`je 0x55786CB3` from 0x55786CA0, `jne 0x55786CBD` from 0x55786CB1), so the run is
safe to rewrite whole.  Nothing is displaced: 10 bytes in, 10 bytes out.

SCOPE.  The block runs for every hero alive on day 1 -- i.e. exactly the ones the
map placed -- and not for later recruits, because the host is gated on day == 1.
Leaders and pre-placed non-leader heroes are both covered (owner ruling
2026-09-22).  If "Customize leaders" is ever ON, leaders skip the block entirely
via the IsClass(TLeader) branch that already sits above it, and behave as vanilla.

================================================================================
THE THREE GUARDS IN THE CAVE, AND WHY EACH IS LOAD-BEARING
================================================================================
1. GetSkillPoints() > 0.  Without it, a level-5 hero whose points were already
   spent in the editor gets an empty level-up dialog on turn 1.  (Owner ruling
   2026-09-22: suppress it.  This guard is the whole reason the feature needs a
   cave -- the test is 14 bytes and only 10 are available in place.)

2. GetLevel() >= levelCache.  ⚠ THE DANGEROUS ONE.  [hero+0x4C] is tag 0x16 and
   is PERSISTED.  If the cache were ever above the XP-derived level, decrementing
   it would not be undone by ValidateHeroUpgrade -- the hero would silently lose
   10 points of budget for the rest of the game, in the save file.  With this
   guard the decrement is only ever taken when the restore is guaranteed to fire.

3. levelCache >= 2.  Keeps the floor at 1; level 0 is not a reachable state
   anywhere else in the engine and SetLevel clamps to 1, but this cave writes the
   field directly and bypasses that clamp.

================================================================================
CAVE
================================================================================
C_TURN1 = 0x5584B000 in CODE, one cave, 40 bytes in an 0x80 span.
  entry: EAX = hero      exit: nothing (EAX/EDX/ECX clobbered, EBX preserved)

    push ebx / mov ebx,eax
    call THero.GetSkillPoints        ; rel32
    test eax,eax / jle done          ; guard 1
    mov eax,ebx / call THero.GetLevel
    movsx eax,al / movzx edx,byte [ebx+0x4C]
    cmp eax,edx / jl done            ; guard 2
    cmp dl,1 / jbe done              ; guard 3
    dec byte [ebx+0x4C]
  done: pop ebx / ret

The host keeps the hero in EBX and does `mov eax,ebx; call UpdateSettings`
immediately after the block, so EAX/EDX/ECX are dead across the call and EBX is
the only register that must survive.  Both callees preserve EBX themselves; the
cave saves it anyway because it holds the hero across two calls.

POSITION-INDEPENDENT: both calls are rel32 and there is no absolute memory
reference, so no call/pop rebase anchor is needed.  Asserted in build_caves().

Allocation: the high-water mark across build_scripts/ in the CODE cave run is
0x5584A3FF (build_item_hpmv / neighbours); 0x55850000 appears only as the upper
bound of build_minddecay_oos.py's .reloc scan, not as a claim.  0x5584B000 sits
above everything and inside a verified 0x9CA10-byte zero run.

RNG    -- the cave makes no draw of any kind, and references neither generator.
          Re-run re_tools/rng_audit.py --owners after --apply anyway (standing rule);
          this is not a P4 site, so --hash is not needed.
MP     -- deterministic: two pure reads and one byte decrement, no clock, no RNG,
          identical on every peer. [hero+0x4C] and [hero+0x50] are both already
          streamed (THero.ReadWrite tags 0x16 and 0x27), so the save format does
          not move.  ⚠ Standing project rule still applies: no mixed modded /
          unmodded multiplayer.
BINARY -- AoWEPACK.dpl only.  THero.NewDay lives nowhere else, so there is no
          AoWz.exe / AoWzCompat.exe lockstep half to keep.
SAVES  -- affects NEW games only.  A save whose day 1 already passed under an
          unpatched DLL has the write-off baked into tag 0x27; this patch does not
          and deliberately should not clear it, because a non-zero tag 0x27 is
          also the legitimate way a map author hands a hero a partial pool.

USAGE
    python build_scripts/build_hero_turn1_upgrade.py            # verify only
    python build_scripts/build_hero_turn1_upgrade.py --dis      # + cave disasm
    python build_scripts/build_hero_turn1_upgrade.py --apply
    python build_scripts/build_hero_turn1_upgrade.py --undo     # surgical
"""
import os
import struct
import subprocess
import sys

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root

DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-turn1upgrade")

# ---------------------------------------------------------------- addresses ---
HOOK          = 0x55786CB3      # THero.NewDay day-1 branch: the confiscation block
HOOK_LEN      = 0x0A            # .. 0x55786CBC inclusive; 0x55786CBD is a jump target

F_SKILLPOINTS = 0x557875C4      # AoWE.THero.GetSkillPoints   EAX=hero -> EAX=points
F_GETLEVEL    = 0x55787740      # AoWE.THero.GetLevel         EAX=hero -> AL=level from XP

OFF_LEVEL     = 0x4C            # THero level cache, 1 byte, streamed as tag 0x16
OFF_WRITEOFF  = 0x50            # THero skill-point write-off, streamed as tag 0x27

CAVE_BASE = 0x5584B000
C_TURN1   = 0x5584B000
CAVE_END  = 0x5584B080          # asserted zero-or-ours across this whole span

_BASE = None                    # VA = file_offset + _BASE, resolved from the PE


def orig_bytes():
    """The 10-byte vanilla confiscation run, rebuilt rather than hard-coded."""
    call_rel = F_SKILLPOINTS - (HOOK + 2 + 5)
    return (bytes.fromhex("8bc3")                       # mov eax, ebx
            + b"\xE8" + struct.pack("<i", call_rel)     # call THero.GetSkillPoints
            + b"\x89\x43" + bytes([OFF_WRITEOFF]))      # mov [ebx+0x50], eax


def patched_bytes():
    """mov eax,ebx / call C_TURN1 / 3 nops -- same 10 bytes, nothing displaced."""
    rel = C_TURN1 - (HOOK + 2 + 5)
    p = bytes.fromhex("8bc3") + b"\xE8" + struct.pack("<i", rel) + b"\x90" * 3
    assert len(p) == HOOK_LEN == len(orig_bytes())
    return p


def off(va):
    return va - _BASE


def resolve_base(d):
    """Set the flat VA->offset delta from the CODE section, and assert every
    address this script touches really lives in CODE (a flat delta is silently
    wrong outside it)."""
    global _BASE
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    image_base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        name = d[o:o + 8].rstrip(b"\0").decode("latin1")
        vsz, va, _rsz, ro = struct.unpack_from("<IIII", d, o + 8)
        if name != "CODE":
            continue
        lo, hi = image_base + va, image_base + va + vsz
        _BASE = lo - ro
        for a in (HOOK, HOOK + HOOK_LEN - 1, F_SKILLPOINTS, F_GETLEVEL,
                  CAVE_BASE, CAVE_END - 1):
            if not lo <= a < hi:
                sys.exit("ABORT: 0x%08X is outside CODE (0x%08X..0x%08X)" % (a, lo, hi))
        return
    sys.exit("ABORT: no CODE section in %s" % DLL)


def check_reloc(d):
    """⚠ A stale .reloc entry corrupts live code at every load and is invisible to
    every other static check (aow1-stale-reloc-corrupts-code).  Nothing here is
    displaced, but a pre-existing entry pointing INTO the rewritten run or into the
    cave span would relocate bytes we own.  Assert there are none."""
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    image_base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    rva, size = struct.unpack_from("<II", d, pe + 24 + 96 + 5 * 8)   # dir[5] = BASERELOC
    if not rva:
        return
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    foff = None
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        vsz, sva, _rsz, ro = struct.unpack_from("<IIII", d, o + 8)
        if sva <= rva < sva + max(vsz, _rsz):
            foff = ro + (rva - sva)
            break
    if foff is None:
        return
    bad, end, p = [], foff + size, foff
    while p < end - 8:
        page, blk = struct.unpack_from("<II", d, p)
        if blk < 8:
            break
        for q in range(p + 8, p + blk, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 0:
                continue
            target = image_base + page + (e & 0xFFF)
            if (HOOK <= target < HOOK + HOOK_LEN) or (CAVE_BASE <= target < CAVE_END):
                bad.append(target)
        p += blk
    if bad:
        sys.exit("ABORT: .reloc entries point into bytes this patch owns: %s"
                 % ", ".join("0x%08X" % b for b in bad))


# ------------------------------------------------------------- mini assembler --
def _ks():
    try:
        from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    except ImportError:
        sys.exit("keystone-engine not installed:  pip install keystone-engine")
    return Ks(KS_ARCH_X86, KS_MODE_32)


def asm_layout(frags, base):
    """frags: list of (label|None, text|bytes|None). Text may use {LABEL}
    placeholders. Iterates to a fixed point so forward references settle."""
    ks = _ks()
    labels = {lab: base for lab, _ in frags if lab}
    for _ in range(8):
        va, out, seen = base, b"", {}
        for lab, item in frags:
            if lab:
                seen[lab] = va
            if item is None:
                continue
            if isinstance(item, (bytes, bytearray)):
                out += bytes(item)
                va += len(item)
                continue
            text = item.format(**{k: hex(v) for k, v in labels.items()})
            enc, _ = ks.asm(text, va)
            if enc is None:
                raise RuntimeError("keystone failed on: %s" % text)
            out += bytes(enc)
            va += len(enc)
        if seen == labels:
            return out
        labels = seen
    raise RuntimeError("cave layout did not converge")


def build_caves():
    """Return {cave_va: bytes}."""
    blob = asm_layout([
        (None,   "push ebx"),
        (None,   "mov ebx, eax"),
        # guard 1 -- does this hero actually have anything to assign?
        (None,   "call %s" % hex(F_SKILLPOINTS)),
        (None,   "test eax, eax"),
        (None,   "jle {DONE}"),
        # guard 2 -- only lag the cache when ValidateHeroUpgrade is certain to
        # restore it.  [hero+0x4C] is PERSISTED; an unrestored decrement is a
        # permanent 10-point budget loss written into the save.
        (None,   "mov eax, ebx"),
        (None,   "call %s" % hex(F_GETLEVEL)),
        (None,   "movsx eax, al"),
        (None,   "movzx edx, byte ptr [ebx + %s]" % hex(OFF_LEVEL)),
        (None,   "cmp eax, edx"),
        (None,   "jl {DONE}"),
        # guard 3 -- floor the cache at 1; this write bypasses SetLevel's clamp.
        (None,   "cmp dl, 1"),
        (None,   "jbe {DONE}"),
        (None,   "dec byte ptr [ebx + %s]" % hex(OFF_LEVEL)),
        ("DONE", "pop ebx"),
        (None,   "ret"),
    ], C_TURN1)
    if len(blob) > CAVE_END - CAVE_BASE:
        raise RuntimeError("cave is %d bytes, the span is %d"
                           % (len(blob), CAVE_END - CAVE_BASE))
    # position-independence: the .dpl never loads at its preferred base, so no
    # absolute memory reference may appear. Both calls are rel32; assert no dword
    # in the blob looks like an image VA.
    for i in range(len(blob) - 3):
        w = struct.unpack_from("<I", blob, i)[0]
        if 0x55700000 <= w < 0x55A00000:
            raise RuntimeError("cave holds what looks like an absolute VA 0x%08X "
                               "at +0x%X -- it must be position-independent" % (w, i))
    return {C_TURN1: blob}


# ------------------------------------------------------------------ plumbing ---
def read_dll():
    if not os.path.exists(DLL):
        sys.exit("not found: %s" % DLL)
    with open(DLL, "rb") as f:
        d = bytearray(f.read())
    if _BASE is None:
        resolve_base(d)
    return d


def kill_game():
    """Standing authorization: the game/editor lock the binaries. Just kill them.
    ⚠ Match with ^...$ -- a bare -match also catches AowEmailWrapper, which does
    not lock anything and must be left alone."""
    # ⚠ SCRATCH GUARD: AOW_GAME_DIR set => we are NOT writing to the real install,
    # so we must NOT kill the user's running game.
    if os.environ.get("AOW_GAME_DIR"):
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match "
         "'^(AoW|AoWz|AoWCompat|AoWzCompat|AoWDevEd|AoWzEd|AoWEd|AoWSetup)$' }"
         " | Stop-Process -Force"],
        capture_output=True)


def state(d, caves):
    """-> 'vanilla' | 'applied' | 'mixed'"""
    orig, patch = orig_bytes(), patched_bytes()
    cur = bytes(d[off(HOOK):off(HOOK) + HOOK_LEN])
    applied = [cur == patch]
    vanilla = [cur == orig]
    for va, blob in caves.items():
        c = bytes(d[off(va):off(va) + len(blob)])
        applied.append(c == blob)
        vanilla.append(c == bytes(len(blob)))
    if all(applied):
        return "applied"
    if all(vanilla):
        return "vanilla"
    return "mixed"


def show(d, caves):
    orig, patch = orig_bytes(), patched_bytes()
    cur = bytes(d[off(HOOK):off(HOOK) + HOOK_LEN])
    tag = "PATCHED" if cur == patch else ("vanilla" if cur == orig
                                          else "*** FOREIGN ***")
    print("AoWEPACK.dpl  %s" % DLL)
    print("  map-placed heroes keep unspent skill points + get a turn-1 level-up prompt")
    print("  hook 0x%08X  %-8s  %d bytes  THero.NewDay day-1 confiscation block"
          % (HOOK, tag, HOOK_LEN))
    print("       now: %s" % cur.hex())
    for va, blob in sorted(caves.items()):
        c = bytes(d[off(va):off(va) + len(blob)])
        t = "PATCHED" if c == blob else ("zero" if c == bytes(len(blob))
                                         else "*** FOREIGN ***")
        print("  cave 0x%08X  %-8s  %d bytes" % (va, t, len(blob)))
    print("  state: %s" % state(d, caves).upper())


def disassemble(caves):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        sys.exit("capstone not installed:  pip install capstone")
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    names = {F_SKILLPOINTS: "THero.GetSkillPoints", F_GETLEVEL: "THero.GetLevel"}
    for va, blob in sorted(caves.items()):
        print("\n---- 0x%08X  C_TURN1  (keep the points, lag the level cache)" % va)
        for i in md.disasm(bytes(blob), va):
            note = ""
            if i.mnemonic == "call":
                try:
                    note = "  ; " + names.get(int(i.op_str, 16), "")
                except ValueError:
                    pass
            print("  %08X  %-22s %s %s%s" % (i.address, i.bytes.hex(), i.mnemonic,
                                             i.op_str, note.rstrip()))
    print("\n---- hook site, vanilla -> patched")
    for label, run in (("vanilla", orig_bytes()), ("patched", patched_bytes())):
        print("  %s  %s" % (label, run.hex()))
        for i in md.disasm(run, HOOK):
            print("    %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic,
                                             i.op_str))


def check_space(d, caves):
    """Every byte of the cave span must be zero or already ours."""
    span = bytes(d[off(CAVE_BASE):off(CAVE_END)])
    ours = bytearray(CAVE_END - CAVE_BASE)
    for va, blob in caves.items():
        ours[va - CAVE_BASE:va - CAVE_BASE + len(blob)] = blob
    for i, b in enumerate(span):
        if b != 0 and b != ours[i]:
            sys.exit("ABORT: cave span byte 0x%08X = 0x%02X, neither zero nor ours"
                     % (CAVE_BASE + i, b))


def do_apply(d, caves):
    st = state(d, caves)
    if st == "applied":
        print("already applied -- nothing to do.")
        return
    if st == "mixed":
        sys.exit("ABORT: partially applied / foreign bytes present. Run --undo first.")
    check_reloc(d)
    check_space(d, caves)
    orig = orig_bytes()
    cur = bytes(d[off(HOOK):off(HOOK) + HOOK_LEN])
    if cur != orig:
        sys.exit("ABORT: 0x%08X is %s, expected %s" % (HOOK, cur.hex(), orig.hex()))

    kill_game()
    if not os.path.exists(BACKUP):          # ⚠ minted on --apply ONLY
        import shutil
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> %s" % os.path.basename(BACKUP))

    for va, blob in caves.items():
        d[off(va):off(va) + len(blob)] = blob
    d[off(HOOK):off(HOOK) + HOOK_LEN] = patched_bytes()
    with open(DLL, "wb") as f:
        f.write(d)
    print("APPLIED: 1 cave, 1 site.")


def do_undo(d, caves):
    st = state(d, caves)
    if st == "vanilla":
        print("not applied -- nothing to undo.")
        return
    orig, patch = orig_bytes(), patched_bytes()
    cur = bytes(d[off(HOOK):off(HOOK) + HOOK_LEN])
    if cur not in (orig, patch):
        sys.exit("ABORT: 0x%08X is foreign (%s)" % (HOOK, cur.hex()))
    for va, blob in caves.items():
        c = bytes(d[off(va):off(va) + len(blob)])
        if c not in (blob, bytes(len(blob))):
            sys.exit("ABORT: cave 0x%08X is foreign" % va)

    kill_game()
    d[off(HOOK):off(HOOK) + HOOK_LEN] = orig
    for va, blob in caves.items():
        d[off(va):off(va) + len(blob)] = bytes(len(blob))
    with open(DLL, "wb") as f:
        f.write(d)
    print("UNDONE: hook restored, cave zeroed. No backup touched.")


def main():
    args = sys.argv[1:]
    d = read_dll()
    caves = build_caves()
    if "--dis" in args:
        disassemble(caves)
    if "--undo" in args:
        do_undo(d, caves)
    elif "--apply" in args:
        do_apply(d, caves)
    else:
        show(d, caves)
        if "--dis" not in args:
            print("\n(dry run -- pass --apply to write, --dis to disassemble the cave)")
        return
    show(read_dll(), caves)


if __name__ == "__main__":
    main()
