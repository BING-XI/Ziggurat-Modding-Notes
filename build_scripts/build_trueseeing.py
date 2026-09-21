#!/usr/bin/env python3
r"""
AoW1 mod -- give TRUE SEEING (ability "True Vision", id 0x29) a conditional attack bonus vs INVISIBLE
units (ability "Invisibility", id 0x36):  +3 melee ATK / +1 ranged ATK, ATTACK ONLY (no damage).

Same shape as the confirmed slayers (Monster Slaying 0x70 vs Dragon marker 0x3f), but with ids
0x29/0x36 and no damage add. Both conditions are plain GetAbilityEnabled (combat VMT+0xa8) -> simpler
than Assassin (no IsClass/classref). IDs verified: TrueVisionRange@0x55780F80 gates on GetAbilityEnabled
(0x29); ConcealedOnMapF@0x55780524 treats a unit invisible on GetAbilityEnabled(0x36).

STRATEGY -- CHAIN, don't rewrite. The three confirmed slayer caves already have the exact attacker/target
register setup at their exits/entry; we leave their logic 100% untouched and only redirect their control
flow through three small new caves. Each new cave adds the True-Seeing branch, then jmps to where the
slayer cave was going. So this LAYERS ON the slayer caves (build_assassin + build_ranged_slayers must be
applied first -- verify-before-write checks their exit/hook bytes and aborts if absent).

  melee (round/opportunity/ability)  cave_melee   @0x5580E070  attacker=EBP target=ESI  ATK=BL
     -> its exit `jmp 0x557666CF` @0x5580E0D5  re-pointed to cave_ts_melee, which `jmp 0x557666CF`.
  melee (deliberate + retaliation)   cave_melee3  @0x5580E120  attacker=ESI target=EDI  ATK=dword[EBX]
     -> its exit `jmp 0x55767C89` @0x5580E183  re-pointed to cave_ts_melee3, which `jmp 0x55767C89`.
  ranged + breath (per shot)         cave_rng     @0x5580E190  attacker=ESI target=[EBP-4] ATK=byte[ESP+8]
     -> the ranged HOOK `jmp cave_rng` @0x5576EB34 re-pointed to cave_ts_rng, which (after its check on the
        pre-cave_rng state: AL=damage, [ESP]=attack) `jmp 0x5580E190` INTO cave_rng. cave_ts_rng runs
        BEFORE cave_rng and must leave AL/[ESP]/ESI/[EBP-4]/edi/ebx/ebp exactly as cave_rng expects.

Melee must hook BOTH tables (the confirmed "only opportunities worked" lesson). Caves are register/
immediate + VMT-indirect + rel32 only => position-independent. Idempotent, verify-before-write, free-space
asserted, backup <game dir>\backups\AoWEPACK.dpl.pre-trueseeing, dry-run by default / --apply.
REVERT: NOT by snapshot. Restoring a whole-file .pre-* wipes every feature applied after it, and
there is no snapshot layer at all now (both stacks were purged, 2026-08-08 and 2026-09-09). This
script has no --undo flag: back it out by hand. Note build_invis_penalty.py rewrites these same
three cave bodies in place, so check which version is installed before touching them.
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]; n = struct.unpack_from("<H", data, e+6)[0]
    op = struct.unpack_from("<H", data, e+20)[0]; s = e+24+op; secs = []
    for i in range(n):
        vs, va, rs, raw = struct.unpack_from("<IIII", data, s+8); secs.append((va, vs, raw, rs)); s += 40
    return secs
def mkva2off(base):
    def f(secs, va):
        rva = va-base
        for va0, vs, raw, rs in secs:
            if va0 <= rva < va0+max(vs, rs): return raw+(rva-va0)
        raise ValueError(hex(va))
    return f
def rel32(src, dst): return struct.pack("<i", dst-(src+5))

DLL_BASE = 0x55700000
TRUE_VISION = 0x29        # attacker: "True Seeing"
INVISIBLE   = 0x36        # target:   "Invisibility"
GAE         = 0xA8        # combat-object VMT slot: GetAbilityEnabled(edx=id) -> AL
MELEE_ATK   = 3
RANGED_ATK  = 1

# --- chain points (installed slayer caves) + their current exit targets (verify-before-write) ---
MELEE_EXIT   = 0x5580E0D5; MELEE_ORIG   = bytes.fromhex("e9f585f5ff"); MELEE_DEST   = 0x557666CF  # cave_melee -> CreateStrikeCA cont
MELEE3_EXIT  = 0x5580E183; MELEE3_ORIG  = bytes.fromhex("e9019bf5ff"); MELEE3_DEST  = 0x55767C89  # cave_melee3 -> CalculateStrikes cont
RNG_HOOK     = 0x5576EB34; RNG_ORIG     = bytes.fromhex("e957f60900"); RNG_CAVE     = 0x5580E190  # ranged hook -> cave_rng entry

# --- new caves (fresh free space past the Turn-Undead caves, which end ~0x5580E364) ---
CAVE_TS_MELEE  = 0x5580E370
CAVE_TS_MELEE3 = 0x5580E3B0
CAVE_TS_RNG    = 0x5580E400

# cave_ts_melee: EBP=attacker, ESI=target, BL=attack. clobber eax/ecx/edx (dest already trashed them).
ts_melee_src = f"""
    mov  edx, 0x{TRUE_VISION:X}
    mov  eax, ebp
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _done
    mov  edx, 0x{INVISIBLE:X}
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _done
    add  bl, {MELEE_ATK}
_done:
    jmp  0x{MELEE_DEST:X}
"""

# cave_ts_melee3: ESI=attacker, EDI=target, EBX=strike record (dword[EBX]=attack).
ts_melee3_src = f"""
    mov  edx, 0x{TRUE_VISION:X}
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _done
    mov  edx, 0x{INVISIBLE:X}
    mov  eax, edi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _done
    add  dword ptr [ebx], {MELEE_ATK}
_done:
    jmp  0x{MELEE3_DEST:X}
"""

# cave_ts_rng: runs BEFORE cave_rng. entry state = ranged hook: AL=damage, [ESP]=attack(uVar4),
# ESI=attacker, [EBP-4]=target. Must preserve all of that for cave_rng. After 3 pushes, attack is at [ESP+0xc].
ts_rng_src = f"""
    push eax
    push ecx
    push edx
    mov  edx, 0x{TRUE_VISION:X}
    mov  eax, esi
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _skip
    mov  eax, [ebp-4]
    mov  edx, 0x{INVISIBLE:X}
    mov  ecx, [eax]
    call dword ptr [ecx+0x{GAE:X}]
    test al, al
    jz   _skip
    add  byte ptr [esp+0xc], {RANGED_ATK}
_skip:
    pop  edx
    pop  ecx
    pop  eax
    jmp  0x{RNG_CAVE:X}
"""

ts_melee  = bytes(ks.asm(ts_melee_src,  CAVE_TS_MELEE)[0])
ts_melee3 = bytes(ks.asm(ts_melee3_src, CAVE_TS_MELEE3)[0])
ts_rng    = bytes(ks.asm(ts_rng_src,    CAVE_TS_RNG)[0])

APPLY = "--apply" in sys.argv
def process(path, base, suffix=".pre-trueseeing"):
    data = bytearray(open(path, "rb").read()); secs = load_sections(data); va2off = mkva2off(base)
    def rd(va, n): o = va2off(secs, va); return bytes(data[o:o+n])

    patches = [
        (CAVE_TS_MELEE,  bytes(len(ts_melee)),  ts_melee,  "cave_ts_melee  (+3 melee ATK vs invisible, round/opportunity)"),
        (CAVE_TS_MELEE3, bytes(len(ts_melee3)), ts_melee3, "cave_ts_melee3 (+3 melee ATK vs invisible, deliberate/retal)"),
        (CAVE_TS_RNG,    bytes(len(ts_rng)),    ts_rng,    "cave_ts_rng    (+1 ranged ATK vs invisible)"),
        (MELEE_EXIT,  MELEE_ORIG,  b"\xE9"+rel32(MELEE_EXIT, CAVE_TS_MELEE),  f"chain cave_melee exit {MELEE_EXIT:08X} -> cave_ts_melee"),
        (MELEE3_EXIT, MELEE3_ORIG, b"\xE9"+rel32(MELEE3_EXIT, CAVE_TS_MELEE3), f"chain cave_melee3 exit {MELEE3_EXIT:08X} -> cave_ts_melee3"),
        (RNG_HOOK,    RNG_ORIG,    b"\xE9"+rel32(RNG_HOOK, CAVE_TS_RNG),      f"chain ranged hook {RNG_HOOK:08X} -> cave_ts_rng"),
    ]

    for label, cva, cbytes in (("ts_melee", CAVE_TS_MELEE, ts_melee), ("ts_melee3", CAVE_TS_MELEE3, ts_melee3), ("ts_rng", CAVE_TS_RNG, ts_rng)):
        print(f"[{label}] @ {cva:08X} ({len(cbytes)} B)")
        for ins in cs.disasm(cbytes, cva):
            print(f"  {ins.address:08X} {ins.bytes.hex(' '):<22}{ins.mnemonic} {ins.op_str}")

    # free-space guard
    for cva, cbytes in ((CAVE_TS_MELEE, ts_melee), (CAVE_TS_MELEE3, ts_melee3), (CAVE_TS_RNG, ts_rng)):
        live = rd(cva, len(cbytes))
        if live != cbytes and any(b != 0 for b in live):
            print(f"[x] cave zone {cva:08X} not free:\n     {live.hex(' ')}"); return False
    # dependency guard: the slayer caves must be present (their exit/hook bytes must match)
    for va, orig, _new, desc in patches[3:]:
        cur = rd(va, len(orig))
        if cur != orig and cur != _new:
            print(f"[x] chain point {va:08X} unexpected -- is build_assassin/build_ranged_slayers applied?"
                  f"\n     exp {orig.hex(' ')}\n     got {cur.hex(' ')}  ({desc})"); return False

    if all(rd(va, len(new)) == new for va, _o, new, _d in patches):
        print("[= ] already applied"); return True
    if not APPLY: print("[dry] caves assemble, zones free, chain points verified"); return True
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bp = os.path.join(BACKUP_DIR, os.path.basename(path)+suffix)
    if not os.path.exists(bp): shutil.copy2(path, bp); print(f"[bak] {bp}")
    for va, orig, new, desc in patches:
        o = va2off(secs, va); data[o:o+len(new)] = new; print(f"[w ] {va:08X} {desc}")
    try: open(path, "wb").write(data)
    except PermissionError: print("[x] LOCKED -- close AoW binaries"); return False
    return True

print()
ok = process(os.path.join(GAME, "AoWEPACK.dpl"), DLL_BASE)
print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first." if not APPLY
      else ("\n[done] Applied. Revert: undo surgically by hand -- a .pre-* restore is not a revert path." if ok else "\n[!] not applied"))
