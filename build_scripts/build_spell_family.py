#!/usr/bin/env python
r"""
build_spell_family.py -- the caster FAMILY of every spell becomes data: Spells.pfs tag 0x12,
streamed into spell byte +0x23.  AoWEPACK.dpl + Release/Spells.pfs.   (2026-09-25)

    0 none   1 Evoker   2 Conjurer   3 Enchanter   4 Ritualist      ability id = 0xAB + family

Consumer: build_caster_cost.py's cave_cost reads [spell+0x23] and queries ability 0xAB+family.
Before this, the family was the spell's CLASS (a VMT slot-difference test), so a spell could not
be moved between families without new code.  The editor half (AoWDevEd) is a separate script.

HALF 1 -- THE STREAM HOOK (AoWEPACK.dpl)
    TSpell.ReadWrite 0x55779234 is [VMT+0x18] of all 117 spell classes and is shared by the game
    (Spells.pfs load) and the editor (Spells.pfs save).  Its tail at 0x557792BB streams tag 0x11
    (research tier, byte +0x21) through [stream+0x30]:
        8d 53 21 / b9 11 00 00 00 / 8b c6 / 8b 18 / ff 53 30 / 5f 5e 5b c3
    [stream+0x30] is rwByte: Engine.TEReadStorageStream's VMT holds rwInteger at +0x2C (the dword
    tags 0x0D-0x0F) and rwByte 0x55510F44 at +0x30, and every tag-0x11 field in the installed
    Spells.pfs is 1 byte.  The 8 bytes `lea edx,[ebx+0x21]; mov ecx,0x11` go to cave_rw, which
    replays tag 0x11 with EDI as the VMT scratch (EDI is popped by the epilogue, so it is free)
    and then streams tag 0x12 into [ebx+0x23] the same way, and runs the epilogue itself.
    ABSENT TAG ON READ: rwByte's not-found arm (0x55510F89) does `mov byte ptr [edi],0`, so a
    record without tag 0x12 -- an old file, or vanilla's -- loads family 0, i.e. no discount.
    +0x23 is alignment padding: TSpell instance size 0x34, no method of the 117 classes touches it.
    Hook 0x557792BB (8 B, no .reloc) -> cave_rw 0x5584D2C0 (slot 0x5584D2C0-0x5584D2FF).

HALF 2 -- THE DATA (Release/Spells.pfs)
    Every record gets tag 0x12 = 1 byte, encoded as tag 0x11 is: a WIDE (u32,u32) directory
    entry appended after the last one, the byte appended after the last payload byte.  Offsets
    are relative to the END of the directory, so no existing entry moves; the body grows 9 B and
    every later file-index offset moves by 9 per earlier record.  Trailing CRC recomputed.
    Values come from the CLASS rule, read live from the DLL (VMT walk: 117 VMTs with
    [VMT+0x18] == TSpell.ReadWrite; spell id from each class's own Create, `mov [reg+0x10],imm32`):
        [VMT+0x6C]-[VMT+0x18]  0x6B27C -> 2   0x767E0 -> 4   0x1FF4 -> 3
                               0x120 and [VMT+0x80]-[VMT+0x18] == 0x7E034 -> 1   else 0
    Spell 109 (Embrittle) has no class of its own: build_embrittle.py instantiates TSlow, so it
    takes TSlow's family.  Expected: 31 Evoker, 13 Conjurer, 18 Enchanter, 12 Ritualist, 35 none.
    --apply only ADDS a missing tag; a tag already present (e.g. authored in the editor) is left
    alone and reported if it differs from the class rule.

ORDER: this script before build_caster_cost.py's data classifier (else every discount is lost in
between); build_caster_cost.py's cave_cost back to the class test before this script's --undo.

USAGE
    python build_spell_family.py            verify / dry run (writes nothing)
    python build_spell_family.py --dis
    python build_spell_family.py --apply    hook, then Spells.pfs
    python build_spell_family.py --undo     surgical: tag 0x12 removed from every record, hook restored
Snapshot: <game dir>\backups\Spells.pfs.pre-spellfamily, on --apply only, and only from a file
with no tag 0x12 anywhere.  The DLL half has no snapshot; its --undo is surgical.
"""
import os, sys, struct, shutil, zlib, importlib.util, collections
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from aowepack_patch import asm, jmp_to, run, kill_aow, GAME, TARGET

SLOT = (0x5584D2C0, 0x5584D300)
CAVE = 0x5584D2C0
HOOK = 0x557792BB
VAN = bytes.fromhex("8d5321b911000000")     # lea edx,[ebx+0x21] / mov ecx,0x11
TAG, FIELD = 0x12, 0x23

SRC = """
    lea edx, [ebx+0x21]
    mov ecx, 0x11
    mov eax, esi
    mov edi, [eax]
    call dword ptr [edi+0x30]
    lea edx, [ebx+0x23]
    mov ecx, 0x12
    mov eax, esi
    mov ebx, [eax]
    call dword ptr [ebx+0x30]
    pop edi
    pop esi
    pop ebx
    ret
"""
caves = [("cave_rw", CAVE, asm(SRC, CAVE))]
hooks = [(HOOK, VAN, jmp_to(HOOK, CAVE, len(VAN)))]
interior = [(HOOK, HOOK + len(VAN), 0x55779234, 0x557792CE)]

SPELLS = os.path.join(GAME, "Release", "Spells.pfs")
BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, "Spells.pfs.pre-spellfamily")
PFS_RESIDUE = 0x2144DF1C
READWRITE = 0x55779234
TSLOW_CREATE = 0x557F8890          # build_embrittle.py builds spell 109 from this ctor
EMBRITTLE = 109
EXPECT = {1: 31, 2: 13, 3: 18, 4: 12, 0: 35}
NAMES = {0: "none", 1: "Evoker", 2: "Conjurer", 3: "Enchanter", 4: "Ritualist"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


T = _load("_pfs_typos", os.path.join(HERE, "build_pfs_typos.py"))


# ------------------------------------------------------------------ class rule, from the live DLL
def class_families():
    """{spell id: family} by the class rule, read from the live AoWEPACK.dpl."""
    rt = os.path.join(HERE, "..", "re_tools")
    sys.path.insert(0, rt)
    from aowsyms import _vmts, get_symbols
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    pe, base, exp, _iat = get_symbols("AoWEPACK.dpl")
    u32 = lambda va: pe.u32(va - base)
    vm = [(v, n) for v, n in _vmts(pe) if u32(v + 0x18) == READWRITE]
    assert len(vm) == 117, "expected 117 TSpell-subtree VMTs, found %d" % len(vm)
    fam = {}
    for v, n in vm:
        k = (u32(v + 0x6C) - u32(v + 0x18)) & 0xFFFFFFFF
        c = (u32(v + 0x80) - u32(v + 0x18)) & 0xFFFFFFFF
        fam[n] = 2 if k == 0x6B27C else 4 if k == 0x767E0 else 3 if k == 0x1FF4 else \
            1 if (k == 0x120 and c == 0x7E034) else 0
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    out, create_of = {}, {}
    for va, nm in exp.items():
        p = nm.split(".")
        if len(p) == 3 and p[2] == "Create" and p[1] in fam:
            create_of[p[1]] = va
            ids = []
            for ins in md.disasm(pe.read(va - base, 0x200), va):
                if ins.mnemonic == "ret":
                    break
                b = ins.bytes
                if b[0] == 0xC7 and len(b) == 7 and b[2] == 0x10 and (b[1] & 0xC0) == 0x40:
                    ids.append(struct.unpack_from("<I", b, 3)[0])
            if ids:
                assert len(ids) == 1, "%s.Create stores %d spell ids" % (p[1], len(ids))
                assert ids[0] not in out, "spell id %d claimed by two classes" % ids[0]
                out[ids[0]] = fam[p[1]]
    assert len(out) == 108, "expected 108 concrete spell classes, found %d" % len(out)
    # spell 109: an instance of TSlow built in a cave (build_embrittle.py)
    assert create_of.get("TSlow") == TSLOW_CREATE, "TSlow.Create moved?"
    out[EMBRITTLE] = fam["TSlow"]
    return out


# ------------------------------------------------------------------ Spells.pfs container
def layout(d):
    """-> (base, index entries, [(rid, body)] in offset order, last body excludes the CRC)."""
    base, ent = T.index_layout(bytes(d))
    order = sorted(ent, key=lambda e: e[1])
    bodies = []
    for j, e in enumerate(order):
        end = order[j + 1][1] if j + 1 < len(order) else len(d) - 4 - base
        bodies.append((e[0], bytes(d[base + e[1]: base + end])))
    assert [e[0] for e in order] == sorted(e[0] for e in ent), "id order != offset order"
    return base, ent, bodies


def rebuild(d, base, ent, bodies):
    """Concatenate `bodies` (offset order), rewrite every index offset, repair the CRC."""
    out = bytearray(d[:base])
    newoff, run_ = {}, 0
    for rid, b in bodies:
        newoff[rid] = run_
        run_ += len(b)
    for rid, _o, pos, w in ent:
        v = newoff[rid]
        if w == 1:
            assert v <= 0xFF, "record %d: small index entry would overflow (%d)" % (rid, v)
            out[pos] = v
        else:
            struct.pack_into("<I", out, pos, v)
    out += b"".join(b for _r, b in bodies) + b"\0\0\0\0"
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    assert zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF == PFS_RESIDUE, "CRC repair failed"
    return out


def fields(body):
    e, s = T.body_dir(body)
    return e, s, T.slice_fields(body, e, s)


def add_tag(body, value):
    """Append tag 0x12 as the last WIDE entry and the last payload byte (tag 0x11's own form)."""
    e, dsz, f = fields(body)
    assert TAG not in f
    assert f.get(0x11) is not None and len(f[0x11]) == 1, "tag 0x11 is not a 1-byte field"
    assert body[0] & 0x80 and [w for t, _o, w in e if t == 0x11] == [4], \
        "tag 0x11 is not a wide entry -- unfamiliar record shape"
    wide = struct.unpack_from("<I", body, 1)[0]
    new = bytearray(body[:dsz]) + struct.pack("<II", TAG, len(body) - dsz) + body[dsz:] + bytes([value])
    struct.pack_into("<I", new, 1, wide + 1)
    e2, s2, f2 = fields(bytes(new))
    want = dict(f); want[TAG] = bytes([value])
    assert f2 == want, "add_tag did not round-trip"
    return bytes(new)


def del_tag(body):
    """Remove tag 0x12 wherever it sits: its entry, its payload byte, later offsets -1 per byte."""
    e, dsz, f = fields(body)
    k = [i for i, (t, _o, _w) in enumerate(e) if t == TAG]
    assert len(k) == 1
    _t, off, w = e[k[0]]
    n = len(f[TAG])
    small = body[0] & 0x7F
    wide = struct.unpack_from("<I", body, 1)[0] if body[0] & 0x80 else 0
    if w == 1:
        small -= 1
    else:
        wide -= 1
    hdr = bytearray([small | (0x80 if (body[0] & 0x80) else 0)])
    if body[0] & 0x80:
        hdr += struct.pack("<I", wide)
    for t, o, ww in e:
        if t == TAG:
            continue
        o2 = o - n if o > off else o
        hdr += bytes([t, o2]) if ww == 1 else struct.pack("<II", t, o2)
    pay = body[dsz:dsz + off] + body[dsz + off + n:]
    new = bytes(hdr) + pay
    f2 = fields(new)[2]
    want = dict(f); del want[TAG]
    assert f2 == want, "del_tag did not round-trip"
    return new


def pfs_state(d, fam):
    base, ent, bodies = layout(d)
    have, diff, missing = {}, [], []
    for rid, b in bodies:
        f = fields(b)[2]
        sid = rid - 10
        if TAG in f:
            have[rid] = f[TAG][0]
            if sid in fam and f[TAG][0] != fam[sid]:
                diff.append((sid, f[TAG][0], fam[sid]))
        else:
            missing.append(rid)
    return base, ent, bodies, have, diff, missing


def pfs_main(mode):
    d = bytearray(open(SPELLS, "rb").read())
    print("\nSpells.pfs -- %s" % SPELLS)
    if zlib.crc32(bytes(d[4:])) & 0xFFFFFFFF != PFS_RESIDUE:
        sys.exit("ABORT: Spells.pfs CRC residue already wrong -- refusing to touch a damaged file")
    fam = class_families()
    base, ent, bodies, have, diff, missing = pfs_state(d, fam)
    sids = [rid - 10 for rid, _b in bodies]
    unknown = [s for s in sids if s not in fam]
    if unknown:
        sys.exit("ABORT: records for spell ids with no class: %s" % unknown)
    cls = collections.Counter(fam[s] for s in sids)
    print("  %d records; class rule: %s" % (len(bodies), ", ".join(
        "%s %d" % (NAMES[k], cls[k]) for k in (1, 2, 3, 4, 0))))
    if dict(cls) != EXPECT:
        sys.exit("ABORT: class counts %s, expected %s" % (dict(cls), EXPECT))
    print("  tag 0x12 present on %d, missing on %d" % (len(have), len(missing)))
    if have:
        cur = collections.Counter(have.values())
        print("  installed values: %s" % ", ".join("%s %d" % (NAMES.get(k, "?%d" % k), cur[k])
                                                   for k in sorted(cur)))
    for sid, got, rule in diff:
        print("  spell %3d: tag 0x12 = %d (%s), class rule says %d -- authored, left alone"
              % (sid, got, NAMES.get(got, "?"), rule))
    if mode == "dis":
        for rid, _b in bodies:
            print("    record %3d  spell %3d  %s" % (rid, rid - 10, NAMES[fam[rid - 10]]))
    if mode not in ("apply", "undo"):
        return
    if mode == "apply" and not missing:
        print("  already applied -- nothing to do"); return
    if mode == "undo" and not have:
        print("  no tag 0x12 anywhere -- nothing to do"); return
    if mode == "apply":
        if not have and not os.path.exists(BACKUP):     # proved unpatched: no tag 0x12 at all
            os.makedirs(BACKUP_DIR, exist_ok=True)
            shutil.copy2(SPELLS, BACKUP)
            print("  backup -> %s" % BACKUP)
        new_bodies = [(rid, add_tag(b, fam[rid - 10]) if rid in missing else b) for rid, b in bodies]
    else:
        new_bodies = [(rid, del_tag(b) if rid in have else b) for rid, b in bodies]
    out = rebuild(d, base, ent, new_bodies)
    # audit: every OTHER tag of every record byte-identical
    _b2, _e2, check = layout(out)
    assert [r for r, _ in check] == [r for r, _ in bodies]
    for (rid, ob), (_r, nb) in zip(bodies, check):
        fo, fn = fields(ob)[2], fields(nb)[2]
        fo.pop(TAG, None)
        tn = fn.pop(TAG, None)
        assert fo == fn, "record %d: another tag changed" % rid
        if mode == "apply":
            assert tn is not None and len(tn) == 1
        else:
            assert tn is None
    kill_aow()
    with open(SPELLS, "wb") as f:
        f.write(out)
    print("  %s: %d -> %d bytes, CRC repaired, every other tag byte-identical"
          % ("tag 0x12 ADDED to %d records" % len(missing) if mode == "apply"
             else "tag 0x12 REMOVED from %d records" % len(have), len(d), len(out)))


if __name__ == "__main__":
    argv = sys.argv[1:]
    mode = "apply" if "--apply" in argv else "undo" if "--undo" in argv else \
        "dis" if "--dis" in argv else "verify"
    if mode == "undo":
        from aowepack_patch import va2off
        dll = open(TARGET, "rb").read()
        o = va2off(dll, 0x55820800)
        if b"\x0f\xb6\x56\x23" in dll[o:o + 0x78] and "--force" not in argv:
            sys.exit("ABORT: build_caster_cost.py's cave_cost reads [spell+0x23] -- undo its data "
                     "classifier first (build_caster_cost.py --classic --apply), or every caster "
                     "discount is lost.  --force overrides.")
        argv = [a for a in argv if a != "--force"]
        # data first: a hook without tags is harmless (family 0); tags without the hook are inert
        pfs_main("undo")
        run("build_spell_family (TSpell.ReadWrite tag 0x12 -> +0x23)", hooks, caves, SLOT, interior, argv)
    else:
        run("build_spell_family (TSpell.ReadWrite tag 0x12 -> +0x23)", hooks, caves, SLOT, interior, argv)
        pfs_main(mode)
