#!/usr/bin/env python3
r"""rngstd -- the project's standard DERIVED-HASH emitter (pattern P4).

    Taxonomy + selection test:  Zig notes/12-re-toolchain.md  4.10
    The two generators (P1/P2/P3):                            4.1 - 4.9
    Audit:  re_tools/rng_audit.py --owners   (P1/P2/P3)
            re_tools/rng_audit.py --hash     (P4 -- see below, this is NOT optional)

WHAT THIS IS FOR
================================================================================
P4 is the pattern for a roll that must give the SAME answer every time the same
situation is evaluated: a dialog that can be reopened, a preview that has to match
the thing it previews, an offer that must not re-roll across a save/reload. It
makes NO draw at all -- it derives the answer from state both peers already agree
on, so it is lockstep-safe by construction, reload-stable by construction, and
available in the exes where the synchronised generator is not.

Run the selection test in 4.10 before reaching for this. P4 is the answer to Q2,
not a general-purpose replacement for P1/P2/P3.

WHY AN EMITTER AND NOT A SNIPPET IN EACH SCRIPT
================================================================================
Because the point of a standard is that every site emits the SAME BYTES. keystone
will happily encode `xor eax,edx` as either 31 D0 or 33 C2 depending on how the
mnemonic is spelled, so two scripts hand-assembling "the same" algorithm produce
two different byte strings -- and then `--hash` can no longer find them, and no
two sites can be compared. So:

  * these functions return literal `bytes`, never an asm string;
  * the byte constants are ASSERTED by the self-test, never re-derived;
  * nothing here imports keystone, and nothing here assembles.

If you find yourself hand-rolling a hash in a build script, import this instead.
A P4 site whose bytes do not contain SIGNATURE is off-convention by definition.

REGISTER CONVENTION
================================================================================
  EAX accumulates.  The caller puts each input in EDX, then emits ONE mix().
  Emit one mix() per input, unrolled -- never a loop.
  Clobbers EAX, EDX, ECX and flags.  Preserves everything else (EBX/ESI/EDI/EBP).
  After range_n(n) the answer is in EDX, 0..n-1.  EAX is destroyed.

Shape of a percentage gate:

    basis()                          ; EAX = FNV basis
    <load input 1 into EDX>          ; caller's code
    mix()
    <load input 2 into EDX>
    mix()
    ...
    fmix32()
    range_n(100)                     ; mov ecx,100 ; mul ecx   -> EDX = 0..99
    cmp edx, <pct> ; jb pass         ; caller's code

or, equivalently, hash_pct(<the loads and mixes>).

POSITION-INDEPENDENT BY CONSTRUCTION
================================================================================
Every instruction emitted here is register-only: no memory operand, no absolute
address, no rel32. The blob is therefore safe verbatim in a DPL cave (which
rebases) as well as in an exe cave. Only the caller's own input loads can break
that -- reaching a global from a DPL cave still needs the `call $+5; pop; sub`
anchor.

THE SALT
================================================================================
The standard salt is the per-game seed constant `map[+0x22C]`.  The map pointer is
PER BINARY -- it is not one address:

    AoWEPACK.dpl              [[0x558E9494]] + 0x22C   (in a cave: needs the PIC anchor)
    AoW.exe / AoWCompat.exe   [[0x0045DF7C]] + 0x22C
    AoWDevEd.exe              [[0x0043289C]] + 0x22C   <- different slot, different build

Set once on day 1, streamed to every peer, never written again. Full evidence,
the writer/serialiser addresses and the two caveats (it is 0 or stale before day 1;
its provenance differs between network and hotseat games) are in 4.10.

Do NOT salt with `map[+0xE4]` (per-MAP, not per-game -- and an AnsiString) or with
`map[+0x230]` (the live synced seed; it advances on every draw, so it is a different
value at every evaluation, which destroys the one property P4 exists to provide).

THE BIAS -- DO NOT "FIX" IT
================================================================================
range_n is a multiply-shift, so buckets are not exactly equal: 2^32/100 =
42949672.96, hence 4 buckets in 100 are short by one value out of ~4.29e7, a
relative deviation of 2.3e-8. That is the same bias `System.@RandInt` has had
since 1999 and the same standing ruling applies: it is far below anything a player
or a test can observe. Adding a rejection loop would cost a branch, a second
evaluation path, and -- in a combat context -- draw-count asymmetry. Do not add one.

ALGORITHM
================================================================================
FNV-1a folded over 32-bit words (not bytes), then the MurmurHash3 finaliser
(fmix32), then multiply-shift reduction to 0..n-1. Chosen because all three steps
are three-instruction-or-fewer register-only sequences, and fmix32 avalanches the
low bits that multiply-shift reduction actually consumes -- plain FNV alone does
not, and a salt that differs by 1 between two games would map to the same bucket.

`model()` is the identical arithmetic in pure Python. It is not decoration: it is
what lets a build script assert its own calibration at write time, and what lets QA
check a whole outcome table without launching the game.
"""
import os
import random
import struct
import sys

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.  Nothing here reads it -- it is
# defined so a caller that imports rngstd standalone still has the project's path idiom.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

M32 = 0xFFFFFFFF

FNV_BASIS = 0x811C9DC5
FNV_PRIME = 0x01000193

# fmix32 (MurmurHash3 finaliser) constants
FMIX_C1 = 0x85EBCA6B
FMIX_C2 = 0xC2B2AE35

# `imul eax, eax, 0x85EBCA6B` -- unique to fmix32, so it locates every P4 site in a
# binary.  rng_audit.py --hash scans for exactly this.  P4 sites make no draw and are
# invisible to --owners by construction; without --hash, "the audit is clean" silently
# means "I did not look".
SIGNATURE = bytes.fromhex("69c06bcaeb85")

# ---------------------------------------------------------------------------
# The emitted byte constants.  ASSERTED by selftest(), never re-derived: two
# scripts must emit identical bytes for the same algorithm or --hash cannot find
# them and no two sites can be compared.
# ---------------------------------------------------------------------------
_B_MOV_EAX_IMM32 = bytes.fromhex("b8")          # mov  eax, imm32
_B_MOV_ECX_IMM32 = bytes.fromhex("b9")          # mov  ecx, imm32
_B_XOR_EAX_EDX   = bytes.fromhex("31d0")        # xor  eax, edx
_B_MOV_EDX_EAX   = bytes.fromhex("89c2")        # mov  edx, eax
_B_IMUL_EAX_IMM  = bytes.fromhex("69c0")        # imul eax, eax, imm32
_B_SHR_EDX_IMM8  = bytes.fromhex("c1ea")        # shr  edx, imm8
_B_MUL_ECX       = bytes.fromhex("f7e1")        # mul  ecx   (EDX:EAX = EAX*ECX)


def _imm32(v):
    return struct.pack("<I", v & M32)


def basis():
    """EAX := FNV basis.   5 bytes.

        b8 c5 9d 1c 81          mov eax, 0x811C9DC5
    """
    return _B_MOV_EAX_IMM32 + _imm32(FNV_BASIS)


def mix():
    """Fold the input already in EDX into the accumulator in EAX.   8 bytes.

        31 d0                   xor  eax, edx
        69 c0 93 01 00 01       imul eax, eax, 0x01000193

    Emit one per input, unrolled.  Never a loop: a loop needs a counter register,
    a pointer and a backward branch, none of which is position-independent for
    free, and the input count is always known at build time.
    """
    return _B_XOR_EAX_EDX + _B_IMUL_EAX_IMM + _imm32(FNV_PRIME)


def fmix32():
    """MurmurHash3 finaliser on EAX.   33 bytes.  Clobbers EDX.

        89 c2 / c1 ea 10 / 31 d0        h ^= h >> 16
        69 c0 6b ca eb 85               h *= 0x85EBCA6B
        89 c2 / c1 ea 0d / 31 d0        h ^= h >> 13
        69 c0 35 ae b2 c2               h *= 0xC2B2AE35
        89 c2 / c1 ea 10 / 31 d0        h ^= h >> 16
    """
    xs16 = _B_MOV_EDX_EAX + _B_SHR_EDX_IMM8 + bytes([16]) + _B_XOR_EAX_EDX
    xs13 = _B_MOV_EDX_EAX + _B_SHR_EDX_IMM8 + bytes([13]) + _B_XOR_EAX_EDX
    return (xs16
            + _B_IMUL_EAX_IMM + _imm32(FMIX_C1)
            + xs13
            + _B_IMUL_EAX_IMM + _imm32(FMIX_C2)
            + xs16)


def range_n(n):
    """EDX := (EAX * n) >> 32, i.e. 0..n-1.   7 bytes.  EAX is destroyed.

        b9 <n:dd>               mov ecx, n
        f7 e1                   mul ecx         ; EDX:EAX = EAX * ECX
    """
    if not isinstance(n, int) or not (1 <= n <= M32):
        raise ValueError("range_n: n must be an int in 1..0xFFFFFFFF, got %r" % (n,))
    return _B_MOV_ECX_IMM32 + _imm32(n) + _B_MUL_ECX


def hash_pct(inner=b""):
    """A complete percentage hash: basis() + inner + fmix32() + range_n(100).

    `inner` is the caller's own input loads with one mix() after each -- that is
    the "caller interleaves mix()" step.  Result in EDX, 0..99; gate it with
    `cmp edx, <pct> ; jb pass`.

    With no argument this is the zero-input form (a constant), which is only ever
    useful as a length/shape reference.
    """
    if not isinstance(inner, (bytes, bytearray)):
        raise TypeError("hash_pct: inner must be bytes, got %r" % (type(inner),))
    return basis() + bytes(inner) + fmix32() + range_n(100)


def model(salt, *keys, n=100):
    """The identical arithmetic in pure Python -> 0..n-1.

    Use it to assert a site's calibration at build time, and to check an outcome
    table without launching the game.  Inputs are taken mod 2^32; the emitted code
    folds whatever 32-bit value happens to be in EDX, so negative and oversized
    Python ints are masked the same way the CPU would.
    """
    if not isinstance(n, int) or not (1 <= n <= M32):
        raise ValueError("model: n must be an int in 1..0xFFFFFFFF, got %r" % (n,))
    h = FNV_BASIS
    for k in (salt,) + keys:
        h = ((h ^ (int(k) & M32)) * FNV_PRIME) & M32
    h ^= h >> 16
    h = (h * FMIX_C1) & M32
    h ^= h >> 13
    h = (h * FMIX_C2) & M32
    h ^= h >> 16
    return (h * n) >> 32


# ===========================================================================
# self-test
# ===========================================================================

def _emulate(blob):
    """Execute an rngstd byte stream and return (eax, edx).

    A decoder written from the ENCODINGS, deliberately not sharing a line of code
    with the emitters or with model(): if a constant is mistyped in one place this
    disagrees.  Also accepts `ba imm32` (mov edx, imm32) so a test can supply
    inputs -- the emitters never produce that.
    """
    eax = edx = ecx = 0
    i = 0
    while i < len(blob):
        op = blob[i]
        if op == 0xB8:                                        # mov eax, imm32
            eax = struct.unpack_from("<I", blob, i + 1)[0]; i += 5
        elif op == 0xB9:                                      # mov ecx, imm32
            ecx = struct.unpack_from("<I", blob, i + 1)[0]; i += 5
        elif op == 0xBA:                                      # mov edx, imm32 (test only)
            edx = struct.unpack_from("<I", blob, i + 1)[0]; i += 5
        elif op == 0x31 and blob[i + 1] == 0xD0:              # xor eax, edx
            eax ^= edx; i += 2
        elif op == 0x89 and blob[i + 1] == 0xC2:              # mov edx, eax
            edx = eax; i += 2
        elif op == 0xC1 and blob[i + 1] == 0xEA:              # shr edx, imm8
            edx = (edx & M32) >> blob[i + 2]; i += 3
        elif op == 0x69 and blob[i + 1] == 0xC0:              # imul eax, eax, imm32
            eax = (eax * struct.unpack_from("<I", blob, i + 2)[0]) & M32; i += 6
        elif op == 0xF7 and blob[i + 1] == 0xE1:              # mul ecx
            p = (eax & M32) * (ecx & M32)
            eax, edx = p & M32, (p >> 32) & M32
            i += 2
        else:
            raise AssertionError("emulator: unknown opcode %02X at +%d" % (op, i))
    return eax & M32, edx & M32


def _emit_full(salt, keys, n):
    """The byte stream a build script would emit for model(salt, *keys, n=n)."""
    inner = b""
    for k in (salt,) + tuple(keys):
        inner += b"\xBA" + struct.pack("<I", int(k) & M32)     # mov edx, k (test-only load)
        inner += mix()
    return basis() + inner + fmix32() + range_n(n)


def selftest(dist_samples=1000000, verbose=True):
    p = print if verbose else (lambda *a, **k: None)
    fail = []

    def check(name, got, want):
        ok = got == want
        if not ok:
            fail.append(name)
        p("  %-28s %-8s %s" % (name, "ok" if ok else "FAIL",
                               got.hex() if isinstance(got, bytes) else got))

    p("rngstd self-test")
    p(" byte constants (asserted, not re-derived)")
    check("basis()",        basis(),        bytes.fromhex("b8c59d1c81"))
    check("mix()",          mix(),          bytes.fromhex("31d0" "69c093010001"))
    check("fmix32()",       fmix32(),       bytes.fromhex("89c2c1ea1031d0"
                                                          "69c06bcaeb85"
                                                          "89c2c1ea0d31d0"
                                                          "69c035aeb2c2"
                                                          "89c2c1ea1031d0"))
    check("range_n(100)",   range_n(100),   bytes.fromhex("b964000000" "f7e1"))
    check("range_n(3)",     range_n(3),     bytes.fromhex("b903000000" "f7e1"))
    check("len basis",      len(basis()),   5)
    check("len mix",        len(mix()),     8)
    check("len fmix32",     len(fmix32()),  33)
    check("len range_n",    len(range_n(100)), 7)
    check("SIGNATURE",      SIGNATURE,      bytes.fromhex("69c06bcaeb85"))
    check("SIGNATURE in fmix32", SIGNATURE in fmix32(), True)
    check("hash_pct() == b+f+r", hash_pct(),
          basis() + fmix32() + range_n(100))
    check("len hash_pct()", len(hash_pct()), 45)

    p(" position-independence")
    allbytes = basis() + mix() + fmix32() + range_n(100)
    # The decoder below knows ONLY register-direct opcodes with immediate operands --
    # no ModRM mod!=3 form, no rel32, no absolute address.  If the emitted stream
    # decodes end to end, every instruction in it is position-independent.
    try:
        _emulate(allbytes)
        pic = True
    except AssertionError:
        pic = False
    check("decodes as register-only", pic, True)
    check("emitted length",  len(allbytes), 53)

    p(" model() vs an independent decoder+emulator over the emitted bytes")
    rnd = random.Random(0x22C22C)
    bad = 0
    cases = 0
    for _ in range(4000):
        nkeys = rnd.randint(0, 4)
        salt = rnd.getrandbits(32)
        keys = [rnd.getrandbits(32) for _ in range(nkeys)]
        n = rnd.choice([2, 3, 4, 5, 6, 7, 10, 20, 100, 255, 1000, 65536])
        _, edx = _emulate(_emit_full(salt, keys, n))
        if edx != model(salt, *keys, n=n):
            bad += 1
        cases += 1
    check("emulator == model (%d cases)" % cases, bad, 0)
    # edge inputs the random sweep will not reach
    for salt, keys in ((0, ()), (0xFFFFFFFF, (0xFFFFFFFF,)), (1, (0, 0, 0)),
                       (FNV_BASIS, (FNV_PRIME,))):
        _, edx = _emulate(_emit_full(salt, keys, 100))
        if edx != model(salt, *keys, n=100):
            bad += 1
    check("emulator == model (edge)", bad, 0)

    p(" range")
    inrange = all(0 <= model(s, s * 7, n=n) < n
                  for n in (2, 3, 100, 1000) for s in range(0, 5000, 7))
    check("0 <= result < n", inrange, True)

    p(" avalanche: salt+1 must not land in the same bucket")
    same = sum(1 for s in range(20000) if model(s, n=100) == model(s + 1, n=100))
    check("adjacent-salt collisions ~1%%: %d/20000" % same, 150 <= same <= 250, True)

    p(" uniformity: model(salt, key) over %d inputs, n=100" % dist_samples)
    buckets = [0] * 100
    rnd = random.Random(FNV_BASIS)
    for _ in range(dist_samples):
        buckets[model(rnd.getrandbits(32), rnd.getrandbits(32), n=100)] += 1
    exp = dist_samples // 100
    # +/-400 at 1e6 samples is the acceptance criterion this convention was signed off
    # against (~4 sigma); scaled as sqrt(N) for other sample counts.
    tol = max(50, round(400 * (dist_samples / 1000000.0) ** 0.5))
    lo, hi = min(buckets), max(buckets)
    check("bucket min/max %d/%d (%d +/- %d)" % (lo, hi, exp, tol),
          exp - tol <= lo and hi <= exp + tol, True)

    p(" bias is documented, not fixed")
    # 2^32 = 42949672*100 + 96, so 96 buckets hold 42949673 values and 4 hold 42949672.
    check("4 short buckets of 100", 100 - (2 ** 32) % 100, 4)
    check("short by 1 in 42949673", (2 ** 32) // 100 + 1, 42949673)

    if fail:
        p("\nFAILED: " + ", ".join(fail))
        return 1
    p("\nall checks passed")
    return 0


if __name__ == "__main__":
    n = 1000000
    for a in sys.argv[1:]:
        if a.startswith("--samples="):
            n = int(a.split("=", 1)[1])
    sys.exit(selftest(dist_samples=n))
