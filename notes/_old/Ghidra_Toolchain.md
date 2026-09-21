# Ghidra toolchain — what is installed and how to start it

**Status: WORKING, verified end-to-end 2026-08-03.** Replaced LaurieWired/GhidraMCP 1.4 (27 tools,
port 8080) with bethington/ghidra-mcp 6.0.0 (267 tools, port 8089) on a new Ghidra 12.1.2.

## What is installed

| piece | where | notes |
|---|---|---|
| Ghidra **12.1.2** | `%USERPROFILE%\Downloads\PROGRAMS\ghidra_12.1.2_PUBLIC\` | launcher `ghidraRun.bat`. Needs JDK 21+; runs on the installed Temurin 25. |
| Ghidra **11.3.2** (old) | `%USERPROFILE%\Downloads\PROGRAMS\ghidra_11.3.2_PUBLIC_20250415\` | left installed as the rollback path. Do not delete. |
| GhidraMCP **6.0.0** extension | `%APPDATA%\ghidra\ghidra_12.1.2_PUBLIC\Extensions\GhidraMCP\` | serves HTTP on **127.0.0.1:8089** |
| Python bridge | `ghidra-mcp-bridge 6.0.0`, installed into **both** Python 3.13 and 3.14 | see the interpreter trap below |
| release downloads | `%USERPROFILE%\Downloads\PROGRAMS\GhidraMCP-6.0.0\` | zip + wheel + INSTALLATION.md, kept for reinstall |
| Claude Desktop config | `%APPDATA%\Claude\claude_desktop_config.json` | `"ghidra": {"command":"%LOCALAPPDATA%\Programs\Python\Python313\python.exe","args":["-m","bridge_mcp_ghidra"]}` (absolute path, expanded in the real file) |

⚠ The console script `bridge-mcp-ghidra.exe` lands in a directory that is **not on PATH** — always use
the `python -m bridge_mcp_ghidra` form. There is **no `--ghidra-server` flag** in v6 (1.4 had one); the
bridge defaults to `http://127.0.0.1:8089` and auto-discovers.

### ⚠ Trap: `"command": "python"` launches a DIFFERENT interpreter than your shell

This machine has **two** Pythons: `C:\Python314\python.exe` (what a shell gets — the one `re_tools/`
uses) and `%LOCALAPPDATA%\Programs\Python\Python313\python.exe` (what **Claude Desktop** resolves bare
`python` to, because its PATH puts Python313 first). Installing the wheel from a shell puts it in 3.14
only, and the MCP server then dies instantly on every start:

```
MCP ghidra: Server disconnected.
```

with the real cause visible only in `%APPDATA%\Claude\logs\mcp-server-ghidra.log`:

```
...\Python313\python.exe: No module named bridge_mcp_ghidra
```

**Fix, and the standing rule:** install the wheel with *both* interpreters and pin `"command"` to an
**absolute** `python.exe` path in the config, never bare `python`. Diagnose any "Server disconnected"
from that log file first — the toast says nothing useful, and the bridge will run perfectly by hand
while failing under Claude.

⚠ Installing on 3.13 upgraded its `mcp` package 1.26.0 → 1.29.0. If some *other* Python MCP server
misbehaves after this, that shared dependency is the first thing to check.

## The project

**`<game dir>\Modding Resources\AoW1 Modding\AoW1-vanilla.gpr`** — program **`AoWEPACK_vanilla.dpl`**,
image base `0x55700000`, `x86:LE:32` / `borlanddelphi`, 8xx functions, headless-analysed in 122 s.

It is a byte-for-byte import of **`AoWEPACK_original_backup.dpl`** (the pristine pre-modding DLL), just
renamed so the program name states what it is. Verified through the running server:
`disassemble_function?address=55771068` → `557710f3: SUB EAX,0xa` (vanilla road build cost 10; the live
DLL charges 5).

- ⚠ Ghidra's `get_metadata` reports an `Executable Path` under a `…\Temp\claude\…\scratchpad\` folder —
  that is just where the renamed copy was staged for import. The bytes live in the project; the path is
  dead metadata, **not** evidence of where the vanilla DLL lives.
- The same folder also holds the older 11.3.2-era projects moved in on 2026-08-03: `Files`,
  `Projects\Misc Files`, `BloodTypes`, `MovePrediction`, `Transport Disappearance` (~219 MB total).
  Those are **11.3.2 projects** — opening one in 12.1.2 upgrades it one-way. Copy before opening.

## Starting it

1. Run `ghidraRun.bat` from the 12.1.2 folder.
2. **File → Open Project** → `AoW1-vanilla.gpr` (the recent-projects list may still point at the old
   `C:\GAMES\AoW1 Modding` location it was moved from).
3. Open `AoWEPACK_vanilla.dpl` in the CodeBrowser.
4. The GhidraMCP plugin is saved in the tool config, so it should already be on. If not:
   **File → Configure → Configure All Plugins → Miscellaneous → Configure → GhidraMCPPlugin**.
   It is a standalone plugin, so it is filed under *Miscellaneous*, not under a package.

Verify without touching Claude:

```bash
curl -s http://127.0.0.1:8089/check_connection
```

Expected: `Connected: GhidraMCP plugin running with program 'AoWEPACK_vanilla.dpl'`. Other useful raw
endpoints: `/list_open_programs`, `/get_metadata`, `/list_functions`,
`/disassemble_function?address=<VA>`, `/decompile_function_by_address?address=<VA>`.

## Policy: this project is VANILLA-ONLY, deliberately

Do **not** import the live `AoWEPACK.dpl` — decided 2026-08-03, don't re-propose it:

- Caves are position-independent via `call $+5; pop; sub`. Ghidra models the `call` as a real
  subroutine, so its stack analysis and the decompile of **every cave** come out as garbage.
- A 5-byte `E9` hook makes Ghidra end the host function at the tail jump, orphaning the original tail as
  undefined bytes, and the cave's jump back into mid-function adds an edge it attributes poorly.
  **Patched functions therefore decompile worse in a live import than in vanilla.**

Correct split: **Ghidra (vanilla) for engine logic, xrefs, types; capstone for anything patched** —
`python re_tools/dasm.py AoWEPACK.dpl <VA> <len>` reads live bytes with imports resolved.

⚠ Corollary: every data table read out of Ghidra (movement costs `0x558E84FC`, rank stat tables) is a
**vanilla** number, not the installed Ziggurat-rebalanced one. Read those from the live file.

## Rollback

One file. Restore the backup and restart Claude Desktop:

```bash
cp "$APPDATA/Claude/claude_desktop_config.json.pre-ghidramcp6" "$APPDATA/Claude/claude_desktop_config.json"
```

Then run the 11.3.2 `ghidraRun.bat` instead. Nothing about the 11.3.2 install, its extension, or its
projects was modified.
