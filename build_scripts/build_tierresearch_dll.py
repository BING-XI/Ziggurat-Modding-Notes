#!/usr/bin/env python3
r"""
AoW1 TIER RESEARCH -- DLL mechanics layer (AoWEPACK.dpl).

Researching any spell of a (sphere, tier) group completes the WHOLE group; research cost is a
flat per-tier ladder; day-1 free spells become "one full tier-1 sphere".

Three caves in the free cave zone (see Spell_Research_System_2026-07-18.md):

  cave_grant @0x5580ED80 -- replaces `call ExecuteSpellResearched` @0x5577CDC4 (the NewTurn
      research-COMPLETION site only; Tomes/day-1 use other paths and stay single-spell).
      Runs the original call, then walks the spell registry and ExecuteSpellResearched()s every
      spell with the same sphere+tier (category<=2, vmt+0x64 enabled). Idempotent by design
      (ExecuteSpellResearched IndexOf-guards).

  cave_cost @... -- replaces `mov eax,[eax+0x18]; mov [ebx+0x38],eax` @0x5577D569 in
      ExecuteResearchSpell: research points = 100 << (tier-1)  => 100/200/400/800 (tier clamped
      1..4). Position-independent, no globals. Applies to human+AI symmetrically; all turn
      counters derive from +0x38 so every display follows.

  cave_day1 @... -- replaces the day-1 triple-random-spell block: entry hook @0x5577CC72
      (after the day1/active/not-preseeded guards, esi=magic), returns to 0x5577CD4A.
      New logic: collect the leader's picked spheres (GetSpherePicks(s)>0 for s=1..6); pick one
      via Map.Random (Cosmos fallback if none); add ALL tier-1 spells of that sphere
      (category<=2, vmt+0x64, not already researched) directly to the researched list --
      same determinism model as vanilla (Map.Random, lockstep NewTurn).

Globals ([0x558FA044] AoWHSSet, [0x558FA040] AoWHSMap) are reached via the call/pop
rebase-delta idiom (the DPL never loads at preferred base; caves have no .reloc entries).
In-module calls are rel32 (rebase-safe).

Layered on the existing patch stack; backup: AoWEPACK.dpl.pre-tierresearch.
Dry-run by default; --apply to write. Idempotent, verify-before-write.

cave_day1 v2 (2026-09-24) -- A CALLABLE ROUTINE, for build_pbem_leadersetup.py stage 2
--------------------------------------------------------------------------------------
v1 was entered by `jmp` at 0x5577CC72 and left by `jmp 0x5577CD4A`, so nothing could CALL it.
build_pbem_leadersetup.py (07-ui.md section 10) defers the day-1 grant of a PBEM human leader
until the leader has picked new spheres in the turn-1 window, then runs THIS grant from its
C_APPLY with ESI = the player's TPlayerMagicControl.  v2 makes that possible with the smallest
change that keeps the NewTurn path equivalent:

    0x5577CC72  E9 <cave_day1> 90 90    ->  E8 <cave_day1> 90 90     (jmp -> call)
    0x5577CC79  E8 2A 44 F8 FF (dead)   ->  E9 <0x5577CD4A>          (new: the return path)
    cave tail   add esp,8 ; jmp 0x5577CD4A   ->   add esp,8 ; ret ; 4 zero bytes

The routine keeps v1's register contract: IN esi = magic; clobbers eax/ecx/edx/ebx/edi/ebp;
preserves esi; stack balanced.  0x5577CC79 is inside vanilla's replaced triple-random block,
dead since v1 (its only entry was the fall-through from 0x5577CC72; nothing branches into
0x5577CC7A..0x5577CC7D; no .reloc covers it).  The two `nop`s at 0x5577CC77/78 are now
EXECUTED on the way back: they are bytes the neutralised .reloc entry 0x5577CC75
(build_relocfix.py) used to cover, and that entry stays neutralised.

WHY IN PLACE HERE, not a chain from build_pbem_leadersetup: the grant must be callable as a
routine, and a jmp-exit cave can only be "called" through a synthetic return frame.  The only
alternatives were this re-tune or a second copy of the grant in the other script, which would
drift silently the first time this grant changes.
⚠ COUPLING: build_pbem_leadersetup.py's C_APPLY CALLS 0x5580EE30 and pins this routine's bytes
(sha256) on every run.  Never revert cave_day1 to v1 (jmp-exit) while that feature is
installed -- C_APPLY's call would never return.  Undo order: build_pbem_leadersetup.py --undo
first.  (This script has no --undo of its own.)  --apply re-tunes an installed v1 in place.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL  = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-tierresearch")

# ---- fixed addresses (preferred-base VAs) ----
EXEC_RESEARCHED = 0x5577CBF8      # TPlayerMagicControl.ExecuteSpellResearched(eax=magic, edx=id)
GETSPELL        = 0x55779AC8      # TSpellControl.GetSpell(eax=ctl, edx=id) -> TSpell*
GETCOUNT        = 0x55779AC0      # TSpellControl.GetCount(eax=ctl) -> int
GETPICKS        = 0x5578B17C      # TLeader.GetSpherePicks(eax=leader, dl=sphere) -> al
MAPRANDOM       = 0x5577827C      # TAoWHSMap.Random(eax=map, edx=n) -> 0..n-1
IL_INDEXOF      = 0x55702EA4      # Engine.TIntegerList.IndexOf(eax=list, edx=v) -> idx/-1
IL_ADD          = 0x55702E74      # Engine.TIntegerList.Add(eax=list, edx=v)
HSSET           = 0x558FA044      # -> AoWHSSet (registry at +0x84)
HSMAP           = 0x558FA040      # -> AoWHSMap

HOOK_GRANT = 0x5577CDC4           # E8 -> ExecuteSpellResearched   (5 bytes)
HOOK_COST  = 0x5577D569           # 8B 40 18 89 43 38              (6 bytes)
HOOK_DAY1  = 0x5577CC72           # B2 01 A1 58 C9 8F 55           (7 bytes)
DAY1_RET   = 0x5577CD4A
HOOK_DAY1_BACK = 0x5577CC79       # v2: E8 2A 44 F8 FF (dead vanilla) -> jmp DAY1_RET (5 bytes)
HOOK_EVTEXT = 0x5577C4B4          # 8B 40 08 89 45 F8 in TPlayerMagicEventLog.GetText (6 bytes)
SPHERE_RSTRTAB = 0x558E8118       # AoWE.TMagicSphereRStr — array of RStr rec ptrs (relocated)
LOADRES    = 0x55701210           # System.LoadResString(eax=rec, edx=&dest)
TRANSLATE  = 0x557249FC           # AoWE.TranslateRStr(eax=str, edx=&dest)
LSTRCATN   = 0x55701198           # System.@LStrCatN thunk (eax=&dest, edx=n, parts pushed)
BSS_EVSTR  = 0x558FA840           # BSS-slack LStr slot for the built "Death I" (prev use ends 0x558FA82C)

CAVE_GRANT = 0x5580ED80           # free zone (last used byte was 0x5580ED7D)
ZONE_END   = 0x5580F400

ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

def assemble_pic(src_fn, addr, npops):
    """Two-pass assemble: src_fn(pop_vas) must place `pop ecx` right after each `call L`;
    iterate until guessed pop VAs converge (call/pop rebase-delta idiom)."""
    guess = [addr + 0x40*(i+1) for i in range(npops)]
    for _ in range(6):
        code = bytes(ks.asm(src_fn(guess), addr)[0])
        pops = [ins.address for ins in cs.disasm(code, addr)
                if ins.mnemonic == "pop" and ins.op_str == "ecx"]
        pops = pops[:npops]
        if pops == guess:
            return code
        assert len(pops) == npops, f"expected {npops} pops, found {len(pops)}"
        guess = pops
    raise RuntimeError("two-pass assembly did not converge")

# ---- cave_grant: complete the whole (sphere,tier) group on research completion ----
# in: eax=magic, edx=finished spell id (call-hooked; must behave like ExecuteSpellResearched)
def src_grant(p):
    return f"""
        push ebx
        push esi
        push edi
        push ebp
        mov esi, eax
        mov edi, edx
        call 0x{EXEC_RESEARCHED:X}
        call L1
    L1: pop ecx
        sub ecx, 0x{p[0]:X}
        mov ebp, ecx
        mov eax, [ebp + 0x{HSSET:X}]
        mov eax, [eax + 0x84]
        mov edx, edi
        call 0x{GETSPELL:X}
        test eax, eax
        jz Ldone
        mov bx, word ptr [eax + 0x20]
        mov eax, [ebp + 0x{HSSET:X}]
        mov eax, [eax + 0x84]
        call 0x{GETCOUNT:X}
        mov edi, eax
    Lloop:
        dec edi
        js Ldone
        mov eax, [ebp + 0x{HSSET:X}]
        mov eax, [eax + 0x84]
        mov edx, edi
        call 0x{GETSPELL:X}
        test eax, eax
        jz Lloop
        cmp word ptr [eax + 0x20], bx
        jnz Lloop
        cmp byte ptr [eax + 0x22], 2
        ja Lloop
        mov ecx, [eax]
        call dword ptr [ecx + 0x64]
        test al, al
        jz Lloop
        mov edx, edi
        mov eax, esi
        call 0x{EXEC_RESEARCHED:X}
        jmp Lloop
    Ldone:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """

# ---- cave_cost: +0x38 = 100 << (tier-1), tier clamped 1..4 ----
# in: eax=TSpell*, ebx=magic  (replaces mov eax,[eax+0x18]; mov [ebx+0x38],eax)
SRC_COST = """
    movzx ecx, byte ptr [eax + 0x21]
    mov eax, 100
    dec ecx
    js Lstore
    cmp ecx, 3
    jle Lshift
    mov ecx, 3
Lshift:
    shl eax, cl
Lstore:
    mov [ebx + 0x38], eax
    ret
"""

# ---- cave_day1: grant all tier-1 spells of one random picked sphere ----
# in: esi=magic (ebx/edi/ebp free to clobber, NewTurn body regs); exits jmp DAY1_RET
def src_day1(p, v1=False):
    TAIL = f"jmp 0x{DAY1_RET:X}" if v1 else "ret"      # v2: a callable routine
    return f"""
        call L1
    L1: pop ecx
        sub ecx, 0x{p[0]:X}
        mov ebp, ecx
        sub esp, 8
        xor ebx, ebx
        mov edi, 1
    Lsph:
        mov eax, [esi + 0x10]
        mov eax, [eax + 0xd4]
        mov edx, edi
        call 0x{GETPICKS:X}
        test al, al
        jz Lnext
        mov eax, edi
        mov byte ptr [esp + ebx], al
        inc ebx
    Lnext:
        inc edi
        cmp edi, 7
        jl Lsph
        xor edi, edi
        test ebx, ebx
        jz Lchosen
        mov edx, ebx
        mov eax, [ebp + 0x{HSMAP:X}]
        call 0x{MAPRANDOM:X}
        movzx edi, byte ptr [esp + eax]
    Lchosen:
        mov eax, [ebp + 0x{HSSET:X}]
        mov eax, [eax + 0x84]
        call 0x{GETCOUNT:X}
        mov ebx, eax
    Lgl:
        dec ebx
        js Lend
        mov eax, [ebp + 0x{HSSET:X}]
        mov eax, [eax + 0x84]
        mov edx, ebx
        call 0x{GETSPELL:X}
        test eax, eax
        jz Lgl
        cmp byte ptr [eax + 0x21], 1
        jnz Lgl
        movzx ecx, byte ptr [eax + 0x20]
        cmp ecx, edi
        jnz Lgl
        cmp byte ptr [eax + 0x22], 2
        ja Lgl
        mov ecx, [eax]
        call dword ptr [ecx + 0x64]
        test al, al
        jz Lgl
        mov eax, [esi + 0x30]
        mov edx, ebx
        call 0x{IL_INDEXOF:X}
        inc eax
        jnz Lgl
        mov eax, [esi + 0x30]
        mov edx, ebx
        call 0x{IL_ADD:X}
        jmp Lgl
    Lend:
        add esp, 8
        {TAIL}
    """

# ---- cave_evtext: research event/popup text = "Death I researched" (tier, not spell) ----
# Replaces `mov eax,[spell+8]; mov [ebp-8],eax` in TPlayerMagicEventLog.GetText's research
# branch: builds "{SphereRStr} {Roman}" into the BSS LStr slot and stores it in the caller's
# TVarRec ([ebp-8]; the 0x0B type byte is written by the untouched next instruction).
# Caller locals [ebp-0x10]/[ebp-0xC] are safe scratch (rewritten right after by the caller).
# Literals live in the cave (read-only OK: refcount -1, only the dest slot is written).
def build_evtext(cave_va):
    data = bytearray()
    def lit(s):
        while len(data) % 4: data.append(0)
        data.extend(struct.pack("<ii", -1, len(s)))
        off = len(data)
        data.extend(s.encode("latin1") + b"\x00")
        return cave_va + off
    romtab_off = 0
    data.extend(b"\x00" * 32)
    p_sp = lit(" ")
    roman = [lit("I"), lit("II"), lit("III"), lit("IV")]
    romptrs = [roman[0], roman[0], roman[1], roman[2], roman[3], roman[3], roman[3], roman[3]]
    struct.pack_into("<8I", data, romtab_off, *romptrs)
    while len(data) % 16: data.append(0)
    code_va = cave_va + len(data)

    def src(p):
        # NOTE: TMagicSphereRStr holds loaded STRING VALUES, not resourcestring recs —
        # pass straight to TranslateRStr (the working cave_title idiom). Feeding them to
        # LoadResString was the v7.5 "LogbookChanged" exception.
        return f"""
        push ebx
        push esi
        push edi
        mov esi, eax
        call L1
    L1: pop ecx
        sub ecx, 0x{p[0]:X}
        mov edi, ecx
        test esi, esi
        jz Lnil
        movzx eax, byte ptr [esi+0x20]
        mov eax, [edi + eax*4 + 0x{SPHERE_RSTRTAB:X}]
        lea edx, [ebp-0xC]
        call 0x{TRANSLATE:X}
        push dword ptr [ebp-0xC]
        lea eax, [edi + 0x{p_sp:X}]
        push eax
        movzx eax, byte ptr [esi+0x21]
        and eax, 7
        mov eax, [edi + eax*4 + 0x{cave_va:X}]
        add eax, edi
        push eax
        lea eax, [edi + 0x{BSS_EVSTR:X}]
        mov edx, 3
        call 0x{LSTRCATN:X}
        mov eax, [edi + 0x{BSS_EVSTR:X}]
        mov [ebp-8], eax
        pop edi
        pop esi
        pop ebx
        ret
    Lnil:
        xor eax, eax
        mov [ebp-8], eax
        pop edi
        pop esi
        pop ebx
        ret
    """
    code = assemble_pic(src, code_va, 1)
    return bytes(data) + code, code_va

# ---- assemble ----
cave_grant = assemble_pic(src_grant, CAVE_GRANT, 1)
CAVE_COST  = (CAVE_GRANT + len(cave_grant) + 15) & ~15
cave_cost  = bytes(ks.asm(SRC_COST, CAVE_COST)[0])
CAVE_DAY1  = (CAVE_COST + len(cave_cost) + 15) & ~15
cave_day1  = assemble_pic(src_day1, CAVE_DAY1, 1)
cave_day1_v1 = assemble_pic(lambda p: src_day1(p, v1=True), CAVE_DAY1, 1)
assert len(cave_day1) < len(cave_day1_v1) and cave_day1[:-1] == cave_day1_v1[:len(cave_day1) - 1]
assert cave_day1[-4:] == bytes.fromhex("83c408c3"), "v2 must end add esp,8 ; ret"
DAY1_REGION = len(cave_day1_v1)   # v2 is written zero-padded to v1's length: no stale tail
# named literally so rng_audit.py --owners attributes the grant's synced draw (+0x46) here too;
# build_pbem_leadersetup.py's C_APPLY calls this exact address and pins these bytes
assert CAVE_DAY1 == 0x5580EE30, "cave_day1 moved -- build_pbem_leadersetup.py calls 0x5580EE30"
CAVE_EVT   = (CAVE_DAY1 + DAY1_REGION + 15) & ~15
cave_evt, EVT_CODE = build_evtext(CAVE_EVT)
CAVE_END   = CAVE_EVT + len(cave_evt)

for nm, va, code in (("cave_grant", CAVE_GRANT, cave_grant),
                     ("cave_cost", CAVE_COST, cave_cost),
                     ("cave_day1", CAVE_DAY1, cave_day1)):
    print(f"{nm} @ {va:08X}  ({len(code)} bytes)")
    for ins in cs.disasm(code, va):
        print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<24} {ins.mnemonic} {ins.op_str}")
    print()
print(f"cave_evtext @ {CAVE_EVT:08X} (data) / code @ {EVT_CODE:08X}  ({len(cave_evt)} bytes total)")
assert CAVE_END <= ZONE_END, f"cave overflow: end {CAVE_END:#x} > {ZONE_END:#x}"

def rel(site, dest):
    return struct.pack("<i", dest - (site + 5))

hook_grant_orig = b"\xE8" + rel(HOOK_GRANT, EXEC_RESEARCHED)
hook_grant_new  = b"\xE8" + rel(HOOK_GRANT, CAVE_GRANT)
hook_cost_orig  = bytes.fromhex("8b 40 18 89 43 38".replace(" ", ""))
hook_cost_new   = b"\xE8" + rel(HOOK_COST, CAVE_COST) + b"\x90"
hook_day1_orig  = bytes.fromhex("b2 01 a1 58 c9 8f 55".replace(" ", ""))
hook_day1_v1    = b"\xE9" + rel(HOOK_DAY1, CAVE_DAY1) + b"\x90\x90"
hook_day1_new   = b"\xE8" + rel(HOOK_DAY1, CAVE_DAY1) + b"\x90\x90"      # v2: call, not jmp
back_day1_orig  = bytes.fromhex("e82a44f8ff")                          # dead vanilla call
back_day1_new   = b"\xE9" + rel(HOOK_DAY1_BACK, DAY1_RET)               # v2: the return path
hook_evt_orig   = bytes.fromhex("8b 40 08 89 45 f8".replace(" ", ""))
hook_evt_new    = b"\xE8" + rel(HOOK_EVTEXT, EVT_CODE) + b"\x90"

def load_secs(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e+6)[0]
    optsz = struct.unpack_from('<H', d, e+20)[0]
    sect = e + 24 + optsz
    secs = []
    for i in range(nsec):
        b = sect + i*40
        vs, va, rs, raw = struct.unpack_from('<IIII', d, b+8)
        secs.append((d[b:b+8].rstrip(b'\0').decode('latin1'), va, vs, raw, rs))
    return secs

IB = 0x55700000
def va2off(secs, va):
    r = va - IB
    for nm, v, vs, raw, rs in secs:
        if v <= r < v + max(vs, rs):
            return raw + (r - v)
    raise ValueError(hex(va))

def main():
    d = bytearray(open(DLL, 'rb').read())
    secs = load_secs(d)
    day1_region_new = cave_day1 + bytes(DAY1_REGION - len(cave_day1))
    # (file offset, vanilla, current build, v1 build or None, description)
    patches = [
        (va2off(secs, HOOK_GRANT), hook_grant_orig, hook_grant_new, None, "hook: NewTurn completion -> cave_grant"),
        (va2off(secs, HOOK_COST),  hook_cost_orig,  hook_cost_new,  None, "hook: ExecuteResearchSpell cost -> cave_cost"),
        (va2off(secs, HOOK_DAY1),  hook_day1_orig,  hook_day1_new,  hook_day1_v1, "hook: day-1 freebies -> call cave_day1"),
        (va2off(secs, HOOK_DAY1_BACK), back_day1_orig, back_day1_new, None, "v2: return path jmp 0x5577CD4A"),
        (va2off(secs, HOOK_EVTEXT), hook_evt_orig,  hook_evt_new,   None, "hook: research event text -> cave_evtext"),
        (va2off(secs, CAVE_GRANT), bytes(len(cave_grant)), cave_grant, None, f"cave_grant @ {CAVE_GRANT:08X}"),
        (va2off(secs, CAVE_COST),  bytes(len(cave_cost)),  cave_cost,  None, f"cave_cost @ {CAVE_COST:08X}"),
        (va2off(secs, CAVE_DAY1),  bytes(DAY1_REGION),     day1_region_new, cave_day1_v1, f"cave_day1 @ {CAVE_DAY1:08X}"),
        (va2off(secs, CAVE_EVT),   bytes(len(cave_evt)),   cave_evt,   None, f"cave_evtext @ {CAVE_EVT:08X}"),
    ]
    ok = True; already = 0; todo = 0; all_vanilla = True; v1_seen = 0
    for off, orig, new, prev, desc in patches:
        cur = bytes(d[off:off+len(new)])
        if cur != orig: all_vanilla = False
        if cur == new: already += 1
        elif cur == orig: todo += 1
        elif prev is not None and cur == prev: todo += 1; v1_seen += 1
        else:
            print(f"MISMATCH {desc}:\n  exp {orig.hex(' ')}\n  got {cur.hex(' ')}"); ok = False
    print(f"{already} already applied, {todo} to patch ({v1_seen} of them v1 -> v2), {len(patches)} total; caves end {CAVE_END:08X} (zone to {ZONE_END:08X})")
    if not ok:
        print("ABORT: byte mismatch (different/partial patch state)."); return 1
    if '--apply' not in sys.argv:
        print("Dry run OK. Re-run with --apply to write."); return 0
    if todo == 0:
        print("Nothing to do."); return 0
    if all_vanilla:                  # ⚠ a snapshot ONLY from a proved-unpatched file (v2: was `not exists`)
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copyfile(DLL, BACKUP); print(f"backup -> {BACKUP}")
    else:
        print("patched file (re-tune in place) -- no backup")
    for off, orig, new, prev, desc in patches:
        d[off:off+len(new)] = new
    open(DLL, 'wb').write(d)
    print("applied.")
    return 0

sys.exit(main())
