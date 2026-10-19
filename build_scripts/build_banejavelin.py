#!/usr/bin/env python
r"""
build_banejavelin.py -- Shoot Bane Javelin (ability 0xBE): Shoot Bolt with physical AND death damage,
DAM 11.  AoWEPACK.dpl + AoWTCPCK.dpl.  Owner's design 2026-10-19 (DAM 7 -> 11 the same day).

WHAT IT IS
    A second TRangedAttackAbility built by the same constructor as Shoot Bolt (0x39), with Shoot
    Bolt's live attack, shots and range, the owner's damage, and the damage-type word 0x00A0
    (Physical 0x80 | Death 0x20):
        ATK 14   DAM 11   1 shot   range band 3 (long, 12 hexes)   types Physical + Death
    Vanilla's Shoot Black Javelin (0x3A) was the same pairing: Shoot Javelin's numbers (then
    5/5, 2 shots, long) with its mask word at 0x5576F814 = 0x00A0, carried by one unit, the Orc
    Shredder Bolt.  Ziggurat turned 0x3A into Throw Javelin (word 0x0080, 8/9, 1 shot, short; an
    unscripted hand edit) and renamed 0x39 Shoot Bolt.  Both stay as they are.

    Projectile, sounds and auto-resolve icon are data: Release/Ability.pfs record 200
    (build_banejavelin_pfs.py) clones the black-javelin frames ARROW.ILB 300-323 and COMBAT.ILB
    hit icon 123 from record 68, and Shoot Bolt's sounds from record 67.

WHY THREE HOOKS AND A BYTE
    Everything else about a ranged attack goes through the ability object (TRangedAttackAbility VMT
    0x5571E8D4: GetAttackRA/GetDamageRA/GetRangeRA/GetDamageTypesRA, CreateRangedAttackCA,
    fcExecuteCombatCommand) or through the AbilTypes category byte, so both combat systems take a
    new id as they take Shoot Bolt.  A census of every module (re_tools/idladder.py, abquery.py and
    an immediate scan, 2026-10-19) finds Shoot Bolt's id compared in exactly three places:
      AoWTCPCK  AoWTC.MakeAbilPath 0x004271EC      0x2C/0x2D/0x39/0x3A/0x7B -> arc 20, step 50.
                                                   Any other id gets arc 50.
      AoWTCPCK  TCAI.CheckUnit 0x004175B0          ranged ids -> EvalPath(checkUnits 0).  Any other
                                                   id is never scored, so the AI would not shoot.
      AoWEPACK  GetUnitIndexAIPriority 0x5575BB26  +100 recruit priority for 0x39 or 0x3A.
    Plus AbilTypes: the relocated table (build_abiltypes_relocate.py) holds category 0 for ids
    170..255, and 0 deselects the ability on click (0x0041EC74) and hides it from the AI.  Shoot
    Bolt's category is 1.
    (TAbilityControl.UnregisterAbilityID 0x557505B8 also names 0x39 -- it is the package
    finalisation, and no mod ability unregisters.)

REGISTRATION (package init -- prove by launching the exe)
    Spliced at the last vanilla `call RegisterAbility` 0x5576F7E2 (Doom Gaze) in the unexported
    ranged-registration routine 0x5576F2EC, EBX = the control; the displaced call is replayed first.
    CreateHurl-style ctor 0x5576ED48 (EAX id, EDX name, CL attack; stack: damage, shots, band,
    types, fast-combat icon -- the last is read by nothing) in the same instruction shape as the
    vanilla blocks, so re_tools/ranged_stats.py reads the numbers back.  Name: an AnsiString
    literal (refcount -1) behind a call/pop anchor.  Selection mask: the ctor sets 0x41 and
    Ability.pfs tag 9 overrides it with 0x03FF.

HOOKS (vanilla bytes asserted, no .reloc under any)
  AoWEPACK.dpl
    R  0x5576F7E2  call RegisterAbility -> call cave_reg
    A  0x5575BB37  mov edx,0x3A (5 B) -> jmp cave_aipri       0x39, 0x3A or 0xBE -> +100
  AoWTCPCK.dpl
    C  0x004694FE  AbilTypes[0xBE] 00 -> 01                   Shoot Bolt's category
    M  0x0042725C  jmp 0x4275EC (default arc) -> jmp cave_arc   0xBE -> 0x4272D1 (arc 20)
    I  0x00417619  jae 0x4176FB (6 B) -> jmp cave_ai + nop      0xBE -> 0x41761F (EvalPath 0)

Slots: AoWEPACK 0x5589F800-0x5589FBFF exclusive; AoWTCPCK 0x0043B640-0x0043B6FF exclusive.  PIC:
rel32 and one call/pop anchor; no absolute address.

RNG: none.  No draw is added or moved; a shot runs vanilla's ranged path (P2 COMBAT RAW in manual
combat, auto-resolve's own) exactly as Shoot Bolt's does.

Couplings.
  * Ceilings: LADDER 0xBF in build_abilityid_ceilings.py and build_tcablist_ceiling.py, or the AI
    scans and the combat panel stop at 0xBD.  re_tools/ability_names.py MODDED names 0xBE, which is
    what those two scripts read.
  * build_abiltypes_relocate.py --undo zeroes ids 170..255 of the table it owns, this byte with
    them: undo this script first.
  * Shoot Bolt's attack, shots and range are copied, not shared: build_ranged_damage.py retunes
    Shoot Bolt alone.  The dry run prints both and flags drift in those three.
  * Record 200, its row in heroskill_races.json and its Ranged column in herodlg_cats.py:
    build_banejavelin_pfs.py, build_heroskill_race.py, build_herodlg_columns.py.

Unproven, static checks cannot reach it: that the tactical AI chooses the shot (CheckUnit's case is
the one Shoot Bolt takes, but only a battle shows it), and the flight arc on screen.

Undo: --undo is surgical.  Remove Shoot Bane Javelin from every unit and item and run
build_banejavelin_pfs.py --undo first -- a unit carrying an unregistered id meets a nil registry slot.

    python build_scripts/build_banejavelin.py            dry run + state, both modules
    python build_scripts/build_banejavelin.py --apply
    python build_scripts/build_banejavelin.py --undo
    python build_scripts/build_banejavelin.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                        # noqa: BLE001
    pass

import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

HERE = os.path.dirname(os.path.abspath(__file__))
EPACK = os.path.join(P.GAME, "AoWEPACK.dpl")
TCPCK = os.path.join(P.GAME, "AoWTCPCK.dpl")

ABIL_ID = 0xBE
NAME = "Shoot Bane Javelin"
ATK, DAM, SHOTS, BAND = 14, 11, 1, 3       # DAM 11: owner 2026-10-19 (Shoot Bolt's is 7)
TYPES = 0x00A0                       # Physical 0x80 | Death 0x20
FC_ICON = 0x7B                       # vanilla Black Javelin's ignored ctor argument (COMBAT.ILB 123)
CATEGORY = 1                         # AbilTypes: Shoot Bolt's

REGISTER = 0x55750238                # TAbilityControl.RegisterAbility
CREATE_RANGED = 0x5576ED48           # TRangedAttackAbility ctor (CreateHurl)
CTORS = {0x5576601C: "CreateEnhancementAbility", CREATE_RANGED: "ranged ctor",
         0x5576EDE8: "bolt ctor", 0x5576EE84: "breath ctor"}
R_SITE = 0x5576F7E2
A_SITE, A_PLUS, A_NEXT = 0x5575BB37, 0x5575BB48, 0x5575BB4B
A_VAN = bytes.fromhex("ba3a000000")                 # mov edx,0x3A
SB_SITE = {"dam": 0x5576F533, "shots": 0x5576F535, "band": 0x5576F537, "atk": 0x5576F55D,
           "mask": 0x5576F53A}                       # Shoot Bolt's block: push imm8 x3, mov ax,[m], mov cl

ABILTYPES = 0x00469440
ABILTYPES_REF = 0x0041EC66                          # mov al,[eax+0x469440] once relocated
C_SITE = ABILTYPES + ABIL_ID
M_SITE, M_LOW, M_DEFAULT = 0x0042725C, 0x004272D1, 0x004275EC
I_SITE, I_EVAL, I_SKIP = 0x00417619, 0x0041761F, 0x004176FB
I_VAN = bytes.fromhex("0f83dc000000")               # jae 0x4176FB

E_SLOT = (0x5589F800, 0x5589FC00)
T_SLOT = (0x0043B640, 0x0043B700)


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def ansistr(s):
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def build_reg(va):
    """Replays the displaced RegisterAbility, then builds and registers the javelin the way the
    host's own blocks do.  EBX = the control throughout; the ctor pops its five arguments."""
    code = bytearray(call_to(va, REGISTER))
    code += asm(f"""
        push {DAM}
        push {SHOTS}
        push {BAND}
        mov  eax, {TYPES:#x}
        push eax
        push {FC_ICON:#x}
    """, va + len(code))
    at = va + len(code)
    code += b"\xE8\x00\x00\x00\x00"                     # call $+5 -- raw: keystone drops it
    anchor = at + 5
    code += asm("pop eax", anchor)
    fix = len(code)
    code += b"\x8D\x90" + b"\0\0\0\0"                   # lea edx,[eax+disp32] -> the name chars
    code += asm(f"""
        mov  cl, {ATK:#x}
        mov  eax, {ABIL_ID:#x}
        call {CREATE_RANGED:#x}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER:#x}
        ret
    """, va + len(code))
    while len(code) % 4:
        code += b"\x90"
    lit = va + len(code) + 8
    code += ansistr(NAME)
    struct.pack_into("<i", code, fix + 2, lit - anchor)
    return bytes(code)


def build_aipri(va):
    """GetUnitIndexAIPriority: EBX = the unit resource, [EBX+0x38] its base ability owner, ESI the
    running priority.  The host's own +0x4C (GetAbSet) query, once more for 0xBE."""
    return asm(f"""
        mov  edx, 0x3a
        mov  eax, dword ptr [ebx + 0x38]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne  {A_PLUS:#x}
        mov  edx, {ABIL_ID:#x}
        mov  eax, dword ptr [ebx + 0x38]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne  {A_PLUS:#x}
        jmp  {A_NEXT:#x}
    """, va)


def build_arc(va):
    """MakeAbilPath's default exit for ids above 0x34; [EBP-4] = the ability id (word)."""
    return asm(f"""
        movsx eax, word ptr [ebp - 4]
        cmp  eax, {ABIL_ID:#x}
        je   {M_LOW:#x}
        jmp  {M_DEFAULT:#x}
    """, va)


def build_ai(va):
    """CheckUnit's ranged case, last rung: flags from `sub eax,5` (CF set = a bolt, 0x78..0x7C);
    [EBP-0x5C] = the ability id."""
    return asm(f"""
        jb   {I_EVAL:#x}
        cmp  dword ptr [ebp - 0x5c], {ABIL_ID:#x}
        je   {I_EVAL:#x}
        jmp  {I_SKIP:#x}
    """, va)


def layout(slot, specs):
    caves, va = [], slot[0]
    for name, fn in specs:
        blob = fn(va)
        caves.append((name, va, blob))
        va = (va + len(blob) + 0xF) & ~0xF
    return {n: v for n, v, _b in caves}, caves


E_AT, E_CAVES = layout(E_SLOT, [("cave_reg", build_reg), ("cave_aipri", build_aipri)])
T_AT, T_CAVES = layout(T_SLOT, [("cave_arc", build_arc), ("cave_ai", build_ai)])

E_HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, E_AT["cave_reg"])),
           (A_SITE, A_VAN, jmp_to(A_SITE, E_AT["cave_aipri"], len(A_VAN)))]
E_INTERIOR = [(A_SITE, A_SITE + len(A_VAN), 0x5575B9D0, 0x5575BC99)]
T_HOOKS = [(C_SITE, b"\x00", bytes([CATEGORY])),
           (M_SITE, jmp_to(M_SITE, M_DEFAULT, 5), jmp_to(M_SITE, T_AT["cave_arc"], 5)),
           (I_SITE, I_VAN, jmp_to(I_SITE, T_AT["cave_ai"], len(I_VAN)))]
T_INTERIOR = [(M_SITE, M_SITE + 5, 0x004271EC, 0x00427626),
              (I_SITE, I_SITE + len(I_VAN), 0x004152A8, 0x00418170)]


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def read_at(d, va):
    return d[P.va2off(d, va)]


def self_checks():
    """The bytes this build emits, checked before anything is written."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    lit = ansistr(NAME)
    for name, va, blob in E_CAVES + T_CAVES:
        code = blob[:-len(lit)].rstrip(b"\x90") if name == "cave_reg" else blob
        if name == "cave_reg":
            assert blob.endswith(lit), "cave_reg does not end in its name literal"
        ins = list(md.disasm(code, va))
        assert sum(i.size for i in ins) == len(code), "%s does not disassemble cleanly" % name
        for i in ins:
            # keystone's imm8 trap: an id above 0x7F must never become a sign-extended byte
            assert "0xffffff" not in i.op_str, "%s %08X: sign-extended immediate: %s %s" % (
                name, i.address, i.mnemonic, i.op_str)
    # the anchor's disp32 must land on the name's characters
    _n, va, blob = E_CAVES[0]
    k = blob.index(b"\xE8\x00\x00\x00\x00")
    disp = struct.unpack_from("<i", blob, k + 6 + 2)[0]
    assert blob[k + 5] == 0x58 and blob[k + 6:k + 8] == b"\x8D\x90"
    assert blob[k + 5 + disp:k + 5 + disp + len(NAME)] == NAME.encode("latin1"), "anchor misses the name"
    # re_tools/ranged_stats.py's reader applied to cave_reg: it must see ATK/DAM/shots/band
    hits = [j for j in range(len(blob) - 5) if blob[j] == 0xE8
            and va + j + 5 + struct.unpack_from("<i", blob, j + 1)[0] == CREATE_RANGED]
    assert len(hits) == 1, "cave_reg calls the ranged ctor %d times" % len(hits)
    i = hits[0]
    assert blob[i - 5] == 0xB8 and struct.unpack_from("<I", blob, i - 4)[0] == ABIL_ID
    assert blob[i - 7] == 0xB1 and blob[i - 6] == ATK
    pushes = []
    j = max(0, i - 0x50)
    while j < i - 1:
        if blob[j] == 0x6A:
            pushes.append(blob[j + 1])
            j += 2
        else:
            j += 1
    assert pushes[-4:-1] == [DAM, SHOTS, BAND], "ranged_stats would read %r" % pushes[-4:]


def check_id():
    """0xBE must be ours alone: no registration idiom outside our slot registers it, and
    ability_names gives it no other name.  Higher ids are other abilities, not a clash."""
    d = open(EPACK, "rb").read()
    module(EPACK, 0x55700000)
    _e, secs = P.sections(d)
    vs, sva, rs, ra = secs[0]
    used = []
    for i in range(ra + 5, ra + rs - 5):
        if d[i] == 0xE8:
            src = P.IMAGE_BASE + sva + (i - ra)
            dst = src + 5 + struct.unpack_from("<i", d, i + 1)[0]
            if dst in CTORS and d[i - 5] == 0xB8:
                used.append((struct.unpack_from("<I", d, i - 4)[0], src, CTORS[dst]))
    lo, hi = E_SLOT
    other = [(i, src, how) for i, src, how in used if i < 0x100 and not lo <= src < hi]
    clash = [u for u in other if u[0] == ABIL_ID]
    if clash:
        sys.exit("ABORT: %s at %08X also registers %#x -- re-derive ABIL_ID" % (clash[0][2], clash[0][1], ABIL_ID))
    top = max(u for u in other)
    sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
    import pfs, ability_names
    keys = {rid - 10 for rid, _b in pfs.load("ability.pfs")[0]}
    named = ability_names.names()
    if named.get(ABIL_ID, NAME) != NAME:
        sys.exit("ABORT: ability_names gives %#x to %r -- re-derive ABIL_ID" % (ABIL_ID, named[ABIL_ID]))
    print("  id %#x ours alone (highest other ctor-call id %#x, highest other named id %#x); Ability.pfs "
          "record %d %s; ability_names %s" % (
              ABIL_ID, top[0], max(k for k in named if k != ABIL_ID), ABIL_ID + 10,
              "present" if ABIL_ID in keys else "absent",
              "names it" if ABIL_ID in named else "DOES NOT NAME IT (add it to MODDED)"))


def report():
    """Shoot Bolt's live numbers against ours, and the couplings' state."""
    d = open(EPACK, "rb").read()
    module(EPACK, 0x55700000)
    sb = {k: read_at(d, va) for k, va in SB_SITE.items() if k != "mask"}
    mo = P.va2off(d, SB_SITE["mask"])
    sb["types"] = struct.unpack_from("<H", d, P.va2off(d, struct.unpack_from("<I", d, mo)[0]))[0]
    ours = dict(atk=ATK, dam=DAM, shots=SHOTS, band=BAND)
    drift = [k for k in ("atk", "shots", "band") if sb[k] != ours[k]]     # DAM is the owner's own
    print("  Shoot Bolt live %d/%d, %d shot(s), band %d, types %#06x;  Bane Javelin %d/%d, %d, %d, "
          "types %#06x%s" % (sb["atk"], sb["dam"], sb["shots"], sb["band"], sb["types"],
                             ATK, DAM, SHOTS, BAND, TYPES,
                             "" if not drift else "   ⚠ DIFFERS in " + ", ".join(drift)))
    t = open(TCPCK, "rb").read()
    module(TCPCK, 0x00400000)
    ref = t[P.va2off(t, ABILTYPES_REF):P.va2off(t, ABILTYPES_REF) + 6]
    if ref != bytes.fromhex("8a8040944600"):
        sys.exit("ABORT: AbilTypes is not at %08X (%s at %08X) -- apply build_abiltypes_relocate.py "
                 "first" % (ABILTYPES, ref.hex(" "), ABILTYPES_REF))
    ladder = read_at(t, 0x00418A76)                     # TCAI.EvalBattle scan 1 terminator imm
    panel = read_at(t, 0x0042354D)                      # CreateTCAbList terminator imm
    print("  AbilTypes relocated: yes;  ceilings: EvalBattle %#04x, combat panel %#04x%s" % (
        ladder, panel, "" if min(ladder, panel) > ABIL_ID else
        "   ⚠ below %#04x: raise LADDER in build_abilityid_ceilings.py and build_tcablist_ceiling.py"
        % (ABIL_ID + 1)))


def go(argv):
    module(EPACK, 0x55700000)
    run("build_banejavelin [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR, argv)
    module(TCPCK, 0x00400000)
    run("build_banejavelin [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, T_INTERIOR, argv)


if __name__ == "__main__":
    self_checks()
    check_id()
    report()
    argv = sys.argv[1:]
    if "--apply" in argv or "--undo" in argv:
        go([a for a in argv if a not in ("--apply", "--undo")])   # both modules verify first
        print("\n" + "=" * 60)
    go(argv)
    if "--apply" in argv:
        sys.path.insert(0, os.path.join(HERE, "..", "re_tools"))
        import ranged_stats
        got = ranged_stats.stats(EPACK).get(ABIL_ID)
        want = {"atk": ATK, "dam": DAM, "shots": SHOTS, "band": BAND}
        assert got and all(got[k] == v for k, v in want.items()), "ranged_stats reads %r" % got
        print("  ranged_stats reads %#x back: %d/%d, %d shot, band %d" % (
            ABIL_ID, got["atk"], got["dam"], got["shots"], got["band"]))
