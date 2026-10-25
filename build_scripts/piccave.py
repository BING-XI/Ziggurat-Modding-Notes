#!/usr/bin/env python
r"""
piccave.py -- shared helpers for position-independent caves: one call/pop anchor per routine and
disp32 placeholders patched in place.  Not a build script.  Used by build_skirmisher.py and later
ability scripts (build_rally.py carries its own copy of the same function).
"""
import struct
from aowepack_patch import asm

ANCHOR = b"\xE8\x00\x00\x00\x00"
POP = {"eax": 0x58, "ecx": 0x59, "edx": 0x5A, "ebx": 0x5B, "esi": 0x5E, "edi": 0x5F}


def ansistr(s):
    """A Delphi AnsiString literal (refcount -1, so LStrAsg shares it); its chars start at +8."""
    b = s.encode("latin1")
    return struct.pack("<iI", -1, len(b)) + b + b"\0"


def pic(src, va, reg, fields, tail=b""):
    """Assemble `src` once.  `{ANC}` marks a `call anc / anc: pop <reg>` anchor (exactly one); each
    `{NAME}` in `fields` is a disp32 placeholder patched to (target - anchor), so no instruction
    changes length.  A target of ("TAIL", n) is byte n of `tail`, appended after 4-byte alignment."""
    ph = {n: 0x7FFFF000 + 0x10 * k for k, n in enumerate(fields)}
    text = src.replace("{ANC}", "call anc_%s\n    anc_%s:\n        pop %s" % (reg, reg, reg))
    code = bytearray(asm(text.format(**{n: "%#x" % v for n, v in ph.items()}), va))
    k = code.find(ANCHOR + bytes([POP[reg]]))
    assert k >= 0 and code.find(ANCHOR + bytes([POP[reg]]), k + 1) < 0, "anchor not found exactly once"
    anchor = va + k + 5
    while len(code) % 4:
        code += b"\x90"
    tail_va = va + len(code)
    for n, tgt in fields.items():
        pos = [j for j in range(len(code) - 3) if code[j:j + 4] == struct.pack("<I", ph[n])]
        assert pos, "placeholder %s not found" % n
        t = tail_va + tgt[1] if isinstance(tgt, tuple) else tgt
        for j in pos:
            struct.pack_into("<i", code, j, t - anchor)
    assert not any(code[j:j + 4] == struct.pack("<I", v) for v in ph.values()
                   for j in range(len(code) - 3)), "a placeholder survived"
    return bytes(code) + tail


def enhancement_reg(va, register, cea, abil_id, name, mask=0x03FF):
    """A registration splice for a plain TEnhancementAbility passive: replay the displaced
    `call RegisterAbility` (EBX = the control), then CreateEnhancementAbility + RegisterAbility."""
    src = f"""
        call {register:#x}
        {{ANC}}
        lea  edx, [eax + {{NAME}}]
        mov  cx, {mask:#x}
        mov  eax, {abil_id:#x}
        call {cea:#x}
        mov  edx, eax
        mov  eax, ebx
        call {register:#x}
        ret
    """
    return pic(src, va, "eax", {"NAME": ("TAIL", 8)}, ansistr(name))
