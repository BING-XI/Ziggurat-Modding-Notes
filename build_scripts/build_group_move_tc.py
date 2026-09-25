#!/usr/bin/env python
r"""
build_group_move_tc.py -- tactical group move: plan the units one after another, front first, and
queue the rest behind the leader.  AoWTCPCK.dpl.

THE PROBLEM (owner, 2026-09-24)
-------------------------------
Box-select several units in tactical combat and click a hex: every unit is planned as if its
group-mates stand still.  Three units sent down a one-hex corridor detour, because "the guy in
front is blocking me", although he is in the selection and moving.

VANILLA (TCombatUnitSelectionControl; RE from Inioch's share8 `aowx-group-move-repath.md`, every
site byte-checked vanilla in ours on 2026-09-24)
    * Preview, `ExecuteMoveSelection 0x41E408`: clears all paths, bubble-sorts the selection by hex
      distance to the mouse hex (TList.Exchange, 0x41E50A-0x41E61C), paths unit 0 to the mouse hex,
      then gives every other unit the SAME OFFSET from the target that it had from unit 0
      (dHXtoHN 0x4022B4 + CenterHNtoHX 0x4022AC) -- the group's shape copied onto the target.  A
      column survives a straight corridor and lands in the walls at a bend.
    * `CalculateMovePath 0x41D678` (selection VMT+8; eax=ctl edx=index ecx=x, push y, push level,
      ret 8) drops temporary TMovementHS markers for every OTHER unit that has a path: flag 0 on its
      destination, flag 1 on its origin.  Only CanMoveOn (VMT+0xD0, may I END here) honours them; the
      transit test CanMoveOver (VMT+0xD4) ignores them, so nobody can walk THROUGH a hex a
      group-mate is leaving, and anyone may walk through a hex another has reserved.
    * `TTacticalCombatUnitHS.CanMoveOn` own-hex branch writes cost 0 on a group-mate's origin
      (0x42083A), which bends reconstructed paths through those hexes (vanilla bug).
    * Click, `MoveUnits 0x41E280` -> `SetupMultiTCUnitMove 0x40F788`: bubble-sorts by path length
      (0x40F81C) and executes the FROZEN preview paths one after another (TMultiMoveTE, index 0 first).

THIS SCRIPT (owner rulings 2026-09-24: plan sequentially front-first; queue behind the leader;
"stop where blocked" on execution; memory aow1-group-move-design)
    CORE (preview and click run the same plan):
      1. order: repeatedly the unit with the FEWEST unordered group-mates on a shortest line from its
         origin to the target T (d(o,oj)+d(oj,T)==d(o,T)), ties by d(o,T) -- the front of the column
         first (Inioch's v3 rule, keyed on T);
      2. clear every path, then plan in that order, so the vanilla markers see exactly the units that
         will already have moved (origin free, destination taken) and the ones still standing;
      3. destination: the first unit that can reach T takes it (the leader).  Every later unit takes
         the first candidate that works, walking back along the most recent mover's route from the
         hex behind its destination (at most 8 hexes), skipping hexes already taken or still occupied
         by a unit yet to move; if none works, vanilla's shape-copy slot; else it stays put;
      4. reach: a unit that cannot reach its hex this round is re-planned to the farthest hex it can
         reach (inline copy of `TMovepath.MovePointsToPos 0x557638D8`, using [ms+0x14]), so the ones
         behind queue behind where it really stops.  Never applied when [ms+0x14] <= 0;
      5. click only: the selection list is physically reordered to the plan order (TList.Exchange on
         [wrapper+8]) and the vanilla sort at 0x40F81C is skipped, so execution follows the plan.
      Units that vanilla's own preview test says cannot move ([[ms+0x10]+0x1C] VMT+0x64) stay put.
    PASS-THROUGH (Inioch's design, re-caved): TTacticalCombatUnitHS VMT+0xD4 -> a unit hex is
      passable when a flag-1 marker (a group-mate leaving) sits on it at hn 0, else vanilla
      (tail-jump to the original thunk 0x402A94); TMovementHS VMT+0xD4 -> a flag-0 marker (someone's
      reserved destination) blocks transit on its own hex (hn 0), anything else passes.
    ORIGIN COST: hook 0x42083A stores the hex's real terrain cost ([mc + terrain*16 + overlay +
      0x31], the part branch's formula at 0x420B0C) instead of 0, with vanilla's bounds (terrain
      0..15, overlay -1..14; outside them it keeps vanilla's 0).

Markers exist only inside the local player's group-move planning, so AI pathing is unaffected.
Paths are fixed before the tokens are built and travel inside them: multiplayer-safe.  No roll.
More than 64 units, or no reachable target: vanilla.

SITES (all vanilla on 2026-09-24)
    0x41E7F7  preview: `jmp 0x41EDD9` (end of the shape-copy loop) -> stub_preview
    0x41E2B0  click:   `call 0x40F788` rel32 retargeted -> stub_click (tail-jumps 0x40F788)
    0x40F81C  SetupMultiTCUnitMove sort: `7E 6B` -> `EB 6B`
    0x412DDC  TTacticalCombatUnitHS VMT+0xD4: 0x402A94 -> cave_unit   (.reloc entry kept)
    0x431214  TMovementHS VMT+0xD4: 0x401B5C -> cave_marker            (.reloc entry kept)
    0x42083A  `mov eax,[ebp-0xC] / xor edx,edx / mov [eax],edx` -> jmp cave_origin (+2 NOP)
    Zone 0x439800-0x43A3FF (reserved to this script).  Caves are PIC (call/pop delta).

USAGE
    python build_group_move_tc.py            verify / dry run (writes nothing)
    python build_group_move_tc.py --dis      also disassemble the caves
    python build_group_move_tc.py --apply    install (or rewrite the caves in place)
    python build_group_move_tc.py --undo     restore all six sites and zero the zone
"""
import os, sys, struct, argparse, subprocess

sys.dont_write_bytecode = True
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TARGET = os.path.join(GAME, "AoWTCPCK.dpl")
IMAGE_BASE = 0x400000

ZONE_LO, ZONE_HI = 0x439800, 0x43A400
MAXN = 64
G_COMBATMAP = 0x46C064
MARKER_VMT = 0x431140
GETMS, LIST_EXCHANGE = 0x40275C, 0x401534
XYL_GET, XYL_CLEAR, DHX = 0x401B1C, 0x401B0C, 0x4022A4
SETUP_MULTI, PREVIEW_EXIT, CLICK_RET = 0x40F788, 0x41EDD9, 0x41E2B5
UNIT_THUNK, MARKER_THUNK = 0x402A94, 0x401B5C
ORIGIN_RESUME = 0x420841
THUNKS = (GETMS, LIST_EXCHANGE, XYL_GET, XYL_CLEAR, DHX)

H_PREVIEW, H_CLICK, H_SORT = 0x41E7F7, 0x41E2B0, 0x40F81C
SLOT_UNIT, SLOT_MARKER, H_ORIGIN = 0x412DDC, 0x431214, 0x42083A
ORIG_PREVIEW = bytes.fromhex("e9dd050000")
ORIG_CLICK = bytes.fromhex("e8d314ffff")
ORIG_SORT, NEW_SORT = bytes.fromhex("7e6b"), bytes.fromhex("eb6b")
ORIG_ORIGIN = bytes.fromhex("8b45f433d28910")

AOW_PROCS = ("AoW", "AoWz", "AoWCompat", "AoWzCompat", "AoWDevEd", "AoWzEd", "AoWEd", "AoWSetup")

# core frame (own ebp).  Locals -0x04..-0x60; six 64-dword arrays below them.
FR = 0x660
ORIG, DESTV, ORDER, CUR, TK, TKD = "-0x160", "-0x260", "-0x360", "-0x460", "-0x560", "-0x660"


def core_src():
    return f"""
        push ebp
        mov ebp, esp
        sub esp, {FR:#x}
        push ebx
        push esi
        push edi
        mov esi, eax
        mov [ebp-0x1C], edx
        mov edi, [eax+8]
        call k_anchor
    k_anchor:
        pop ebx
        sub ebx, k_anchor
        mov eax, [ebx+{G_COMBATMAP:#x}]
        mov eax, [eax+0x88]
        mov [ebp-0x20], eax
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov [ebp-4], eax
        cmp eax, 2
        jl k_done
        cmp eax, {MAXN}
        jg k_done
        mov dword ptr [ebp-0xC], 0
    k_fill:
        mov eax, [ebp-0xC]
        cmp eax, [ebp-4]
        jge k_fill_end
        mov [ebp+eax*4{CUR}], eax
        mov dword ptr [ebp+eax*4{TK}], 0
        call c_ms
        mov [ebp-0x48], eax
        call c_org
        mov edx, [ebp-0xC]
        mov [ebp+edx*4{ORIG}], eax
        mov dword ptr [ebp+edx*4{DESTV}], -1
        mov eax, [ebp-0x48]
        mov eax, [eax+8]
        cmp dword ptr [eax+8], 0
        jle k_fill_next
        xor edx, edx
        call {XYL_GET:#x}
        and eax, 0xFFFF
        mov edx, [ebp-0xC]
        mov [ebp+edx*4{DESTV}], eax
    k_fill_next:
        inc dword ptr [ebp-0xC]
        jmp k_fill
    k_fill_end:
        mov eax, [ebp{DESTV}]
        cmp eax, -1
        je k_done
        mov [ebp-0x2C], eax
        mov dword ptr [ebp-8], 0
    k_ord:
        mov eax, [ebp-8]
        cmp eax, [ebp-4]
        jge k_ord_end
        mov dword ptr [ebp-0x10], -1
        mov dword ptr [ebp-0x14], 0x7FFFFFFF
        mov dword ptr [ebp-0xC], 0
    k_cand:
        mov eax, [ebp-0xC]
        cmp eax, [ebp-4]
        jge k_cand_end
        cmp dword ptr [ebp+eax*4{TK}], 0
        jne k_cand_next
        mov eax, [ebp+eax*4{ORIG}]
        mov [ebp-0x3C], eax
        mov edx, [ebp-0x2C]
        call c_dist
        mov [ebp-0x34], eax
        mov dword ptr [ebp-0x38], 0
        mov dword ptr [ebp-0x18], 0
    k_way:
        mov eax, [ebp-0x18]
        cmp eax, [ebp-4]
        jge k_way_end
        cmp eax, [ebp-0xC]
        je k_way_next
        cmp dword ptr [ebp+eax*4{TK}], 0
        jne k_way_next
        mov eax, [ebp+eax*4{ORIG}]
        mov [ebp-0x48], eax
        mov edx, eax
        mov eax, [ebp-0x3C]
        call c_dist
        mov [ebp-0x4C], eax
        mov eax, [ebp-0x48]
        mov edx, [ebp-0x2C]
        call c_dist
        add eax, [ebp-0x4C]
        cmp eax, [ebp-0x34]
        jne k_way_next
        inc dword ptr [ebp-0x38]
    k_way_next:
        inc dword ptr [ebp-0x18]
        jmp k_way
    k_way_end:
        mov ecx, [ebp-0x34]
        cmp ecx, 0xFFF
        jbe k_d_ok
        mov ecx, 0xFFF
    k_d_ok:
        mov eax, [ebp-0x38]
        shl eax, 12
        or ecx, eax
        cmp ecx, [ebp-0x14]
        jge k_cand_next
        mov eax, [ebp-0xC]
        mov [ebp-0x10], eax
        mov [ebp-0x14], ecx
    k_cand_next:
        inc dword ptr [ebp-0xC]
        jmp k_cand
    k_cand_end:
        mov ecx, [ebp-0x10]
        cmp ecx, -1
        je k_ord_end
        mov edx, [ebp-8]
        mov [ebp+edx*4{ORDER}], ecx
        mov dword ptr [ebp+ecx*4{TK}], 1
        inc dword ptr [ebp-8]
        jmp k_ord
    k_ord_end:
        mov eax, [ebp-8]
        mov [ebp-4], eax
        mov dword ptr [ebp-0xC], 0
    k_clr:
        mov eax, [ebp-0xC]
        cmp eax, [ebp-4]
        jge k_clr_end
        call c_ms
        mov eax, [eax+8]
        call {XYL_CLEAR:#x}
        inc dword ptr [ebp-0xC]
        jmp k_clr
    k_clr_end:
        mov dword ptr [ebp-0x40], -1
        mov dword ptr [ebp-8], 0
    k_plan:
        mov eax, [ebp-8]
        cmp eax, [ebp-4]
        jge k_done
        mov ecx, [ebp+eax*4{ORDER}]
        mov [ebp-0x30], ecx
        cmp dword ptr [ebp-0x1C], 0
        je k_pos_ready
        mov dword ptr [ebp-0xC], 0
    k_fpos:
        mov eax, [ebp-0xC]
        cmp eax, [ebp-4]
        jge k_pos_ready
        mov edx, [ebp+eax*4{CUR}]
        cmp edx, [ebp-0x30]
        je k_fpos_found
        inc dword ptr [ebp-0xC]
        jmp k_fpos
    k_fpos_found:
        mov ecx, [ebp-8]
        cmp eax, ecx
        je k_fpos_same
        mov edx, [ebp+ecx*4{CUR}]
        mov [ebp+eax*4{CUR}], edx
        mov edx, [ebp-0x30]
        mov [ebp+ecx*4{CUR}], edx
        mov edx, ecx
        mov ecx, eax
        mov eax, [edi+8]
        call {LIST_EXCHANGE:#x}
    k_fpos_same:
        mov eax, [ebp-8]
        mov [ebp-0x30], eax
    k_pos_ready:
        mov eax, [ebp-0x30]
        call c_ms
        mov eax, [eax+0x10]
        mov eax, [eax+0x1C]
        mov edx, [eax]
        call dword ptr [edx+0x64]
        test al, al
        jne k_stay
        cmp dword ptr [ebp-0x40], -1
        jne k_queue
        mov eax, [ebp-0x2C]
        call c_attempt
        cmp eax, 1
        je k_path
        cmp eax, 2
        je k_stay
        jmp k_try_v
    k_queue:
        mov eax, [ebp-0x40]
        call c_ms
        mov eax, [eax+8]
        mov [ebp-0x50], eax
        mov ecx, [eax+8]
        mov [ebp-0x54], ecx
        mov dword ptr [ebp-0x44], 1
    k_q_loop:
        mov eax, [ebp-0x44]
        cmp eax, [ebp-0x54]
        jge k_try_v
        cmp eax, 9
        jge k_try_v
        mov edx, eax
        mov eax, [ebp-0x50]
        call {XYL_GET:#x}
        and eax, 0xFFFF
        call c_attempt
        cmp eax, 1
        je k_path
        cmp eax, 2
        je k_stay
        inc dword ptr [ebp-0x44]
        jmp k_q_loop
    k_try_v:
        mov eax, [ebp-8]
        mov eax, [ebp+eax*4{ORDER}]
        mov eax, [ebp+eax*4{DESTV}]
        cmp eax, -1
        je k_stay
        call c_attempt
        cmp eax, 1
        je k_path
    k_stay:
        mov eax, [ebp-0x30]
        call c_ms
        mov eax, [eax+8]
        call {XYL_CLEAR:#x}
        mov eax, [ebp-8]
        mov ecx, [ebp+eax*4{ORDER}]
        mov ecx, [ebp+ecx*4{ORIG}]
        mov [ebp+eax*4{TKD}], ecx
        jmp k_plan_next
    k_path:
        call c_reach
        mov eax, [ebp-0x30]
        mov [ebp-0x40], eax
        call c_ms
        mov eax, [eax+8]
        xor edx, edx
        call {XYL_GET:#x}
        and eax, 0xFFFF
        mov edx, [ebp-8]
        mov [ebp+edx*4{TKD}], eax
    k_plan_next:
        inc dword ptr [ebp-8]
        jmp k_plan
    k_done:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret

    c_ms:
        mov edx, eax
        mov eax, edi
        call {GETMS:#x}
        ret

    c_org:
        mov eax, [eax+0x10]
        mov eax, [eax+4]
        movzx edx, byte ptr [eax+0x11]
        shl edx, 8
        movzx eax, byte ptr [eax+0x10]
        or eax, edx
        ret

    c_dist:
        push ebx
        mov ebx, edx
        movzx ecx, bh
        push ecx
        movzx ecx, bl
        movzx edx, ah
        movzx eax, al
        call {DHX:#x}
        pop ebx
        ret

    c_try:
        mov [ebp-0x58], eax
        mov eax, [ebp-0x30]
        call c_ms
        mov eax, [eax+8]
        call {XYL_CLEAR:#x}
        mov eax, [ebp-0x58]
        mov edx, eax
        shr edx, 8
        and edx, 0xFF
        push edx
        push dword ptr [ebp-0x20]
        mov ecx, eax
        and ecx, 0xFF
        mov edx, [ebp-0x30]
        mov eax, esi
        mov ebx, [eax]
        call dword ptr [ebx+8]
        mov eax, [ebp-0x30]
        call c_ms
        mov eax, [eax+8]
        mov eax, [eax+8]
        ret

    c_attempt:
        mov [ebp-0x58], eax
        call c_taken
        test eax, eax
        jnz a_fail
        mov eax, [ebp-8]
        mov eax, [ebp+eax*4{ORDER}]
        mov eax, [ebp+eax*4{ORIG}]
        cmp eax, [ebp-0x58]
        je a_stay
        mov eax, [ebp-0x58]
        call c_try
        cmp eax, 1
        jg a_path
    a_fail:
        xor eax, eax
        ret
    a_path:
        mov eax, 1
        ret
    a_stay:
        mov eax, 2
        ret

    c_taken:
        mov ecx, [ebp-0x58]
        mov dword ptr [ebp-0x18], 0
    t_done_loop:
        mov eax, [ebp-0x18]
        cmp eax, [ebp-8]
        jge t_rest
        cmp ecx, [ebp+eax*4{TKD}]
        je t_yes
        inc dword ptr [ebp-0x18]
        jmp t_done_loop
    t_rest:
        mov eax, [ebp-8]
        inc eax
        mov [ebp-0x18], eax
    t_rest_loop:
        mov eax, [ebp-0x18]
        cmp eax, [ebp-4]
        jge t_no
        mov edx, [ebp+eax*4{ORDER}]
        cmp ecx, [ebp+edx*4{ORIG}]
        je t_yes
        inc dword ptr [ebp-0x18]
        jmp t_rest_loop
    t_yes:
        mov eax, 1
        ret
    t_no:
        xor eax, eax
        ret

    c_reach:
        mov eax, [ebp-0x30]
        call c_ms
        mov edx, [eax+0x14]
        mov eax, [eax+8]
        mov [ebp-0x5C], eax
        test edx, edx
        jle r_ret
        mov ecx, [eax+8]
        mov [ebp-0x60], ecx
        jmp r_chk
    r_loop:
        dec ecx
        mov eax, [ebp-0x5C]
        mov eax, [eax+4]
        movsx eax, byte ptr [eax+ecx*4+3]
        sub edx, eax
    r_chk:
        test ecx, ecx
        jle r_end
        test edx, edx
        jge r_loop
    r_end:
        test edx, edx
        jge r_have
        inc ecx
    r_have:
        test ecx, ecx
        jle r_ret
        mov edx, [ebp-0x60]
        dec edx
        cmp ecx, edx
        jge r_ret
        mov edx, ecx
        mov eax, [ebp-0x5C]
        call {XYL_GET:#x}
        and eax, 0xFFFF
        call c_try
    r_ret:
        ret
    """


def stub_preview_src(core):
    return f"""
        mov eax, [ebp-4]
        xor edx, edx
        call {core:#x}
        jmp {PREVIEW_EXIT:#x}
    """


def stub_click_src(core):
    return f"""
        push eax
        mov eax, [ebp-4]
        mov edx, 1
        call {core:#x}
        pop eax
        jmp {SETUP_MULTI:#x}
    """


def cave_unit_src():
    return f"""
        push eax
        push edx
        push ebx
        push esi
        push edi
        call u_anchor
    u_anchor:
        pop ebx
        sub ebx, u_anchor
        lea ebx, [ebx+{MARKER_VMT:#x}]
        mov esi, [edx+4]
        movzx ecx, byte ptr [esi+0xD]
        movzx eax, byte ptr [esi+0xC]
        mov esi, [esi+8]
        lea edi, [esi+eax*4]
    u_loop:
        dec ecx
        js u_vanilla
        mov edx, [esi+ecx*4]
        test edx, edx
        jz u_loop
        cmp [edx], ebx
        jne u_loop
        cmp byte ptr [edi+ecx], 0
        jne u_loop
        cmp byte ptr [edx+0xC], 0
        je u_loop
        pop edi
        pop esi
        pop ebx
        pop edx
        pop eax
        mov eax, 1
        ret
    u_vanilla:
        pop edi
        pop esi
        pop ebx
        pop edx
        pop eax
        jmp {UNIT_THUNK:#x}
    """


def cave_marker_src():
    return """
        cmp byte ptr [edx+8], 0
        jne m_pass
        cmp byte ptr [eax+0xC], 0
        je m_block
    m_pass:
        mov eax, 1
        ret
    m_block:
        xor eax, eax
        ret
    """


def cave_origin_src():
    return f"""
        mov edx, [ebp-8]
        mov eax, [edx+4]
        movsx ecx, byte ptr [eax+0x14]
        cmp ecx, 0
        jl o_van
        cmp ecx, 15
        jg o_van
        movsx eax, byte ptr [eax+0x15]
        cmp eax, -1
        jl o_van
        cmp eax, 14
        jg o_van
        mov edx, [edx]
        shl ecx, 4
        add edx, ecx
        movsx eax, byte ptr [edx+eax+0x31]
        mov edx, [ebp-0xC]
        mov [edx], eax
        jmp {ORIGIN_RESUME:#x}
    o_van:
        mov eax, [ebp-0xC]
        xor edx, edx
        mov [eax], edx
        jmp {ORIGIN_RESUME:#x}
    """


def asm(src, va):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)
    return bytes(enc)


def build():
    """-> [(name, va, bytes)] laid out 16-aligned from ZONE_LO."""
    out, cur = [], ZONE_LO
    core = asm(core_src(), cur)
    out.append(("core", cur, core))
    core_va = cur
    cur = (cur + len(core) + 15) & ~15
    for name, fn in (("stub_preview", lambda v: stub_preview_src(core_va)),
                     ("stub_click", lambda v: stub_click_src(core_va)),
                     ("cave_unit", lambda v: cave_unit_src()),
                     ("cave_marker", lambda v: cave_marker_src()),
                     ("cave_origin", lambda v: cave_origin_src())):
        blob = asm(fn(cur), cur)
        out.append((name, cur, blob))
        cur = (cur + len(blob) + 15) & ~15
    assert cur <= ZONE_HI, "caves overflow the zone: %#x" % cur
    return out


def va_of(caves, name):
    return next(v for n, v, _ in caves if n == name)


def kill_aow():
    for n in AOW_PROCS:
        if subprocess.run(["taskkill", "/F", "/IM", n + ".exe"],
                          capture_output=True, text=True).returncode == 0:
            print("  killed running %s.exe" % n)


def pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    return e, [struct.unpack_from("<IIII", d, e + 24 + opt + 40 * i + 8) for i in range(nsec)]


def va2off(d, va):
    rva = va - IMAGE_BASE
    for vsize, vaddr, rsize, raw in pe(d)[1]:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    sys.exit("ABORT: VA %08X is in no section" % va)


def relocs_in(d, lo, hi):
    e = pe(d)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    if not size:
        return []
    off = va2off(d, IMAGE_BASE + rva)
    end, hits = off + size, []
    while off < end:
        page, blk = struct.unpack_from("<II", d, off)
        if blk < 8:
            break
        for k in range((blk - 8) // 2):
            ent = struct.unpack_from("<H", d, off + 8 + 2 * k)[0]
            va = IMAGE_BASE + page + (ent & 0xFFF)
            if ent >> 12 and va < hi and va + 4 > lo:
                hits.append(va)
        off += blk
    return hits


def jumps_into(d, lo, hi, fn_lo, fn_hi):
    """Relative jumps/calls inside [fn_lo, fn_hi) whose target falls strictly inside (lo, hi)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    o = va2off(d, fn_lo)
    bad = []
    for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(bytes(d[o:o + fn_hi - fn_lo]), fn_lo):
        if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
            try:
                t = int(ins.op_str, 16)
            except ValueError:
                continue
            if lo < t < hi:
                bad.append((ins.address, t))
    return bad


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


def wanted(caves):
    """-> {site: (vanilla bytes, installed bytes)}"""
    return {
        H_PREVIEW: (ORIG_PREVIEW, b"\xE9" + rel32(H_PREVIEW, va_of(caves, "stub_preview"))),
        H_CLICK: (ORIG_CLICK, b"\xE8" + rel32(H_CLICK, va_of(caves, "stub_click"))),
        H_SORT: (ORIG_SORT, NEW_SORT),
        SLOT_UNIT: (struct.pack("<I", UNIT_THUNK), struct.pack("<I", va_of(caves, "cave_unit"))),
        SLOT_MARKER: (struct.pack("<I", MARKER_THUNK), struct.pack("<I", va_of(caves, "cave_marker"))),
        H_ORIGIN: (ORIG_ORIGIN, b"\xE9" + rel32(H_ORIGIN, va_of(caves, "cave_origin")) + b"\x90\x90"),
    }


def show(caves):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for name, va, blob in caves:
        print("\n  ---- %s @%08X (%d B)" % (name, va, len(blob)))
        for ins in md.disasm(blob, va):
            print("    %08X  %-24s %s %s" % (ins.address, ins.bytes.hex(" "), ins.mnemonic, ins.op_str))


def main():
    ap = argparse.ArgumentParser(description="tactical group move: sequential plan, queue behind the leader")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--undo", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()

    caves = build()
    want = wanted(caves)
    d = bytearray(open(TARGET, "rb").read())
    print("build_group_move_tc -- %s" % TARGET)

    # context: thunks must be `jmp [iat]`
    for t in THUNKS:
        o = va2off(d, t)
        if d[o:o + 2] != b"\xFF\x25":
            sys.exit("ABORT: thunk %08X is not `jmp [iat]` (%s)" % (t, bytes(d[o:o + 6]).hex(" ")))

    states = {}
    for site, (van, new) in want.items():
        o = va2off(d, site)
        cur = bytes(d[o:o + len(van)])
        if cur == van:
            states[site] = "vanilla"
        elif cur == new:
            states[site] = "installed"
        elif site in (SLOT_UNIT, SLOT_MARKER) and ZONE_LO <= struct.unpack("<I", cur)[0] < ZONE_HI:
            states[site] = "ours-moved"
        elif cur[:1] in (b"\xE8", b"\xE9") and site != H_SORT and \
                ZONE_LO <= site + 5 + struct.unpack("<i", cur[1:5])[0] < ZONE_HI:
            states[site] = "ours-moved"
        else:
            states[site] = "FOREIGN " + cur.hex(" ")
    for site, st in states.items():
        print("  %08X  %s" % (site, st))
    for name, va, blob in caves:
        print("  cave %-12s %08X  %4d B" % (name, va, len(blob)))
    zo, zh = va2off(d, ZONE_LO), va2off(d, ZONE_HI)
    zone = bytes(d[zo:zh])
    installed_caves = all(bytes(d[va2off(d, va):va2off(d, va) + len(b)]) == b for _n, va, b in caves)
    rl = relocs_in(d, H_PREVIEW, H_PREVIEW + 5) + relocs_in(d, H_CLICK, H_CLICK + 5) + \
        relocs_in(d, H_SORT, H_SORT + 2) + relocs_in(d, H_ORIGIN, H_ORIGIN + 7) + \
        relocs_in(d, ZONE_LO, ZONE_HI)
    slot_rl = [relocs_in(d, s, s + 4) for s in (SLOT_UNIT, SLOT_MARKER)]
    inner = jumps_into(d, H_ORIGIN, H_ORIGIN + 7, 0x42079C, 0x420CB4) + \
        jumps_into(d, H_PREVIEW, H_PREVIEW + 5, 0x41E408, 0x41EDE0)
    print("  zone %08X-%08X: %s" % (ZONE_LO, ZONE_HI, "zero" if not any(zone) else
                                    "our caves" if installed_caves else "NOT ZERO"))
    print("  .reloc under hooks/zone: %s; slot relocs present: %s" %
          (", ".join("%08X" % v for v in rl) or "none", [bool(x) for x in slot_rl]))
    print("  jumps into a hook's interior: %s" % (inner or "none"))
    if a.dis:
        show(caves)

    all_van = all(s == "vanilla" for s in states.values())
    all_ours = all(s in ("installed", "ours-moved") for s in states.values())
    state = "VANILLA" if all_van else "INSTALLED" if all_ours and installed_caves else \
        "OURS, CAVES DIFFER" if all_ours else "MIXED"
    print("state: %s" % state)
    if any(s.startswith("FOREIGN") for s in states.values()) or state == "MIXED":
        sys.exit("ABORT: sites are neither all vanilla nor all ours")
    if rl or inner or not all(slot_rl):
        sys.exit("ABORT: a .reloc entry or an interior jump conflicts with a hook "
                 "(or a VMT slot lost its .reloc)")

    if not (a.apply or a.undo):
        print("\n(dry run -- nothing written)")
        return
    if a.apply and state == "INSTALLED":
        print("\nalready installed -- nothing to do")
        return
    if a.undo and state == "VANILLA":
        print("\nalready vanilla -- nothing to do")
        return
    if a.apply and state == "VANILLA" and any(zone):
        sys.exit("ABORT: zone %08X-%08X is not zero" % (ZONE_LO, ZONE_HI))

    kill_aow()
    with open(TARGET, "r+b") as f:
        f.seek(zo)
        f.write(b"\0" * (zh - zo))
        if a.apply:
            for _n, va, blob in caves:
                f.seek(va2off(d, va))
                f.write(blob)
        for site, (van, new) in want.items():
            f.seek(va2off(d, site))
            f.write(new if a.apply else van)
    back = open(TARGET, "rb").read()
    for site, (van, new) in want.items():
        o = va2off(back, site)
        assert back[o:o + len(van)] == (new if a.apply else van), "%08X did not stick" % site
    print("\n%s" % ("APPLIED" if a.apply else "UNDONE -- six sites vanilla, zone zeroed"))


if __name__ == "__main__":
    main()
