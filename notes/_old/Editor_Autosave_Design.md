# Editor Timer-Autosave — Design

**Status: v1 APPLIED + LIVE-TESTED + REVERTED (2026-07-07). The cave is byte-perfect and does not
crash, but the HOOK POINT IS WRONG — it never fires — so the feature does not work. Reverted; needs
a redesign onto a verified-reliable hook (see "Live-test finding" below). NOT shipping.**
Build script: `build_editor_autosave.py`. Binaries: `AoWDevEd.exe`, `AoWEd.exe` (backups
`<exe>.pre-autosave` — ⚠ **deleted after the revert; no snapshot exists**, see Revert below).

## Live-test finding (2026-07-07) — WHY v1 FAILED, and the fix path
Applied to AoWDevEd.exe (short 120-frame test interval) and driven live. Runtime proof via
process-memory reads (module base 0x00400000, no ASLR):
- Hook installed perfectly: entry `E9 e3 72 0b 00 90` = `jmp 0x4E0000`; cave code + AnsiString
  literal (`FF FF FF FF 4C…`) all correct. Editor launches, reaches map, **does not crash** (so
  the JMP-hook + eax-preservation review fixes are validated).
- **BUT the cave frame counter `[0x4E0064]` stayed exactly 0** through: 4 s active, a placement
  click, 300 posted `WM_MOUSEMOVE`, AND 24 *real* cursor moves across hexes with the editor
  foreground. So `TMainForm.HSMEditUpdateFrame` @0x428D18 is **never called** in these scenarios.
- Root cause: `THSMEdit.UpdateFrame` @0x55614904 (HSEPack, the per-frame method) **early-exits
  when the global `HSEdData.UpdateMap`==0** (0x5561491F) and only fires the `OnUpdateFrame` event
  when app-active (`[Application+0x7d]`) AND the real mouse is over a valid hex. `OnUpdateFrame`
  is thus scene-activity-gated, NOT a per-frame tick. The live status-bar hex coords are updated
  via `OnMouseMove` (`HSMEditMouseMove`), not this handler — so `OnUpdateFrame` genuinely idles.
- **Fix path (redesign v2):** hook a point that provably runs during editing, and verify it with
  the same ctr-read method BEFORE building the full cave. Best candidates:
  1. **`TMainForm.HSMEditMouseMove` @0x42AADC (EXE, no rebasing)** — fires on every real mouse move
     over the map (that's how live coords update). Reliable during active editing; exe-local so
     the existing absolute-address cave design mostly carries over. **Preferred.**
  2. `THSMEdit.UpdateFrame` ENTRY @0x55614904 (HSEPack) — runs every frame the display loop calls
     it, *before* the UpdateMap gate; but HSEPack REBASES → needs a position-independent cave
     (call/pop delta for ctr+string), and it's shared with the game (dead-but-harmless there).
  3. Hook the placement/edit path → "save every N edits" (exe-local, verifiable, but not time-based).
- **Time source** is still open (no GetTickCount/GetElapsedMilliSeconds import): prefer runtime
  `GetProcAddress(GetModuleHandle("kernel32"),"GetTickCount")` from the cave IF the exe imports
  GetProcAddress+GetModuleHandle (check first); else frame/edit counting on the chosen hook, or
  IAT surgery. A real ms clock + a reliable hook = a proper wall-clock timer.
- **Lesson:** the diagnosis tooling (ctr read at the cave's fixed VA, module-base read) now lets
  us EMPIRICALLY verify any candidate hook fires before investing in the full cave. Do that first.

## (v1 detail below — cave mechanics still valid, only the hook target was wrong)
Date: 2026-07-07. Built by an Opus subagent; **reviewed by main, which found + fixed two
showstopper cave bugs** (see "Review corrections" below) before any apply. This doc reflects the
corrected code.

## Review corrections (2026-07-07)
1. **Hook was `CALL` (E8) → changed to `JMP` (E9).** With a call, the pushed return address sits
   under the re-run prologue's frame, so the handler's own `ret` would return into its own body
   (0x428D1E) → crash on the first frame. A jmp pushes nothing; the re-run prologue then builds a
   correct frame whose `[ebp+4]` is the real caller return address.
2. **`eax` (Self) was clobbered on the save path.** The resumed body does `mov ebx,eax` at
   0x428D2F using `eax` as `Self` *before* reloading it, but the save branch overwrote `eax`
   (HSSet / SaveHSM return). Added `push eax` / `pop eax` around the SaveHSM call. (`ecx/edx` are
   genuinely dead there — the body reloads them — so they may be clobbered.)

## Goal
While the map editor is open, write the current map to a **backup file** every *N* minutes
(default 5) **without** touching the user's real filename or the modified/dirty flag. A
crash/hang costs at most *N* minutes. Conservative over clever: a broken autosave that
corrupts a map is worse than none.

---

## Hook point (per exe — verified independently)

`TMainForm.HSMEditUpdateFrame` — the editor's per-rendered-frame handler (the render loop;
runs continuously, `Sleep(1)` at top; ~60/s after `build_editor_framerate.py`). It is wired
as a published VMT method (`VMT_TMainForm+0x18cd` holds its address; invoked as the app idle /
frame callback).

At entry `eax = TMainForm` (Delphi `Self`); it is not clobbered until `mov ebx,eax` several
instructions in — so the hook at the absolute entry sees a clean `Self` in `eax`.

| exe            | entry VA     | resume VA (entry+6) | entry bytes (identical)      |
|----------------|--------------|---------------------|------------------------------|
| AoWDevEd.exe   | `0x00428D18` | `0x00428D1E`        | `55 8B EC 83 C4 9C`          |
| AoWEd.exe      | `0x00428CA0` | `0x00428CA6`        | `55 8B EC 83 C4 9C`          |

Those 6 bytes = `push ebp; mov ebp,esp; add esp,-0x64`. **The two exes are structurally
identical**; only the entry addresses (and the appended-section VAs) differ. The offsets used
below (`+0x22c`, `+0x1c0`, `+0x1bc`, `+0x3c`) were confirmed present in **both** handler
bodies.

### Displaced-bytes plan
Overwrite the 6 entry bytes with `E9 <rel32-to-cave> 90` (`jmp cave` + `nop`). **JMP, not CALL:**
nothing is pushed at cave entry, so after the cave re-executes the displaced prologue
(`push ebp; mov ebp,esp; add esp,-0x64`) the new frame's `[ebp+4]` is the genuine caller return
address and the handler's own `ret` is correct. (A CALL hook would leave the hook return address
under the frame and the epilogue would `ret` into the body → crash.) The cave preserves `eax`
(Self) across the save; all timer/guard-fail paths leave `eax` untouched.

Verify-before-write asserts the 6 entry bytes equal `55 8B EC 83 C4 9C` before patching; if not
(already hooked, or unexpected build) it aborts that exe.

---

## Cave logic (annotated; `eax = TMainForm` at entry)

```
; --- frame timer (self-contained, no imports) ---
inc  dword [ctr]                 ; ctr in cave data, init 0
cmp  dword [ctr], AUTOSAVE_FRAMES ; = minutes*60*fps (default 5*60*60 = 18000)
jb   _done
mov  dword [ctr], 0              ; reset and fire

; --- guards ---
mov  ecx, [eax+0x22c]            ; HSMEdit
test ecx,ecx / jz _done
cmp  byte [ecx+0x1bc], 0         ; "map loaded" flag (Save early-outs on 0)
jz   _done
mov  edx, [ecx+0x1c0]            ; HSSet (THSEngine container)
test edx,edx / jz _done
mov  ecx, [edx+0x3c]             ; THSMap
test ecx,ecx / jz _done
test byte [ecx+0x3c], 1          ; modified/dirty bit
jz   _done                       ; nothing changed -> skip

; --- do the save (edx = HSSet); preserve eax=Self across the call ---
push eax                         ; SAVE Self (TMainForm) — body needs it at 0x428D2F
push 0                           ; callback DATA
push 0                           ; callback CODE  (NIL -> progress skipped)
mov  eax, edx                    ; eax = HSSet
mov  edx, <lit+8>                ; filename AnsiString ptr (our const, NOT +0x1e4)
mov  ecx, [eax]                  ; HSSet vmt
call [ecx+0xAC]                  ; THSEngine.SaveHSM  (ret 8 -> cleans our 2 pushes)
pop  eax                         ; RESTORE Self

_done:
push ebp                         ; re-run displaced prologue
mov  ebp, esp
add  esp, -0x64
jmp  <resume>                    ; JMP hook -> stack is clean here, ret stays correct
```

We **never** call `THSMap.ResetModified` (@`0x5560C3D4`), so the user's dirty flag persists and
they still see unsaved changes. Register discipline: `eax` (Self) is preserved via push/pop
around the save (the body consumes it before reloading); `ecx/edx` are dead across resume (the
body reloads them). Stack balance on the save path: `push eax` + SaveHSM `ret 8` (cleans the two
callback dwords) + `pop eax` = net zero; SaveHSM (Delphi ABI) preserves `ebx/esi/edi`.

---

## Object-layout facts (verified from HSEPack.dpl `THSMEdit.Save` @0x55614ED0 and friends)

| datum                | address / offset                       | how confirmed |
|----------------------|----------------------------------------|---------------|
| HSMEdit ptr          | `[TMainForm+0x22c]`                    | frame handler `mov esi,[ebx+0x22c]` |
| "map loaded" flag    | `byte [THSMEdit+0x1bc]`                | `Save`: `cmp [ebx+0x1bc],0 / je exit0` |
| HSSet (THSEngine)    | `[THSMEdit+0x1c0]`                     | `Save`: `mov esi,[ebx+0x1c0]` |
| THSMap               | `[HSSet+0x3c]`                         | `Save`: `mov eax,[esi+0x3c]` before ResetModified |
| modified bit         | `byte [THSMap+0x3c] & 0x01`           | `Set/ResetModified` @0x5560C3C0/0x5560C3D4 OR/AND-NOT a const byte = **0x01** (read from 0x5560C3D0/0x5560C3E8) |
| real filename        | `AnsiString [THSMEdit+0x1e4]`         | `Save`: `mov edx,[ebx+0x1e4]` (we do NOT use this) |
| save virtual         | `[ [HSSet]+0xAC ]` = `THSEngine.SaveHSM` @0x5561043C | `Save`: `mov ecx,[eax]; call [ecx+0xAC]`; THSEngine VMT base 0x556033F0, slot +0xAC = SaveHSM (verified) |

### Save-virtual call convention (`THSEngine.SaveHSM`)
`eax = Self(HSSet)`, `edx = filename AnsiString`, plus **two stack dwords**:
`[ebp+0x8] = callback CODE`, `[ebp+0xc] = callback DATA`. Pushed by the caller in the order
`push DATA; push CODE` (matches `THSMEdit.Save`: `push ebx(THSMEdit); push ProgressEvent`).
SaveHSM forwards both to `TEngine.WriteEObject`, storing them at `stream+0x1c` (code) /
`stream+0x20` (data). **Epilogue `ret 8`** (@0x5561051D) cleans the two dwords → caller stack
balanced.

### Why NIL callback is safe (verified — key finding)
`Engine.TEStorageStream.ShowProgress` @`0x5550FF58`:
```
cmp word ptr [stream+0x1e], 0    ; = HIGH WORD of the code pointer at +0x1c
je  skip
...call [stream+0x1c]
```
The "Assigned" guard tests the **upper 16 bits of the code pointer**. A NIL (0) code pointer →
guard is 0 → the callback is skipped entirely. So pushing `0,0` for the callback is provably
safe; no rebasing DLL address (like the game's `ProgressEvent` @0x5561509C) is needed inside the
exe cave.

---

## The AnsiString literal (Delphi 3 const layout — verified)

Embedded in the cave's data section (fixed exe base 0x400000, so an absolute pointer is fine):

```
[lit+0] = FF FF FF FF        ; refcount = -1  (immutable const; never freed/realloc'd)
[lit+4] = <length : dword>   ; strlen of the path
[lit+8] = <path chars...> 00 ; NUL-terminated
```
`edx = lit+8` (pointer to first char). Layout confirmed against real exe literals, e.g.
`0x404EE4 'Index'`, `0x407B84 'Change Terrain'` — all `FF FF FF FF | len | chars | 00`.

**Backup filename (v1, fixed absolute):**
`<game dir>\Save\editor_autosave.hsm` — baked into the patch as an absolute literal at build time;
`build_editor_autosave.py` derives it from the resolved game directory.
(`Save\` exists in the game dir). Appending `.autosave.hsm` to the *live* filename is a
nice-to-have deferred to v2 — it needs a runtime AnsiString concat (VCL `@LStrCat*`) and a
temp string slot; the fixed const is the conservative choice and avoids all string-lifetime
risk.

---

## Timer: frame-count, not wall-clock (rationale)

The spec suggested `GFXEPACK.GetElapsedMilliSeconds`, "already imported by the exe." **It is
not**: the IAT of both exes imports GFXEPACK only for unit-init symbols
(`GFXE.GFXE`, `..TDrawPanel`), **not** `GetElapsedMilliSeconds` (which GFXEPACK *does* export
@0x5500D790). Neither `GetTickCount` nor `timeGetTime` is imported either. Options weighed:

- Hardcode a cross-DLL absolute call → **rejected**: the DPLs rebase at runtime (see
  `aow1-dpl-rebasing`), so a DLL VA is not fixed.
- Import-table surgery to add `GetTickCount` → **rejected as too invasive/risky** for a
  static-only deliverable (bound-import descriptors, OFT=0, in-place IAT patched by the loader).
- **Frame counting → chosen.** The hook *is* the render loop, so a per-frame counter is a
  robust clock: no rollover concern (a dword counter reset each interval), no first-call/first-
  tick edge case, zero imports. `AUTOSAVE_FRAMES = minutes*60*fps`.

**SPECULATIVE / caveat:** wall-clock accuracy tracks the *actual* frame rate. Default assumes
FrameRate=60 (after `build_editor_framerate.py`). If the user runs a different FrameRate, pass
`--fps` to match, else the real interval scales by `60/actual_fps`. If the render loop stalls
(e.g. modal dialog open, minimized), frames stop accumulating and the timer pauses — which is
acceptable (no save while the editor is blocked) but means the interval is "N minutes of active
editing," not strict wall-clock.

---

## Exact byte patches (per exe)

Both exes, at their entry VA, overwrite 6 bytes:
```
orig:  55 8B EC 83 C4 9C                       ; push ebp; mov ebp,esp; add esp,-0x64
new:   E9 <rel32 = cave - (entry+5)> 90        ; jmp cave ; nop   (JMP, not CALL)
```
Plus one appended PE section `.asv` (characteristics `0x60000020` = code|exec|read) containing
`[cave code ~100 B][dword frame counter = 0][AnsiString literal]`.

Dry-run cave VAs (independent per exe layout; code is 0x66 B after the eax-preservation fix):
- AoWDevEd.exe: cave `0x004E0000`, ctr `0x004E0068`, str `0x004E0074`.
- AoWEd.exe:    cave `0x004DF000`, ctr `0x004DF068`, str `0x004DF074`.

Section header room and pristine-entry-bytes are both asserted before writing.

---

## Verifications needed AT LIVE-APPLY TIME (checklist)

1. **`[HSSet]+0xAC` runtime class.** `[THSMEdit+0x1c0]` is a `THSEngine` *or a subclass*. We
   verified the base-class VMT slot +0xAC = `SaveHSM` with `ret 8`. If the live object is a
   subclass that **overrides** +0xAC, confirm the override keeps the same signature
   `(eax=Self, edx=filename, 2 stack dwords, ret 8)`. (Almost certain — the game's own
   `THSMEdit.Save` calls this exact slot the same way — but confirm the actual runtime `[[HSSet]]`
   vtable points at 0x5561043C, e.g. with a one-shot breakpoint / logging when first firing.)
2. **First real save writes a loadable .hsm.** After the first autosave fires, load
   `Save\editor_autosave.hsm` in the editor and confirm it opens intact and matches the map.
3. **Dirty flag persists.** After an autosave fires, the editor must still show unsaved changes
   (title `*` / prompt on close). Confirms we did not hit ResetModified.
4. **Real filename untouched.** After autosave, `File > Save` must still target the user's own
   file, not `editor_autosave.hsm`. (`[THSMEdit+0x1e4]` unchanged — we never write it.)
5. **NIL-callback path.** Confirm no crash/hang during the save with the 0,0 callback (the
   ShowProgress guard analysis says it's skipped; verify empirically once).
6. **Timer cadence.** With FrameRate=60, first autosave ~5 min after edits begin; subsequent
   every ~5 min. Sanity-check the interval and adjust `--minutes`/`--fps` if the loop rate
   differs from assumption.
7. **Both exes.** Test whichever exe the user actually runs; the other is patched identically
   but is a distinct build — validate independently if both are used.
8. **Save-failure safety (IMPORTANT — new risk, main-review).** The cave calls SaveHSM from the
   render loop *outside* any try/except (vanilla `Save` is called from a button handler that HAS
   surrounding SEH; our frame-loop hook does not). If SaveHSM raises (target dir missing, file
   read-only/locked, disk full), the exception propagates unguarded → possible editor crash mid-
   session — which is worse than no autosave. `Save\` exists so the happy path is fine, but at
   apply time **test a failure case**: make `Save\editor_autosave.hsm` read-only, edit, wait for a
   fire, and confirm the editor does not crash. If it does, v1.1 must wrap the save in a minimal
   SEH frame (set up `fs:[0]` handler chain in the cave) or pre-check the path is writable.
9. **First frame after apply doesn't crash.** Because the hook is the per-frame handler, any
   cave/stack error manifests instantly on launch — so "editor launches and reaches the map at
   all" already validates the JMP-hook + eax-preservation fixes. Watch the very first launch.

## Revert
**Nothing to revert — the feature is already off, and the backups are gone.** Verified 2026-07-30:
`AoWDevEd.exe` contains no `.asv` section (while `.tres`, `.vgo` and `.mtb` from other features are all
present), confirming the 2026-07-07 revert stuck. `<exe>.pre-autosave` exists in neither the game root nor
`Modding Resources/backups/` — it was deleted after the revert, like other redundant post-confirmation
backups.

If v1 is ever re-applied and then needs removing: it has no shared code cave with other features (its own
`.asv` section + a 6-byte entry patch), so a surgical undo is independent of every other layer — restore
the 6 entry bytes and drop the section. Do not expect a snapshot to exist.
