#!/usr/bin/env python3
r"""
ref_probe.py -- who points at this object?  Scan a running AoW1's writable memory for dwords equal
to the given address(es), and name the Delphi object (class + field offset) or module global that
holds each one.

WHEN TO REACH FOR THIS
----------------------
A dangling pointer, a list that still holds a freed unit, "which army owns this enchantment":
anything where the question is the REVERSE of a field read.  Pair it with hwbp.py (who writes a
field) and veh_capture.py (who crashed on it).

Ported 2026-09-25 from Inioch's ref_probe.py (share8).  Changed here: the target comes from zigexe;
an owning object is recognised by the live Delphi VMT self-pointer ([vmt-40h] == vmt, class name
at [vmt-20h]) instead of a regex over one DLL file, so classes from every module (exe, AoWEPACK,
TCPCK, VCL30...) are named; references held in module globals (MEM_IMAGE data) are reported as
module+offset instead of skipped; the targeted object's own class is printed first.

USAGE
-----
    python ref_probe.py 0A3301B4 022C6D5C          # one or more absolute addresses
    python ref_probe.py 0A3301B4 --pid 1234 --back 0x800

READING THE OUTPUT
------------------
    0A3301B4 (TUnit) <- 0A2F11C8  TArmy obj@0A2F1190 +0x38
    0F3AD584 (TAoWHSMap) <- 00FCA040  AoWEPACK.dpl+0x1FA040  link 0x558FA040 (global)

⚠ The owner is the nearest preceding dword that is a live VMT, within --back bytes.  A class-
reference FIELD (a `TClass` value) also looks like a VMT, so an owner whose field offset looks
implausible may be a classref inside a bigger object -- widen --back and compare.
⚠ A hit inside a TList's item array has no VMT before it (the array is a bare heap block), and
neither does a local on a thread stack; both print as "no object before it".  For a list, probe
the array's own address again to find the TList.
"""
import argparse
import ctypes as C
import os
import struct
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import veh_capture as V                       # noqa: E402  (k32, rpm, modules, ModuleMap, MBI)
from zignames import zigexe                   # noqa: E402
from hwbp import find_pid                     # noqa: E402

k32 = V.k32
READABLE_WRITABLE = (0x04, 0x08, 0x40, 0x80)  # RW, WRITECOPY, EXECUTE_RW, EXECUTE_WRITECOPY
PAGE_GUARD = 0x100
MEM_COMMIT, MEM_IMAGE = 0x1000, 0x1000000


class Vmts:
    """Is this dword a live Delphi VMT?  Cached, because every hit walks back over many dwords."""

    def __init__(self, hp):
        self.hp, self.cache = hp, {}

    def name(self, v):
        if v in self.cache:
            return self.cache[v]
        out = None
        if v & 3 == 0 and 0x10000 <= v < 0x80000000:
            if V.rdw(self.hp, v - 0x40) == v:
                p = V.rdw(self.hp, v - 0x20)
                s = V.rpm(self.hp, p, 64) if p else b""
                if s and 0 < s[0] < 64 and len(s) > s[0] and all(0x20 < c < 0x7F for c in s[1:1 + s[0]]):
                    out = s[1:1 + s[0]].decode("ascii")
        self.cache[v] = out
        return out


def regions(hp):
    mbi = V.MBI()
    addr = 0
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(hp, C.c_void_p(addr), C.byref(mbi), C.sizeof(mbi)):
            break
        base, size = int(mbi.BaseAddress or 0), int(mbi.RegionSize or 0)
        if size <= 0:
            break
        if (mbi.State == MEM_COMMIT and (mbi.Protect & 0xFF) in READABLE_WRITABLE
                and not mbi.Protect & PAGE_GUARD):
            yield base, size, mbi.Type == MEM_IMAGE
        addr = base + size


def main(argv=None):
    p = argparse.ArgumentParser(prog="ref_probe.py", formatter_class=argparse.RawDescriptionHelpFormatter,
                                description=__doc__)
    p.add_argument("addrs", nargs="+", help="absolute address(es), hex")
    p.add_argument("--pid", type=int, help="default: the running %s" % zigexe.GAME_EXE)
    p.add_argument("--exe", default=zigexe.GAME_EXE)
    p.add_argument("--back", type=lambda s: int(s, 0), default=0x400,
                   help="how far before a hit to look for the owning object's VMT (default 0x400)")
    p.add_argument("--max", type=int, default=200, help="stop after this many hits per address")
    a = p.parse_args(argv)

    targets = [int(x, 16) for x in a.addrs]
    pid = a.pid or find_pid(a.exe)
    if not pid:
        print("[x] %s is not running (or pass --pid)" % a.exe)
        return 2
    hp = k32.OpenProcess(0x0410, False, pid)          # QUERY_INFORMATION | VM_READ
    if not hp:
        print("[x] OpenProcess(%d) failed, error %d" % (pid, C.get_last_error()))
        return 2
    mm = V.ModuleMap(V.modules(pid))
    vm = Vmts(hp)
    label = {}
    for t in targets:
        cls = vm.name(V.rdw(hp, t) or 0)
        label[t] = "%08X (%s)" % (t, cls or "not an object start")
    pats = {struct.pack("<I", t): t for t in targets}
    counts = dict.fromkeys(targets, 0)
    scanned = 0
    try:
        for base, size, is_image in regions(hp):
            data = V.rpm(hp, base, size)
            scanned += len(data)
            for pat, t in pats.items():
                i = data.find(pat)
                while i != -1 and counts[t] < a.max:
                    if i % 4 == 0 and base + i != t:
                        hit = base + i
                        if is_image:
                            owner = "%s (global)" % mm.describe(hit)
                        else:
                            owner = "no object before it (a bare heap block, or a stack)"
                            for back in range(4, min(a.back, i) + 1, 4):
                                cand = struct.unpack_from("<I", data, i - back)[0]
                                cls = vm.name(cand)
                                if cls:
                                    owner = "%s obj@%08X +0x%X" % (cls, hit - back, back)
                                    break
                        print("%s <- %08X  %s" % (label[t], hit, owner))
                        counts[t] += 1
                    i = data.find(pat, i + 1)
    finally:
        k32.CloseHandle(hp)
    for t in targets:
        print("-- %s: %d reference(s)%s" % (label[t], counts[t],
                                             " (stopped at --max)" if counts[t] >= a.max else ""))
    print("-- scanned %.1f MB of writable memory in pid %d" % (scanned / 1e6, pid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
