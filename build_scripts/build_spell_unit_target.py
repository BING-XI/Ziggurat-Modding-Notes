#!/usr/bin/env python
r"""
build_spell_unit_target.py -- single-unit spells cannot be cast on an empty hex in tactical
combat, and the cursor says so (owner's report 2026-10-04, widened the same day).  AoWTCPCK.dpl.

VANILLA
    TCombatUnitSelectionControl.MouseDownEvent @0x41EE28 resolves the clicked hex's unit
    (field VMT +0x80, ClassID 0x220104) into [ebp-8].  With a unit there, the side test at
    0x41F5C3..0x41F63F checks the spell's target flags (GetCombatInfo byte +7, [spell+0x3B]:
    1 friendly, 2 enemy), which is why a friendly hex refuses Lethargy.  With no unit,
    0x41F593 `cmp [ebp-8],0 / jne` falls through to 0x41F599 `mov eax,[ebp-4] / call
    ExecuteMoveSelection` with no flag test at all.  ExecuteMoveSelection @0x41E408 reads the
    spell's tactical class (AoWTC.SpellTypes[id]); every class but 0 and 4 computes a ranged path
    and issues the cast at the hex.  Vanilla Slow did the same.

    UpdateMoveCursor @0x41F6E8 mirrors it: an empty hovered hex ([ebp-0x14] == 0) goes to
    0x41F8AF, the animated hex-target cursor (frames 0x55..0x58 in [ctrl+0x2C]); a refused unit
    target gets frame 0x59 at 0x41F99D / 0x41FA0B.

    Neither SpellTypes (class 7 also holds Call Flames) nor [spell+0x3B] (2 for every combat
    spell: TCombatSpell.Create @0x557F7200, never overridden) tells unit-only spells apart, so
    the rule is a spell-id list.

THE RULE  (cave pred: EAX = selected unit's HS, EDX = the target hex's field -> AL = 1 refuse)
    Only when the HS is casting ([hs+0x34] == 0x34, the spellcasting ability) and the hex has no
    unit (both callers test that first):
      * UNIT_ONLY -- every combat-castable class-7 spell that acts on a unit: refused.
        Desiccate (41, class 7) is a world-map land spell (TRejuvenate) and is not listed.
      * CALL_FLAMES (113) -- refused unless the hex holds something it damages or ignites:
          - a wooden wall still standing: TCityWall (ClassID 0x220504) with [+0x2D] == 1 (wood;
            2 stone, the encoding build_townquake_retune.py records) and HP [+0x20] > 0.
            TCityWall.MapFieldMsgProc slot 0xB (message 0x3100B) damages only that case, and
            CombatFire.CreateFire @0x406D64 ignites only that case;
          - a Combat Structure (0x220506) or a Combat Terrain object (0x220166): their
            MapFieldMsgProc slot 0xB (0x432DB9 / 0x4104E8) damages them unconditionally.
        Bare ground is refused even where CreateFire would light it (flammable decoration or a
        burnable TCombatILTerrain, 0x220136).
      Call Flames sends 0x3100B to the hex and then calls CreateFire(100) --
      TCAbRangedTE.Execute 0x40CA99.

SITES
    C  0x41F59C  MouseDownEvent's empty-hex `call ExecuteMoveSelection` -> cave_click (call
                 retarget, nothing displaced).  cave_click rebuilds the clicked field exactly as
                 MouseDownEvent did at 0x41F4A8 (GetField(container [scr+0x10], GetXhx, GetYhx,
                 level [scr+0x88]) with scr = [0x46C064], reached PIC), asks pred, and returns
                 without casting on a refusal; otherwise tail-jumps to ExecuteMoveSelection with
                 EAX restored.  The caller continues at 0x41F5A1 `jmp 0x41F6D4`, the exit.
    U  0x41F8AF  UpdateMoveCursor's empty/self branch, 8 bytes (`mov eax,[ebp-4] / cmp word
                 [eax+0x2C],0x55`) -> jmp cave_cursor + 3 nop.  The branch is also reached for
                 the caster's own hex ([ebp-0x14] == [ebp-0x10]); that case is left vanilla.  On
                 a refusal the cave sets frame 0x59 and jumps to 0x41FA14, the cursor commit
                 vanilla's refusals use; otherwise it replays the 8 bytes and resumes at 0x41F8B7
                 with the flags of the replayed cmp.  [ebp-8] is the hovered field (0x41F780).

MULTIPLAYER / REPLAYS
    Local input and cursor only: a refused click issues no command.  No state, no random draws.
    The tactical AI does not go through either site.

Since 2026-10-25 UNIT_ONLY is tested as a 128-bit set held in four immediates (the cmp ladder had
no room for Regeneration and Enmity of Nine Hells), and cave_click / cave_cursor are pinned at
0x0043AD50 / 0x0043ADB0, so a changed list re-tunes pred in place with --apply.

Zone 0x0043AC40-0x0043AE3F, exclusive (above build_wallcrush_dam.py's zone).  PIC: rel32 and one
call/pop anchor for the screen variable.  Surgical --undo.  --apply re-tunes the 2026-10-04 v1
(site C only, Lethargy/Embrittle) in place.

    python build_scripts/build_spell_unit_target.py            dry run + state
    python build_scripts/build_spell_unit_target.py --apply
    python build_scripts/build_spell_unit_target.py --undo
    python build_scripts/build_spell_unit_target.py --dis      disassemble the caves
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

P.TARGET = os.path.join(P.GAME, "AoWTCPCK.dpl")
P.IMAGE_BASE = 0x00400000

SLOT = (0x0043AC40, 0x0043AE40)
PRED = 0x0043AC40                  # then cave_click, cave_cursor, 16-aligned

C_SITE = 0x0041F59C                 # MouseDownEvent: call ExecuteMoveSelection
EXEC_MOVE = 0x0041E408
U_SITE, U_RESUME, U_COMMIT = 0x0041F8AF, 0x0041F8B7, 0x0041FA14
U_VAN = bytes.fromhex("8b45fc6683782c55")   # mov eax,[ebp-4] / cmp word [eax+0x2c],0x55
FRAME_NO = 0x59

GET_HS = 0x0041D2E8                 # TCombatUnitSelectionControl.GetTCUnitHS (EAX = ctrl)
GET_X, GET_Y = 0x00402164, 0x0040216C   # HSEngine.THSMapMouse.GetXhx / GetYhx thunks
GET_FIELD = 0x00401E6C              # HSEngine.TMapContainer.GetField thunk
V_SCREEN = 0x0046C064               # AoWTCPCK BSS: the combat screen object

AB_CAST = 0x34
UNIT_ONLY = (8, 15, 16, 17, 32, 33, 35, 36, 37, 39, 40, 42, 43, 49, 55, 56, 77, 79, 82, 84,
             88, 90, 101, 109, 110, 111, 121)
#            Dispel Magic, Haste, Enchant Weapon, Stone Skin, Free Movement, Fury, Remedy,
#            Holy Champion, Unholy Champion, Concealment, Fire Halo, Water Walking, Wind Walking,
#            Liquid Form, Healing Water, Bless, Dark Gift, Regeneration, Enmity of Nine Hells,
#            Dwarven Satchels (battle-castable since 2026-10-25, build_battlecast_unitspells.py),
#            Mistform, Static Shield (2026-10-26),
#            Turn Undead,
#            Embrittle, Lethargy, Entangle, Vaporize
CALL_FLAMES = 113
CID_WALL, CID_STRUCT, CID_TERRAIN = 0x220504, 0x220506, 0x220166
WALL_MAT, WALL_HP, WOOD = 0x2D, 0x20, 1


def call_to(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5))


def build_pred(va):
    # UNIT_ONLY as a 128-bit set in four immediates (2026-10-25: the cmp ladder outgrew the room
    # before the pinned cave_click once Regeneration and Enmity joined)
    assert all(0 <= s < 128 for s in UNIT_ONLY)
    w = [sum(1 << (s & 31) for s in UNIT_ONLY if s >> 5 == k) for k in range(4)]
    return asm(f"""
        push  ebx
        push  esi
        mov   esi, edx
        xor   ebx, ebx
        test  eax, eax
        je    out
        cmp   dword ptr [eax + 0x34], {AB_CAST:#x}
        jne   out
        mov   ecx, dword ptr [eax + 0x38]
        cmp   ecx, 127
        ja    notset
        mov   edx, ecx
        shr   edx, 5
        mov   eax, {w[0]:#x}
        dec   edx
        js    test_bit
        mov   eax, {w[1]:#x}
        dec   edx
        js    test_bit
        mov   eax, {w[2]:#x}
        dec   edx
        js    test_bit
        mov   eax, {w[3]:#x}
    test_bit:
        bt    eax, ecx
        jb    refuse
    notset:
        cmp   ecx, {CALL_FLAMES}
        jne   out
        test  esi, esi
        je    out
        mov   eax, esi
        mov   edx, {CID_WALL:#x}
        mov   ecx, dword ptr [eax]
        call  dword ptr [ecx + 0x80]
        test  eax, eax
        je    nowall
        cmp   byte ptr [eax + {WALL_MAT:#x}], {WOOD}
        jne   nowall
        cmp   dword ptr [eax + {WALL_HP:#x}], 0
        jg    out
    nowall:
        mov   eax, esi
        mov   edx, {CID_STRUCT:#x}
        mov   ecx, dword ptr [eax]
        call  dword ptr [ecx + 0x80]
        test  eax, eax
        jne   out
        mov   eax, esi
        mov   edx, {CID_TERRAIN:#x}
        mov   ecx, dword ptr [eax]
        call  dword ptr [ecx + 0x80]
        test  eax, eax
        jne   out
    refuse:
        mov   bl, 1
    out:
        mov   eax, ebx
        pop   esi
        pop   ebx
        ret
    """, va)


def build_click(va):
    head = asm("push eax\npush ebx\npush esi", va)
    anchor = va + len(head) + 5
    call = asm(f"call {anchor:#x}", va + len(head))
    body = asm(f"""
        pop   ebx
        mov   ebx, dword ptr [ebx + {(V_SCREEN - anchor) & 0xFFFFFFFF:#x}]
        call  {GET_HS:#x}
        mov   esi, eax
        xor   edx, edx
        test  ebx, ebx
        je    ask
        push  dword ptr [ebx + 0x88]
        mov   eax, dword ptr [ebx + 0xc]
        call  {GET_Y:#x}
        push  eax
        mov   eax, dword ptr [ebx + 0xc]
        call  {GET_X:#x}
        mov   edx, eax
        mov   eax, dword ptr [ebx + 0x10]
        pop   ecx
        call  {GET_FIELD:#x}
        mov   edx, eax
    ask:
        mov   eax, esi
        call  {PRED:#x}
        pop   esi
        pop   ebx
        test  al, al
        pop   eax
        jne   skip
        jmp   {EXEC_MOVE:#x}
    skip:
        ret
    """, anchor)
    return head + call + body


def build_cursor(va):
    return asm(f"""
        cmp   dword ptr [ebp - 0x14], 0
        jne   van
        mov   eax, dword ptr [ebp - 0x10]
        mov   edx, dword ptr [ebp - 8]
        call  {PRED:#x}
        test  al, al
        je    van
        mov   eax, dword ptr [ebp - 4]
        mov   word ptr [eax + 0x2c], {FRAME_NO:#x}
        jmp   {U_COMMIT:#x}
    van:
        mov   eax, dword ptr [ebp - 4]
        cmp   word ptr [eax + 0x2c], 0x55
        jmp   {U_RESUME:#x}
    """, va)


PINNED = {"cave_click": 0x0043AD50, "cave_cursor": 0x0043ADB0}   # the installed addresses: a
# longer UNIT_ONLY grows pred in place, so the hooks keep their bytes and --apply re-tunes it.


def layout():
    out = [("pred", PRED, build_pred(PRED))]
    assert PRED + len(out[0][2]) <= PINNED["cave_click"], "pred outgrew its room"
    out.append(("cave_click", PINNED["cave_click"], build_click(PINNED["cave_click"])))
    assert PINNED["cave_click"] + len(out[1][2]) <= PINNED["cave_cursor"], "cave_click outgrew its room"
    out.append(("cave_cursor", PINNED["cave_cursor"], build_cursor(PINNED["cave_cursor"])))
    return out


caves = layout()
CLICK, CURSOR = caves[1][1], caves[2][1]
hooks = [(C_SITE, call_to(C_SITE, EXEC_MOVE), call_to(C_SITE, CLICK)),
         (U_SITE, U_VAN, jmp_to(U_SITE, CURSOR, len(U_VAN)))]
interior = [(C_SITE, C_SITE + 5, 0x0041EE28, 0x0041F6E8),
            (U_SITE, U_SITE + len(U_VAN), 0x0041F6E8, 0x0041FD08)]

V1_CAVE, V1_LEN = 0x0043AC40, 37
V1_SHA = "b61aa3a642484164a7dd9c4bfd1646441dfdf8b04c4bf387734c6360d05b6279"


def clear_v1():
    """v1 (2026-10-04, site C only, 37 B at 0x43AC40): put site C back to vanilla and zero the old
    body so run() sees a vanilla file.  Only on --apply/--undo, and only for that exact body."""
    import hashlib
    if not ({"--apply", "--undo"} & set(sys.argv[1:])):
        return
    d = bytearray(open(P.TARGET, "rb").read())
    sc, vc = P.va2off(d, C_SITE), P.va2off(d, V1_CAVE)
    if bytes(d[sc:sc + 5]) != call_to(C_SITE, V1_CAVE):
        return
    if hashlib.sha256(bytes(d[vc:vc + V1_LEN])).hexdigest() != V1_SHA:
        sys.exit("ABORT: site C calls 0x%08X but the body there is not v1's" % V1_CAVE)
    P.kill_aow()
    d[sc:sc + 5] = call_to(C_SITE, EXEC_MOVE)
    d[vc:vc + V1_LEN] = bytes(V1_LEN)
    open(P.TARGET, "wb").write(d)
    print("cleared v1 (site C restored, 37 B zeroed)")


if __name__ == "__main__":
    clear_v1()
    run("build_spell_unit_target", hooks, caves, SLOT, interior)
