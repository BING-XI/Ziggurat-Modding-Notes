# AoW1 — Engine mechanics behind AI ground-item pickup

**Status: ANALYSIS ONLY (2026-07-21). NOTHING APPLIED. NOTHING TESTED IN-GAME.**
Every statement below is static analysis (Ghidra decompilation + capstone disassembly of the shipped
binaries). Byte-level claims were re-read straight out of the files while writing this doc, so the
*bytes* are certain; the *behavioural* conclusions drawn from them are not confirmed until someone
runs the game.

Companion docs:
- **`AI_Sites_And_Loot.md`** — ⭐ **what was actually built and applied** (`build_ai_itemloot.py` +
  `build_ai_sitesearch.py`, 🔨 APPLIED, UNTESTED 2026-09-03). The §2-§4 and §6-§7 substrate below is
  what those caves rest on; go there for cave VAs, the value metric, the revert commands and the
  traps.
- `Investigation_AI_Item_Pickup.md` — the feature investigation proper (the two doors that block AI
  item acquisition, the UI-only paths, the `build_ai_itempickup.py` design). **Read that first.**
- `Investigation_Items.md` — item struct/field map.

This doc holds the **low-level engine substrate** discovered while designing that patch: how engine
collections are laid out, how list removal actually behaves, how the token pipeline dispatches, and
what owns/frees the ground-item list. §2–§4 and §6–§7 are **reusable by any feature**, not just item
pickup — they are filed here only because this is where they were derived.

---

## 1. ⚠ Address notation — the preferred bases OVERLAP

Three modules are cited here, and **two of them occupy the same numeric VA range**, so a bare address
is ambiguous. Every address in this doc is tagged with its module. Section headers give the default.

| Module | ImageBase | CODE section (preferred VA) |
|---|---|---|
| `Enginep.dpl` | `0x55500000` | `0x55501000` – `0x5552F044` |
| `AoWEPACK.dpl` | `0x55700000` | `0x55701000` – **`0x558E7918`** |
| `Network.dpl` | **`0x55800000`** | `0x55801000` – `0x55806210` |

**`Network.dpl`'s entire image sits inside `AoWEPACK.dpl`'s CODE range.** Consequences:

- `0x55803868` is `TTokenControl.AddEvent` **in Network.dpl** — and is *also* a perfectly valid
  AoWEPACK.dpl code address. The docs already contain AoWEPACK addresses in this range, e.g.
  `MapCtrl.TAoWMapControl.SelectHS@0x5580602f` and `cave_razemode@0x5580D100`.
- **Worst case, exact collision:** this project allocates AoWEPACK caves from **`0x55810000`**
  (`Investigation_AI_Item_Pickup.md` §6c), and Network.dpl's `.reloc` section starts at
  **`0x55810000`** — the same number, a different module.

`Enginep.dpl` (`0x555xxxxx`) does not overlap either, so Engine addresses are unambiguous.

None of this matters at runtime — the DPLs all rebase, which is exactly *why* the preferred bases
were allowed to collide. It matters only for reading and writing these notes. **Always write the
module name next to an address in the `0x558xxxxx` range.**

---

## 2. Engine collection layout — the count is NOT at `list+8` [Enginep.dpl]

`TItemList`, and every other `TEChangeNotifyNode` descendant, is **not** an array. `node+8` holds a
pointer to a plain VCL `TList`, and the payload lives one further indirection down:

```
node + 8                → TList*
[node + 8] + 4          → element array   (TList.FList — TItem** )
[node + 8] + 8          → element count   (TList.FCount)
```

`Engine.TEChangeNotifyNode.GetCount@0x5551A2F4` is literally that double dereference:

```
5551A2F4  8B 40 08     mov eax, [eax + 8]      ; -> the TList
5551A2F7  8B 40 08     mov eax, [eax + 8]      ; -> FCount
5551A2FA  C3           ret
```

**The trap:** `node+8` *looks* like a count field (it is a small integer-sized slot at the offset
where many Delphi containers keep one) and reads as a plausible pointer-or-count either way. Treating
it as the count yields a huge garbage value — a cave looping to it walks off the end of the heap.
`GetCount` is dispatched **virtually at `vmt+0x54`**, so the cheap correct move is to call the slot
rather than inline the two loads.

**Independent confirmation** — `TItemList.GetItem@0x55794A2C` **[AoWEPACK.dpl]** uses exactly this
layout, and is fully bounds-checked in both directions:

```
55794A32  test esi, esi
55794A34  jl   0x55794A4D          ; i < 0        -> return 0
55794A38  mov  edx, [eax]
55794A3A  call [edx + 0x54]        ; GetCount (virtual)
55794A3D  cmp  esi, eax
55794A3F  jge  0x55794A4D          ; i >= count   -> return 0
55794A41  mov  eax, [ebx + 8]      ; the TList
55794A44  mov  eax, [eax + 4]      ; FList (element array)
55794A47  mov  eax, [eax + esi*4]  ; element
55794A4A  ret
55794A4D  xor  eax, eax            ; out of range -> NIL
```

⇒ **The safe idiom for a cave is `for i = 0,1,2,… : GetItem(list, i)` until it returns 0.** No count
read, no layout assumption, and it is inherently robust to the list mutating under you. This is what
`build_ai_itempickup.py` does.

---

## 3. List removal has TWO modes, selected by `GetControlStyle() & 8` [Enginep.dpl]

`Engine.TEChangeNotifyNode.RemoveChild@0x5551A554`:

```
5551A55A  mov  eax, ebx
5551A55C  mov  edx, [eax]
5551A55E  call [edx + 4]           ; GetControlStyle (virtual, vmt+4)
5551A561  test al, 8
5551A563  jz   0x5551A583          ; bit CLEAR -> compacting TList.Remove
          ; ---- bit SET: nil the slot in place ----
5551A565  mov  eax, [ebx + 8]
5551A56A  call <TList.IndexOf>
5551A56F  mov  esi, eax
5551A571  cmp  esi, -1
5551A574  jz   ...
5551A576  mov  eax, [ebx + 8]
5551A579  mov  eax, [eax + 4]      ; element array
5551A57C  xor  edx, edx
5551A57E  mov  [eax + esi*4], edx  ; slot := NIL, COUNT UNCHANGED
```

| Style bit 8 | Behaviour | Effect on indices |
|---|---|---|
| **clear** | compacting `TList.Remove` | later elements shift down; count decreases |
| **set** | slot set to NIL in place | indices stable; count unchanged; **holes** |

**Who is which:**

| Collection | Style | Mode |
|---|---|---|
| Ground `TItemList` (a `TItemHS`'s list) | `0x01` | **compacting** |
| `THeroItems` (hero equip array) | `0x09` | **sparse** — fixed 6 entries, NIL holes |
| `THeroInventory` (backpack) | `0x09` | **sparse** |

Constants (all verified by reading the bytes):

- `Engine.TEObject.GetControlStyle` returns the byte at **`0x55519314` = `0x01`** [Enginep.dpl]
- `THeroItems.GetControlStyle` ORs in the byte at **`0x55786338` = `0x08`** [AoWEPACK.dpl] ⇒ `0x09`
- `THeroInventory.GetControlStyle` ORs in the byte at **`0x55786058` = `0x08`** [AoWEPACK.dpl] ⇒ `0x09`

**Why this matters for pickup:** the two collections behave *oppositely*, and a cave touching both
must not carry an assumption across.

- Iterating the **hero equip array** by index 0..5 is correct and holes are expected — never treat a
  NIL as end-of-list.
- Iterating the **ground list** while removing from it is the classic compaction bug: taking item *i*
  shifts everything after it down one, so a naive `i++` skips the next item. `build_ai_itempickup.py`
  dodges this by refetching the list and restarting the scan after every successful pickup.

---

## 4. Hero equip slot tables — asymmetric, and read without a bounds check [AoWEPACK.dpl]

Two lookup tables in DATA, adjacent, each followed by instruction padding (so they are **exactly** 6
and 7 bytes — do not read further):

```
0x558E8DB0  02 00 03 04 01 04 | 8B C0        position -> type   (6 entries, then `mov eax,eax` pad)
0x558E8DB8  01 04 00 02 03 0F 0F | 90        type -> position   (7 entries, then a 0x90 NOP pad)
0x558E8DC0  00 01 03 07 0F 1F 3F 7F          UNRELATED (a 2^n-1 bitmask table)
```

The 7th byte of the type→position table is **`0x0F` real data**; the `0x90` after it is x86 NOP
padding, **not** an eighth entry.

**The asymmetry:** position→type shows `04` at **both position 3 and position 5** — item type 4 owns
two slots (the two ring slots). But the forward table can only ever return one answer, and it returns
**3**. So **slot 5 is unreachable through `GetItemTypePosition`.**

`THeroItems.GetItemTypePosition@0x55786740` is four instructions with **no bounds check at all**:

```
55786740  33 C0                 xor eax, eax
55786742  8A C2                 mov al, dl                    ; type, 0..255, UNCHECKED
55786744  8A 80 B8 8D 8E 55     mov al, [eax + 0x558E8DB8]    ; absolute ref into a 7-byte table
5578674A  C3                    ret
```

Any type ≥ 7 reads out of bounds — up to 249 bytes past the table, straight into the bitmask table
above and whatever follows it. (Also note the **absolute** memory operand: this instruction cannot
simply be copied into a DPL cave, which must be position-independent.)

**Use `THeroItems.CanPlaceItem@0x5578674C` instead — it is the complete predicate:**

```
55786755  test edi, edi     ; item non-NIL
55786757  je   -> false
5578675B  mov  al, bl
5578675D  cmp  eax, 6
55786760  jge  -> false     ; position < 6          (the bounds check the other one lacks)
55786766  call 0x55786718   ; GetPositionItem — slot must be EMPTY
5578676D  jne  -> false
55786773  call 0x55786734   ; position -> type  (the 0x558E8DB0 table)
55786778  cmp  al, [edi + 0x34]   ; item+0x34 = item type
5578677B  je   -> true
```

Because it maps **position → type** and compares, rather than type → position, a scan of positions
0..5 through `CanPlaceItem` **does** reach slot 5. That is precisely why the pickup design scans slots
rather than looking the position up from the type.

---

## 5. Ground-item hot-spot lifetime — the list is live and self-freeing [AoWEPACK.dpl]

`THero.GetItemsOnGround@0x55788C7C` returns the **live** `TItemList` owned by the hex's `TItemHS`, or
**0** when the hex has no item hot-spot (i.e. almost every hex):

```
55788C7C  mov  edx, [0x558FA040]      ; the map singleton
55788C82  mov  edx, [edx + 0x11C]     ; the tactical-combat map, if any
55788C88  test edx, edx
55788C8A  je   0x55788C96             ; none -> use the strategic map
55788C8C  xchg edx, eax               ; EAX = combat map, EDX = hero
55788C8F  call [ecx + 0x10C]          ; map vmt+0x10C = GetHeroItemsOnGround
```

⇒ `map+0x11C` is the combat-map override, and map `vmt+0x10C` resolves to
`TAbstractAoWHSMap.GetHeroItemsOnGround@0x557737A8`. (The `map+0x11C == 0` "strategic only" gate in
`build_ai_itempickup.py` is therefore exactly the right gate.)

**Two rules follow, and violating either is a crash:**

1. **The caller must never free it.** It is the hot-spot's own list, not a copy.
2. **The pointer must not be held across a removal.** `TItemHS.ItemsChanged@0x55795D10` **destroys the
   hot-spot** — and `TItemHS.Destroy@0x55795CE0` frees the `TItemList` at `itemHS+0x0C` — as soon as
   the list empties:

```
55795D13  mov  eax, [ebx + 0x0C]     ; itemHS+0x0C = the TItemList
55795D16  mov  edx, [eax]
55795D18  call [edx + 0x54]          ; GetCount  (the virtual slot from §2)
55795D1B  test eax, eax
55795D1D  jne  0x55795D3E            ; still has items -> just Changed()
55795D1F  cmp  byte [ebx + 0x10], 0
55795D23  je   0x55795D33            ; -> DESTROY
55795D25  mov  eax, [0x558FA040]
55795D2A  cmp  dword [eax + 0x174], 0
55795D31  jle  0x55795D3E            ; map still initialising -> skip destroy
55795D33  mov  dl, 1
55795D37  mov  ecx, [eax]
55795D39  call [ecx - 4]             ; Destroy(true)  — SELF-DESTRUCT
```

Precisely: it self-destructs when `count == 0` **and** (`itemHS+0x10 == 0` **or** `map+0x174 > 0`).
A cave should treat "may free" as unconditional rather than lean on that guard.

⇒ **Taking the last item on a hex frees the list you are iterating.** Only item **IDs** (plain
integers) may cross a mutation boundary — never the list or item pointers. Hence refetch-per-slot and
break-on-success.

---

## 6. Token dispatch is ASYNCHRONOUS [Network.dpl]

`TTokenControl.AddEvent@0x55803868` does **not** execute anything. It validates, then enqueues via
`vmt+0`:

```
55803870  call 0x55803968       ; validity check
55803875  test al, al
55803877  je   0x5580388F       ; failed -> raise (0x55801564 / 0x55801080)
5580388F  mov  edx, esi
55803893  mov  ecx, [eax]
55803895  call [ecx]            ; vmt+0 -> append to tc.FEventList
```

Execution happens later, on the executer's own pass:

```
TTokenExecuter.Process@0x55803FD0  ──►  ExecuteTokenEvent@0x55803D24
```

`TTokenEvent.Create@0x558031D4` sets the token counter to **-1**, which makes tokens always take the
plain-append path — so there is no duplicate-counter exception to design around.

**Consequence for any mod:** minting a token is a *request*, not an action. Nothing has happened when
`AddEvent` returns, and the effect lands on a later pass — which is why the pickup patch calls
`THero.ExecutePlaceItem` directly instead (see `Investigation_AI_Item_Pickup.md` §6b for the MP-safety
argument that makes that legitimate at those two injection sites).

---

## 7. `GetBusy` — why a token-minting pickup would silently do nothing

`TPlayer.GetBusy@0x557516D0` **[AoWEPACK.dpl]** delegates to the token manager at `map+0x23C`:

```
557516D6  cmp  dword [esi + 0x48], 0    ; explicit busy lock
557516DA  jne  -> busy
557516DC  movsx edx, byte [esi + 0xA6]  ; player index
557516E3  mov  eax, [0x558FA040]
557516E8  mov  eax, [eax + 0x23C]       ; the TTokenManager
557516F0  call [ecx + 0x14]             ; vmt+0x14  ->  0x55804310  [Network.dpl]
557516F3  test al, al
557516F5  je   -> busy                  ; 0 from vmt+0x14 == BUSY
```

⚠ **Polarity:** the routine at `0x55804310` **[Network.dpl]** is a *ready* predicate — it returns
**1 = can accept a token**, **0 = cannot** — and `GetBusy` **negates** it. Do not copy it into a cave
as if it returned "busy".

It returns 0 (⇒ busy) in exactly two cases:

```
55804345  call 0x558038E0          ; Count(tc.FEventList)
5580434A  test eax, eax
5580434C  jne  -> 0                ; (a) ANY event already queued for this player
...
5580435B  cmp  eax, [edx + 8]      ; tc == executer.FActiveTC ?
5580435E  jne  -> 1
55804363  test byte [eax + 0x24], 2
55804367  je   -> 1
55804369  xor  eax, eax            ; (b) active TC and flag 2 set -> 0
```

(`0x558038E0` is `mov eax,[eax+4]; call <GetCount>` — the count of `tc+4`, the event list.)

**And flag 2 is held for the entire execute pass.** In `TTokenExecuter.Process@0x55803FD0`:

```
55804036  mov  al, [0x55804114]    ; = 2        <-- SET
5580403B  or   al, [esi + 0x24]
5580403E  mov  [esi + 0x24], al
55804041  mov  eax, [esi + 4]
55804044  mov  [esi + 8], eax      ; executer+8 = FActiveTC
   ... drain loop: repeatedly call vmt+0 (ExecuteTokenEvent) while GetCount != 0 ...
558040AD  mov  al, [0x55804114]    ; = 2        <-- CLEARED, only once the queue is empty
558040B2  not  eax
558040B4  and  al, [esi + 0x24]
```

There is a 3-entry flag-constant table at `0x55804110` **[Network.dpl]**: `01 / 02 / 04` at
`+0x00 / +0x04 / +0x08`. Flag **2** (`0x55804114`) is the active-pass flag above; flag 1
(`0x55804110`) is the narrower "inside ExecuteTokenEvent" flag.

### The two consequences

1. **Any code that calls `THero.PlaceItem@0x55788E94` from inside token execution is silently
   refused.** `PlaceItem` re-checks `GetBusy`, flag 2 is set for the whole pass, so it returns without
   minting and **without error**. A hook placed anywhere downstream of token execution would appear to
   run correctly and do nothing.
2. **Even outside token execution, only the first call per pass succeeds.** The first `PlaceItem`
   enqueues an event; condition (a) then reports busy for every subsequent call until the executer
   drains. So "equip a hero's worth of items in one go" via the token API is not possible regardless of
   where it is hooked.

This is the mechanical justification for the direct-`ExecutePlaceItem` design. It is **not** a
"tokens are inconvenient" preference — the token route provably cannot work from an engine-side hook.

---

## 8. What this means for `build_ai_itempickup.py` (built, NOT applied, NOT tested)

Every shape decision in that script traces to something above:

| Design choice | Forced by |
|---|---|
| `GetItem(list, i)` until it returns 0 — never read a count | §2 (layout trap + the bounds-checked accessor) |
| Refetch the list per slot, break on success | §3 (ground list compacts) + §5 (list may be freed) |
| Only item **IDs** cross a mutation boundary | §5 (use-after-free) |
| Null-check `GetItemsOnGround` | §5 (returns 0 on nearly every hex) |
| Scan positions 0..5 through `CanPlaceItem`; never call `GetItemTypePosition` | §4 (slot 5 unreachable; no bounds check; absolute mem ref) |
| Gate on `map+0x11C == 0` | §5 (that field *is* the combat-map override the getter reads) |
| Direct `ExecutePlaceItem`, no token | §6 + §7 (token route is refused inside execution, and rate-limited outside it) |

**None of this has been applied or run.** The reasoning is only as good as static analysis gets; the
first in-game test may still find something none of the above predicts.

---

## 9. Quick reference — addresses by module

**Enginep.dpl** (base `0x55500000`)
```
0x5551A2F4  TEChangeNotifyNode.GetCount      mov eax,[eax+8]; mov eax,[eax+8]; ret
0x5551A554  TEChangeNotifyNode.RemoveChild   two modes on GetControlStyle & 8
0x55519314  TEObject.GetControlStyle byte    = 0x01
```

**AoWEPACK.dpl** (base `0x55700000`)
```
0x55794A2C  TItemList.GetItem                bounds-checked both ends, 0 past end
0x55786740  THeroItems.GetItemTypePosition   NO bounds check — avoid
0x5578674C  THeroItems.CanPlaceItem          the real predicate (pos<6, empty, type match)
0x55786718  THeroItems.GetPositionItem
0x55786734  THeroItems.GetPositionType       reads the 0x558E8DB0 table
0x55786338  THeroItems style OR byte         = 0x08  (=> style 0x09, sparse)
0x55786058  THeroInventory style OR byte     = 0x08  (=> style 0x09, sparse)
0x558E8DB0  position -> type table           02 00 03 04 01 04        (6 bytes)
0x558E8DB8  type -> position table           01 04 00 02 03 0F 0F     (7 bytes)
0x55795D10  TItemHS.ItemsChanged             self-destructs when the list empties
0x55795CE0  TItemHS.Destroy                  frees the TItemList at itemHS+0x0C
0x55788C7C  THero.GetItemsOnGround           LIVE list, or 0 — never free it
0x557737A8  TAbstractAoWHSMap.GetHeroItemsOnGround   (map vmt+0x10C)
0x557516D0  TPlayer.GetBusy                  -> TTokenManager at map+0x23C, vmt+0x14
0x55788E94  THero.PlaceItem                  token minter — refused during execution
0x558FA040  the map singleton (BSS)
```
Field offsets: `itemHS+0x0C` list · `item+0x34` type · `map+0x11C` combat map · `map+0x174` init
state · `map+0x23C` token manager · `map+0xA4` current-turn player · `map+0xA5` local player ·
`player+0x48` busy lock · `player+0xA6` player index · `player+0xA7 != 0` = AI

**Network.dpl** (base `0x55800000` — ⚠ overlaps AoWEPACK, see §1)
```
0x558031D4  TTokenEvent.Create               counter := -1 (always plain-append)
0x55803868  TTokenControl.AddEvent           ENQUEUE ONLY — asynchronous
0x558038E0  count of tc.FEventList
0x55803D24  ExecuteTokenEvent
0x55803FD0  TTokenExecuter.Process           holds flag 2 across the whole drain loop
0x55804310  TTokenManager vmt+0x14           READY predicate (1 = ready); GetBusy negates it
0x55804110  flag constants                   01 / 02 / 04 at +0x00 / +0x04 / +0x08
```
Field offsets: `tc+4` event list · `executer+8` FActiveTC · `executer+0x24` flags ·
`executer+0x10` token-control list · `manager+0x10` control list · `manager+4` executer
