#!/usr/bin/env python3
r"""
AoW1 movement-predictor fix for AoWEPACK.dpl
Builds a code cave implementing per-unit path walking (TrueReachPos) and hooks
three call sites:
  1. TMoveArmyTE.Setup   @ 55747B01 - execution path truncation
  2. MoveArmyEx          @ 5574A36E - destination-reached check (attack/combine)
  3. TSelectedArmy.Update@ 557936A3 - TMoveSettings+14h synthetic budget (UI)

Cave: 0x5580D700.  Sole owner -- no other build script references that VA.

⚠⚠ THE BACKUP LINE  --  CHANGED 2026-09-10
  `BACKUP` used to be `os.path.join(GAME, "AoWEPACK_original_backup.dpl")`, i.e. the
  name of the PRISTINE VANILLA REFERENCE, and line ~284 does `shutil.copyfile(DPL,
  BACKUP)` -- so `--apply` wrote the live PATCHED DLL over a file with the reference's
  name.  That is the whole reason CLAUDE.md and the project memory carry a standing
  "never run build_patch.py --apply".

  Where it landed changed under the script's feet.  `GAME` is `__file__/../..`, which
  the 2026-09-09 move redefined from the game ROOT to `<root>\Ziggurat\`, while the real
  reference has sat at `<root>\Ziggurat\Modding Resources\AoWEPACK_original_backup.dpl`
  throughout.  So the copy has been landing beside the reference rather than on it, and
  today would only have dropped a 2.7 MB stray `Ziggurat\AoWEPACK_original_backup.dpl`
  that looks exactly like the reference and is a patched DLL.  Near-miss, not a rescue:
  the destination moved by accident, not by design, and a mis-set `AOW_GAME_DIR` aims it
  straight back.  ⚠ Do not read this as clearance to run `--apply` -- see REVERT below.

  Now: `<game dir>\backups\AoWEPACK.dpl.pre-patch`, per the standing rule (2026-09-03),
  created on demand and only on `--apply`.  The reference's NAME appears nowhere in this
  file any more, so no path here can reach it.

  ⚠ The snapshot is also gated on freshness.  The verify loop treats an already-patched
  site as OK and falls through, so a second `--apply` -- or an `--apply` over a re-tune --
  would otherwise mint a `.pre-patch` from the script's OWN OUTPUT: a snapshot sitting on
  disk looking authoritative while containing patched bytes.  It is written only when no
  site reported ALREADY PATCHED and no snapshot exists yet.

REVERT
  ⚠ There is NONE.  This script has no `--undo` and no `--revert`; the three sites and
  the cave must be restored by hand from the vanilla bytes listed in `patches` (the
  `orig` column) if the patch is ever backed out.  The `.pre-patch` snapshot is NOT a
  revert path -- restoring a whole-file snapshot wipes every other feature applied to
  AoWEPACK.dpl since it was taken.
"""
import shutil, sys, os

# GAME = two levels up from this script (<root>\Ziggurat\Modding Resources\build_scripts\),
# i.e. <root>\Ziggurat -- the MOD directory, which is where the live packages are.
# ⚠ Leave AOW_GAME_DIR unset; setting it silently redirects every write below.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

DPL = os.path.join(GAME, "AoWEPACK.dpl")

BACKUP_DIR = os.path.join(GAME, "backups")
BACKUP = os.path.join(BACKUP_DIR, os.path.basename(DPL) + ".pre-patch")

FILE_DELTA = 0x55700C00           # VA - FILE_DELTA = file offset (CODE section)

# game function addresses
TRANSPORTER      = 0x5578E00C     # TArmy.Transporter(eax=army, edx=mask) -> eax unit*/0
UNIT_CREATE_MPT  = 0x5577FDC4     # TAbstractUnit.CreateMovePointTable(eax=unit, edx=buf256)
GETFIELD_STUB    = 0x557020FC     # TMapContainer.GetField(eax=cont, edx=x, ecx=y, push level)
GETMOVESETTINGS  = 0x557639DC     # TMoveSettingsList.GetMoveSettings(eax=list, edx=i)
POS_TO_MP        = 0x55763904     # TMovepath.PosToMovePoints(eax=path, edx=pos) -> eax cost
AOWHSMAP         = 0x558FA040     # global: pointer to TAoWHSMap

CAVE_BASE = 0x5580D700

# ---------------------------------------------------------------- assembler --
class Asm:
    def __init__(self, base):
        self.base = base
        self.buf = bytearray()
        self.labels = {}
        self.fix32 = []   # (offset_in_buf, label)  E8/E9 rel32
        self.fix8  = []   # (offset_in_buf, label)  short jcc/jmp rel8
    def here(self): return self.base + len(self.buf)
    def label(self, name): self.labels[name] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def call(self, target):          # E8 rel32, target = int VA or label str
        self.db(0xE8); self._rel32(target)
    def jmp32(self, target):
        self.db(0xE9); self._rel32(target)
    def _rel32(self, target):
        if isinstance(target, str):
            self.fix32.append((len(self.buf), target)); self.buf += b'\0\0\0\0'
        else:
            rel = target - (self.here() + 4)
            self.buf += rel.to_bytes(4, 'little', signed=True)
    def j8(self, opcode, label):     # short jump with rel8 to label
        self.db(opcode); self.fix8.append((len(self.buf), label)); self.db(0x00)
    def resolve(self):
        for off, lab in self.fix32:
            rel = self.labels[lab] - (self.base + off + 4)
            self.buf[off:off+4] = rel.to_bytes(4, 'little', signed=True)
        for off, lab in self.fix8:
            rel = self.labels[lab] - (self.base + off + 1)
            assert -128 <= rel <= 127, f"rel8 out of range for {lab}: {rel}"
            self.buf[off] = rel & 0xFF

a = Asm(CAVE_BASE)

# ------------------------------------------------------------ cave_exec -----
# called instead of MovePointsToPos from TMoveArmyTE.Setup @55747B01
# in: eax = path, edx = minMP (ignored); caller frame: [ebp-4]=armyHS, [ebp-5]=mask
a.label('cave_exec')
a.db(0x8B, 0xC8)                    # mov ecx, eax          ; path
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]      ; armyHS
a.db(0x8B, 0x40, 0x1C)              # mov eax, [eax+0x1C]   ; TArmy
a.db(0x0F, 0xB6, 0x55, 0xFB)        # movzx edx, byte [ebp-5] ; mask
a.jmp32('true_reach')               # tail-jump; ret goes back to Setup

# -------------------------------------------------------- cave_movearmy -----
# called instead of MovePointsToPos from MoveArmyEx @5574A36E
# in: eax = path, edx = minMP (ignored); esi = armyHS; [ebp-1] = mask
a.label('cave_movearmy')
a.db(0x8B, 0xC8)                    # mov ecx, eax          ; path
a.db(0x8B, 0x46, 0x1C)              # mov eax, [esi+0x1C]   ; TArmy
a.db(0x0F, 0xB6, 0x55, 0xFF)        # movzx edx, byte [ebp-1] ; mask
a.jmp32('true_reach')

# --------------------------------------------------------- cave_display -----
# replaces 13 bytes in TSelectedArmy.Update @557936A3
# in: ebp = minMP, esi = settings index, ebx = TSelectedArmy
# must preserve ebx/esi/edi/ebp
a.label('cave_display')
a.db(0x57)                          # push edi
a.db(0x8B, 0xD6)                    # mov edx, esi
a.db(0x8B, 0x43, 0x08)              # mov eax, [ebx+8]      ; settings list
a.call(GETMOVESETTINGS)             # -> eax = TMoveSettings
a.db(0x8B, 0xF8)                    # mov edi, eax
a.db(0x89, 0x6F, 0x14)              # mov [edi+0x14], ebp   ; vanilla default
a.db(0x8B, 0x4F, 0x08)              # mov ecx, [edi+8]      ; path
a.db(0x83, 0x79, 0x08, 0x02)        # cmp dword [ecx+8], 2  ; path count
a.j8(0x7C, 'disp_out')              # jl  -> keep vanilla
a.db(0x8B, 0x47, 0x10)              # mov eax, [edi+0x10]   ; armyHS
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x74, 'disp_out')              # jz  -> keep vanilla
a.db(0x8B, 0x40, 0x1C)              # mov eax, [eax+0x1C]   ; TArmy
a.db(0x0F, 0xB6, 0x57, 0x20)        # movzx edx, byte [edi+0x20] ; selection mask
a.call('true_reach')                # -> eax = true reach position
a.db(0x8B, 0xD0)                    # mov edx, eax
a.db(0x8B, 0x47, 0x08)              # mov eax, [edi+8]      ; path
a.call(POS_TO_MP)                   # -> eax = B* (merged cost of true prefix)
a.db(0x89, 0x47, 0x14)              # mov [edi+0x14], eax   ; synthetic budget
a.label('disp_out')
a.db(0x5F)                          # pop edi
a.db(0xC3)                          # ret

# ---------------------------------------------------------- true_reach ------
# TrueReachPos(eax=TArmy, edx=mask byte, ecx=path) -> eax = position index
# position semantics identical to TMovepath.MovePointsToPos (0 = destination)
a.label('true_reach')
a.db(0x55)                          # push ebp
a.db(0x8B, 0xEC)                    # mov ebp, esp
a.db(0x81, 0xEC, 0x10, 0x01, 0x00, 0x00)  # sub esp, 0x110
a.db(0x53)                          # push ebx
a.db(0x56)                          # push esi
a.db(0x57)                          # push edi
a.db(0x89, 0x45, 0xF8)              # mov [ebp-8], eax      ; army
a.db(0x89, 0x55, 0xF4)              # mov [ebp-0xC], edx    ; mask
a.db(0x89, 0x4D, 0xFC)              # mov [ebp-4], ecx      ; path
a.db(0xC7, 0x45, 0xF0, 0xFF, 0xFF, 0xFF, 0xFF)  # mov dword [ebp-0x10], -1 ; best = none
# transporter? (eax=army, edx=mask still live)
a.call(TRANSPORTER)
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x74, 'tr_multi')              # jz multi
a.db(0x8B, 0xD8)                    # mov ebx, eax          ; unit = transporter
a.call('unit_walk')
a.db(0x89, 0x45, 0xF0)              # mov [ebp-0x10], eax
a.j8(0xEB, 'tr_done')               # jmp done
a.label('tr_multi')
a.db(0x8B, 0x45, 0xF8)              # mov eax, [ebp-8]
a.db(0x8B, 0x10)                    # mov edx, [eax]
a.db(0xFF, 0x52, 0x54)              # call [edx+0x54]       ; unit count
a.db(0x8B, 0xF8)                    # mov edi, eax          ; count
a.db(0x33, 0xF6)                    # xor esi, esi          ; index
a.label('tr_uloop')
a.db(0x3B, 0xF7)                    # cmp esi, edi
a.j8(0x7D, 'tr_done')               # jge done
a.db(0xB8, 0x01, 0x00, 0x00, 0x00)  # mov eax, 1
a.db(0x8B, 0xCE)                    # mov ecx, esi
a.db(0xD3, 0xE0)                    # shl eax, cl
a.db(0x85, 0x45, 0xF4)              # test [ebp-0xC], eax   ; selected?
a.j8(0x74, 'tr_next')               # jz next
a.db(0x8B, 0x45, 0xF8)              # mov eax, [ebp-8]      ; army
a.db(0x8B, 0x40, 0x08)              # mov eax, [eax+8]      ; TUnitList
a.db(0x8B, 0x40, 0x04)              # mov eax, [eax+4]      ; items
a.db(0x8B, 0x1C, 0xB0)              # mov ebx, [eax+esi*4]  ; unit
a.call('unit_walk')                 # -> eax = unit stop pos
a.db(0x3B, 0x45, 0xF0)              # cmp eax, [ebp-0x10]
a.j8(0x7E, 'tr_next')               # jle next (keep max = worst unit)
a.db(0x89, 0x45, 0xF0)              # mov [ebp-0x10], eax
a.label('tr_next')
a.db(0x46)                          # inc esi
a.j8(0xEB, 'tr_uloop')              # jmp uloop
a.label('tr_done')
a.db(0x8B, 0x45, 0xF0)              # mov eax, [ebp-0x10]
a.db(0x83, 0xF8, 0xFF)              # cmp eax, -1           ; no unit processed?
a.j8(0x75, 'tr_fin')                # jnz fin
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]
a.db(0x8B, 0x40, 0x08)              # mov eax, [eax+8]
a.db(0x48)                          # dec eax               ; = source pos (no reach)
a.label('tr_fin')
a.db(0x5F)                          # pop edi
a.db(0x5E)                          # pop esi
a.db(0x5B)                          # pop ebx
a.db(0x8B, 0xE5)                    # mov esp, ebp
a.db(0x5D)                          # pop ebp
a.db(0xC3)                          # ret

# ----------------------------------------------------------- unit_walk ------
# in: ebx = unit*, ebp = true_reach frame; out: eax = stop position
# walks path from source (count-1) toward destination (0) using the unit's own
# cost table and remaining MP -- mirrors actual per-hex deduction in MovedTo.
a.label('unit_walk')
a.db(0x56)                          # push esi
a.db(0x57)                          # push edi
a.db(0x8B, 0xC3)                    # mov eax, ebx
a.db(0x8D, 0x95, 0xF0, 0xFE, 0xFF, 0xFF)  # lea edx, [ebp-0x110] ; 256-byte buf
a.call(UNIT_CREATE_MPT)             # build unit cost table (incl. haste etc.)
a.db(0x8B, 0xC3)                    # mov eax, ebx
a.db(0x8B, 0x10)                    # mov edx, [eax]
a.db(0xFF, 0x92, 0xD8, 0x00, 0x00, 0x00)  # call [edx+0xD8] ; unit.MovePoints -> al
a.db(0x0F, 0xBE, 0xF8)              # movsx edi, al         ; edi = mp
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]      ; path
a.db(0x8B, 0x70, 0x08)              # mov esi, [eax+8]      ; count
a.db(0x4E)                          # dec esi               ; pos = count-1 (source)
a.label('uw_walk')
a.db(0x85, 0xF6)                    # test esi, esi
a.j8(0x7E, 'uw_done')               # jle done (0 = destination reached)
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]
a.db(0x8B, 0x40, 0x04)              # mov eax, [eax+4]      ; items
a.db(0x8B, 0x54, 0xB0, 0xFC)        # mov edx, [eax+esi*4-4] ; next hop entry
a.db(0x8B, 0xCA)                    # mov ecx, edx
a.db(0xC1, 0xE9, 0x10)              # shr ecx, 16
a.db(0x81, 0xE1, 0xFF, 0x00, 0x00, 0x00)  # and ecx, 0xFF  ; level
a.db(0x51)                          # push ecx              ; GetField stack arg
a.db(0x8B, 0xCA)                    # mov ecx, edx
a.db(0xC1, 0xE9, 0x08)              # shr ecx, 8
a.db(0x81, 0xE1, 0xFF, 0x00, 0x00, 0x00)  # and ecx, 0xFF  ; y
a.db(0x81, 0xE2, 0xFF, 0x00, 0x00, 0x00)  # and edx, 0xFF  ; x
a.db(0xA1) ; a.buf += AOWHSMAP.to_bytes(4, 'little')  # mov eax, [AoWHSMap]
a.db(0x8B, 0x40, 0x10)              # mov eax, [eax+0x10]   ; TMapContainer
a.call(GETFIELD_STUB)               # -> eax = TMapField*
a.db(0xF6, 0x40, 0x19, 0x40)        # test byte [eax+0x19], 0x40 ; special hex?
a.j8(0x74, 'uw_tbl')                # jz table cost
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]      ; special: use stored
a.db(0x8B, 0x40, 0x04)              # mov eax, [eax+4]      ;   merged cost byte
a.db(0x0F, 0xBE, 0x54, 0xB0, 0xFF)  # movsx edx, byte [eax+esi*4-1]
a.j8(0xEB, 'uw_have')               # jmp have
a.label('uw_tbl')
a.db(0x0F, 0xB6, 0x50, 0x14)        # movzx edx, byte [eax+0x14] ; terrain
a.db(0xC1, 0xE2, 0x04)              # shl edx, 4
a.db(0x0F, 0xB6, 0x48, 0x15)        # movzx ecx, byte [eax+0x15] ; road
a.db(0x03, 0xD1)                    # add edx, ecx
a.db(0x8D, 0x8D, 0xF0, 0xFE, 0xFF, 0xFF)  # lea ecx, [ebp-0x110]
a.db(0x0F, 0xBE, 0x54, 0x11, 0x01)  # movsx edx, byte [ecx+edx+1] ; +1 like game
a.label('uw_have')
a.db(0x85, 0xD2)                    # test edx, edx
a.j8(0x78, 'uw_done')               # js done (0xFF impassable for this unit)
a.db(0x3B, 0xD7)                    # cmp edx, edi
a.j8(0x7F, 'uw_done')               # jg done (cost > remaining mp)
a.db(0x2B, 0xFA)                    # sub edi, edx          ; mp -= cost
a.db(0x4E)                          # dec esi               ; advance one hex
a.j8(0xEB, 'uw_walk')               # jmp walk
a.label('uw_done')
a.db(0x8B, 0xC6)                    # mov eax, esi
a.db(0x5F)                          # pop edi
a.db(0x5E)                          # pop esi
a.db(0xC3)                          # ret

a.resolve()
cave = bytes(a.buf)
print(f"Cave size: {len(cave)} (0x{len(cave):X}) bytes at 0x{CAVE_BASE:X}..0x{CAVE_BASE+len(cave):X}")
for name in ('cave_exec','cave_movearmy','cave_display','true_reach','unit_walk'):
    print(f"  {name:14s} @ 0x{a.labels[name]:08X}")

# ------------------------------------------------------------- site patches --
def rel32(src_call_va, dst_va):
    return (dst_va - (src_call_va + 5)).to_bytes(4, 'little', signed=True)

patches = [
    # (VA, expected original bytes, new bytes, description)
    (0x55747B01,
     bytes([0xE8]) + rel32(0x55747B01, 0x557638D8),
     bytes([0xE8]) + rel32(0x55747B01, a.labels['cave_exec']),
     "TMoveArmyTE.Setup: MovePointsToPos -> cave_exec"),
    (0x5574A36E,
     bytes([0xE8]) + rel32(0x5574A36E, 0x557638D8),
     bytes([0xE8]) + rel32(0x5574A36E, a.labels['cave_movearmy']),
     "MoveArmyEx: MovePointsToPos -> cave_movearmy"),
    (0x557936A3,
     bytes([0x8B,0xD6, 0x8B,0x43,0x08, 0xE8]) + rel32(0x557936A8, 0x557639DC) + bytes([0x89,0x68,0x14]),
     bytes([0xE8]) + rel32(0x557936A3, a.labels['cave_display']) + bytes([0x90]*8),
     "TSelectedArmy.Update: budget store -> cave_display"),
    (CAVE_BASE, bytes(len(cave)), cave, "code cave"),
]

with open(DPL, 'rb') as fh:
    data = bytearray(fh.read())

ok = True
already = False
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    cur = bytes(data[off:off+len(orig)])
    if cur == new:
        print(f"ALREADY PATCHED: {desc}")
        already = True
    elif cur != orig:
        print(f"MISMATCH at VA 0x{va:X} ({desc}):")
        print(f"  expected {orig.hex(' ')}")
        print(f"  found    {cur.hex(' ')}")
        ok = False

if not ok:
    print("Aborting - original bytes did not match."); sys.exit(1)

if '--apply' not in sys.argv:
    print("\nDry run OK. Re-run with --apply to write the patch."); sys.exit(0)

# ⚠ Only ever snapshot a file PROVED unpatched.  `already` means at least one site
# already carries our bytes, so the DPL on disk is this script's own previous output --
# snapshotting it would mint a `.pre-patch` full of patched bytes.
if already:
    print("Snapshot SKIPPED: a site is already patched, so AoWEPACK.dpl on disk is not\n"
          "  a clean pre-patch state.  Nothing written to backups/.")
elif os.path.isfile(BACKUP):
    print(f"Snapshot already exists, left alone: {BACKUP}")
else:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copyfile(DPL, BACKUP)
    print(f"Snapshot written: {BACKUP}")

for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc} @ VA 0x{va:X}")
with open(DPL, 'wb') as fh:
    fh.write(data)
print("AoWEPACK.dpl patched successfully.")
