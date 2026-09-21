# -*- coding: utf-8 -*-
"""
build_drillmaster.py — new passive ability: Drillmaster (id 0xAA).

    python build_scripts/build_drillmaster.py           dry run + disassembly (default)
    python build_scripts/build_drillmaster.py --apply    write it
    python build_scripts/build_drillmaster.py --undo     restore hooks, zero the caves
    python build_scripts/build_drillmaster.py --dis      disassemble the caves only

EFFECT
    A stack containing a Drillmaster grants **+1 XP per turn to every other unit in it**.
    The carriers are excluded (a trainer does not train itself) and so are heroes, who
    already have their own XP trickle.

HOW IT IS ASSEMBLED FROM EXISTING ENGINE MACHINERY
    hook  TArmy.NewTurn @0x5578F79C — an army IS the stack.
          ⚠ NOT one call per turn: the engine calls it for EVERY player and filters with
          `cmp dl,[army+0x12]` (dl = player index). The cave must repeat that guard, or the
          grant fires once per player — three players gave +3 XP a turn instead of +1.
    walk  copied from TArmy.UpdateFormation @0x5578D034 (the Leadership aura):
              count = [[army+8]+8]   items = [[army+8]+4]   unit = [items + i*4]
          ⚠ the count lives on the LIST at +8, not on the army.
    test  unit->vmt[0x148](id) — GetAbilityEnabled. This is the ITEM-AWARE accessor pair
          (+0x144/+0x148), not the self-only +0x84/+0x88 one, so a Drillmaster *item* would
          work too. Picking the wrong pair is a documented way to ship an ability that does
          nothing.
    xp    unit->vmt[0x15C] get / [0x160] set. Both virtual, so one path covers heroes
          (dword at +0x48) and units (clamped byte) with no special casing.
    hero  System.@IsClass(obj, THero-vmt) — catches TLeader too, since it descends from THero.

REGISTRATION  (the Path of Sand recipe — see Path_Of_Sand_NewAbility.md)
    CreateEnhancementAbility(id, name, icon) then RegisterAbility(ctrl, obj), spliced by
    repointing one of the RegisterAbility calls inside PassiveAb.RegisterPassiveAbilities.
    EBX holds the ability-control for that whole function, so re-registering is trivial.
    ⚠ Path of Sand already owns the Path-of-Frost call @0x557BC9E9. This script takes the
    LAST call in the function, @0x557BCF39, so the two features do not fight over a site.
    A duplicate id raises a loud "Ability already registered (n)" box at startup, so a
    collision fails visibly rather than silently.

ID 0xAB is the first free id above everything in use (measured, see check_id_free). The
ceiling exists because TAbilityOwner.ReadWrite serialises each per-owner record under tag
0x32+id and the tag is one byte. Drillmaster is a plain passive with no per-owner record, so
it is nowhere near that limit.

CAVES are position-independent: the DPL rebases, so the THero class reference is reached by
the call/pop delta trick rather than an absolute address.
"""
import os, sys, struct, shutil, zlib

try:
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    sys.exit("needs keystone-engine and capstone:  py -m pip install keystone-engine capstone")

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-drillmaster")
DLL_BASE = 0x55700000

# 0xAB — the first id above the highest one in use. NOT 0xAA: Ability_ID_Budget.md calls
# 0xAA-0xCD "guaranteed safe", but that has gone stale — 0xAA is now occupied, and
# registering it a second time threw an unhandled "already registered" exception at startup,
# which the user saw as `Runtime error 217`. Never trust the documented band; the collision
# check below re-measures it from the binary and the data on every build.
ABILITY_ID = 0xAB
ABILITY_NAME = b"Drillmaster"

# CreateEnhancementAbility's third argument is NOT an icon — it is a TAbilitySelectionType
# bitmask that lands in the word at [ability+0x20]. Names read off the RTTI enum @0x55708E6C:
#   0x001 astUnit         0x002 astHeadItem       0x004 astTorsoItem   0x008 astAttackItem
#   0x010 astDefenseItem  0x020 astRingItem       0x040 astUseItem     0x080 astCustomizeLeader
#   0x100 astHeroUpgrade  0x200 astEditor
# The hero level-up dialog demands BOTH of the top two: the dialog's own fill loop tests
# astHeroUpgrade (`test byte ptr [ability+0x21],1`), and TAbility.CanExpand @0x5574E8B8 ANDs the
# mask with THero.GetAbilitySelectionTypes @0x55786B10, which returns astEditor. Miss either and
# the ability is registered, assignable and functional — but never offered at level-up.
# 0x03FF (every context) is what 80 of the 101 level-up abilities carry; narrow it in DevEd if
# a Drillmaster item is unwanted.
SEL_TYPES = 0x03FF

REGISTER_ABIL = 0x55750238
CREATE_ENH    = 0x5576601C
ISCLASS       = 0x557010C0
THERO_VMT     = 0x55711FEC

VMT_ABIL_ENABLED = 0x148
VMT_GET_XP       = 0x15C
VMT_SET_XP       = 0x160

# --- hook sites --------------------------------------------------------------------
REG_INJ  = 0x557BCF39                                    # last RegisterAbility call in the function
REG_ORIG = b"\xE8" + struct.pack("<i", REGISTER_ABIL - (REG_INJ + 5))

TURN_INJ  = 0x5578F79C                                   # TArmy.NewTurn entry
TURN_ORIG = bytes.fromhex("53 8b d8 3a 53 12")           # push ebx; mov ebx,eax; cmp dl,[ebx+0x12]
TURN_BACK = 0x5578F7A2                                   # the jne that consumes that cmp

CAVE_REG = 0x55816000                                    # inside an 861 KB free run from 0x5581546D

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)
PH_NAME = 0x61111116
PH_HERO = 0x62222226


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def fix_pic(code, va, pop_op, subs):
    """Turn `call $+5 ; pop <reg>` into a delta anchor and rewrite placeholders.

    The call's rel32 is zeroed so it simply falls through to the pop, which then holds the
    RUNTIME address of itself. Every placeholder becomes (target - anchor), so a
    `lea reg,[reg+ph]` yields the rebased target. This is why nothing here uses an absolute
    address: the DPL never loads at its preferred base.
    """
    # ⚠ never write the anchor as `call $+5` — keystone assembles that to NOTHING, silently.
    # The search then latches onto whatever earlier E8 happens to sit five bytes before a
    # matching pop and zeroes ITS rel32. In cave_reg that was the `call RegisterAbility`,
    # which would have turned into a call to the middle of this cave. Emit a real
    # `call <addr>`; the target is irrelevant because the rel32 is zeroed here anyway.
    code = bytearray(code)
    i = next(k for k in range(len(code) - 5) if code[k] == 0xE8 and code[k + 5] == pop_op)
    anchor = va + i + 5
    code[i + 1:i + 5] = struct.pack("<i", 0)
    for ph, tgt in subs:
        hits = [k for k in range(len(code) - 3) if code[k:k + 4] == struct.pack("<I", ph)]
        assert len(hits) == 1, "placeholder %#x found %d times" % (ph, len(hits))
        code[hits[0]:hits[0] + 4] = struct.pack("<i", tgt - anchor)
    return bytes(code)


# --- cave_reg: re-issue the displaced RegisterAbility, then create + register ours ----
def build_reg(name_va, sel=None):
    src = """
        call 0x%X
        call 0x%X
        pop eax
        lea edx, [eax + 0x%X]
        mov ecx, 0x%X
        mov eax, 0x%X
        call 0x%X
        mov edx, eax
        mov eax, ebx
        call 0x%X
        ret
    """ % (REGISTER_ABIL, CAVE_REG, PH_NAME, SEL_TYPES if sel is None else sel,
           ABILITY_ID, CREATE_ENH, REGISTER_ABIL)
    return fix_pic(asm(src, CAVE_REG), CAVE_REG, 0x58, [(PH_NAME, name_va)])


_probe = build_reg(0)
NAME_BLOB_VA = (CAVE_REG + len(_probe) + 3) & ~3
NAME_VA = NAME_BLOB_VA + 8                                # past the refcount+length header
name_blob = struct.pack("<iI", -1, len(ABILITY_NAME)) + ABILITY_NAME + b"\x00"
cave_reg = build_reg(NAME_VA)

CAVE_TURN = (NAME_BLOB_VA + len(name_blob) + 0xF) & ~0xF


GUARD = chr(10).join(("cmp dl, byte ptr [eax + 0x12]", "        jne done"))


def build_turn(owner_guard=True, stacking=True):
    # ebx doubles as the Drillmaster tally: pass 1 counts them (v1/v2 stopped at the first and
    # used it as a 0/1 flag), pass 2 adds that tally instead of a hard 1. Two Drillmasters in a
    # stack therefore train everyone else at +2 XP a turn. Drillmasters still receive nothing —
    # they do not train each other — which keeps the original rule intact.
    count_them = "inc ebx" if stacking else chr(10).join(
        ("mov ebx, 1", "        jmp p1done"))
    grant = "add edx, ebx" if stacking else "inc edx"
    src = """
        pushad
        pushfd
        %s
        mov ebx, eax
        mov eax, [ebx + 8]
        test eax, eax
        je  done
        mov edi, [eax + 8]
        mov esi, [eax + 4]
        test edi, edi
        jle done
        call 0x%X
        pop ebp
        lea ebp, [ebp + 0x%X]
        xor ebx, ebx
        xor ecx, ecx
    p1:
        push ecx
        mov eax, [esi + ecx*4]
        mov edx, 0x%X
        mov ecx, [eax]
        call dword ptr [ecx + 0x%X]
        pop ecx
        test al, al
        je  p1next
        %s
    p1next:
        inc ecx
        cmp ecx, edi
        jl  p1
    p1done:
        test ebx, ebx
        je  done
        xor ecx, ecx
    p2:
        push ecx
        mov eax, [esi + ecx*4]
        mov edx, 0x%X
        mov ecx, [eax]
        call dword ptr [ecx + 0x%X]
        test al, al
        jne p2next
        mov ecx, [esp]
        mov eax, [esi + ecx*4]
        mov edx, ebp
        call 0x%X
        test al, al
        jne p2next
        mov ecx, [esp]
        mov eax, [esi + ecx*4]
        mov ecx, [eax]
        call dword ptr [ecx + 0x%X]
        mov edx, eax
        %s
        mov ecx, [esp]
        mov eax, [esi + ecx*4]
        mov ecx, [eax]
        call dword ptr [ecx + 0x%X]
    p2next:
        pop ecx
        inc ecx
        cmp ecx, edi
        jl  p2
    done:
        popfd
        popad
        push ebx
        mov ebx, eax
        cmp dl, byte ptr [ebx + 0x12]
        jmp 0x%X
    """ % (GUARD if owner_guard else "",
           CAVE_TURN, PH_HERO, ABILITY_ID, VMT_ABIL_ENABLED, count_them,
           ABILITY_ID, VMT_ABIL_ENABLED,
           ISCLASS, VMT_GET_XP, grant, VMT_SET_XP, TURN_BACK)
    return fix_pic(asm(src, CAVE_TURN), CAVE_TURN, 0x5D, [(PH_HERO, THERO_VMT)])


cave_turn = build_turn()
# Every cave variant this script has ever shipped, keyed by cave VA. Verify-before-write accepts
# any of them as a starting state, so a re-tune is a rewrite IN PLACE and never needs a revert —
# the same property build_copper_medal.py has. Append here whenever a cave changes.
#   cave_reg  v1 2026-08-07  mask 0x0037: no astHeroUpgrade, no astEditor, so the hero level-up
#                            dialog never offered it (see SEL_TYPES)
#   cave_turn v1 2026-08-07  no owner guard: fired once per PLAYER, +3 XP a turn with 3 players
#   cave_turn v2 2026-08-07  guarded, but stopped at the first Drillmaster: a second one in the
#                            same stack added nothing
PRIOR_CAVES = {
    CAVE_REG:  [build_reg(NAME_VA, sel=0x0037)],
    CAVE_TURN: [build_turn(owner_guard=False, stacking=False),
                build_turn(owner_guard=True, stacking=False)],
}
CAVE_ZONE_END = CAVE_TURN + max([len(cave_turn)] + [len(c) for c in PRIOR_CAVES[CAVE_TURN]]) + 0x10

WRITES = [
    (CAVE_REG,     cave_reg,  "cave_reg  (re-register + create/register Drillmaster)"),
    (NAME_BLOB_VA, name_blob, 'name literal "%s"' % ABILITY_NAME.decode()),
    (CAVE_TURN,    cave_turn, "cave_turn (stack scan + XP grant, hooked on TArmy.NewTurn)"),
    (REG_INJ,  b"\xE8" + struct.pack("<i", CAVE_REG - (REG_INJ + 5)),
     "RegisterAbility call @%08X -> cave_reg" % REG_INJ),
    (TURN_INJ, b"\xE9" + struct.pack("<i", CAVE_TURN - (TURN_INJ + 5)) + b"\x90",
     "TArmy.NewTurn @%08X -> cave_turn" % TURN_INJ),
]
ORIGINALS = {REG_INJ: REG_ORIG, TURN_INJ: TURN_ORIG,
             CAVE_REG: bytes(len(cave_reg)), NAME_BLOB_VA: bytes(len(name_blob)),
             CAVE_TURN: bytes(len(cave_turn))}


# =========================================== Release/Ability.pfs: the mask that actually counts
# TAbilityControl.ReadWrite @0x55750164 serialises every ability under tag `list index + 10`, and
# RegisterAbility parks the object at list[id], so the record key is id + 10. TAbility.ReadWrite
# @0x5574F07C then reads tag 9 straight into the word at [ability+0x20]. That load happens AFTER
# registration, so the DATA FILE WINS over whatever the cave passed: all 21 vanilla
# CreateEnhancementAbility sites register a mask the .pfs promptly overwrites (0 of 21 agree).
# Patching only the cave would have changed nothing in game.
ABIL_PFS = os.path.join(GAME, "Release", "Ability.pfs")
ABIL_PFS_BACKUP = os.path.join(BACKUP_DIR, os.path.basename(ABIL_PFS) + ".pre-drillmaster")
PFS_RESIDUE = 0x2144DF1C          # crc32(d[4:]) of an intact file — see PFS_Format_CRC.md


def pfs_tag9_offset(d):
    """File offset of record (ABILITY_ID+10)'s tag-9 word.

    Derived, never hard-coded: AoWDevEd rewrites this file whole and every offset inside it
    moves. Record bodies tile the file from the first one to EOF, so absolute starts fall out of
    the body lengths.

    The CRC gate below is the file's integrity check, and it lives here because EVERY path that
    touches Ability.pfs comes through this function — pfs_read (the dry-run report and undo's
    backup read) and pfs_write both call it on the buffer AS READ. So a damaged file aborts the
    run before anything at all is written, the DLL half included. What it buys, stated honestly:
      CATCHES  incoherent damage — a flipped payload byte, a nudged offset, a truncated file:
               anything whose bytes no longer match the stored CRC.
      MISSES   a coherent-but-wrong layout. Damage that was re-CRC'd (by an earlier version of
               this very script, say) reads as intact and always will.
    """
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT: Ability.pfs CRC residue is %#010x, expected %#010x — the file is ALREADY "
                 "damaged, before this script has edited anything.\n"
                 "       Refusing to touch it: repairing the CRC over the damage would stamp it "
                 "valid and destroy the evidence that anything was ever wrong.\n"
                 "       Restore Release/Ability.pfs (a .pre-* copy, or the game's install media) "
                 "or re-save it from AoWDevEd, then re-run."
                 % (zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF, PFS_RESIDUE))
    # ⚠ Do NOT re-add the "integrity check" that used to sit at the end of this function:
    #       assert bytes(d[a:a + len(body)]) == body, "record reconstruction failed"
    #   It reconstructed record starts by tiling body lengths backwards from EOF and compared the
    #   result against the body parse_index had handed back. That is CIRCULAR and CANNOT FAIL:
    #   parse_index produced `body` as a slice AT the very offset being re-derived, so tiling
    #   backwards reproduces the same `a` by construction. It read as proof the layout was sound
    #   and proved only that slicing is deterministic. The CRC residue above is the real check.
    #   build_vision9.py:pfs_plan carries the same warning — it had the same check, it passed a
    #   deliberate +3 offset nudge, and it was removed there too.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pfs", os.path.join(GAME, "Modding Resources", "re_tools", "pfs.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    recs = m.parse_index(bytes(d))
    starts, at = {}, len(d)
    for rid, body in reversed(recs):
        at -= len(body)
        starts[rid] = at
    key = ABILITY_ID + 10
    if key not in starts:
        sys.exit("ABORT: Ability.pfs has no record %d for ability %#04x. Assign the ability to "
                 "something in AoWDevEd and save, so the editor creates one." % (key, ABILITY_ID))
    a, body = starts[key], dict(recs)[key]
    p = 1 + (4 if body[0] & 0x80 else 0)
    ent = [(body[1 + 2 * k], body[2 + 2 * k]) for k in range(body[0] & 0x7f)]
    p += 2 * len(ent)
    for k in range(struct.unpack_from("<I", body, 1)[0] if body[0] & 0x80 else 0):
        t, o = struct.unpack_from("<II", body, p + 8 * k); ent.append((t, o))
    p += 8 * (len(ent) - (body[0] & 0x7f))
    for t, o in ent:
        if t == 9:
            return a + p + o
    sys.exit("ABORT: record %d carries no tag 9 (selection mask)." % key)


def pfs_read(path=None):
    d = bytearray(open(path or ABIL_PFS, "rb").read())
    return d, struct.unpack_from("<H", d, pfs_tag9_offset(d))[0]


def pfs_write(value):
    # Both calls below gate on the CRC residue of the file as read (see pfs_tag9_offset), so an
    # already-damaged Ability.pfs aborts HERE rather than having a fresh valid CRC stamped over it.
    d, _cur = pfs_read()
    struct.pack_into("<H", d, pfs_tag9_offset(d), value)   # length-preserving u16, no offsets move
    struct.pack_into("<I", d, len(d) - 4, zlib.crc32(bytes(d[4:-4])) & 0xFFFFFFFF)
    # ⚠ not an `assert`: `python -O` strips those, and a stripped guard here would not fail loudly
    # — it would write a file the game and the editor reject on load.
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT: CRC repair produced residue %#010x, expected %#010x — nothing written."
                 % (zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF, PFS_RESIDUE))
    open(ABIL_PFS, "wb").write(bytes(d))


def check_id_free(d):
    """Abort if ABILITY_ID is already registered. Measured, never taken on trust.

    Two independent sources: `mov eax,<id>; call CreateEnhancementAbility` in the DLL, and the
    record keys of Release/Ability.pfs (key = id + 10). A collision is not a soft failure —
    the engine raises during unit initialisation and Delphi reports `Runtime error 217`
    before the main window ever appears.
    """
    import importlib.util
    used = set()
    for i in range(len(d) - 10):
        if d[i] == 0xB8 and d[i + 5] == 0xE8:
            try:
                va = off2va(d, i + 5)
            except ValueError:
                continue
            if va and (va + 5 + struct.unpack_from("<i", d, i + 6)[0]) & 0xFFFFFFFF == CREATE_ENH:
                # skip OUR OWN cave, or a re-run against an already-applied file reports the
                # id we just installed as a collision
                if CAVE_REG <= va < CAVE_TURN + len(cave_turn):
                    continue
                used.add(struct.unpack_from("<I", d, i + 1)[0])
    # Ability.pfs is read only to WIDEN the picture when choosing a fresh id. It must not
    # drive the abort: once the ability is assigned to a unit in DevEd, the editor writes a
    # record for our own id, and treating that as a collision would block every re-run.
    data = set()
    try:
        sp = os.path.join(GAME, "Modding Resources", "re_tools", "pfs.py")
        spec = importlib.util.spec_from_file_location("pfs", sp)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        data = {rid - 10 for rid, _b in m.load("ability.pfs")[0]}
    except Exception:                                          # noqa: BLE001
        print("  (could not read Ability.pfs — id check used the DLL only)")
    if ABILITY_ID in used:
        free = [x for x in range(0, 0xCE) if x not in used | data]
        sys.exit("ABORT: ability id 0x%02X is registered by the DLL already — this is the "
                 "collision that shows in game as `Runtime error 217`. Free ids: %s"
                 % (ABILITY_ID, ", ".join("0x%02X" % x for x in free[-6:])))
    both = used | data
    print("  id 0x%02X free to register (%d ids known, highest 0x%02X)%s"
          % (ABILITY_ID, len(both), max(both),
             "; already assigned to units in Ability.pfs" if ABILITY_ID in data else ""))


def off2va(d, off):
    for va0, sz, raw in sections(d):
        if raw <= off < raw + sz:
            return DLL_BASE + va0 + (off - raw)
    raise ValueError(off)


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    s, out = pe + 24 + opt, []
    for _ in range(n):
        vs, va, rs, raw = struct.unpack_from("<IIII", d, s + 8)
        out.append((va, max(vs, rs), raw))
        s += 40
    return out


def va2off(d, va):
    """⚠ per-section, never one global delta — this DLL's .data skews differently."""
    for va0, sz, raw in sections(d):
        if va0 <= va - DLL_BASE < va0 + sz:
            return raw + (va - DLL_BASE - va0)
    raise ValueError("VA %08X not mapped" % va)


def dis(d, va, n, title):
    print("\n  ---- %s  @%08X (%d bytes)" % (title, va, n))
    o = va2off(d, va)
    for ins in cs.disasm(bytes(d[o:o + n]), va):
        print("    %08X  %-9s %s" % (ins.address, ins.mnemonic, ins.op_str))


def main():
    apply_, undo, only_dis = "--apply" in sys.argv, "--undo" in sys.argv, "--dis" in sys.argv
    d = bytearray(open(DLL, "rb").read())

    print("Drillmaster: ability id 0x%02X, caves at %08X..%08X"
          % (ABILITY_ID, CAVE_REG, CAVE_TURN + len(cave_turn)))
    if not undo:
        check_id_free(d)
    if only_dis:
        dis(d, CAVE_REG, len(cave_reg), "cave_reg")
        dis(d, CAVE_TURN, len(cave_turn), "cave_turn")
        return

    def classify(va, new):
        cur = bytes(d[va2off(d, va):va2off(d, va) + len(new)])
        if cur == new:
            return "done"
        if cur == ORIGINALS[va]:
            return "clean"
        o = va2off(d, va)
        for prior in PRIOR_CAVES.get(va, ()):
            if bytes(d[o:o + len(prior)]) == prior:
                return "prior"
        return "other"

    states = {classify(va, new) for va, new, _t in WRITES}
    print("current: %s" % ", ".join(sorted(states)))
    for va, new, t in WRITES:
        print("  %08X  %-5s %s" % (va, classify(va, new).upper(), t))
    if "other" in states:
        sys.exit("\nABORT: a site matches neither the original nor the target. Investigate.")

    _pfs, pfs_cur = pfs_read()
    pfs_done = pfs_cur == SEL_TYPES
    print("  Ability.pfs   %-5s record %d tag 9 (selection mask) = %#06x -> %#06x"
          % ("DONE" if pfs_done else "TODO", ABILITY_ID + 10, pfs_cur, SEL_TYPES))
    if not pfs_done:
        print("                missing%s%s"
              % ("" if pfs_cur & 0x100 else " astHeroUpgrade(0x100)",
                 "" if pfs_cur & 0x200 else " astEditor(0x200)"))

    print("\n  cave_reg  %d bytes    name blob %d bytes    cave_turn %d bytes"
          % (len(cave_reg), len(name_blob), len(cave_turn)))
    for va, blob, title in ((CAVE_REG, cave_reg, "cave_reg"), (CAVE_TURN, cave_turn, "cave_turn")):
        print("\n  ---- %s (assembled) ----" % title)
        for ins in cs.disasm(blob, va):
            print("    %08X  %-9s %s" % (ins.address, ins.mnemonic, ins.op_str))

    target = "clean" if undo else "done"
    pfs_at_target = (not pfs_done) if undo else pfs_done
    if states == {target} and pfs_at_target:
        print("\nnothing to do — already %s." % target)
        return
    if not (apply_ or undo):
        print("\ndry run. --apply to write, --undo to revert.")
        return

    # zero the whole cave zone first: a shrinking cave would otherwise leave a tail of the
    # previous build lying in executable memory
    z0, z1 = va2off(d, CAVE_REG), va2off(d, CAVE_ZONE_END)
    d[z0:z1] = bytes(z1 - z0)
    for va, new, _t in WRITES:
        o = va2off(d, va)
        if undo:
            d[o:o + len(new)] = ORIGINALS[va]
        else:
            d[o:o + len(new)] = new
    if not undo and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("\nbackup: %s" % os.path.basename(BACKUP))
    open(DLL, "wb").write(bytes(d))
    print("wrote AoWEPACK.dpl -> %s" % target)

    # Ability.pfs: patch the VALUE, not the file, so a DevEd re-save between apply and undo is
    # not clobbered — the backup exists to remember the old mask, not to be copied back.
    if undo:
        if not pfs_done:
            print("Ability.pfs untouched (mask is not ours)")
        elif os.path.exists(ABIL_PFS_BACKUP):
            was = pfs_read(ABIL_PFS_BACKUP)[1]
            pfs_write(was)
            print("Ability.pfs record %d tag 9 -> %#06x (from %s)"
                  % (ABILITY_ID + 10, was, os.path.basename(ABIL_PFS_BACKUP)))
        else:
            print("Ability.pfs left at %#06x — no backup to read the old mask from" % SEL_TYPES)
    elif not pfs_done:
        if not os.path.exists(ABIL_PFS_BACKUP):
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(ABIL_PFS, ABIL_PFS_BACKUP)
            print("backup: %s" % os.path.basename(ABIL_PFS_BACKUP))
        pfs_write(SEL_TYPES)
        print("Ability.pfs record %d tag 9 %#06x -> %#06x (CRC repaired)"
              % (ABILITY_ID + 10, pfs_cur, SEL_TYPES))


if __name__ == "__main__":
    main()
