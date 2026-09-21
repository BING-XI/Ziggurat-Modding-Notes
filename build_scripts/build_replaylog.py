#!/usr/bin/env python3
r"""
AoW1 mod -- COMBAT LOG: re-display a battle when its REPLAY is re-opened from the Event History list.

PROBLEM. The combat log captures lines by tail-hooking the damage GENERATION funnels
(TDamageCA.Generate/GenerateEx). A replay never regenerates: `Generate`/`GenerateEx` are reachable only
through CA VMT slots +0x68/+0x6c, and AoW.exe imports no Generate/GenerateEx/Create*CA at all -- the exe
structurally cannot trigger generation. The replay merely plays back the combat actions stored by pointer
in the battle's TCombatLogbook. On top of that, cave_drain's `_m_none` path clears the memo AND discards
pending ring slots on the replay-closed transition, so the first viewing consumes the content and deletes
it. Result: a re-opened replay is blank.

FIX. One hook on the playback path, emitting one line per action as it plays.

  hook 5 B @0x55729D97  (`8b 53 08 8b c6` = mov edx,[ebx+8] ; mov eax,esi)  cont @0x55729D9C
  inside TDamageCA.Play @0x55729D78, on the single trigger-tick branch (guarded by `jne` @0x55729D95,
  so the body runs EXACTLY ONCE per action -- Play itself is called every frame until it returns 0).
  State there:  ESI = the CA,  EBX = TCombatViewer   (prologue `mov ebx,edx ; mov esi,eax` @0x55729D7B)
                [EBX+8] = the viewer's private playback TCombat,  [[EBX+8]+0xc] = its TCombatData.

WHY THIS HOOK. `Play` is dispatched only from TCombatViewer.Update; AoW.exe imports no CA methods and
AoWTCPCK imports neither GetCombatActions nor TCombatViewer/TCombatLogbook, so Play NEVER runs during a
live battle => zero double-logging. (TDamageCA.Execute was rejected: it runs in BOTH contexts, already
runs twice per action because DistributeCombatEvent auto-opens the replay after resolution, and
TCombatViewer.SetPosition re-Executes actions 0..pos-1 on EVERY slider drag -- a hook there would re-emit
the whole battle per seek.)

SPELLS -- SECOND ENTRY POINT (added 2026-07-25). Play is VMT slot +0x54, and **TCombatSpellCA
(VMT 0x557F3CC8) overrides it with 0x557F6A6C, which never calls base** (an old header here claimed
"the three Play overrides all call base" -- the survey missed this fourth one; when a hook's coverage
rests on "all the overrides call base", enumerate the VMT slot across every descendant). So spells never
reach HOOK; a second hook enters the same line builder from inside the override:

  hook2 6 B @0x557F6A72  (`83 7b 14 00 75 1f` = cmp dword [ebx+0x14],0 ; jne 0x557F6A97)
  Same register convention at that point (prologue `mov ebx,edx ; mov esi,eax` @0x557F6A6E:
  ESI = the spell CA, EBX = the viewer) and the same +0x0C/+0x0D/+0x0E/+0x10/+0x13 field layout.
  The cave replicates the displaced trigger-tick test itself: [ebx+0x14]==0 -> log + continue at
  0x557F6A78, else skip to 0x557F6A97. Runs EXACTLY once per action, like HOOK.
  ⚠ WHY NOT the doc's original 5-byte site @0x557F6A78 (`a1 e8 92 8e 55`): that instruction has a
  .reloc HIGHLOW entry at 0x557F6A79 (verified) -- the loader's rebase fixup would add the delta to
  our jmp rel32 operand and send it into the weeds. 0x557F6A72..77 is reloc-free, and a module-wide
  branch scan found NOTHING targeting the displaced bytes (verified 2026-07-25).
  TTurnUndeadSpellCA inherits the override (VMT+0x54 == 0x557F6A6C, verified) -> covered by the same
  hook, still once per action. TDamageCA descendants keep VMT+0x54 = 0x55729D78 -> no double logging.

ADDITIVE BY DESIGN. Brand-new cave in free space at 0x5580F180+; it does NOT touch the combat-log image
at 0x5580E440.. (whose build script expects a virgin zeroed zone and would therefore demand a
whole-file restore -- see that doc's corrected staging rule). So this cannot regress the
confirmed-working log.

NO ATK/DEF TAIL, EVER -- SETTLED 2026-07-25, do not "fix" this. Replay lines are
`Valkyrie hits Shadow for 5 damage +vertigo` / `Valkyrie casts Fire Bolt on Shadow for 5 damage`,
without the `(70%, 8 ATK vs 6 DEF)` part. Two independent reasons, both structural:
  (a) the attack is a transient stack argument to Generate -- absent from the CA and from
      TDamageCA.ReadWrite, so it simply does not survive the battle;
  (b) any defensive stat read at replay comes from the battle-START roster snapshot the logbook
      restores, so a Curse/Bless landing mid-battle makes the stat AND the derived hit% WRONG --
      right often enough to be trusted, which is worse than absent.
A spell-only partial tail (spell ATK is exact -- static TSpell+0x34 via the gated CA+0x18 -> GetSpell
path -- with only RES from the snapshot) was weighed and REJECTED for (b), and would need this cave
relocated anyway (24 B of the zone left). The LIVE log (build_combatlog_dll.py) prints the true
at-the-moment tail; combat-math verification belongs there. Everything else round-trips (incl. across
save/load):
  +0x0c bit0 retaliation · +0x0d attacker id · +0x0e target id · +0x10 rolled damage (0 = miss)
  +0x13 word effect landings
IDs -> objects via TCombatData.FindID @0x55728C68 (eax = data, edx = id -> eax = obj, 0 if absent),
exactly as vanilla does at 0x55729DA6..0x55729DAC. Names via strategic unit (combatObj+0x4c)
-> GetName at unit vmt+0xF8. ⚠ +0x4c is TCombatUnit-ONLY (TCombatWall reuses it for packed bytes), so
the fetch is @IsClass-gated BEFORE the read -- a NIL check alone caused the "Blt Error" crash on every
wall hit (see Blt_Error_Wall_Damage.md). Walls fall back to the literal "Wall", other classes to "?".
TCombat.Activate re-Initializes every object at replay, so the +0x4c link is live.

Ring protocol + guards copied verbatim from the log worker (slot = Delphi SHORTSTRING, length clamped to
SLOT_SZ-1 -- over-running that length byte is what caused the v3 heap corruption / "Runtime error 216").
PIC: one call/pop anchor (EDI); literals anchor-relative. Only the EXE's addresses are absolute, which is
correct -- AoW.exe is fixed-base. Idempotent, verify-before-write, free-space asserted, dry-run / --apply.
Snapshot goes to `<game dir>\backups\AoWEPACK.dpl.pre-replayspell`.

Revert: there is no --undo flag here. To take the feature OUT, restore the TWO hook sites
(HOOK/HOOK_ORIG 5 B, HOOK2/HOOK2_ORIG 6 B) -- that orphans the cave harmlessly. To RE-TUNE, just
re-run with --apply: the script rewrites its own cave in place. A `.pre-*` restore is NOT a revert
path: it is a whole-file copy that drops every feature applied since, and there is no snapshot layer
left at all (both stacks were purged, 2026-08-08 / 2026-09-09).
"""
import os, sys, shutil, struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never the game root (rule 2026-09-03)
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

def load_sections(data):
    e=struct.unpack_from("<I",data,0x3C)[0]; n=struct.unpack_from("<H",data,e+6)[0]
    op=struct.unpack_from("<H",data,e+20)[0]; s=e+24+op; secs=[]
    for i in range(n):
        vs,va,rs,raw=struct.unpack_from("<IIII",data,s+8); secs.append((va,vs,raw,rs)); s+=40
    return secs
def mkva2off(base):
    def f(secs,va):
        rva=va-base
        for va0,vs,raw,rs in secs:
            if va0<=rva<va0+max(vs,rs): return raw+(rva-va0)
        raise ValueError(hex(va))
    return f
def rel32(src,dst): return struct.pack("<i",dst-(src+5))

DLL_BASE = 0x55700000
CAVE     = 0x5580F180          # free region, starting after cave_abinherent (ends 0x5580F173)
CAVE_LIMIT = 0x5580F600        # self-imposed ceiling; the assert below keeps us inside it.
                               # ⚠ The old note here said "free to 0x55812000". That is NO LONGER TRUE:
                               # build_combatlog_dll.py RELOCATED its cave to 0x55811000 (2026-07-22)
                               # and it is now ~3 KB. Real headroom is 0x5580F180..0x55811000. Do not
                               # raise CAVE_LIMIT past 0x55811000 without re-checking that script.

HOOK     = 0x55729D97
HOOK_ORIG= bytes.fromhex("8b53088bc6")     # mov edx,[ebx+8] ; mov eax,esi  (computed, never read back)
HOOK_CONT= 0x55729D9C

# second entry: TCombatSpellCA.Play override (never calls base -- see the header)
HOOK2     = 0x557F6A72
HOOK2_ORIG= bytes.fromhex("837b1400751f") # cmp dword [ebx+0x14],0 ; jne 0x557F6A97  (reloc-free)
HOOK2_CONT= 0x557F6A78                    # trigger-tick fall-through (the once-per-action block)
HOOK2_SKIP= 0x557F6A97                    # the displaced jne's target (every other tick)

FINDID   = 0x55728C68          # eax = TCombatData, edx = id -> eax = combat object (0 if absent)
GETNAME_V= 0xF8                # strategic-unit VMT slot: GetName(eax=unit, edx=@out LStr)
IS_CLASS = 0x557010C0          # System.@IsClass thunk: EAX=obj, EDX=classref VALUE -> AL
TCOMBATUNIT_VMT = 0x55715A94   # TCombatUnit VMT base (== [0x55715A54]); reach via the cave's delta
TCOMBATSPELLCA_VMT = 0x557F3CC8  # TCombatSpellCA VMT base. It overrides Play (VMT+0x54 -> 0x557F6A6C,
                               # never calls base), so spells reach the builder via HOOK2, not HOOK.
                               # (It does NOT override Generate/GenerateEx, which is why
                               # build_combatlog_dll.py's live-battle hook does see them.)
                               # TTurnUndeadSpellCA descends from it (covered free); the Turn Undead
                               # ABILITY CA does not descend from it (correctly excluded).
AOWHSSET   = 0x558FA044        # AoWE.AoWHSSet global (POINTER cell); TSpellControl at +0x84
SPELLCTRL_OFF = 0x84
GETSPELL   = 0x55779AC8        # GetSpell(eax=ctrl, edx=id) -> eax=TSpell (0 if id >= count)
                               # ⚠ RAISES a Delphi range error on a NEGATIVE id -- never pass one.
SPELL_NAME = 0x08              # TSpell+0x08 = spell name, a plain LStr VALUE
TCOMBATWALL_VMT = 0x55715C40   # TCombatWall VMT base; walls have no strategic unit so they can never
                               # reach GetName -- they get the literal "Wall" rather than "?"
INTTOSTR = 0x5570158C          # eax=int, edx=@out LStr
LSTRLASG = 0x55701158          # eax=@dest, edx=src value
LSTRCAT  = 0x55701188          # eax=@dest, edx=src value -> dest := dest+src
LSTRARRCLR=0x55701148          # eax=@first, edx=count

# exe-side globals (fixed base 0x400000; never rebases).
# The ring MAGIC still gates "is this our patched game exe (not DevEd)"; we no longer WRITE the ring.
# WHY NOT THE RING: measured 2026-07-21 (live_ui.py) -- the hook fires and fills the ring during a
# replay (wrIdx climbed 48->67, slots held our marker), but cave_drain pumps off MapWindowUpdate, which
# does NOT tick while the fast-combat replay window animates, so rdIdx froze and nothing reached the memo
# (then close cleared it). TDamageCA.Play runs ONLY during a replay and on the main thread, so we bypass
# the ring and Add the line straight to our window's memo -- the same call cave_drain makes, self-
# refreshing, needing no pump.  inst 0x45B2E0 -> memo +0x48 -> TStringList +0x118 -> Add [vmt+0x34].
RING=0x60D000; MAGIC=0x31474C43   # 'CLG1'
GVAR_INSTANCE=0x45B2E0            # our TCombatLogWin instance (exe global)
MEMO_OFF=0x48; FSTRINGS_OFF=0x118; ADD_V=0x34
SLOT_SZ=128; SLOTS_N=64           # retained only for the wire-format cross-check below
def _check_wire():
    """The ring is a wire format shared with the two combat-log scripts. A silent mismatch reads every
    line from the middle of an earlier one (garbage shortstring length -> heap corruption). Hard-fail."""
    import re
    here=os.path.dirname(os.path.abspath(__file__))
    for fn,pat,exp in (("build_combatlog_exe.py", r"RING_SLOTS\s*=\s*(\d+);\s*SLOT_SZ\s*=\s*(\d+)", (SLOTS_N,SLOT_SZ)),
                       ("build_combatlog_dll.py", r"SLOT_SZ\s*=\s*(\d+);\s*SLOTS_N\s*=\s*(\d+)",   (SLOT_SZ,SLOTS_N))):
        try: t=open(os.path.join(here,fn)).read()
        except OSError: continue
        m=re.search(pat,t); assert m, f"cannot find the ring constants in {fn}"
        got=(int(m.group(1)),int(m.group(2)))
        assert got==exp, f"WIRE-FORMAT MISMATCH vs {fn}: {got} != {exp}. All three scripts must agree."
_check_wire()

def lstr_const(s):
    """Delphi AnsiString literal: refcount -1 (never freed/written by the VCL) + length + chars + NUL."""
    b=s.encode("latin1"); return struct.pack("<ii",-1,len(b))+b+b"\x00"

# effect-landing bits of word[CA+0x13] -> suffix (same mapping as build_combatlog_dll.py's efx table)
EFFECTS=[(0," +burning"),(1," +frozen"),(2," +stunned"),(4," +poisoned"),(5," +cursed"),(6," +vertigo")]
LITS={"DIAG":"[replay tick]", "Q":"?", "WALL":"Wall",
      "CASTS":" casts ", "ONTGT":" on ", "BUTMISS":" but misses ", "HITS":" hits ", "HITSB":" hits back at ",
      "MISS":" misses ", "MISSB":" misses back at ", "FOR":" for ", "DMG":" damage"}
for _b,_s in EFFECTS: LITS[f"E{_b}"]=_s
lit_off={}; pool=b""
for _n,_s in LITS.items():
    lit_off[_n]=len(pool); pool+=lstr_const(_s)

DIAG="--diag" in sys.argv
def emit(lit_va):
    """Assemble the cave. `anchor` (the call/pop site) is resolved by a two-pass in build()."""
    anchor=None
    def body(anchor):
        DIAG_SRC=""
        def d(n):
            """Literal VALUE ptr as an anchor-relative displacement, rendered signed so keystone can
            parse it (literals sit after the code, so this is positive in practice)."""
            v=lit_va+lit_off[n]+8-anchor
            return f"+ 0x{v:X}" if v>=0 else f"- 0x{-v:X}"
        if DIAG:
            # --diag: emit a fixed marker and commit, skipping FindID / GetName / damage / effects.
            # Isolates "hook fires + guards pass + ring & drain work" from "the line is built right".
            DIAG_SRC = (f"""
            lea  eax, [ebp-0x04]
            lea  edx, [edi {d('DIAG')}]
            call 0x{LSTRLASG:X}
            jmp  _commit
            """)
        def cu():                                 # TCombatUnit classref, EDI-anchor-relative
            o=TCOMBATUNIT_VMT-anchor
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        def cw():                                 # TCombatWall classref, same base
            o=TCOMBATWALL_VMT-anchor
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        def csc():                                # TCombatSpellCA classref, same base
            o=TCOMBATSPELLCA_VMT-anchor
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        def g(addr):                              # a module GLOBAL's cell, anchor-relative
            o=addr-anchor
            return f"[edi + 0x{o:X}]" if o>=0 else f"[edi - 0x{-o:X}]"
        # name fetch: obj -> strategic unit (+0x4c) -> GetName(vmt+0xF8) into `slot`.
        #
        # THE TYPE GATE IS LOAD-BEARING -- do not "simplify" it back to a NIL check.
        # +0x4C is a TCombatUnit-only field. TCombatWall has a smaller instance and reuses that
        # offset for PACKED BYTES, so on a wall the read yields nonzero garbage, sails through the
        # NIL test, and `mov ecx,[eax]` dereferences it -> access violation. That AV is swallowed by
        # TFastCombatForm.FCWinDrawSurface's catch-all (AoW.exe 0x435F26), which discards the real
        # exception and re-raises a generic one, which aowInt then reports as the fixed label
        # "Blt Error" with caption "Error - FCWin". Hence: every hit on a combat wall popped an error
        # dialog that named neither the fault nor the component. Diagnosed 2026-07-22 by probing both
        # handlers (build_bltprobe.py / build_bltprobe_exe.py); see Raze_Dialog_Freeze_Fix.md.
        #
        # build_combatlog_dll.py had the identical defect and was fixed the same way; this cave is a
        # SEPARATE feature with its own copy, which is why gating the combat log's seven hooks off
        # never made the symptom go away and wrongly exonerated it.
        def name(obj_off, slot):
            return f"""
            mov  eax, [ebp-0x{obj_off:X}]
            test eax, eax
            jz   _q{slot:X}
            lea  edx, {cu()}
            call 0x{IS_CLASS:X}
            test al, al
            jz   _q{slot:X}
            mov  eax, [ebp-0x{obj_off:X}]
            mov  eax, [eax+0x4C]
            test eax, eax
            jz   _q{slot:X}
            lea  edx, [ebp-0x{slot:X}]
            mov  ecx, [eax]
            call dword ptr [ecx+0x{GETNAME_V:X}]
            jmp  _n{slot:X}
        _q{slot:X}:
            mov  eax, [ebp-0x{obj_off:X}]
            test eax, eax
            jz   _qq{slot:X}
            lea  edx, {cw()}
            call 0x{IS_CLASS:X}
            test al, al
            jz   _qq{slot:X}
            lea  eax, [ebp-0x{slot:X}]
            lea  edx, [edi {d('WALL')}]
            call 0x{LSTRLASG:X}
            jmp  _n{slot:X}
        _qq{slot:X}:
            lea  eax, [ebp-0x{slot:X}]
            lea  edx, [edi {d('Q')}]
            call 0x{LSTRLASG:X}
        _n{slot:X}:
        """
        efx=""
        for b,_ in EFFECTS:
            efx+=f"""
            test word ptr [esi+0x13], 0x{1<<b:X}
            jz   _x{b}
            lea  eax, [ebp-0x04]
            lea  edx, [edi {d(f'E{b}')}]
            call 0x{LSTRCAT:X}
        _x{b}:
        """
        return f"""
        _entry1:                          /* HOOK lands at CAVE, as it always has */
            call _worker
            mov  edx, [ebx+8]             /* the displaced original pair, then back to base Play */
            mov  eax, esi
            jmp  0x{HOOK_CONT:X}
        _entry2:                          /* HOOK2: spell-CA Play override */
            cmp  dword ptr [ebx+0x14], 0  /* the displaced trigger-tick test */
            jne  _e2skip
            call _worker
            jmp  0x{HOOK2_CONT:X}
        _e2skip:
            jmp  0x{HOOK2_SKIP:X}
        _worker:
            pushad
            push ebp
            mov  ebp, esp
            sub  esp, 0x30
            xor  eax, eax
            mov  [ebp-0x04], eax
            mov  [ebp-0x08], eax
            mov  [ebp-0x0C], eax
            mov  [ebp-0x10], eax
            mov  [ebp-0x28], eax          /* spell-name LStr; cleared separately at _clean */
            mov  [ebp-0x14], esi
            mov  [ebp-0x18], ebx
            call _anch
        _anch:
            pop  edi

            mov  eax, [0x40003C]
            cmp  dword ptr [eax+0x400050], 0x20E000
            jb   _done
            cmp  dword ptr [0x{RING:X}], 0x{MAGIC:X}
            jne  _done
            {DIAG_SRC}
            mov  eax, [ebx+8]
            mov  eax, [eax+0x0C]
            mov  [ebp-0x1C], eax
            movzx edx, byte ptr [esi+0x0D]
            call 0x{FINDID:X}
            mov  [ebp-0x20], eax
            mov  eax, [ebp-0x1C]
            movzx edx, byte ptr [esi+0x0E]
            call 0x{FINDID:X}
            mov  [ebp-0x24], eax
            {name(0x20, 0x08)}
            {name(0x24, 0x0C)}

            lea  eax, [ebp-0x04]
            mov  edx, [ebp-0x08]
            call 0x{LSTRLASG:X}

            cmp  byte ptr [esi+0x10], 0
            je   _m
            test byte ptr [esi+0x0C], 1
            jz   _hf
            lea  edx, [edi {d('HITSB')}]
            jmp  _vg
        _hf:
            lea  edx, [edi {d('HITS')}]
            jmp  _vg
        _m:
            test byte ptr [esi+0x0C], 1
            jz   _mf
            lea  edx, [edi {d('MISSB')}]
            jmp  _vg
        _mf:
            lea  edx, [edi {d('MISS')}]
        _vg:
            /* Spell? -> " casts <Spell> on " (hit) / " but misses " (miss) instead of the melee
               verb. ESI is the CA here. NB CA+0x18 is the spell id on TCombatSpellCA ONLY --
               TStrikeCA reuses that offset for strike flags, and GetSpell RAISES on a negative id,
               inside the combat pump. Class-gate first; every step falls back to the plain verb. */
            mov  [ebp-0x2C], edx
            mov  eax, esi
            lea  edx, {csc()}
            call 0x{IS_CLASS:X}
            test al, al
            jz   _vp
            mov  eax, [esi+0x18]
            test eax, eax
            js   _vp
            mov  edx, eax
            mov  eax, {g(AOWHSSET)}
            test eax, eax
            jz   _vp
            mov  eax, [eax+0x{SPELLCTRL_OFF:X}]
            test eax, eax
            jz   _vp
            call 0x{GETSPELL:X}
            test eax, eax
            jz   _vp
            mov  edx, [eax+0x{SPELL_NAME:X}]
            test edx, edx
            jz   _vp
            lea  eax, [ebp-0x28]
            call 0x{LSTRLASG:X}
            lea  eax, [ebp-0x04]
            lea  edx, [edi {d('CASTS')}]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x04]
            mov  edx, [ebp-0x28]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x04]
            cmp  byte ptr [esi+0x10], 0
            je   _vcm
            lea  edx, [edi {d('ONTGT')}]
            jmp  _vcc
        _vcm:
            lea  edx, [edi {d('BUTMISS')}]
        _vcc:
            call 0x{LSTRCAT:X}
            jmp  _vt
        _vp:
            lea  eax, [ebp-0x04]
            mov  edx, [ebp-0x2C]
            call 0x{LSTRCAT:X}
        _vt:
            lea  eax, [ebp-0x04]
            mov  edx, [ebp-0x0C]
            call 0x{LSTRCAT:X}

            movzx eax, byte ptr [esi+0x10]
            test eax, eax
            jz   _commit
            lea  eax, [ebp-0x04]
            lea  edx, [edi {d('FOR')}]
            call 0x{LSTRCAT:X}
            movzx eax, byte ptr [esi+0x10]
            lea  edx, [ebp-0x10]
            call 0x{INTTOSTR:X}
            lea  eax, [ebp-0x04]
            mov  edx, [ebp-0x10]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x04]
            lea  edx, [edi {d('DMG')}]
            call 0x{LSTRCAT:X}
            {efx}
        _commit:
            mov  eax, [ebp-0x04]
            test eax, eax
            jz   _clean
            mov  eax, [0x{GVAR_INSTANCE:X}]
            test eax, eax
            jz   _clean
            mov  eax, [eax+0x{MEMO_OFF:X}]
            test eax, eax
            jz   _clean
            mov  eax, [eax+0x{FSTRINGS_OFF:X}]
            test eax, eax
            jz   _clean
            mov  edx, [ebp-0x04]
            mov  ecx, [eax]
            call dword ptr [ecx+0x{ADD_V:X}]
        _clean:
            lea  eax, [ebp-0x10]
            mov  edx, 4
            call 0x{LSTRARRCLR:X}
            lea  eax, [ebp-0x28]
            mov  edx, 1
            call 0x{LSTRARRCLR:X}
        _done:
            mov  esp, ebp
            pop  ebp
            popad
            ret                           /* back to whichever entry stub called us */
        """
    # two-pass: the anchor sits a fixed distance into the body, but literal displacements can change
    # instruction encodings, so size once with a provisional anchor then re-emit and assert stability.
    # Anchor located by the full `call $+5 ; pop edi` pattern, NOT a bare 0x5f -- with the entry stubs
    # ahead of the worker, a 0x5f byte can now legally occur inside a jmp rel32 operand.
    ANCH=b"\xe8\x00\x00\x00\x00\x5f"
    a0=CAVE+64
    b0=bytes(ks.asm(body(a0),CAVE)[0])
    off=b0.find(ANCH)
    assert off>=0 and b0.find(ANCH,off+1)<0, "call/pop anchor pattern not found or not unique"
    anchor=CAVE+off+5                          # VA of the `pop edi`
    out=bytes(ks.asm(body(anchor),CAVE)[0])
    assert len(out)==len(b0), ("cave size unstable between passes",len(b0),len(out))
    assert out.find(ANCH)==off, "anchor moved between passes"
    return out,anchor

APPLY="--apply" in sys.argv
# backup suffix is PER GENERATION: `.pre-replaylog` named the pre-spell build's snapshot, so this
# generation uses its own name rather than silently reusing that one.
def build(path, suffix=".pre-replayspell"):
    data=bytearray(open(path,"rb").read()); secs=load_sections(data); va2off=mkva2off(DLL_BASE)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])

    code,anchor=emit(CAVE+0x300)   # size pass: provisional forward lit_va keeps disp32 encodings
    lit_va=(CAVE+len(code)+15)&~15
    code,anchor=emit(lit_va)
    lit_va2=(CAVE+len(code)+15)&~15
    assert lit_va2==lit_va, ("literal pool moved between passes",hex(lit_va),hex(lit_va2))
    img=code+b"\x00"*(lit_va-CAVE-len(code))+pool

    print(f"\n[cave_replaylog] @{CAVE:08X}  code {len(code)} B  literals @{lit_va:08X} ({len(pool)} B)"
          f"  total {len(img)} B  (room {CAVE_LIMIT-CAVE} B)   anchor={anchor:08X}")
    for ins in cs.disasm(code, CAVE):
        print(f"  {ins.address:08X} {ins.bytes.hex(' '):<20}{ins.mnemonic} {ins.op_str}")

    if CAVE+len(img) > CAVE_LIMIT:
        print(f"[x] cave overflows its zone ({len(img)} B > {CAVE_LIMIT-CAVE} B)"); return False

    # _entry2 sits right after _entry1's fixed 15 bytes (call 5 + mov edx,[ebx+8] 3 + mov eax,esi 2 +
    # jmp 5); locate it by its unique first instruction and cross-check against that arithmetic.
    e2off=code.find(bytes.fromhex("837b1400"))          # cmp dword [ebx+0x14],0 -- only in _entry2
    assert e2off==15 and code.find(bytes.fromhex("837b1400"),e2off+1)<0, \
        ("cannot locate _entry2 in the assembled cave", e2off)
    ENTRY2=CAVE+e2off

    hook_new =b"\xE9"+rel32(HOOK,CAVE)
    hook2_new=b"\xE9"+rel32(HOOK2,ENTRY2)+b"\x90"       # 6 displaced bytes -> jmp rel32 + 1 nop
    patches=[(CAVE, bytes(len(img)), img, "cave_replaylog"),
             (HOOK,  HOOK_ORIG,  hook_new,  f"TDamageCA.Play trigger tick {HOOK:08X} -> cave"),
             (HOOK2, HOOK2_ORIG, hook2_new, f"TCombatSpellCA.Play trigger test {HOOK2:08X} -> _entry2")]

    # Zone ownership. The hook already pointing at CAVE proves a previous build of THIS script owns the
    # zone, so overwrite it in place -- never demand a revert (a whole-file restore of AoWEPACK.dpl
    # would drop every other feature on it). Only require virgin zeros when we do NOT already own it,
    # and always assert we stay inside the ceiling.
    cur=rd(HOOK,5)
    owned = (cur == b"\xE9"+rel32(HOOK,CAVE))
    live=rd(CAVE,len(img))
    if not owned and live!=img and any(b!=0 for b in live):
        print(f"[x] cave zone {CAVE:08X} is not free and we do not own it:\n     {live[:32].hex(' ')}")
        return False
    if owned and live!=img:
        print(f"[i] rewriting our previously-installed cave in place ({len(img)} B)")
    if cur!=HOOK_ORIG and cur!=hook_new:
        print(f"[x] hook site {HOOK:08X} unexpected\n     exp {HOOK_ORIG.hex(' ')}\n     got {cur.hex(' ')}")
        return False
    cur2=rd(HOOK2,6)
    if cur2!=HOOK2_ORIG and cur2!=hook2_new:
        print(f"[x] hook2 site {HOOK2:08X} unexpected\n     exp {HOOK2_ORIG.hex(' ')}\n     got {cur2.hex(' ')}")
        return False
    if all(rd(va,len(new))==new for va,_o,new,_d in patches):
        print("[= ] already applied"); return True
    if not APPLY:
        print("[dry] cave assembles and fits, zone free, hook site verified"); return True
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bp=os.path.join(BACKUP_DIR, os.path.basename(path)+suffix)
    if not os.path.exists(bp): shutil.copy2(path,bp); print(f"[bak] {bp}")
    for va,_o,new,desc in patches:
        o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError: print("[x] LOCKED -- close AoW binaries"); return False
    return True

ok=build(os.path.join(GAME,"AoWEPACK.dpl"))
# NO "revert = copy the backup" instruction here, deliberately: a `.pre-*` snapshot is a whole-file
# copy, so restoring one drops every feature applied to AoWEPACK.dpl since it was taken. This script
# rewrites its own cave in place, so re-running it is always the correct way to change or re-tune the
# feature.
# To take the feature OUT, restore the TWO hook sites (HOOK/HOOK_ORIG 5 B and HOOK2/HOOK2_ORIG 6 B
# above) -- that orphans the cave harmlessly and touches nothing else.
print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first." if not APPLY
      else ("\n[done] Applied. To re-tune, just re-run this script (it rewrites the cave in place).\n"
            f"        To disable: restore {HOOK_ORIG.hex(' ')} at {HOOK:08X}\n"
            f"                    and     {HOOK2_ORIG.hex(' ')} at {HOOK2:08X}."
            if ok else "\n[!] not applied"))
