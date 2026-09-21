#!/usr/bin/env python3
r"""
AoW1 Unit Spellcasting -- the "Spellcasting level >= spell tier" gate is for UNITS ONLY.

USER RULING 2026-09-03: "Spellcasting level should only restrict tier of spell that's castable
for units, not heroes."  A unit with the Spellcasting ability stays limited to spell tiers up to
its ability level; a HERO or the LEADER may cast anything the player has researched.

WHAT WAS WRONG
--------------
`build_spellcast_multiturn.py` M2 injects `cave_tiergate` into `THero.CanCastSpell @0x55789710`
at 0x5578974D (`E9 rel32 + NOP`, displacing `mov esi,eax ; movsx edx,[ebx+0x24]`).  That gate
compares `GetAbilityLevel(caster, 0x34)` against `TSpell+0x21` for EVERY caster.  Units reach
`THero.CanCastSpell` because Phase 1 unlocked the `is THero` gates, so hero and unit share the
one chokepoint -- and the 2026-07-06 decision was deliberately "units AND heroes".  That decision
is now reversed for heroes.

HOW THIS PATCHES IT -- 4 BYTES IN THE HOST BINARY
-------------------------------------------------
`cave_tiergate` occupies a 50-byte slot (0x5580D95E .. 0x5580D98F) hard-bounded by
`build_spellcast_persist.py`'s cave at 0x5580D990, and already uses 48 of it.  An IsClass test
costs ~25 bytes, so it cannot be added in place.  Rather than relocate another feature's cave,
this script RETARGETS THE EXISTING HOOK'S rel32 -- the only bytes it writes inside vanilla code
are the 4 displacement bytes at 0x5578974E.  Nothing is displaced, there is no resume hazard, and
`--undo` is a 4-byte write.  (Same idiom as the wrapper-thunk trick in `City_Flag_Bauble_Lag.md`,
applied to an `E9` instead of an `E8`.)

  cave_herotier @ 0x55846000 (own reserved zone, verified all-zero, no .reloc entries)
      in:  EAX = TSpell*            (from TSpellControl.GetSpell @0x55789748)
           EBX = caster             (THero / TLeader / TUnit / TAdjustableUnit)
           ESI = spell id, EDI = &err
      IsClass(caster, THero)?
        yes -> hero family (THero AND its subclass TLeader): replicate the two displaced
               instructions and jmp 0x55789753 == VANILLA behaviour, no tier test at all.
        no  -> jmp 0x5580D95E, i.e. straight into the untouched `cave_tiergate`, which still
               does the level>=tier compare for units.

`cave_tiergate` itself is NOT modified -- `build_spellcast_multiturn.py` keeps verifying it
byte-for-byte.  That script's hook entry gained this cave's address as a second accepted
"already applied" state so a dry run stays clean and a future `--apply` cannot clobber us.

WHY IsClass AND NOT A FIELD TEST
--------------------------------
`IsClass(obj, THero)` is the engine's own test and is true for `THero` *and* its descendant
`TLeader`, which is exactly the "heroes and leaders" set the ruling names.  Verified in this
file, not assumed: the class-reference cell `[0x55711FAC]` holds VMT 0x55711FEC whose
`[VMT-0x20]` ShortString reads "THero"; `[0x557121F8]` -> VMT 0x55712238 reads "TLeader".
The exe half (`cave_bookfilter`) already uses the same test through the exe's own classref
`[0x0045DFC4]`.

The level lookup is left exactly as it is: `cave_tiergate` reads Spellcasting `0x34` through
**VMT +0x144** (`mov ecx,[eax]; push 0x34; pop edx; call [ecx+0x144]`), the ITEM-AWARE slot --
not the self-only `+0x84`.  That was the 2026-08-28 fix and this patch does not disturb it.

⚠⚠ MANDATORY COMPANION HALF, IN ANOTHER FEATURE'S SCRIPT
--------------------------------------------------------
This patch is HALF the ruling and on its own is a SILENT NO-OP.  The casting BOOK is pruned by
`cave_bookfilter @0x0060C0A8` in AoW.exe / AoWCompat.exe: until its `_loop` also exempts heroes,
a hero never SEES a too-high-tier spell, so nothing observable changes.  That cave belongs to

    build_scripts/build_scroll_spellbook.py      <- the exe half lives HERE, not in this file

where the `_loop` prune was reordered on 2026-09-03 (hero-family test first, `jne _keep`, tier and
Cosmos prunes unit-only).  It is a size-neutral reorder -- 36 bytes before and after -- because
`.sc` has 0 spare bytes.  Apply / verify BOTH:

    python build_scripts/build_spellcast_herotier.py --apply     # this file, AoWEPACK.dpl
    python build_scripts/build_scroll_spellbook.py  --apply      # AoW.exe + AoWCompat.exe

⚠ `build_scroll_spellbook.py --undo` RESTORES THE OLD EVERYONE-TIER-PRUNED FILTER and therefore
silently re-breaks the hero exemption -- verified 2026-09-03: after that undo,
`build_spellcast_book_exe.py` reports a clean `6 already, 0 to patch` while heroes are tier-limited
again, and nothing anywhere says so.  Revert order for the whole ruling:

    python build_scripts/build_spellcast_herotier.py --undo --apply    # DLL first
    python build_scripts/build_scroll_spellbook.py  --undo --apply     # exes second

Undoing THIS file alone is safe and independent: it just puts every caster back under the gate.

PIC
---
The DPL never loads at its preferred base.  The classref cell is reached with the standard
`call $+5 ; pop ecx ; sub ecx, <L1 preferred VA>` rebase-delta anchor; `@IsClass` (0x557010C0)
and both exit jumps are in-module rel32.  No absolute in-image operand is emitted, so no .reloc
entry is needed -- confirmed: the 8 KB zone carries none.

SCOPE -- what this does NOT touch
--------------------------------
`THero.CanCastCombatSpell @0x55789A3C` carries no tier gate at all (byte-identical to pristine),
`build_spellcast_tcpck.py` has none either, and `build_scroll_spellbook.py`'s stage-2 append keeps
its own deliberate "scroll spell needs level >= tier" rule (user decision 2026-07-30, left standing
2026-09-03).  So a hero casts any RESEARCHED spell regardless of tier but still cannot cast a
too-high-tier SCROLL spell.  That asymmetry is SANCTIONED -- do not "harmonise" it without asking.

Dry-run by default; `--apply` writes; `--undo` restores the rel32 to `cave_tiergate` and zeroes
this cave (touches no backup).  The cave disassembly is printed on every run -- read it (keystone
silently mis-encodes some immediates).  Idempotent, verify-before-write.
Backup `AoWEPACK.dpl.pre-herotier` is minted ONLY from a file proved to be in the pre-feature
state (hook still pointing at cave_tiergate AND our zone still zero) -- never on --undo, never
on a re-tune.
"""
import os, sys, shutil, struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL    = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-herotier")
IMAGE_BASE = 0x55700000

# ---- addresses (preferred-base VAs, all verified against the live file) ------------------
CANCAST_INJECT = 0x5578974D   # build_spellcast_multiturn.py's M2 hook: E9 rel32 + 90
CANCAST_CONT   = 0x55789753   # vanilla continuation (after the two displaced instructions)
TIERGATE       = 0x5580D95E   # build_spellcast_multiturn.py's cave_tiergate -- NOT modified
ISCLASS        = 0x557010C0   # AoWEPACK thunk -> System.@IsClass(eax=obj, edx=class) -> al
THERO_CLASSREF = 0x55711FAC   # [.] = THero class reference (VMT 0x55711FEC, name at VMT-0x20)
TLEADER_CLASSREF = 0x557121F8 # [.] = TLeader (VMT 0x55712238) -- asserted only, TLeader is a
                              # descendant of THero so IsClass(obj, THero) already covers it

CAVE      = 0x55846000        # exclusive reservation for this feature
CAVE_SPAN = 0x80              # bytes this script owns and zeroes on --undo
ZONE_END  = 0x55848000        # end of the reservation (asserted zero beyond the cave)

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)


def assemble_pic(src_fn, addr, npops=1):
    """Two-pass assemble: src_fn(pop_vas) places `pop ecx` immediately after each `call L`;
    iterate until the guessed pop VAs converge (the call/pop rebase-delta idiom)."""
    guess = [addr + 0x20 * (i + 1) for i in range(npops)]
    for _ in range(6):
        code = bytes(ks.asm(src_fn(guess), addr)[0])
        pops = [ins.address for ins in cs.disasm(code, addr)
                if ins.mnemonic == "pop" and ins.op_str == "ecx"][:npops]
        if pops == guess:
            return code
        assert len(pops) == npops, f"expected {npops} pops, found {len(pops)}"
        guess = pops
    raise RuntimeError("two-pass assembly did not converge")


def src_herotier(p):
    # NOTE: no ';' comments inside the asm -- keystone hangs on them (project trap).
    return f"""
        push eax
        call L1
    L1: pop ecx
        sub ecx, 0x{p[0]:X}
        mov edx, dword ptr [ecx + 0x{THERO_CLASSREF:X}]
        mov eax, ebx
        call 0x{ISCLASS:X}
        test al, al
        pop eax
        jnz Lhero
        jmp 0x{TIERGATE:X}
    Lhero:
        mov esi, eax
        movsx edx, byte ptr [ebx + 0x24]
        jmp 0x{CANCAST_CONT:X}
    """


cave = assemble_pic(src_herotier, CAVE, 1)
assert len(cave) <= CAVE_SPAN, f"cave {len(cave)} B exceeds owned span {CAVE_SPAN}"
cave_region = cave + b"\x00" * (CAVE_SPAN - len(cave))


def rel32(site, dest):
    return struct.pack("<i", dest - (site + 5))


HOOK_OLD = b"\xE9" + rel32(CANCAST_INJECT, TIERGATE) + b"\x90"
HOOK_NEW = b"\xE9" + rel32(CANCAST_INJECT, CAVE) + b"\x90"


# ---- PE helpers -------------------------------------------------------------------------
def load_secs(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    sect = e + 24 + optsz
    secs = []
    for i in range(nsec):
        b = sect + i * 40
        vs, va, rs, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append((d[b:b + 8].rstrip(b"\0").decode("latin1"), va, vs, raw, rs))
    return secs


def va2off(secs, va):
    r = va - IMAGE_BASE
    for nm, v, vs, raw, rs in secs:
        if v <= r < v + max(vs, rs):
            return raw + (r - v)
    raise ValueError(hex(va))


def reloc_hits(d, secs, lo, hi):
    """Every .reloc entry whose target VA lies in [lo, hi)."""
    e = struct.unpack_from("<I", d, 0x3C)[0]
    magic = struct.unpack_from("<H", d, e + 24)[0]
    dd = e + 24 + (96 if magic == 0x10B else 112)
    rva, size = struct.unpack_from("<II", d, dd + 5 * 8)
    off = va2off(secs, IMAGE_BASE + rva)
    end, hits = off + size, []
    while off < end:
        pg, blk = struct.unpack_from("<II", d, off)
        if blk == 0:
            break
        for i in range((blk - 8) // 2):
            w = struct.unpack_from("<H", d, off + 8 + i * 2)[0]
            if w >> 12 and lo <= IMAGE_BASE + pg + (w & 0xFFF) < hi:
                hits.append(IMAGE_BASE + pg + (w & 0xFFF))
        off += blk
    return hits


def classname(d, secs, classref_va):
    vmt = struct.unpack_from("<I", d, va2off(secs, classref_va))[0]
    p = struct.unpack_from("<I", d, va2off(secs, vmt - 0x20))[0]
    o = va2off(secs, p)
    return vmt, d[o + 1:o + 1 + d[o]].decode("latin1")


# ---- report -----------------------------------------------------------------------------
print(f"cave_herotier @ {CAVE:08X}  ({len(cave)} bytes, owns {CAVE_SPAN} to "
      f"{CAVE + CAVE_SPAN:08X}; reservation to {ZONE_END:08X})")
for ins in cs.disasm(cave, CAVE):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<22} {ins.mnemonic} {ins.op_str}")
print(f"hook @ {CANCAST_INJECT:08X}:  {HOOK_OLD.hex(' ')}  ->  {HOOK_NEW.hex(' ')}"
      f"   (only the 4 rel32 bytes at {CANCAST_INJECT + 1:08X} change)")
print()


def main():
    undo = "--undo" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    secs = load_secs(d)

    def rd(va, n):
        o = va2off(secs, va)
        return bytes(d[o:o + n])

    # --- preconditions -------------------------------------------------------------------
    vmt_h, nm_h = classname(d, secs, THERO_CLASSREF)
    vmt_l, nm_l = classname(d, secs, TLEADER_CLASSREF)
    print(f"classref check: [{THERO_CLASSREF:08X}] -> VMT {vmt_h:08X} = '{nm_h}'   "
          f"[{TLEADER_CLASSREF:08X}] -> VMT {vmt_l:08X} = '{nm_l}'")
    if (nm_h, nm_l) != ("THero", "TLeader"):
        print("ABORT: class-reference cells do not name THero/TLeader."); return 1
    if rd(ISCLASS, 2) != b"\xFF\x25":
        print(f"ABORT: {ISCLASS:08X} is not a jmp-[iat] thunk (@IsClass)."); return 1

    # cave_tiergate must still be build_spellcast_multiturn.py's v2 body -- we jump into it.
    tg = rd(TIERGATE, 6)
    if tg != bytes.fromhex("89 c6 56 57 53 89"):
        print(f"ABORT: cave_tiergate @{TIERGATE:08X} does not start with the expected v2 bytes "
              f"(found {tg.hex(' ')}). Run build_spellcast_multiturn.py first."); return 1

    hits = reloc_hits(d, secs, CAVE, CAVE + CAVE_SPAN) + \
        reloc_hits(d, secs, CANCAST_INJECT, CANCAST_INJECT + 6)
    if hits:
        print(f"ABORT: .reloc entries inside the cave or the hook: "
              f"{[f'{h:08X}' for h in hits]}"); return 1

    tail = rd(CAVE + CAVE_SPAN, ZONE_END - CAVE - CAVE_SPAN)
    if set(tail) != {0}:
        print(f"ABORT: reservation {CAVE + CAVE_SPAN:08X}..{ZONE_END:08X} is not zero."); return 1

    # --- patch table ---------------------------------------------------------------------
    zero_region = b"\x00" * CAVE_SPAN
    patches = [
        (CANCAST_INJECT, HOOK_OLD, HOOK_NEW, "CanCastSpell hook rel32 -> cave_herotier"),
        (CAVE, zero_region, cave_region, f"cave_herotier @ {CAVE:08X}"),
    ]

    ok = True
    already = todo = 0
    pristine = 0                                   # patches still in the pre-feature state
    for va, old, new, desc in patches:
        target, other = (old, new) if undo else (new, old)
        cur = rd(va, len(new))
        if cur == target:
            already += 1
            if undo:
                pristine += 1
        elif cur == other:
            todo += 1
            if not undo:
                pristine += 1
        else:
            print(f"MISMATCH {desc} @ {va:08X}:\n  pre-feature {old[:24].hex(' ')}"
                  f"\n  patched     {new[:24].hex(' ')}\n  found       {cur[:24].hex(' ')}")
            ok = False
    verb = "undone" if undo else "applied"
    print(f"{already} already {verb}, {todo} to change, {len(patches)} total")
    if not ok:
        print("ABORT: byte mismatch (different/partial patch state)."); return 1
    if "--apply" not in sys.argv:
        print("\nDry run OK. Re-run with --apply to write, --undo --apply to remove.")
        return 0
    if todo == 0:
        print("Nothing to do."); return 0

    # Backup ONLY from a file proved to be in the pre-feature state -- never on --undo (the
    # current file IS the patched state by definition), never on a re-tune.
    if not undo and pristine == len(patches) and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copyfile(DLL, BACKUP)
        print(f"backup -> {BACKUP}")
    elif not undo and not os.path.exists(BACKUP):
        print("(no backup: file is not in the pre-feature state; --undo is the revert path)")

    for va, old, new, desc in patches:
        o = va2off(secs, va)
        blob = old if undo else new
        d[o:o + len(blob)] = blob
        print(f"  wrote {va:08X}  {desc}")
    open(DLL, "wb").write(bytes(d))
    print("undone." if undo else "applied.")
    return 0


sys.exit(main())
