#!/usr/bin/env python3
r"""
AoW1 mod -- COMBAT LOG: report the RESISTANCE ROLL that decides whether a damage EFFECT lands.

PROBLEM. The log says *whether* an effect landed (the `+vertigo` suffix, from word[CA+0x13]) but never
what odds it had, and a RESISTED effect is completely invisible -- no roll, no odds, nothing. Worse, a
repeat hit on an already-afflicted target prints no suffix either (the engine short-circuits before
rolling), so "no +vertigo" is ambiguous between "resisted" and "already vertigo'd".

THE MECHANIC (decoded; design doc Combat_Log_Implementation_Design.md §11).
TAbstractUnit.ExecuteDamageEffectsRole @0x55781BA4 -- reached as combat vmt+0x118 via
TCombatUnit.ExecuteDamageEffectsRole @0x55724C3C, a one-line forwarder to the strategic unit:

    types &= ~self.vmt[0xEC]()                  ; drop fully-immune types
    baseRes = self.vmt[0xCC]()                  ; GetResistance
    partial = self.vmt[0xF0]()                  ; PARTIAL protection mask
    for (bit, statusId) in the fixed order below:
        if types & bit:
            if self.vmt[0x148](statusId): continue        ; ALREADY afflicted -> no roll at all
            res = (partial & bit) ? baseRes + 2 : baseRes
            if HitRole(5 - res): result |= bit            ; <-- THE ROLL

=> effect chance = clamp(50 + 10*(5-res), 10, 90) = clamp(100 - 10*res, 10, 90) %, the same HitRole
   @0x55725D98 curve as to-hit. RES 5 -> 50%, RES 7 -> 30%, RES 9 -> 10% floor, RES <= 4 -> capped 90%.
   Partial protection is a flat +2 RES against that one type.

FIX. Each of the six roll sites is a standalone 5-byte `call HitRole` with **EAX = 5-res on entry** and
**AL = landed on return** -- so a per-effect stub gets the exact odds AND the exact outcome, including
rolls that FAIL. Repoint all six to stubs that call HitRole and then emit their own log line:

    vertigo 30% vs res 7 - landed
    poisoned 50% vs res 5 - resisted

Because each stub emits immediately, no BSS table and no clear-hook are needed (§11's original plan
assumed appending to the damage line, which would have required patching the log worker and therefore a
rewrite of the combat-log image -- see that doc's corrected staging rule).

ORDERING NOTE. The effect roll happens INSIDE Generate, before the log worker's tail hook at the Generate
epilogue -- so an effect line appears just ABOVE the damage line it belongs to. Each line names its own
effect, so it reads fine either way.

ADDITIVE: new cave at 0x5580F600 (free region, above build_replaylog.py's cave which ends ~0x5580F4A3);
touches only the six call sites. PIC (call/pop anchor, all literals anchor-relative). Idempotent,
verify-before-write, dry-run / --apply. Snapshot goes to `<game dir>\backups\AoWEPACK.dpl.pre-effectroll`.

Revert = `--revert` (surgical: the six roll sites go back to HitRole, the cave is zeroed). A `.pre-*`
restore is NOT a revert path -- it is a whole-file copy that drops every feature applied since, and
there is no snapshot layer left at all (both stacks were purged, 2026-08-08 / 2026-09-09).
"""
import os, sys, shutil, struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_DIR = os.path.join(GAME, "backups")   # snapshots live here, never the game root (rule 2026-09-03)
ks = Ks(KS_ARCH_X86, KS_MODE_32); cs = Cs(CS_ARCH_X86, CS_MODE_32)

def load_sections(data):
    e=struct.unpack_from("<I",data,0x3C)[0]; n=struct.unpack_from("<H",data,e+6)[0]
    op=struct.unpack_from("<H",data,e+20)[0]; s=e+24+op; secs=[]
    for i in range(n):
        vs,va,rs,raw=struct.unpack_from("<IIII",data,s+8); secs.append((va,vs,raw,rs)); s+=40
    return secs
def mkva2off(base):
    def f(secs,va):
        rva=va-base
        for va0,vs,raw,rs in secs:
            if va0<=rva<va0+max(vs,rs): return raw+(rva-va0)
        raise ValueError(hex(va))
    return f
def rel32(src,dst): return struct.pack("<i",dst-(src+5))

DLL_BASE = 0x55700000
CAVE     = 0x5580F600
CAVE_LIMIT = 0x5580FA00
HITROLE  = 0x55725D98          # eax = attack-defence margin -> AL bool

# the six roll sites, in the order ExecuteDamageEffectsRole tests them
SITES=[(0x55781C37,"burning"), (0x55781C97,"stunned"), (0x55781CE9,"poisoned"),
       (0x55781D3B,"cursed"),  (0x55781D8D,"vertigo"), (0x55781DED,"frozen")]

INTTOSTR = 0x5570158C          # eax=int, edx=@out LStr
LSTRLASG = 0x55701158          # eax=@dest, edx=src value
LSTRCAT  = 0x55701188          # eax=@dest, edx=src value -> dest := dest+src
LSTRARRCLR=0x55701148          # eax=@first, edx=count

RING=0x60D000; WR=RING+4; RD=RING+8; SLOTS=RING+0x20
MAGIC=0x31474C43
SLOT_SZ=128; SLOTS_N=64
def _check_wire():
    import re
    here=os.path.dirname(os.path.abspath(__file__))
    for fn,pat,exp in (("build_combatlog_exe.py", r"RING_SLOTS\s*=\s*(\d+);\s*SLOT_SZ\s*=\s*(\d+)", (SLOTS_N,SLOT_SZ)),
                       ("build_combatlog_dll.py", r"SLOT_SZ\s*=\s*(\d+);\s*SLOTS_N\s*=\s*(\d+)",   (SLOT_SZ,SLOTS_N))):
        try: t=open(os.path.join(here,fn)).read()
        except OSError: continue
        m=re.search(pat,t); assert m, f"cannot find the ring constants in {fn}"
        got=(int(m.group(1)),int(m.group(2)))
        assert got==exp, f"WIRE-FORMAT MISMATCH vs {fn}: {got} != {exp}. All scripts must agree."
_check_wire()

def lstr_const(s):
    b=s.encode("latin1"); return struct.pack("<ii",-1,len(b))+b+b"\x00"

LITS={"PCT":"% vs res ", "LAND":" - landed", "RES":" - resisted", "SP":" "}
for _va,_nm in SITES: LITS["N"+_nm]=_nm
lit_off={}; pool=b""
for _n,_s in LITS.items():
    lit_off[_n]=len(pool); pool+=lstr_const(_s)

def emit(lit_va):
    def body(anchor):
        def d(n):
            v=lit_va+lit_off[n]+8-anchor
            return f"+ 0x{v:X}" if v>=0 else f"- 0x{-v:X}"
        # one stub per site: preserve the diff, run the real roll, log, return AL to the caller
        stubs=""
        for i,(_va,nm) in enumerate(SITES):
            stubs+=f"""
        _s{i}:
            push ebx
            mov  ebx, eax
            call 0x{HITROLE:X}
            push eax
            mov  edx, ebx
            mov  ecx, {i}
            call _emit
            pop  eax
            pop  ebx
            ret
        """
        # _emit(edx = diff (5-res), ecx = effect index) -- clobbers nothing the stub still needs
        names="".join(f"""
            cmp  ecx, {i}
            jne  _k{i}
            lea  edx, [edi {d('N'+nm)}]
            jmp  _got
        _k{i}:
        """ for i,(_va,nm) in enumerate(SITES))
        return f"""
            jmp _stubs
        _emit:
            pushad
            push ebp
            mov  ebp, esp
            sub  esp, 0x20
            xor  eax, eax
            mov  [ebp-0x04], eax
            mov  [ebp-0x08], eax
            mov  [ebp-0x0C], edx
            call _anch
        _anch:
            pop  edi
            mov  eax, [0x40003C]
            cmp  dword ptr [eax+0x400050], 0x20E000
            jb   _done
            cmp  dword ptr [0x{RING:X}], 0x{MAGIC:X}
            jne  _done
            mov  eax, [0x{WR:X}]
            sub  eax, [0x{RD:X}]
            cmp  eax, {SLOTS_N-1}
            jae  _done
            {names}
            lea  edx, [edi {d('Nvertigo')}]
        _got:
            lea  eax, [ebp-0x04]
            call 0x{LSTRLASG:X}
            lea  eax, [ebp-0x04]
            lea  edx, [edi {d('SP')}]
            call 0x{LSTRCAT:X}
            mov  eax, [ebp-0x0C]
            add  eax, eax
            imul eax, eax, 5
            add  eax, 0x32
            cmp  eax, 0xA
            jge  _c1
            mov  eax, 0xA
        _c1:
            cmp  eax, 0x5A
            jle  _c2
            mov  eax, 0x5A
        _c2:
            lea  edx, [ebp-0x08]
            call 0x{INTTOSTR:X}
            lea  eax, [ebp-0x04]
            mov  edx, [ebp-0x08]
            call 0x{LSTRCAT:X}
            lea  eax, [ebp-0x04]
            lea  edx, [edi {d('PCT')}]
            call 0x{LSTRCAT:X}
            mov  eax, 5
            sub  eax, [ebp-0x0C]
            lea  edx, [ebp-0x08]
            call 0x{INTTOSTR:X}
            lea  eax, [ebp-0x04]
            mov  edx, [ebp-0x08]
            call 0x{LSTRCAT:X}


            mov  eax, [ebp+0x28]
            test al, al
            jz   _no
            lea  edx, [edi {d('LAND')}]
            jmp  _o
        _no:
            lea  edx, [edi {d('RES')}]
        _o:
            lea  eax, [ebp-0x04]
            call 0x{LSTRCAT:X}
            mov  eax, [ebp-0x04]
            test eax, eax
            jz   _clean
            mov  ecx, [eax-4]
            cmp  ecx, {SLOT_SZ-1}
            jbe  _len
            mov  ecx, {SLOT_SZ-1}
        _len:
            mov  edx, [0x{WR:X}]
            and  edx, {SLOTS_N-1}
            shl  edx, {SLOT_SZ.bit_length()-1}
            add  edx, 0x{SLOTS:X}
            mov  [edx], cl
            mov  esi, eax
            lea  edi, [edx+1]
            cld
            rep  movsb
            mov  eax, [0x{WR:X}]
            inc  eax
            mov  [0x{WR:X}], eax
        _clean:
            lea  eax, [ebp-0x08]
            mov  edx, 2
            call 0x{LSTRARRCLR:X}
        _done:
            mov  esp, ebp
            pop  ebp
            popad
            ret
        _stubs:
            {stubs}
        """
    a0=CAVE+16
    b0=bytes(ks.asm(body(a0),CAVE)[0])
    off=b0.find(b"\x5f", 8)                     # `pop edi` after `call _anch`
    anchor=CAVE+off
    out=bytes(ks.asm(body(anchor),CAVE)[0])
    assert len(out)==len(b0), ("cave size unstable",len(b0),len(out))
    # stub entry points: each begins `push ebx; mov ebx,eax` (53 89 c3) after the `_stubs` label
    ents=[]; i=-1
    while True:
        i=out.find(b"\x53\x89\xc3", i+1)
        if i<0: break
        ents.append(CAVE+i)
    assert len(ents)==len(SITES), ("stub scan failed", [hex(x) for x in ents])
    return out, anchor, ents

APPLY="--apply" in sys.argv
REVERT="--revert" in sys.argv
def build(path, suffix=".pre-effectroll"):
    data=bytearray(open(path,"rb").read()); secs=load_sections(data); va2off=mkva2off(DLL_BASE)
    def rd(va,n): o=va2off(secs,va); return bytes(data[o:o+n])

    code,anchor,ents=emit(CAVE+0x400)
    lit_va=(CAVE+len(code)+15)&~15
    code,anchor,ents=emit(lit_va)
    assert (CAVE+len(code)+15)&~15==lit_va, "literal pool moved between passes"
    img=code+b"\x00"*(lit_va-CAVE-len(code))+pool

    print(f"\n[cave_effectroll] @{CAVE:08X}  code {len(code)} B  literals @{lit_va:08X} ({len(pool)} B)"
          f"  total {len(img)} B  (room {CAVE_LIMIT-CAVE} B)  anchor={anchor:08X}")
    for (va,nm),e in zip(SITES,ents):
        print(f"   {nm:<9} roll @{va:08X}  ->  stub @{e:08X}")
    if CAVE+len(img)>CAVE_LIMIT:
        print(f"[x] cave overflows its zone"); return False

    patches=[(CAVE, bytes(len(img)), img, "cave_effectroll")]
    for (va,nm),e in zip(SITES,ents):
        orig=b"\xE8"+rel32(va,HITROLE)          # computed constant, never read from the live file
        patches.append((va, orig, b"\xE8"+rel32(va,e), f"{nm} roll -> stub"))

    # --revert: point the six roll sites back at HitRole and zero the cave, i.e. stock behaviour.
    # Added 2026-07-22 to A/B this feature against a freeze localised (via build_combatdiag.py) to
    # INSIDE a single TFastCombatUnit.fcExecute call in round 2 of an auto-resolved battle. This
    # patch fires on every damage event, was applied untested on 2026-07-21, and is therefore the
    # cheapest single variable to eliminate. Re-apply by running this script again with --apply.
    if REVERT:
        patches=[(CAVE, img, bytes(len(img)), "cave_effectroll -> zeroed")] + [
            (va, b"\xE8"+rel32(va,e), b"\xE8"+rel32(va,HITROLE), f"{nm} roll -> HitRole (stock)")
            for (va,nm),e in zip(SITES,ents)]

    live=rd(CAVE,len(img))
    if live!=img and any(b!=0 for b in live):
        print(f"[x] cave zone {CAVE:08X} not free:\n     {live[:32].hex(' ')}"); return False
    for va,orig,new,desc in patches[1:]:
        cur=rd(va,5)
        if cur!=orig and cur!=new:
            print(f"[x] roll site {va:08X} unexpected ({desc})"
                  f"\n     exp {orig.hex(' ')}\n     got {cur.hex(' ')}"); return False
    if all(rd(va,len(new))==new for va,_o,new,_d in patches):
        print("[= ] already applied"); return True
    if not APPLY:
        print("[dry] cave assembles and fits, zone free, all six roll sites verified"); return True
    # ⚠ Snapshot on --apply ONLY. --revert runs through this same write path, so without the
    # REVERT guard a revert would copy the PATCHED DLL to a name that reads as pre-patch. That
    # was masked until 2026-09-10 by a stale snapshot already sitting at the old path; once
    # snapshots moved to backups\ and the loose ones were pruned, the guard became load-bearing.
    if not REVERT:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        bp=os.path.join(BACKUP_DIR, os.path.basename(path)+suffix)
        if not os.path.exists(bp): shutil.copy2(path,bp); print(f"[bak] {bp}")
    for va,_o,new,desc in patches:
        o=va2off(secs,va); data[o:o+len(new)]=new; print(f"[w ] {va:08X} {desc}")
    try: open(path,"wb").write(data)
    except PermissionError: print("[x] LOCKED -- close AoW binaries"); return False
    return True

ok=build(os.path.join(GAME,"AoWEPACK.dpl"))
print("\n[dry-run] Re-run with --apply to write. Close all AoW binaries first." if not APPLY
      else ("\n[done] Applied. Revert = --revert (surgical). NOT a .pre-* restore: a whole-file copy drops"
            "\n       every feature applied since, and there is no snapshot layer left."
            if ok else "\n[!] not applied"))
