#!/usr/bin/env python3
r"""
AoW1 mod -- "terroratk12": the Terror spell's ATTACK value, 16 -> 12.

Pure immediate rewrite. No cave, no hook, no keystone, no relocation, nothing
displaced. Five instruction immediates change value in place, same widths.

================================================================================
THE NUMBER
================================================================================
User decision, final: Terror's ATK is 12 in the current (doubled) Ziggurat scale.

Its provenance, because this constant has been misread once already:

    vanilla  AoWEPACK_original_backup.dpl  ..........  6   (all five sites)
    live before this patch  ....................... 16
    live after this patch  ........................ 12

The 6 -> 8 step was an UNDOCUMENTED pre-convention Ziggurat change that was
already in the install before the 5% conversion ran. The hit-chance audit
sampled the *installed* DLL, recorded 8, and the doubling pass took 8 -> 16.
So "8 -> 16" in Zig notes/_old/FivePct_Doubled_Sources_Inventory.md was doubling
a Ziggurat value, not a vanilla one -- vanilla was 6 and would have doubled to
12, which is exactly the value this script restores. (Those _old/ files are
historical records of what the conversion did and are accurate as such; they are
deliberately NOT edited. See Zig notes/01-combat-maths.md.)

    *** --undo restores 16, NOT vanilla 6. ***
    The undo target is the pre-change live state, per project convention.

================================================================================
THE FIVE SITES -- ALL MUST MOVE TOGETHER
================================================================================
Terror's power is encoded FIVE times, not two or three. Copies 4 and 5 were
missed by the original hit-chance audit and only caught by the 5% conversion
sweep (Zig notes/_old/HitChance_Increment_Audit.md:222 records the correction).

A partial edit is SILENT: the spell would use different powers in tactical vs
auto-resolve vs the AI's own damage estimate, and nothing would report it. Hence
the all-or-nothing state machine below -- any disagreement between the five is
"mixed" and aborts.

  # immVA       file off  w  instruction                function
  1 0x557F9A81  0x0F8E81  1  mov byte ptr [eax], imm8   TTerror.Create
                                (spell ATK stat, [self+0x34]; `lea eax,[ebx+0x34]`
                                 sits at 0x557F9A7C immediately above)
  2 0x557F9887  0x0F8C87  4  mov eax, imm32             TFastCombatTerrorCA.Generate
  3 0x557F9A0B  0x0F8E0B  4  mov eax, imm32             TTacticalCombatTerrorCA.Generate
  4 0x557F9CA6  0x0F90A6  4  mov eax, imm32             TTerror.fcGetDamageValueEx
  5 0x557F9D8F  0x0F918F  4  mov eax, imm32             TTerror.tcGetDamageValueEx

Sites 2-5 are the identical idiom -- the power, minus the defender's stat, into
the to-hit roll:

    movsx eax, al          ; defender stat
    push  eax
    mov   eax, POWER       ; <-- the immediate this script rewrites
    pop   edx
    sub   eax, edx
    call  HitRole            (sites 2,3 -- 0x55725D98)
    call  HitRoleProbability (sites 4,5 -- 0x55725DCC)

Site 4 lives in fcGetDamageValueEx, which is DEAD CODE for Terror (VMT +0x98 is
overridden but never called -- fcPrefetchCombatCommands accumulates the value
inline; see Zig notes/10-ai-and-structures.md). It is rewritten anyway so the
five never disagree: a future session that revives that path must not find a
stale 16 in it.

*** DO NOT touch 0x557F9A85 (`mov byte ptr [eax+1], 0`, TTerror damage
[self+0x35]). It is 0 in both live and pristine and is not an ATK site. ***

VERIFY-BEFORE-WRITE covers the OPCODE, not just the immediate: each site asserts
its `c6 00` / `b8` prefix, so a wrong address aborts instead of corrupting a
neighbouring instruction.

================================================================================
NOT A CAVE FEATURE -- what this does NOT interact with
================================================================================
.reloc     scanned: ZERO relocation entries touch any of the five sites, so the
           loader does not rewrite these bytes and a file patch is authoritative.
           (These are plain immediates, not addresses -- expected, but checked.)

build_terror_oncepercombat.py  (APPLIED) -- checked, no overlap with anything it
           owns: hooks 0x5572708C(5) / 0x557F991E(8) / 0x557F9B20(7) /
           0x557F9BE8(5), VMT slot 0x557F625C(4), caves 0x5582A000-0x5582A200.
           Its C_WRAPTC wrapper CALLS tcGetDamageValueEx (0x557F9D44) unchanged
           and its verifier checks hook runs / slot value / cave bytes only --
           none of which include site 5 at 0x557F9D8F inside that function. It
           still dry-runs APPLIED afterwards.

build_leadership_fearless.py   (APPLIED) -- checked, no overlap: its four
           retargeted `call rel32` + nop runs are at 0x557F9844, 0x557F99C8,
           0x557F9B6B, 0x557F9D55 (8 bytes each).

Neighbouring spells left alone: TSacredWrath.Create 0x557F9717 (live 12) and
TWindsOfFury.Create 0x557F9E5F (live 16, pristine 8 -- a real doubling). Both
are different classes and are NOT sixth copies of Terror's power.

RNG    no cave, no draw -- the SYNCED/RAW rule does not apply.
MP     a constant baked into every peer's DLL identically; nothing to desync.
.pfs   untouched. Terror's power is code-side only.

================================================================================
USAGE
================================================================================
    python build_scripts/build_terror_atk12.py            # verify only (default)
    python build_scripts/build_terror_atk12.py --show     # same, explicit
    python build_scripts/build_terror_atk12.py --dis      # + disassembly
    python build_scripts/build_terror_atk12.py --apply
    python build_scripts/build_terror_atk12.py --undo     # surgical: back to 16

RE-TUNING is a one-line edit: change TARGET_ATK, and add the value being
superseded to ACCEPT so verify-before-write still recognises the installed
bytes. Never revert-and-reapply -- there is no backup stack.
"""
import os
import shutil
import subprocess
import sys

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

DLL = os.path.join(GAME, "AoWEPACK.dpl")
PRISTINE = os.path.join(GAME, "Modding Resources", "AoWEPACK_original_backup.dpl")

BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-terroratk12")

BASE = 0x55700C00                  # CODE section: VA = file_offset + BASE

# ------------------------------------------------------------------ the value --
TARGET_ATK = 12                    # <-- THE DESIGN VALUE. A re-tune is this line.
PREV_ATK = 16                      # pre-change live value; --undo restores THIS
VANILLA_ATK = 6                    # pristine reference only -- never written

# verify-before-write accepts any of these as a known installed state; a re-tune
# appends the superseded value here so the new script still recognises the old
# bytes (per the in-place-rewrite convention -- never revert-and-reapply).
ACCEPT = (PREV_ATK, TARGET_ATK)

# ------------------------------------------------------------------ the sites --
# (va_of_immediate, width, opcode_prefix_bytes, label)
# The prefix is asserted immediately BEFORE the immediate, so a wrong address
# aborts rather than mangling a neighbouring instruction.
SITES = [
    (0x557F9A81, 1, b"\xC6\x00", "TTerror.Create              spell ATK [self+0x34]"),
    (0x557F9887, 4, b"\xB8",     "TFastCombatTerrorCA.Generate      auto-resolve"),
    (0x557F9A0B, 4, b"\xB8",     "TTacticalCombatTerrorCA.Generate  tactical"),
    (0x557F9CA6, 4, b"\xB8",     "TTerror.fcGetDamageValueEx        AI value (dead code)"),
    (0x557F9D8F, 4, b"\xB8",     "TTerror.tcGetDamageValueEx        AI value, tactical"),
]

# --dis lead-in: bytes to back up from the OPCODE so the window starts on a real
# instruction boundary. Site 1's is `lea eax,[ebx+0x34]` (3); sites 2-5 open with
# `movsx eax,al` + `push eax` (4). Guessed lead-ins decode as garbage -- these are
# measured against the live bytes.
DIS_LEAD = {0x557F9A81: 3, 0x557F9887: 4, 0x557F9A0B: 4, 0x557F9CA6: 4, 0x557F9D8F: 4}
DIS_LEN = {0x557F9A81: 12, 0x557F9887: 20, 0x557F9A0B: 20, 0x557F9CA6: 20, 0x557F9D8F: 20}


def off(va):
    return va - BASE


def read_dll():
    if not os.path.exists(DLL):
        sys.exit("not found: %s" % DLL)
    with open(DLL, "rb") as f:
        return bytearray(f.read())


def imm(d, va, w):
    return int.from_bytes(d[off(va):off(va) + w], "little")


def kill_game():
    """Standing authorization: the game/editor lock the binaries. Just kill them."""
    # SCRATCH GUARD: AOW_GAME_DIR set => we are not writing to the real install,
    # so we must not kill the user's running game.
    if os.environ.get("AOW_GAME_DIR"):
        return
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process | Where-Object { $_.ProcessName -match '^(AoW|AoWCompat|AoWDevEd|AoWEd)$' }"
         " | Stop-Process -Force"],
        capture_output=True)


def check_opcodes(d):
    """Abort unless every site's opcode prefix is exactly where it should be.
    This is what turns a wrong address into an abort instead of a corrupted
    instruction stream."""
    for va, w, pre, label in SITES:
        cur = bytes(d[off(va) - len(pre):off(va)])
        if cur != pre:
            sys.exit("ABORT: 0x%08X opcode prefix is %s, expected %s (%s)\n"
                     "       The address is wrong or the site has moved. "
                     "Nothing written."
                     % (va, cur.hex(), pre.hex(), label))
        if w == 1 and max(ACCEPT) > 0xFF:
            sys.exit("ABORT: 0x%08X is an imm8 site but a value > 255 is configured." % va)


def state(d):
    """-> 'applied' | 'pre' | 'mixed' | 'foreign'

    'mixed' is the important one: a PARTIAL edit is otherwise silent, because the
    spell would simply use different powers in different combat modes."""
    vals = [imm(d, va, w) for va, w, _, _ in SITES]
    if len(set(vals)) != 1:
        return "mixed"
    v = vals[0]
    if v == TARGET_ATK:
        return "applied"
    if v == PREV_ATK:
        return "pre"
    return "foreign"


def pristine_vals():
    """The five values in the pristine DLL, or None if it is not present."""
    if not os.path.exists(PRISTINE):
        return None
    with open(PRISTINE, "rb") as f:
        p = bytearray(f.read())
    return [imm(p, va, w) for va, w, _, _ in SITES]


def show(d):
    print("AoWEPACK.dpl  %s" % DLL)
    print("  Terror ATK:  vanilla %d  ->  pre-change %d  ->  target %d"
          % (VANILLA_ATK, PREV_ATK, TARGET_ATK))
    pv = pristine_vals()
    for i, (va, w, pre, label) in enumerate(SITES):
        cur = imm(d, va, w)
        raw = bytes(d[off(va) - len(pre):off(va) + w]).hex()
        tag = ("TARGET" if cur == TARGET_ATK else
               "pre-change" if cur == PREV_ATK else "*** FOREIGN ***")
        vtag = "" if pv is None else "  vanilla=%d" % pv[i]
        print("  %d 0x%08X off 0x%06X w%d  %-16s = %-4d %-14s%s"
              % (i + 1, va, off(va), w, raw, cur, tag, vtag))
        print("      %s" % label)
    st = state(d)
    print("  state: %s" % st.upper())
    if st == "mixed":
        print("  *** THE FIVE SITES DISAGREE -- Terror would use different powers in")
        print("  *** tactical vs auto-resolve vs the AI estimate. Fix before playing.")


def disassemble(d):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        sys.exit("capstone not installed:  pip install capstone")
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for i, (va, w, pre, label) in enumerate(SITES):
        start = va - len(pre) - DIS_LEAD[va]
        n = DIS_LEN[va]
        print("\n---- site %d  0x%08X  %s" % (i + 1, va, label))
        for ins in md.disasm(bytes(d[off(start):off(start) + n]), start):
            mark = "   <== the immediate" if ins.address == va - len(pre) else ""
            print("  %08X  %-14s %s %s%s"
                  % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str, mark))


def write_value(d, value, what):
    st = state(d)
    if st == "foreign":
        sys.exit("ABORT: the five sites all read %d, which is neither %d nor %d. "
                 "Foreign bytes -- nothing written."
                 % (imm(d, *SITES[0][:2]), PREV_ATK, TARGET_ATK))
    if st == "mixed":
        vals = [imm(d, va, w) for va, w, _, _ in SITES]
        sys.exit("ABORT: the five sites disagree (%s). A partial edit is already "
                 "present -- resolve it by hand before writing." % vals)
    cur = imm(d, *SITES[0][:2])
    if cur == value:
        print("already %d at all five sites -- nothing to do." % value)
        return False
    check_opcodes(d)

    kill_game()

    # BACKUP GATE -- only ever snapshot a file PROVED to be the pre-change state.
    # An --undo runs over our own output by definition, and a re-tune runs over a
    # previous --apply's output; both would mint a `.pre-*` that looks
    # authoritative while containing a patched state. So: snapshot only when
    # every site still reads PREV_ATK.
    if cur == PREV_ATK and value == TARGET_ATK:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if not os.path.exists(BACKUP):
            shutil.copy2(DLL, BACKUP)
            print("backup -> backups\\%s" % os.path.basename(BACKUP))
        else:
            print("backup exists, left alone: backups\\%s" % os.path.basename(BACKUP))
    else:
        print("no backup taken (current state is not the pre-change one -- "
              "a snapshot here would capture patched bytes).")

    for va, w, _, _ in SITES:
        d[off(va):off(va) + w] = value.to_bytes(w, "little")
    with open(DLL, "wb") as f:
        f.write(d)
    print("%s: Terror ATK %d -> %d at all five sites." % (what, cur, value))
    return True


def main():
    args = sys.argv[1:]
    d = read_dll()
    if "--dis" in args:
        disassemble(d)
    if "--undo" in args:
        write_value(d, PREV_ATK, "UNDONE")
    elif "--apply" in args:
        write_value(d, TARGET_ATK, "APPLIED")
    else:
        show(d)
        if "--dis" not in args:
            print("\n(dry run -- pass --apply to write, --dis to disassemble the sites)")
        return
    show(read_dll())


if __name__ == "__main__":
    main()
