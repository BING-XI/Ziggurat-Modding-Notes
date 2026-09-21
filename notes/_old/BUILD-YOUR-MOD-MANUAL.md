# Build a Game-Data-Driven Manual for Your AoW1 Mod

*(Shared by the AoWx project — this is how the AoWx Manual.html is generated 100% from game
files. The included `build_mod_manual.py` is a portable, trimmed version that works on any
AoW1 install. All formats below were reverse engineered from the engine — use them for
whatever tooling you like.)*

## Quick start

1. Copy `build_mod_manual.py` into your game root (next to AoW.exe).
2. `py build_mod_manual.py`  (Python 3; Pillow optional — `py -m pip install pillow` for portraits)
3. Open `Mod Manual.html`. Self-contained single file, portraits embedded, safe to ship with your mod.

It reads `Release/Unitres.pfs`, `Ability.pfs`, `Spells.pfs`, `Unitgfx.pfs` and the face ILBs —
so it always reflects **what your mod actually does**, not what a stale doc says. Re-run after
every editor save to refresh.

Optional JSON files next to the script:
- `abil_names.json` — `{"20": "My Custom Ability"}` override/extend ability id→name
- `spell_names.json` — `{"3": "Fireball"}` (the game files store **no** spell names!)
- `face_offset.json` — `{"FACES\\MYPACK.ILB": -1}` per-file portrait index correction (see below)

---

## The file formats (everything the script relies on)

### PFS / HSS property streams (`Release/*.pfs`)

- Optional magic `1C DF 44 21`, then version `01 00 00`, then the **root property table**.
- Property table: `[ctrl:u8]` → if `ctrl&0x80` read `nd:u32`; then `(ctrl&0x7F)` byte pairs
  `(tag:u8, off:u8)`; then `nd` dword pairs `(tag:u32, off:u32)`. **Offsets are relative to the
  table's END** (the "data base"). The engine reader is tag-indexed, not sequential — never
  assume field order.
- Root field **1** = children table (itself a property table: id → offset). Child records are
  `[classid:u32][table][data]` — EXCEPT `Ability.pfs` and `Spells.pfs`, whose root table IS the
  record list and records start with the table directly (no classid).

### Units — `Unitres.pfs` (child classid 0x20212)

| tag | meaning |
|-----|---------|
| 0xA | race ShortString — **or the unit name if 0xB is absent** (independents/monsters) |
| 0xB | unit name |
| 0xE–0x13 | ATK / DEF / DMG / HP / Move / RES bytes (255 = no melee attack) |
| 0x14 | level |
| 0x1A | description: `[len:u32][chars]` |
| 0x1B | gold cost (u32) |
| 0x19 / 0x1E / 0x1F | base / Silver-medal / Gold-medal **ability owners** |
| 0x8 | first dword = gfx id for the portrait chain (defaults to the unit's child id) |

Ability owner sub-table: tag **2** = count word, tag **3** = bitfield where **bit i = has
ability id i**. Leveled abilities (Marksmanship I–III etc.) appear as byte pattern
`02 00 02 0A 00 0B 01 <level> <id> 00` inside the owner's span.

### Abilities — `Ability.pfs`

Root key = **ability id + 10**. Tags: **5** = description (`len32`, cp1252, includes the
I/II/III level text), **6** = hero level-up skill-point cost (absent = not learnable),
**9** = 2-byte set `TAbilitySelectionTypes`:
bit0 unit, bit1–5 head/torso/attack/defense/ring item, bit6 use item,
**bit7 = Customize Leader, bit8 = Hero Upgrade**, bit9 editor.
(That's how "can heroes learn this" is stored — the same checkboxes you see in the editor.)

⚠️ Some ability ids are **runtime-assigned at registration** and can differ between mods if
you've added/registered custom abilities. The script ships a vanilla-ish id→name map; verify
against your mod (hover an ability in the editor, or cross-check descriptions) and override
via `abil_names.json`.

### Spells — `Spells.pfs`

Root table = spell list, records are tables directly. Tag **0xA** description, **0xD** casting
cost, **0xF** research cost. **Names are not in the game files** (they're UI resource strings) —
provide `spell_names.json` or live with "Spell #id".

### Portraits — `Unitgfx.pfs` chain + ILB decoding

Unit tag8 gfx id → `Unitgfx.pfs` child (classid 0x20210): tag **6** = face ILB path
(e.g. `FACES\L_FACES.ILB`), tag **8** = face index within that ILB, tag 5 = unit sprite ILB,
tag 7 = legacy display name (don't trust it for matching).

⚠️ **Index base differs per face file.** The original game files (UNITS/H_FACES/L_FACES/
ADD_UNITS/R_FACES) are 0-based vs the marker-scan order; some custom face packs are 1-based
(subtract 1). If a pack's portraits are all shifted by one, add it to `face_offset.json`
with `-1`.

### ILB pixel formats (all three cracked)

Frames are located by the pixel-format marker dword **0x56509310**. Relative to the marker:
`-0x18` data size, `-0x14` data offset (add the file's data base = dword at file offset 0x10),
`-0x10/-0xC` record w/h, `+4/+8` sub-image w/h. Transparent key color = RGB565 **0x4D2B**.

1. **Raw 16bpp**: when `size == w*h*2` — pixels are literal RGB565, dims at `-0x10/-0xC`.
2. **Row-encoded 16bpp**: otherwise — dims at `+4/+8`; each row is
   `[len:u16][xstart:u16][(len-4)/2 pixels]`, and the **stride is len rounded UP to a multiple
   of 4** — the pad word looks like a pixel and shears the image if you miss this.
   Extra trap: city tiles (`City1-4.ILB`) need rows **centered** (`x0 = (w-n)//2`), not
   x=xstart — left-aligning shears them 45°.
3. **8bpp RLE (unit sprites, `Images/UNITS/**`)**: 256×RGBX palette at file+0x24; record table
   entries are ~0x5F bytes (`[dw 2][b 2][nameLen dw][8.3 name][... w,h @name_end, size,offset
   @name_end+21]`); rows `[len:u16][xstart:u16][payload]` with **no alignment**; payload bytes:
   `0x00` escape → next byte = transparent-run length, else palette index.
   Direction sets: 72 records = 6 directions × 12 animation frames; **set 2 (record 12) is the
   front-right facing** the editor preview uses (set order: front, front-right, back-right,
   back, back-left, front-left).

### Items (bonus, not in the script) — `ITEMS.PFS` + `ITEMGFX.PFS`

Item record (classid 0x20268): tag 8 name, tag 9 second string, **0xF slot**
(0 Head, 1 Torso, 2 Attack, 3 Defense, 4 Ring, 6 Use), **0x13 value**, **0xB/0xC/0xD/0xE =
ATK/DEF/DMG/RES signed byte bonuses**, 0x14 movement, **0x7 gfx id**, and the item's own table
doubles as an ability owner (tag2/tag3 + the leveled pattern above). `ITEMGFX.PFS` children:
tag6 = ILB path, **tag7 = file-local frame index** (tag3 is the global id — don't use it).
Watch for dangling gfx refs — several vanilla+modded items point past the end of their ILB.

---

## Extending it

The script is deliberately small and dependency-light (Pillow only, and only for portraits).
Things the full AoWx manual adds that you can bolt on with the formats above: medal stat-row
tables, per-ability hover tooltips, spell spheres/levels (we sourced those from our docs — the
pfs doesn't group them), items page, changelog page, search. If you build something cool on
top of this, share it back. — AoWx
