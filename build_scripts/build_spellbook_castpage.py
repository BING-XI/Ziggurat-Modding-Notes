#!/usr/bin/env python
r"""
build_spellbook_castpage.py -- the spellbook decides "cast now" or "start casting" on the cost the
engine charges.  AoWz.exe.

THE DEFECT (vanilla, armed by our discounts)
    The strategic spellbook click handler (fn 0x430788, mode [ebx+0x220] = 0) compares the hero's
    casting points (VMT +0x12C) with the RAW spell cost [spell+0x14] at 0x430844:
        enough, or cheats on -> 0x430871: CastSpell, close the book
        otherwise            -> 0x4308AC: CastSpell, then the casting-in-progress page (0x43073C)
    THero.CastSpell decides on the cost our wallet charges (build_caster_wallet.py hook F at
    0x5578964A swaps the raw cost for CastingMana inside CanCastSpellInstantly).  So with
    Evoker/Conjurer/Enchanter/Ritualist (x0.6) or Mastery (x0.75), a hero whose points cover only the
    discounted cost casts at once and still gets the casting page; with the opposed x1.5 the spell
    starts charging and the book closes.  Found through Inioch's share9
    (patch_exe_cast_nocharge_popup_v1.py, the same rewrite).

THE PATCH (in place, no cave)
    0x430833..0x430852 (32 B: casting points, the raw compare, the cheat test) ->
        lea eax,[ebp-4] / push eax              ; var message: the handler's own AnsiString local
        mov ecx,[esi+0x14] / mov edx,[esi+0x10] ; raw cost, spell id
        mov eax,[ebx+0x22C]                     ; the hero
        call 0x4027A4                           ; THero.CanCastSpellInstantly (jmp [0x45DC90])
        test al,al / jne 0x430871 / jmp 0x4308AC
    + nop padding.  CanCastSpellInstantly 0x55789640 (EAX hero, EDX spell id, ECX cost, [esp] var
    message; ret 4) is true when the wallet's cost <= the casting points, or cheats are on (the test
    this replaces), or the hero is channelling this very spell and it is ready -- and only if
    CanCastSpell passes.  Anything else takes the "start casting" branch: CastSpell, then the casting
    page or CastSpell's own error message.  [ebp-4] is zeroed in the prologue and finalised by the
    handler's SEH frame; CastSpell already writes it.  The fixup at 0x430854 (`mov eax,[0x45DF7C]`)
    sits past the rewrite and stays valid; no branch lands inside it (scanned 0x430788..0x430940).

RNG: none.  UI only; the engine's decision is unchanged.

Unproven, static checks cannot reach it: that unit spellcasters and scroll casts, which reach the
same handler, see the right page.

    python build_scripts/build_spellbook_castpage.py            dry run + state
    python build_scripts/build_spellbook_castpage.py --apply
    python build_scripts/build_spellbook_castpage.py --undo     surgical: the 32 bytes back
"""
import sys
sys.dont_write_bytecode = True
from exe_patch import asm, run

SITE = 0x00430833
VANILLA = bytes.fromhex("8b832c0200008b10ff922c0100000fbec03b46147d28"
                        "8b832c0200000fbe5024")
CANCAST_INSTANT = 0x004027A4                   # jmp [0x45DC90] = THero.CanCastSpellInstantly
CAST_CLOSE, CAST_CHARGE = 0x00430871, 0x004308AC

new = asm(f"""
    lea  eax, [ebp - 4]
    push eax
    mov  ecx, dword ptr [esi + 0x14]
    mov  edx, dword ptr [esi + 0x10]
    mov  eax, dword ptr [ebx + 0x22c]
    call {CANCAST_INSTANT:#x}
    test al, al
    jne  {CAST_CLOSE:#x}
    jmp  {CAST_CHARGE:#x}
""", SITE)
assert len(new) <= len(VANILLA), "rewrite is %d bytes" % len(new)
new += b"\x90" * (len(VANILLA) - len(new))

hooks = [(SITE, VANILLA, new)]

if __name__ == "__main__":
    run("build_spellbook_castpage", hooks, [], (SITE, SITE))
