# Unit-window party arrows — every entry path

**Status: 🔨 APPLIED, UNTESTED (2026-09-03)**
**Script:** `build_scripts/build_unitwin_party_arrows.py`
**Binaries:** `AoW.exe` + `AoWCompat.exe` (lockstep)
**Backups:** `AoW.exe.pre-unitwinpartyarrows`, `AoWCompat.exe.pre-unitwinpartyarrows`
**Revert:** `python build_scripts/build_unitwin_party_arrows.py --undo` — surgical, touches no backup.

Adopted from Inioch share6 (`memory/unitwindow-party-arrows.md`). Every address re-verified on our
`AoW.exe` and byte-identical to `Ziggurat upload/AoW.exe`; his cave VAs and his `.xbfs` section do
**not** exist here.

---

## The vanilla behaviour, and why the arrows vanish

`TUnitWindow`'s prev/next arrows cycle the displayed unit's stack. All 15 entry paths funnel through
`UpdateUnitWindow @0x00407DB8`, whose arrow decision at `0x00407E52..0x00407EAC` **hides** them if any
of:

1. `[[0x0045EBDC]]` (`AoWTC.AoWCombatMap`) ≠ nil — in tactical combat;
2. `[G+0xA4]` == nil — no army selected on the map;
3. `PartyIndexOfUnit(G, unit) < 0` — displayed unit is not in the selected army;
4. `[G+0x88]` (party slot 1) ≤ −1 — selected army has < 2 visible units.

`G = [[0x0045A420]]` = `0x0045B2C0`, the `TGeneral` data module. **`TMapEvents.TheMapArmySelected
@0x0044EC30` is the sole writer** of `[G+0x84..0xA0]` (8 slot indices, −1 = empty) and `[G+0xA4]`
(the `TUnitList` they index). Those fields therefore describe the army **selected on the map** — the
bottom control bar's contents — not the unit being displayed. Open the window from the events
portrait or the items-found dialog and tests 2–4 fail. Not a bug in those callers.

⚠ Never overwrite those slots to fake a party context: `TControlWin.Unit1FrameMouseDown` reads the
same array to map a bar frame to a unit, so writing them corrupts the bottom bar.

| symbol | VA / offset |
|---|---|
| `UpdateUnitWindow` | `0x00407DB8` |
| show path / hide block / hide tail | `0x00407E8D` / `0x00407EAD` / `0x00407EB5` |
| `PPrevClick` / `PNextClick` | `0x0040ABF0` / `0x0040AC9C` (vanilla resume `0x0040ABF4` / `0x0040ACA0`) |
| `TGeneral.PartyIndexOfUnit` | `0x00454100` (eax=G, edx=unit → eax) |
| `TUnitWindow` instance | `[0x0045A53C]` = `0x0045B070` |
| `TGeneral` | `[0x0045A420]` = `0x0045B2C0` |
| `PNext` / `PPrev` / `UnitMainPnl` | `[self+0x210]` / `[self+0x214]` / `[self+0x16C]` |
| local player id | `[[0x0045DF7C]]+0xA5` |

---

## The fix

Drive the arrows from the unit's **own** army — `army := [unit+4]` (`TEObject.Owner`) — guarded by a
Delphi-3 VMT-header class walk for `"TArmy"` (name at `[vmt-0x20]`, parent at `[vmt-0x18]`, self-ptr
at `[vmt-0x40]` as a validity guard). The exe does not import the `TArmy` classref, so the walk
replaces `IsClass` with no new import and stays rebase-proof.

Three hooks into a new appended section:

| site | bytes | → |
|---|---|---|
| `0x00407EAD` (hide block) | `E9 4E712200 90 90 90` | cave slot 0 |
| `0x0040ABF0` (`PPrevClick`) | `E9 10442200` | cave slot 1 |
| `0x0040AC9C` (`PNextClick`) | `E9 69432200` | cave slot 2 |

**Section `.pyar`** — VA `0x0062F000`, VirtualSize/RawSize `0x1000`, raw `0x00229200`, characteristics
`0x60000020` (CODE|EXEC|READ, **no WRITE** — the cave holds no mutable state). Sections 11 → 12,
SizeOfImage `0x22F000` → `0x230000`. Cave body 653 B: a 3-slot `jmp` table at `0x62F000/005/00A`,
then `_armyof`, `_viscount`, `_vis`, `_prev`, `_next`, `_stepwork`.

ASLR is off (`DllCharacteristics = 0x0000`, ImageBase `0x400000`), so absolutes in the cave are fine.

---

## Three deviations from Inioch's version

1. ⭐ **`[vmt-0x18]` needs a DOUBLE dereference.** Measured here: `[0x557130EC-0x18] = 0x55710E88`,
   and `[0x55710E88] = 0x55710EC8` = the `TUnitList` VMT. His single deref makes the ancestor walk
   dead code that matches only the exact class — so AoWEPACK's **three `TArmy` descendants**
   (`TArmyView` `0x55713210`, `TDefendersArmy` `0x557C12B4`, `TPrisonersArmy` `0x557C53F4`) would
   silently get no arrows. **Send this back to him.**
2. **Engine accessors, not raw fields.** Count via `TArmy` VMT `+0x54`, members via the exe's own
   bounds-checked thunk `0x004026C4`, concealment via VMT `+0xB8`. His `[army+8]` / `[[army+8]+4][i]`
   bypasses both.
3. **Vanilla-first control flow.** Each handler asks `PartyIndexOfUnit` first; if it passes, it
   replays the displaced prologue and jumps back into the **vanilla body**. The party-window path
   therefore runs unmodified code, which makes his v1 failure mode structurally impossible rather
   than merely avoided.

⚠⚠ **There is NO ownership gate, and there must not be one.** His v1 gated on
`[unit+0x24] == local player`, assuming vanilla only showed arrows for your own stacks. Wrong —
`TheMapArmySelected` has no ownership test, so clicking an **enemy or independent** stack fills the
slots and vanilla shows *working* arrows for it. Symptom of the gate: arrows visible, clicks dead.
No information leak from dropping it — the concealment filter still runs with the local player's id.

**General lesson:** when replacing a handler, the reachability of the code you replaced is a superset
of the cases your new gate imagines. Enumerate who populates the state a feature reads *before*
inventing a safety condition it never had.

---

## ⚠ Cross-feature coupling

`build_wheel_ext.py` identifies the arrow buttons by comparing a button's `OnClick` (`[btn+0x138]`)
against the **literal addresses** `0x0040ABF0` / `0x0040AC9C`. Each dword occurs exactly once in the
exe, in `TUnitWindow`'s published method table.

⇒ **Do not "improve" this by repointing the method table.** Patching the function bodies (what we do)
keeps the wheel preview working; repointing the table would break it silently. Its behaviour now
engages in more contexts, since the arrows appear in more contexts.

---

## Section-append rules this feature depends on

- **`SizeOfImage` is recomputed as `align_up(max(rva + max(vsize, rsize)))` over ALL sections**, never
  from our own. Proved necessary: with a dummy section appended after `.pyar`, a re-apply yields
  `0x231000`, where the naive computation gives `0x230000` and unmaps it.
- **Re-apply overwrites `.pyar` in place** when the body fits its raw slot. A re-apply that rebuilds
  as `d[:raw] + body` destroys every section appended later.
- **`--undo` leaves the `.pyar` header inert** rather than truncating — removing it would renumber
  sections, which is the operation that can unmap another feature's cave.
- ⚠ If another feature appends a section **before** this one is applied, `ensure_section` refuses with
  an actionable message: raise `SEC_RVA` to the new max end; the hooks derive from `CAVE_VA` and
  nothing else changes.

---

## Lockstep

`AoWCompat.exe` is `AoW.exe` with one byte changed at file `0x3BB7C` (`0x0F` → `0x05`). The script
patches both and asserts pre and post that they differ in exactly that byte. Verified after apply.

---

## Needs the user's in-game test

- Arrows appear **and cycle** from the **events-window portrait** and the **items-found pickup dialog**.
- The **party side window** behaves exactly as before (that path never reaches the cave).
- ⭐ Arrows **work** on an **enemy** and an **independent** stack clicked on the map — the v1 regression.
- **No** arrows during tactical combat.
- A stack with concealed units cycles only the visible ones; one visible unit ⇒ no arrows.
- Site defenders / prisoners (`TDefendersArmy` / `TPrisonersArmy`) if reachable — the descendant fix.
- Mouse-wheel unit preview over the arrows (`build_wheel_ext.py`) still works.
