#!/usr/bin/env python
r"""
build_dual_sphere_exe.py -- the AoWz.exe half of the dual-sphere groundwork (build_dual_sphere.py).

1. SPHERE LABEL.  Three spell views print "<sphere>, Level <tier>" through
   `TranslateRStr(TMagicSphereRStr[spell+0x20])`.  A dual spell carries sphere 7 (Secret), so each
   of those `call 0x4021E4` is retargeted to a stub: a sphere-7 spell found in the DLL's dual table
   prints "<first>/<second>" (e.g. "Death/Fire") from the same sphere strings; anything else goes
   straight on to TranslateRStr.
     0x0042E93C  TSpellBook.FillSlot class label (cast books, info view)   spell = EBX
     0x0042FFC4  currently-casting page                                    spell = EDI
     0x0044BA42  TWizardsTowerDlg spell line                               spell = ESI
   The Magic tab, research info and researched views print the label too but blank or discard it
   (build_magictab_tiername.py, cave_class), and duals are never researched.
2. UNIT BOOK FILTER.  build_scroll_spellbook.py's cave_bookfilter hides from a UNIT caster every
   spell whose tier exceeds its Spellcasting level (`movzx edi,[ecx+0x21] / cmp edi,[ebp-0xC]` at
   0x0060C114).  Those 7 bytes become `call cave_booktier` + 2 nop: tier + 1 for a sphere-7 spell,
   matching build_dual_sphere.py's cave_gate (owner: a dual tier-N spell needs Spellcasting N+1).
   build_scroll_spellbook.py accepts this chained cave as its applied state and refuses --undo
   while it is in place.  ⚠ Undo THIS script first.

The DLL table is reached through dual_find (pinned 0x558B6100) at its run-time address:
`[0x0045DF78]` (the AoWHSSet import cell) - 0x558FA044 + 0x558B6100.

Slot 0x0062BC00-0x0062BDFF (.hcol), exclusive.  The exe never rebases: absolute addresses.
No RNG.  Surgical --undo.

    python build_scripts/build_dual_sphere_exe.py            dry run + state
    python build_scripts/build_dual_sphere_exe.py --apply
    python build_scripts/build_dual_sphere_exe.py --undo
"""
import os, struct, sys
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from exe_patch import asm, run

SLOT = (0x0062BC00, 0x0062BE00)
LIT_SLASH = 0x0062BC00          # AnsiString "/" (refcount -1); chars at +8
COMMON = 0x0062BC10
STUBS = {"ebx": 0x0062BCA0, "edi": 0x0062BCC0, "esi": 0x0062BCE0}
BOOKTIER = 0x0062BD00

TRANSLATE = 0x004021E4
SPHERE_RSTR = 0x0045E034         # IAT: AoWE.TMagicSphereRStr
HSSET_CELL, HSSET_LINKED = 0x0045DF78, 0x558FA044
DUAL_FIND = 0x558B6100
LSTRCAT, LSTRCLR = 0x0045D300, 0x0045D320
DUAL_SPHERE = 7

SITES = {0x0042E93C: "ebx", 0x0042FFC4: "edi", 0x0044BA42: "esi"}
BOOK_SITE, BOOK_ORIG = 0x0060C114, bytes.fromhex("0fb679213b7df4")


def rel(src, dst, op):
    return bytes([op]) + struct.pack("<i", dst - (src + 5))


def lit():
    return struct.pack("<iI", -1, 1) + b"/\0" + b"\0" * 6


def common():
    # in: eax = the original RStr, edx = &dest, ecx = spell.  Out: dest = "<S1>/<S2>", or the plain
    # translation when the spell is not in the dual table.
    return asm(f"""
        push ebx
        push esi
        push edi
        push eax
        mov  esi, edx
        mov  ebx, ecx
        mov  eax, dword ptr [{HSSET_CELL:#x}]
        sub  eax, {HSSET_LINKED:#x}
        add  eax, {DUAL_FIND:#x}
        mov  edx, dword ptr [ebx + 0x10]
        call eax
        test eax, eax
        je   Lplain
        mov  edi, eax
        movzx eax, byte ptr [edi + 2]
        mov  edx, dword ptr [{SPHERE_RSTR:#x}]
        mov  eax, dword ptr [edx + eax*4]
        mov  edx, esi
        call {TRANSLATE:#x}
        push 0
        movzx eax, byte ptr [edi + 3]
        mov  edx, dword ptr [{SPHERE_RSTR:#x}]
        mov  eax, dword ptr [edx + eax*4]
        mov  edx, esp
        call {TRANSLATE:#x}
        mov  eax, esi
        mov  edx, {LIT_SLASH + 8:#x}
        call dword ptr [{LSTRCAT:#x}]
        mov  eax, esi
        mov  edx, dword ptr [esp]
        call dword ptr [{LSTRCAT:#x}]
        mov  eax, esp
        call dword ptr [{LSTRCLR:#x}]
        pop  eax
        pop  eax
        pop  edi
        pop  esi
        pop  ebx
        ret
    Lplain:
        pop  eax
        mov  edx, esi
        pop  edi
        pop  esi
        pop  ebx
        jmp  {TRANSLATE:#x}
    """, COMMON)


def stub(reg, va):
    return asm(f"""
        cmp  byte ptr [{reg} + 0x20], {DUAL_SPHERE}
        jne  {TRANSLATE:#x}
        push ecx
        mov  ecx, {reg}
        call {COMMON:#x}
        pop  ecx
        ret
    """, va)


def booktier():
    # Replays `movzx edi,[ecx+0x21] / cmp edi,[ebp-0xC]` with tier + 1 for a dual spell; the flags
    # of the cmp survive the ret for the `jg` that follows the call site.
    return asm(f"""
        movzx edi, byte ptr [ecx + 0x21]
        cmp  byte ptr [ecx + 0x20], {DUAL_SPHERE}
        jne  Lcmp
        inc  edi
    Lcmp:
        cmp  edi, dword ptr [ebp - 0xc]
        ret
    """, BOOKTIER)


def main():
    caves = [("lit_slash", LIT_SLASH, lit()), ("common", COMMON, common())]
    caves += [("stub_" + r, STUBS[r], stub(r, STUBS[r])) for r in ("ebx", "edi", "esi")]
    caves.append(("booktier", BOOKTIER, booktier()))
    hooks = [(va, rel(va, TRANSLATE, 0xE8), rel(va, STUBS[r], 0xE8)) for va, r in SITES.items()]
    hooks.append((BOOK_SITE, BOOK_ORIG, rel(BOOK_SITE, BOOKTIER, 0xE8) + b"\x90\x90"))
    run("build_dual_sphere_exe -- dual-sphere label + unit book tier", hooks, caves, SLOT)


if __name__ == "__main__":
    main()
