#!/usr/bin/env python3
r"""
AoW1 raze DIAGNOSTIC toggler -- isolates WHERE the AI non-city raze chain stops.

The v6 chain: [want] TAIGroupRazeControl.Process -> GetRazeable -> ValidateRazeStructure
(own*2 < hostile+neutral players, r15)  ->  [feasibility] CanRaze -> cave_forcefail v6
(result==4 && superiority<50)  ->  raze.

Two independently toggleable levers (game must be CLOSED to apply):

  --gate-open   NOP the two v6 branch-outs in cave_forcefail's AI non-city path
                (cmp al,4 / jne  and  cmp eax,50 / jge). AI non-city razes then pass
                UNCONDITIONALLY once CanRaze is reached -- i.e. once the WANT fired.
                * razes with this  -> the v6 SIM VERDICT was the blocker (result!=4 or sup>=50).
                * still no raze    -> the want never fired; escalate to --want-open.

  --want-open   RazeControl mode default DAT_557D7414: 0x01 -> 0x05 (sets bit2 =
                unconditional raze-anything; ValidateRazeStructure AND ValidateRazeCity
                then return TRUE always). WARNING: with this set the AI will try to raze
                EVERYTHING it captures (cities included) -- test-map use only.
                * razes with this  -> the bfi tally/validator was the blocker (relation /
                                      radius / strength-category mask inputs).
                * still no raze    -> RazeControl/status-5 never ran; the selector's
                                      "target consumed" timing is the blocker -> deep-trace next.

  --revert      Restore BOTH levers to v6 stock.
  (no args)     Report current lever state (dry).

Ladder: run --gate-open first, retest; only if still no raze add --want-open, retest.
Idempotent; verifies bytes before writing; one-time whole-file backup .pre-razediag.
"""
import os, shutil, struct, sys

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # rule 2026-09-03: snapshots live here, never the game root
DLL   = os.path.join(GAME, "AoWEPACK.dpl")
DLL_BASE = 0x55700000

def load_sections(data):
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e+6)[0]
    optsize = struct.unpack_from("<H", data, e+20)[0]
    sec = e+24+optsize; secs=[]
    for i in range(nsec):
        vsize,vaddr,rsize,raw = struct.unpack_from("<IIII", data, sec+8)
        secs.append((vaddr,vsize,raw,rsize)); sec+=40
    return secs
def va2off(secs, va):
    rva = va-DLL_BASE
    for vaddr,vsize,raw,rsize in secs:
        if vaddr <= rva < vaddr+max(vsize,rsize):
            return raw+(rva-vaddr)
    raise ValueError(f"VA {va:08X} not mapped")

# ---- lever definitions: (va, stock_bytes, diag_bytes, name) ----
# v6 cave_forcefail AI non-city branch (see build_razebattle_tower.py src_forcefail):
#   5580D1D5  3c 04     cmp al, 4
#   5580D1D7  75 d1     jne Lnoforce      <- lever byte pair 1
#   5580D1D9  8b 45 f0  mov eax,[ebp-0x10]
#   5580D1DC  e8 ..     call GetSuperiority
#   5580D1E1  83 f8 32  cmp eax, 0x32
#   5580D1E4  7d c4     jge Lnoforce      <- lever byte pair 2
GATE = [
    (0x5580D1D7, bytes.fromhex("75 d1".replace(" ","")), b"\x90\x90", "v6 result==4 branch"),
    (0x5580D1E4, bytes.fromhex("7d c4".replace(" ","")), b"\x90\x90", "v6 sup<50 branch"),
]
# TAIGroupRazeControl.Reset @0x557D73E0 reads the mode default byte:
#   557D73F8  a0 14 74 7d 55   mov al, [0x557D7414]   (DAT_557D7414 = 0x01 stock)
WANT = [
    (0x557D7414, b"\x01", b"\x05", "RazeControl mode default (bit2 = raze-anything)"),
]

def state(data, secs, levers):
    out=[]
    for va, stock, diag, name in levers:
        cur = bytes(data[va2off(secs,va):va2off(secs,va)+len(stock)])
        s = "STOCK" if cur==stock else ("DIAG" if cur==diag else f"UNEXPECTED {cur.hex(' ')}")
        out.append((name, va, s))
    return out

def set_levers(data, secs, levers, to_diag):
    for va, stock, diag, name in levers:
        o = va2off(secs,va)
        cur = bytes(data[o:o+len(stock)])
        want = diag if to_diag else stock
        prior = stock if to_diag else diag
        if cur == want:
            print(f"[= ] {va:08X} {name}: already {'DIAG' if to_diag else 'STOCK'}")
        elif cur == prior:
            data[o:o+len(want)] = want
            print(f"[w ] {va:08X} {name}: -> {'DIAG' if to_diag else 'STOCK'} ({want.hex(' ')})")
        else:
            raise SystemExit(f"[x] {va:08X} {name}: unexpected bytes {cur.hex(' ')} -- aborting, nothing written")

def main():
    args = set(sys.argv[1:])
    data = bytearray(open(DLL,"rb").read())
    secs = load_sections(data)
    print("current lever state:")
    for name, va, s in state(data, secs, GATE+WANT):
        print(f"   {va:08X}  {name:45s} {s}")
    if not args:
        print("\n(no args: dry report only; use --gate-open / --want-open / --revert)"); return
    reverting = "--revert" in args
    if reverting:
        set_levers(data, secs, GATE, False); set_levers(data, secs, WANT, False)
    else:
        if "--gate-open" in args: set_levers(data, secs, GATE, True)
        if "--want-open" in args: set_levers(data, secs, WANT, True)
    # rule 2026-09-10: a .pre-* snapshot is minted on the APPLY path ONLY. Reverting
    # through this same write path would snapshot the PATCHED dll under a "pre-" name.
    if not reverting:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        bak = os.path.join(BACKUP_DIR, os.path.basename(DLL) + ".pre-razediag")
        if not os.path.exists(bak):
            shutil.copy2(DLL, bak); print(f"[bak] {bak}")
    try:
        open(DLL,"wb").write(data)
    except PermissionError:
        raise SystemExit("[x] AoWEPACK.dpl LOCKED -- close all AoW binaries and retry")
    print("[done]")

if __name__ == "__main__":
    main()
