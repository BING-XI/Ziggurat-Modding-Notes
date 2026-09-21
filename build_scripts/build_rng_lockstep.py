#!/usr/bin/env python3
r"""
AoW1 mod -- "modded terrain rolls draw from the SYNCHRONISED generator, not the raw one".

THE DEFECT
  Three modded caves rolled through the RAW generator (System.@RandInt, AoWEPACK thunk
  0x55701080), which draws from `System.RandSeed` -- a PER-PROCESS global. All three decide
  replicated terrain state, so two machines running the same turn paint different maps from
  the first cast onward. It is silent: it assembles, it verifies, and single player is
  perfect.

  Vanilla is not ambiguous about any of the three -- it draws from the SYNCHRONISED generator,
  AoWE.TAoWHSMap.Random @0x5577827C, in the very same functions:

    site      cave (owner)                                      injected into
    5580DB72  5580DB60 cave_lavadirt (build_raiseterrain_lavadirt.py)
                                                Mountain.TRaiseTerrainTE.RaiseTerrain
                                                  -- vanilla draws SYNC twice, at 557A3397 and
                                                     557A346E; the second is inside the anim
                                                     block (557A3414) the cave jumps into
    5580DB46  5580DB40 cave_iceroll  (build_icestorm_lava.py)
                                                Storms.TIceStorm.ChangeStormTerrain
                                                  -- vanilla draws SYNC at 557CCF1E
    5580BEA8  5580BE74 Fire Storm terrain helper (ORPHAN -- no build script owned it)
                                                Storms.TFireStorm.ChangeStormTerrain
                                                  -- vanilla makes no draw there, but its
                                                     sibling TIceStorm.ChangeStormTerrain,
                                                     reached through the same VMT slot from
                                                     the same TBlastStorm.UpdateStorm, is SYNC

  Full rule + the vanilla SYNC/RAW split + the audit of every modded site:
  "Modding Resources/Zig notes/12-re-toolchain.md" section 4.  Audit: re_tools/rng_audit.py.

MECHANISM -- a drop-in stub, so no cave is rebuilt and no branch target moves
  The obvious fix (inline the synced call at each site) costs +14 bytes per site: the synced
  generator needs the map in EAX, and `[0x558E9494]` is an absolute data ref that a DPL cave
  must reach through the call/pop delta. cave_iceroll ends at exactly 0x5580DB60 where
  cave_lavadirt begins, so growing it in place would collide; the Fire Storm cave would have to
  be rebuilt whole (its internal `jne 0x5580BEBB` / `je 0x5580BEB7` targets would all shift),
  and nothing owns it to rebuild it from.

  Instead, one shared stub with EXACTLY the @RandInt ABI -- EAX = n in, EAX = 0..n-1 out,
  clobbering EAX/EDX/flags and nothing else:

      rng_sync:  push ecx                 ; TAoWHSMap.Random clobbers ECX; @RandInt does not,
                 mov  edx, eax            ;   so preserve it and stay a true drop-in
                 call $+5                 ; PIC anchor (aow1-dpl-rebasing)
                 pop  eax
                 mov  eax, [eax + (0x558E9494 - anchor)]   ; -> ptr to AoWE.AoWHSMap
                 mov  eax, [eax]                            ; -> the map
                 call 0x5577827C          ; TAoWHSMap.Random(EAX=map, EDX=n)
                 pop  ecx
                 ret

  Each defective site then changes by FOUR BYTES -- the rel32 of its existing `call` is
  repointed from the raw thunk to the stub (aow1-call-retarget-thunk). Nothing is displaced,
  no cave grows, every internal branch target is untouched, and `--undo` is the same four
  bytes back.

  ECX is safe at all three sites even without the stub's push/pop (lavadirt never reads it
  again; iceroll has its own push/pop; the Fire Storm cave reloads it with `mov ecx,[esp]`),
  but the stub preserves it anyway so a future call site cannot be bitten by the difference
  between the two generators' clobber sets.

BEHAVIOUR
  Distribution is unchanged -- same ranges (2, 4, 4), and TAoWHSMap.Random is literally
  @RandInt with the replicated seed swapped in and out. What changes is WHICH numbers come
  out, and that these three now advance [map+0x230] like every other synchronised draw. An
  in-progress game will therefore roll a different sequence from here on. That is the fix
  working, not a regression.

  Emphatically NOT changed: the summon-spell cave at 0x5580C500 and the combat-log cave at
  0x558114E0 stay raw -- both sit in functions where VANILLA draws raw, and combat rolls are
  supposed to be raw (TCombat.Execute re-anchors System.RandSeed from one synced draw). Same
  for build_shield.py's auto-resolve arc at 0x5582310E. See the rule doc before "fixing" any
  of them.

Idempotent (accepts already-retargeted sites); verifies every original byte before writing;
backs up to .pre-rnglockstep; dry-run by default, --apply to write, --undo to revert
surgically (restores the three rel32s, zeroes the stub, touches no backup).
"""
import shutil, sys, struct, os
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL = os.path.join(GAME, "AoWEPACK.dpl")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-rnglockstep")

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

DLL_BASE  = 0x55700000
RANDINT   = 0x55701080      # AoWEPACK thunk -> VCL30.dpl!System.@RandInt   (RAW, per-process seed)
MAPRANDOM = 0x5577827C      # AoWE.TAoWHSMap.Random  EAX=map, EDX=n        (SYNCED, map[+0x230])
MAPPTR    = 0x558E9494      # ptr -> AoWE.AoWHSMap ;  map = [[MAPPTR]]
PH_MAP    = 0x11111111

# 0x55827000: page-aligned, all-zero for 0x200 bytes, and 0xF35 past build_reformingflesh.py's
# declared CAVE_ZONE_END (0x558260CB) so its growth slack cannot reach it. Verified unclaimed:
#   grep -rl "55827" "Modding Resources/build_scripts/"   -> no hits
STUB = 0x55827000
STUB_ZONE = 0x40            # asserted still zero beyond the stub, so it may grow later

# every modded call site that must draw synced, with the cave that owns it
SITES = [
    (0x5580DB72, "cave_lavadirt  @5580DB60  (build_raiseterrain_lavadirt.py) "
                 "-- TRaiseTerrainTE.RaiseTerrain, vanilla SYNC x2"),
    (0x5580DB46, "cave_iceroll   @5580DB40  (build_icestorm_lava.py) "
                 "-- TIceStorm.ChangeStormTerrain, vanilla SYNC"),
    (0x5580BEA8, "firestorm helper @5580BE74 (ORPHAN, no owning script) "
                 "-- TFireStorm.ChangeStormTerrain, sibling is SYNC"),
]


def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e + 6)[0]
    optsize = struct.unpack_from("<H", data, e + 20)[0]
    sec = e + 24 + optsize
    secs = []
    for i in range(nsec):
        vsize, vaddr, rsize, raw = struct.unpack_from("<IIII", data, sec + 8)
        secs.append((vaddr, vsize, raw, rsize))
        sec += 40
    return secs


def va2off(secs, va):
    rva = va - DLL_BASE
    for vaddr, vsize, raw, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raw + (rva - vaddr)
    raise ValueError("VA %08X not mapped" % va)


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


def make_stub():
    src = """
        push ecx
        mov  edx, eax
        call _anchor
    _anchor:
        pop  eax
        mov  eax, [eax + 0x%X]
        mov  eax, [eax]
        call 0x%X
        pop  ecx
        ret
    """ % (PH_MAP, MAPRANDOM)
    code = bytearray(ks.asm(src, STUB)[0])
    # call/pop-delta anchor: E8 <rel32> followed by 0x58 (pop eax)
    i = next(k for k in range(len(code) - 5) if code[k] == 0xE8 and code[k + 5] == 0x58)
    anchor = STUB + i + 5                         # the VA that `pop eax` lands in EAX
    code[i + 1:i + 5] = struct.pack("<i", 0)      # call -> next instruction
    assert code[i + 6] == 0x8B and code[i + 7] == 0x80, "expected mov eax,[eax+disp32]"
    assert struct.unpack_from("<I", code, i + 8)[0] == PH_MAP, "placeholder moved"
    code[i + 8:i + 12] = struct.pack("<i", MAPPTR - anchor)
    return bytes(code)


STUB_CODE = make_stub()


def call_bytes(site, target):
    return b"\xE8" + rel32(site, target)


def read_dll():
    with open(DLL, "rb") as f:
        return bytearray(f.read())


def show(label, blob, va):
    print("   %s  (%d bytes @ %08X)" % (label, len(blob), va))
    for ins in cs.disasm(bytes(blob), va):
        note = ""
        if ins.mnemonic == "call" and ins.op_str.endswith("%x" % MAPRANDOM):
            note = "   ; AoWE.TAoWHSMap.Random  <- SYNCED"
        print("     %08X  %-8s %s%s" % (ins.address, ins.mnemonic, ins.op_str, note))


def status(data, secs):
    """-> (stub_state, [(va, state, desc)]) with state in 'done'/'raw'/'unknown'"""
    off = va2off(secs, STUB)
    cur = bytes(data[off:off + len(STUB_CODE)])
    if cur == STUB_CODE:
        stub = "done"
    elif cur == bytes(len(STUB_CODE)):
        stub = "absent"
    else:
        stub = "unknown"
    out = []
    for va, desc in SITES:
        o = va2off(secs, va)
        cur = bytes(data[o:o + 5])
        if cur == call_bytes(va, STUB):
            st = "done"
        elif cur == call_bytes(va, RANDINT):
            st = "raw"
        else:
            st = "unknown"
        out.append((va, st, desc))
    return stub, out


def main():
    apply_ = "--apply" in sys.argv
    undo = "--undo" in sys.argv
    dis = "--dis" in sys.argv

    data = read_dll()
    secs = load_sections(data)
    stub_state, sites = status(data, secs)

    print("build_rng_lockstep -- modded terrain rolls -> synchronised generator")
    print("   stub @%08X : %s" % (STUB, stub_state))
    for va, st, desc in sites:
        print("   %08X : %-7s %s" % (va, st, desc))
    if dis:
        show("rng_sync stub", STUB_CODE, STUB)

    if any(st == "unknown" for _, st, _ in sites) or stub_state == "unknown":
        print("\nABORT: a site does not hold either the raw or the retargeted form.")
        print("       Something else owns those bytes now -- do not write over it.")
        return 2

    if undo:
        if stub_state == "absent" and all(st == "raw" for _, st, _ in sites):
            print("\nnothing to undo -- already vanilla-generator")
            return 0
        if not apply_:
            print("\n--undo dry run: would restore %d call site(s) to `call %08X` and zero "
                  "the %d-byte stub. Add --apply to write." %
                  (sum(1 for _, st, _ in sites if st == "done"), RANDINT, len(STUB_CODE)))
            return 0
        for va, st, _ in sites:
            o = va2off(secs, va)
            data[o:o + 5] = call_bytes(va, RANDINT)
        o = va2off(secs, STUB)
        data[o:o + len(STUB_CODE)] = bytes(len(STUB_CODE))
        with open(DLL, "wb") as f:
            f.write(data)
        print("\nUNDONE: 3 call sites restored to the raw thunk, stub zeroed. "
              "No backup touched.")
        return 0

    todo = [s for s in sites if s[1] == "raw"] or []
    if stub_state == "done" and not todo:
        print("\nalready applied -- all three sites draw from TAoWHSMap.Random")
        return 0

    if not apply_:
        print("\ndry run: would write the %d-byte stub at %08X and retarget %d call site(s) "
              "(4 bytes each). Add --apply to write." % (len(STUB_CODE), STUB, len(todo)))
        return 0

    # verify the zone beyond the stub is still zero, so a later grow has room
    o = va2off(secs, STUB)
    tail = bytes(data[o + len(STUB_CODE):o + STUB_ZONE])
    assert tail == bytes(len(tail)), "cave zone past the stub is no longer zero -- someone " \
                                     "else allocated into %08X" % (STUB + len(STUB_CODE))

    if not os.path.exists(BACKUP):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(DLL, BACKUP)
        print("\nbacked up -> %s" % os.path.basename(BACKUP))

    data[o:o + len(STUB_CODE)] = STUB_CODE
    for va, st, _ in sites:
        if st == "raw":
            data[va2off(secs, va):va2off(secs, va) + 5] = call_bytes(va, STUB)
    with open(DLL, "wb") as f:
        f.write(data)
    print("\nAPPLIED: stub @%08X + %d call site(s) retargeted." % (STUB, len(todo)))
    print("   verify:  python \"Modding Resources/re_tools/rng_audit.py\" --owners")
    print("   the three sites must print `ok`, not `RAW`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
