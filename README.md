# Ziggurat Modding Notes

The working notes, patch scripts and reverse-engineering toolkit behind
[Ziggurat](https://github.com/BING-XI/Ziggurat-Engine-Mod), a rebalance of Age of Wonders (1999)
applied as binary patches to the game's Delphi 3 modules.

Almost everything here was written by, or for, an AI coding assistant over several months of
sessions. It is a record, not a tutorial. Start at `notes/00-INDEX.md`.

| folder | holds |
|---|---|
| `notes/` | twelve thematic notes: combat maths, abilities, spells, UI, editor, terrain, AI, engine internals, RE toolchain |
| `build_scripts/` | one `build_*.py` per feature. Keystone-assembled caves, dry-run by default, `--apply` to write, most with `--undo` |
| `re_tools/` | PE / VMT / DFM parsers, IAT-reference finder, annotated disassembler, RNG audit, hang-stack reader |
| `agents/` | the pm / coder / qa agent prompts used with Claude Code |
| `CLAUDE.md` | the standing project instructions the assistant reads every session |

Scripts expect to sit at `<game dir>/Ziggurat/Modding Resources/build_scripts/` inside a
Ziggurat install and need `pip install capstone keystone-engine`. Paths that pointed at the
author's machine have been replaced with `<game dir>`, `<documents>` or `<profile>`.
