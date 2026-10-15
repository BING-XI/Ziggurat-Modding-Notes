#!/usr/bin/env python
r"""
build_combatlog_linger.py -- the combat log keeps its text after a MANUAL battle and stays up ~10 s.
AoWz.exe (exe_patch.py).  Owner request 2026-10-14; v2 2026-10-15: no linger after auto-combat or a
replay (owner: "the combat log staying open after autocombat was a mistake").

BEFORE
    cave_drain (build_combatlog_exe.py, .clog @0x00610360, pumped every frame from
    TMWindow.MapWindowUpdate) picks a mode each tick: 1 = tactical (RING_TACTICAL [0x60D00C] = 1),
    2 = the fast-combat window [0x45B1B0]+0x44 is visible, 0 = neither.  On the change to 0
    (`_m_none`, 0x006103C2) it cleared the memo and discarded the unread ring slots (rdIdx := wrIdx),
    and `_vis` (0x0061055C) hid the window in the same tick.  TTacticalCombat.Finalize drops
    RING_TACTICAL before the logbook is finalised, so the last lines (the battle result from
    build_combatlog_endings.py) were wiped a frame or two after they were written.

AFTER
    change to 0     no clear, no discard: the tick falls through to `_drain`, which appends the
                    unread ring lines as on any tick.  From mode 1 (manual combat) the linger
                    starts: G_LING := 1, G_LSTART := now (ms of the day).  From mode 2 (the
                    fast-combat window: auto-combat and replays) it does not, so `_nowant` hides
                    the window in the same tick, as before 2026-10-14.
    mode-0 ticks    (`_nowant`) G_SEAL := the memo's line count.  While lingering and fewer than
                    LINGER_MS have passed, `want` := the window's CURRENT visibility, so the linger
                    keeps a shown window up and never shows a hidden one.  After that, or when the
                    clock reads earlier than G_LSTART (midnight), G_LING := 0 and the window hides
                    through the stock `_apply` path.  The rect is not touched in mode 0, so the
                    window stays where it was.
    change 0 -> 1/2 (`_m_have`) the previous battle's lines go: the first G_SEAL lines are deleted,
                    or the whole list cleared when it holds no more than that.  Lines a replay wrote
                    straight into the memo (cl_emit_replay) after the last mode-0 tick survive.
                    G_LING := 0, G_SEAL := 0, then the stock placement code runs.  A 1 <-> 2 change
                    clears nothing, as before.  The ring is NOT reset here: every tick in every mode
                    drains it, so at this tick it holds only lines written since the previous tick,
                    which belong to the battle that is starting.
    fast combat     TFastCombatWindow's show method 0x004352EC (only caller: the event-log
                    dispatcher 0x0044EF42, live auto-combat and replays alike) ends with
                    SetVisible(1) at 0x00435357.  Just before it, when [BSS_LASTMODE] = 0: the memo is
                    cleared, G_SEAL := 0, the linger ends and our window is hidden.  So a linger never
                    overlaps a fast-combat animation, and the hide happens before that window is
                    visible.  From the next tick the stock mode-2 rule applies unchanged (it shows
                    the log at the replay placement while the fast-combat window is visible).

CLOCK
    SysUtils.Time through the exe's own IAT cell 0x0045D408 (vcl30; GetLocalTime + EncodeTime, the
    fraction of the day in ST0), times 86400000, fistp.  AoWz.exe imports no GetTickCount and no
    timeGetTime; MapWindowUpdate's frame rate is not fixed, so frames were not counted.

SITES (verify-before-write against the bytes build_combatlog_exe.py installed)
    0x006103C2  7 B  cmp dword [0x45B2F4],0           -> jmp cave_none + 2 nop    (`_m_none`)
    0x006103FE 12 B  cmp esi,[0x45B2F4] ; je 0x61050C -> jmp cave_have + 7 nop    (`_m_have`)
    0x0061057D 12 B  mov edx,1 ; jmp 0x610586 ; xor edx,edx ; mov eax,[ebx+0x44]
                     -> jmp cave_want ; nop nop ; jmp cave_nowant   (entries 0x61057D `_want` and
                     0x610584 `_nowant` kept; 0x610586 `_apply` was reached only from the replaced
                     jmp at 0x610582; the caves rejoin at 0x610589)
    0x00435357  5 B  mov dl,1 ; mov eax,[ebx+0x44]    -> jmp cave_fcshow
    Branch targets inside cave_drain were enumerated: no other jump lands inside these windows.
    No .reloc entry under any hook or the slot (exe_patch checks on every run).

SLOT 0x0062AB40..0x0062AD3F, exclusive (.hcol, RWX, from the free run above
    build_combatlog_autoscroll.py's 0x0062AB00..0x0062AB3F).  State lives in the slot:
    G_LING 0x0062AB40, G_LSTART 0x0062AB44, G_SEAL 0x0062AB48 (zero on disk; --undo zero-fills).

COUPLINGS
    build_combatlog_exe.py --apply rewrites the whole .clog blob in place and silently removes the
    three cave_drain hooks (cave_fcshow at 0x435357 would remain).  Re-run this script with --apply
    after it, or --undo this one first.
    build_clogwin_gate.py's `vis` site 0x0061055C is untouched; its OFF state jumps to 0x610584,
    which is now cave_nowant, and since the linger only keeps the current visibility, OFF still
    means never visible.

NO RANDOMNESS.  Draws nothing; rng_audit has no site here.

USAGE
    python build_combatlog_linger.py [--dis]     verify / dry run
    python build_combatlog_linger.py --apply
    python build_combatlog_linger.py --undo      surgical: restores the four sites, zero-fills the slot
"""
import struct
import sys
sys.dont_write_bytecode = True
from exe_patch import asm, jmp_to, run

LINGER_MS = 10000

SLOT = (0x0062AB40, 0x0062AD40)
G_LING, G_LSTART, G_SEAL = 0x0062AB40, 0x0062AB44, 0x0062AB48
K_MSDAY = 0x0062AB50                   # double 86400000.0
CODE = 0x0062AB60

IAT_TIME = 0x0045D408                  # VCL30 SysUtils.Time
BSS_LASTMODE = 0x0045B2F4
GVAR_INSTANCE = 0x0045B2E0             # TCombatLogWin
DRAIN = 0x0061050C                     # cave_drain `_drain`
HAVE_CONT = 0x0061040A                 # cave_drain: cmp esi,2 (placement)
APPLY_TEST = 0x00610589                # cave_drain `_apply`: test eax,eax (eax = ctl, edx = want)

H_NONE, H_NONE_VAN = 0x006103C2, bytes.fromhex("833df4b2450000")
H_HAVE, H_HAVE_VAN = 0x006103FE, bytes.fromhex("3b35f4b24500" "0f8402010000")
H_VIS, H_VIS_VAN = 0x0061057D, bytes.fromhex("ba01000000" "eb02" "31d2" "8b4344")
H_FC, H_FC_VAN = 0x00435357, bytes.fromhex("b201" "8b4344")
FC_CONT = 0x0043535C                   # mov ecx,[eax] ; call [ecx+0x6C]  (SetVisible(FC, 1))

SRC = {
    # EAX := milliseconds since local midnight.  Clobbers ECX, EDX.
    "now_ms": f"""
        call dword ptr [{IAT_TIME:#x}]
        fmul qword ptr [{K_MSDAY:#x}]
        push eax
        fistp dword ptr [esp]
        pop eax
        ret
    """,
    # replaces `_m_none`.  The `mov` between the second cmp and the jne leaves the flags alone.
    "cave_none": """
        cmp dword ptr [{LM:#x}], 0
        je {DRAIN:#x}
        cmp dword ptr [{LM:#x}], 1
        mov dword ptr [{LM:#x}], 0
        jne {DRAIN:#x}
        call {now_ms:#x}
        mov dword ptr [{G_LSTART:#x}], eax
        mov dword ptr [{G_LING:#x}], 1
        jmp {DRAIN:#x}
    """,
    # replaces `cmp esi,[LASTMODE] ; je _drain`.  EAX = manager, ECX = window ctl: both kept.
    "cave_have": """
        cmp esi, dword ptr [{LM:#x}]
        je {DRAIN:#x}
        cmp dword ptr [{LM:#x}], 0
        jne {HAVE_CONT:#x}
        mov dword ptr [{G_LING:#x}], 0
        push eax
        push ecx
        push edi
        mov eax, dword ptr [ebx+0x48]
        mov eax, dword ptr [eax+0x118]
        test eax, eax
        je h_done
        mov edi, eax
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x14]
        cmp dword ptr [{G_SEAL:#x}], eax
        jb h_part
        mov eax, edi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x40]
        jmp h_done
    h_part:
        cmp dword ptr [{G_SEAL:#x}], 0
        je h_done
        mov eax, edi
        xor edx, edx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x44]
        dec dword ptr [{G_SEAL:#x}]
        jmp h_part
    h_done:
        mov dword ptr [{G_SEAL:#x}], 0
        pop edi
        pop ecx
        pop eax
        jmp {HAVE_CONT:#x}
    """,
    # replaces `_want`
    "cave_want": """
        mov edx, 1
        mov eax, dword ptr [ebx+0x44]
        jmp {APPLY_TEST:#x}
    """,
    # replaces `_nowant`
    "cave_nowant": """
        mov eax, dword ptr [ebx+0x48]
        test eax, eax
        je n_time
        mov eax, dword ptr [eax+0x118]
        test eax, eax
        je n_time
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x14]
        mov dword ptr [{G_SEAL:#x}], eax
    n_time:
        cmp dword ptr [{G_LING:#x}], 0
        je n_hide
        call {now_ms:#x}
        sub eax, dword ptr [{G_LSTART:#x}]
        cmp eax, {LINGER_MS}
        jb n_keep
        mov dword ptr [{G_LING:#x}], 0
    n_hide:
        xor edx, edx
        jmp n_out
    n_keep:
        xor edx, edx
        mov eax, dword ptr [ebx+0x44]
        test eax, eax
        je n_out
        movzx edx, byte ptr [eax+0x75]
    n_out:
        mov eax, dword ptr [ebx+0x44]
        jmp {APPLY_TEST:#x}
    """,
    # before TFastCombatWindow's SetVisible(1).  EBX = fast-combat window, ESI = event: kept.
    "cave_fcshow": """
        cmp dword ptr [{LM:#x}], 0
        jne f_out
        mov dword ptr [{G_LING:#x}], 0
        mov dword ptr [{G_SEAL:#x}], 0
        mov eax, dword ptr [{GV:#x}]
        test eax, eax
        je f_out
        mov ecx, dword ptr [eax+0x48]
        test ecx, ecx
        je f_hide
        mov ecx, dword ptr [ecx+0x118]
        test ecx, ecx
        je f_hide
        push eax
        mov eax, ecx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x40]
        pop eax
    f_hide:
        mov eax, dword ptr [eax+0x44]
        test eax, eax
        je f_out
        cmp byte ptr [eax+0x75], 0
        je f_out
        xor edx, edx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x6C]
    f_out:
        mov dl, 1
        mov eax, dword ptr [ebx+0x44]
        jmp {FC_CONT:#x}
    """,
}


def build():
    caves = [("k_msday", K_MSDAY, struct.pack("<d", 86400000.0))]
    env = dict(LM=BSS_LASTMODE, DRAIN=DRAIN, HAVE_CONT=HAVE_CONT, APPLY_TEST=APPLY_TEST,
               G_LING=G_LING, G_LSTART=G_LSTART, G_SEAL=G_SEAL, GV=GVAR_INSTANCE,
               FC_CONT=FC_CONT, LINGER_MS=LINGER_MS)
    va = CODE
    for name in ("now_ms", "cave_none", "cave_have", "cave_want", "cave_nowant", "cave_fcshow"):
        blob = asm(SRC[name].format(**env), va)
        caves.append((name, va, blob))
        env[name] = va
        va = (va + len(blob) + 3) & ~3
    return caves


caves = build()
at = {n: va for n, va, _b in caves}
hooks = [
    (H_NONE, H_NONE_VAN, jmp_to(H_NONE, at["cave_none"], len(H_NONE_VAN))),
    (H_HAVE, H_HAVE_VAN, jmp_to(H_HAVE, at["cave_have"], len(H_HAVE_VAN))),
    (H_VIS, H_VIS_VAN, jmp_to(H_VIS, at["cave_want"], 7) + jmp_to(H_VIS + 7, at["cave_nowant"], 5)),
    (H_FC, H_FC_VAN, jmp_to(H_FC, at["cave_fcshow"], len(H_FC_VAN))),
]
assert H_VIS + 7 == 0x00610584

if __name__ == "__main__":
    run("build_combatlog_linger", hooks, caves, SLOT)
