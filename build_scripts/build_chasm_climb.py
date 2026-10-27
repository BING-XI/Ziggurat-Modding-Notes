#!/usr/bin/env python
r"""
build_chasm_climb.py -- Mountaineering parties path between map levels through chasm edges.
AoWEPACK.dpl.  Owner's design 2026-10-25 (05-spells-added.md, "Earth/Fire -- agreed design").

THE RULES
  C = a Chasm hex (terrain 0x0B), C' = the hex beneath it, A = a land hex beside C, X' = a hex
  whose overhead hex X is land beside a chasm.  Links, both ways:
    A -> C' and C' -> A        down into the chasm and up out of it
    X' -> X and X -> X'        up and down the wall beside a chasm
  "Above" and "beneath" follow the level chain Firmament 3 / Surface 0 / Caverns 1 / Depths 2 /
  Abyss 4, skipping levels disabled in the map's mask ([map+0x41C]) as flight does.  The landing
  hex is priced with the party's own movement table (Tunneling for Earth, Swimming for water ...)
  and is never a chasm or the border.  Every moving unit needs Mountaineering (move-type bit 0x20);
  with a transport only the transport does (vanilla's transport rule, TArmy.MoveTypes).  A climb
  needs 4 movement points and uses all that are left; the AI climbs too.

THE PATH SEARCH -- links, as caves, teleporters and one-hex bridges are
  TMoveControl asks a hex for its links at three places, all `test [esi+0x19],0x80 / je / mov
  edx,ebx / mov eax,esi / call TMapField.MoveExclusive` (15 B; ESI = the hex, EBX = the move
  control): ProcessHexagon 0x557458CE (every hex a line reaches), ExecuteExternalMove 0x55745A88
  (a link's landing) and SetupMove 0x55745CA4 (the start hex).  Each becomes `mov edx,ebx / mov
  eax,esi / call cave_links` + 6 nops.  cave_links replays the vanilla link call, then, for a
  mover whose table allows a mountain on grass ([mc+0x41], a one-byte filter) and that stands on
  no chasm, in a search on the world map ([mc+4] = AoWHSMap 0x558FA040), emits the climbs with
  TMoveControl.ExecuteExternalMove(mc, hex, landing, cost) -- the call caves use, so path
  reconstruction (sub-moves), ValidPath's re-run and the AI see them.
  Battles (gate added 2026-10-26): every combat path search runs the same ProcessHexagon on
  TAoWCombatMap's TCombatMoveControl, built with the combat map at 0x41B428.  The combat map is
  not a TAoWHSMap, so TAoWEngine.SetHSMap leaves AoWHSMap on the world map during a battle.
  There [mc+0x134] is the unit's TCUnitHS and [mc+0x138] is 0 (only writer 0x41D8F3), so k_elig
  never let a climb through.  But the cave read the world map at combat coordinates with the
  combat map's neighbour offsets (TMapContainer.GetField has no bounds check).  It did so when a
  combat hex bordered terrain 0x0B (TRndTacHsm.RandomMap 0x4261CD copies each world hex's terrain
  onto its region, Chasm included) and, when the map has Firmament, on every hex any flyer or
  climber searched.  On a world map narrower than 59 or shorter than 53 hexes (the battlefield
  grid) GetField reads past its column or row table and returns a wild pointer.
  The mover is the move control's own [mc+0x134] (TArmyHS) / [mc+0x138] (unit mask), which
  vanilla's TArmyHS.CanMoveOver reads during every search.
  Cost: d = the hex's cost so far, m0 = TArmy.MovePoints, M = TArmy.Moves (both over the mask;
  M < 4 = no climb).  r = what is left of the turn at the hex: m0 - d, or M - ((d - m0) mod M) in
  a later turn.  cost = r when r >= 4, else r + M (wait out the turn, climb the next).  So the
  landing's cost is the end of a turn, and turn markers after a climb are right.

THE EXECUTION
  The army only walks as far as build_patch.py's TrueReachPos (cave 0x5580D75A) allows; its
  per-unit walk unit_walk deducts each step at 0x5580D86D (`test edx,edx / js / cmp edx,edi`,
  EDX = step cost, EDI = that unit's movement left).  That 6-byte check -> cave_walk: a step
  between levels whose source hex has no link object (bit 0x80 of [field+0x19]: no cave or
  teleporter) needs 4 points and costs all of them, so the move stops after a climb.  Flights
  (build_fly_levels.py's two-node paths) meet the same rule, which matches theirs.
  TMoveArmyTE.ExecuteMove 0x55748262 (7 B after the step's MoveTo) -> cave_drain: the same test
  on the step just taken sets every unit of the moving army to 0 movement (TAbstractUnit
  SetMovePoints, VMT +0xDC; passengers too, as flight's ruling).  Warp Party moves armies
  through TArmyHS.MoveTo directly, not this transaction, so it is untouched.

COUPLINGS
  0x5580D86D is inside build_patch.py's live cave (that script cannot be re-applied and its dry
  run already reports a mismatch).  This script's --undo restores the 6 bytes.

RNG: none.  PIC: one call/pop anchor per cave, rel32 calls.  Slot 0x558B9000-0x558B97FF,
exclusive.  Surgical --undo.

Unproven: what the player's view does when a pathed climb moves the selected army to another
level; the cost of the extra checks in AI searches for climbing armies.

    python build_scripts/build_chasm_climb.py            dry run + state
    python build_scripts/build_chasm_climb.py --apply
    python build_scripts/build_chasm_climb.py --undo
    python build_scripts/build_chasm_climb.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
from aowepack_patch import asm, jmp_to, run
from piccave import pic

SLOT = (0x558B9000, 0x558B9800)

AOWHSMAP = 0x558FA040            # global holding the TAoWHSMap
MOVEXCL = 0x5570206C             # HSEngine.TMapField.MoveExclusive(eax=field, edx=mc)
EXTMOVE = 0x55745928             # TMoveControl.ExecuteExternalMove(eax=mc, edx=src, ecx=dst, [cost]) ret 4
GETFIELD = 0x557020FC            # TMapContainer.GetField(eax=cont, edx=x, ecx=y, [level]) ret 4
GETMP = 0x557452E4               # TMoveControlSettings.GetMovePoints(eax=set, edx=x, ecx=y, [level]) ret 4
TRANSPORTER = 0x5578E00C         # TArmy.Transporter(eax=army, dl=mask) -> unit | nil
ARMY_MP = 0x5578D8D0             # TArmy.MovePoints(eax=army, dl=mask) -> al
ARMY_MOVES = 0x5578D95C          # TArmy.Moves(eax=army, dl=mask) -> al
XYL_GET = 0x55701CF4             # TXYLList.Get(eax=list, edx=index) -> x | y<<8 | L<<16 | cost<<24
CHASM, BORDER = 0x0B, 0x0F
MOUNTAIN_ON_GRASS = 0x31 + 1 * 16 + 0     # [mc + this] = the mover's grass x mountain cost
MT_MOUNTAINEER = 0x20
MIN_MP = 4
MASK_OFF = 0x41C
NO = 0xFF
UP_T = bytes([3, 0, 1, NO, 2])
DN_T = bytes([1, 2, 4, 0, NO])

LINK_SITES = {"hexagon": (0x557458CE, 0x557456F8, 0x557458E6),
              "external": (0x55745A88, 0x55745928, 0x55745AE8),
              "setup": (0x55745CA4, 0x55745AE8, 0x55745D64)}
WALK_HOOK, WALK_VAN = 0x5580D86D, bytes.fromhex("85d278093bd7")
W_SUB, W_DONE = 0x5580D875, 0x5580D87A
DRAIN_HOOK, DRAIN_VAN, DRAIN_RESUME = 0x55748262, bytes.fromhex("8b53288bc68b08"), 0x55748269


def link_vanilla(va):
    """`test [esi+0x19],0x80 / je +9 / mov edx,ebx / mov eax,esi / call MoveExclusive`."""
    return (bytes.fromhex("f6461980" "7409" "8bd3" "8bc6") + b"\xE8"
            + struct.pack("<i", MOVEXCL - (va + 15)))


def link_new(va, cave):
    return bytes.fromhex("8bd3" "8bc6") + b"\xE8" + struct.pack("<i", cave - (va + 9)) + b"\x90" * 6


def build_links(va):
    """eax = hex, edx = move control.  Preserves ebx, esi, edi, ebp.
    Frame: [esp] level, +4 down, +8 up, +0xC elig (-1 unknown), +0x10 cost (-2 unknown, -1 none),
    +0x14 direction, +0x18 the hex above, +0x1C 'borders a chasm'."""
    nb = lambda reg: f"""
        movzx edx, byte ptr [{reg}+0x10]
        and  edx, 1
        shl  edx, 5
        add  edx, ebx
        add  {reg}, dword ptr [edx+ecx*4+0x148]"""
    getf = """
        push edx
        mov  edx, eax
        mov  eax, dword ptr [edi+{MAP}]
        mov  eax, dword ptr [eax+0x10]
        call %#x""" % GETFIELD
    src = f"""
        push ebp
        push ebx
        push esi
        push edi
        sub  esp, 0x20
        mov  esi, eax
        mov  ebx, edx
        test byte ptr [esi+0x19], 0x80
        je   k_climb
        mov  edx, ebx
        mov  eax, esi
        call {MOVEXCL:#x}
    k_climb:
        cmp  byte ptr [ebx+{MOUNTAIN_ON_GRASS:#x}], 0
        jl   k_early
        cmp  byte ptr [esi+0x14], {CHASM:#x}
        je   k_early
        cmp  dword ptr [ebx+0x134], 0
        je   k_early
        {{ANC}}
        mov  eax, dword ptr [edi+{{MAP}}]
        cmp  eax, dword ptr [ebx+4]
        je   k_world
    k_early:
        jmp  k_out
    k_world:
        movsx eax, byte ptr [esi+0x12]
        mov  dword ptr [esp], eax
        mov  dword ptr [esp+0xc], -1
        mov  dword ptr [esp+0x10], -2
        mov  dword ptr [esp+0x1c], 0
        mov  dl, 1
        call k_next
        mov  dword ptr [esp+4], eax
        mov  eax, dword ptr [esp]
        xor  edx, edx
        call k_next
        mov  dword ptr [esp+8], eax
        mov  dword ptr [esp+0x14], 1
    k_dl:
        mov  ecx, dword ptr [esp+0x14]
        mov  eax, esi
        {nb("eax")}
        cmp  byte ptr [eax+0x14], {CHASM:#x}
        jne  k_dn
        mov  dword ptr [esp+0x1c], 1
        mov  edx, dword ptr [esp+4]
        test edx, edx
        js   k_dn
        movsx ecx, byte ptr [eax+0x11]
        movsx eax, byte ptr [eax+0x10]
        {getf}
        call k_link
    k_dn:
        inc  dword ptr [esp+0x14]
        cmp  dword ptr [esp+0x14], 6
        jle  k_dl
        cmp  dword ptr [esp+0x1c], 0
        je   k_up
        mov  edx, dword ptr [esp+4]
        test edx, edx
        js   k_up
        movsx ecx, byte ptr [esi+0x11]
        movsx eax, byte ptr [esi+0x10]
        {getf}
        call k_link
    k_up:
        mov  edx, dword ptr [esp+8]
        test edx, edx
        js   k_out
        movsx ecx, byte ptr [esi+0x11]
        movsx eax, byte ptr [esi+0x10]
        {getf}
        test eax, eax
        je   k_out
        mov  dword ptr [esp+0x18], eax
        cmp  byte ptr [eax+0x14], {CHASM:#x}
        jne  k_wall
        mov  dword ptr [esp+0x14], 1
    k_ul:
        mov  ecx, dword ptr [esp+0x14]
        mov  eax, dword ptr [esp+0x18]
        {nb("eax")}
        call k_link
        inc  dword ptr [esp+0x14]
        cmp  dword ptr [esp+0x14], 6
        jle  k_ul
        jmp  k_out
    k_wall:
        mov  dword ptr [esp+0x14], 1
    k_wl:
        mov  ecx, dword ptr [esp+0x14]
        mov  eax, dword ptr [esp+0x18]
        {nb("eax")}
        cmp  byte ptr [eax+0x14], {CHASM:#x}
        je   k_wlink
        inc  dword ptr [esp+0x14]
        cmp  dword ptr [esp+0x14], 6
        jle  k_wl
        jmp  k_out
    k_wlink:
        mov  eax, dword ptr [esp+0x18]
        call k_link
    k_out:
        add  esp, 0x20
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret

    k_link:
        test eax, eax
        je   kl_ret
        mov  cl, byte ptr [eax+0x14]
        cmp  cl, {CHASM:#x}
        je   kl_ret
        cmp  cl, {BORDER:#x}
        je   kl_ret
        push eax
        mov  ecx, dword ptr [esp+0x14]
        test ecx, ecx
        jns  kl_e
        call k_elig
        mov  dword ptr [esp+0x14], eax
        mov  ecx, eax
    kl_e:
        test ecx, ecx
        je   kl_pop
        mov  ecx, dword ptr [esp+0x18]
        cmp  ecx, -2
        jne  kl_c
        call k_cost
        mov  dword ptr [esp+0x18], eax
        mov  ecx, eax
    kl_c:
        test ecx, ecx
        js   kl_pop
        push ecx
        mov  ecx, dword ptr [esp+4]
        mov  edx, esi
        mov  eax, ebx
        call {EXTMOVE:#x}
    kl_pop:
        pop  eax
    kl_ret:
        ret

    k_elig:
        push esi
        push edi
        xor  eax, eax
        mov  edx, dword ptr [ebx+0x134]
        mov  edi, dword ptr [edx+0x1c]
        test edi, edi
        je   ke_ret
        movzx esi, byte ptr [ebx+0x138]
        test esi, esi
        je   ke_ret
        mov  edx, esi
        mov  eax, edi
        call {TRANSPORTER:#x}
        test eax, eax
        je   ke_units
        mov  edx, dword ptr [eax]
        call dword ptr [edx+0xe8]
        test al, {MT_MOUNTAINEER:#x}
        setne al
        movzx eax, al
        jmp  ke_ret
    ke_units:
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx+0x54]
        mov  ecx, eax
        mov  edx, 1
        shl  edx, cl
        dec  edx
        test edx, esi
        je   ke_none
        push eax
        push 0
    ke_loop:
        mov  ecx, dword ptr [esp]
        cmp  ecx, dword ptr [esp+4]
        jge  ke_all
        bt   esi, ecx
        jae  ke_next
        mov  eax, dword ptr [edi+8]
        mov  eax, dword ptr [eax+4]
        mov  eax, dword ptr [eax+ecx*4]
        mov  edx, dword ptr [eax]
        call dword ptr [edx+0xe8]
        test al, {MT_MOUNTAINEER:#x}
        je   ke_fail
    ke_next:
        inc  dword ptr [esp]
        jmp  ke_loop
    ke_all:
        add  esp, 8
        mov  eax, 1
        jmp  ke_ret
    ke_fail:
        add  esp, 8
    ke_none:
        xor  eax, eax
    ke_ret:
        pop  edi
        pop  esi
        ret

    k_cost:
        push esi
        push edi
        mov  eax, dword ptr [ebx+0x134]
        mov  eax, dword ptr [eax+0x1c]
        movzx edx, byte ptr [ebx+0x138]
        call {ARMY_MOVES:#x}
        movsx edi, al
        cmp  edi, {MIN_MP}
        jl   kc_no
        mov  eax, dword ptr [ebx+0x134]
        mov  eax, dword ptr [eax+0x1c]
        movzx edx, byte ptr [ebx+0x138]
        call {ARMY_MP:#x}
        movsx eax, al
        push eax
        movsx eax, byte ptr [esi+0x12]
        push eax
        movsx ecx, byte ptr [esi+0x11]
        movsx edx, byte ptr [esi+0x10]
        mov  eax, dword ptr [ebx+0x1dc]
        call {GETMP:#x}
        pop  ecx
        cmp  eax, ecx
        jg   kc_later
        sub  ecx, eax
        mov  eax, ecx
        jmp  kc_r
    kc_later:
        sub  eax, ecx
        cdq
        idiv edi
        mov  eax, edi
        sub  eax, edx
    kc_r:
        cmp  eax, {MIN_MP}
        jge  kc_ret
        add  eax, edi
        jmp  kc_ret
    kc_no:
        or   eax, -1
    kc_ret:
        pop  edi
        pop  esi
        ret

    k_next:
        push ecx
        push esi
        mov  ecx, dword ptr [edi+{{MAP}}]
    kn_loop:
        cmp  eax, 4
        ja   kn_no
        test dl, dl
        jne  kn_dn
        movzx eax, byte ptr [edi+eax+{{UPT}}]
        jmp  kn_t
    kn_dn:
        movzx eax, byte ptr [edi+eax+{{DNT}}]
    kn_t:
        cmp  eax, {NO:#x}
        je   kn_no
        mov  esi, dword ptr [ecx+0x10]
        cmp  eax, dword ptr [esi+0x14]
        jge  kn_no
        movzx esi, byte ptr [ecx+{MASK_OFF:#x}]
        bt   esi, eax
        jb   kn_loop
        jmp  kn_ret
    kn_no:
        or   eax, -1
    kn_ret:
        pop  esi
        pop  ecx
        ret
    """
    return pic(src, va, "edi", {"MAP": AOWHSMAP, "UPT": ("TAIL", 0), "DNT": ("TAIL", 8)},
               UP_T + b"\0" * 3 + DN_T + b"\0" * 3)


def build_walk(va):
    """unit_walk's step check: EDX = step cost, EDI = movement left, ESI = path index, [ebp-4] path."""
    src = f"""
        push edx
        push ebx
        mov  eax, dword ptr [ebp-4]
        mov  eax, dword ptr [eax+4]
        mov  ecx, dword ptr [eax+esi*4]
        mov  edx, dword ptr [eax+esi*4-4]
        shr  ecx, 16
        shr  edx, 16
        cmp  cl, dl
        je   w_plain
        mov  eax, dword ptr [eax+esi*4]
        mov  ecx, eax
        shr  ecx, 16
        and  ecx, 0xff
        push ecx
        movzx ecx, ah
        movzx edx, al
        {{ANC}}
        mov  eax, dword ptr [ebx+{{MAP}}]
        mov  eax, dword ptr [eax+0x10]
        call {GETFIELD:#x}
        test eax, eax
        je   w_plain
        test byte ptr [eax+0x19], 0x80
        jne  w_plain
        pop  ebx
        pop  edx
        cmp  edi, {MIN_MP}
        jl   {W_DONE:#x}
        mov  edx, edi
        jmp  {W_SUB:#x}
    w_plain:
        pop  ebx
        pop  edx
        test edx, edx
        js   {W_DONE:#x}
        cmp  edx, edi
        jg   {W_DONE:#x}
        jmp  {W_SUB:#x}
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP})


def build_drain(va):
    """After a step's MoveTo: EBX = the TMoveArmyTE, ESI = the hex just entered."""
    src = f"""
        push edi
        mov  edx, dword ptr [ebx+0x18]
        inc  edx
        mov  eax, dword ptr [ebx+0x14]
        cmp  edx, dword ptr [eax+8]
        jge  d_out
        call {XYL_GET:#x}
        mov  ecx, eax
        shr  ecx, 16
        cmp  cl, byte ptr [esi+0x12]
        je   d_out
        and  ecx, 0xff
        push ecx
        movzx ecx, ah
        movzx edx, al
        {{ANC}}
        mov  eax, dword ptr [edi+{{MAP}}]
        mov  eax, dword ptr [eax+0x10]
        call {GETFIELD:#x}
        test eax, eax
        je   d_out
        test byte ptr [eax+0x19], 0x80
        jne  d_out
        mov  eax, dword ptr [ebx+0x28]
        mov  edi, dword ptr [eax+0x1c]
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx+0x54]
        push eax
        push 0
    d_loop:
        mov  ecx, dword ptr [esp]
        cmp  ecx, dword ptr [esp+4]
        jge  d_done
        mov  eax, dword ptr [edi+8]
        mov  eax, dword ptr [eax+4]
        mov  eax, dword ptr [eax+ecx*4]
        xor  edx, edx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx+0xdc]
        inc  dword ptr [esp]
        jmp  d_loop
    d_done:
        add  esp, 8
    d_out:
        pop  edi
        mov  edx, dword ptr [ebx+0x28]
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        jmp  {DRAIN_RESUME:#x}
    """
    return pic(src, va, "edi", {"MAP": AOWHSMAP})


def layout():
    caves, at, va = [], {}, SLOT[0]
    for name, fn in (("links", build_links), ("walk", build_walk), ("drain", build_drain)):
        b = fn(va)
        caves.append(("cave_" + name, va, b))
        at[name] = va
        va = (va + len(b) + 0xF) & ~0xF
    return at, caves


AT, CAVES = layout()
HOOKS = [(va, link_vanilla(va), link_new(va, AT["links"])) for va, _lo, _hi in LINK_SITES.values()]
HOOKS += [(WALK_HOOK, WALK_VAN, jmp_to(WALK_HOOK, AT["walk"], len(WALK_VAN))),
          (DRAIN_HOOK, DRAIN_VAN, jmp_to(DRAIN_HOOK, AT["drain"], len(DRAIN_VAN)))]
INTERIOR = [(va, va + 15, lo, hi) for va, lo, hi in LINK_SITES.values()]
INTERIOR += [(WALK_HOOK, WALK_HOOK + 6, 0x5580D7DB, 0x5580D87F),
             (DRAIN_HOOK, DRAIN_HOOK + 7, 0x557481FC, 0x557482D8)]
assert max(va + len(b) for _n, va, b in CAVES) <= SLOT[1]

if __name__ == "__main__":
    print("  layout:", ", ".join("%s %08X" % (n, v) for n, v in AT.items()))
    print("  slot used: %d of %d B" % (max(va + len(b) for _n, va, b in CAVES) - SLOT[0], SLOT[1] - SLOT[0]))
    run("build_chasm_climb", HOOKS, CAVES, SLOT, INTERIOR)
