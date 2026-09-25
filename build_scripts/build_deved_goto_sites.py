#!/usr/bin/env python
r"""
build_deved_goto_sites.py -- the editor's Go-to (Items and Heroes tabs) finds an item or hero that
sits inside an exploration site, and centres on the site.  AoWDevEd.exe -> AoWzEd.exe.

From Inioch's share8 patch_devx_prune_unused_v2.py, part 4 only (its prune menu, toolbar buttons and
validation-centre parts are not taken).

VANILLA
    GotoItemClick / GoToHeroClick ask TItem.GetLocation / TAbstractUnit.GetLocation for the object's
    hex, then `cmp byte [esp],0FFh / je exit` (0x42CD44 items, 0x42CDE0 heroes): an object with no
    hex of its own does nothing.  An item in a site's treasure and a hero in a site's defender party
    have no hex, so Go-to is dead for exactly the objects hardest to find by eye.

THE FIX
    Both 6-byte tests become `call goto_item|goto_hero / nop`.  If x != 0FFh the stub returns and
    vanilla continues.  Otherwise find_site walks the map's structure list (map+0x100 -> [+8] ->
    TList: count [+8], items [+4]) for a site whose treasure list (TItemExplorationSite +0x3C, items)
    or defender army (TExplorationSite +0x34, heroes) is the object's owner ([obj+4]), writes the
    site's GetXhx/GetYhx/GetLhx (VMT +0x74/+0x78/+0x7C) into the caller's x/y/level bytes and returns
    to vanilla's CenterView + PlayCenterAnimation.  No match: discard the return address and take
    vanilla's exit (0x42CD86 / 0x42CE22), as before.
    Class tests walk the VMT parent chain against AoWEPACK VMTs rebased through the AoWHSMap import
    slot ([0x43289C] - 0x558FA040); TItemExplorationSite 0x557C23BC (instance 0x40), its parent
    TExplorationSite 0x557C1440 (instance 0x38).  Hero mode matches any site but reads only +0x34:
    a plain TExplorationSite has no +0x3C.  Coordinates: VMT +0x74/+0x78/+0x7C are the HSEPack
    thunks TMultiHexMO.GetXhx / GetYhx and TMapObject.GetLhx.

CAVE
    0x0059BB00 in .nmg's top slack (0x0059BAE6-0x0059BBFF is free, above build_deved_itemhpmv.py's
    relocated TITEMEDITFORM); slot 0x0059BB00-0x0059BBFF, exclusive.  .nmg is RWX and file-backed to
    0x0059BC00.
    ⚠ FORWARD HAZARD: build_deved_newmapgen.py rebuilds .nmg and zeroes everything above its body,
    this cave included (it is latent: that script refuses --apply while installed).  After any such
    rebuild, re-run this script's --apply; until then the hooks call zeroes and the editor crashes on
    Go-to.

USAGE
    python build_deved_goto_sites.py [--dis]   verify / dry run
    python build_deved_goto_sites.py --apply   then derives AoWzEd.exe (build_zigeditor.py --apply)
    python build_deved_goto_sites.py --undo    surgical, then derives AoWzEd.exe
"""
import os, struct, subprocess, sys
sys.dont_write_bytecode = True
from exe_patch import run, HERE
import zigexe
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

SLOT = (0x0059BB00, 0x0059BC00)
CAVE = 0x0059BB00
HOOK_ITEM, EXIT_ITEM = 0x0042CD44, 0x0042CD86
HOOK_HERO, EXIT_HERO = 0x0042CDE0, 0x0042CE22
HOOK_VAN = bytes.fromhex("803c24ff743c")
T_GETSELITEM, T_GETSELHERO = 0x00403118, 0x00403158
MAP_SLOT, DLL_MAPVAR = 0x0043289C, 0x558FA040
VMT_ITEMSITE, VMT_SITE = 0x557C23BC, 0x557C1440
SITE_ITEMS, SITE_ARMY = 0x3C, 0x34

SRC = f"""
goto_item:
    cmp byte ptr [esp + 4], 0xff
    jne g_ret
    mov eax, ebx
    call {T_GETSELITEM:#x}
    push {EXIT_ITEM:#x}
    xor edx, edx
    jmp g_common
goto_hero:
    cmp byte ptr [esp + 4], 0xff
    jne g_ret
    mov eax, ebx
    call {T_GETSELHERO:#x}
    push {EXIT_HERO:#x}
    xor edx, edx
    inc edx
g_common:
    test eax, eax
    je g_fail
    lea ecx, [esp + 8]
    call find_site
    test al, al
    je g_fail
    pop eax
g_ret:
    ret
g_fail:
    pop eax
    pop ecx
    jmp eax

find_site:
    push ebx
    push esi
    push edi
    push ebp
    mov ebp, ecx
    mov edi, edx
    mov esi, dword ptr [eax + 4]
    mov eax, dword ptr [{MAP_SLOT:#x}]
    mov ebx, eax
    sub ebx, {DLL_MAPVAR:#x}
    test esi, esi
    je fs_no
    mov eax, dword ptr [eax]
    test eax, eax
    je fs_no
    mov eax, dword ptr [eax + 0x100]
    test eax, eax
    je fs_no
    mov eax, dword ptr [eax + 8]
    test eax, eax
    je fs_no
    mov eax, dword ptr [eax + 8]
    test eax, eax
    je fs_no
    mov ecx, dword ptr [eax + 8]
    mov eax, dword ptr [eax + 4]
    lea edx, [ebx + {VMT_ITEMSITE:#x}]
    test edi, edi
    je fs_loop
    lea edx, [ebx + {VMT_SITE:#x}]
fs_loop:
    dec ecx
    js fs_no
    mov ebx, dword ptr [eax + ecx*4]
    test ebx, ebx
    je fs_loop
    push eax
    mov eax, dword ptr [ebx]
ic_loop:
    cmp eax, edx
    je ic_yes
    mov eax, dword ptr [eax - 0x18]
    test eax, eax
    je ic_no
    mov eax, dword ptr [eax]
    test eax, eax
    jne ic_loop
ic_no:
    pop eax
    jmp fs_loop
ic_yes:
    pop eax
    test edi, edi
    jne fs_army
    cmp dword ptr [ebx + {SITE_ITEMS:#x}], esi
    je fs_hit
    jmp fs_loop
fs_army:
    cmp dword ptr [ebx + {SITE_ARMY:#x}], esi
    jne fs_loop
fs_hit:
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x74]
    mov byte ptr [ebp], al
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x78]
    mov byte ptr [ebp + 1], al
    mov eax, ebx
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x7c]
    mov byte ptr [ebp + 2], al
    mov al, 1
    jmp fs_out
fs_no:
    xor eax, eax
fs_out:
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret
"""


def assemble():
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code = bytes(ks.asm(SRC, CAVE)[0])
    probe = bytes(ks.asm(SRC + "\nmov eax, goto_hero", CAVE)[0])
    assert probe[:len(code)] == code and len(probe) == len(code) + 5
    return code, struct.unpack_from("<I", probe, len(code) + 1)[0]


def call6(src, dst):
    return b"\xE8" + struct.pack("<i", dst - (src + 5)) + b"\x90"


code, GOTO_HERO = assemble()
caves = [("cave_goto_sites", CAVE, code)]
hooks = [(HOOK_ITEM, HOOK_VAN, call6(HOOK_ITEM, CAVE)),
         (HOOK_HERO, HOOK_VAN, call6(HOOK_HERO, GOTO_HERO))]

if __name__ == "__main__":
    did = run("build_deved_goto_sites", hooks, caves, SLOT, targets=[zigexe.SRC_EDITOR])
    if did:
        print("\nderiving %s ..." % zigexe.LIVE_EDITOR)
        r = subprocess.run([sys.executable, os.path.join(HERE, "build_zigeditor.py"), "--apply"],
                           capture_output=True, text=True)
        print("\n".join(r.stdout.strip().splitlines()[-3:]))
        if r.returncode:
            sys.exit("build_zigeditor.py --apply FAILED: %s" % r.stderr.strip()[-400:])
