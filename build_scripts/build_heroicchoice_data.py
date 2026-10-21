#!/usr/bin/env python
r"""
build_heroicchoice_data.py -- a unit type carries up to three heroic-medal OPTIONS (an ability bundle
plus six stat deltas each) and one ALWAYS ability set, loaded from and saved to Unitres.pfs.
AoWEPACK.dpl only.  Owner's design 2026-10-20 (Always added the same day).  This is the data layer:
build_deved_heroicchoice.py edits it in the editor and build_heroicchoice.py turns it into the
in-game choice and grant.  Layout and tags: heroicchoice.py.

WHAT CHANGES
    size    TUnitResource's instance size 0x54 -> 0x78 (VMT-0x1C).  No class inherits
            TUnitResource (THeroResource derives from TAbstractUnitResource), so nothing else moves.
    create  VMT +0x20 -> cave_create: the original constructor, then four more owners of the
            class the constructor uses for the medal sets ([0x55784B40] -> TUnitResourceAbility
            Owner, read through the cell so the rebase applies), stored at +0x54/+0x58/+0x5C
            (options) and +0x74 (Always).
    destroy VMT -0x04 -> cave_destroy: frees the four owners, then the original destructor.
    rw      VMT +0x18 -> cave_rw: the original ReadWrite, then the options.
            Loading (StorageMode & LOAD_MASK == 1; the translation pass is not a load and only
            streams): the options are cleared first (owner Clear, deltas 0), so a stream that
            carries none -- every record saved before this feature, and every record without
            options -- leaves the type with none.  TEObject.Assign/Copy stream through ReadWrite
            (EngineP Engine.TEObject.Assign @0x555191F4: WriteEObject + ReadEObject), so an
            Assign over a type that had options clears them too.  Then owners (tags 0x21..0x23,
            stream +0x0C), deltas (tags 0x24..0x35, stream +0x30) and the Always owner (tag
            0x36), then ValidateOwnerTypeAbilities on the four owners, as vanilla does for its four.
            Writing: nothing at all unless an option or the Always set is present, so Unitres.pfs
            and the mapset stay byte-identical for every unit type with neither.
    Nothing calls the three methods directly: each is referenced only by its VMT slot and the
    export table, and no other module imports them.

HOOKS (dwords; the three slots' .reloc entries are kept -- the new values are inside this image)
    0x55710A48  instance size   0x54        -> 0x78
    0x55710A60  VMT -0x04       0x55784CC8  -> cave_destroy
    0x55710A7C  VMT +0x18       0x55784DE4  -> cave_rw
    0x55710A84  VMT +0x20       0x55784C44  -> cave_create

Slot 0x558B0000-0x558B03FF, exclusive.  PIC: rel32, register-relative, and one call/pop anchor
for the owner-class cell.  No RNG.  Surgical --undo.

Couplings: build_copper_medal.py patches the bodies of Create/Destroy/ReadWrite (loop counts, the
gold/copper serialiser at 0x55813060); the wrappers call those bodies and touch none of their
bytes, in either order.  build_deved_heroicchoice.py and build_heroicchoice.py read the layout and
abort unless this is installed; undo them first.

    python build_scripts/build_heroicchoice_data.py            dry run + state
    python build_scripts/build_heroicchoice_data.py --apply
    python build_scripts/build_heroicchoice_data.py --undo
    python build_scripts/build_heroicchoice_data.py --dis
"""
import struct, sys
sys.dont_write_bytecode = True

from aowepack_patch import asm, run
import heroicchoice as G

SLOT = G.DATA_SLOT

INSTSIZE_VA = 0x55710A48
SLOT_DESTROY, SLOT_RW, SLOT_CREATE = 0x55710A60, 0x55710A7C, 0x55710A84
ORIG_DESTROY, ORIG_RW, ORIG_CREATE = 0x55784CC8, 0x55784DE4, 0x55784C44
OWNER_CLASS_CELL = 0x55784B40          # [cell] = TUnitResourceAbilityOwner VMT (has its own .reloc)
ABOWNER_CREATE = 0x5574F0EC            # AoWE.TAbilityOwner.Create (EAX=class, DL=1, ECX=0)
ABOWNER_CLEAR = 0x5574F11C             # AoWE.TAbilityOwner.Clear (EAX=owner)
VALIDATE = 0x5574F154                  # AoWE.TAbilityOwner.ValidateOwnerTypeAbilities (EAX=owner)
TOBJECT_FREE = 0x557010B8              # thunk -> VCL30 System.TObject.Free (nil-safe)
# A true load is StorageMode & 0x45 == 1 -- the engine's own test (TEObject.MainReadWrite, EngineP
# 0x55519394) before it calls Clear.  Bit 0 alone also matches TTranslateStorageStream (mode 0x15),
# which TAoWEngine.TranslateEObjectFromFile runs over every resource right after each load and
# which carries no data: clearing on it wiped every option at every load (found 2026-10-20).
LOAD_MASK = 0x45

def build_create(va):
    """EAX = class (or self), DL = allocate flag -- passed through to the original untouched."""
    anchor = va + 7                    # push ebx (1) + push esi (1) + call $+5 (5)
    owners = "".join(f"""
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, dword ptr [ebx + {OWNER_CLASS_CELL - anchor:#x}]
        call {ABOWNER_CREATE:#x}
        mov  dword ptr [esi + {off:#x}], eax""" for off in G.ALL_OWNER_OFFS)
    blob = asm(f"""
        push ebx
        push esi
        call {anchor:#x}
        pop  ebx
        call {ORIG_CREATE:#x}
        mov  esi, eax
        {owners}
        mov  eax, esi
        pop  esi
        pop  ebx
        ret
    """, va)
    assert blob[2] == 0xE8 and blob[7] == 0x5B, "anchor is not at +7"
    return blob


def build_destroy(va):
    frees = "".join(f"""
        mov  eax, dword ptr [esi + {off:#x}]
        call {TOBJECT_FREE:#x}
        mov  dword ptr [esi + {off:#x}], 0""" for off in G.ALL_OWNER_OFFS)
    return asm(f"""
        push eax
        push edx
        push esi
        mov  esi, eax
        {frees}
        pop  esi
        pop  edx
        pop  eax
        jmp  {ORIG_DESTROY:#x}
    """, va)


def build_present(va):
    """AL = 1 when any option is present.  EAX = the TUnitResource.  Preserves EBX/ESI/EDI."""
    owner_tests = "".join(f"""
        mov  eax, dword ptr [ebp + {off:#x}]
        call owner_any
        test al, al
        jne  yes""" for off in G.ALL_OWNER_OFFS)
    return asm(f"""
        push ebp
        mov  ebp, eax
        {owner_tests}
        xor  ecx, ecx
    stat_loop:
        cmp  byte ptr [ebp + ecx + {G.STATS_OFF:#x}], 0
        jne  yes
        inc  ecx
        cmp  ecx, {3 * G.NSTATS}
        jb   stat_loop
        xor  eax, eax
        pop  ebp
        ret
    yes:
        mov  eax, 1
        pop  ebp
        ret
    owner_any:
        test eax, eax
        je   oa_no
        mov  ecx, dword ptr [eax + 0xc]
        mov  edx, dword ptr [eax + 8]
        test edx, edx
        je   oa_no
        add  ecx, 7
        shr  ecx, 3
    oa_loop:
        test ecx, ecx
        je   oa_no
        cmp  byte ptr [edx], 0
        jne  oa_yes
        inc  edx
        dec  ecx
        jmp  oa_loop
    oa_no:
        xor  eax, eax
        ret
    oa_yes:
        mov  eax, 1
        ret
    """, va)


def build_rw(va, present):
    clear = "".join(f"""
        mov  eax, dword ptr [edi + {off:#x}]
        call {ABOWNER_CLEAR:#x}""" for off in G.ALL_OWNER_OFFS)
    owners = "".join(f"""
        mov  ecx, {tag:#x}
        mov  edx, dword ptr [edi + {off:#x}]
        mov  eax, esi
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0xc]""" for off, tag in zip(G.OWNER_OFFS, G.OWNER_TAGS))
    always = f"""
        mov  ecx, {G.ALWAYS_TAG:#x}
        mov  edx, dword ptr [edi + {G.ALWAYS_OFF:#x}]
        mov  eax, esi
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0xc]"""
    stats = "".join(f"""
        mov  ecx, {G.stat_tag(k, i):#x}
        lea  edx, [edi + {G.stat_off(k, i):#x}]
        mov  eax, esi
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x30]""" for k in range(3) for i in range(G.NSTATS))
    validate = "".join(f"""
        mov  eax, dword ptr [edi + {off:#x}]
        call {VALIDATE:#x}""" for off in G.ALL_OWNER_OFFS)
    return asm(f"""
        push ebx
        push esi
        push edi
        mov  edi, eax
        mov  esi, edx
        call {ORIG_RW:#x}
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx]
        mov  ecx, eax
        and  al, {LOAD_MASK:#x}
        cmp  al, 1
        je   reading
        test cl, 1
        jne  stream
        mov  eax, edi
        call {present:#x}
        test al, al
        je   done
        jmp  stream
    reading:
        {clear}
        xor  eax, eax
        mov  dword ptr [edi + {G.STATS_OFF:#x}], eax
        mov  dword ptr [edi + {G.STATS_OFF + 4:#x}], eax
        mov  dword ptr [edi + {G.STATS_OFF + 8:#x}], eax
        mov  dword ptr [edi + {G.STATS_OFF + 12:#x}], eax
        mov  word ptr [edi + {G.STATS_OFF + 16:#x}], ax
    stream:
        {owners}
        {stats}
        {always}
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx]
        test al, 1
        je   done
        {validate}
    done:
        pop  edi
        pop  esi
        pop  ebx
        ret
    """, va)


def layout():
    """Caves packed in order, each 16-aligned.  cave_present is a public entry: build_heroicchoice.py
    calls it (EAX = TUnitResource -> AL), so its address is pinned by an assert."""
    out, va = [], SLOT[0]
    for name, fn in (("cave_create", build_create), ("cave_destroy", build_destroy),
                     ("cave_present", build_present), ("cave_rw", None)):
        blob = fn(va) if fn else build_rw(va, dict((n, v) for n, v, _ in out)["cave_present"])
        out.append((name, va, blob))
        va = (va + len(blob) + 15) & ~15
    return out


caves = layout()
CAVE_CREATE, CAVE_DESTROY, CAVE_PRESENT, CAVE_RW = (v for _n, v, _b in caves)
assert CAVE_PRESENT == G.DATA_PRESENT, "cave_present moved: update heroicchoice.DATA_PRESENT"
hooks = [(INSTSIZE_VA, struct.pack("<I", G.INSTSIZE_OLD), struct.pack("<I", G.INSTSIZE)),
         (SLOT_DESTROY, struct.pack("<I", ORIG_DESTROY), struct.pack("<I", CAVE_DESTROY)),
         (SLOT_RW, struct.pack("<I", ORIG_RW), struct.pack("<I", CAVE_RW)),
         (SLOT_CREATE, struct.pack("<I", ORIG_CREATE), struct.pack("<I", CAVE_CREATE))]

if __name__ == "__main__":
    run("build_heroicchoice_data", hooks, caves, SLOT, [],
        reloc_ok=(SLOT_DESTROY, SLOT_RW, SLOT_CREATE))
