"""Sampling profiler WITH a poor-man's stack walk, for the UI thread of a running AoW binary.

sampler.py records EIP only, which is useless when the hot address is a kernel stub: you learn the
thread is in ZwDelayExecution but not WHO called it. This one also reads a window of the stack at
ESP and reports the first few return addresses that land inside a known AoW module, so waits get
attributed to the AoW function responsible.

Usage: stack_prof.py --window <hwnd-hex> [--seconds 8] [--hz 300] [--exe AoWzEd.exe]

⚠ --exe names a RUNNING process. AoWDevEd.exe is the editor PATCH SOURCE and is not launched --
AoWzEd.exe is the one build_zigeditor.py produces and the owner runs.
"""
import argparse, bisect, ctypes, os, sys, time
from collections import Counter
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowsyms import get_symbols, GAME
from zignames import zigexe
from sampler import (find_pid, list_threads, module_map, WOW64_CONTEXT,
                     WOW64_CONTEXT_CONTROL, THREAD_RIGHTS, PROCESS_ALL_READ, k32)

u32 = ctypes.WinDLL("user32", use_last_error=True)

ap = argparse.ArgumentParser()
ap.add_argument("--exe", default=zigexe.LIVE_EDITOR)
ap.add_argument("--window", required=True)
ap.add_argument("--seconds", type=float, default=8)
ap.add_argument("--hz", type=float, default=300)
ap.add_argument("--depth", type=int, default=3, help="AoW return addresses to report per sample")
ap.add_argument("--slots", type=int, default=96, help="stack dwords to scan from ESP")
args = ap.parse_args()

pid = find_pid(args.exe)
assert pid, f"{args.exe} not running"
hproc = k32.OpenProcess(PROCESS_ALL_READ, False, pid)
mods = module_map(hproc)
tid = u32.GetWindowThreadProcessId(ctypes.c_void_p(int(args.window, 16)), None)
assert tid, "bad window handle"

symcache = {}


def load_syms(modname):
    key = modname.lower()
    if key not in symcache:
        entry = None
        if os.path.exists(os.path.join(GAME, modname)) and key.endswith((".dpl", ".exe")):
            try:
                _, base, syms, _ = get_symbols(modname)
                entry = (base, sorted(syms.items()))
            except Exception:
                entry = None
        symcache[key] = entry
    return symcache[key]


AOW = tuple(m.lower() for m in
            ("aowdeved.exe", "aow.exe", "hsepack.dpl", "dcpack.dpl", "gfxepack.dpl", "ilpack.dpl",
             "aowepack.dpl", "enginep.dpl", "adcpack.dpl", "soundp.dpl", "network.dpl"))


def locate(addr):
    for base, size, name in mods:
        if base <= addr < base + size:
            off = addr - base
            e = load_syms(name)
            if e:
                pref, symlist = e
                va = pref + off
                keys = [s[0] for s in symlist]
                i = bisect.bisect_right(keys, va) - 1
                if i >= 0 and va - symlist[i][0] < 0x4000:
                    return name, f"{name}!{symlist[i][1]}+{va - symlist[i][0]:#x}"
            return name, f"{name}+{off:#x}"
    return None, None


def read(addr, n):
    buf = (ctypes.c_char * n)()
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(hproc, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return None
    return bytes(buf[:got.value])


h = k32.OpenThread(THREAD_RIGHTS, False, tid)
assert h, "OpenThread failed"
ctx = WOW64_CONTEXT()
interval = 1.0 / args.hz
eip_hist = Counter()
chain_hist = Counter()
attrib = Counter()
n = 0
t_end = time.perf_counter() + args.seconds
while time.perf_counter() < t_end:
    t0 = time.perf_counter()
    if k32.SuspendThread(h) != 0xFFFFFFFF:
        try:
            ctx.ContextFlags = WOW64_CONTEXT_CONTROL
            if k32.Wow64GetThreadContext(h, ctypes.byref(ctx)):
                eip, esp = ctx.Eip, ctx.Esp
                blob = read(esp, args.slots * 4)
            else:
                blob = None
        finally:
            k32.ResumeThread(h)
    else:
        blob = None
    if blob:
        n += 1
        _, es = locate(eip)
        eip_hist[es or f"?{eip:#x}"] += 1
        chain = []
        seen = set()
        for i in range(0, len(blob) - 3, 4):
            v = int.from_bytes(blob[i:i + 4], "little")
            mod, s = locate(v)
            if mod and mod.lower() in AOW and s not in seen:
                seen.add(s)
                chain.append(s)
                if len(chain) >= args.depth:
                    break
        if chain:
            attrib[chain[0]] += 1
            chain_hist[" <- ".join(chain)] += 1
        else:
            attrib["(no AoW frame on stack)"] += 1
    dt = time.perf_counter() - t0
    if dt < interval:
        time.sleep(interval - dt)
k32.CloseHandle(h)

print(f"{n} samples of tid {tid}\n")
print("== EIP ==")
for s, c in eip_hist.most_common(8):
    print(f"  {c:5d} {100*c/n:5.1f}%  {s}")
print("\n== nearest AoW frame (who is actually running/waiting) ==")
for s, c in attrib.most_common(12):
    print(f"  {c:5d} {100*c/n:5.1f}%  {s}")
print("\n== AoW stack chains ==")
for s, c in chain_hist.most_common(10):
    print(f"  {c:5d} {100*c/n:5.1f}%  {s}")
