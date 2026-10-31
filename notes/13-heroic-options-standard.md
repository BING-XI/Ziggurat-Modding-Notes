# Heroic options — the standard

How a unit type's heroic options are designed. Derived from the owner's edits of the Human options
(saved in AoWzEd, 2026-10-30) and his rulings of 2026-10-21/22; his edits are the examples. A heroic
unit takes one of its type's options: up to three per type, each up to three abilities (a levelled
one counts once) plus six stat deltas, −10..+10 (`build_scripts/heroicchoice.py`). The owner authors
and fine-tunes options in the editor; `build_heroic_options.py` only writes first drafts into empty
slots.

## Shape of an option

- One clear direction per option, and three different directions per type.
- Two or three abilities that work together are the norm: Throw Javelin + Marksmanship 4 +
  Skirmisher (Lancer); Magic Immunity + Magic Strike + Magebane (Pikeman); Mantle of Gloom +
  Invisibility (Priest).
- Small stat deltas, +1 or +2, season most options and follow the direction: the Lancer's
  monster-hunter option is Fearless + Monster Slaying with DAM +1, MV +4, RES +1. A bare-stat option
  is rare.
- No padding: an ability that adds little to the direction comes off (Night Vision was dropped from
  the Musketeer's Marksmanship 8).
- One ability may appear in two options of the same type (Mental Discipline in two of the
  Zweihander's).

## What the stats and protections mean

- **Armour is Defense.** Heavy armour = DEF up, Moves down: Man-at-Arms DEF +2, MV −4.
- **Physical Protection is not armour.** It means flesh that mundane weapons barely hurt — the mark of
  a supernatural creature. Never give it to mundane troops.
- Physical Immunity: never. Elemental Protections: never; use the elemental Immunities. Magic
  Protection: fine. Magic Immunity: fine inside a mage-hunter package (Pikeman: Magic Immunity +
  Magic Strike + Magebane, RES +2).

## Maluses

- A strong gain carries a cost. Extra Shots comes with DEF −1, MV −2 (Musketeer) or MV −4 (Air
  Galley); heavy armour with MV −4; Flying with DEF and MV down.
- Nothing else takes a malus.

## Roles

- **A first ranged attack is allowed**, bundled with enough Marksmanship to land and a way to use it:
  Lancer Throw Javelin + Marksmanship 4 + Skirmisher, DEF +1. A shooter may gain a second ranged attack
  (Air Galley: True Seeing + Magic Bolts).
- **Skirmisher** works after melee and ranged attacks alike (the attack costs 12 moves instead of the
  turn, once per round); pair it with mobility or terrain (Musketeer: Wall Climbing + Skirmisher).
- **Shooters:** Extra Shots with its malus; a top Marksmanship on its own; or Skirmisher with a
  movement or terrain ability.
- **Leaders and line troops:** Rally, Drillmaster, Bard's Skills, Mental Discipline (Cavalier: Bard's
  Skills + Drillmaster + Rally, RES +2; Man-at-Arms: Rally + Mental Discipline, RES +4).
- **A non-caster** can take Spell Casting 1 as a battle-mage option (Zweihander, RES +1).
- **A holy unit can turn dark:** Priest Cause Fear + Round Attack, ATK +2; Mantle of Gloom +
  Invisibility, MV +2.

## Which abilities

- Existing abilities, plus the new ones the owner has endorsed: Extra Shots, Rally, Skirmisher,
  Searing Aura, Mirror Image, Mental Discipline, Rime Aura, Lucky, Smoky Haze, Stone Gaze. Proposals he
  has not endorsed stay out.
