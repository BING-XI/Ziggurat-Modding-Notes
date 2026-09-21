#!/usr/bin/env python3
r"""
AoW1 mod -- "simfly": fast-combat-equivalent flying economics in TCombatPredictor.

WHY (full analysis: Modding Resources/Raze_CombatPredictor_Analysis.md, esp. §4/§6b/§8):
The battle estimator TCombatPredictor (used by the raze gate AND the city civil-status
garrison-vs-rebels check) zeroes melee damage against flyers (TStrikeAbility.GetDamageValueEx
@0x55766C90, ability id 1) and models NO retaliation. Ground melee units are silently
excluded from the sim, so a single Great Eagle "wipes" an entire militia cost-free --
razes max cities, and a lone flying garrison counts as a Strong occupation force.
Real fast combat charges the flyer retaliation for every exchange (fcExecuteCombatCommand
executes the defender's strikes too); this patch reproduces those economics inside the
estimator, scoped by a flag so ONLY the three "hypothetical militia" sims change:

    TStructure.CanRaze            Execute call @ 0x5575FC8B
    TCity.GetCivilStatus          Execute call @ 0x557AC3AB
    TCity.ListCivilStatusInfo     Execute call @ 0x557ABFD2

AI attack planning, AI build priorities, tactical wall CV, real/auto combat: byte-identical
(they run with the flag clear).

MECHANISM (3 caves + 5 hooks, all rel32 / delta-addressed => rebase-safe per aow1-dpl-rebasing):

  cave_exec @0x5580C810 -- replaces the 3 `CALL TCombatPredictor.Execute` sites:
      set flag=1, CALL Execute, clear flag, return AL (result byte -- the two civil-status
      callers consume it). EAX(predictor) passes straight through to Execute.

  cave_cv @0x5580C850 -- replaces `CALL TMeleeRound.GetDefenderDV` @0x55766CED inside
      TStrikeAbility.GetDamageValueEx. Flag clear: tail-jmp to the real GetDefenderDV
      (byte-identical behaviour). Flag set: return 0, so rec[2]=0 and GetCombatValue's
      a*a/(d+a) formula yields RAW AttackerDV. Rationale: a2/(a+d) is vanilla's fuzzy
      retaliation *discount*; once cave_retal charges retaliation as real damage, keeping
      the discount would double-count it (flyer would need (a+d)/a more rounds than a
      real fast combat). The flying gate itself stays 100% vanilla -- melee still cannot
      target flyers, here as in every real combat engine.

  cave_retal @0x5580C880 -- replaces the ExecuteRound damage site @0x5572AAD4
      (`SUB [EAX+0x4C],EDX ; MOV BL,1`, exactly 5 bytes; EAX=target cpUnit, EDX=damage,
      ESI=attacker cpUnit, EDI loop counter preserved, BL=acted flag). Replicates the
      2 instructions, then under the flag: if the attacker's real unit has Strike (0x15)
      and its melee AttackerDV for THIS pair >= the damage just dealt (i.e. melee was its
      chosen max-CV attack -- exact under cave_cv, so ranged attacks charge nothing),
      recompute the pair's TMeleeRound and subtract GetDefenderDV (the target's
      retaliation) from the ATTACKER's HP. Per pair per round this equals one real
      fast-combat exchange: deal AttackerDV, eat DefenderDV.

  Flag byte lives at 0x558FA800 -- in the BSS section's page slack (BSS spans RVA
  0x1EA000..0x1FA231, mapped through 0x1FAFFF as zero-initialized READ-WRITE memory;
  bytes past 0x1FA231 are mapped, writable, zero and unused; no file bytes exist for it).
  LESSON (v1 crash): the CODE-section cave space is mapped read+execute -- fine for code
  and for data that is only READ, but a WRITE there raises an access violation (seen as
  "Access violation ... Write of address xxxC808" on city select). Mutable cave state
  must live in a writable section; BSS slack is the clean spot.
  Caves address the flag and the AoWHSSet global (0x558FA044) via call/pop rebase-delta.

EXPECTED IN-GAME EFFECT:
  * Lone Great Eagle on a big city: raze DENIED (it dies to retaliation + archers in-sim).
  * Eagle vs 1-2 weak defenders it genuinely beats one-by-one in fast combat: still allowed.
  * Lone flying garrison no longer fakes "Oppressed"/"Strong occupation forces";
    a garrison that would genuinely beat the militia still intimidates without fighting.
  * AI held to the same standards (AI razing goes through the same CanRaze).

NOT included (later phases): raze-as-real-battle, rebellion battles, raze gate re-spec
(Patch 0/A), militia preview dialog. AoWTCPCK.dpl port = phase 2 (TCP/IP games).

Idempotent; verifies every original byte; dry-run by default, pass --apply (close all AoW binaries
first). Snapshot goes to `<game dir>\backups\AoWEPACK.dpl.pre-simfly`.

Revert: there is no --undo flag here, and copying the snapshot back is NOT a revert path -- it is a
whole-file copy, so it would silently destroy every feature applied to AoWEPACK.dpl since. Undo by
hand: restore each patch site's ORIG bytes from the table below. There is no snapshot layer left at
all (both stacks were purged, 2026-08-08 / 2026-09-09).
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never the game root (rule 2026-09-03)
ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e+6)[0]
    optsize = struct.unpack_from("<H", data, e+20)[0]
    sec = e+24+optsize; secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw = struct.unpack_from("<IIII", data, sec+8)
        secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def mkva2off(base):
    def va2off(secs, va):
        rva = va-base
        for vaddr,vsize,raw,rsize in secs:
            if vaddr <= rva < vaddr+max(vsize,rsize):
                return raw+(rva-vaddr)
        raise ValueError(f"VA {va:08X} not mapped")
    return va2off
def rel32(src, dst): return struct.pack("<i", dst-(src+5))

DLL_BASE   = 0x55700000
EXECUTE    = 0x5572B028      # TCombatPredictor.Execute
GETDEFDV   = 0x55768064      # TMeleeRound.GetDefenderDV
GETATTDV   = 0x5576804C      # TMeleeRound.GetAttackerDV
CALCUNIT   = 0x55767A3C      # TMeleeRound.CalculateUnit (EAX=mr, EDX=attacker, ECX=target)
GETABILITY = 0x557501C0      # TAbilityControl.GetAbility (EAX=ctrl, EDX=id)
HSSET_PTR  = 0x558FA044      # link-time VA of the AoWHSSet global pointer

FLAG       = 0x558FA860      # 1 byte in BSS page slack: mapped RW, zero-init, no file bytes.
                             # ⚠ MOVED 2026-07-22 from 0x558FA800, which was NOT unused: it is also
                             # build_path_outerring.py's SCRATCH/SX, and that feature's cave_stash
                             # (hooked in TAbstractUnit.MovedTo) writes the move's centre X there on
                             # EVERY UNIT MOVE. Measured live via build_combatdiag.py: this byte read
                             # 0x08/0x1D/0x1B -- map coordinates -- at the start of ordinary battles,
                             # i.e. simfly's cave_cv/cave_retal were silently active in NORMAL combat
                             # (zeroed defender DVs -> SetupRoundTargets drops targets -> a round pump
                             # that can hang). It also invalidated the old "simfly cannot leak into the
                             # AI" claim: the AI's direct TCombatPredictor.Execute calls were affected.
                             # Claimed BSS bytes: 0x800/0x801 path SX/SY · 0x801-0x80C razebattle ·
                             # 0x810/0x820/0x82C combatlog · 0x840 tierresearch. Free from 0x844 up.
CAVE_EXEC  = 0x5580C810
CAVE_CV    = 0x5580C850
CAVE_RETAL = 0x5580C880

# hook sites (all verified identical in live AoWEPACK.dpl and the vanilla backup)
SITE_RAZE   = 0x5575FC8B; ORIG_RAZE   = bytes.fromhex("e8 98 b3 fc ff")  # CALL Execute (CanRaze)
SITE_CIVST  = 0x557AC3AB; ORIG_CIVST  = bytes.fromhex("e8 78 ec f7 ff")  # CALL Execute (GetCivilStatus)
SITE_CIVLS  = 0x557ABFD2; ORIG_CIVLS  = bytes.fromhex("e8 51 f0 f7 ff")  # CALL Execute (ListCivilStatusInfo)
SITE_CV     = 0x55766CED; ORIG_CV     = bytes.fromhex("e8 72 13 00 00")  # CALL GetDefenderDV
SITE_RETAL  = 0x5572AAD4; ORIG_RETAL  = bytes.fromhex("29 50 4c b3 01")  # SUB [EAX+4C],EDX ; MOV BL,1

def assemble_pic(src_fn, addr, npops):
    """Two-pass: src_fn(popvas) -> asm text using the runtime VAs of each successive
    'pop ecx' (for the call/pop delta trick). Iterate until the guessed pop VAs match."""
    guess = [addr + 0x40*(i+1) for i in range(npops)]   # big values -> stable disp32 encodings
    for _ in range(6):
        code, _ = ks.asm(src_fn(guess), addr)
        code = bytes(code)
        pops = [ins.address for ins in cs.disasm(code, addr)
                if ins.mnemonic == "pop" and ins.op_str == "ecx"]
        assert len(pops) == npops, f"expected {npops} pops, found {len(pops)}"
        if pops == guess:
            return code
        guess = pops
    raise RuntimeError("two-pass assembly did not converge")

# ---- cave_exec: flag wrapper around TCombatPredictor.Execute ----
def src_exec(p):
    return f"""
        call ${{}}L1
    L1: pop ecx
        sub ecx, 0x{p[0]:X}
        mov byte ptr [ecx + 0x{FLAG:X}], 1
        call 0x{EXECUTE:X}
        push eax
        call L2
    L2: pop ecx
        sub ecx, 0x{p[1]:X}
        mov byte ptr [ecx + 0x{FLAG:X}], 0
        pop eax
        ret
    """.replace("${}L1", "L1")

# ---- cave_cv: rec[2]=0 under flag, else vanilla GetDefenderDV ----
def src_cv(p):
    return f"""
        call L1
    L1: pop ecx
        sub ecx, 0x{p[0]:X}
        cmp byte ptr [ecx + 0x{FLAG:X}], 0
        jnz Lzero
        jmp 0x{GETDEFDV:X}
    Lzero:
        xor eax, eax
        ret
    """

# ---- cave_retal: charge the target's retaliation to the attacker ----
def src_retal(p):
    return f"""
        sub dword ptr [eax + 0x4C], edx
        mov bl, 1
        call L1
    L1: pop ecx
        sub ecx, 0x{p[0]:X}
        cmp byte ptr [ecx + 0x{FLAG:X}], 0
        jz Ldone
        push eax
        push edx
        mov eax, dword ptr [esi + 4]
        mov edx, 0x15
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jz Lrestore
        call L2
    L2: pop ecx
        sub ecx, 0x{p[1]:X}
        mov eax, dword ptr [ecx + 0x{HSSET_PTR:X}]
        mov eax, dword ptr [eax + 0x80]
        mov edx, 0x15
        call 0x{GETABILITY:X}
        mov eax, dword ptr [eax + 0x28]
        push eax
        mov edx, dword ptr [esi + 4]
        mov ecx, dword ptr [esp + 8]
        mov ecx, dword ptr [ecx + 4]
        call 0x{CALCUNIT:X}
        mov eax, dword ptr [esp]
        call 0x{GETATTDV:X}
        cmp eax, dword ptr [esp + 4]
        jl Lpopmr
        mov eax, dword ptr [esp]
        call 0x{GETDEFDV:X}
        sub dword ptr [esi + 0x4C], eax
    Lpopmr:
        add esp, 4
    Lrestore:
        pop edx
        pop eax
    Ldone:
        ret
    """

cave_exec  = assemble_pic(src_exec,  CAVE_EXEC,  2)
cave_cv    = assemble_pic(src_cv,    CAVE_CV,    1)
cave_retal = assemble_pic(src_retal, CAVE_RETAL, 2)
assert CAVE_EXEC + len(cave_exec)  <= CAVE_CV,    "cave_exec overruns cave_cv"
assert CAVE_CV   + len(cave_cv)    <= CAVE_RETAL, "cave_cv overruns cave_retal"
assert CAVE_RETAL + len(cave_retal) <= 0x5580D640, "cave_retal overruns free space"

hook = lambda site, cave: b"\xE8" + rel32(site, cave)

# The three caves are rewritten IN PLACE when the FLAG address changes, so the currently-installed
# bytes must be an acceptable prior as well as the virgin zeros. Gated on our hooks already being
# present, which proves the bytes at those addresses are ours and not some other feature's.
_live_data = open(os.path.join(GAME, "AoWEPACK.dpl"), "rb").read()
_live_secs = load_sections(bytearray(_live_data)); _live_v2o = mkva2off(DLL_BASE)
def _live(va, n):
    try:
        o = _live_v2o(_live_secs, va); return bytes(_live_data[o:o+n])
    except Exception:
        return None
_HOOKED = _live(SITE_CV, len(ORIG_CV)) == hook(SITE_CV, CAVE_CV)
def _own(va, priors):
    if _HOOKED:
        lb = _live(va, len(priors[-1]))
        if lb and lb not in priors:
            return priors + [lb]
    return priors

dll_patches = [
    (CAVE_EXEC,  _own(CAVE_EXEC,  [bytes(len(cave_exec))]),  cave_exec,  "cave_exec (flag wrapper around Execute)"),
    (CAVE_CV,    _own(CAVE_CV,    [bytes(len(cave_cv))]),    cave_cv,    "cave_cv (melee CV = raw AttackerDV under flag)"),
    (CAVE_RETAL, _own(CAVE_RETAL, [bytes(len(cave_retal))]), cave_retal, "cave_retal (retaliation per melee attack)"),
    (SITE_RAZE,  ORIG_RAZE,  hook(SITE_RAZE,  CAVE_EXEC), "CanRaze Execute -> cave_exec"),
    (SITE_CIVST, ORIG_CIVST, hook(SITE_CIVST, CAVE_EXEC), "GetCivilStatus Execute -> cave_exec"),
    (SITE_CIVLS, ORIG_CIVLS, hook(SITE_CIVLS, CAVE_EXEC), "ListCivilStatusInfo Execute -> cave_exec"),
    (SITE_CV,    ORIG_CV,    hook(SITE_CV,    CAVE_CV),   "GetDamageValueEx GetDefenderDV -> cave_cv"),
    (SITE_RETAL, ORIG_RETAL, hook(SITE_RETAL, CAVE_RETAL),"ExecuteRound damage site -> cave_retal"),
]

for name, addr, code in (("cave_exec",CAVE_EXEC,cave_exec),
                         ("cave_cv",CAVE_CV,cave_cv),
                         ("cave_retal",CAVE_RETAL,cave_retal)):
    print(f"\n{name} @ {addr:08X}  ({len(code)} B)")
    for ins in cs.disasm(code, addr):
        print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<20} {ins.mnemonic} {ins.op_str}")

APPLY = "--apply" in sys.argv
def process(path, base, patches, backup_suffix=".pre-simfly"):
    data = bytearray(open(path,"rb").read())
    secs = load_sections(data); va2off = mkva2off(base)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])
    if all(rd(va,len(new))==new for va,_o,new,_d in patches):
        print(f"[= ] {os.path.basename(path)}: already applied"); return True
    ok=True
    for va,orig,new,desc in patches:
        cur=rd(va,len(new))
        origs = orig if isinstance(orig,(list,tuple)) else [orig]
        if cur not in origs and cur!=new:
            ok=False; print(f"[!] {va:08X} ({desc})\n     exp "
                            + " | ".join(o.hex(' ') for o in origs) + f"\n     got {cur.hex(' ')}")
    if not ok:
        print(f"[x] {os.path.basename(path)}: originals mismatch -- not written"); return False
    if not APPLY:
        print(f"[dry] {os.path.basename(path)}: originals verified"); return True
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bpath=os.path.join(BACKUP_DIR, os.path.basename(path)+backup_suffix)
    if not os.path.exists(bpath): shutil.copy2(path,bpath); print(f"[bak] {bpath}")
    for va,orig,new,desc in patches:
        o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError:
        print(f"[x] {os.path.basename(path)} LOCKED -- close all AoW binaries and retry"); return False
    return True

path = os.path.join(GAME,"AoWEPACK.dpl")
print()
ok = process(path, DLL_BASE, dll_patches)
if not APPLY:
    print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first.")
elif ok:
    print("\n[done] Applied. ⚠ Revert is NOT copying the .pre-simfly snapshot back over AoWEPACK.dpl:"
          "\n       a .pre-* file is a WHOLE-FILE snapshot, so restoring it silently destroys every"
          "\n       feature applied since. There is no --undo here -- undo by hand, restoring each"
          "\n       patch site's ORIG bytes from the table this script printed.")
else:
    print("\n[!] Not applied -- see above.")
