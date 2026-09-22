#!/usr/bin/env python3
r"""
AoW1 mod -- "turn1upgrade": a hero holding unspent skill points is OFFERED them.

FULL ANALYSIS: Modding Resources/Zig notes/01-combat-maths.md  section 5,
               "Hero skill points -- the budget, the price list, and the hero library"

================================================================================
THE PROBLEM, AS MEASURED (2026-09-22, live process + PBEM saves)
================================================================================
Set a leader to level 8 in the editor and it arrives in game with 44 of its 90
skill points unspent -- and NOTHING WILL EVER OFFER THEM.  The editor agrees the
points exist ("Skill Points 44/90" in Leader Properties); the game simply has no
path that opens the spend UI.

The level-up dialog is raised by THero.ValidateHeroUpgrade @0x55787D54, called
from THero.NewTurn @0x55787FE7 on the owner's turn.  Its trigger is a LAG, not an
event:

    if (hero.levelCache[+0x4C] < GetLevel())          ; GetLevel derives from XP [+0x48]
        hero.levelCache = GetLevel()
        raise THeroUpgradeEventLog(old -> new)        ; this IS the level-up dialog
        if (player[+0xA7] != 0) ExecuteUpgradeHeroAI  ; AI spends its own

⚠⚠ A level SET in the editor can never satisfy that condition.  THero.SetLevel
@0x55787750 writes BOTH `[+0x48] = LevelToExperience(level)` and `[+0x4C] = level`,
so cache == GetLevel() from the moment the map loads.  Measured live: Grozt at
cache 8 / XP 170, where LevelToExperience(8) is exactly 170.  The points stay
stranded until the hero naturally earns past the NEXT threshold -- level 9 at
XP 200 -- and everything banked below that is simply never offered.

So the fix is to create the lag artificially whenever a hero has points to spend.

================================================================================
WHY THE HOOK IS IN NewTurn AND NOT NewDay  (v1 was wrong -- corrected 2026-09-22)
================================================================================
v1 put the decrement in the day-1 branch of THero.NewDay @0x55786C3C, replacing
vanilla's skill-point confiscation there:

    55786C4B  cmp dword ptr [map+0x174], 1     ; the DAY COUNTER -> day 1 only
    55786CBA  mov dword ptr [ebx+0x50], eax    ; bank the unspent pool as a write-off

**It never fired.**  Measured with an out-of-band ReadProcessMemory poller across a
real PBEM game start: map loaded with `map[+0x174] == 1`, every leader read
`[+0x50] == 0`, and at the sample immediately before ValidateHeroUpgrade ran (XP
still exactly 170, i.e. pre-award) Grozt's cache already read 8, not 7.  All three
guards passed on those values, so the block itself did not execute for heroes at
game start.  `TPlayerControl.NewDay+0x27 @0x55754DCB` is the only incrementer of
the counter and `TAoWHSMap.Create+0x32E` the only other writer, so the gate value
is right -- but whatever dispatches per-unit NewDay does not reach heroes on the
first day.  Not chased further: NewTurn is provably on the path, so use it.

NewTurn IS proven live: the same poller watched XP move 170 -> 172 for Grozt and
45 -> 47 for the other three leaders on turn 1, and that award is emitted by
ValidateHeroUpgrade itself.

⭐ GENERALISABLE: three static guards all passing is not evidence the code ran.
Only an execution trace is.  This cost a full build-and-test cycle.

================================================================================
WHAT THIS PATCH DOES -- two sites, one cave
================================================================================
SITE 1  0x55786CB3, 10 bytes -> 10x nop.  Removes vanilla's day-1 confiscation
        so an unspent pool survives if that block ever does execute.  Both inbound
        jumps land on the run's boundaries (`je 0x55786CB3` from 0x55786CA0,
        `jne 0x55786CBD` from 0x55786CB1), so the whole run is safe to blank.
        ⚠ Kept even though the block was not observed to run: it is vanilla's only
        writer of [hero+0x50] in the module, and leaving it armed would let a
        confiscation land on any path that does reach it.

SITE 2  0x55787FE7, 5 bytes.  `call ValidateHeroUpgrade` retargeted to the cave --
        the call-retarget idiom: 4 displacement bytes change, nothing is displaced,
        and --undo is the original rel32.  The cave tail-jumps to the real
        ValidateHeroUpgrade, so its semantics are untouched.

C_TURN1 = 0x5584B000, PIC (three rel32 transfers, no absolute operand, no anchor).
  entry: EAX = hero, as ValidateHeroUpgrade expects.

    push ebx / mov ebx,eax
    call THero.GetSkillPoints @0x557875C4 / test eax,eax / jle done      ; guard 1
    mov eax,ebx / call THero.GetLevel @0x55787740
    movsx eax,al / movzx edx,byte [ebx+0x4C] / cmp eax,edx / jl done     ; guard 2
    cmp dl,1 / jbe done                                                  ; guard 3
    dec byte [ebx+0x4C]
  done: mov eax,ebx / pop ebx / jmp THero.ValidateHeroUpgrade @0x55787D54

ValidateHeroUpgrade then sees cache < GetLevel(), raises the dialog, and restores
the cache in the same call.  EDX/ECX are clobbered, which is safe: the call site
sets only EAX (`mov eax,esi` at 0x55787FE5) and ValidateHeroUpgrade overwrites its
third argument before reading it.

================================================================================
THE THREE GUARDS, AND WHY EACH IS LOAD-BEARING
================================================================================
1. GetSkillPoints() > 0.  The whole point: offer only when there is something to
   assign.  It is also what makes the behaviour self-limiting -- once the player
   spends, the guard stops firing.  ⚠ A hero who DECLINES the dialog is offered it
   again next turn, by design: the alternative is stranding the points again.
2. GetLevel() >= levelCache.  ⚠⚠ THE DANGEROUS ONE.  [hero+0x4C] is tag 0x16 and
   is PERSISTED.  If the cache were ever above the XP-derived level, decrementing
   it would not be undone -- a permanent 10-point budget loss written into the
   save.  This guard makes the restore certain.
3. levelCache >= 2.  Floors the cache at 1; this write bypasses SetLevel's clamp.

SCOPE.  Every hero, every turn, on its owner's turn -- map-placed, recruited or
levelled in play.  AI-owned heroes included; ExecuteUpgradeHeroAI spends for them.

RNG    -- no draw of any kind, neither generator referenced.  Re-run
          re_tools/rng_audit.py --owners after --apply (standing rule); not a P4
          site, so --hash is not needed.
MP     -- deterministic: two pure reads and one byte decrement, no clock, no RNG,
          identical on every peer.  [hero+0x4C] and [hero+0x50] are both already
          streamed (THero.ReadWrite tags 0x16 and 0x27), so the save format does
          not move.  ⚠ Standing rule: no mixed modded / unmodded multiplayer.
BINARY -- AoWEPACK.dpl only.  THero.NewTurn and THero.NewDay live nowhere else, so
          there is no AoWz.exe / AoWzCompat.exe lockstep half.

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
SITE_NEWDAY   = 0x55786CB3      # THero.NewDay day-1 confiscation block, 10 bytes
NEWDAY_LEN    = 0x0A            # .. 0x55786CBC; 0x55786CBD is a jump target

SITE_NEWTURN  = 0x55787FE7      # THero.NewTurn: call ValidateHeroUpgrade, 5 bytes
NEWTURN_LEN   = 0x05

F_SKILLPOINTS = 0x557875C4      # AoWE.THero.GetSkillPoints        EAX=hero -> EAX=points
F_GETLEVEL    = 0x55787740      # AoWE.THero.GetLevel              EAX=hero -> AL=level from XP
F_VALIDATE    = 0x55787D54      # AoWE.THero.ValidateHeroUpgrade   EAX=hero

OFF_LEVEL     = 0x4C            # THero level cache, 1 byte, streamed as tag 0x16
OFF_WRITEOFF  = 0x50            # THero skill-point write-off, streamed as tag 0x27

CAVE_BASE = 0x5584B000
C_TURN1   = 0x5584B000
CAVE_END  = 0x5584B080          # asserted zero-or-ours across this whole span

_BASE = None                    # VA = file_offset + _BASE, resolved from the PE


def rel32(frm_end, to):
    return struct.pack("<i", to - frm_end)


def orig_newday():
    """The 10-byte vanilla confiscation run, rebuilt rather than hard-coded."""
    return (bytes.fromhex("8bc3")                              # mov eax, ebx
            + b"\xE8" + rel32(SITE_NEWDAY + 2 + 5, F_SKILLPOINTS)
            + b"\x89\x43" + bytes([OFF_WRITEOFF]))             # mov [ebx+0x50], eax


def patched_newday():
    return b"\x90" * NEWDAY_LEN


def orig_newturn():
    return b"\xE8" + rel32(SITE_NEWTURN + 5, F_VALIDATE)


def patched_newturn():
    return b"\xE8" + rel32(SITE_NEWTURN + 5, C_TURN1)


SITES = {
    SITE_NEWDAY:  (orig_newday,  patched_newday,  NEWDAY_LEN,
                   "THero.NewDay day-1 confiscation block -> nops"),
    SITE_NEWTURN: (orig_newturn, patched_newturn, NEWTURN_LEN,
                   "THero.NewTurn: call ValidateHeroUpgrade -> C_TURN1"),
}


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
        for a in (SITE_NEWDAY, SITE_NEWDAY + NEWDAY_LEN - 1, SITE_NEWTURN,
                  F_SKILLPOINTS, F_GETLEVEL, F_VALIDATE, CAVE_BASE, CAVE_END - 1):
            if not lo <= a < hi:
                sys.exit("ABORT: 0x%08X is outside CODE (0x%08X..0x%08X)" % (a, lo, hi))
        return
    sys.exit("ABORT: no CODE section in %s" % DLL)


def check_reloc(d):
    """⚠ A stale .reloc entry corrupts live code at every load and is invisible to
    every other static check (aow1-stale-reloc-corrupts-code).  Nothing here is
    displaced, but a pre-existing entry pointing INTO a rewritten run or into the
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
    owned = [(SITE_NEWDAY, NEWDAY_LEN), (SITE_NEWTURN, NEWTURN_LEN),
             (CAVE_BASE, CAVE_END - CAVE_BASE)]
    bad, end, p = [], foff + size, foff
    while p < end - 8:
        page, blk = struct.unpack_from("<II", d, p)
        if blk < 8:
            break
        for q in range(p + 8, p + blk, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 0:
                continue
            t = image_base + page + (e & 0xFFF)
            if any(a <= t < a + n for a, n in owned):
                bad.append(t)
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
        # tail-call the real thing with EAX = hero, exactly as the call site had it
        ("DONE", "mov eax, ebx"),
        (None,   "pop ebx"),
        (None,   "jmp %s" % hex(F_VALIDATE)),
    ], C_TURN1)
    if len(blob) > CAVE_END - CAVE_BASE:
        raise RuntimeError("cave is %d bytes, the span is %d"
                           % (len(blob), CAVE_END - CAVE_BASE))
    # position-independence: the .dpl never loads at its preferred base, so no
    # absolute memory reference may appear. Every transfer is rel32; assert no
    # dword in the blob looks like an image VA.
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
    if os.environ.get("AOW_GAME_DIR"):      # scratch guard: not the real install
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match "
         "'^(AoW|AoWz|AoWCompat|AoWzCompat|AoWDevEd|AoWzEd|AoWEd|AoWSetup)$' }"
         " | Stop-Process -Force"],
        capture_output=True)


def state(d, caves):
    applied, vanilla = [], []
    for va, (orig_fn, patch_fn, n, _desc) in SITES.items():
        cur = bytes(d[off(va):off(va) + n])
        applied.append(cur == patch_fn())
        vanilla.append(cur == orig_fn())
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
    print("AoWEPACK.dpl  %s" % DLL)
    print("  a hero holding unspent skill points is offered them on its owner's turn")
    for va in sorted(SITES):
        orig_fn, patch_fn, n, desc = SITES[va]
        cur = bytes(d[off(va):off(va) + n])
        tag = ("PATCHED" if cur == patch_fn() else
               "vanilla" if cur == orig_fn() else "*** FOREIGN ***")
        print("  site 0x%08X  %-8s  %2d B  %s" % (va, tag, n, desc))
        print("       now: %s" % cur.hex())
    for va, blob in sorted(caves.items()):
        c = bytes(d[off(va):off(va) + len(blob)])
        t = ("PATCHED" if c == blob else
             "zero" if c == bytes(len(blob)) else "*** FOREIGN ***")
        print("  cave 0x%08X  %-8s  %d bytes" % (va, t, len(blob)))
    print("  state: %s" % state(d, caves).upper())


def disassemble(caves):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        sys.exit("capstone not installed:  pip install capstone")
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    names = {F_SKILLPOINTS: "THero.GetSkillPoints", F_GETLEVEL: "THero.GetLevel",
             F_VALIDATE: "THero.ValidateHeroUpgrade"}
    for va, blob in sorted(caves.items()):
        print("\n---- 0x%08X  C_TURN1  (lag the cache when points are unspent)" % va)
        for i in md.disasm(bytes(blob), va):
            note = ""
            if i.mnemonic in ("call", "jmp"):
                try:
                    note = "  ; " + names.get(int(i.op_str, 16), "")
                except ValueError:
                    pass
            print("  %08X  %-22s %s %s%s" % (i.address, i.bytes.hex(), i.mnemonic,
                                             i.op_str, note.rstrip()))
    for va in sorted(SITES):
        orig_fn, patch_fn, _n, desc = SITES[va]
        print("\n---- site 0x%08X  %s" % (va, desc))
        for label, run in (("vanilla", orig_fn()), ("patched", patch_fn())):
            print("  %s  %s" % (label, run.hex()))
            for i in md.disasm(run, va):
                print("    %08X  %-22s %s %s" % (i.address, i.bytes.hex(),
                                                 i.mnemonic, i.op_str))


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
    for va, (orig_fn, _p, n, _desc) in SITES.items():
        cur = bytes(d[off(va):off(va) + n])
        if cur != orig_fn():
            sys.exit("ABORT: 0x%08X is %s, expected %s"
                     % (va, cur.hex(), orig_fn().hex()))

    kill_game()
    if not os.path.exists(BACKUP):          # ⚠ minted on --apply ONLY
        import shutil
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("backup -> %s" % os.path.basename(BACKUP))

    for va, blob in caves.items():
        d[off(va):off(va) + len(blob)] = blob
    for va, (_o, patch_fn, n, _desc) in SITES.items():
        d[off(va):off(va) + n] = patch_fn()
    with open(DLL, "wb") as f:
        f.write(d)
    print("APPLIED: 1 cave, %d sites." % len(SITES))


def do_undo(d, caves):
    st = state(d, caves)
    if st == "vanilla":
        print("not applied -- nothing to undo.")
        return
    for va, (orig_fn, patch_fn, n, _desc) in SITES.items():
        cur = bytes(d[off(va):off(va) + n])
        if cur not in (orig_fn(), patch_fn()):
            sys.exit("ABORT: 0x%08X is foreign (%s)" % (va, cur.hex()))
    for va, blob in caves.items():
        c = bytes(d[off(va):off(va) + len(blob)])
        if c not in (blob, bytes(len(blob))):
            sys.exit("ABORT: cave 0x%08X is foreign" % va)

    kill_game()
    for va, (orig_fn, _p, n, _desc) in SITES.items():
        d[off(va):off(va) + n] = orig_fn()
    for va, blob in caves.items():
        d[off(va):off(va) + len(blob)] = bytes(len(blob))
    with open(DLL, "wb") as f:
        f.write(d)
    print("UNDONE: %d sites restored, cave zeroed. No backup touched." % len(SITES))


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
