#!/usr/bin/env python
r"""
build_wheel_combo.py -- the mouse wheel scrolls a dropped-down combo box's list (the multiplayer
lobby's race-assignment and preferred-race dropdowns).  aowInt.dpl.

An extension of our wheel stack in the shape build_wheel_ext.py uses: one latch + one helper in
a contract-header slot; vcl30.dpl is untouched.  REQUIRES build_wheel_aowint.py (header, the CLR
hook that zeroes the latch block every mouse-move sweep, and slot 0) and build_wheel_ext.py
(slots 1-2, latches 3-6).  RE from Inioch's share8 build_wheel_combo.py; his hooks go into his
own WheelScroll and are not reused.

TAOWComboBox (VMT 0x59811FCC): +0x118 dropped-down flag (-1 open / 0 closed), +0x120 its own
TAOWVScrollBar (FPos +0x148), TAOWComboBox.Update 0x598131CC copies the bar's FPos into the top
item +0x12C (clamped) and repaints.  TAOWScrollBar.SetFPos 0x5980CA28 (eax = bar, edx = pos) clamps.

  H9 SETC  TAOWComboBox.CheckMouseMove's cursor-inside marker 0x59813AC1 (7 B,
           `mov [ebx+0x78],-1`, ebx = the combo, vanilla, no .reloc) -> cave_setc:
           replay; latch[7] (0x5983E05C, the spare) = the combo while it is dropped down.
  WheelCombo(delta) -> header slot 3 (0x5982401C, RVA): latch[7] set and the combo still open ->
           SetFPos(bar, FPos -/+ 3), wheel up = up the list; TAOWComboBox.Update; eax = 1.
           Else eax = 0 and the pump tries nothing further (slot 3 is last).
The LL hook ORs the whole 8-latch block, so latch[7] also arms the wheel capture.

Rolls: none (UI only).  PIC: call/pop delta for the latch, rel32 elsewhere.
Cave 0x59824800-0x598248FF (CODE's zero tail above build_wheel_ext.py's 0x59824400..0x598247FF),
exclusive.  Surgical --undo (hook, cave, slot 3; the latch is zeroed every sweep anyway).
"""
import os, struct, sys
sys.dont_write_bytecode = True
import aowepack_patch as P
from aowepack_patch import asm, jmp_to, run

P.TARGET = os.path.join(P.GAME, "aowInt.dpl")
P.IMAGE_BASE = 0x59800000

SLOT = (0x59824800, 0x59824900)
CAVE_SET, CAVE_WHEEL = 0x59824800, 0x59824840
HOOK, VAN, RESUME = 0x59813AC1, bytes.fromhex("c74378ffffffff"), 0x59813AC8
HDR_SLOT3 = 0x5982401C
LATCH7 = 0x5983E05C
CB_OPEN, CB_BAR, SB_FPOS = 0x118, 0x120, 0x148
F_SETFPOS, F_COMBO_UPDATE = 0x5980CA28, 0x598131CC
LINES = 3


def build_set(va):
    return asm(f"""
        mov dword ptr [ebx + 0x78], -1
        cmp dword ptr [ebx + {CB_OPEN:#x}], 0
        je s_out
        push eax
        call s_here
    s_here:
        pop eax
        sub eax, s_here
        mov dword ptr [eax + {LATCH7:#x}], ebx
        pop eax
    s_out:
        jmp {RESUME:#x}
    """, va)


def build_wheel(va):
    head = asm("push ebp\nmov ebp, esp\npush ebx\npush esi", va)
    a = va + len(head) + 5
    call = asm(f"call {a:#x}", va + len(head))
    tail = asm(f"""
        pop ebx
        sub ebx, {a:#x}
        mov esi, dword ptr [ebx + {LATCH7:#x}]
        test esi, esi
        je w_fail
        cmp dword ptr [esi + {CB_OPEN:#x}], 0
        je w_fail
        mov eax, dword ptr [esi + {CB_BAR:#x}]
        test eax, eax
        je w_fail
        mov edx, dword ptr [eax + {SB_FPOS:#x}]
        cmp dword ptr [ebp + 8], 0
        jle w_down
        sub edx, {LINES}
        jmp w_set
    w_down:
        add edx, {LINES}
    w_set:
        call {F_SETFPOS:#x}
        mov eax, esi
        call {F_COMBO_UPDATE:#x}
        mov eax, 1
        jmp w_exit
    w_fail:
        xor eax, eax
    w_exit:
        pop esi
        pop ebx
        pop ebp
        ret 4
    """, a)
    return head + call + tail


caves = [("cave_setc", CAVE_SET, build_set(CAVE_SET)),
         ("WheelCombo", CAVE_WHEEL, build_wheel(CAVE_WHEEL))]
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE_SET, len(VAN))),
         (HDR_SLOT3, bytes(4), struct.pack("<I", CAVE_WHEEL - P.IMAGE_BASE))]
interior = [(HOOK, HOOK + len(VAN), 0x59813A40, 0x59813B40)]

if __name__ == "__main__":
    d = open(P.TARGET, "rb").read()
    o = P.va2off(d, 0x59824000)
    assert d[o:o + 4] == b"AZWH" and struct.unpack_from("<I", d, o + 0xC)[0] == 8, \
        "build_wheel_aowint.py's contract header (8 latches) is not installed"
    assert struct.unpack_from("<I", d, o + 0x18)[0], "build_wheel_ext.py (slots 1-2) is not installed"
    run("build_wheel_combo", hooks, caves, SLOT, interior)
