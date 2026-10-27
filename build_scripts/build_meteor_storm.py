#!/usr/bin/env python
r"""
build_meteor_storm.py -- Meteor Storm (spell 92), the Earth/Air dual tier-2 world-map storm.  AoWEPACK.dpl.
Data: build_meteor_storm_pfs.py (Spells.pfs record 102).  Art: build_meteor_fx.py (METEOR.ILB).
Owner's design 2026-10-26 (05-spells-added.md, "Meteor Storm -- agreed design"): cast like the storms,
lands at the start of the caster's second turn after casting, one Physical strike of 16 ATK / 20 DMG on
every unit within 4 hexes, no warning on the map, only the caster's defeat stops it, mana 60; every
player's event log reads "A Meteor Storm has been summoned!" when it is cast.

THE SPELL  a TFireStormSpell INSTANCE (classref 0x557CC060, Create 0x557CE198), registered after
  Pestilence in RegisterStorms (H_REG, the last `call RegisterSpell`, replayed first).  Mana 60,
  research 160 (the single tier-3 figure; it only prices Wizard's Tower offers), sphere 7 (dual), tier 2.
  Targeting, the radius-4 pulse, the underground rule (build_maplevel4.py's Firmament ruling) and the AI
  are TStormSpell's own.
STORM TYPE 0  vanilla's "Blast Storm" slot: no spell or altar creates a bare TBlastStorm, and its
  StormType returns 0.  Meteor Storm takes it:
  - StormDamageType[0] 0x558E8330: dtNone (9) -> dtPhysical (7).
  - ExecuteStormDamage's jump table entry 0 (0x5578072E, was the 0/0 default) -> E_STR: ATK 16, DMG 20.
    The vanilla tail is unchanged: the x4 flyer rule, immunity/protection, no status effect (only types
    2, 3 and 6 carry one).
  - TArmy.RetrieveStormDamageInfo's entry 0 (0x55790379) -> E_AI: 8 / 10, half the strike, as every
    other entry there still holds vanilla's undoubled estimate (Fire 7/5, Lightning 8/7).
  - TArmy.IncommingStorm names the storm in the army event log from TStormTypeRStr[type]; entry 0 is the
    shared "None", so both TranslateRStr calls (0x5579050D, 0x5579052D) go through E_NAME, which hands
    "Meteor Storm" over for type 0.
  The storm message 0x1150 reaches only TArmyHS (IncommingStorm; skipped under a magic shield, as for
  every storm) and TPoisonCloud (type 1 only).
THE CAST  TFireStormSpell VMT +0x9C CreateStorm (0x557CC0FC) -> E_CS: spell 92 gets a bare TBlastStorm,
  every other id Fire Storm's TFireStorm.  TBlastStorm's own VMT (only bare instances use it):
  +0x12C InitializeStorm -> E_INIT, +0x130 -> TStorm.UpdateStorm (returns 0), +0x134 ->
  TStorm.FinalizeStorm (unlocks the event log TStorm.InitializeStorm locked).  So TStormSpellTE.Process
  (a token event: every peer runs it) creates the storm, calls E_INIT, books the cast (CastingDone) and
  frees the storm in the same step.  E_INIT (eax storm, dl player, cl x, [esp+8] y, [esp+4] level):
  - TStorm.InitializeStorm;
  - a MARKER (below) on the target hex: countdown 2, owner = the caster;
  - a TTextEventLog "A Meteor Storm has been summoned!" through DistributeEventLog (every active
    player's logbook, no popup), as TGlobalEnchantment.Cast announces a global spell;
  - the record's sound cue 0, for the caster's seat only.
THE MARKER  a private class: at RegisterStorms (H_CLS, its `call RegisterEClasses`, replayed first)
  E_CLS copies TFrozenWaterHS's VMT (-0x40..+0x110) into System.@GetMem memory once, kept in BSS
  0x558FAED4, and registers it under ClassID 0x2E001 (found in no package, exe or dll).  The copy keeps
  TFrozenWaterHS's parent (THexagonSprite), so nothing that looks for frozen-water markers by class
  (Grip of Winter, Awaken Volcano, Ice Storm) ever finds it; instance size 0x18; slots: +0x24 ClassID
  -> E_CID, +0x44 MsgProc -> E_MSG, +0xA0 TerrainChanged -> the parent's (it survives any terrain
  change), +0xA8 Show -> E_SHOW.  ReadWrite stays TFrozenWaterHS's: +0x0C countdown and +0x0D owner are
  saved (build_gripofwinter.py's inline hook also streams +0x0E/+0x0F, both 0 here).  +0x10 (impact
  frame) and +0x14 (drawing) are display state and are not saved.
EACH TURN  E_MSG: TEObject.MsgProc, then on 0x20020002 (TPlayerControl.NewTurn's turn start) for the
  owner only: countdown - 1.  At 0 the meteors land: TriggerStormDamage(type 0, x, y, level, 0, 4,
  owner) -- the storm message on every hex within 4, as Pestilence's cloud deals its damage from the
  same broadcast -- then the impact animation starts and the record's sound cue 1 plays where the
  storms play theirs (always for the turn's player, else when TerrainVisible).  Below 0 (the owner's
  next turn) the marker frees itself, as MeltIce does.  A defeated caster has no turn: the marker stays,
  unseen and inert.
THE ANIMATION  E_SHOW draws nothing until the impact; then ImageLib's TImageSequenceList.Show draws the
  record's image sequence 0 (the meteor chain, build_meteor_storm_pfs.py) at the hex's pixel position +
  16 -- TImageSequenceAnimation.Show's anchor -- at frame [map+0x40] - impact frame, until it reports
  every sequence finished.  [map+0x40] steps once per map frame (THSMap.NewFrame), the tick the storm
  animations run on.

RNG: P1 SYNCED, vanilla's own -- TArmy.IncommingStorm reseeds System.RandSeed from TAoWHSMap.Random for
the storm's rolls; these caves draw nothing.  Every peer runs the cast (a token event) and the turn
broadcast, so the marker, its countdown and the strike are replicated state.
Slot 0x558C2000-0x558C2FFF, exclusive; BSS 0x558FAED4.  PIC (call/pop anchors).  Pinned entries.
Surgical --undo.  ⚠ A save holding a marker (cast, not yet landed) does not load without this script
(ClassID 0x2E001 unknown).  The two registrations run at package init: proved only by launching the exe.

Couplings
  * build_maplevel4.py patches TStormSpell.CanActivate / AICastSpellPriority (Firmament): inherited.
  * build_gripofwinter.py's ReadWrite hook runs for the marker too (harmless: +0x0E/+0x0F are 0).
  * build_stormeffectroll.py / build_relocfix.py own ExecuteStormDamage's effect tail; untouched here.

    python build_scripts/build_meteor_storm.py            dry run + state
    python build_scripts/build_meteor_storm.py --apply
    python build_scripts/build_meteor_storm.py --undo
    python build_scripts/build_meteor_storm.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, run
from piccave import pic, ansistr

SPELL_ID, NAME = 92, "Meteor Storm"
MESSAGE = "A Meteor Storm has been summoned!"
MANA, RESEARCH, SPHERE, TIER = 60, 160, 7, 2
ATK, DMG, AI_ATK, AI_DMG = 16, 20, 8, 10
DELAY, RADIUS = 2, 4
CLASS_ID, MARKER_SIZE = 0x2E001, 0x18
SLOT = (0x558C2000, 0x558C3000)
BSS_CLASS = 0x558FAED4

AOWHSMAP, AOWHSSET = 0x558FA040, 0x558FA044
REGISTER_SPELL, LSTRASG, GETMEM, REG_ECLASSES = 0x55779B40, 0x55701150, 0x55701008, 0x557033FC
FS_CELL, FS_VMT, FS_CREATE, FS_CREATESTORM = 0x557CC020, 0x557CC060, 0x557CE198, 0x557CE23C
BLAST_CELL, BLAST_VMT = 0x557CB220, 0x557CB260
FW_CELL, FW_VMT = 0x55714774, 0x557147B4
TEXTLOG_CELL, TEXTLOG_VMT = 0x557FC524, 0x557FC564
ANIM_CREATE, STORM_INIT, STORM_UPD, STORM_FIN = 0x557FB4A8, 0x557CC710, 0x557CC72C, 0x557CC730
BLAST_INIT, BLAST_UPD, BLAST_FIN = 0x557CC910, 0x557CCAC0, 0x557CCC60
TEOBJ_CREATE, PLACEHX, MSGPROC = 0x55703064, 0x557025F4, 0x557030F4
TRIGGER, GETSPELL, SFX_PLAY, TERRVIS, SEQ_SHOW = 0x5575B4C8, 0x55779AC8, 0x55702CF4, 0x5577595C, 0x55702904
LOG_CREATE, DISTRIBUTE, TRANSLATE = 0x557FD398, 0x557FE4B0, 0x557249FC
STR_JOIN, AI_JOIN = 0x55780796, 0x557903FF
VMT_NEG, VMT_LEN = 0x40, 0x110          # header, then the slots up to the class-name string

# hook sites
H_CLS, H_REG = 0x557CE61D, 0x557CE6B0
H_NAMES = (0x5579050D, 0x5579052D)
S_CS = FS_VMT + 0x9C
S_INIT, S_UPD, S_FIN = BLAST_VMT + 0x12C, BLAST_VMT + 0x130, BLAST_VMT + 0x134
T_STR, T_STR_OLD = 0x5578072E, 0x55780792
T_AI, T_AI_OLD = 0x55790379, 0x557903F5
B_TYPE = 0x558E8330
ENTRIES = ("str", "ai", "cid", "name", "cs", "cls", "reg", "init", "msg", "show")
ENTRY = {n: SLOT[0] + 5 * i for i, n in enumerate(ENTRIES)}
A = {}


def r_str(va):
    return asm(f"""
        mov  ebp, {ATK}
        mov  esi, {DMG}
        jmp  {STR_JOIN:#x}
    """, va)


def r_ai(va):
    return asm(f"""
        mov  dword ptr [ebp - 0xc], {AI_ATK}
        mov  dword ptr [ebp - 0x10], {AI_DMG}
        jmp  {AI_JOIN:#x}
    """, va)


def r_cid(va):
    return asm(f"""
        mov  eax, {CLASS_ID:#x}
        ret
    """, va)


def r_name(va):
    """At IncommingStorm's two TranslateRStr calls (eax = TStormTypeRStr[edi], edx = dest)."""
    src = f"""
        test edi, edi
        jne  n_go
        {{ANC}}
        lea  eax, [ecx + {{NAME}}]
    n_go:
        jmp  {TRANSLATE:#x}
    """
    return pic(src, va, "ecx", {"NAME": ("TAIL", 8)}, ansistr(NAME))


def r_cs(va):
    """TFireStormSpell VMT +0x9C (eax = the spell): spell 92 gets a bare TBlastStorm."""
    src = f"""
        cmp  dword ptr [eax + 0x10], {SPELL_ID}
        jne  c_fire
        {{ANC}}
        mov  eax, dword ptr [edx + {{BLAST}}]
        xor  ecx, ecx
        mov  dl, 1
        jmp  {ANIM_CREATE:#x}
    c_fire:
        jmp  {FS_CREATESTORM:#x}
    """
    return pic(src, va, "edx", {"BLAST": BLAST_CELL})


def r_cls(va):
    """RegisterStorms' `call RegisterEClasses` (eax engine, edx array, ecx high): the replayed call, then
    the marker class (built once) registered in this engine."""
    src = f"""
        push ebx
        push esi
        push edi
        mov  ebx, eax
        call {REG_ECLASSES:#x}
        {{ANC}}
        mov  eax, dword ptr [esi + {{BSS}}]
        test eax, eax
        jne  k_reg
        mov  eax, {VMT_NEG + VMT_LEN:#x}
        call {GETMEM:#x}
        mov  edi, eax
        push esi
        push edi
        mov  esi, dword ptr [esi + {{FW}}]
        sub  esi, {VMT_NEG:#x}
        mov  ecx, {(VMT_NEG + VMT_LEN) // 4:#x}
        cld
        rep movsd dword ptr es:[edi], dword ptr [esi]
        pop  edi
        pop  esi
        lea  edx, [edi + {VMT_NEG:#x}]
        mov  dword ptr [edx - {VMT_NEG:#x}], edx
        mov  dword ptr [edx - 0x1c], {MARKER_SIZE:#x}
        lea  eax, [esi + {{CID}}]
        mov  dword ptr [edx + 0x24], eax
        lea  eax, [esi + {{MSG}}]
        mov  dword ptr [edx + 0x44], eax
        lea  eax, [esi + {{SHOW}}]
        mov  dword ptr [edx + 0xa8], eax
        mov  eax, dword ptr [edx - 0x18]
        mov  eax, dword ptr [eax]
        mov  eax, dword ptr [eax + 0xa0]
        mov  dword ptr [edx + 0xa0], eax
        mov  dword ptr [esi + {{BSS}}], edx
        mov  eax, edx
    k_reg:
        push eax
        mov  edx, esp
        xor  ecx, ecx
        mov  eax, ebx
        call {REG_ECLASSES:#x}
        pop  eax
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "esi", {"BSS": BSS_CLASS, "FW": FW_CELL, "CID": ENTRY["cid"],
                                "MSG": ENTRY["msg"], "SHOW": ENTRY["show"]})


def r_reg(va):
    """RegisterStorms' last `call RegisterSpell` (ebx = the spell control): replayed, then spell 92."""
    src = f"""
        call {REGISTER_SPELL:#x}
        push esi
        push edi
        {{ANC}}
        mov  eax, dword ptr [esi + {{FS}}]
        xor  ecx, ecx
        mov  dl, 1
        call {FS_CREATE:#x}
        mov  edi, eax
        lea  eax, [edi + 8]
        lea  edx, [esi + {{NAME}}]
        call {LSTRASG:#x}
        mov  dword ptr [edi + 0x10], {SPELL_ID}
        mov  dword ptr [edi + 0x14], {MANA}
        mov  dword ptr [edi + 0x18], {RESEARCH}
        mov  dword ptr [edi + 0x1c], 0
        mov  byte ptr [edi + 0x20], {SPHERE}
        mov  byte ptr [edi + 0x21], {TIER}
        mov  edx, edi
        mov  eax, ebx
        call {REGISTER_SPELL:#x}
        pop  edi
        pop  esi
        ret
    """
    return pic(src, va, "esi", {"FS": FS_CELL, "NAME": ("TAIL", 8)}, ansistr(NAME))


def r_init(va):
    """TBlastStorm VMT +0x12C for spell 92's storm: eax storm, dl player, cl x, [esp+8] y, [esp+4]
    level; ret 8.  Frame: [ebp+8] level, [ebp+0xC] y; esi player, edi x."""
    src = f"""
        push ebp
        mov  ebp, esp
        push ebx
        push esi
        push edi
        movzx esi, dl
        movzx edi, cl
        push dword ptr [ebp + 0xc]
        push dword ptr [ebp + 8]
        mov  ecx, edi
        mov  edx, esi
        call {STORM_INIT:#x}
        {{ANC}}
        mov  eax, dword ptr [ebx + {{BSS}}]
        test eax, eax
        je   i_log
        xor  ecx, ecx
        mov  dl, 1
        call {TEOBJ_CREATE:#x}
        push eax
        mov  byte ptr [eax + 0xc], {DELAY}
        mov  ecx, esi
        mov  byte ptr [eax + 0xd], cl
        push dword ptr [ebp + 0xc]
        push dword ptr [ebp + 8]
        mov  ecx, edi
        mov  edx, eax
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {PLACEHX:#x}
        pop  edx
        test al, al
        jne  i_log
        mov  eax, edx
        mov  dl, 1
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx - 4]
    i_log:
        mov  eax, dword ptr [ebx + {{TEXTLOG}}]
        xor  ecx, ecx
        mov  dl, 1
        call {LOG_CREATE:#x}
        mov  edi, eax
        lea  eax, [edi + 0x18]
        lea  edx, [ebx + {{MESSAGE}}]
        call {LSTRASG:#x}
        mov  eax, edi
        xor  edx, edx
        call {DISTRIBUTE:#x}
        mov  eax, edi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x2c]
        mov  eax, dword ptr [ebx + {{MAP}}]
        movsx eax, byte ptr [eax + 0xa5]
        cmp  eax, esi
        jne  i_out
        mov  eax, dword ptr [ebx + {{SET}}]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, {SPELL_ID}
        call {GETSPELL:#x}
        mov  eax, dword ptr [eax + 0x28]
        test eax, eax
        je   i_out
        xor  edx, edx
        call {SFX_PLAY:#x}
    i_out:
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret  8
    """
    tail = ansistr(MESSAGE)
    return pic(src, va, "ebx", {"BSS": BSS_CLASS, "MAP": AOWHSMAP, "SET": AOWHSSET,
                                "TEXTLOG": TEXTLOG_CELL, "MESSAGE": ("TAIL", 8)}, tail)


def r_msg(va):
    """The marker's MsgProc (eax marker, edx message).  esi marker, edi message, ebx anchor."""
    src = f"""
        push ebx
        push esi
        push edi
        mov  esi, eax
        mov  edi, edx
        call {MSGPROC:#x}
        cmp  dword ptr [edi], 0x20020002
        jne  m_out
        movsx eax, byte ptr [esi + 0xd]
        cmp  eax, dword ptr [edi + 0x18]
        jne  m_out
        dec  byte ptr [esi + 0xc]
        jg   m_out
        jl   m_free
        {{ANC}}
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x7c]
        movsx eax, al
        push eax
        push 0
        push {RADIUS}
        movsx eax, byte ptr [esi + 0xd]
        push eax
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        push eax
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        mov  edx, eax
        pop  ecx
        xor  eax, eax
        call {TRIGGER:#x}
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  eax, dword ptr [eax + 0x40]
        mov  dword ptr [esi + 0x10], eax
        mov  byte ptr [esi + 0x14], 1
        mov  eax, dword ptr [ebx + {{MAP}}]
        mov  dl, byte ptr [eax + 0xa4]
        cmp  dl, byte ptr [eax + 0xa5]
        je   m_snd
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x7c]
        push eax
        push {RADIUS}
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        push eax
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        mov  edx, eax
        pop  ecx
        mov  eax, dword ptr [ebx + {{MAP}}]
        call {TERRVIS:#x}
        test al, al
        je   m_out
    m_snd:
        mov  eax, dword ptr [ebx + {{SET}}]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, {SPELL_ID}
        call {GETSPELL:#x}
        mov  eax, dword ptr [eax + 0x28]
        test eax, eax
        je   m_out
        mov  edx, 1
        call {SFX_PLAY:#x}
        jmp  m_out
    m_free:
        mov  eax, esi
        mov  dl, 1
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx - 4]
    m_out:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "SET": AOWHSSET})


def r_show(va):
    """The marker's Show (eax marker, edx view x, ecx view y, [esp+4] surface; ret 4).  Frame: [ebp+8]
    surface, [ebp-0x10] view y, [ebp-0x14] x, [ebp-0x18] y."""
    src = f"""
        cmp  byte ptr [eax + 0x14], 0
        jne  s_go
        ret  4
    s_go:
        push ebp
        mov  ebp, esp
        push ebx
        push esi
        push edi
        push ecx
        mov  esi, eax
        mov  edi, edx
        {{ANC}}
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x74]
        movsx eax, al
        push eax
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x78]
        movsx eax, al
        push eax
        mov  eax, dword ptr [ebx + {{SET}}]
        mov  eax, dword ptr [eax + 0x84]
        mov  edx, {SPELL_ID}
        call {GETSPELL:#x}
        mov  eax, dword ptr [eax + 0x2c]
        test eax, eax
        je   s_end
        mov  ecx, dword ptr [ebp - 0x18]
        shl  ecx, 5
        mov  edx, dword ptr [ebp - 0x14]
        and  edx, 1
        shl  edx, 4
        add  ecx, edx
        sub  ecx, dword ptr [ebp - 0x10]
        add  ecx, 0x10
        push ecx
        mov  edx, dword ptr [ebx + {{MAP}}]
        mov  edx, dword ptr [edx + 0x40]
        sub  edx, dword ptr [esi + 0x10]
        and  edx, 0xfffff
        push edx
        push dword ptr [ebp + 8]
        mov  ecx, dword ptr [ebp - 0x14]
        shl  ecx, 5
        add  ecx, 8
        sub  ecx, edi
        add  ecx, 0x10
        xor  edx, edx
        call {SEQ_SHOW:#x}
        test al, al
        jne  s_out
    s_end:
        mov  byte ptr [esi + 0x14], 0
    s_out:
        add  esp, 0xc
        pop  edi
        pop  esi
        pop  ebx
        pop  ebp
        ret  4
    """
    return pic(src, va, "ebx", {"MAP": AOWHSMAP, "SET": AOWHSSET})


BUILDERS = [("str", r_str), ("ai", r_ai), ("cid", r_cid), ("name", r_name), ("cs", r_cs),
            ("cls", r_cls), ("reg", r_reg), ("init", r_init), ("msg", r_msg), ("show", r_show)]


def layout():
    base = (SLOT[0] + 5 * len(ENTRIES) + 15) & ~15
    for n, _b in BUILDERS:
        A.setdefault(n, base)
    for _ in range(3):
        va, blobs = base, []
        for n, b in BUILDERS:
            A[n] = va
            blob = b(va)
            blobs.append(("r_" + n, va, blob))
            va = (va + len(blob) + 15) & ~15
    assert va <= SLOT[1], "slot overflow"
    jt = b"".join(b"\xE9" + struct.pack("<i", A[n] - (ENTRY[n] + 5)) for n in ENTRIES)
    return [("entries", SLOT[0], jt)] + blobs


def checks(d):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    u = lambda v: struct.unpack_from("<I", d, P.va2off(d, v))[0]
    rb = lambda va, n: bytes(d[P.va2off(d, va):P.va2off(d, va) + n])
    name = lambda vmt: rb(u(vmt - 0x20) + 1, rb(u(vmt - 0x20), 1)[0])
    for cell, vmt, nm in ((FS_CELL, FS_VMT, b"TFireStormSpell"), (BLAST_CELL, BLAST_VMT, b"TBlastStorm"),
                          (FW_CELL, FW_VMT, b"TFrozenWaterHS"), (TEXTLOG_CELL, TEXTLOG_VMT, b"TTextEventLog")):
        if u(cell) != vmt or name(vmt) != nm:
            sys.exit("ABORT: %08X no longer holds %s" % (cell, nm.decode()))
    if u(FW_VMT - 0x1C) != 0x10 or u(TEXTLOG_VMT - 0x1C) != 0x1C:
        sys.exit("ABORT: TFrozenWaterHS / TTextEventLog instance size changed")
    if u(FW_VMT - 0x20) - FW_VMT != VMT_LEN:
        sys.exit("ABORT: TFrozenWaterHS's VMT is no longer %#x bytes of slots" % VMT_LEN)
    if rb(H_CLS - 9, 9) != bytes.fromhex("8bd4b9060000008bc3"):
        sys.exit("ABORT: RegisterStorms' RegisterEClasses call site moved")
    for h in H_NAMES:
        if rb(h - 7, 3) != bytes.fromhex("8b04bd") or u(h - 4) != 0x558E8264:
            sys.exit("ABORT: %08X is not IncommingStorm's TranslateRStr(TStormTypeRStr[edi])" % h)
    _e, secs = P.sections(d)
    for _vs, sva, rs, ra in secs:             # nobody else creates spell 92
        for i in range(ra, ra + rs - 7):
            src = P.IMAGE_BASE + sva + (i - ra)
            if SLOT[0] <= src < SLOT[1]:
                continue
            if d[i] == 0xC7 and d[i + 1] in range(0x40, 0x48) and d[i + 2] == 0x10 \
                    and struct.unpack_from("<I", d, i + 3)[0] == SPELL_ID:
                sys.exit("ABORT: %08X also stores spell id %d" % (src, SPELL_ID))
    dual = d[P.va2off(d, 0x558B6000):P.va2off(d, 0x558B6000) + 0x100]
    if not any(struct.unpack_from("<HBB", dual, k) in ((SPELL_ID, 3, 4), (SPELL_ID, 4, 3)) for k in range(0, 0xFC, 4)):
        print("  NOTE: build_dual_sphere.py's TABLE does not list spell %d as Earth/Air yet" % SPELL_ID)
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for n, va, blob in layout()[1:]:
        code = blob
        for lit in (ansistr(NAME), ansistr(MESSAGE)):
            if lit in code:
                code = code[:code.index(lit)]
        code = code.rstrip(b"\x90")
        ins = list(md.disasm(code, va))
        assert sum(i.size for i in ins) == len(code), "%s does not disassemble cleanly" % n
        for i in ins:
            if i.mnemonic == "push" and i.op_str.startswith("0x"):
                v = int(i.op_str, 16)
                assert v < 0x80 or v == 0xFFFFFFFF, "%08X: push %s (imm8 sign trap)" % (i.address, i.op_str)
            assert i.mnemonic != "call" or not i.op_str.startswith("0x") or \
                P.IMAGE_BASE <= int(i.op_str, 16) < 0x55990000, "%08X: call outside the image" % i.address


def main():
    blobs = layout()
    d = open(P.TARGET, "rb").read()
    checks(d)
    rel = lambda src, dst: b"\xE8" + struct.pack("<i", dst - (src + 5))
    pk = lambda v: struct.pack("<I", v)
    hooks = [(H_CLS, rel(H_CLS, REG_ECLASSES), rel(H_CLS, ENTRY["cls"])),
             (H_REG, rel(H_REG, REGISTER_SPELL), rel(H_REG, ENTRY["reg"]))]
    hooks += [(h, rel(h, TRANSLATE), rel(h, ENTRY["name"])) for h in H_NAMES]
    hooks += [(S_CS, pk(FS_CREATESTORM), pk(ENTRY["cs"])),
              (S_INIT, pk(BLAST_INIT), pk(ENTRY["init"])),
              (S_UPD, pk(BLAST_UPD), pk(STORM_UPD)),
              (S_FIN, pk(BLAST_FIN), pk(STORM_FIN)),
              (T_STR, pk(T_STR_OLD), pk(ENTRY["str"])),
              (T_AI, pk(T_AI_OLD), pk(ENTRY["ai"])),
              (B_TYPE, b"\x09", b"\x07")]
    print("  routines: " + ", ".join("%s %08X" % (n, v) for n, v in A.items()))
    run("build_meteor_storm -- Meteor Storm (AoWEPACK)", hooks, blobs, SLOT, [],
        reloc_ok=(S_CS, S_INIT, S_UPD, S_FIN, T_STR, T_AI))


if __name__ == "__main__":
    main()
