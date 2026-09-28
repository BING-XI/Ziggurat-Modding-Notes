#!/usr/bin/env python
r"""
build_fly_levels.py -- a party of flyers changes map level by clicking the Flying ability.
AoWEPACK.dpl only.  Owner design 2026-09-26.

THE RULES (owner rulings 2026-09-26)
    * Level order, top to bottom: Firmament (3), Surface (0), Caverns (1), Depths (2), and a
      future Abyss (4).  UP_T / DN_T below are that order as two lookup tables; a level index
      at or above the map's level count is refused, so the Abyss row is inert until it exists.
      Since 2026-09-27 a level DISABLED in the map's mask ([map+0x41C], build_maplevel4.py v4)
      is skipped: the walk continues past it in the same direction (fly_next), so with Caverns
      off a Surface flyer goes down to Depths.  The Yes/No prompt text is indexed by the pair
      (up target, down target) for the same reason.  The dry run executes the assembled
      fly_next against the Python fly_next() for every level, direction, mask and count.
    * UP is allowed when the hex directly above is Sky (0x0E) or Chasm (0x0B).
    * DOWN is allowed when the hex you stand on is Sky or Chasm AND the hex below is not
      Earth (7), Rock (8) or the border ring (0x0F) -- every down-flight is the exact reverse
      of an allowed up-flight.
    * Only the SELECTED units fly, and each of them must have Flying (ability id 1) and at least
      4 movement points; unselected units stay behind, as in a split move.  `gmask` takes the
      selection from TSelectedArmy.GetSelection when the clicked army is the selected one, and
      the whole army otherwise.
    * A flying transport carries its passengers (owner ruling 2026-09-27): when the flying units
      include a transport (TArmy.Transporter(army, mask), capacity > 0), only the transport needs
      Flying and 4 MP.  This is vanilla's own transport rule -- TArmy.MoveTypes / MovePoints /
      ValidTerrainEx look only at that unit when there is one.  A transport cannot fly off and
      strand passengers: TSelectedArmy.SetSelection already drops it from a selection that leaves
      carried units behind (TArmy.ValidateMoveSelection), so the remaining non-flyers are refused.
      Capacity is not re-checked at the flight, as vanilla does not re-check it at a move; it is
      enforced when units join the stack.  Passengers are drained to 0 MP with the transport
      (owner ruling 2026-09-27; cave_mv drains every unit on a vertical Sky/Chasm move, whatever
      its step cost -- TArmy.MovedTo passes passengers a step cost of 0).
    * The target hex must be empty or hold something of the mover's own (the move engine
      merges / enters exactly as it does through a cave).
    * The change costs ALL remaining movement.  A successful flight plays sound 0 of the Winds
      of Fury spell's library (spell 0x7E, SFX\ATTACK\WIND.WAV) for the mover only:
      GetSpell([AoWHSSet+0x84], 0x7E), library [spell+0x28] (TSpell.ReadWrite tag 0xB), PlayEx.
    * Exactly one direction valid -> clicking Flying takes it.  Both valid -> a Yes/No/Cancel
      popup: Yes = up, No = down, Cancel = stay.

THE UI -- no exe patch
    Flying is a TMovementAbility (its GetWallCombatFeatures tests [self+0xC] == 1).  Two of
    that class's VMT slots are repointed; each cave tests id == 1 and tail-jumps to the
    original for every other movement ability:
      +0x98 GetControlType  0x557B7374   -> cave_gct: id 1 -> [strategic] on a map with >1 level
      +0xB4 Activate        0x557B7390   -> cave_act
    GetControlType bit 0 is what makes an ability clickable: TGeneral.ManagerUpdate (exe
    0x455DAE) sorts such abilities to the front of the unit banner, whose click handler
    TUnitBanner.AbLBMouseDown (0x404327) calls Activate; the unit window enables its Use button
    on the same bit (T1AbilityLBChange 0x4098A0) and TUnitWindow.UseAbility (0x409F4C) calls
    Activate(ability, unit, var err) and shows `err` when it returns False.

THE MOVE -- the vanilla cave route
    cave_exec copies Cave.TCave.EnterEx @0x557B3A1C: a two-node TMovepath [target, start]
    (TXYLList items are x | y<<8 | level<<16 | cost<<24, END first), step cost 4 (= MIN_MP, so
    the path is always affordable), then
    MoveArmyEx(armyHS, selection mask, path, 0, 0) -- which builds the TMoveArmyTE and sends
    it through the token manager, so multiplayer, animation and fog are the vanilla ones.  The
    owner's view then follows to the new level and the army is re-selected, as EnterEx does.

    The ARMY comes from the clicked unit the way TSelectedArmy.SelectBuildRoad @0x55793B98
    does it: [unit+4] is its TArmy (IsClass-checked), TArmy.GetArmyHS gives the TArmyHS.
    ⚠ 0x20217 is the TArmyHS CLASS ID, not a "selected army" control: EnterEx's
    `[cave+4] -> vmt+0x80(0x20217)` asks the cave's MAP FIELD for the army standing on it
    (TAoWMapField.GetArmyHS 0x55771EB0 is exactly that call).  v1 sent it to the map object
    instead, hit an unrelated method, found no army and returned silently -- the click played
    its sound and did nothing.  The popup answer gets the army from
    TSelectedArmy.GetArmyHS([map+0xD8]) @0x557923E8.

TWO ENGINE GATES THE MOVE HAS TO PASS
  A. TMoveControl.ValidPath @0x557468E8 re-runs the pathfinder and requires each node's summed
     step cost to equal the pathfinder's cost for that hex.  The pathfinder's only vertical
     links are caves, so a fly path fails on every peer.  Hook the epilogue @0x55746979
     (`8B C3 59 5A 5D 5F`, 6 B) -> cave_vp: when vanilla said no, a two-node path whose nodes
     share x,y, whose levels are UP_T / DN_T neighbours and whose terrain obeys the rule above
     is accepted.  Map state only, so every peer agrees.  Everything else is untouched.
  B. The charge.  TArmy.MovedTo calls each unit's TAbstractUnit.MovedTo(old, new, stepCost)
     @0x55780328, which charges min(terrain cost, stepCost) and clamps at 0.  The clamp block
     @0x55780343..0x55780355 (19 B, register-only, no .reloc) is replaced by cave_mv: the same
     clamp, then a vertical move (same x,y, different level) with Sky or Chasm at either end
     charges 127, which the vanilla `cost > MP -> SetMovePoints(0)` turns into zero movement.
     It runs inside the synced move execution, so it is deterministic.  Downstream only
     waterheal's cave (0x557803BA -> 0x55824000) follows, and it only saves/restores EDI.
     A cave entrance whose hex is Sky or Chasm would drain too -- walkers cannot stand there,
     and no cave is placed on them today.

THE POPUP
    Cave entry's question box is Cave.TEnterCaveEventLog: a 0x2C-byte TMessageEventLog whose
    only overrides are Yes (+0x80) and No (+0x84); [log+0x25] is TMessageEventLogButtons
    (mebOk 0 / mebOkCancel 1 / mebYesNo 2 / mebYesNoCancel 3); [log+0x20] the text lines;
    VMT +0x70 shows it, +0x2C releases it.  Neither class is registered for streaming, so the
    popup behaves exactly as vanilla's cave prompt.  cave_popup clones that VMT ONCE per process
    into BSS 0x558FAA30..0x558FAAF7 (0xC8 B = VMT-0x40 .. +0x88) by copying the LIVE, already
    relocated table -- a clone assembled into the file would carry stale absolute pointers after
    the rebase -- and repoints Yes / No at cave_yes / cave_no (flag byte 0x558FAAF8).  [log+0x28]
    keeps the army pointer as an identity token: the answer compares it with the currently
    selected army (never dereferences it) and re-checks every rule before moving.

WARP PARTY (2026-09-27, owner ruling: Warp Party follows the flying order)
    TWarpParty.CalculateWarpLocation @0x557EB1DC picked destination levels by abs(L - cur) == 1,
    i.e. index adjacency.  cave_warp (hook 0x557EB2CE, 23 B) replaces that test with
    L == fly_next(cur, up) or L == fly_next(cur, down), so Depths warps to Caverns / the Abyss,
    Surface to Caverns / the Firmament, and disabled placeholders are never a destination.  It
    changes only which hexes are candidates; the spell's own synced draw is untouched.

Rolls: none.  PIC: rel32 calls, one call/pop anchor per entry point, BSS / data / IAT through
the load delta.  Slot 0x5584F800-0x558507FF (grown from 0x800 on 2026-09-27, relaid out after
a surgical --undo), exclusive.  Surgical --undo.
"""
import struct
import sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run

SLOT = (0x5584F800, 0x55850800)   # grown +0x800 on 2026-09-27 (fly_next + the pair texts)
BASE = SLOT[0]

# ---- engine ------------------------------------------------------------------
MAPVAR       = 0x558FA040      # AoWE.AoWHSMap
GETFIELD     = 0x557020FC      # HSEngine.TMapContainer.GetField(eax=cont, edx=x, ecx=y, [level])
GETPLAYER    = 0x55771C98      # TAoWMapField.GetPlayer -> al (-1 = nobody)
XYL_CREATE   = 0x55701CB4      # HSEngine.TXYLList.Create
XYL_ADD      = 0x55701CD4      # HSEngine.TXYLList.AddXYL(eax, edx=x, ecx=y, [level])
MOVEPATH_CLS = 0x5570D9B0      # cell -> AoWE..TMovepath
MOVEARMYEX   = 0x5574A318      # AoWE.MoveArmyEx(eax=sel, dl=mask, ecx=path, [0], [action]) ret 8
TOBJ_FREE    = 0x557010B8      # System.TObject.Free
SELECT       = 0x55793B70      # TSelectedArmy.Select(eax=[map+0xD8], edx=sel)
MSGLOG_NEW   = 0x557FE080      # EventLog.TMessageEventLog.Create
CAVELOG_VMT  = 0x557B335C      # Cave..TEnterCaveEventLog
LSTRASG_IAT  = 0x558FB674      # VCL30 System.@LStrAsg (IAT cell)
ISCLASS      = 0x557010C0      # System.@IsClass(eax=obj, edx=classref)
ARMY_CLS     = 0x557130AC      # cell -> AoWE..TArmy
ARMY_GETHS   = 0x5578C8B8      # TArmy.GetArmyHS(eax=army) -> TArmyHS | nil
SEL_GETHS    = 0x557923E8      # TSelectedArmy.GetArmyHS(eax=[map+0xD8]) -> TArmyHS | nil
SEL_GETSEL   = 0x5579240C      # TSelectedArmy.GetSelection(eax=[map+0xD8]) -> al unit mask
TRANSPORTER  = 0x5578E00C      # TArmy.Transporter(eax=army, dl=mask) -> first transport in mask | nil
SETVAR       = 0x558FA044      # AoWE.AoWHSSet
GETSPELL     = 0x55779AC8      # TSpellControl.GetSpell(eax=[set+0x84], edx=id)
PLAYEX       = 0x55702CFC      # Sound.TSFXLibrary.PlayEx(eax=lib, edx=idx, ecx=vol, 5 stack)
SFX_SPELL    = 0x7E            # TWindsOfFury's id; sound 0 of its library is SFX\ATTACK\WIND.WAV
SFX_VOLUME   = 0x32            # half volume (owner ruling 2026-09-27); 0x64 is the engine's full
MIN_MP       = 4               # owner ruling 2026-09-26: every flyer needs 4 MP; also the step cost
ABIL_FLY     = 1
SKY, CHASM   = 0x0E, 0x0B
EARTH, ROCK, BORDER = 7, 8, 0x0F

# level order Firmament 3 / Surface 0 / Caverns 1 / Depths 2 / Abyss 4, as up/down tables
NO = 0xFF
UP_T = [3, 0, 1, NO, 2]
DN_T = [1, 2, 4, 0, NO]
NAME = {0: "Surface", 1: "Caverns", 2: "Depths", 3: "Firmament", 4: "Abyss"}

# BSS: the popup class clone
CLONE      = 0x558FAA30        # VMT-0x40 .. VMT+0x88
CLONE_LEN  = 0xC8
CLONE_VMT  = CLONE + 0x40
CLONE_FLAG = CLONE + CLONE_LEN  # 0x558FAAF8
assert CLONE_FLAG < 0x558FAB00

# ---- sites -------------------------------------------------------------------
MOVEAB_VMT = 0x557B72DC                            # PassiveAb..TMovementAbility
GCT_SLOT, GCT_ORIG = MOVEAB_VMT + 0x98, 0x5574E730  # TAbility.GetControlType
ACT_SLOT, ACT_ORIG = MOVEAB_VMT + 0xB4, 0x5574EF68  # TAbility.Activate
VP_HOOK, VP_VAN = 0x55746979, bytes.fromhex("8bc3595a5d5f")
MV_HOOK, MV_VAN = 0x55780343, bytes.fromhex("8bf885ff7d058b7d08eb083b7d087e038b7d08")
MV_RESUME = 0x55780356
# Warp Party (2026-09-27, owner ruling): its destination levels are the FLYING neighbours.
# GlobalSpells.TWarpParty.CalculateWarpLocation @0x557EB1DC loops every level L and keeps those
# with abs(L - caster level) == 1 -- index adjacency, which sends Depths to the Firmament, never
# lets the Abyss reach Depths, and ignores disabled placeholders.  The 23-byte test
# (movsx .. jne 0x557EB372) becomes: L == fly_next(cur, up) or L == fly_next(cur, down).
# Entry: al = the caster's level (GetLevel), [esp+4] = L, [esp] = the army -- all live.
WARP_HOOK = 0x557EB2CE
WARP_VAN = bytes.fromhex("0fbec050" "8b442408" "5a" "2bc2" "99" "33c2" "2bc2" "48" "0f858d000000")
WARP_YES, WARP_NO = 0x557EB2E5, 0x557EB372


def astr(s):
    """Delphi 3 const AnsiString: refcount -1, length, chars, NUL, 4-aligned."""
    b = struct.pack("<iI", -1, len(s)) + s.encode("ascii") + b"\0"
    return b + b"\0" * (-len(b) % 4)


MSGS = {
    "none":  "There is nowhere to fly from here.",
    "nofly": "Every selected unit must be able to fly.",
    "nomp":  "Every selected unit needs 4 movement points.",
}
MASK_OFF = 0x41C               # the map's disabled-levels mask (build_maplevel4.py v4)


def fly_next(level, down, mask, count):
    """What the fly_next cave computes: walk UP_T / DN_T from `level`, skipping a
    level disabled in the map's mask; a missing level (>= count) ends the walk."""
    t = level
    while True:
        if not 0 <= t <= 4:
            return -1
        t = (DN_T if down else UP_T)[t]
        if t == NO or t >= count:
            return -1
        if not (mask >> t) & 1:
            return t


# The Yes/No prompt appears only when BOTH directions are open, and with levels
# skipped the pair of targets is no longer a function of the current level, so the
# text table is indexed [up target * 5 + down target].  Every pair any mask/count
# can produce gets a string; the rest stay 0 and the cave shows no prompt for them.
PAIRS = sorted({(fly_next(lv, 0, m, n), fly_next(lv, 1, m, n))
                for lv in range(5) for m in range(0, 64, 2) for n in range(1, 7)
                if fly_next(lv, 0, m, n) >= 0 and fly_next(lv, 1, m, n) >= 0})
POPUP = {p: "Fly up to the %s? Choose No to fly down to the %s." % (NAME[p[0]], NAME[p[1]])
         for p in PAIRS}
TXT_OFF = 0x10                 # 25 dwords
STR_OFF = 0x78


def layout():
    """Data block: UP_T @+0, DN_T @+8, pair text table @+0x10 (25 dwords), strings from +0x78."""
    data = bytearray(STR_OFF)
    data[0:5] = bytes(UP_T)
    data[8:13] = bytes(DN_T)
    addr = {}
    for key, s in list(MSGS.items()) + [(("pop", k), v) for k, v in POPUP.items()]:
        addr[key] = BASE + len(data) + 8            # the chars, past refcount + length
        data += astr(s)
    for (u, d) in PAIRS:
        struct.pack_into("<I", data, TXT_OFF + 4 * (u * 5 + d), addr[("pop", (u, d))])
    return bytes(data), addr


DATA, STR = layout()
UPT, DNT, TXT = BASE, BASE + 8, BASE + TXT_OFF


def anchor(reg, at):
    """call $+5 / pop reg / sub reg, link -> reg = load delta."""
    return f"call 0x{at + 5:X}\npop {reg}\nsub {reg}, 0x{at + 5:X}\n"


def anchored(prefix, reg, at):
    """`prefix` (label-free) followed by an anchor placed at its measured end."""
    return prefix + "\n" + anchor(reg, at + len(asm(prefix, at)))


def sources(a):
    """Every cave body, given the address map `a` (pass 1 uses placeholders)."""
    S = {}
    # ---- fly_next: eax=level dl=0 up / 1 down ebp=delta -> eax = next open level or -1 -------
    # Walks UP_T / DN_T, skipping levels disabled in the map's mask; a missing level (>= the
    # level count) or NO ends the walk.  Preserves everything but eax.
    S["fly_next"] = f"""
        push ecx
        push esi
        mov  ecx, [ebp+0x{MAPVAR:X}]
    fn_loop:
        cmp  eax, 4
        ja   fn_no
        test dl, dl
        jne  fn_dn
        movzx eax, byte ptr [ebp+eax+0x{UPT:X}]
        jmp  fn_t
    fn_dn:
        movzx eax, byte ptr [ebp+eax+0x{DNT:X}]
    fn_t:
        cmp  eax, {NO}
        je   fn_no
        mov  esi, [ecx+0x10]
        cmp  eax, [esi+0x14]
        jge  fn_no
        movzx esi, byte ptr [ecx+0x{MASK_OFF:X}]
        bt   esi, eax
        jb   fn_loop
        jmp  fn_ret
    fn_no:
        or   eax, -1
    fn_ret:
        pop  esi
        pop  ecx
        ret
    """
    # ---- fly_dir: ebx=army ebp=delta dl=0 up / 1 down -> eax = target level or -1 ----------
    S["fly_dir"] = f"""
        push esi
        push edi
        push edx
        movsx esi, byte ptr [ebx+0x15]
        mov  eax, esi
        mov  dl, byte ptr [esp]
        call 0x{a['fly_next']:X}
        test eax, eax
        js   fd_no
        mov  edi, eax
        push edi
        movsx edx, byte ptr [ebx+0x13]
        movsx ecx, byte ptr [ebx+0x14]
        call 0x{GETFIELD:X}
        test eax, eax
        jz   fd_no
        push eax
        call 0x{GETPLAYER:X}
        test al, al
        js   fd_occ
        cmp  al, [ebx+0x12]
        jne  fd_nop
    fd_occ:
        mov  eax, [esp]
        mov  dl, [eax+0x14]
        cmp  byte ptr [esp+4], 0
        jne  fd_down
        cmp  dl, {CHASM}
        je   fd_ok
        cmp  dl, {SKY}
        je   fd_ok
        jmp  fd_nop
    fd_down:
        cmp  dl, {EARTH}
        je   fd_nop
        cmp  dl, {ROCK}
        je   fd_nop
        cmp  dl, {BORDER}
        je   fd_nop
        push esi
        movsx edx, byte ptr [ebx+0x13]
        movsx ecx, byte ptr [ebx+0x14]
        mov  eax, [ebp+0x{MAPVAR:X}]
        mov  eax, [eax+0x10]
        call 0x{GETFIELD:X}
        test eax, eax
        jz   fd_nop
        mov  dl, [eax+0x14]
        cmp  dl, {CHASM}
        je   fd_ok
        cmp  dl, {SKY}
        je   fd_ok
    fd_nop:
        pop  eax
    fd_no:
        pop  edx
        or   eax, -1
        pop  edi
        pop  esi
        ret
    fd_ok:
        pop  eax
        pop  edx
        mov  eax, edi
        pop  edi
        pop  esi
        ret
    """
    # ---- gmask: ebx=army esi=armyHS ebp=delta -> eax = unit mask that flies -----------------
    # The selection when this army is the selected one; otherwise (or an empty selection) all.
    S["gmask"] = f"""
        mov  eax, [ebp+0x{MAPVAR:X}]
        mov  eax, [eax+0xD8]
        test eax, eax
        jz   gm_all
        push eax
        call 0x{SEL_GETHS:X}
        cmp  eax, esi
        pop  eax
        jne  gm_all
        call 0x{SEL_GETSEL:X}
        movzx edx, al
        call gm_full
        and  eax, edx
        jnz  gm_out
    gm_all:
        call gm_full
    gm_out:
        ret
    gm_full:
        mov  eax, [ebx+8]
        mov  ecx, [eax+8]
        mov  eax, 1
        shl  eax, cl
        dec  eax
        ret
    """
    # ---- fly_check: ebx=army ebp=delta edx=mask -> 0x100 no flyer / 0x200 short of MP /
    #      bits 1 up, 2 down.  Only the units in `mask` are checked; when `mask` holds a
    #      transport (TArmy.Transporter), only the transport is. -----------------------------
    S["fly_check"] = f"""
        push esi
        push edi
        push edx
        mov  eax, [ebx+8]
        test eax, eax
        jz   fc_zero
        mov  eax, ebx
        mov  edx, [esp]
        call 0x{TRANSPORTER:X}
        test eax, eax
        jz   fc_list
        mov  esi, eax
        call fc_one
        test eax, eax
        jnz  fc_out
        jmp  fc_loc
    fc_list:
        mov  eax, [ebx+8]
        mov  edi, [eax+8]
    fc_u:
        dec  edi
        js   fc_loc
        bt   dword ptr [esp], edi
        jnc  fc_u
        mov  eax, [ebx+8]
        mov  eax, [eax+4]
        mov  esi, [eax+edi*4]
        test esi, esi
        jz   fc_u
        call fc_one
        test eax, eax
        jnz  fc_out
        jmp  fc_u
    fc_loc:
        cmp  byte ptr [ebx+0x13], 0xFF
        je   fc_zero
        xor  esi, esi
        xor  edx, edx
        call 0x{a['fly_dir']:X}
        test eax, eax
        js   fc_d
        or   esi, 1
    fc_d:
        mov  dl, 1
        call 0x{a['fly_dir']:X}
        test eax, eax
        js   fc_r
        or   esi, 2
    fc_r:
        mov  eax, esi
        jmp  fc_out
    fc_zero:
        xor  eax, eax
    fc_out:
        pop  edx
        pop  edi
        pop  esi
        ret
    fc_one:
        mov  eax, esi
        mov  edx, {ABIL_FLY}
        mov  ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        jz   fo_nofly
        mov  eax, esi
        mov  ecx, [eax]
        call dword ptr [ecx+0xD8]
        cmp  al, {MIN_MP}
        jl   fo_nomp
        xor  eax, eax
        ret
    fo_nofly:
        mov  eax, 0x100
        ret
    fo_nomp:
        mov  eax, 0x200
        ret
    """
    # ---- fly_exec: ebx=army esi=armyHS ebp=delta edi=target level ---------------------
    S["fly_exec"] = f"""
        mov  dl, 1
        mov  eax, [ebp+0x{MOVEPATH_CLS:X}]
        call 0x{XYL_CREATE:X}
        push eax
        push edi
        movsx edx, byte ptr [ebx+0x13]
        movsx ecx, byte ptr [ebx+0x14]
        mov  eax, [esp+4]
        call 0x{XYL_ADD:X}
        mov  eax, [esp]
        mov  eax, [eax+4]
        mov  byte ptr [eax+3], {MIN_MP}
        movsx eax, byte ptr [ebx+0x15]
        push eax
        movsx edx, byte ptr [ebx+0x13]
        movsx ecx, byte ptr [ebx+0x14]
        mov  eax, [esp+4]
        call 0x{XYL_ADD:X}
        call 0x{a['gmask']:X}
        mov  edx, eax
        push 0
        push 0
        mov  ecx, [esp+8]
        mov  eax, esi
        call 0x{MOVEARMYEX:X}
        movzx ecx, al
        pop  eax
        push ecx
        call 0x{TOBJ_FREE:X}
        pop  eax
        test al, al
        jz   fe_out
        mov  eax, [ebp+0x{MAPVAR:X}]
        mov  dl, [eax+0xA5]
        cmp  dl, [ebx+0x12]
        jne  fe_out
        mov  eax, [ebp+0x{SETVAR:X}]
        mov  eax, [eax+0x84]
        test eax, eax
        jz   fe_view
        mov  edx, {SFX_SPELL}
        call 0x{GETSPELL:X}
        test eax, eax
        jz   fe_view
        mov  eax, [eax+0x28]
        test eax, eax
        jz   fe_view
        push 0
        push 0
        push 1
        push 0
        push 0
        mov  ecx, {SFX_VOLUME}
        xor  edx, edx
        call 0x{PLAYEX:X}
    fe_view:
        mov  eax, [ebp+0x{MAPVAR:X}]
        mov  edx, edi
        mov  ecx, [eax]
        call dword ptr [ecx+0xB8]
        mov  eax, [ebp+0x{MAPVAR:X}]
        mov  eax, [eax+0xD8]
        mov  edx, esi
        call 0x{SELECT:X}
    fe_out:
        ret
    """
    # ---- fly_popup: ebx=army ebp=delta ---------------------------------------------------
    S["fly_popup"] = f"""
        push esi
        push edi
        cmp  byte ptr [ebp+0x{CLONE_FLAG:X}], 0
        jne  p_have
        lea  esi, [ebp+0x{CAVELOG_VMT - 0x40:X}]
        lea  edi, [ebp+0x{CLONE:X}]
        mov  ecx, {CLONE_LEN // 4}
    p_cp:
        mov  eax, [esi]
        mov  [edi], eax
        add  esi, 4
        add  edi, 4
        dec  ecx
        jnz  p_cp
        lea  eax, [ebp+0x{CLONE_VMT:X}]
        mov  [ebp+0x{CLONE:X}], eax
        lea  eax, [ebp+0x{a['cave_yes']:X}]
        mov  [ebp+0x{CLONE_VMT + 0x80:X}], eax
        lea  eax, [ebp+0x{a['cave_no']:X}]
        mov  [ebp+0x{CLONE_VMT + 0x84:X}], eax
        mov  byte ptr [ebp+0x{CLONE_FLAG:X}], 1
    p_have:
        movsx esi, byte ptr [ebx+0x15]
        mov  eax, esi
        xor  edx, edx
        call 0x{a['fly_next']:X}
        test eax, eax
        js   p_out
        imul edi, eax, 5
        mov  eax, esi
        mov  dl, 1
        call 0x{a['fly_next']:X}
        test eax, eax
        js   p_out
        add  edi, eax
        mov  edi, [ebp+edi*4+0x{TXT:X}]
        test edi, edi
        je   p_out
        add  edi, ebp
        xor  ecx, ecx
        mov  dl, 1
        lea  eax, [ebp+0x{CLONE_VMT:X}]
        call 0x{MSGLOG_NEW:X}
        mov  esi, eax
        mov  [esi+0x28], ebx
        mov  edx, edi
        mov  eax, [esi+0x20]
        mov  ecx, [eax]
        call dword ptr [ecx+0x2C]
        mov  byte ptr [esi+0x25], 3
        push 0
        push 0
        mov  cl, 1
        mov  dl, 1
        mov  eax, esi
        mov  edi, [eax]
        call dword ptr [edi+0x70]
        mov  eax, esi
        mov  edx, [eax]
        call dword ptr [edx+0x2C]
    p_out:
        pop  edi
        pop  esi
        ret
    """
    # ---- cave_act: TMovementAbility VMT +0xB4.  eax=ability edx=unit ecx=&err -> al --------
    at = a["cave_act"]
    S["cave_act"] = anchored(f"""
        cmp  dword ptr [eax+0xC], {ABIL_FLY}
        jne  0x{ACT_ORIG:X}
        push ebx
        push esi
        push edi
        push ebp
        push ecx
        mov  edi, edx""", "ebp", at) + f"""
        mov  ebx, [edi+4]
        test ebx, ebx
        jz   a_fail
        mov  eax, ebx
        mov  edx, [ebp+0x{ARMY_CLS:X}]
        call 0x{ISCLASS:X}
        test al, al
        jz   a_fail
        mov  eax, ebx
        call 0x{ARMY_GETHS:X}
        test eax, eax
        jz   a_fail
        mov  esi, eax
        cmp  [esi+0x1C], ebx
        jne  a_fail
        mov  eax, [ebp+0x{MAPVAR:X}]
        mov  al, [eax+0xA5]
        cmp  al, [ebx+0x12]
        jne  a_fail
        call 0x{a['gmask']:X}
        mov  edx, eax
        call 0x{a['fly_check']:X}
        cmp  eax, 0x100
        je   a_nofly
        cmp  eax, 0x200
        je   a_nomp
        test eax, eax
        jz   a_none
        cmp  eax, 3
        je   a_both
        xor  edx, edx
        cmp  eax, 1
        je   a_one
        mov  dl, 1
    a_one:
        call 0x{a['fly_dir']:X}
        test eax, eax
        js   a_none
        mov  edi, eax
        call 0x{a['fly_exec']:X}
        jmp  a_true
    a_both:
        call 0x{a['fly_popup']:X}
    a_true:
        pop  ecx
        mov  al, 1
        jmp  a_out
    a_nofly:
        lea  edx, [ebp+0x{STR['nofly']:X}]
        jmp  a_msg
    a_nomp:
        lea  edx, [ebp+0x{STR['nomp']:X}]
        jmp  a_msg
    a_none:
        lea  edx, [ebp+0x{STR['none']:X}]
    a_msg:
        pop  eax
        call dword ptr [ebp+0x{LSTRASG_IAT:X}]
        xor  eax, eax
        jmp  a_out
    a_fail:
        pop  ecx
        xor  eax, eax
    a_out:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    # ---- cave_yes / cave_no: the popup's answers.  eax=log -> al=1 ------------------------
    S["cave_yes"] = f"""
        mov  dl, 0
        jmp  0x{a['cave_ans']:X}
    """
    S["cave_no"] = f"""
        mov  dl, 1
        jmp  0x{a['cave_ans']:X}
    """
    at = a["cave_ans"]
    S["cave_ans"] = anchored("""
        push ebx
        push esi
        push edi
        push ebp
        push edx
        mov  edi, eax""", "ebp", at) + f"""
        mov  eax, [ebp+0x{MAPVAR:X}]
        test eax, eax
        jz   n_out
        mov  eax, [eax+0xD8]
        test eax, eax
        jz   n_out
        call 0x{SEL_GETHS:X}
        test eax, eax
        jz   n_out
        mov  esi, eax
        mov  ebx, [esi+0x1C]
        test ebx, ebx
        jz   n_out
        cmp  ebx, [edi+0x28]
        jne  n_out
        mov  eax, [ebp+0x{MAPVAR:X}]
        mov  al, [eax+0xA5]
        cmp  al, [ebx+0x12]
        jne  n_out
        call 0x{a['gmask']:X}
        mov  edx, eax
        call 0x{a['fly_check']:X}
        cmp  eax, 3
        ja   n_out
        movzx edx, byte ptr [esp]
        lea  ecx, [edx+1]
        test eax, ecx
        jz   n_out
        call 0x{a['fly_dir']:X}
        test eax, eax
        js   n_out
        mov  edi, eax
        call 0x{a['fly_exec']:X}
    n_out:
        pop  edx
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        mov  al, 1
        ret
    """
    # ---- cave_gct: TMovementAbility VMT +0x98.  eax=ability -> al ------------------------
    at = a["cave_gct"]
    S["cave_gct"] = anchored(f"""
        cmp  dword ptr [eax+0xC], {ABIL_FLY}
        jne  0x{GCT_ORIG:X}
        push ecx""", "ecx", at) + f"""
        mov  ecx, [ecx+0x{MAPVAR:X}]
        test ecx, ecx
        jz   g0
        mov  ecx, [ecx+0x10]
        test ecx, ecx
        jz   g0
        cmp  dword ptr [ecx+0x14], 1
        jle  g0
        pop  ecx
        mov  al, 1
        ret
    g0:
        pop  ecx
        xor  eax, eax
        ret
    """
    # ---- cave_vp: ValidPath epilogue.  bl = vanilla verdict, esi = path; all else dead -----
    at = a["cave_vp"]
    S["cave_vp"] = anchor("ebp", at) + f"""
        test bl, bl
        jnz  v_done
        cmp  dword ptr [esi+8], 2
        jne  v_done
        mov  eax, [esi+4]
        mov  ecx, [eax]
        mov  edx, [eax+4]
        cmp  cx, dx
        jne  v_done
        mov  eax, ecx
        shr  eax, 16
        movzx edi, al
        mov  eax, edx
        shr  eax, 16
        movzx esi, al
        cmp  esi, 4
        ja   v_done
        movsx eax, cl
        movsx ecx, ch
        push ecx
        push eax
        mov  eax, esi
        xor  edx, edx
        call 0x{a['fly_next']:X}
        cmp  eax, edi
        je   v_up
        mov  eax, esi
        mov  dl, 1
        call 0x{a['fly_next']:X}
        cmp  eax, edi
        jne  v_pop
        push edi
        mov  edx, [esp+4]
        mov  ecx, [esp+8]
        mov  eax, [ebp+0x{MAPVAR:X}]
        mov  eax, [eax+0x10]
        call 0x{GETFIELD:X}
        test eax, eax
        jz   v_pop
        mov  dl, [eax+0x14]
        cmp  dl, {EARTH}
        je   v_pop
        cmp  dl, {ROCK}
        je   v_pop
        cmp  dl, {BORDER}
        je   v_pop
        mov  edi, esi
    v_up:
        push edi
        mov  edx, [esp+4]
        mov  ecx, [esp+8]
        mov  eax, [ebp+0x{MAPVAR:X}]
        mov  eax, [eax+0x10]
        call 0x{GETFIELD:X}
        test eax, eax
        jz   v_pop
        mov  dl, [eax+0x14]
        cmp  dl, {CHASM}
        je   v_ok
        cmp  dl, {SKY}
        jne  v_pop
    v_ok:
        mov  bl, 1
    v_pop:
        add  esp, 8
    v_done:
        mov  eax, ebx
        pop  ecx
        pop  edx
        pop  ebp
        pop  edi
        jmp  0x{VP_HOOK + 6:X}
    """
    # ---- cave_mv: TAbstractUnit.MovedTo clamp block, plus the vertical-fly drain ----------
    S["cave_mv"] = f"""
        mov  edi, eax
        test edi, edi
        jge  m1
        mov  edi, [ebp+8]
        jmp  m2
    m1:
        cmp  edi, [ebp+8]
        jle  m2
        mov  edi, [ebp+8]
    m2:
        mov  eax, [ebp-4]
        test eax, eax
        jz   m_out
        mov  dx, [eax+0x10]
        cmp  dx, [esi+0x10]
        jne  m_out
        mov  dl, [eax+0x12]
        cmp  dl, [esi+0x12]
        je   m_out
        mov  dl, [eax+0x14]
        cmp  dl, {CHASM}
        je   m_drain
        cmp  dl, {SKY}
        je   m_drain
        mov  dl, [esi+0x14]
        cmp  dl, {CHASM}
        je   m_drain
        cmp  dl, {SKY}
        jne  m_out
    m_drain:
        mov  edi, 0x7F
    m_out:
        jmp  0x{MV_RESUME:X}
    """
    # ---- cave_warp: Warp Party's level test.  al = caster level, [esp+4] = candidate level ------
    at = a["cave_warp"]
    S["cave_warp"] = f"""
        movsx eax, al
        push ebp
        """ + anchor("ebp", at + len(asm("movsx eax, al\npush ebp", at))) + f"""
        push eax
        xor  edx, edx
        call 0x{a['fly_next']:X}
        cmp  eax, [esp+0xC]
        je   w_yes
        mov  eax, [esp]
        mov  dl, 1
        call 0x{a['fly_next']:X}
        cmp  eax, [esp+0xC]
        je   w_yes
        add  esp, 4
        pop  ebp
        jmp  0x{WARP_NO:X}
    w_yes:
        add  esp, 4
        pop  ebp
        jmp  0x{WARP_YES:X}
    """
    return S


ORDER = ["fly_next", "fly_dir", "gmask", "fly_check", "fly_exec", "fly_popup", "cave_act", "cave_yes", "cave_no",
         "cave_ans", "cave_gct", "cave_vp", "cave_mv", "cave_warp"]


def build():
    """Two passes: sizes with placeholder addresses, then the real layout."""
    code0 = (BASE + len(DATA) + 0xF) & ~0xF
    a = {k: code0 for k in ORDER}
    for _ in range(3):
        va = code0
        new = {}
        src = sources(a)
        for k in ORDER:
            new[k] = va
            va = (va + len(asm(src[k], va)) + 0xF) & ~0xF
        if new == a:
            break
        a = new
    src = sources(a)
    return a, [("data", BASE, DATA)] + [(k, a[k], asm(src[k], a[k])) for k in ORDER]


ADDR, CAVES = build()


def check_anchors():
    """Every anchor's `sub` constant must equal the address its `call $+5` returns to."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for name, va, blob in CAVES[1:]:
        ins = list(md.disasm(blob, va))
        for i, x in enumerate(ins):
            if x.mnemonic == "call" and x.op_str == hex(x.address + 5):
                sub = ins[i + 2]
                if sub.mnemonic != "sub" or int(sub.op_str.split(",")[1], 16) != x.address + 5:
                    sys.exit("ABORT: %s anchor at %08X does not match its sub" % (name, x.address))
            if "ptr [0x55" in x.op_str:
                sys.exit("ABORT: %s has an absolute memory operand at %08X: %s %s"
                         % (name, x.address, x.mnemonic, x.op_str))
    assert CAVES[-1][1] + len(CAVES[-1][2]) <= SLOT[1], "cave outgrew its slot"


check_anchors()


def check_fly_next():
    """EXECUTE the assembled fly_next (build_maplevel4's interpreter) against fly_next()
    for every level -2..7, both directions, every mask over levels 1..5, counts 1..6."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    from build_maplevel4 import _Mini
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    mem, code = {}, {}
    for name, va, blob in CAVES:
        for i, x in enumerate(blob):
            mem[va + i] = x
        if name == "fly_next":
            for ins in md.disasm(blob, va):
                code[ins.address] = ins
    emu = _Mini(code, mem)
    fake_map, fake_cont = 0x10000, 0x20000

    def setw(at, v):
        for i, x in enumerate((v & 0xFFFFFFFF).to_bytes(4, "little")):
            mem[at + i] = x

    runs = 0
    for count in range(1, 7):
        for mask in range(0, 64, 2):
            setw(MAPVAR, fake_map)
            mem[fake_map + MASK_OFF] = mask
            setw(fake_map + 0x10, fake_cont)
            setw(fake_cont + 0x14, count)
            for lv in range(-2, 8):
                for d in (0, 1):
                    got = emu.run(ADDR["fly_next"], {"eax": lv, "edx": d, "ebp": 0})
                    if got != fly_next(lv, d, mask, count):
                        sys.exit("ABORT: fly_next L=%d dir=%d mask=%02X n=%d -> %d"
                                 % (lv, d, mask, count, got))
                    runs += 1
    return runs


FLY_NEXT_RUNS = check_fly_next()

caves = CAVES
hooks = [
    (GCT_SLOT, struct.pack("<I", GCT_ORIG), struct.pack("<I", ADDR["cave_gct"])),
    (ACT_SLOT, struct.pack("<I", ACT_ORIG), struct.pack("<I", ADDR["cave_act"])),
    (VP_HOOK, VP_VAN, jmp_to(VP_HOOK, ADDR["cave_vp"], len(VP_VAN))),
    (MV_HOOK, MV_VAN, jmp_to(MV_HOOK, ADDR["cave_mv"], len(MV_VAN))),
    (WARP_HOOK, WARP_VAN, jmp_to(WARP_HOOK, ADDR["cave_warp"], len(WARP_VAN))),
]
interior = [
    (VP_HOOK, VP_HOOK + len(VP_VAN), 0x557468E8, 0x55746984),
    (MV_HOOK, MV_HOOK + len(MV_VAN), 0x55780328, 0x557803BA),
    (WARP_HOOK, WARP_HOOK + len(WARP_VAN), 0x557EB1DC, 0x557EB454),
]

if __name__ == "__main__":
    run("build_fly_levels", hooks, caves, SLOT, interior, reloc_ok=(GCT_SLOT, ACT_SLOT))
