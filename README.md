PK EM Helper
=====

![License](https://img.shields.io/badge/License-GPLv3-blue.svg)

Pokémon Emerald helper to distribute the Aurora Ticket, Mystic Ticket, Eon Ticket and Old Sea Map and set their event flags, programmed in Python. Companion to [pk-ah-helper](https://github.com/byjpr/pk-ah-helper), which does the same for FireRed and LeafGreen.

For each event it:
  * adds the key item to the Key Items pocket (quantity 1, correctly
    XOR-encrypted with the save's encryption key)
  * sets the "received" event flag (where the game defines one)
  * sets the ferry-destination flag so the Lilycove sailor lists the island

| Event | Item | Destination | Encounter |
| --- | --- | --- | --- |
| `--aurora` | Aurora Ticket | Birth Island | Deoxys (Lv30) |
| `--mystic` | Mystic Ticket | Navel Rock | Ho-Oh + Lugia (Lv70) |
| `--eon` | Eon Ticket | Southern Island | Latios or Latias (Lv50) |
| `--oldseamap` | Old Sea Map | Faraway Island | Mew (Lv30) |

## Usage

```
Usage:
  python3 emerald_tickets.py SAVE.sav                  # all four events -> SAVE.patched.sav
  python3 emerald_tickets.py SAVE.sav --aurora         # one event only
  python3 emerald_tickets.py SAVE.sav --eon --mystic   # any combination
  python3 emerald_tickets.py SAVE.sav -o out.sav       # choose output path
  python3 emerald_tickets.py SAVE.sav --in-place       # overwrite (writes .bak first)
  python3 emerald_tickets.py SAVE.sav --info           # inspect, change nothing
```

All destinations depart from the ferry terminal at Lilycove City harbor.

> [!WARNING]
> **Back up your save first.** Even though `--in-place` writes a `.bak`
> automatically, keep your own copy of the original save somewhere else
> before running the tool on any file. Save corruption can't always be
> undone, and a backup sitting next to the file being modified is not a
> real backup.

## Using RetroArch `.srm` saves

RetroArch battery saves (`.srm`) for GBA cores are the same raw flash format
as `.sav`, so the tool works on them directly — the extension doesn't matter:

```
python3 emerald_tickets.py "Pokemon - Emerald Version.srm"
```

The output will be named `Pokemon - Emerald Version.patched.sav`. RetroArch
only loads a save whose name matches the ROM exactly, so rename it back
before launching the game:

```
mv "Pokemon - Emerald Version.patched.sav" "Pokemon - Emerald Version.srm"
```

Alternatively, patch with `--in-place` and no renaming is needed (a `.bak`
backup of the original is written first).

**Note:** make sure RetroArch is fully closed before patching, or the core
will overwrite your patched file with its in-memory copy. Savestates
(`.state` files) are not supported — save in-game at a Pokémon Center first.

## Emerald only

This tool is for Pokémon Emerald saves only. Emerald stores its flags, bag
and encryption key at different offsets than FireRed/LeafGreen, and every
event flag has a different ID — running the wrong tool on a save would
corrupt it. The script detects the game and refuses to patch anything that
doesn't look like Emerald; for FireRed/LeafGreen saves, use
[pk-ah-helper](https://github.com/byjpr/pk-ah-helper) instead.

All offsets and constants are taken from the
[pret/pokeemerald](https://github.com/pret/pokeemerald) decompilation.
