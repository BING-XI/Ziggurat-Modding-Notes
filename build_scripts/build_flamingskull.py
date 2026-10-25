#!/usr/bin/env python
r"""
build_flamingskull.py -- Hurl Flaming Skull (ability 0xBF): Hurl Boulder with physical, fire, death and
wall damage.  AoWEPACK.dpl + AoWTCPCK.dpl.  Owner's design 2026-10-19; the owner assigns the units.

WHAT IT IS
    A TRangedAttackAbility built by the ranged ctor 0x5576ED48 with Hurl Boulder's (0x18) live
    attack, shots and range, two less damage, and the damage-type word 0x01A1 (Fire 0x01 | Death 0x20 | Physical 0x80 | Wall 0x100):
        ATK 8   DAM 11   1 shot   range band 3 (long, 12 hexes)   types Physical + Fire + Death + Wall
    The cut vanilla ability: AoWEPACK's resourcestring AoWE.HurlFireSkullRStr (0x55709954, loaded by
    no code) and Combat.ILB entry 116, a flaming skull no record used.  The record
    (build_flamingskull_pfs.py) puts entry 116 in image slot 0 (the tactical flight sprite, as Fire
    Cannon flies Combat.ILB 112) and slot 40 (TRangedAttackCA.ShowObject 0x5576E550 draws slot 40 in
    the auto-combat replay).  The ctor's fifth argument, read by nothing, is that number: 0x74.

WALLS -- WHY THE DAMAGE BIT ALONE DOES NOTHING
    dtWall (0x100) does two things by itself: TCombatWall.GetImmunityTypes 0x55725C40 is "everything
    but dtWall", so a hit carrying it can damage a wall object, and TRangedAttackAbility
    .GetWallCombatFeatures 0x5576E6D4 reports wcWallBreaching.  But nothing asks the ability.  The
    unit-level TAbstractUnit.GetWallCombatFeatures 0x5577ECCC (VMT +0x120, cached per combat unit at
    [+0x55] by TCombatUnit.UpdateWallCombatFeatures) grants wcWallBreaching by ability id -- Wall
    Crushing 0x75, Hurl Boulder 0x18, Self Destruct 0x41, Fire Cannon 0x2C -- and that is what
    TTacticalCombat.ValidateWallCombat 0x00429540 (a side behind walls with no breacher or passer has
    no fight), TFastCombat.AttackerCanCrushWall 0x557446F4 and the strategic predictor read.  And in
    manual combat a wall is damaged by a map-field message, not by the shot's CA:
    TCAbRangedTE.Execute sends 0x31001 for Hurl Boulder and 0x31002 for Fire Cannon to the impact
    hex, and the TCityWall / TCombatTerrain / TCombatStructure MapFieldMsgProc handlers price the hit
    off GetAbility(0x18) / GetAbility(0x2C) .GetCombatInfo.  A new id with the wall bit therefore
    breaches nothing, which is the failure an earlier wall-type ability met.

    So: GetWallCombatFeatures also accepts 0xBF; the TE routes 0xBF into Hurl Boulder's 0x31001 case
    and stores the ability id in the message's +0xC (unused by 0x31001; only the TE sends 0x31001);
    the three handlers read that id instead of the constant 0x18.

THE OTHER ID SITES (re_tools/idladder.py, abquery.py, immediate scan for 0x18 and 0x2C)
    AoWTCPCK  MakeAbilPath 0x004271EC        0x16/0x18/0x19 lob at arc 100; any other id arc 50
    AoWTCPCK  TCAI.CheckUnit 0x004175B0      0x18/0x2C -> EvalPath with the wall flag
    AoWTCPCK  TCAI.CheckUnit 0x004178DE      the same flag for the second EvalPath
    AoWEPACK  GetUnitIndexAIPriority         +100 for wall breakers (0x18/0x2C) at 0x5575BC15
    plus AbilTypes[0xBF] = 2, Hurl Boulder's category.  The fire part does not ignite the impact hex
    (that is the 0x31012 message of Flame Throwing and the breaths); fire damage still sets Burning
    through the damage types.

REGISTRATION (package init -- prove by launching the exe)
    Spliced at Hurl Boulder's `call RegisterAbility` 0x5576F6A7 in the ranged-registration routine
    0x5576F2EC (EBX = the control), replayed first.  Name "Hurl Flaming Skull", an AnsiString literal
    behind a call/pop anchor.  Ability.pfs tag 9 sets the mask (0x03FF).

HOOKS (vanilla bytes asserted, no .reloc under any)
  AoWEPACK.dpl
    R  0x5576F6A7  call RegisterAbility -> call cave_reg
    W  0x5577ED64  mov edx,0x2C (5 B) -> jmp cave_wcf         0x75/0x18/0x41/0x2C/0xBF -> breaching
    P  0x5575BC26  mov edx,0x2C (5 B) -> jmp cave_aip         0x18/0x2C/0xBF -> +100
  AoWTCPCK.dpl
    C  0x004694FF  AbilTypes[0xBF] 00 -> 02
    M  0x004271FD  movsx/cmp 0x34 (7 B) -> jmp cave_arc       0xBF -> 0x427298 (lob)
    A  0x004175AD  mov/cmp 0x2D (6 B) -> jmp cave_ai          0xBF -> 0x41766D (EvalPath, walls)
    F  0x004178DE  cmp 0x18/je (6 B) -> jmp cave_flag         0xBF -> wall flag 1
    T  0x0040C721  jae 0x40CAF2 (6 B) -> jmp cave_te          0xBF -> cave_msg
    B  0x0040C783  mov [ebp-0x64],0x31001 (7 B) -> jmp cave_msg   msg+0xC := the ability id
    H1 0x00405E0A  mov edx,0x18 -> call cave_hid              TCityWall.MapFieldMsgProc
    H2 0x00410310  mov edx,0x18 -> call cave_hid              TCombatTerrain.MapFieldMsgProc
    H3 0x00432BC5  mov edx,0x18 -> call cave_hid              TCombatStructure.MapFieldMsgProc

Slots: AoWEPACK 0x5589FC00-0x5589FFFF exclusive; AoWTCPCK 0x0043B700-0x0043B7FF exclusive.  PIC:
rel32 and one call/pop anchor; no absolute address.

RNG: none added or moved.  The wall handlers keep their own synced draw (TAoWHSMap.Random) exactly as
for Hurl Boulder; only the ability whose combat info they read changes.

Couplings.
  * Ceilings: LADDER 0xC0 in build_abilityid_ceilings.py and build_tcablist_ceiling.py;
    re_tools/ability_names.py MODDED names 0xBF.
  * build_abiltypes_relocate.py --undo zeroes this script's category byte: undo this first.
  * build_banejavelin.py hooks the same two AoWTCPCK ladders at other instructions (their default
    exits) and GetUnitIndexAIPriority at 0x5575BB37; no byte is shared.
  * Hurl Boulder's attack, shots and range are copied (damage is the owner's 11, Hurl Boulder's 13
    less two): the dry run flags drift in those three.
  * build_combatlog_siege.py derives its SetHitPoints tables from the live TCityWall and
    TCombatStructure MapFieldMsgProcs, through H1 and H3: its hid_id() recognises cave_hid by
    shape (mov edx,[ebp-8] / mov edx,[edx+0xC] / cmp / je / mov edx,0x18 / ret) and reads the 0x18.
    Reshaping cave_hid makes that script abort at import; update its HID_SHAPE with it.  Order is
    free: its tables are the same with or without this script.

Unproven, static checks cannot reach it: that the AI sieges with it, the wall damage on screen, and
where the skull sits on its flight path (slot 0 centres it on the path, as Hurl Boulder's frames are).

Undo: --undo is surgical.  Remove Hurl Flaming Skull from every unit and item and run
build_flamingskull_pfs.py --undo first.

    python build_scripts/build_flamingskull.py            dry run + state, both modules
    python build_scripts/build_flamingskull.py --apply
    python build_scripts/build_flamingskull.py --undo
    python build_scripts/build_flamingskull.py --dis
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

ABIL_ID = 0xBF
NAME = "Hurl Flaming Skull"
ATK, DAM, SHOTS, BAND = 8, 11, 1, 3              # Hurl Boulder's, DAM 13 -> 11 (owner 2026-10-19)
TYPES = 0x01A1                                   # Fire | Death | Physical | Wall
FC_ICON = 0x74                                   # Combat.ILB 116, the ctor's unread argument
CATEGORY = 2                                     # AbilTypes: Hurl Boulder's

REGISTER = 0x55750238
CREATE_RANGED = 0x5576ED48
CTORS = {0x5576601C: "CreateEnhancementAbility", CREATE_RANGED: "ranged ctor",
         0x5576EDE8: "bolt ctor", 0x5576EE84: "breath ctor"}
R_SITE = 0x5576F6A7
W_SITE, W_YES, W_NO = 0x5577ED64, 0x5577ED77, 0x5577ED80
P_SITE, P_YES, P_NEXT = 0x5575BC26, 0x5575BC59, 0x5575BC37
MOV_EDX_2C = bytes.fromhex("ba2c000000")
HB_SITE = {"dam": 0x5576F66E, "shots": 0x5576F670, "band": 0x5576F672, "atk": 0x5576F698,
           "mask": 0x5576F675}                   # Hurl Boulder's block

ABILTYPES = 0x00469440
ABILTYPES_REF = 0x0041EC66
C_SITE = ABILTYPES + ABIL_ID
M_SITE, M_LOB, M_RESUME = 0x004271FD, 0x00427298, 0x00427204
M_VAN = bytes.fromhex("0fbf45fc83f834")              # movsx eax,word [ebp-4] / cmp eax,0x34
A_SITE, A_EVAL_WALL, A_RESUME = 0x004175AD, 0x0041766D, 0x004175B3
A_VAN = bytes.fromhex("8b45a483f82d")                # mov eax,[ebp-0x5c] / cmp eax,0x2d
F_SITE, F_YES, F_NEXT = 0x004178DE, 0x004178EE, 0x004178E4
F_VAN = bytes.fromhex("837da418740a")                # cmp dword [ebp-0x5c],0x18 / je 0x4178EE
T_SITE, T_FIRE, T_SKIP = 0x0040C721, 0x0040C727, 0x0040CAF2
T_VAN = bytes.fromhex("0f83cb030000")                # jae 0x40CAF2
B_SITE, B_RESUME = 0x0040C783, 0x0040C78A
B_VAN = bytes.fromhex("c7459c01100300")              # mov dword [ebp-0x64],0x31001
H_SITES = (0x00405E0A, 0x00410310, 0x00432BC5)
H_VAN = bytes.fromhex("ba18000000")                  # mov edx,0x18
HURL_BOULDER = 0x18

E_SLOT = (0x5589FC00, 0x558A0000)
T_SLOT = (0x0043B700, 0x0043B800)


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def ansistr(s):
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def build_reg(va):
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


def build_wcf(va):
    """TAbstractUnit.GetWallCombatFeatures: ESI = the unit, BL = the features so far."""
    return asm(f"""
        mov  edx, 0x2c
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  {W_YES:#x}
        mov  edx, {ABIL_ID:#x}
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  {W_YES:#x}
        jmp  {W_NO:#x}
    """, va)


def build_aip(va):
    """GetUnitIndexAIPriority's wall-breaker test: EBX = the unit resource, [EBX+0x38] its owner."""
    return asm(f"""
        mov  edx, 0x2c
        mov  eax, dword ptr [ebx + 0x38]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne  {P_YES:#x}
        mov  edx, {ABIL_ID:#x}
        mov  eax, dword ptr [ebx + 0x38]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne  {P_YES:#x}
        jmp  {P_NEXT:#x}
    """, va)


def build_arc(va):
    return asm(f"""
        movsx eax, word ptr [ebp - 4]
        cmp  eax, {ABIL_ID:#x}
        je   {M_LOB:#x}
        cmp  eax, 0x34
        jmp  {M_RESUME:#x}
    """, va)


def build_ai(va):
    return asm(f"""
        mov  eax, dword ptr [ebp - 0x5c]
        cmp  eax, {ABIL_ID:#x}
        je   {A_EVAL_WALL:#x}
        cmp  eax, 0x2d
        jmp  {A_RESUME:#x}
    """, va)


def build_flag(va):
    return asm(f"""
        cmp  dword ptr [ebp - 0x5c], 0x18
        je   {F_YES:#x}
        cmp  dword ptr [ebp - 0x5c], {ABIL_ID:#x}
        je   {F_YES:#x}
        jmp  {F_NEXT:#x}
    """, va)


def build_msg(va):
    """Hurl Boulder's impact case: the message's +0xC ([ebp-0x58]) := the ability id, which the
    three wall/terrain/structure handlers read through cave_hid."""
    return asm(f"""
        mov  eax, dword ptr [ebp - 0x20]
        mov  eax, dword ptr [eax + 0x14]
        mov  dword ptr [ebp - 0x58], eax
        mov  dword ptr [ebp - 0x64], 0x31001
        jmp  {B_RESUME:#x}
    """, va)


def build_te(va, msg):
    """The ladder's last rung: flags from `sub eax,5` (CF set = a breath); [EBP-0x20]+0x14 = the id."""
    return asm(f"""
        jb   {T_FIRE:#x}
        mov  eax, dword ptr [ebp - 0x20]
        cmp  dword ptr [eax + 0x14], {ABIL_ID:#x}
        je   {msg:#x}
        jmp  {T_SKIP:#x}
    """, va)


def build_hid(va):
    """Replaces `mov edx,0x18` before GetAbility in the 0x31001 handlers; [EBP-8] = the message."""
    return asm(f"""
        mov  edx, dword ptr [ebp - 8]
        mov  edx, dword ptr [edx + 0xc]
        cmp  edx, {ABIL_ID:#x}
        je   h_out
        mov  edx, {HURL_BOULDER:#x}
    h_out:
        ret
    """, va)


def layout(slot, specs):
    caves, va, at = [], slot[0], {}
    for name, fn in specs:
        blob = fn(va, at)
        caves.append((name, va, blob))
        at[name] = va
        va = (va + len(blob) + 0xF) & ~0xF
    return at, caves


E_AT, E_CAVES = layout(E_SLOT, [("cave_reg", lambda v, a: build_reg(v)),
                                ("cave_wcf", lambda v, a: build_wcf(v)),
                                ("cave_aip", lambda v, a: build_aip(v))])
T_AT, T_CAVES = layout(T_SLOT, [("cave_arc", lambda v, a: build_arc(v)),
                                ("cave_ai", lambda v, a: build_ai(v)),
                                ("cave_flag", lambda v, a: build_flag(v)),
                                ("cave_msg", lambda v, a: build_msg(v)),
                                ("cave_te", lambda v, a: build_te(v, a["cave_msg"])),
                                ("cave_hid", lambda v, a: build_hid(v))])

E_HOOKS = [(R_SITE, call_to(R_SITE, REGISTER), call_to(R_SITE, E_AT["cave_reg"])),
           (W_SITE, MOV_EDX_2C, jmp_to(W_SITE, E_AT["cave_wcf"], 5)),
           (P_SITE, MOV_EDX_2C, jmp_to(P_SITE, E_AT["cave_aip"], 5))]
E_INTERIOR = [(W_SITE, W_SITE + 5, 0x5577ECCC, 0x5577ED85),
              (P_SITE, P_SITE + 5, 0x5575B9D0, 0x5575BC99)]
T_HOOKS = ([(C_SITE, b"\x00", bytes([CATEGORY])),
            (M_SITE, M_VAN, jmp_to(M_SITE, T_AT["cave_arc"], len(M_VAN))),
            (A_SITE, A_VAN, jmp_to(A_SITE, T_AT["cave_ai"], len(A_VAN))),
            (F_SITE, F_VAN, jmp_to(F_SITE, T_AT["cave_flag"], len(F_VAN))),
            (T_SITE, T_VAN, jmp_to(T_SITE, T_AT["cave_te"], len(T_VAN))),
            (B_SITE, B_VAN, jmp_to(B_SITE, T_AT["cave_msg"], len(B_VAN)))]
           + [(h, H_VAN, call_to(h, T_AT["cave_hid"])) for h in H_SITES])
T_INTERIOR = [(M_SITE, M_SITE + len(M_VAN), 0x004271EC, 0x00427626),
              (A_SITE, A_SITE + len(A_VAN), 0x004152A8, 0x00418170),
              (F_SITE, F_SITE + len(F_VAN), 0x004152A8, 0x00418170),
              (T_SITE, T_SITE + len(T_VAN), 0x0040B2F8, 0x0040CB00),
              (B_SITE, B_SITE + len(B_VAN), 0x0040B2F8, 0x0040CB00)]


def module(path, base):
    P.TARGET, P.IMAGE_BASE = path, base


def read_at(d, va):
    return d[P.va2off(d, va)]


def self_checks():
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
            assert "0xffffff" not in i.op_str, "%s %08X: sign-extended immediate: %s %s" % (
                name, i.address, i.mnemonic, i.op_str)
    _n, va, blob = E_CAVES[0]
    k = blob.index(b"\xE8\x00\x00\x00\x00")
    disp = struct.unpack_from("<i", blob, k + 8)[0]
    assert blob[k + 5] == 0x58 and blob[k + 6:k + 8] == b"\x8D\x90"
    assert blob[k + 5 + disp:k + 5 + disp + len(NAME)] == NAME.encode("latin1"), "anchor misses the name"
    hits = [j for j in range(len(blob) - 5) if blob[j] == 0xE8
            and va + j + 5 + struct.unpack_from("<i", blob, j + 1)[0] == CREATE_RANGED]
    assert len(hits) == 1
    i = hits[0]
    assert blob[i - 5] == 0xB8 and struct.unpack_from("<I", blob, i - 4)[0] == ABIL_ID
    assert blob[i - 7] == 0xB1 and blob[i - 6] == ATK
    pushes, j = [], max(0, i - 0x50)
    while j < i - 1:
        if blob[j] == 0x6A:
            pushes.append(blob[j + 1]); j += 2
        else:
            j += 1
    assert pushes[-4:-1] == [DAM, SHOTS, BAND], "ranged_stats would read %r" % pushes[-4:]


def check_id():
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
    d = open(EPACK, "rb").read()
    module(EPACK, 0x55700000)
    hb = {k: read_at(d, va) for k, va in HB_SITE.items() if k != "mask"}
    mo = P.va2off(d, HB_SITE["mask"])
    hb["types"] = struct.unpack_from("<H", d, P.va2off(d, struct.unpack_from("<I", d, mo)[0]))[0]
    ours = dict(atk=ATK, dam=DAM, shots=SHOTS, band=BAND)
    drift = [k for k in ("atk", "shots", "band") if hb[k] != ours[k]]     # DAM is the owner's own
    print("  Hurl Boulder live %d/%d, %d shot(s), band %d, types %#06x;  Flaming Skull %d/%d, %d, %d, "
          "types %#06x%s" % (hb["atk"], hb["dam"], hb["shots"], hb["band"], hb["types"],
                             ATK, DAM, SHOTS, BAND, TYPES,
                             "" if not drift else "   ⚠ DIFFERS in " + ", ".join(drift)))
    t = open(TCPCK, "rb").read()
    module(TCPCK, 0x00400000)
    ref = t[P.va2off(t, ABILTYPES_REF):P.va2off(t, ABILTYPES_REF) + 6]
    if ref != bytes.fromhex("8a8040944600"):
        sys.exit("ABORT: AbilTypes is not at %08X -- apply build_abiltypes_relocate.py first" % ABILTYPES)
    ladder, panel = read_at(t, 0x00418A76), read_at(t, 0x0042354D)
    print("  AbilTypes relocated: yes;  ceilings: EvalBattle %#04x, combat panel %#04x%s" % (
        ladder, panel, "" if min(ladder, panel) > ABIL_ID else
        "   ⚠ below %#04x: raise LADDER in build_abilityid_ceilings.py and build_tcablist_ceiling.py"
        % (ABIL_ID + 1)))


def go(argv):
    module(EPACK, 0x55700000)
    run("build_flamingskull [AoWEPACK]", E_HOOKS, E_CAVES, E_SLOT, E_INTERIOR, argv)
    module(TCPCK, 0x00400000)
    run("build_flamingskull [AoWTCPCK]", T_HOOKS, T_CAVES, T_SLOT, T_INTERIOR, argv)


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
