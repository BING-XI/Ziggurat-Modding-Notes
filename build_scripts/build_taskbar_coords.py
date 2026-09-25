#!/usr/bin/env python
r"""
build_taskbar_coords.py -- the world taskbar shows the hex under the cursor as "X,Y,Z" at the right
end of the message box ("-,-,-" off the map).  AoWz.exe + AoWzCompat.exe in lockstep.

From Inioch's share8 patch_aowx_cursor_coords.py (aowx-taskbar-coords.md); every address below
was re-verified on AoWz.exe 2026-09-25.

HOW
  1. TTBWINDOW DFM (RCDATA, 35452 B at rva 0x1CEAB0, resource data entry at file 0x731A0) gains a
     TAOWLabel `CoordLbl`, a clone of TimeLbl with font FontModule.Age10, Alignment.RightOffset
     355 and BottomOffset 6.  355 px: TBMessEdit runs to RightOffset 275, but the player/race turn
     indicator PInd (75 px, RightOffset 275, higher priority) is drawn over the edit's right 75 px,
     so the visible text ends 350 px from the right edge; a label under PInd makes the indicators
     flicker.  The grown DFM cannot stay in .rsrc, so the entry is repointed at the copy here.
  2. TTBWindow (VMT 0x456CAC) field table (0x456CD4, 60 fields) is relocated with CoordLbl
     appended at +0x144 (class index 4 = TAOWLabel); VMT-0x2C repointed, instance size (VMT-0x1C)
     0x144 -> 0x148.  The TTBWindow instance is the global at 0x45B2C8.
  3. TMWindow.MapWindowMouseMove 0x450EF8 runs only while the cursor is over the map view; after it
     updates THSMapMouse ([[0x45DF7C]]+0xC) the 7 bytes at 0x450F77 (`mov dx,0x270F / mov
     eax,[ebx+0x44]`) are hooked -> cave_hook: flag := 1, X = GetXhx(mouse), Y = GetYhx(mouse)
     (HSEPack, not imported: IAT 0x45D9D8 TMapContainer.GetField + the link distance), Z =
     [map+0x88]; on a change, format into one of two static AnsiStrings (refcount -1, alternated
     so SetGText never receives the pointer it already holds) and TAOWLabel.SetGText(CoordLbl).
  4. TMainForm's published method-table entry for DisplayMouseMove (code dword at file 0x51BB0)
     -> dmm_wrap: flag := 0, the original 0x4536E8, and if the flag is still 0 the cursor was not
     over the map: show "-,-,-".

WHERE -- AoWz.exe has no free section-header slot, so this GROWS .ibnr, the last section, which
  build_itembanner_hpmv.py owns (0x00630000..0x00632FFF).  This feature is its tenant above it:
      .ibnr SizeOfRawData = VirtualSize  0x3000 -> 0xD000,  SizeOfImage 0x233000 -> 0x23D000
      0x00633000  the grown TTBWINDOW DFM, then the relocated field table, then the code/data
  build_itembanner_hpmv.py --undo refuses while .ibnr is larger than its own 0x3000.
  --undo here restores every pointer and hook, truncates the file back and shrinks .ibnr.

Rolls: none.  Fixed-base exe; absolute addresses throughout.
"""
import os, struct, sys
sys.dont_write_bytecode = True
import zigexe
from aowepack_patch import asm, kill_aow, show

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
BASE = 0x400000
SEC = b".ibnr"
IBNR_VA, IBNR_OWN = 0x00630000, 0x3000
GROW_VA, NEW_SIZE = 0x00633000, 0xD000

RES_ENTRY_FO, RES_RVA, RES_SIZE = 0x731A0, 0x1CEAB0, 0x8A7C
VMT_FT_FO, VMT_SIZE_FO, FT_VA, FT_LEN, FT_COUNT = 0x56080, 0x56090, 0x456CD4, 885, 60
OLD_INST, NEW_INST, CLS_LABEL, NEW_FIELD = 0x144, 0x148, 4, 0x144
G_TBWINDOW, G_MAP, IAT_GETFIELD = 0x45B2C8, 0x45DF7C, 0x45D9D8
LINK_GETFIELD, LINK_GETXHX, LINK_GETYHX = 0x55608D84, 0x5560B6B0, 0x5560B718
T_SETGTEXT = 0x403254                     # AoWLabel.TAOWLabel.SetGText (eax = label, edx = text)
HOOK, HOOK_ORIG, HOOK_CONT = 0x450F77, bytes.fromhex("66ba0f278b4344"), 0x450F7E
MT_DMM_FO, DISPLAYMOUSEMOVE = 0x51BB0, 0x4536E8
MAP_MOUSE, MAP_LEVEL = 0x0C, 0x88
LABEL_RIGHT, LABEL_BOTTOM = 355, 6


def ss(s):
    return bytes([len(s)]) + s


def obj_span(d, o):
    def skip_val(p):
        t = d[p]
        p += 1
        if t in (0, 8, 9, 13):
            return p
        if t == 1:
            while d[p] != 0:
                p = skip_val(p)
            return p + 1
        if t == 2:
            return p + 1
        if t == 3:
            return p + 2
        if t == 4:
            return p + 4
        if t == 5:
            return p + 10
        if t in (6, 7):
            return p + 1 + d[p]
        if t in (10, 12):
            return p + 4 + struct.unpack_from("<I", d, p)[0]
        if t == 11:
            while d[p] != 0:
                p += 1 + d[p]
            return p + 1
        raise ValueError("DFM value type %d at %#x" % (t, p))
    p = o + 1 + d[o]
    p += 1 + d[p]
    while d[p] != 0:
        p += 1 + d[p]
        p = skip_val(p)
    p += 1
    while d[p] != 0:
        p = obj_span(d, p)
    return p + 1


def build_dfm(dfm):
    i = dfm.find(b"\x09TAOWLabel\x07TimeLbl")
    assert i >= 0 and dfm.count(b"\x07TimeLbl") == 1, "TimeLbl not found once"
    e = obj_span(dfm, i)
    raw = dfm[i:e]
    cl = raw[0]
    body = raw[1 + cl + 1 + raw[1 + cl]:]
    out = raw[:1 + cl] + ss(b"CoordLbl") + body
    for old, new in ((b"\x07AOWFont\x07" + ss(b"FontModule.TBarNumber"),
                      b"\x07AOWFont\x07" + ss(b"FontModule.Age10")),
                     (b"\x15Alignment.RightOffset\x03\xe1\x00",
                      b"\x15Alignment.RightOffset\x03" + struct.pack("<h", LABEL_RIGHT)),
                     (b"\x16Alignment.BottomOffset\x02\x04",
                      b"\x16Alignment.BottomOffset\x02" + bytes([LABEL_BOTTOM]))):
        assert out.count(old) == 1, old
        out = out.replace(old, new)
    assert b"CoordLbl" not in dfm
    return dfm[:e] + out + dfm[e:]


def build_field_table(ft):
    out = bytearray(ft) + struct.pack("<IH", NEW_FIELD, CLS_LABEL) + ss(b"CoordLbl")
    struct.pack_into("<H", out, 0, FT_COUNT + 1)
    return bytes(out)


def build_code(va):
    """Data block first (flag, last X/Y/Z, two AnsiStrings, selector), then the code."""
    FLAG, LX, LY, LZ = va, va + 4, va + 8, va + 12
    BUF0 = va + 0x18                   # header [-8] refcount, [-4] length
    BUF1 = BUF0 + 0x28
    BSEL = BUF1 + 0x20
    data = bytearray(0x80)
    struct.pack_into("<Iiii", data, 0, 0, -2, -2, -2)
    for b in (BUF0, BUF1):
        o = b - va
        struct.pack_into("<iI", data, o - 8, -1, 5)
        data[o:o + 6] = b"-,-,-\0"
    struct.pack_into("<I", data, BSEL - va, BUF0)
    cva = va + len(data)
    dx = (LINK_GETXHX - LINK_GETFIELD) & 0xFFFFFFFF
    dy = (LINK_GETYHX - LINK_GETFIELD) & 0xFFFFFFFF
    code = asm(f"""
    itoa:
        push ebx
        mov  ebx, 10
        xor  ecx, ecx
    i1: xor  edx, edx
        div  ebx
        push edx
        inc  ecx
        test eax, eax
        jne  i1
    i2: pop  eax
        add  al, 0x30
        stosb
        loop i2
        pop  ebx
        ret
    commit:
        mov  byte ptr [edi], 0
        mov  edx, dword ptr [{BSEL:#x}]
        mov  eax, edi
        sub  eax, edx
        mov  dword ptr [edx - 4], eax
        mov  eax, {BUF0 + BUF1:#x}
        sub  eax, edx
        mov  dword ptr [{BSEL:#x}], eax
        mov  eax, dword ptr [{G_TBWINDOW:#x}]
        test eax, eax
        je   sl_ret
        mov  eax, dword ptr [eax + {NEW_FIELD:#x}]
        test eax, eax
        je   sl_ret
        call {T_SETGTEXT:#x}
    sl_ret:
        ret
    blank:
        cmp  dword ptr [{LX:#x}], -1
        je   bl_ret
        mov  dword ptr [{LX:#x}], -1
        mov  edi, dword ptr [{BSEL:#x}]
        mov  dword ptr [edi], 0x2C2D2C2D
        mov  byte ptr [edi + 4], 0x2D
        add  edi, 5
        call commit
    bl_ret:
        ret
    update:
        mov  dword ptr [{FLAG:#x}], 1
        mov  eax, dword ptr [{G_MAP:#x}]
        mov  eax, dword ptr [eax]
        test eax, eax
        je   u_blank
        mov  esi, eax
        mov  eax, dword ptr [esi + {MAP_MOUSE:#x}]
        test eax, eax
        je   u_blank
        mov  edi, eax
        mov  ecx, dword ptr [{IAT_GETFIELD:#x}]
        add  ecx, {dx:#x}
        mov  eax, edi
        call ecx
        cmp  eax, -1
        je   u_blank
        push eax
        mov  ecx, dword ptr [{IAT_GETFIELD:#x}]
        add  ecx, {dy:#x}
        mov  eax, edi
        call ecx
        pop  ecx
        cmp  eax, -1
        je   u_blank
        mov  edx, dword ptr [esi + {MAP_LEVEL:#x}]
        cmp  ecx, dword ptr [{LX:#x}]
        jne  u_chg
        cmp  eax, dword ptr [{LY:#x}]
        jne  u_chg
        cmp  edx, dword ptr [{LZ:#x}]
        je   u_ret
    u_chg:
        mov  dword ptr [{LX:#x}], ecx
        mov  dword ptr [{LY:#x}], eax
        mov  dword ptr [{LZ:#x}], edx
        push edx
        push eax
        mov  edi, dword ptr [{BSEL:#x}]
        mov  eax, ecx
        call itoa
        mov  al, 0x2C
        stosb
        pop  eax
        call itoa
        mov  al, 0x2C
        stosb
        pop  eax
        call itoa
        call commit
    u_ret:
        ret
    u_blank:
        call blank
        ret
    cave_hook:
        push esi
        push edi
        call update
        pop  edi
        pop  esi
        mov  dx, 0x270F
        mov  eax, dword ptr [ebx + 0x44]
        jmp  {HOOK_CONT:#x}
    dmm_wrap:
        mov  dword ptr [{FLAG:#x}], 0
        push dword ptr [esp + 8]
        push dword ptr [esp + 8]
        call {DISPLAYMOUSEMOVE:#x}
        cmp  dword ptr [{FLAG:#x}], 0
        jne  w_done
        push esi
        push edi
        call blank
        pop  edi
        pop  esi
    w_done:
        ret  8
    """, cva)
    return bytes(data) + code, cva


class Exe:
    def __init__(self, name):
        self.name = name
        self.path = os.path.join(GAME, name)
        self.d = bytearray(open(self.path, "rb").read())
        d = self.d
        self.e = struct.unpack_from("<I", d, 0x3C)[0]
        self.nsec = struct.unpack_from("<H", d, self.e + 6)[0]
        self.opt = self.e + 24
        self.tbl = self.opt + struct.unpack_from("<H", d, self.e + 20)[0]

    def secs(self):
        for i in range(self.nsec):
            o = self.tbl + 40 * i
            vs, va, rs, ra = struct.unpack_from("<IIII", self.d, o + 8)
            yield self.d[o:o + 8].rstrip(b"\0"), va, vs, rs, ra, o

    def off(self, va):
        for _n, sva, vs, rs, ra, _o in self.secs():
            if sva <= va - BASE < sva + rs:
                return ra + va - BASE - sva
        sys.exit("ABORT: %s %08X has no file bytes" % (self.name, va))

    def ibnr(self):
        s = list(self.secs())
        n, va, vs, rs, ra, o = s[-1]
        assert n == SEC and va == IBNR_VA - BASE, \
            "%s: .ibnr is not the last section -- build_itembanner_hpmv.py must be applied" % self.name
        assert ra + rs == len(self.d), "%s: .ibnr does not run to EOF" % self.name
        return vs, rs, ra, o


def plan_for(x):
    """Returns (state, blob, sites)."""
    d = x.d
    vs, rs, ra, hdr = x.ibnr()
    grown = rs == NEW_SIZE
    assert rs in (IBNR_OWN, NEW_SIZE), "%s: .ibnr is %#x B, expected %#x or %#x" % (x.name, rs, IBNR_OWN, NEW_SIZE)
    o = x.off(BASE + RES_RVA)
    dfm = bytes(d[o:o + RES_SIZE])
    assert dfm[:4] == b"TPF0", "the .rsrc TTBWINDOW master is not a DFM"
    fo = x.off(FT_VA)
    ft = bytes(d[fo:fo + FT_LEN])
    assert struct.unpack_from("<H", ft, 0)[0] == FT_COUNT
    new_dfm, new_ft = build_dfm(dfm), build_field_table(ft)
    off_ft = (len(new_dfm) + 15) & ~15
    off_code = (off_ft + len(new_ft) + 15) & ~15
    blob_code, cva = build_code(GROW_VA + off_code)
    blob = bytearray(off_code) + blob_code
    blob[:len(new_dfm)] = new_dfm
    blob[off_ft:off_ft + len(new_ft)] = new_ft
    assert IBNR_OWN + len(blob) <= NEW_SIZE, "blob %d B does not fit" % len(blob)
    code = bytes(blob_code[0x80:])
    # entry points, located by their unique first instructions: cave_hook is `push esi / push edi /
    # call update / pop edi / pop esi` right before the replayed `mov dx,0x270F`; dmm_wrap opens with `mov [FLAG],0`
    i = code.find(bytes.fromhex("66ba0f27"))
    j = code.find(bytes.fromhex("c705") + struct.pack("<I", GROW_VA + off_code) + bytes(4))
    assert code.count(bytes.fromhex("66ba0f27")) == 1 and i > 9 and j > 0
    hook_at, wrap_at = cva + i - 9, cva + j
    assert code[i - 9:i - 7] == bytes.fromhex("5657") and code[i - 7] == 0xE8         and code[i - 2:i] == bytes.fromhex("5f5e")
    sites = [
        (VMT_FT_FO, struct.pack("<I", FT_VA), struct.pack("<I", GROW_VA + off_ft), "TTBWindow field-table pointer"),
        (VMT_SIZE_FO, struct.pack("<I", OLD_INST), struct.pack("<I", NEW_INST), "TTBWindow instance size"),
        (RES_ENTRY_FO, struct.pack("<II", RES_RVA, RES_SIZE),
         struct.pack("<II", GROW_VA - BASE, len(new_dfm)), "TTBWINDOW resource entry"),
        (x.off(HOOK), HOOK_ORIG, b"\xE9" + struct.pack("<i", hook_at - (HOOK + 5)) + b"\x90\x90",
         "MapWindowMouseMove hook"),
        (MT_DMM_FO, struct.pack("<I", DISPLAYMOUSEMOVE), struct.pack("<I", wrap_at), "DisplayMouseMove entry"),
    ]
    st = []
    for off, old, new, _desc in sites:
        cur = bytes(d[off:off + len(old)])
        st.append("vanilla" if cur == old else "installed" if cur == new else "FOREIGN " + cur.hex())
    region = bytes(d[ra + IBNR_OWN:ra + IBNR_OWN + len(blob)]) if grown else b""
    if all(s == "vanilla" for s in st) and not grown:
        state = "VANILLA"
    elif all(s == "installed" for s in st) and grown and region == bytes(blob):
        state = "INSTALLED"
    else:
        state = "MIXED"
    return state, st, bytes(blob), sites, (off_ft, off_code, hook_at, wrap_at, len(new_dfm))


def resize(x, size):
    vs, rs, ra, hdr = x.ibnr()
    if size > rs:
        x.d += bytes(size - rs)
    else:
        del x.d[ra + size:]
    struct.pack_into("<I", x.d, hdr + 8, size)
    struct.pack_into("<I", x.d, hdr + 16, size)
    struct.pack_into("<I", x.d, x.opt + 56, IBNR_VA - BASE + size)


def main():
    apply_, undo = "--apply" in sys.argv, "--undo" in sys.argv
    exes = [Exe(n) for n in zigexe.EXES]
    plans = []
    print("build_taskbar_coords")
    for x in exes:
        state, st, blob, sites, info = plan_for(x)
        print("  %-15s %s   %s" % (x.name, state, ", ".join(s.split()[0] for s in st)))
        if any(s.startswith("FOREIGN") for s in st):
            sys.exit("ABORT: foreign bytes at a site")
        plans.append((x, state, blob, sites, info))
    off_ft, off_code, hook_at, wrap_at, dfm_len = plans[0][4]
    print("  DFM %d B (+%d) @%08X | field table @%08X | cave_hook %08X | dmm_wrap %08X | ends %08X"
          % (dfm_len, dfm_len - RES_SIZE, GROW_VA, GROW_VA + off_ft, hook_at, wrap_at,
             GROW_VA + len(plans[0][2])))
    if "--dis" in sys.argv:
        show([("code", GROW_VA + off_code + 0x80, plans[0][2][off_code + 0x80:])])
    if not (apply_ or undo):
        print("\n(dry run -- nothing written)")
        return
    kill_aow()
    for x, state, blob, sites, _info in plans:
        if (apply_ and state == "INSTALLED") or (undo and state == "VANILLA"):
            continue
        if apply_:
            if x.ibnr()[1] != NEW_SIZE:
                resize(x, NEW_SIZE)
            _vs, _rs, ra, _h = x.ibnr()
            x.d[ra + IBNR_OWN:ra + NEW_SIZE] = bytes(NEW_SIZE - IBNR_OWN)
            x.d[ra + IBNR_OWN:ra + IBNR_OWN + len(blob)] = blob
            for off, _old, new, _desc in sites:
                x.d[off:off + len(new)] = new
        else:
            for off, old, _new, _desc in sites:
                x.d[off:off + len(old)] = old
            resize(x, IBNR_OWN)
        open(x.path, "wb").write(x.d)
    a, b = (open(os.path.join(GAME, n), "rb").read() for n in zigexe.EXES)
    diff = [i for i in range(len(a)) if a[i] != b[i]] if len(a) == len(b) else None
    assert diff == [zigexe.COMPAT_BYTE], "lockstep broken: %s" % diff
    print("\n%s both exes; lockstep holds" % ("APPLIED to" if apply_ else "UNDONE on"))


if __name__ == "__main__":
    main()
