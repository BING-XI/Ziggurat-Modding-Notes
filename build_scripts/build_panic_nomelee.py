r"""Panicked units cannot INITIATE melee, but still retaliate.

Design: copy vanilla's flying rule exactly.  AoW1 forbids a non-flying unit from initiating melee
on a flying one purely through the "may I initiate?" gates -- `TMeleeRound.Calculate` itself has no
flying test, which is why the ground unit still retaliates against the flyer that dived on it.
Gating Panicked (ability 0x6C) at the same gates inherits that behaviour with no change to any
combat arithmetic.

The first five sites begin with the identical vanilla instruction `mov edx,1` (BA 01 00 00 00) --
the first half of the flying test -- so an E9 rel32 hook displaces exactly one instruction and
nothing else.  Each cave performs the *same object load the vanilla flying test performs*, only
with ability id 0x6C, which is what makes the register/type assumptions safe by construction.

    file            hook VA     function                                        gates
    AoWTCPCK.dpl    0x0041FA7F  TCombatUnitSelectionControl.UpdateMoveCursor    player's attack cursor
    AoWTCPCK.dpl    0x00415478  TCAI.CheckUnit                                  tactical AI evaluation
    AoWTCPCK.dpl    0x00408749  TCombatMoveTE.ExecuteDefaultMove                free / opportunity swing
    AoWTCPCK.dpl    0x00422CE8  TTacticalCombatUnitHS.MeleeMoveTC               player's click-to-attack
    AoWEPACK.dpl    0x55766B75  TStrikeAbility.CanExecuteMelee                  auto-resolve melee
    AoWEPACK.dpl    0x5576833D  TTouchAbility.CanTouch                          touch attacks (tactical + fast)

The touch hook sits INSIDE the `side(attacker) != side(target)` arm, so friendly touch abilities
(Healing, Command) are unaffected -- a panicked healer still heals.

`meleemove` -- the hard gate, added 2026-09-12 (user-reported bug)
----------------------------------------------------------------
The `cursor` hook only chooses a cursor GLYPH.  Its forbidden arm at 0x0041FABE writes
Self+0x2C := 0x59 and [[0x46c064]+0xC]+0x34 := 0x100 and returns; the click path never reads
either field.  A left-click therefore still launched the attack under the "blocked" cursor:

    TCombatUnitSelectionControl.MoveUnits @0x0041E280      (no cursor/validity test anywhere)
      -> MoveSelectedRoute @0x0041E01C                     call @0x0041E323
        -> MeleeMoveTC @0x00422CD8                         call @0x0041E1E6, attackerHS+0x34 == -1
          -> CreateTCMeleeMoveTE @0x00409BFC

`MeleeMoveTC` has exactly two callers (TCAI.EvalBattle @0x0041AB74, MoveSelectedRoute
@0x0041E1E6) and is the sole caller of `CreateTCMeleeMoveTE`, so it is the single chokepoint
for every deliberate tactical melee.  Gating it there is scope decision 4 of
`Zig notes/02-abilities-modded.md`, declined 2026-08-31 "still available if a hole turns up".

This is the one site whose hook displaces SIX bytes, not five:

    00422CE4  mov byte ptr [ebp-9], 0   ; Result := False   -- already run before the hook
    00422CE8  mov eax,[ebp-4]           ; \ displaced pair, re-run at the top of the cave
    00422CEB  mov eax,[eax+0x1c]        ; / EAX := attacker's TCombatUnit
    00422CEE  call 0x402544             ; GetPlayer -- READS EAX, hence the push/pop bracket
    ...
    00422D60  mov al,[ebp-9] / mov esp,ebp / pop ebp / ret

so the hook is `E9 rel32` + one `0x90`, and the forbid arm jumps to 0x00422D60, returning False
with no cleanup: [ebp-9] is still 0 and nothing has been allocated.  `MoveSelectedRoute` already
handles a False return (`test al,al / je 0x41e279` -> plain exit), the same path vanilla takes
when the token control refuses, so no new code path is created.

SIDE EFFECT, accepted: wall/gate smashing also runs through `MeleeMoveTC` (attackerHS+0x34 == -1
with a wall on the destination hex), so a panicked unit can no longer break walls.  That matches
what the `cursor` hook already displays -- it tests the attacker only and never looks at the
target's type -- so no wall exemption is wanted.

NOT gated, deliberately: ranged attacks (out of scope), retaliation (the point of the feature), and
`TSelfDestructAbility.CanTouch @0x55768EC4`, which does not call the inherited CanTouch and carries
no flying gate in vanilla either.  The `cursor` and `ai` hooks STAY: `cursor` is what tells the
player why the click does nothing, and `ai` stops the tactical AI wasting a turn walking into a
refusal.

Full derivation, the six vanilla flying sites, the scope decisions and the rejected approaches:
    Modding Resources/Zig notes/02-abilities-modded.md, "Panic -- cannot initiate melee"

Usage:
    python build_scripts/build_panic_nomelee.py            # verify current state (dry run)
    python build_scripts/build_panic_nomelee.py --dis      # + disassemble the caves
    python build_scripts/build_panic_nomelee.py --apply    # write
    python build_scripts/build_panic_nomelee.py --undo     # surgical revert (restore hooks, zero caves)

--apply snapshots each target to <game dir>/backups/<file>.pre-panicnomelee -- but ONLY when every
site in that file still reads vanilla. ⚠ The absence of a .pre-* file is not proof the file is
unpatched: adding the sixth site to an install that already carried the other five would otherwise
have minted a ".pre-panicnomelee" holding this script's own previous output. That snapshot is a
courtesy, not the revert path -- --undo is, and it touches no backup.
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys

import capstone
import keystone

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

FEATURE = "panicnomelee"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
PANICKED = 0x6C          # ability id, applied by Cause Fear 0x33
VMT_GETABILITYENABLED = 0xA8   # TCombatObject slot; forwards to [cu+0x4c].vtable[0x148]

# Vanilla bytes a hook site must show. PER-SITE: five sites displace `mov edx,1`, the head of the
# flying test; `meleemove` displaces a SIX-byte pair. Every site carries its own `vanilla=`.
VANILLA_MOVEDX1 = bytes([0xBA, 0x01, 0x00, 0x00, 0x00])            # mov edx, 1
VANILLA_LOADSELF = bytes([0x8B, 0x45, 0xFC, 0x8B, 0x40, 0x1C])     # mov eax,[ebp-4]; mov eax,[eax+0x1c]

# cave bases: large verified zero runs, clear of every existing feature's caves
CAVE_BASE = {
    "AoWEPACK.dpl": 0x55828000,   # inside the 0x55827018 run (788968 B free)
    "AoWTCPCK.dpl": 0x00438300,   # inside the 0x00438240 run (190912 B free)
}
CAVE_STRIDE = 0x40                # per-site slot; each cave is ~0x24 bytes

# ---------------------------------------------------------------------------
# site table.  `load` is the attacker load, mirroring the vanilla flying test's own load, and the
# cave is built from the shared template: push eax/ecx/edx, load, query, pop, then re-issue the
# displaced `mov edx,1` on the allowed path.
#
# A site may instead carry `body=` (an explicit cave head, ending with the flags set by `test al,al`)
# plus `restore=` (asm re-issued on the ALLOWED path before `jmp resume`, or None when the cave head
# already did the displaced work).  `meleemove` uses that override: its resume target reads EAX.
#
# ⚠ ORDER IS LOAD-BEARING. cave_va() numbers slots by a site's index WITHIN ITS FILE, so inserting a
# site anywhere but the end of its file's run renumbers every later cave and every installed site
# reports state=foreign. Append only.
# ---------------------------------------------------------------------------
SITES = [
    dict(file="AoWTCPCK.dpl", name="cursor",   hook=0x0041FA7F, resume=0x0041FA84,
         forbid=0x0041FABE, load=["mov eax, [ebp-0x10]", "mov eax, [eax+0x1c]"],
         vanilla=VANILLA_MOVEDX1,
         why="TCombatUnitSelectionControl.UpdateMoveCursor -- player's attack cursor"),
    dict(file="AoWTCPCK.dpl", name="ai",       hook=0x00415478, resume=0x0041547D,
         forbid=0x004158AF, load=["mov eax, [ebp+0x14]"],
         vanilla=VANILLA_MOVEDX1,
         why="TCAI.CheckUnit -- tactical AI melee evaluation"),
    dict(file="AoWTCPCK.dpl", name="freeswing", hook=0x00408749, resume=0x0040874E,
         forbid=0x0040880E, load=["mov eax, [ebp-0x10]", "mov eax, [eax+0x1c]"],
         vanilla=VANILLA_MOVEDX1,
         why="TCombatMoveTE.ExecuteDefaultMove -- free / opportunity swing"),
    # appended 2026-09-12 -- index 3 within AoWTCPCK.dpl -> cave 0x004383C0
    dict(file="AoWTCPCK.dpl", name="meleemove", hook=0x00422CE8, resume=0x00422CEE,
         forbid=0x00422D60, vanilla=VANILLA_LOADSELF,
         body=["mov eax, [ebp-4]",               # \ the two displaced instructions, run first
               "mov eax, [eax+0x1c]",            # / EAX = attacker's TCombatUnit
               "push eax",                       # resume target 0x00422CEE reads EAX
               f"mov edx, {PANICKED}",
               "mov ecx, [eax]",
               f"call dword ptr [ecx+{VMT_GETABILITYENABLED}]",
               "test al, al",
               "pop eax"],                       # pop does not touch flags
         restore=None,                           # cave head already ran the displaced pair
         why="TTacticalCombatUnitHS.MeleeMoveTC -- the player's click-to-attack hard gate"),
    dict(file="AoWEPACK.dpl", name="autoresolve", hook=0x55766B75, resume=0x55766B7A,
         forbid=0x55766B9B, load=["mov eax, esi"],
         vanilla=VANILLA_MOVEDX1,
         why="TStrikeAbility.CanExecuteMelee -- auto-resolve melee"),
    dict(file="AoWEPACK.dpl", name="touch",    hook=0x5576833D, resume=0x55768342,
         forbid=0x55768363, load=["mov eax, edi"],
         vanilla=VANILLA_MOVEDX1,
         why="TTouchAbility.CanTouch -- touch attacks, tactical + fast"),
]

LOCKING = ("AoW", "AoWCompat", "AoWDevEd", "AoWEd")


# ---------------------------------------------------------------------------
# minimal PE helper (VA -> file offset is PER SECTION)
# ---------------------------------------------------------------------------
class PEFile:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as fh:
            self.data = bytearray(fh.read())
        pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        if self.data[pe:pe + 4] != b"PE\0\0":
            raise SystemExit(f"{path}: not a PE file")
        nsec = struct.unpack_from("<H", self.data, pe + 6)[0]
        opt = struct.unpack_from("<H", self.data, pe + 20)[0]
        self.image_base = struct.unpack_from("<I", self.data, pe + 24 + 28)[0]
        self.sections = []
        off = pe + 24 + opt
        for i in range(nsec):
            s = off + i * 40
            name = self.data[s:s + 8].rstrip(b"\0").decode("latin1")
            vsize, vaddr, rawsz, raw = struct.unpack_from("<IIII", self.data, s + 8)
            chars = struct.unpack_from("<I", self.data, s + 36)[0]
            self.sections.append((name, vaddr, vsize, raw, rawsz, chars))

    def off(self, va):
        rva = va - self.image_base
        for name, vaddr, vsize, raw, rawsz, chars in self.sections:
            if vaddr <= rva < vaddr + max(vsize, rawsz):
                o = raw + (rva - vaddr)
                if o >= len(self.data):
                    raise SystemExit(f"{self.path}: VA {va:#x} outside raw data")
                return o
        raise SystemExit(f"{self.path}: VA {va:#x} in no section")

    def read(self, va, n):
        o = self.off(va)
        return bytes(self.data[o:o + n])

    def write(self, va, blob):
        o = self.off(va)
        self.data[o:o + len(blob)] = blob

    def section_of(self, va):
        rva = va - self.image_base
        for s in self.sections:
            if s[1] <= rva < s[1] + max(s[2], s[4]):
                return s
        return None

    def save(self):
        with open(self.path, "wb") as fh:
            fh.write(self.data)


# ---------------------------------------------------------------------------
def cave_va(site, index_within_file):
    return CAVE_BASE[site["file"]] + index_within_file * CAVE_STRIDE


def build_cave(site, cave):
    """Assemble the cave at its final VA so keystone emits correct rel32s (PIC)."""
    if "body" in site:
        body = list(site["body"])
        restore = site.get("restore")
    else:
        body = [
            "push eax", "push ecx", "push edx",
            *site["load"],
            f"mov edx, {PANICKED}",
            "mov ecx, [eax]",
            f"call dword ptr [ecx+{VMT_GETABILITYENABLED}]",
            "test al, al",
            "pop edx", "pop ecx", "pop eax",       # pops do not touch flags
        ]
        restore = "mov edx, 1"                     # the displaced instruction
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_32)
    head, _ = ks.asm("\n".join(body), cave)
    head = bytes(head)
    # jnz <forbidden-stub>  (2 bytes, short) ; [restore] ; jmp resume ; stub: jmp forbid
    tail_at = cave + len(head)
    allowed_src = (restore + "\n" if restore else "") + f"jmp {site['resume']:#x}"
    mov_jmp, _ = ks.asm(allowed_src, tail_at + 2)
    mov_jmp = bytes(mov_jmp)
    jnz = bytes([0x75, len(mov_jmp)])
    stub_at = tail_at + 2 + len(mov_jmp)
    stub, _ = ks.asm(f"jmp {site['forbid']:#x}", stub_at)
    blob = head + jnz + mov_jmp + bytes(stub)
    if len(blob) > CAVE_STRIDE:
        raise SystemExit(f"{site['name']}: cave {len(blob)} B exceeds stride {CAVE_STRIDE}")
    return blob


def hook_bytes(site, cave):
    """E9 rel32, NOP-padded out to the full displaced length (6 B at meleemove, 5 elsewhere)."""
    pad = len(site["vanilla"]) - 5
    if pad < 0:
        raise SystemExit(f"{site['name']}: displaced run {len(site['vanilla'])} B < 5, cannot hook")
    return b"\xE9" + struct.pack("<i", cave - (site["hook"] + 5)) + b"\x90" * pad


def disasm(blob, va, indent="      "):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return "\n".join(f"{indent}{i.address:08X}  {i.mnemonic:<7s} {i.op_str}"
                     for i in md.disasm(blob, va))


def check_pic(blob, va, tag):
    """A .dpl cave must carry no absolute memory reference."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    bad = []
    for ins in md.disasm(blob, va):
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                bad.append(f"{ins.address:08X} {ins.mnemonic} {ins.op_str}")
    if bad:
        raise SystemExit(f"{tag}: cave is NOT position-independent:\n  " + "\n  ".join(bad))


def kill_game():
    """Standing authorization: game files are locked while any AoW binary runs."""
    # ⚠ SCRATCH GUARD (2026-09-03): AOW_GAME_DIR set => we are NOT writing to the real
    # install, so we must NOT kill the user's running game. Without this, an agent doing a
    # "safe" scratch-copy round-trip still terminates the live game -- which happened, and
    # was misreported as a crash-on-expiry. Standing kill authorization applies to the real
    # install only.
    if os.environ.get("AOW_GAME_DIR"):
        return
    if sys.platform != "win32":
        return
    names = "|".join(LOCKING)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"Get-Process | Where-Object {{ $_.ProcessName -match '^({names})$' }} | Stop-Process -Force"],
        capture_output=True)


# ---------------------------------------------------------------------------
def plan():
    """Return {filename: [(site, cave_va, cave_blob, hook_blob)]}."""
    out = {}
    for site in SITES:
        out.setdefault(site["file"], []).append(site)
    built = {}
    for fname, sites in out.items():
        rows = []
        for i, site in enumerate(sites):
            cave = cave_va(site, i)
            blob = build_cave(site, cave)
            check_pic(blob, cave, f"{fname}:{site['name']}")
            rows.append((site, cave, blob, hook_bytes(site, cave)))
        built[fname] = rows
    return built


def state_of(pe, site, cave, blob, hook):
    """'vanilla' | 'installed' | 'foreign'"""
    live_hook = pe.read(site["hook"], len(site["vanilla"]))
    if live_hook == site["vanilla"]:
        return "vanilla"
    if live_hook == hook and pe.read(cave, len(blob)) == blob:
        return "installed"
    return "foreign"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the patch")
    ap.add_argument("--undo", action="store_true", help="surgical revert")
    ap.add_argument("--dis", action="store_true", help="disassemble every cave")
    args = ap.parse_args()

    if args.apply and args.undo:
        raise SystemExit("--apply and --undo are mutually exclusive")

    built = plan()
    if args.apply or args.undo:
        kill_game()

    for fname, rows in built.items():
        path = os.path.join(GAME, fname)
        if not os.path.isfile(path):
            raise SystemExit(f"missing {path}")
        pe = PEFile(path)
        print(f"\n=== {fname}  (image base {pe.image_base:#x}) ===")

        states = []
        for site, cave, blob, hook in rows:
            st = state_of(pe, site, cave, blob, hook)
            states.append(st)
            sec = pe.section_of(cave)
            print(f"  {site['name']:<12s} hook {site['hook']:#010x} -> cave {cave:#010x} "
                  f"[{len(blob)} B, {sec[0]}]  state={st}")
            print(f"      {site['why']}")
            if args.dis:
                print(disasm(blob, cave))

        if "foreign" in states:
            raise SystemExit(
                f"{fname}: a hook site holds bytes that are neither vanilla nor ours -- "
                "another patch owns it. Aborting without writing.")

        if args.undo:
            if all(s == "vanilla" for s in states):
                print("  nothing to undo (already vanilla)")
                continue
            for (site, cave, blob, hook), st in zip(rows, states):
                if st != "installed":
                    continue
                pe.write(site["hook"], site["vanilla"])  # restore the displaced instruction(s)
                pe.write(cave, b"\0" * len(blob))        # zero our own cave
            pe.save()
            print("  UNDONE (hooks restored, caves zeroed) -- no backup touched")
            continue

        if all(s == "installed" for s in states):
            print("  already installed, bytes verified identical -- nothing to do")
            continue

        # verify-before-write: every cave zone must still be free
        for site, cave, blob, hook in rows:
            zone = pe.read(cave, CAVE_STRIDE)
            if zone != b"\0" * CAVE_STRIDE and zone[:len(blob)] != blob:
                raise SystemExit(
                    f"{fname}: cave zone {cave:#x} is not free "
                    f"(first bytes {zone[:8].hex(' ').upper()}). Aborting.")

        if not args.apply:
            print("  DRY RUN -- would install the hooks above. Re-run with --apply.")
            continue

        # ⚠ Snapshot ONLY from a file PROVED unpatched. The absence of a .pre-* file is not proof:
        # an --apply that adds a SITE to an already-installed feature (2026-09-12, `meleemove`)
        # would otherwise mint a ".pre-panicnomelee" holding this script's own previous output.
        backup = os.path.join(BACKUP_DIR, os.path.basename(path) + f".pre-{FEATURE}")
        if all(s == "vanilla" for s in states):
            if not os.path.exists(backup):
                os.makedirs(BACKUP_DIR, exist_ok=True)
                shutil.copy2(path, backup)
                print(f"  backup -> {backup}")
        else:
            print("  no backup minted -- this file already carries part of the feature "
                  "(a snapshot now would be of patched bytes); --undo is the revert path")
        for site, cave, blob, hook in rows:
            pe.write(cave, blob + b"\0" * (CAVE_STRIDE - len(blob)))
            pe.write(site["hook"], hook)
        pe.save()
        print("  APPLIED")

    if not (args.apply or args.undo):
        print("\n(dry run -- nothing written)")


if __name__ == "__main__":
    main()
