#!/usr/bin/env python3
r"""
AoW1 mod -- "leadership_others": Leadership buffs every OTHER unit in the party, never itself,
and the ability card splits own level from received level ("Leadership III (+IV received)").

Ported from a fellow modder's `patch_leadership_others_v1.py` (Inioch, 2026-09-13,
`Modding Resources/Inioch/share7/patch scripts/`) and re-verified against OUR AoWEPACK.dpl.
See "DEVIATIONS FROM THE ORIGINAL" at the bottom -- one whole change of his is deliberately NOT
ported, because in our build it would break build_leadership_fearless.py.

================================================================================
VANILLA MODEL (ability id 0x2E, TLeadershipAbility VMT 0x55722008)
================================================================================
Per-owner TLeadershipAbilityData record (TAbilityOwner.GetAbilityData @0x5574F1C4, EAX=owner,
EDX=id -> record | nil):
    [+0x0C] own (inherent) level   [+0x0E] id   [+0x10] borrowed (aura) level   [+0x14] source name

  TLeadershipAbility.GetLevel      VMT+0x70  @0x557661C4  = max(own, borrowed)
  attack-bonus getter              VMT+0x5C  @0x557661FC  `mov ecx,[eax]; call [ecx+0x70]` then
  defence-bonus getter             VMT+0x60  @0x55766210   index the byte ladder with that level
  SetExternalSource                          @0x55766224  (EAX=abil, EDX=unit, CL=level,
                                                            [esp+4]=name; ret 4)
  ResetExternalSource                        @0x557662E4
  CanExpand                        VMT+0xC4  @0x557663A8  reads [record+0x0C] directly (own < cap)
  GetInherent                      VMT+0x90  @0x55766384  = [record+0x0C] != 0
  TMultiLevelAbility.GetName       VMT+0x58  @0x55765298  = GetLevelName(GetLevel(owner))

  TArmy.UpdateFormation @0x5578D034 (every stack change; TCombatUnit.SetParty re-runs it at combat
  start, so it holds in tactical AND auto-resolve):
    pass 1  ResetExternalSource on every unit, and find max1 = highest GetAbilityLevel(0x2E)
            (VMT+0x144, item-aware) in the army, plus that unit's name
    pass 2  @0x5578D128..0x5578D186: SetExternalSource(max1) on every unit whose level < max1

  So vanilla's leader always buffs ITSELF with its own level, and the strongest leader in a stack
  never receives anything.

================================================================================
NEW RULE
================================================================================
A unit's Leadership bonus = the highest OWN Leadership level among the OTHER units in its party.
Never its own. Two leaders buff each other; a lone leader gets nothing.

  A  BONUS SOURCE.  Both bonus getters call `cave_blevel` instead of GetLevel: the bonus level is
     the unit's own record's BORROWED field only ([+0x10]); no record -> 0.  5 bytes each
     (`8b 08 ff 51 70` -> `e8 rel32`), nothing displaced.
       0x557661FC  attack   0x55766210  defence
     ⚠ The `mov al,[eax+0x5580F0C0]` / `[...+0x5580F0C8]` ladders two instructions later are
     build_leadership4.py's relocated tables; they are NOT touched here, and the disp32 at
     0x55766207 that carries a .reloc entry sits outside our 5-byte window.

  B  PROPAGATION.  Pass 2 is replaced by `cave_pass2`, hooked on its first 6 bytes at 0x5578D128
     (`83 7d f8 00 7e 58` -> `e9 rel32` + one `nop`) and resuming at the function's shared exit
     0x5578D186. The vanilla pass-2 bytes stay in place, dead, because 0x5578D162 carries a .reloc
     entry that must not be displaced (verified: the only .reloc entry in 0x5578D128..0x5578D186).
        loop 1: count = #units whose own level == max1; max2 = highest own level below max1
        loop 2: target(u) = max2 if (own(u)==max1 and count==1) else max1
                if target > 0: SetExternalSource(ability, u, target, name) -- which creates the
                record and sets the bit, but writes the borrowed field only when own < target --
                then force [record+0x10] := target, and re-fire the unit's VMT+0x90
                "AbilitiesChanged" (TUnit caches its ability bonuses in [unit+0x44..0x47]; the
                SetExternalSource call already fired +0x90 BEFORE our direct write, so without the
                re-fire a non-hero top leader would never see its received bonus).
     Own levels are read through VMT+0x144 GetAbilityLevel, exactly as pass 1 does, so item-granted
     Leadership (Crown of Kings) still projects an aura.
     Host frame: [ebp-4]=army, [ebp-8]=max1, [ebp-0xC]=name. The host pushes EBX and ESI (restored
     at 0x5578D1A8) and does NOT push EDI, so the cave saves EDI and may clobber EBX/ESI. ESP is
     restored exactly before the jump to 0x5578D186, whose `pop edx/pop ecx/pop ecx` unwinds the
     SEH frame.

  C  DISPLAY.  TLeadershipAbility VMT+0x58 (slot 0x55722060, .reloc-covered -- repointing the value
     keeps the loader fixing it up) -> `cave_lname`, replacing TMultiLevelAbility.GetName:
        read the owner's record; own=[+0x0C], borrowed=[+0x10]
        temp := GetLevelName(ability, own)   -- dispatched through VMT+0x10c, which is
                                                build_leadership4.py's cave_lsname @0x5580F000,
                                                so the two features compose and neither pins the
                                                other's address
        result := borrowed ? temp + " (+<roman> received)" : temp
     Follower with no own level: "Leadership (+IV received)". Leader: "Leadership III (+I received)"
     or plain "Leadership III" when alone.
     The four suffix literals are embedded as Delphi AnsiStrings (refcount -1, never freed) with a
     PIC pointer table, the same idiom build_leadership4.py uses for the game's own " I".." IV".
     They are NEW English text with no vanilla counterpart, so there is no ResStr.mld entry to
     extend and no .pfs record to edit: an in-DLL constant is the right home (a .pfs description
     record would not reach this label, which is built by code at query time).

Untouched: GetLevel itself, hero level-up CanExpand, the aura garbage collector, pass 1, and
build_leadership4.py's ladders/costs/level names.

================================================================================
CAVES  --  0x5584A000, exclusive 0x400 (verified all-zero; new high-water mark)
================================================================================
  cave_blevel  0x5584A000   borrowed level of a unit's record
  cave_pass2   0x5584A040   the replacement propagation pass
  cave_lname   0x5584A180   the split "own (+received)" label, plus the four literals
Previous high-water mark was combatunitguard.py's 0x55849000+0x100 (see 12-re-toolchain.md §6.1).
⚠ Inioch's own cave zone (0x55815D00) is NOT reused -- his addresses are chosen against his build
and have collided with live Ziggurat code before (his 0x5580E120 is our assassin cave).

POSITION INDEPENDENCE
  Every call out is rel32 and every dispatch is register-indirect. The two absolute references --
  the AoWHSSet global 0x558FA044 in cave_pass2 and the suffix pointer table in cave_lname -- are
  reached with the standard `call $+5; pop reg; sub reg,<link addr>` load-delta anchor, so the
  .dpl may rebase freely. No new .reloc entries, none displaced.

NO RNG.  Nothing here draws; the RNG pattern taxonomy does not apply (rng_audit.py --owners is
unchanged by this feature).

MULTIPLAYER.  UpdateFormation is deterministic and runs on every peer from replicated state; the
new pass reads only own levels and the party roster, so every peer computes the same auras.

REVERT -- `--undo` is surgical: it restores the two 5-byte getter calls, the 6-byte pass-2 head and
the VMT slot, and zeroes the three caves. It touches no backup and stays correct however many later
features are stacked on the DLL. The `<game dir>\backups\AoWEPACK.dpl.pre-leadershipothers`
snapshot is NOT a revert path (whole-file copy; restoring it would destroy every feature applied
afterwards) and is minted on --apply only, from a file proved to hold the original bytes at all
four sites.

================================================================================
DEVIATIONS FROM THE ORIGINAL
================================================================================
 1. HIS CHANGE (C) IS NOT PORTED -- GetLevel still returns max(own, borrowed).
    He made TLeadershipAbility.GetLevel return the own level only. In our DLL that would break
    build_leadership_fearless.py: "Leadership IV makes the whole stack count as Fearless" derives
    its answer at query time from `GetAbilityLevel(unit, 0x2E) >= 4` (VMT+0x144 -> GetLevel), which
    for a FOLLOWER is exactly the borrowed level. Own-only would silently drop every follower out
    of the Fearless stack and leave only the leader -- and the leader, under this very rework, now
    usually holds max2 rather than IV.
    His two motivations do not transfer either: our CanExpand @0x557663A8 and GetInherent
    @0x55766384 already read [record+0x0C] directly, so the hero level-up cap and the "is it
    inherent" test never saw a borrowed level here, and build_leadership_fix.py already routes the
    grant comparison in UpdateDefaultAbilities through GetInherentLevel.
    Consequence kept, knowingly: the map editor's ability list still shows a follower's effective
    level, as it did in vanilla.
 2. HIS CAVE_LNAME CALLED TMultiLevelAbility.GetName and relied on (1) to make it render the own
    level. Ours reads the record itself and dispatches GetLevelName through VMT+0x10c, so the
    split display works with GetLevel left alone, and build_leadership4.py's cave_lsname is reached
    through the VMT rather than by hard-coded address.
 3. Caves moved 0x55815D00 -> 0x5584A000 (his zone is not the free zone in our DLL).
 4. Target is AoWEPACK.dpl located by the project resolver; VA->file offset through the real PE
    section table; keystone-assembled from source and capstone-disassembled (`--dis`); project
    conventions -- dry-run default / --apply / surgical --undo / snapshot in <game>\backups\.

IN-GAME CHECKLIST (nobody has played this)
  1. Lone hero with Leadership III, alone in a stack: card reads "Leadership III", no bonus in the
     attack/defence breakdown.
  2. That hero plus three ordinary units: the units' cards read "Leadership (+III received)" and
     they gain +3/+3; the hero itself gains nothing.
  3. Two heroes, Leadership III and Leadership I, stacked: the III hero reads
     "Leadership III (+I received)" (+1/+1), the I hero reads "Leadership I (+III received)"
     (+3/+3), the ordinary units +3/+3.
  4. Two heroes with the SAME level (co-leaders): both receive that level.
  5. Buy a Leadership level in the hero level-up dialog -- the party bonus must update immediately
     (build_leadership_aura.py) and the numerals must still read I..IV.
  6. Leadership IV stack: every member still counts as Fearless (Terror / Cause Fear do nothing) --
     this is the coupling deviation 1 protects.
  7. Crown of Kings (item-granted Leadership) on a hero: the party still receives the aura.
  8. Split the stack, move, end turn, reload a save: bonuses recompute, no stuck "received" text.
  9. Auto-resolve a battle with a Leadership stack: the bonus applies there too.
 10. Map editor: assigning/removing Leadership still behaves.

Idempotent, verify-before-write, free-space asserted, dry-run by default / --apply / --undo / --dis.
"""
import os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Ziggurat/Modding Resources/build_scripts/)
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never the game root
TARGET = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(TARGET) + ".pre-leadershipothers")
DLL_BASE = 0x55700000

ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

# ---------------------------------------------------------------- engine addresses
LEADERSHIP  = 0x2E
GET_ABDATA  = 0x5574F1C4      # TAbilityOwner.GetAbilityData (EAX=owner, EDX=id) -> record|nil
GET_ABILITY = 0x557501C0      # TAbilityControl.GetAbility   (EAX=control, EDX=id) -> ability
SET_EXTSRC  = 0x55766224      # TLeadershipAbility.SetExternalSource (ret 4)
AOWHSSET_G  = 0x558FA044      # [g]+0x80 = TAbilityControl
ML_GETNAME  = 0x55765298      # TMultiLevelAbility.GetName (the value we replace in the VMT slot)
LSTRCAT3    = 0x55701190      # System.@LStrCat3 (EAX=@dest, EDX=s1, ECX=s2)
LSTRASG     = 0x55701150      # System.@LStrAsg  (EAX=@dest, EDX=src)
LSTRCLR     = 0x55701140      # System.@LStrClr  (EAX=@s)

SITE_ATK    = 0x557661FC      # `mov ecx,[eax]; call [ecx+0x70]`
SITE_DEF    = 0x55766210      # ditto
ORIG_GET    = bytes.fromhex("8b08ff5170")
SITE_P2     = 0x5578D128      # cmp dword [ebp-8],0 ; jle 0x5578D186
ORIG_P2     = bytes.fromhex("837df8007e58")
P2_EXIT     = 0x5578D186
SITE_NAME   = 0x55722060      # TLeadershipAbility VMT+0x58 (GetName)

SUFFIXES = (" (+I received)", " (+II received)", " (+III received)", " (+IV received)")

# ---------------------------------------------------------------- cave layout
CAVE_BASE   = 0x5584A000
CAVE_LIMIT  = 0x400           # exclusive 0x5584A000..0x5584A3FF
CAVE_BLEVEL = CAVE_BASE + 0x000
CAVE_PASS2  = CAVE_BASE + 0x040
CAVE_LNAME  = CAVE_BASE + 0x180


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


# ---------------------------------------------------------------- cave_blevel
blevel_src = f"""
    test edx, edx
    jz   _zero
    mov  ecx, [eax+0xC]              /* ability id */
    mov  eax, edx                    /* owner */
    mov  edx, ecx
    call 0x{GET_ABDATA:X}
    test eax, eax
    jz   _zero
    movzx eax, byte ptr [eax+0x10]   /* borrowed level */
    ret
_zero:
    xor  eax, eax
    ret
"""
cave_blevel = asm(blevel_src, CAVE_BLEVEL)

# ---------------------------------------------------------------- cave_pass2
PLACEHOLDER = 0x11111111       # forces imm32/disp32 encodings so pass 1 and pass 2 are the same size

_p2_head = """
    cmp  dword ptr [ebp-8], 0
    jg   _start
"""
_unit_count = """
    mov  eax, [ebp-4]
    mov  eax, [eax+8]
    mov  esi, [eax+8]
"""
_unit_i = """
    mov  eax, [ebp-4]
    mov  eax, [eax+8]
    mov  eax, [eax+4]
    mov  ebx, [eax+esi*4]
"""
_own_level = f"""
    mov  edx, {LEADERSHIP}
    mov  eax, ebx
    mov  ecx, [eax]
    call dword ptr [ecx+0x144]
"""
def build_pass2(anchor):
    return bytearray(asm(_p2_head + f"""
    jmp  0x{P2_EXIT:X}
_start:
    push edi
    call _anchor
_anchor:
    pop  edi
    sub  edi, 0x{anchor:X}
    push 0                           /* [esp+4] = max2  */
    push 0                           /* [esp]   = count */
""" + _unit_count + """
_l1:
    dec  esi
    js   _l1end
""" + _unit_i + _own_level + """
    cmp  eax, [ebp-8]
    jne  _notmax
    inc  dword ptr [esp]
    jmp  _l1
_notmax:
    cmp  eax, [esp+4]
    jle  _l1
    mov  [esp+4], eax
    jmp  _l1
_l1end:
""" + _unit_count + """
_l2:
    dec  esi
    js   _l2end
""" + _unit_i + _own_level + f"""
    mov  ecx, [ebp-8]                /* target = max1 */
    cmp  eax, ecx
    jne  _tgt
    cmp  dword ptr [esp], 1
    jne  _tgt
    mov  ecx, [esp+4]                /* sole top leader -> max2 */
_tgt:
    test ecx, ecx
    jle  _l2
    push ecx
    mov  eax, [edi + 0x{AOWHSSET_G:X}]
    mov  eax, [eax+0x80]
    mov  edx, {LEADERSHIP}
    call 0x{GET_ABILITY:X}
    mov  ecx, [esp]                  /* cl = target */
    push dword ptr [ebp-0xC]         /* source name */
    mov  edx, ebx
    call 0x{SET_EXTSRC:X}            /* pops the name */
    mov  eax, ebx
    mov  edx, {LEADERSHIP}
    call 0x{GET_ABDATA:X}
    pop  ecx
    test eax, eax
    jz   _l2
    mov  byte ptr [eax+0x10], cl     /* borrowed := target */
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x90]        /* AbilitiesChanged: refresh the cached bonuses */
    jmp  _l2
_l2end:
    add  esp, 8
    pop  edi
    jmp  0x{P2_EXIT:X}
""", CAVE_PASS2))


_p2_probe = build_pass2(PLACEHOLDER)
_p2_anchor_off = _p2_probe.find(bytes.fromhex("e8000000005f"))      # call $+5 ; pop edi
assert _p2_anchor_off > 0 and _p2_probe.count(bytes.fromhex("e8000000005f")) == 1, "pass2 anchor not found"
ANCHOR_P2 = CAVE_PASS2 + _p2_anchor_off + 5
cave_pass2 = bytes(build_pass2(ANCHOR_P2))
assert len(cave_pass2) == len(_p2_probe), "pass2 changed size between passes"
assert cave_pass2[_p2_anchor_off + 5] == 0x5F, "pass2 call/pop anchor mismatch (expected `pop edi`)"

# ---------------------------------------------------------------- cave_lname
_ln_pro = """
    push ebx
    push esi
    push edi
    push ebp
    mov  edi, ecx
    mov  esi, edx
    mov  ebx, eax
"""
_ln_pro_len = len(asm(_ln_pro, CAVE_LNAME))
ANCHOR_LN = CAVE_LNAME + _ln_pro_len + 5


def build_lname(suf_tab, anchor=ANCHOR_LN):
    src = _ln_pro + f"""
    call _n
_n:
    pop  ebp
    sub  ebp, 0x{anchor:X}
    push 0                           /* [esp+4] = temp AnsiString */
    push 0                           /* [esp]   = borrowed level  */
    xor  eax, eax                    /* eax = own level */
    test esi, esi
    jz   _havelv
    mov  eax, esi
    mov  edx, [ebx+0xC]
    call 0x{GET_ABDATA:X}
    test eax, eax
    jz   _zerolv
    movzx ecx, byte ptr [eax+0x10]
    mov  [esp], ecx
    movzx eax, byte ptr [eax+0xC]
    jmp  _havelv
_zerolv:
    xor  eax, eax
_havelv:
    lea  ecx, [esp+4]
    mov  edx, eax
    mov  eax, ebx
    mov  ebx, [eax]
    call dword ptr [ebx+0x10C]       /* GetLevelName(ability, own, @temp) */
    mov  eax, [esp]
    test eax, eax
    jz   _plain
    cmp  eax, 4
    jle  _ok
    mov  eax, 4
_ok:
    dec  eax
    mov  ecx, [ebp + eax*4 + 0x{suf_tab:X}]
    add  ecx, ebp
    mov  edx, [esp+4]
    mov  eax, edi
    call 0x{LSTRCAT3:X}
    jmp  _fin
_plain:
    mov  eax, edi
    mov  edx, [esp+4]
    call 0x{LSTRASG:X}
_fin:
    lea  eax, [esp+4]
    call 0x{LSTRCLR:X}
    add  esp, 8
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""
    return bytearray(asm(src, CAVE_LNAME))


# two passes: the suffix table VA depends on the code length, which depends on the VA
_probe = build_lname(PLACEHOLDER)
SUF_TAB = (CAVE_LNAME + len(_probe) + 3) & ~3
lname_code = build_lname(SUF_TAB)
assert len(lname_code) == len(_probe), "lname code length changed between passes"
assert lname_code[_ln_pro_len + 5] == 0x5D, "lname call/pop anchor mismatch (expected `pop ebp`)"

# ---- data: 4-dword pointer table (link-time VAs) + the AnsiString literals
blob = bytearray(lname_code)
blob += b"\x90" * (SUF_TAB - (CAVE_LNAME + len(blob)))
tab_off = len(blob)
blob += b"\x00" * (4 * len(SUFFIXES))
for i, s in enumerate(SUFFIXES):
    while len(blob) % 4:
        blob += b"\x00"
    blob += struct.pack("<iI", -1, len(s))          # refcount -1 (never freed), length
    struct.pack_into("<I", blob, tab_off + i * 4, CAVE_LNAME + len(blob))
    blob += s.encode("ascii") + b"\x00"
cave_lname = bytes(blob)
for i, s in enumerate(SUFFIXES):                    # self-check: table slot -> its own bytes
    p = struct.unpack_from("<I", cave_lname, tab_off + i * 4)[0] - CAVE_LNAME
    assert cave_lname[p:p + len(s)] == s.encode("ascii"), s
    assert struct.unpack_from("<I", cave_lname, p - 4)[0] == len(s), s

CAVES = ((CAVE_BLEVEL, cave_blevel, "cave_blevel"),
         (CAVE_PASS2,  cave_pass2,  "cave_pass2"),
         (CAVE_LNAME,  cave_lname,  "cave_lname + suffix literals"))
for va, body, desc in CAVES:
    assert va + len(body) <= CAVE_BASE + CAVE_LIMIT, f"{desc} overflows the cave block"
assert CAVE_BLEVEL + len(cave_blevel) <= CAVE_PASS2, "cave_blevel overruns cave_pass2"
assert CAVE_PASS2 + len(cave_pass2) <= CAVE_LNAME, "cave_pass2 overruns cave_lname"


# ---------------------------------------------------------------- PE helpers
def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]; n = struct.unpack_from("<H", data, e + 6)[0]
    op = struct.unpack_from("<H", data, e + 20)[0]; s = e + 24 + op; secs = []
    for _ in range(n):
        vs, va, rs, raw = struct.unpack_from("<IIII", data, s + 8); secs.append((va, vs, raw, rs)); s += 40
    return secs


def va2off(secs, va):
    rva = va - DLL_BASE
    for va0, vs, raw, rs in secs:
        if va0 <= rva < va0 + max(vs, rs):
            return raw + (rva - va0)
    raise ValueError(hex(va))


def relocs(data, secs):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    rva, size = struct.unpack_from("<II", data, e + 24 + 96 + 5 * 8)
    p = va2off(secs, DLL_BASE + rva); end = p + size; out = set()
    while p < end:
        pg, blk = struct.unpack_from("<II", data, p)
        if blk < 8:
            break
        for k in range(8, blk, 2):
            x = struct.unpack_from("<H", data, p + k)[0]
            if x >> 12 == 3:
                out.add(DLL_BASE + pg + (x & 0xFFF))
        p += blk
    return out


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


def show(body, va, desc):
    print(f"[cave ] {desc} @ {va:08X} ({len(body)} B)")
    for ins in cs.disasm(body, va):
        print(f"  {ins.address:08X} {ins.bytes.hex(' '):<26}{ins.mnemonic} {ins.op_str}")


# ---------------------------------------------------------------- patch table
PATCHES = [
    (SITE_ATK,  ORIG_GET,  b"\xE8" + rel32(SITE_ATK, CAVE_BLEVEL),
     f"{SITE_ATK:08X} attack-bonus getter: GetLevel -> cave_blevel"),
    (SITE_DEF,  ORIG_GET,  b"\xE8" + rel32(SITE_DEF, CAVE_BLEVEL),
     f"{SITE_DEF:08X} defence-bonus getter: GetLevel -> cave_blevel"),
    (SITE_P2,   ORIG_P2,   b"\xE9" + rel32(SITE_P2, CAVE_PASS2) + b"\x90",
     f"{SITE_P2:08X} UpdateFormation pass 2 -> cave_pass2"),
    (SITE_NAME, struct.pack("<I", ML_GETNAME), struct.pack("<I", CAVE_LNAME),
     f"{SITE_NAME:08X} VMT+0x58 GetName -> cave_lname"),
]


def main():
    apply_ = "--apply" in sys.argv
    undo = "--undo" in sys.argv
    if apply_ and undo:
        print("[x] --apply and --undo are mutually exclusive"); return 1

    print()
    if "--dis" in sys.argv or "--show" in sys.argv:
        for va, body, desc in CAVES:
            show(body, va, desc)
        print(f"[data ] suffix table @ {SUF_TAB:08X}: " +
              ", ".join(f"{struct.unpack_from('<I', cave_lname, tab_off + i * 4)[0]:08X}"
                        for i in range(len(SUFFIXES))))
        print("[data ] " + " | ".join(repr(s) for s in SUFFIXES))

    data = bytearray(open(TARGET, "rb").read())
    secs = load_sections(data)
    rd = lambda va, n: bytes(data[va2off(secs, va):va2off(secs, va) + n])

    # ---- state of every site
    state = []
    for va, old, new, desc in PATCHES:
        cur = rd(va, len(old))
        state.append("patched" if cur == new else "vanilla" if cur == old else "FOREIGN")
    for (va, old, new, desc), st in zip(PATCHES, state):
        print(f"  [{st:7}] {desc}")
    cave_state = []
    for va, body, desc in CAVES:
        live = rd(va, len(body))
        cave_state.append("ours" if live == body else "zero" if not any(live) else "FOREIGN")
        print(f"  [{cave_state[-1]:7}] {va:08X} {desc} ({len(body)} B)")

    if "FOREIGN" in state or "FOREIGN" in cave_state:
        print("[x] a site or cave holds bytes that are neither original nor ours -- aborting")
        return 1

    R = relocs(data, secs)
    assert SITE_NAME in R, "VMT slot 0x55722060 should carry a .reloc entry"
    hit = [r for va, old, new, d in PATCHES if va != SITE_NAME
           for r in R if va <= r < va + len(new)]
    hit += [r for va, body, d in CAVES for r in R if va <= r < va + len(body)]
    if hit:
        print("[x] .reloc entry inside a hook window or cave: " +
              ", ".join(f"{h:08X}" for h in hit))
        return 1
    print(f"[reloc] clean: no .reloc entry inside any hook window or cave "
          f"(VMT slot {SITE_NAME:08X} is reloc'd by design -- value repointed, entry kept)")

    if undo:
        if all(s == "vanilla" for s in state) and all(c in ("zero",) for c in cave_state):
            print("[= ] nothing applied"); return 0
        for va, old, new, desc in PATCHES:
            o = va2off(secs, va); data[o:o + len(old)] = old; print(f"[u ] restore {desc}")
        for va, body, desc in CAVES:
            o = va2off(secs, va); data[o:o + len(body)] = b"\x00" * len(body)
            print(f"[u ] zero {va:08X} {desc}")
        try:
            open(TARGET, "wb").write(data)
        except PermissionError:
            print("[x] LOCKED -- close every AoW binary"); return 1
        print("[done] undone (surgical; no backup touched)"); return 0

    if all(s == "patched" for s in state) and all(c == "ours" for c in cave_state):
        print("[= ] already applied -- chain intact"); return 0
    if not all(s in ("vanilla", "patched") for s in state):
        print("[x] mixed state -- not written"); return 1
    # growth-zone guard: everything from the end of cave_lname to the block ceiling must be zero
    tail_va = CAVE_LNAME + len(cave_lname)
    tail_n = (CAVE_BASE + CAVE_LIMIT) - tail_va
    if any(rd(tail_va, tail_n)):
        print(f"[x] {tail_va:08X}..{CAVE_BASE + CAVE_LIMIT:08X} is not zero -- refusing to write")
        return 1
    print(f"[space] {tail_va:08X}..{CAVE_BASE + CAVE_LIMIT:08X} verified zero")

    if not apply_:
        print("\n[dry] originals verified, caves free. Re-run with --apply to write.")
        return 0

    # snapshot ONLY on --apply, and only from a file proved to hold the original bytes
    if all(s == "vanilla" for s in state) and not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(TARGET, BACKUP); print(f"[bak] {BACKUP}")
    for va, body, desc in CAVES:
        o = va2off(secs, va); data[o:o + len(body)] = body; print(f"[w ] {va:08X} {desc}")
    for va, old, new, desc in PATCHES:
        o = va2off(secs, va); data[o:o + len(new)] = new; print(f"[w ] {desc}")
    try:
        open(TARGET, "wb").write(data)
    except PermissionError:
        print("[x] LOCKED -- close every AoW binary (AoWz.exe/AoWzCompat.exe/AoWzEd.exe)"); return 1
    print("[done] applied, UNTESTED -- run the in-game checklist in this docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
