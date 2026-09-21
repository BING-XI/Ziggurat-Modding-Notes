#!/usr/bin/env python3
r"""
PARTY PLACER -> RANDOM ARMY GENERATOR  --  AoWDevEd.exe only.  (Stage 1)

WHAT IT DOES
  The editor's Party tool used to drop an EMPTY stack that the mapmaker then filled
  unit-by-unit in the Army Properties dialog. With this patch a freshly placed party
  arrives pre-filled with a random stack:

      Weak    3-4 x level 1
      Medium  4 x level 1, 2 x level 2
      Large   4 x level 1, 3 x level 2, 1 x level 3

  drawn only from the races allowed by a bitmask. Both knobs live in .pty globals
  (g_strength / g_racemask); Stage 2 will add the configuration dialog on the Party
  button that writes them. Defaults: Medium, all races.

  Only EMPTY, newly created parties are filled -- clicking an existing stack with the
  Party tool still just opens it. The Army Properties dialog still opens afterwards, so
  the owner can be set and the roll tweaked.

HOW  (full derivation in Modding Resources/Party_Random_Generator.md)
  * Hook: TArmyPlaceControl.MsgProc @0x41A35C is the editor class that actually creates
    and places the TArmyHS. The 8 bytes at 0x41A414
        85 F6 74 21 6A 00 6A 00   test esi,esi / je 0x41A439 / push 0 / push 0
    become `jmp cave` + 3 nops; the cave re-implements those four instructions exactly and,
    when esi is non-nil and its TArmy is empty, calls the generator first.
    TArmyHS+0x1C = the TArmy.
  * All engine primitives are reached WITHOUT new imports, via the runtime rebase delta
        dll_delta = [0x432898] - 0x558FA044
    ([0x432898] is the exe's IAT slot for the imported AoWEPACK *variable* AoWE.AoWHSSet,
    so it holds that variable's runtime address; 0x558FA044 is its preferred VA). Adding
    dll_delta to any AoWEPACK preferred VA yields its runtime address.
  * Generator: for each (level,count) of the chosen strength, walk the unit resource list
    ([[[0x432898]] + 0x5C], count at [[list+8]+8]) re-pointing ONE scratch TUnit at each
    resource and keeping the indices whose VMT+0xA0 GetUnitLevel matches and whose VMT+0xA4
    GetRace is in the mask; then `count` times create a TUnit for a random candidate and
    TArmy.CanAddUnit(+0xA4)/AddUnit(+0xAC)/Release(+0x2C) -- the same create/add/release
    sequence AoWE.FillWithRandomUnits uses.
    NOTE the engine's own FillWithRandomUnits is budget-driven and its set parameter is a
    unit-TYPE set, not a race set, which is why selection is done here instead.

CONVENTIONS: dry-run by default (prints a capstone disassembly), --apply to write;
idempotent; verify-before-write (aborts unless the hook bytes are exactly vanilla or
exactly ours); auto-backup to `<game dir>\backups\AoWDevEd.exe.pre-partyrnd`. Editor-only.
Close AoWDevEd.exe first. Revert: there is no --undo here, and copying the snapshot back is NOT a
revert path -- it is a WHOLE-FILE copy, so it drops every other AoWDevEd feature applied since.
Undo surgically: restore the 8 hook bytes at HOOK_VA, the 5 at ARMYBTN_VA, and zero .pty.

Needs: pip install keystone-engine capstone
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import party_dialog as PD

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXE = "AoWDevEd.exe"
BACKUP_SUFFIX = ".pre-partyrnd"
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never beside the target (rule 2026-09-03)
SECT_NAME = b".pty\0\0\0\0"

# ---- hook site -------------------------------------------------------------------
HOOK_VA    = 0x41A414
ORIG_HOOK  = bytes([0x85, 0xF6, 0x74, 0x21, 0x6A, 0x00, 0x6A, 0x00])
RESUME_VA  = 0x41A41C          # 'mov eax,esi' -- after the two push 0
SKIP_VA    = 0x41A439          # the 'not placed' path

# ---- engine addresses (AoWEPACK preferred VAs; + dll_delta at runtime) ------------
IAT_AOWHSSET   = 0x432898      # exe IAT slot -> runtime address of AoWE.AoWHSSet
AOWHSSET_PREF  = 0x558FA044    # its preferred VA
TUNIT_CLASSREF = 0x55710C6C    # global holding the TUnit class reference
FN_UNIT_CREATE = 0x5577EB28    # TAbstractUnit.Create   EAX=classref DL=1 ECX=0
FN_SET_URES    = 0x55782BE4    # TUnit.SetUnitResource  EAX=unit EDX=res
FN_GET_URES    = 0x55785050    # TUnitResourceList.GetUnitResource EAX=list EDX=idx
FN_RANDINT     = 0x55701080    # System._RandInt        EAX=range -> EAX
FN_RANDOMIZE   = 0x55701030    # System.Randomize

HSSET_URESLIST = 0x5C          # HSSet -> TUnitResourceList
ARMYHS_ARMY    = 0x1C          # TArmyHS -> TArmy
ARMY_BEHAVIOR  = 0x24          # TArmy: authored behaviour byte (what the editor combo writes)

# TMainForm.ArmyBtnClick -- the Party tool button. First 5 bytes are exactly
#   push ebx / mov ebx,eax / mov eax,edx   -> replaced by a jmp to armybtn_hook.
ARMYBTN_VA   = 0x42B69C
ARMYBTN_ORIG = bytes([0x53, 0x8B, 0xD8, 0x8B, 0xC2])

LAYOUT = PD.build_layout()
NCTRL  = len(LAYOUT)

V_RELEASE   = 0x2C             # TUnit  VMT: TAbstractUnit.Release
V_GETLEVEL  = 0xA0             # TUnit  VMT: TUnit.GetUnitLevel
V_GETRACE   = 0xA4             # TUnit  VMT: TUnit.GetRace
V_COUNT     = 0x54             # TArmy  VMT: GetCount
V_CANADD    = 0xA4             # TArmy  VMT: TArmy.CanAddUnit
V_ADDUNIT   = 0xAC             # TArmy  VMT: TArmy.AddUnit

MAX_CAND = 512                 # candidate index slots (word each)

# strength -> up to three (level, count) pairs; count 0 ends the list
# (level, base count, random span) per tier; actual count = base + RandInt(span), so span 1
# means "exactly base" and span N spreads over base .. base+N-1. A zero count ends the list.
STRENGTH_TABLE = [
    [(1, 3, 2), (0, 0, 0), (0, 0, 0)],     # Weak    3-4 x lvl1
    [(1, 3, 3), (2, 2, 1), (0, 0, 0)],     # Medium  3-5 x lvl1, 2 x lvl2
    [(1, 4, 1), (2, 2, 2), (3, 1, 1)],     # Large   4 x lvl1, 2-3 x lvl2, 1 x lvl3
]
DEFAULT_STRENGTH = 1
# No races ticked by default: until the mapmaker opts in, the Party tool behaves exactly as it
# always did (an empty stack to fill by hand). fill_army early-outs on a zero mask.
DEFAULT_RACEMASK = 0x00000000


def asm_src(ks, src, va):
    """keystone (LLVM) has no ';' comments in Intel mode -- strip them first."""
    clean = "\n".join(ln.split(";", 1)[0] for ln in src.splitlines())
    code, _ = ks.asm(clean, va)
    return bytes(code)


def gen_source(base_va):
    """Lay out .pty and return (asm source, symbol offsets). Data first, code after."""
    # ---- data block (offsets from base_va) ----
    off = 0
    g_strength = base_va + off; off += 4
    g_racemask = base_va + off; off += 4
    g_seeded   = base_va + off; off += 4
    g_ncand    = base_va + off; off += 4
    g_behavior = base_va + off; off += 4
    g_spec     = base_va + off; off += 3 * 3 * 3      # 3 strengths x 3 entries x (lvl,base,span)
    off = (off + 3) & ~3
    g_ctrls    = base_va + off; off += NCTRL * 4      # runtime dialog control pointers
    g_cand     = base_va + off; off += MAX_CAND * 2
    off = (off + 3) & ~3

    dlg_data_off = off
    dlg_blob, dlg_syms, off = PD.emit_data(LAYOUT, base_va, off)
    off = (off + 15) & ~15
    code_va    = base_va + off

    src = f"""
; ============================= generator =============================
;  EAX = TArmy.  Preserves everything, balances the stack.
fill_army:
        push ebp
        mov  ebp, esp
        sub  esp, 0x2C
        push ebx
        push esi
        push edi
        mov  dword ptr [ebp - 0x04], eax        ; army

        cmp  dword ptr [{g_racemask:#x}], 0     ; no races chosen -> leave the party empty,
        jz   fa_done                            ; i.e. exactly the vanilla Party tool

        mov  eax, dword ptr [{IAT_AOWHSSET:#x}]
        sub  eax, {AOWHSSET_PREF:#x}
        mov  dword ptr [ebp - 0x08], eax        ; dll_delta

        mov  eax, dword ptr [{IAT_AOWHSSET:#x}]
        mov  eax, dword ptr [eax]               ; the HSSet object
        test eax, eax
        jz   fa_done
        mov  eax, dword ptr [eax + {HSSET_URESLIST:#x}]
        mov  dword ptr [ebp - 0x0C], eax        ; unit resource list
        test eax, eax
        jz   fa_done

        mov  ecx, dword ptr [eax + 8]           ; engine list: count = [[list+8]+8]
        test ecx, ecx
        jz   fa_done
        mov  ecx, dword ptr [ecx + 8]
        mov  dword ptr [ebp - 0x10], ecx        ; resource count
        cmp  ecx, 0
        jle  fa_done

        mov  eax, dword ptr [ebp - 0x08]        ; seed the RNG once per session
        cmp  dword ptr [{g_seeded:#x}], 0
        jnz  fa_noseed
        mov  dword ptr [{g_seeded:#x}], 1
        mov  esi, eax
        add  esi, {FN_RANDOMIZE:#x}
        call esi
    fa_noseed:

        mov  eax, dword ptr [ebp - 0x08]        ; scratch TUnit
        mov  eax, dword ptr [eax + {TUNIT_CLASSREF:#x}]
        test eax, eax
        jz   fa_done
        xor  ecx, ecx
        mov  dl, 1
        mov  esi, dword ptr [ebp - 0x08]
        add  esi, {FN_UNIT_CREATE:#x}
        call esi
        mov  dword ptr [ebp - 0x14], eax        ; scratch
        test eax, eax
        jz   fa_done

        mov  eax, dword ptr [{g_strength:#x}]   ; clamp strength to 0..2
        cmp  eax, 2
        jbe  fa_str_ok
        mov  eax, 1
    fa_str_ok:
        lea  esi, [eax + eax * 2]               ; strength * 9 bytes (3 entries x 3 bytes)
        lea  esi, [esi + esi * 2]
        add  esi, {g_spec:#x}
        mov  dword ptr [ebp - 0x18], esi        ; spec cursor
        mov  dword ptr [ebp - 0x1C], 0          ; pair index

    fa_pair:
        mov  esi, dword ptr [ebp - 0x18]
        movzx eax, byte ptr [esi]               ; level
        movzx ecx, byte ptr [esi + 1]           ; base count
        test ecx, ecx
        jz   fa_pairs_done
        mov  dword ptr [ebp - 0x20], eax        ; wanted level
        mov  dword ptr [ebp - 0x24], ecx        ; wanted count

        movzx eax, byte ptr [esi + 2]           ; random span: count += RandInt(span)
        cmp  eax, 2                             ; span 0/1 -> fixed count, skip the call
        jb   fa_nobonus
        mov  esi, dword ptr [ebp - 0x08]
        add  esi, {FN_RANDINT:#x}
        call esi
        add  dword ptr [ebp - 0x24], eax
    fa_nobonus:

        ; ---- build the candidate list for this level ----
        mov  dword ptr [{g_ncand:#x}], 0
        mov  edi, 0                             ; resource index
    fa_scan:
        cmp  edi, dword ptr [ebp - 0x10]
        jge  fa_scan_done
        mov  eax, dword ptr [ebp - 0x0C]
        mov  edx, edi
        mov  esi, dword ptr [ebp - 0x08]
        add  esi, {FN_GET_URES:#x}
        call esi
        test eax, eax
        jz   fa_scan_next
        mov  edx, eax
        mov  eax, dword ptr [ebp - 0x14]
        mov  esi, dword ptr [ebp - 0x08]
        add  esi, {FN_SET_URES:#x}
        call esi

        mov  eax, dword ptr [ebp - 0x14]        ; level = unit.GetUnitLevel()
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {V_GETLEVEL:#x}]
        movsx eax, al
        cmp  eax, dword ptr [ebp - 0x20]
        jne  fa_scan_next

        mov  eax, dword ptr [ebp - 0x14]        ; race = unit.GetRace()
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {V_GETRACE:#x}]
        movsx eax, al
        cmp  eax, 31
        ja   fa_scan_next
        mov  ecx, eax
        mov  eax, dword ptr [{g_racemask:#x}]
        shr  eax, cl
        test eax, 1
        jz   fa_scan_next

        mov  eax, dword ptr [{g_ncand:#x}]      ; keep it
        cmp  eax, {MAX_CAND}
        jge  fa_scan_next
        mov  word ptr [eax * 2 + {g_cand:#x}], di
        inc  eax
        mov  dword ptr [{g_ncand:#x}], eax
    fa_scan_next:
        inc  edi
        jmp  fa_scan
    fa_scan_done:

        ; ---- add `count` random picks ----
        cmp  dword ptr [{g_ncand:#x}], 0
        jz   fa_next_pair
        mov  edi, 0
    fa_add:
        cmp  edi, dword ptr [ebp - 0x24]
        jge  fa_next_pair
        mov  eax, dword ptr [{g_ncand:#x}]
        mov  esi, dword ptr [ebp - 0x08]
        add  esi, {FN_RANDINT:#x}
        call esi
        movzx eax, word ptr [eax * 2 + {g_cand:#x}]
        mov  edx, eax
        mov  eax, dword ptr [ebp - 0x0C]
        mov  esi, dword ptr [ebp - 0x08]
        add  esi, {FN_GET_URES:#x}
        call esi
        test eax, eax
        jz   fa_add_next
        mov  dword ptr [ebp - 0x28], eax        ; the resource

        mov  eax, dword ptr [ebp - 0x08]        ; unit := TUnit.Create
        mov  eax, dword ptr [eax + {TUNIT_CLASSREF:#x}]
        xor  ecx, ecx
        mov  dl, 1
        mov  esi, dword ptr [ebp - 0x08]
        add  esi, {FN_UNIT_CREATE:#x}
        call esi
        test eax, eax
        jz   fa_add_next
        mov  ebx, eax
        mov  edx, dword ptr [ebp - 0x28]
        mov  eax, ebx
        mov  esi, dword ptr [ebp - 0x08]
        add  esi, {FN_SET_URES:#x}
        call esi

        mov  edx, ebx                           ; if army.CanAddUnit(unit)
        mov  eax, dword ptr [ebp - 0x04]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_CANADD:#x}]
        test al, al
        jz   fa_release
        mov  edx, ebx                           ;    army.AddUnit(unit)
        mov  eax, dword ptr [ebp - 0x04]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + {V_ADDUNIT:#x}]
    fa_release:
        mov  eax, ebx                           ; unit.Release
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {V_RELEASE:#x}]
    fa_add_next:
        inc  edi
        jmp  fa_add

    fa_next_pair:
        add  dword ptr [ebp - 0x18], 3
        inc  dword ptr [ebp - 0x1C]
        cmp  dword ptr [ebp - 0x1C], 3
        jl   fa_pair
    fa_pairs_done:

        mov  eax, dword ptr [ebp - 0x14]        ; scratch.Release
        test eax, eax
        jz   fa_done
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {V_RELEASE:#x}]

    fa_done:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret

; ============================= placement hook =============================
;  Replaces: test esi,esi / je 0x41A439 / push 0 / push 0
hook:
        test esi, esi
        jz   hk_skip
        mov  eax, dword ptr [esi + {ARMYHS_ARMY:#x}]
        test eax, eax
        jz   hk_tail
        mov  edx, dword ptr [eax]               ; only fill an EMPTY, fresh party
        call dword ptr [edx + {V_COUNT:#x}]
        test eax, eax
        jnz  hk_tail
        mov  eax, dword ptr [esi + {ARMYHS_ARMY:#x}]
        call fill_army
        mov  eax, dword ptr [esi + {ARMYHS_ARMY:#x}]    ; TArmy+0x24 = authored behaviour
        mov  cl, byte ptr [{g_behavior:#x}]
        mov  byte ptr [eax + {ARMY_BEHAVIOR:#x}], cl
    hk_tail:
        push 0
        push 0
        jmp  {RESUME_VA:#x}                     ; rel32 -- must not clobber a register:
    hk_skip:                                    ; MsgProc's return value lives in EAX
        jmp  {SKIP_VA:#x}
"""
    S = dict(base=base_va, code=code_va, g_strength=g_strength, g_racemask=g_racemask,
             g_seeded=g_seeded, g_ncand=g_ncand, g_behavior=g_behavior, g_spec=g_spec,
             g_ctrls=g_ctrls, g_cand=g_cand, data_len=code_va - base_va,
             dlg_blob=dlg_blob, dlg_data_off=dlg_data_off, **dlg_syms)
    src += PD.dialog_source(S, LAYOUT)
    return src, S


# ---- PE helpers (same shapes as the other AoWDevEd build scripts) -----------------
def load_sections(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e + 6)[0]
    optsz = struct.unpack_from('<H', d, e + 20)[0]
    opt = e + 24
    sectbl = opt + optsz
    secs = []
    for i in range(nsec):
        b = sectbl + i * 40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b + 8)
        secs.append((va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs,
                salign=struct.unpack_from('<I', d, opt + 32)[0],
                falign=struct.unpack_from('<I', d, opt + 36)[0],
                hdrsz=struct.unpack_from('<I', d, opt + 84)[0])


def align(x, a): return (x + a - 1) // a * a


def rva2off(secs, rva):
    for va0, vsz, raw, rsz, _ in secs:
        if va0 <= rva < va0 + max(vsz, rsz):
            return raw + (rva - va0)
    raise ValueError(hex(rva))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    path = os.path.join(GAME, EXE)
    d = bytearray(open(path, "rb").read())
    F = load_sections(d)

    hook_off = rva2off(F["secs"], HOOK_VA - 0x400000)
    hook_now = bytes(d[hook_off:hook_off + 8])
    have_sect = any(bytes(d[s[4]:s[4] + 4]) == SECT_NAME[:4] for s in F["secs"])

    newva = align(max(s[0] + max(s[1], s[3]) for s in F["secs"]), F["salign"])
    if have_sect:
        for s in F["secs"]:
            if bytes(d[s[4]:s[4] + 4]) == SECT_NAME[:4]:
                newva = s[0]
    base_va = 0x400000 + newva

    src, S = gen_source(base_va)
    code = asm_src(ks, src, S["code"])

    body = bytearray(b"\x00" * S["data_len"])
    body[S["dlg_data_off"]:S["dlg_data_off"] + len(S["dlg_blob"])] = S["dlg_blob"]
    body += code
    struct.pack_into("<I", body, S["g_strength"] - base_va, DEFAULT_STRENGTH)
    struct.pack_into("<I", body, S["g_racemask"] - base_va, DEFAULT_RACEMASK)
    struct.pack_into("<I", body, S["g_behavior"] - base_va, PD.DEFAULT_BEHAVIOUR)
    spec = S["g_spec"] - base_va
    for si, entries in enumerate(STRENGTH_TABLE):
        for pi, (lvl, base, span) in enumerate(entries):
            body[spec + si * 9 + pi * 3] = lvl
            body[spec + si * 9 + pi * 3 + 1] = base
            body[spec + si * 9 + pi * 3 + 2] = span

    # Label addresses: the source emits fill_army, then `hook`, then show_dialog, then
    # armybtn_hook. Recover each by assembling successive prefixes.
    def label_va(marker):
        return S["code"] + len(asm_src(ks, src.split(marker)[0], S["code"]))

    hook_va = label_va("; ============================= placement hook")
    armybtn_va = label_va("; ===================== Party button hook =====================")

    patched_hook = b"\xE9" + struct.pack("<i", hook_va - (HOOK_VA + 5)) + b"\x90\x90\x90"
    patched_btn = b"\xE9" + struct.pack("<i", armybtn_va - (ARMYBTN_VA + 5))

    btn_off = rva2off(F["secs"], ARMYBTN_VA - 0x400000)
    btn_now = bytes(d[btn_off:btn_off + 5])

    print(f"[{EXE}] .pty rva {newva:#x} -> VA {base_va:#x}; data {S['data_len']}B, "
          f"code {len(code)}B")
    print(f"    fill_army {S['code']:#x}  place-hook {hook_va:#x}  armybtn-hook {armybtn_va:#x}")
    print(f"    globals: g_strength {S['g_strength']:#x}(={DEFAULT_STRENGTH}) "
          f"g_racemask {S['g_racemask']:#x}(={DEFAULT_RACEMASK:#x}) "
          f"g_behavior {S['g_behavior']:#x}(={PD.DEFAULT_BEHAVIOUR}) "
          f"g_ctrls {S['g_ctrls']:#x}[{NCTRL}] g_cand {S['g_cand']:#x}[{MAX_CAND}]")

    installed = have_sect and hook_now == patched_hook and btn_now == patched_btn
    if installed:
        # Matching hook targets are NOT proof of being up to date: a change that only touches
        # cave DATA (dialog layout, strength table, defaults) leaves every label address alone.
        # Compare the whole intended body against what is installed.
        sec = [s for s in F["secs"] if bytes(d[s[4]:s[4] + 4]) == SECT_NAME[:4]][0]
        cur = bytes(d[sec[2]:sec[2] + len(body)])
        if cur == bytes(body):
            print(f"[{EXE}] already patched and up to date - no-op")
            return 0
        nd = sum(1 for a, b in zip(cur, bytes(body)) if a != b) + abs(len(cur) - len(body))
        print(f"[{EXE}] hooks current but .pty contents differ ({nd} bytes) - rewriting in place")
        installed = False

    # Accept EITHER pristine bytes or bytes we previously wrote (any older cave layout),
    # so the caves can be rewritten in place without ever restoring a backup.
    ours_hook = hook_now[0] == 0xE9 and hook_now[5:] == b"\x90\x90\x90"
    ours_btn = btn_now[0] == 0xE9
    assert hook_now == ORIG_HOOK or (have_sect and ours_hook), (
        f"place hook {HOOK_VA:#x} is neither vanilla nor ours: {hook_now.hex()}")
    assert btn_now == ARMYBTN_ORIG or (have_sect and ours_btn), (
        f"Party button hook {ARMYBTN_VA:#x} is neither vanilla nor ours: {btn_now.hex()}")
    if not have_sect:
        assert F["sectbl"] + (F["nsec"] + 1) * 40 <= F["hdrsz"], "no header room for a new section"

    if not args.apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            cs = Cs(CS_ARCH_X86, CS_MODE_32)
            labels = {S["code"]: "fill_army", hook_va: "place hook",
                      armybtn_va: "armybtn hook"}
            print("---- .pty code ----")
            for i in cs.disasm(code, S["code"]):
                mark = f"   <<< {labels[i.address]}" if i.address in labels else ""
                print(f"  {i.address:08X}  {i.mnemonic:7s} {i.op_str}{mark}")
        except ImportError:
            print("  (capstone not installed - skipping disasm preview)")
        print(f"---- place hook  @ {HOOK_VA:#x}: {hook_now.hex()} -> {patched_hook.hex()}")
        print(f"---- armybtn hook@ {ARMYBTN_VA:#x}: {btn_now.hex()} -> {patched_btn.hex()}")
        print(f"[{EXE}] dry-run OK - re-run with --apply to write")
        return 0

    backup = os.path.join(BACKUP_DIR, os.path.basename(path) + BACKUP_SUFFIX)
    if not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(path, backup)
        print(f"    backup -> {backup}")

    if have_sect:
        # rewrite the cave in place -- .pty is the LAST section, so its raw data runs to EOF
        sec = [s for s in F["secs"] if bytes(d[s[4]:s[4] + 4]) == SECT_NAME[:4]][0]
        va0, vsz, raw, rsz, hdr = sec
        assert raw + rsz >= len(d) - F["falign"], (
            ".pty is not the last section any more - refusing to rewrite in place")
        rawsz = align(len(body), F["falign"])
        d = d[:raw] + bytearray(body) + bytearray(b"\x00" * (rawsz - len(body)))
        struct.pack_into("<II", d, hdr + 8, len(body), va0)
        struct.pack_into("<II", d, hdr + 16, rawsz, raw)
        struct.pack_into("<I", d, F["opt"] + 56, align(va0 + len(body), F["salign"]))
        print(f"    rewrote .pty in place ({len(body)}B raw {rawsz}B) - no backup layer added")
    else:
        newraw = align(len(d), F["falign"])
        d += b"\x00" * (newraw - len(d))
        rawsz = align(len(body), F["falign"])
        d += bytes(body) + b"\x00" * (rawsz - len(body))
        b = F["sectbl"] + F["nsec"] * 40
        struct.pack_into("<8sIIII", d, b, SECT_NAME, len(body), newva, rawsz, newraw)
        struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, 0xE0000060)  # R/W/X: globals live here
        struct.pack_into("<H", d, F["e"] + 6, F["nsec"] + 1)
        struct.pack_into("<I", d, F["opt"] + 56, align(newva + len(body), F["salign"]))

    d[hook_off:hook_off + 8] = patched_hook
    d[btn_off:btn_off + 5] = patched_btn

    try:
        open(path, "wb").write(d)
    except PermissionError:
        print(f"[{EXE}] LOCKED - close the editor and retry")
        return 1
    print(f"[{EXE}] applied: .pty @ rva {newva:#x} ({len(body)}B); "
          f"place hook {HOOK_VA:#x}->{hook_va:#x}, Party button {ARMYBTN_VA:#x}->{armybtn_va:#x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
