#!/usr/bin/env python
r"""
build_airwater_ench.py -- the two Air/Water dual unit enchantments, Mistform (spell 88, ability 0x54)
and Static Shield (spell 90, ability 0x55), and Mistform's absorb; and the Life/Air one, Spectral Wings
(spell 96, ability 0x97; owner's design 2026-10-27, 05-spells-added.md "Life/Air: Spectral Wings"),
which shares their TWindWalking plumbing.  AoWEPACK.dpl.  Static Shield's
stun: build_staticshield.py.  Data: build_airwater_pfs.py.  Battle casting:
build_battlecast_unitspells.py + build_spell_unit_target.py.  Owner's design 2026-10-26
(05-spells-added.md, "Air/Water -- agreed design").

THE SPELLS  TWindWalking INSTANCES (a friendly unit enchantment castable on the map and in battle:
  Create sets [+0xC] = 3 and GetCombatInfo byte 7 = 1), built by TWindWalking.Create (classref cell
  0x557E63B4) and registered at 0x557E8DF5 (Healing Water's `call RegisterSpell` in
  RegisterUnitSpells, EBX = the control, replayed first).  Sphere 7 (dual), research 80 / 240 (the
  single tier figures one tier up).  The world-map AI casts Static Shield: its [spell+0x40] is 225
  (Bless's and Dark Gift's), so TUnitSpell.AIRetrieveOptimalTargetUnit gives it to the highest-level
  unit of the caster's army that is no war machine and passes ValidTargetUnit, scored level + 225.
  Mistform keeps Create's -1, which the AI skips.  The battle AI casts no friendly unit spell.
    88 Mistform       12 mana, upkeep 1, tier 1, enchantment level 2
    90 Static Shield  45 mana, upkeep 5, tier 3, enchantment level 4
    96 Spectral Wings 50 mana, upkeep 5, tier 3, enchantment level 4 (Life/Air; the AI never casts it)
  A dual enchantment's level is its equivalent single tier, dual tier + 1 (owner, 2026-10-26; as
  Dwarven Satchels 2 and Enmity of Nine Hells 4); Dispel's chance is strength + 50 - 10 x level.  TWindWalking hard-codes its enchantment 0xA5; the spell id picks:
    X1  0x557E7F59  ExecuteSpell `mov edx,0xa5` (5 B) -> call cave_sel   EBX = the spell
    X2  0x557E7F6C  ExecuteSpell `mov edx,0xa5` (5 B) -> call cave_sel
    V   0x557E7FA8  ValidTargetUnit entry (6 B) -> jmp cave_vtu: for 88 / 90, TUnitSpell.
        ValidTargetUnit, then refuse a unit already holding that enchantment (so Mistform takes a
        Wind Walking unit).  Wind Walking keeps vanilla's tests -- refuse a flyer (0x01), a Wind
        Walker (0xA5) or a floater (0x3B) -- but asks for Floating through cave_raw, which skips Q's
        widening, so a Mistform unit can take Wind Walking (owner, 2026-10-26: it floats on after
        the absorb).  Vanilla's body after 0x557E7FAE is no longer reached.  Spectral Wings: TUnitSpell.
        ValidTargetUnit, then refuse a flyer (0x01, which the widening below answers for 0x97 too, so
        a winged unit is refused) or a Wind Walker (0xA5); a floater (Mistform included) may take it.
THE ENCHANTMENTS  registered at 0x557BCBFA (RegisterPassiveAbilities' last free direct `call
  RegisterAbility`, replayed first).
    0x54 Mistform       a TWindWalkingEnchantment instance: its Remove is the base Remove, then
                        TArmy.ValidateTerrain -- a unit that loses it over water, chasm or sky
                        falls as when Wind Walking is dispelled there.
    0x55 Static Shield  a TUnitEnchantmentAbility instance (Regeneration's recipe).
    0x97 Spectral Wings a TWindWalkingEnchantment instance: losing it over water, chasm or sky falls
                        as Wind Walking does (vanilla Remove).  0x97 was a nil registry slot that no
                        binary uses as a constant (checked 2026-10-27; the launch proves the id).
  Both are unit enchantments: dispellable, counted by Magebane, upkeep through the Magic window.
THE GRANTS
  F   0x5574F7B6  GetAbMoveTypesAll's `call [ecx+0x88]` for Floating 0x3B (6 B; ESI = the owner) ->
      call cave_f + nop: 0x3B, else 0x54.  The unit's move types (Floating = the Flying bit).
  W   0x5574F7A3  GetAbMoveTypesAll's `call [ecx+0x88]` for Wind Walking 0xA5 (6 B; ESI = the owner)
      -> call cave_w + nop: 0xA5, else 0x97 -- Flying's move bit, as Flying and Wind Walking set it.
  L   0x5574FB7B  GetAbImmunityTypesAll's `call [ecx+0x88]` for Lightning Immunity 0x09 (6 B; EBX
      = the owner) -> call cave_l + nop: 0x09, else 0x55.  Both combat systems and map storms.
  Q   0x5577F5E0  TAbstractUnit.GetAbilityEnabled's entry (6 B) -> jmp cave_q + nop: a query for
      0x3B is has(0x3B) or has(0x54); for 0x09, has(0x09) or has(0x55).  It is +0x148 for every unit
      and hero, and TCombatUnit's +0xA8 forwards to it: Wind Walking's / Water Walking's / Liquid
      Form's target tests, Geyser, Winds of Fury, AoWTCPCK's CanMoveOn tests and the lightning stun
      roll (0x55781C65).  For 0x01 (Flying) and 0xB2 (Embrittled), has(id) or has(0x97): a winged unit
      counts as a flyer everywhere (Weight of the World included), and build_embrittle.py's combat
      damage cave gives it the physical x1.5 (refusing Embrittle on it, which would do the same).
  PW  0x55781B1E  TAbstractUnit.ExecuteDamageRole's `not eax / and ax,si` (5 B, after the roll and
      build_weakness.py's T cave, before the protection halve) -> jmp cave_pw: the same x1.5 on the
      world map (storms, Meteor Storm): doubled when the halve fires (exact cancel), else (3d+1)>>1,
      capped at 126.
MISTFORM'S ABSORB  the next damage above 0 that lands ends Mistform instead; a miss or a hit already
  reduced to 0 leaves it.  mist_end = RemoveAbility(0x54) on the unit with DEFER set.
  D   0x55726C7D  TCombatObject.ExecuteDamage's GetHitPoints call (10 B; EBX = the final damage
      after the 0..126 bound, ESI = the object) -> call cave_d + 5 nop: a TCombatUnit whose unit
      holds 0x54 (self-only +0x4C) takes 0 (no hit points, no hit flag, no Lethe wake, Lucky not
      spent) and LAST := the object.  Every call clears LAST first.  One body serves both combat
      systems: melee, retaliation, ranged, breath, spells, ticks, Razor Plate, auto-resolve.
  FX  0x55724C1C  TCombatUnit.ExecuteDamageEffects' entry (7 B) -> jmp cave_fx: the object in LAST
      gets no effects (Poison / Fire / Cold Strike, stuns, panic riders of the absorbed blow) and
      LAST is cleared.  Effects follow their damage call within one CA (TDamageCA, TStrikeCA,
      TSelfDestructCA), so LAST names the blow just absorbed.
  S   0x557689F4  TSelfDestructCA.Execute's GetHitPoints call for the user (10 B; ESI = the user)
      -> call cave_s + 5 nop: the user's Mistform ends first, so it cannot outlive its own blast.
  M   0x55781B37  TAbstractUnit.ExecuteDamageRole's exit (5 B; EDI = the final map damage after
      immunity, roll, protection and weakness; EBX = the unit) -> jmp cave_m: 0x54 ends, EDI := 0.
      Storms, map fire, holy and unholy ground, poison plants, Town Quake, Vortex, Awaken Volcano.
      Storms skip their status effects at 0 damage.  Living Flame's heal never reaches it.
THE FALL (owner 2026-10-26: as on dispel)  ValidateTerrain may kill units, which is unsafe inside
  the damage loops, so a Mistform removal under DEFER queues the unit instead:
  VT  0x557BBBB2  TWindWalkingEnchantment.Remove's `call TArmy.ValidateTerrain` (ESI = the unit) ->
      call cave_vt: not deferred -> ValidateTerrain (Wind Walking, and Mistform's dispel, upkeep and
      caster-death removals, unchanged).  Deferred -> when the unit cannot stand there alone
      (TAbstractUnit.ValidTerrain, with the hex's terrain bytes), its id goes in QUEUE.
  VAL 0x5578CF7C  TArmy.Validate's entry (6 B) -> jmp cave_val: drain the queue first -- for each
      id, FindUnit, then (as Remove does) its army's hex terrain and TArmy.ValidateTerrain, which
      checks the transporter, drowns / burns / crushes what cannot stand there and validates the
      army (re-entering here with the entry already cleared).  Every map damage source validates
      its army after its loop; TArmyHS.MoveTo validates too, so a battle's absorbs are drained by
      the first validation after the battle.
BSS  LAST 0x558FAD24 (4 B), DEFER 0x558FAD28 (1 B), QUEUE 0x558FAD2C..0x558FAD3F (5 unit ids;
  when full the first is overwritten), in the clear gap.

RNG: none (no draw added; every gate is replicated state).
Slot 0x558BE400-0x558BEBFF, exclusive.  PIC.  Surgical --undo.  The registrations run at package
init: proved only by launching the exe.
Couplings: build_panic_cleardamage.py's damage roll (same function's entry) skips a unit holding
0x54, so an absorbed blow gives no recovery roll; build_staticshield.py reads 0x55 through +0xA8.

    python build_scripts/build_airwater_ench.py            dry run + state
    python build_scripts/build_airwater_ench.py --apply
    python build_scripts/build_airwater_ench.py --undo
    python build_scripts/build_airwater_ench.py --dis
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run
from piccave import pic, ansistr

MF_ID, MF, MF_NAME = 88, 0x54, "Mistform"
SS_ID, SS, SS_NAME = 90, 0x55, "Static Shield"
SW_ID, SW, SW_NAME = 96, 0x97, "Spectral Wings"
SPELLS = (   # id, ability, mana, research, upkeep, tier, enchantment level, AI weight (None: never)
    (MF_ID, MF, 12, 80, 1, 1, 2, None),
    (SS_ID, SS, 45, 240, 5, 3, 4, 225),
    (SW_ID, SW, 50, 240, 5, 3, 4, None),
)
EMBRITTLED, PHYS_BIT, DMG_CLAMP = 0xB2, 0x80, 126
SPHERE = 7
FLOATING, LIGHTNING_IMM, WW_ENCH = 0x3B, 0x09, 0xA5
SLOT = (0x558BE400, 0x558BEC00)
BSS_LAST, BSS_DEFER, BSS_QUEUE, QN = 0x558FAD24, 0x558FAD28, 0x558FAD2C, 5
assert BSS_QUEUE + 4 * QN <= 0x558FAD40           # the Mantle of Gloom list starts there

REGISTER_ABIL, REGISTER_SPELL = 0x55750238, 0x55779B40
LSTRASG, ISCLASS = 0x55701150, 0x557010C0
WW_CELL, WW_CREATE = 0x557E63B4, 0x557E7E80
WWE_VMT, WWE_CREATE, WWE_REMOVE = 0x557B8EA0, 0x557BBAB8, 0x557BBB4C
TUEA_VMT, TUEA_CREATE = 0x55722364, 0x55765518
UNITSPELL_VTU = 0x5577ACAC
TCU_CELL = 0x55715A54                       # TCombatUnit VMT - 0x40 (its self pointer)
TARMY_CELL = 0x557130AC
VAR_AOWHSMAP = 0x558FA040
FINDUNIT, GETLOCATION, GETFIELD = 0x5577E948, 0x5577ED94, 0x557020FC
VALIDATE_TERRAIN, VALID_TERRAIN = 0x5578CF70, 0x5577FFFC

R_ABIL, R_SPELL, VT_SITE = 0x557BCBFA, 0x557E8DF5, 0x557BBBB2
SITES = {   # name: (va, vanilla, function lo, hi)
    "sel1": (0x557E7F59, "baa5000000", 0x557E7F38, 0x557E7FA8),
    "sel2": (0x557E7F6C, "baa5000000", 0x557E7F38, 0x557E7FA8),
    "vtu":  (0x557E7FA8, "53568bf18bce", 0x557E7FA8, 0x557E8000),
    "f":    (0x5574F7B6, "ff9188000000", 0x5574F764, 0x5574F920),
    "l":    (0x5574FB7B, "ff9188000000", 0x5574FADC, 0x5574FC14),
    "q":    (0x5577F5E0, "53568bf28bd8", 0x5577F5E0, 0x5577F618),
    "d":    (0x55726C7D, "8bc68b10ff9288000000", 0x55726C58, 0x55726D40),
    "fx":   (0x55724C1C, "53565166891424", 0x55724C1C, 0x55724C3C),
    "s":    (0x557689F4, "8bc68b10ff9288000000", 0x557689A0, 0x55768A14),
    "m":    (0x55781B37, "8bc75f5e5b", 0x55781AC4, 0x55781B48),
    "val":  (0x5578CF7C, "535657558bf8", 0x5578CF7C, 0x5578D034),
    "w":    (0x5574F7A3, "ff9188000000", 0x5574F764, 0x5574F920),
    "pw":   (0x55781B1E, "f7d06623c6", 0x55781AC4, 0x55781B48),
}
CALLS = ("sel1", "sel2", "f", "l", "w", "d", "s")  # call cave (+ nops); the rest jmp
FLYING = 0x01
RESUME = {"vtu": 0x557E7FAE, "q": 0x5577F5E6, "fx": 0x55724C23, "m": 0x55781B3C, "val": 0x5578CF82,
          "pw": 0x55781B23}
TARGET_OF = {"sel1": "sel", "sel2": "sel"}
A = {}


def c_sel(va):
    return asm(f"""
        mov  edx, {WW_ENCH:#x}
        cmp  dword ptr [ebx + 0x10], {MF_ID}
        jne  s_ss
        mov  edx, {MF:#x}
        ret
    s_ss:
        cmp  dword ptr [ebx + 0x10], {SS_ID}
        jne  s_sw
        mov  edx, {SS:#x}
        ret
    s_sw:
        cmp  dword ptr [ebx + 0x10], {SW_ID}
        jne  s_out
        mov  edx, {SW:#x}
    s_out:
        ret
    """, va)


def c_vtu(va):
    """EAX = the spell, EDX passed through, ECX = the unit; AL; plain ret."""
    return asm(f"""
        push ebx
        push esi
        mov  esi, ecx
        mov  ebx, {MF:#x}
        cmp  dword ptr [eax + 0x10], {MF_ID}
        je   v_ours
        mov  ebx, {SS:#x}
        cmp  dword ptr [eax + 0x10], {SS_ID}
        je   v_ours
        cmp  dword ptr [eax + 0x10], {SW_ID}
        je   v_wings
        mov  ecx, esi
        call {UNITSPELL_VTU:#x}
        test al, al
        je   v_no
        mov  eax, esi
        mov  edx, {FLYING:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  v_no
        mov  eax, esi
        mov  edx, {WW_ENCH:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  v_no
        mov  eax, esi
        mov  edx, {FLOATING:#x}
        call {A['raw']:#x}
        test al, al
        jne  v_no
        mov  al, 1
        jmp  v_out
    v_wings:
        mov  ecx, esi
        call {UNITSPELL_VTU:#x}
        test al, al
        je   v_no
        mov  eax, esi
        mov  edx, {FLYING:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  v_no
        mov  eax, esi
        mov  edx, {WW_ENCH:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  v_no
        mov  al, 1
        jmp  v_out
    v_ours:
        mov  ecx, esi
        call {UNITSPELL_VTU:#x}
        test al, al
        je   v_no
        mov  eax, esi
        mov  edx, ebx
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne  v_no
        mov  al, 1
        jmp  v_out
    v_no:
        xor  eax, eax
    v_out:
        pop  esi
        pop  ebx
        ret
    """, va)


def c_or(va, owner, alias):
    """Replaces `call [ecx+0x88]` (EAX = owner, EDX = the vanilla id): that id, else `alias`."""
    return asm(f"""
        call dword ptr [ecx + 0x88]
        test al, al
        jne  o_out
        mov  eax, {owner}
        mov  edx, {alias:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x88]
    o_out:
        ret
    """, va)


def c_q(va):
    """GetAbilityEnabled(EAX unit, EDX id) -> AL, with 0x3B / 0x09 / 0x01 / 0xB2 widened (Spectral
    Wings answers Flying, and Embrittled for build_embrittle.py's physical weakness)."""
    return asm(f"""
        cmp  edx, {FLOATING:#x}
        je   q_mf
        cmp  edx, {LIGHTNING_IMM:#x}
        je   q_ss
        cmp  edx, {FLYING:#x}
        je   q_sw
        cmp  edx, {EMBRITTLED:#x}
        je   q_sw
        jmp  q_orig
    q_mf:
        mov  ecx, {MF:#x}
        jmp  q_alias
    q_sw:
        mov  ecx, {SW:#x}
        jmp  q_alias
    q_ss:
        mov  ecx, {SS:#x}
    q_alias:
        push ecx
        push eax
        call q_orig
        test al, al
        pop  edx
        pop  ecx
        jne  q_yes
        mov  eax, edx
        mov  edx, ecx
        jmp  q_orig
    q_yes:
        ret
    q_orig:
        push ebx
        push esi
        mov  esi, edx
        mov  ebx, eax
        jmp  {RESUME['q']:#x}
    """, va)


def c_raw(va):
    """GetAbilityEnabled without the widening: EAX unit, EDX id -> AL."""
    return asm(f"""
        push ebx
        push esi
        mov  esi, edx
        mov  ebx, eax
        jmp  {RESUME['q']:#x}
    """, va)


def c_owner(va):
    """EAX = a combat object -> EAX = its unit when that unit holds Mistform itself, else 0."""
    src = f"""
        push ebx
        push esi
        mov  esi, eax
        {{ANC}}
        mov  edx, dword ptr [ebx + {{TCU}}]
        call {ISCLASS:#x}
        test al, al
        je   o_no
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xb8]
        test eax, eax
        je   o_no
        mov  esi, eax
        mov  edx, {MF:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        je   o_no
        mov  eax, esi
        jmp  o_out
    o_no:
        xor  eax, eax
    o_out:
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"TCU": TCU_CELL})


def c_end(va):
    """mist_end: EAX = the unit holding Mistform -> RemoveAbility(0x54) with DEFER set."""
    src = f"""
        push ebx
        {{ANC}}
        mov  byte ptr [ebx + {{DEFER}}], 1
        mov  edx, {MF:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x98]
        mov  byte ptr [ebx + {{DEFER}}], 0
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"DEFER": BSS_DEFER})


def c_d(va):
    src = f"""
        push edi
        {{ANC}}
        mov  dword ptr [edi + {{LAST}}], 0
        test ebx, ebx
        jle  d_hp
        mov  eax, esi
        call {A['owner']:#x}
        test eax, eax
        je   d_hp
        call {A['end']:#x}
        xor  ebx, ebx
        mov  dword ptr [edi + {{LAST}}], esi
    d_hp:
        pop  edi
        mov  eax, esi
        mov  edx, dword ptr [eax]
        jmp  dword ptr [edx + 0x88]
    """
    return pic(src, va, "edi", {"LAST": BSS_LAST})


def c_fx(va):
    src = f"""
        push ebx
        {{ANC}}
        cmp  eax, dword ptr [ebx + {{LAST}}]
        jne  x_go
        mov  dword ptr [ebx + {{LAST}}], 0
        pop  ebx
        xor  eax, eax
        ret
    x_go:
        pop  ebx
        push ebx
        push esi
        push ecx
        mov  word ptr [esp], dx
        jmp  {RESUME['fx']:#x}
    """
    return pic(src, va, "ebx", {"LAST": BSS_LAST})


def c_s(va):
    return asm(f"""
        mov  eax, esi
        call {A['owner']:#x}
        test eax, eax
        je   s_hp
        call {A['end']:#x}
    s_hp:
        mov  eax, esi
        mov  edx, dword ptr [eax]
        jmp  dword ptr [edx + 0x88]
    """, va)


def c_m(va):
    return asm(f"""
        test edi, edi
        jle  m_out
        mov  eax, ebx
        mov  edx, {MF:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        je   m_out
        mov  eax, ebx
        call {A['end']:#x}
        xor  edi, edi
    m_out:
        mov  eax, edi
        pop  edi
        pop  esi
        pop  ebx
        jmp  {RESUME['m']:#x}
    """, va)


def c_pw(va):
    """TAbstractUnit.ExecuteDamageRole after the roll and the Weaknesses (EAX = the protection mask,
    SI = the hit's types minus immunities, EDI = the damage, EBX = the unit): Spectral Wings'
    Physical Weakness on the world map.  Doubled when the protection halve will fire (exact
    cancel), else x1.5 rounded up; capped at 126.  Then the displaced `not eax / and ax,si`."""
    return asm(f"""
        test edi, edi
        jle  p_go
        test si, {PHYS_BIT:#x}
        je   p_go
        push eax
        mov  eax, ebx
        mov  edx, {SW:#x}
        call {A['raw']:#x}
        test al, al
        pop  eax
        je   p_go
        push eax
        not  eax
        and  ax, si
        pop  eax
        jne  p_15
        add  edi, edi
        jmp  p_cap
    p_15:
        lea  edi, [edi + edi*2]
        inc  edi
        sar  edi, 1
    p_cap:
        cmp  edi, {DMG_CLAMP}
        jle  p_go
        mov  edi, {DMG_CLAMP}
    p_go:
        not  eax
        and  ax, si
        jmp  {RESUME['pw']:#x}
    """, va)


def c_vt(va):
    """Replaces Remove's `call TArmy.ValidateTerrain` (EAX = the army, DL / CL = the hex's terrain
    bytes, ESI = the unit)."""
    src = f"""
        push ebx
        {{ANC}}
        cmp  byte ptr [ebx + {{DEFER}}], 0
        jne  t_defer
        pop  ebx
        jmp  {VALIDATE_TERRAIN:#x}
    t_defer:
        mov  eax, esi
        call {VALID_TERRAIN:#x}
        test al, al
        jne  t_out
        mov  eax, dword ptr [esi + 0x18]
        lea  edx, [ebx + {{QUEUE}}]
        mov  ecx, {QN}
    t_find:
        cmp  dword ptr [edx], 0
        je   t_put
        cmp  dword ptr [edx], eax
        je   t_out
        add  edx, 4
        dec  ecx
        jne  t_find
        lea  edx, [ebx + {{QUEUE}}]
    t_put:
        mov  dword ptr [edx], eax
    t_out:
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"DEFER": BSS_DEFER, "QUEUE": BSS_QUEUE})


def c_check(va):
    """EAX = a unit -> its army's hex terrain, then TArmy.ValidateTerrain (Remove's own tail)."""
    src = f"""
        push ebx
        push esi
        push ecx
        mov  esi, eax
        {{ANC}}
        mov  eax, dword ptr [esi + 4]
        test eax, eax
        je   c_out
        mov  edx, dword ptr [ebx + {{TARMY}}]
        call {ISCLASS:#x}
        test al, al
        je   c_out
        lea  eax, [esp + 2]
        push eax
        lea  ecx, [esp + 5]
        lea  edx, [esp + 4]
        mov  eax, esi
        call {GETLOCATION:#x}
        cmp  byte ptr [esp], 0xff
        je   c_out
        movsx eax, byte ptr [esp + 2]
        push eax
        movsx ecx, byte ptr [esp + 5]
        movsx edx, byte ptr [esp + 4]
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x10]
        call {GETFIELD:#x}
        mov  cl, byte ptr [eax + 0x15]
        mov  dl, byte ptr [eax + 0x14]
        mov  eax, dword ptr [esi + 4]
        call {VALIDATE_TERRAIN:#x}
    c_out:
        pop  ecx
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"TARMY": TARMY_CELL, "MAP": VAR_AOWHSMAP})


def c_drain(va):
    src = f"""
        push ebx
        push esi
        push edi
        {{ANC}}
        xor  edi, edi
    r_loop:
        mov  edx, dword ptr [ebx + edi*4 + {{QUEUE}}]
        test edx, edx
        je   r_next
        mov  dword ptr [ebx + edi*4 + {{QUEUE}}], 0
        mov  eax, dword ptr [ebx + {{MAP}}]
        test eax, eax
        je   r_next
        mov  eax, dword ptr [eax + 0xfc]
        call {FINDUNIT:#x}
        test eax, eax
        je   r_next
        call {A['check']:#x}
    r_next:
        inc  edi
        cmp  edi, {QN}
        jl   r_loop
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"QUEUE": BSS_QUEUE, "MAP": VAR_AOWHSMAP})


def c_val(va):
    return asm(f"""
        push eax
        call {A['drain']:#x}
        pop  eax
        push ebx
        push esi
        push edi
        push ebp
        mov  edi, eax
        jmp  {RESUME['val']:#x}
    """, va)


def names_tail():
    a = ansistr(MF_NAME)
    a += b"\x90" * (-len(a) % 4)
    b = ansistr(SS_NAME)
    b += b"\x90" * (-len(b) % 4)
    return a + b + ansistr(SW_NAME), 8, len(a) + 8, len(a) + len(b) + 8


def c_reg_ab(va):
    """`call RegisterAbility` replayed (EBX = the control), then 0x54, 0x55 and 0x97."""
    tail, mf_at, ss_at, sw_at = names_tail()
    src = f"""
        call {REGISTER_ABIL:#x}
        push esi
        {{ANC}}
        lea  eax, [esi + {{WWE}}]
        xor  ecx, ecx
        mov  dl, 1
        call {WWE_CREATE:#x}
        push eax
        lea  eax, [eax + 8]
        lea  edx, [esi + {{MFN}}]
        call {LSTRASG:#x}
        pop  eax
        mov  dword ptr [eax + 0xc], {MF:#x}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_ABIL:#x}
        lea  eax, [esi + {{TUEA}}]
        xor  ecx, ecx
        mov  dl, 1
        call {TUEA_CREATE:#x}
        push eax
        lea  eax, [eax + 8]
        lea  edx, [esi + {{SSN}}]
        call {LSTRASG:#x}
        pop  eax
        mov  dword ptr [eax + 0xc], {SS:#x}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_ABIL:#x}
        lea  eax, [esi + {{WWE}}]
        xor  ecx, ecx
        mov  dl, 1
        call {WWE_CREATE:#x}
        push eax
        lea  eax, [eax + 8]
        lea  edx, [esi + {{SWN}}]
        call {LSTRASG:#x}
        pop  eax
        mov  dword ptr [eax + 0xc], {SW:#x}
        mov  edx, eax
        mov  eax, ebx
        call {REGISTER_ABIL:#x}
        pop  esi
        ret
    """
    return pic(src, va, "esi", {"WWE": WWE_VMT, "TUEA": TUEA_VMT, "MFN": ("TAIL", mf_at),
                                "SSN": ("TAIL", ss_at), "SWN": ("TAIL", sw_at)}, tail)


def c_reg_spell(va):
    """`call RegisterSpell` replayed (EBX = the control), then spells 88, 90 and 96."""
    tail, mf_at, ss_at, sw_at = names_tail()
    body = ""
    for (sid, _ab, mana, research, upkeep, tier, level, ai), nm in zip(SPELLS, ("MFN", "SSN", "SWN")):
        body += f"""
        mov  eax, dword ptr [esi + {{{{CELL}}}}]
        xor  ecx, ecx
        mov  dl, 1
        call {WW_CREATE:#x}
        mov  edi, eax
        lea  eax, [edi + 8]
        lea  edx, [esi + {{{{{nm}}}}}]
        call {LSTRASG:#x}
        mov  dword ptr [edi + 0x10], {sid}
        mov  dword ptr [edi + 0x14], {mana}
        mov  dword ptr [edi + 0x18], {research}
        mov  dword ptr [edi + 0x1c], {upkeep}
        mov  byte ptr [edi + 0x20], {SPHERE}
        mov  byte ptr [edi + 0x21], {tier}
        mov  byte ptr [edi + 0x3c], {level}
        {"" if ai is None else "mov  dword ptr [edi + 0x40], %d" % ai}
        mov  edx, edi
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        """
    src = f"""
        call {REGISTER_SPELL:#x}
        push esi
        push edi
        {{ANC}}
        {body.replace("{{", "{").replace("}}", "}")}
        pop  edi
        pop  esi
        ret
    """
    return pic(src, va, "esi", {"CELL": WW_CELL, "MFN": ("TAIL", mf_at), "SSN": ("TAIL", ss_at),
                                "SWN": ("TAIL", sw_at)}, tail)


BUILDERS = [
    ("sel", c_sel), ("vtu", c_vtu),
    ("f", lambda va: c_or(va, "esi", MF)), ("l", lambda va: c_or(va, "ebx", SS)),
    ("w", lambda va: c_or(va, "esi", SW)), ("pw", c_pw),
    ("q", c_q), ("raw", c_raw), ("owner", c_owner), ("end", c_end), ("d", c_d), ("fx", c_fx), ("s", c_s),
    ("m", c_m), ("vt", c_vt), ("check", c_check), ("drain", c_drain), ("val", c_val),
    ("reg_ab", c_reg_ab), ("reg_spell", c_reg_spell),
]


def layout():
    for name, _b in BUILDERS:
        A.setdefault(name, SLOT[0] + 0x700)
    for _ in range(3):
        va, blobs = SLOT[0], []
        for name, b in BUILDERS:
            A[name] = va
            blob = b(va)
            blobs.append(("cave_" + name, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    return blobs


def checks(d):
    rb = lambda va, n: bytes(d[P.va2off(d, va):P.va2off(d, va) + n])
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]

    def cname(vmt):
        p = P.va2off(d, u(vmt - 0x20))
        return d[p + 1:p + 1 + d[p]].decode()
    for vmt, name in ((WWE_VMT, "TWindWalkingEnchantment"), (TUEA_VMT, "TUnitEnchantmentAbility"),
                      (u(WW_CELL), "TWindWalking"), (u(TCU_CELL), "TCombatUnit"), (u(TARMY_CELL), "TArmy")):
        if u(vmt - 0x40) != vmt or cname(vmt) != name:
            sys.exit("ABORT: %s's VMT moved" % name)
    if u(WWE_VMT + 0xD4) != WWE_REMOVE or not WWE_REMOVE < VT_SITE < WWE_REMOVE + 0x74:
        sys.exit("ABORT: TWindWalkingEnchantment.Remove moved")
    for va, want, what in (
            (R_ABIL - 2, "8bc3", "`mov eax,ebx` before the ability registration site"),
            (R_SPELL - 2, "8bc3", "`mov eax,ebx` before the spell registration site"),
            (0x557BBB5E, "8b4604", "Remove's `mov eax,[esi+4]` (ESI = the unit)")):
        if rb(va, len(want) // 2).hex() != want:
            sys.exit("ABORT: %s is not at %08X" % (what, va))
    _e, secs = P.sections(d)
    for vs, sva, rs, ra in secs:            # nobody else creates spell 88 / 90 / 96 or ability 0x54 / 0x55 / 0x97
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i] == 0xC7 and d[i + 1] in range(0x40, 0x48):
                v = struct.unpack_from("<I", d, i + 3)[0]
                if (d[i + 2] == 0x10 and v in (MF_ID, SS_ID, SW_ID)) or (d[i + 2] == 0x0C and v in (MF, SS, SW)):
                    sys.exit("ABORT: %08X also stores %#x at +%#x" % (src, v, d[i + 2]))


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    rel = lambda src, dst, op: bytes([op]) + struct.pack("<i", dst - (src + 5))
    hooks = [(R_ABIL, rel(R_ABIL, REGISTER_ABIL, 0xE8), rel(R_ABIL, A["reg_ab"], 0xE8)),
             (R_SPELL, rel(R_SPELL, REGISTER_SPELL, 0xE8), rel(R_SPELL, A["reg_spell"], 0xE8)),
             (VT_SITE, rel(VT_SITE, VALIDATE_TERRAIN, 0xE8), rel(VT_SITE, A["vt"], 0xE8))]
    interior = []
    for name, (va, van, lo, hi) in SITES.items():
        van = bytes.fromhex(van)
        tgt = A[TARGET_OF.get(name, name)]
        new = (rel(va, tgt, 0xE8) + b"\x90" * (len(van) - 5)) if name in CALLS else jmp_to(va, tgt, len(van))
        hooks.append((va, van, new))
        interior.append((va, va + len(van), lo, hi))
    print("  layout: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_airwater_ench -- Mistform, Static Shield, Spectral Wings (AoWEPACK)", hooks, blobs, SLOT,
        interior)


if __name__ == "__main__":
    main()
