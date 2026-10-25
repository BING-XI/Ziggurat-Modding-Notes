#!/usr/bin/env python3
r"""
AoW1 mod -- "Fire heals Fire units", with a "+N" heal number in the Party-Damage popup.

Fire damage HEALS a unit holding Living Flame -- the renamed Fire Halo enchantment 0xA3, or the
passive 0x52 that Fire Elemental (226), Fire Sprite (228) and Salamander (58) carry (v3,
2026-10-22; until then the test was resource index 226/228) -- for all STRATEGIC / role fire:
Firestorm, map-hex fires, Fire Barrier (all flow through TAbstractUnit.ExecuteDamageRole
@0x55781AC4). Battle fire is build_livingflame.py's (TCombatObject.ExecuteDamageRole).
RNG: unchanged in kind -- the heal draws through the host's own roller (ExecuteDamageRole_500)
for a fire-immune holder, where vanilla drew nothing; v3 only widens WHICH units take that draw.

Touches TWO binaries, both inside `Ziggurat\` (exe names from `zigexe.py`):
  AoWEPACK.dpl    : 3 caves + 3 redirects
  AoWz.exe        : 1 five-byte patch
⚠ The exe half is LIVE as soon as it is written: `Ziggurat/AoWz.exe` runs from `Ziggurat/`. (Until 2026-09-09 this needed a second `build_overlay.py --apply` step; that script is retired.)

cave_mapfire_gate additionally makes MAP-HEX FIRE / FIRE BARRIER heal Living Flame holders:
TArmy.TriggerFireDamage pre-gates its loop on fire-immunity and skips
ExecuteDamageRole for immune units, so without this the map-fire path never
reached cave_fireheal. The gate cave reroutes ONLY Living Flame holders into the damage path
(other fire-immune units keep showing "immune").

MECHANISM
  Heal: cave_fireheal redirects ExecuteDamageRole. For a Living Flame holder hit by
  fire (param4==0x0001) it returns the NEGATED damage roll; every fire caller does
  `SetHP(HP - dmg)`, so a negative dmg heals (HP-(-x)=HP+x), and the storm
  `if(0<dmg)` secondary-effect guard is skipped. SetHitPoints (TUnit) clamps to
  [0,max]. Identity (v3): the unit's item-aware ability query, VMT +0x148, for 0xA3
  then 0x52. (v1/v2 read unit+0x40->resource, +4->list, call [list.vtable+0x84] ==
  UnitResourceIndex 226/228; those bodies stay accepted prior states.)

  Display: the callers log `dmg` (now negative) into the event-log byte list the
  Party-Damage popup renders. The popup (TArmyEventDlg in AoWz.exe) draws each
  number via AoWEPACK's exported ShowDamageIcon(x,y,font,type,VALUE), which does
  IntToStr(VALUE) + font draw. Two edits make heals show "+N":
    (1) EXE @0x436BFF: `and eax,0xFF` -> `movsx eax,al` so the popup passes the
        SIGNED value (e.g. -2) to ShowDamageIcon at this call site only.
    (2) cave_plusnum redirects ShowDamageIcon's IntToStr: if VALUE<0 it prints
        "+" + IntToStr(-VALUE) (via @LStrCat3 and an embedded "+" AnsiString
        literal, addressed by call/pop delta so it's rebase-safe); VALUE>=0 is
        unchanged, so normal damage numbers are untouched. Only fire-heals ever
        produce a negative here.

Rebase-safe (aow1-dpl-rebasing): caves use rel32 + register-relative refs only;
the one absolute datum (the "+" literal) is reached via call/pop delta.
Idempotent, verifies every original byte per file. Dry-run by default; pass --apply. Re-run with no
args to verify.

Revert: NOT by snapshot -- undo surgically. There is no snapshot layer at all (both stacks were
purged, 2026-08-08 and 2026-09-09), so a `.pre-*` restore is not a revert path. A
`<game dir>\backups\<file>.pre-firefeed` is minted only from a file whose every site still holds
the untouched original bytes; a re-tune over our own caves and any partially-applied file take
none. (The "no backup file exists yet" gate was not a proof of anything: after the 2026-09-09
rename no `AoWz.exe.pre-firefeed` can exist, so it would have snapshotted the PATCHED exe under an
authoritative-looking name.)
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zigexe                                   # mod binary names (AoWz.exe)
BACKUP_DIR = os.path.join(GAME, "backups")      # ⚠ backups/, never the game root -- rule 2026-09-03
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

# ---- PE section mapping ------------------------------------------------------
def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e+6)[0]
    optsize = struct.unpack_from("<H", data, e+20)[0]
    sec = e+24+optsize
    secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw = struct.unpack_from("<IIII", data, sec+8)
        secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def mkva2off(base):
    def va2off(secs, va):
        rva = va-base
        for vaddr,vsize,raw,rsize in secs:
            if vaddr <= rva < vaddr+max(vsize,rsize):
                return raw+(rva-vaddr)
        raise ValueError(f"VA {va:08X} not mapped")
    return va2off
def rel32(src, dst): return struct.pack("<i", dst-(src+5))

# ============================ AoWEPACK.dpl ====================================
DLL_BASE = 0x55700000
# --- addresses (Ghidra-verified) ---
EXECDMGROLE = 0x55781AC4; EXEC_CONT = 0x55781ACA        # ExecuteDamageRole prologue redirect
EXEC_ORIG   = b"\x55\x8b\xec\x83\xc4\xf8"
ROLL500     = 0x55725EAC                                 # ExecuteDamageRole_500B4C01
FIRE_MASK   = 0x0001; ID_ELEM = 0xE2; ID_SPRT = 0xE4
SHOWDMG_INJ = 0x5575A94B; SHOWDMG_CONT = 0x5575A956      # ShowDamageIcon IntToStr redirect (11 bytes)
SHOWDMG_ORIG= b"\x8d\x55\xf8\x8b\x45\x0c\xe8\x36\x6c\xfa\xff"
INTTOSTR    = 0x5570158C; LSTRCAT3 = 0x55701190

CAVE_A = 0x5580DA20                                      # cave_fireheal
# cave_plusnum placed after cave_A (both in verified zero space)

# ---- cave_fireheal (returns -roll for a Living Flame holder hit by fire; v1/v2: 226/228) ----
#
# v2 (2026-08-29, user ruling): **keep the damage roll, drop the ATK-vs-DEF to-hit roll.**
# v1 replicated ExecuteDamageRole's non-immune branch verbatim, so the HEAL inherited the engine's
# to-hit check: `AoWE.ExecuteDamageRole @0x55725EAC` rolls d20, returns 0 on roll<=1 (flat fumble)
# and 0 again when `roll < 10-(attack-defence)`. A Fire Elemental (DEF 6) in map fire (attack 12,
# damage 6) therefore healed NOTHING 20% of the time -- and, because the margin is attack-DEFENCE,
# the tougher the fire unit the worse it healed, so a Stone Skin or a medal made it heal less.
# Nothing about a fire creature being fed by fire should involve dodging.
#
# v2 keeps the magnitude roll (heal still varies 1..damage) but:
#   * discards the caller's strength and passes a fixed margin, so DEFENCE no longer enters;
#   * clamps a rolled 0 up to 1, so the flat 1-in-10 fumble cannot make a heal whiff either.
# NOMISS_MARGIN 8 makes the roll's threshold `10-8 = 2`, which is the lowest value that empties the
# miss band (roll<=1 is already handled above it) -- larger margins would also skew the magnitude
# scaling upward, since the denominator is `18-threshold`. Resulting heal per fire tick, damage 6:
# 1..6 with mean 3.40 for BOTH units, never 0 (was: Elemental 20% zeros / mean 2.95, Sprite 10% /
# 3.30). Flip HEAL_TAKES_TOHIT_ROLL back to True and re-run to restore v1 -- both bodies are
# accepted pre-states, so the cave re-tunes in place with no backup involved.
HEAL_TAKES_TOHIT_ROLL = False
NOMISS_MARGIN = 8


# v3 (2026-10-22, owner's Living Flame design): the HEALED UNITS are no longer resource indices
# 226/228 but any unit holding Living Flame -- Fire Halo's enchantment 0xA3 (renamed Living Flame)
# or the passive 0x52 that Fire Elemental, Fire Sprite and Salamander carry (build_livingflame.py,
# which also heals in battle). Tested through the item-aware ability query, VMT +0x148, with
# EAX = the unit -- so a hero under the spell heals too. The index test is kept only as an
# accepted prior body. Both new bodies fit the runs the old ones were written in.
FIRE_AURA, LIVING_FLAME = 0xA3, 0x52
IDENTITY_BY_ABILITY = True


def _ident_index():
    return f"""
    mov edx, [eax+0x40]
    test edx, edx
    jz _restore
    mov ecx, [edx+4]
    mov eax, ecx
    mov ecx, [ecx]
    call dword ptr [ecx+0x84]
    cmp eax, {ID_ELEM}
    je _heal
    cmp eax, {ID_SPRT}
    jne _restore
"""


def _ident_ability():
    # [esp] = the unit (pushed last); ECX/EDX are on the stack, so the query may clobber them
    return f"""
    mov ecx, [eax]
    mov edx, {FIRE_AURA}
    call dword ptr [ecx+0x148]
    test al, al
    jnz _heal
    mov eax, [esp]
    mov ecx, [eax]
    mov edx, {LIVING_FLAME}
    call dword ptr [ecx+0x148]
    test al, al
    jz _restore
"""


def _caveA_src(tohit, by_ability=False):
    heal_v1 = f"""
    pop eax
    pop ecx
    pop edx
    push ecx
    push edx
    mov edx, [eax]
    call dword ptr [edx+0xc4]
    movsx eax, al
    pop edx
    sub edx, eax
    pop eax
    call 0x{ROLL500:X}
    neg eax
    ret 4
"""
    heal_v2 = f"""
    pop eax
    pop eax
    pop edx
    mov edx, {NOMISS_MARGIN}
    call 0x{ROLL500:X}
    test eax, eax
    jnz _neg
    mov eax, 1
_neg:
    neg eax
    ret 4
"""
    return f"""
    cmp word ptr [esp+4], {FIRE_MASK}
    jne _orig
    push edx
    push ecx
    push eax
""" + (_ident_ability() if by_ability else _ident_index()) + """
_heal:
""" + (heal_v1 if tohit else heal_v2) + f"""
_restore:
    pop eax
    pop ecx
    pop edx
_orig:
    push ebp
    mov ebp, esp
    add esp, -8
    jmp 0x{EXEC_CONT:X}
"""


_bodies = {(t, b): bytes(ks.asm(_caveA_src(t, b), CAVE_A)[0]) for t in (True, False) for b in (False, True)}
_want = _bodies[(HEAL_TAKES_TOHIT_ROLL, IDENTITY_BY_ABILITY)]
# Pad every body to ONE written run: CAVE_B/CAVE_C are derived from len(caveA), so a cave that
# changed length would silently relocate them (and re-tuning would leave the tail of the previous
# body lying in the gap). The run is the v1/v2 run (89 B); the ability bodies must fit inside it.
_runlen = max(len(_bodies[(True, False)]), len(_bodies[(False, False)]))
assert len(_want) <= _runlen, "the chosen body outgrew cave_fireheal's run"   # (v1 + ability test does)
caveA       = _want + b"\x00" * (_runlen - len(_want))
caveA_prior = [b + b"\x00" * (_runlen - len(b)) for k, b in _bodies.items()
               if b != _want and len(b) <= _runlen]

CAVE_B = (CAVE_A + len(caveA) + 0xF) & ~0xF             # 16-align after cave_A

# ---- cave_plusnum : if VALUE<0 -> "+" + IntToStr(-VALUE) ; else IntToStr(VALUE)
# placeholder 0xF0F0F0F0 in the lea disp32 -> patched to (pluschar - delta) after assembly
PLACEHOLDER = 0xF0F0F0F0
caveB_src = f"""
    mov eax, dword ptr [ebp+0xc]
    test eax, eax
    jns _pos
    neg eax
    lea edx, [ebp-8]
    call 0x{INTTOSTR:X}
    call _delta
_delta:
    pop ecx
    lea edx, [ecx+0x{PLACEHOLDER:X}]
    mov ecx, dword ptr [ebp-8]
    lea eax, [ebp-8]
    call 0x{LSTRCAT3:X}
    jmp _done
_pos:
    lea edx, [ebp-8]
    mov eax, dword ptr [ebp+0xc]
    call 0x{INTTOSTR:X}
_done:
    jmp 0x{SHOWDMG_CONT:X}
"""
codeB, _ = ks.asm(caveB_src, CAVE_B); codeB = bytearray(codeB)
PLUSLIT = bytes.fromhex("ffffffff" "01000000" "2b" "00")   # AnsiString "+" (refcount -1, len 1)
# locate `call _delta` (E8 00000000) -> delta_off = index+5  (the `pop ecx`)
i_call = bytes(codeB).find(b"\xe8\x00\x00\x00\x00")
assert i_call != -1, "call _delta not found"
delta_off = i_call + 5
assert codeB[delta_off] == 0x59, "expected pop ecx at _delta"
literal_off = len(codeB)
pluschar_off = literal_off + 8                           # ptr points at the '+' byte
imm = pluschar_off - delta_off
ph = struct.pack("<I", PLACEHOLDER)
i_ph = bytes(codeB).find(b"\x8d\x91"+ph)                 # lea edx,[ecx+0xF0F0F0F0]
assert i_ph != -1, "lea placeholder not found"
codeB[i_ph+2:i_ph+6] = struct.pack("<i", imm)
caveB = bytes(codeB) + PLUSLIT

# ---- cave_mapfire_gate : make map-hex fire / Fire Barrier heal Living Flame holders too ---
# TArmy.TriggerFireDamage @0x55790110 pre-gates its loop with
#   if ((GetImmunityTypes & 1)==0) ExecuteDamageRole(...) else log(0,type9)
# so fire-immune holders never reach ExecuteDamageRole. This cave replaces that
# gate: non-immune -> damage path; fire-immune -> damage path ONLY for a holder
# (else original "immune" branch). ESI=unit, AL=immunity bits at entry.
TRIG_GATE   = 0x5579020C
TRIG_ORIG   = b"\xa8\x01\x75\x70\x66"                    # test al,1 ; jne 0x55790280 ; (66 = MOV AX prefix)
TRIG_ELSE   = 0x55790280                                 # original immune branch (log 0 / type 9)
TRIG_REJOIN = 0x55790228                                 # MOV EDI,EAX (after the ExecuteDamageRole call)
CAVE_C = (CAVE_B + len(caveB) + 0xF) & ~0xF
# ---------------------------------------------------------------------------------------------
# Map-fire ATTACK and DAMAGE.
#
# ⚠ THIS CAVE IS THE ONLY LIVE COPY OF THESE TWO NUMBERS -- and that fact defeated BOTH doubling
# passes (found 2026-08-26). `redir_trig` below overwrites TriggerFireDamage's immunity gate at
# TRIG_GATE with `jmp CAVE_C`, so the ORIGINAL body at 0x55790211..0x55790227 never executes.
# The 5% conversion doubled the attack at 0x5579021D (6->12) and the DAM/HP pass doubled the damage
# at 0x55790218 (3->6) -- both into that DEAD body. `build_damhpdouble.py` still reports 85/85
# at-target, a false all-clear, because these cave addresses are in neither manifest.
#
# Net effect while stale: DEFENCE doubled AND the to-hit slope halved, so an UNdoubled attack is a
# net LOSS rather than a halving (a DEF-5 unit went from ~65% burn chance to ~35%); combined with
# the stale damage, strategic map fire was running about 4x too weak. It also halved the
# Fire-feeds-Fire heal, because cave_fireheal reuses this caller's ECX/EDX verbatim to size "+N".
#
# ⚠ Do NOT "fix" this by restoring TRIG_ORIG to make the doubled body live again -- that reverts
# fire-heals-fire. Re-tune HERE, and keep PREV_* in step so verify-before-write still recognises
# the installed cave (CLAUDE.md's in-place cave rewrite rule).
MAPFIRE_DAM, MAPFIRE_ATK = 6, 12      # 2026-08-26: doubled from 3 / 6
PREV_MAPFIRE = [(3, 6)]               # every body this cave has legitimately held, oldest first

def _caveC_src(dam, atk, by_ability=False):
    ident = f"""
    mov eax, esi
    mov ecx, [eax]
    mov edx, {FIRE_AURA}
    call dword ptr [ecx+0x148]
    test al, al
    jnz _dmg
    mov eax, esi
    mov ecx, [eax]
    mov edx, {LIVING_FLAME}
    call dword ptr [ecx+0x148]
    test al, al
    jnz _dmg
""" if by_ability else f"""
    mov eax, [esi+0x40]
    test eax, eax
    jz _immune
    mov edx, eax
    mov eax, [eax+4]
    mov ecx, [eax]
    call dword ptr [ecx+0x84]
    cmp eax, {ID_ELEM}
    je _dmg
    cmp eax, {ID_SPRT}
    je _dmg
"""
    return f"""
    test al, 1
    jz _dmg
""" + ident + f"""
_immune:
    jmp 0x{TRIG_ELSE:X}
_dmg:
    mov eax, 1
    push eax
    mov ecx, {dam}
    mov edx, {atk}
    mov eax, esi
    call 0x{EXECDMGROLE:X}
    jmp 0x{TRIG_REJOIN:X}
"""

caveC_src = _caveC_src(MAPFIRE_DAM, MAPFIRE_ATK, IDENTITY_BY_ABILITY)
caveC, _ = ks.asm(caveC_src, CAVE_C); caveC = bytes(caveC)
# Bodies this cave may already hold, so a re-tune verifies instead of aborting: every earlier
# atk/dam pair with the index test, and the current pair with the other identity test. All are
# written as ONE run, padded with zeros (the bytes after the shorter body are zero on disk), and
# the run must stop short of the next owner's cave at 0x5580DB20.
_c_all = [bytes(ks.asm(_caveC_src(_d, _a, _b), CAVE_C)[0])
          for _d, _a in PREV_MAPFIRE + [(MAPFIRE_DAM, MAPFIRE_ATK)] for _b in (False, True)]
_c_run = max(len(b) for b in _c_all)
assert CAVE_C + _c_run <= 0x5580DB20, "cave_mapfire_gate would run into the cave at 0x5580DB20"
caveC_prior = [b + b"\x00" * (_c_run - len(b)) for b in _c_all if b != caveC]
caveC = caveC + b"\x00" * (_c_run - len(caveC))

# ---- redirects ----
redir_exec  = b"\xE9" + rel32(EXECDMGROLE, CAVE_A) + b"\x90"
redir_showd = b"\xE9" + rel32(SHOWDMG_INJ, CAVE_B) + b"\x90"*6
redir_trig  = b"\xE9" + rel32(TRIG_GATE, CAVE_C)         # exactly 5 bytes over test+jne+MOVprefix
assert len(redir_exec)==6 and len(redir_showd)==11 and len(redir_trig)==len(TRIG_ORIG)==5

dll_patches = [
    (CAVE_A,      [bytes(len(caveA))] + caveA_prior, caveA,
     "cave_fireheal (heal %s a to-hit roll)" % ("takes" if HEAL_TAKES_TOHIT_ROLL else "SKIPS")),
    (CAVE_B,      bytes(len(caveB)), caveB,       "cave_plusnum (+N display)"),
    (CAVE_C,      [bytes(len(caveC))] + caveC_prior, caveC,
     "cave_mapfire_gate (map fire heals Living Flame holders; atk %d dam %d)" % (MAPFIRE_ATK, MAPFIRE_DAM)),
    (EXECDMGROLE, EXEC_ORIG,         redir_exec,  "ExecuteDamageRole -> cave_fireheal"),
    (SHOWDMG_INJ, SHOWDMG_ORIG,      redir_showd, "ShowDamageIcon IntToStr -> cave_plusnum"),
    (TRIG_GATE,   TRIG_ORIG,         redir_trig,  "TriggerFireDamage immunity gate -> cave_mapfire_gate"),
]

# ======================= AoWz.exe ============================
EXE_BASE = 0x400000
EXE_SITE = 0x436BFF
EXE_ORIG = b"\x25\xff\x00\x00\x00"                        # and eax,0xff
EXE_NEW  = b"\x0f\xbe\xc0\x90\x90"                        # movsx eax,al ; nop ; nop
exe_patches = [(EXE_SITE, EXE_ORIG, EXE_NEW, "popup damage value -> signed (movsx)")]

# ============================ report ==========================================
print(f"cave_fireheal @ {CAVE_A:08X}  ({len(caveA)} B)")
print(f"cave_plusnum  @ {CAVE_B:08X}  ({len(caveB)} B, code {len(codeB)} + lit {len(PLUSLIT)}; "
      f'"+" @ {CAVE_B+pluschar_off:08X}, delta@{CAVE_B+delta_off:08X}, imm={imm})')
print(f"cave_mapfire_gate @ {CAVE_C:08X}  ({len(caveC)} B)")
print("--- cave_fireheal ---")
for ins in cs.disasm(caveA, CAVE_A):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<22} {ins.mnemonic} {ins.op_str}")
print("--- cave_plusnum ---")
for ins in cs.disasm(bytes(codeB), CAVE_B):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<22} {ins.mnemonic} {ins.op_str}")
print("--- cave_mapfire_gate ---")
for ins in cs.disasm(caveC, CAVE_C):
    print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<22} {ins.mnemonic} {ins.op_str}")

# ============================ apply / verify ==================================
APPLY = "--apply" in sys.argv
def process(path, base, patches, backup_suffix=".pre-firefeed"):
    data = bytearray(open(path,"rb").read())
    secs = load_sections(data); va2off = mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    # `orig` may be a single byte-run OR a list of accepted pre-states (the untouched original plus
    # every earlier body this cave has held). That is what lets a cave be RE-TUNED in place:
    # verify-before-write against either the installed bytes or the new ones, per CLAUDE.md.
    def accepted(orig): return list(orig) if isinstance(orig,(list,tuple)) else [orig]
    # idempotency: applied if every 'new' already present
    if all(rd(va,len(new))==new for va,_o,new,_d in patches):
        print(f"[= ] {os.path.basename(path)}: already applied"); return True
    ok=True; virgin=0
    for va,orig,new,desc in patches:
        alts=accepted(orig)
        assert all(len(a)==len(new) for a in alts), f"{va:08X}: accepted pre-state length mismatch"
        cur=rd(va,len(new))
        # alts[0] is the UNTOUCHED original by this table's convention; later entries are earlier
        # bodies of our own cave. Only alts[0] counts as pre-feature.
        if cur==alts[0]: virgin+=1
        if cur not in alts and cur!=new:
            ok=False; print(f"[!] {os.path.basename(path)} {va:08X} ({desc})\n"
                             f"     exp {alts[0].hex(' ')}\n     got {cur.hex(' ')}")
    if not ok:
        print(f"[x] {os.path.basename(path)}: originals mismatch -- not written"); return False
    if not APPLY:
        print(f"[dry] {os.path.basename(path)}: originals verified"); return True
    # ⚠ Snapshot ONLY from a file PROVED unpatched -- every site still on its untouched original.
    # "No backup file exists yet" accepts this script's own past output, and after the 2026-09-09
    # rename no AoWz.exe.pre-firefeed can exist, so that gate would have minted a lie.
    if virgin != len(patches):
        print(f"[bak] skipped for {os.path.basename(path)} -- {len(patches)-virgin} of "
              f"{len(patches)} site(s) already carry a version of this feature "
              f"(a .pre-* of a patched file is a lie)")
    else:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        bpath=os.path.join(BACKUP_DIR, os.path.basename(path)+backup_suffix)
        if not os.path.exists(bpath): shutil.copy2(path,bpath); print(f"[bak] {bpath}")
    for va,orig,new,desc in patches:
        o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {os.path.basename(path)} {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError:
        print(f"[x] {os.path.basename(path)} LOCKED -- close all AoW binaries and retry"); return False
    return True

targets = [(os.path.join(GAME,"AoWEPACK.dpl"), DLL_BASE, dll_patches)] + \
          [(os.path.join(GAME,e), EXE_BASE, exe_patches) for e in zigexe.EXES]
print()
allok=True
for path,base,patches in targets:
    if not os.path.exists(path): print(f"[skip] {path} not found"); continue
    allok &= process(path, base, patches)
if not APPLY:
    print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
elif allok:
    print("\n[done] Applied to all files. Revert: undo surgically -- a .pre-* restore is not a revert path.")
else:
    print("\n[!] One or more files not fully applied -- see above.")
