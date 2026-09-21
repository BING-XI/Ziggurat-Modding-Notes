"""AoW1 .hss (HSSET) CRC — verify and repair.

MECHANISM (decoded 2026-07-27 from HSEngine.THSEngine.LoadHSS, HSEPack.dpl 5560F75C;
the lead came from the user's own 2021 notes pointing at EngineP.dpl!Engine.GetCRC32):

    ebx = *(u32*)(file + size - 4)      ; stored CRC = the LAST dword of the file
    ...                                 ; a signature string is compared first
    crc = GetCRC32(file, size - 4)      ; covers EVERYTHING except that trailing dword
    cmp ebx, eax / je ok
    raise Exception('Invalid HSSET')    ; unhandled at startup -> the app dies silently

`Engine.GetCRC32` (EngineP.dpl 5550E608) is textbook reflected CRC-32 — init 0xFFFFFFFF,
crc = table[(crc ^ byte) & 0xFF] ^ (crc >> 8), final XOR 0xFFFFFFFF — i.e. identical to
zlib.crc32.  The lookup table is BUILT AT RUNTIME (Engine.ReleaseCRC32Table frees it),
which is why scanning the binaries for a static CRC32 table finds nothing.

Note this differs from TEngine.ReadFromFileCRC (EngineP 5551C084), a *different* container
used by other file types, which stores its CRC in the FIRST dword and covers file[4:].

Usage:
  hss_crc.py <file.hss>          -- report stored vs computed
  hss_crc.py <file.hss> --fix    -- rewrite the trailing dword to match the content
"""
import os, struct, sys, zlib


def crc_of(data: bytes) -> int:
    """CRC the engine expects over a .hss: everything but the trailing dword."""
    return zlib.crc32(data[:-4]) & 0xFFFFFFFF


def stored_crc(data: bytes) -> int:
    return struct.unpack_from("<I", data, len(data) - 4)[0]


def verify(data: bytes) -> bool:
    return len(data) > 8 and stored_crc(data) == crc_of(data)


def fix(data: bytes) -> bytes:
    """Return data with its trailing CRC dword corrected."""
    out = bytearray(data)
    struct.pack_into("<I", out, len(out) - 4, crc_of(bytes(data)))
    return bytes(out)


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    p = sys.argv[1]
    d = open(p, "rb").read()
    s, c = stored_crc(d), crc_of(d)
    print(f"{os.path.basename(p)}: {len(d)} bytes  stored={s:#010x} computed={c:#010x} "
          f"{'VALID' if s == c else 'MISMATCH'}")
    if s != c and "--fix" in sys.argv:
        open(p, "wb").write(fix(d))
        print(f"  fixed -> trailing dword set to {c:#010x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
