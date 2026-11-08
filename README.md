# MGSV Radio Tuner and Mission Skip

For Metal Gear Solid V: The Phantom Pain on Windows. Reduce Ocelot and Miller's radio chatter, and skip
story missions and side ops by holding three keys. No Infinite Heaven or SnakeBite needed.

[Русская версия](README.ru.md)

## Features

- **Radio filter:** set how many lines to keep per category, with a pause between comments.
- **Mission skip:** hold `V` + `R` + `E` for 3 seconds in a story mission and it counts as cleared.
- **Side op skip:** the same keys in free roam clear the side op loaded nearby.
- **Stuck mission fix:** if a skipped mission has not started ending after 6 seconds, the mod ends it.
- **Story check:** the same keys where nothing can be skipped list the missions that episode 43 still
  needs, and open it if the game already permits it.

## Install

1. Close the game. Download the release zip and unpack it anywhere.
2. Run `Install.bat` and allow administrator rights.
3. If the game is not found, paste the folder that contains `master`.
4. Start the game. About 8 seconds after loading you should see
   `Radio Tuner: hold V+R+E 3 sec = skip mission / side op`.

To remove the mod, run `Uninstall.bat` from the same folder.

## Settings

Edit `radio_tuner.json`, then run `Install.bat` again.

| Setting | Default | Meaning |
|---|---|---|
| `chance.common` | 30 | % of routine comments to keep (`f…_rtrg` labels) |
| `chance.mission` | 100 | % of mission reactions to keep (`s…_rtrg` labels) |
| `chance.story` | 100 | % of briefings and mission progress to keep. Keep at 100 |
| `chance.gameover` | 100 | % of Game Over lines to keep |
| `cooldown_sec` | 45 | Minimum pause between common and mission comments |
| `mute_labels` | `[]` | Radio labels to always mute |
| `allow_labels` | `[]` | Radio labels to always keep |
| `skip_mission` | `true` | `false` turns off the skip and the story check |
| `skip_hold_sec` | 3 | How long to hold the keys, 1 second or more |
| `game_dir` | empty | Game folder, found automatically when empty |

## Before you skip

Save first. A skipped mission counts as cleared, but its objectives stay undone:

- cutscenes during and after the mission can be lost, including the ending of episode 46;
- rank and rewards will be low;
- some missions set story flags only through their normal ending, so progress may not advance.

## Compatibility

- Developed and played on the PC version, game version 1.0.15.4. Other versions are untested.
- Skipping was tried with a keyboard only.
- The stuck mission fix and the story check have only run in simulation so far, not in the game.
- **Offline only.** Do not use it with FOB or MGO. The skip does nothing on FOB missions, but modified
  game files online are at your own risk.
- It changes `TppRadio.lua`. Mods that replace that file, possibly including Infinite Heaven, can conflict
  with it. After changing other mods, run `Uninstall.bat` and then `Install.bat`.

If restoring fails, for example after a game update, use Steam: Properties > Installed Files >
Verify integrity of game files.

## How it works

The patcher finds `TppRadio.lua` inside the game's `.dat` archives, appends a small Lua block and writes the
new version to the end of the same archive. Other files are not changed. What it needs for restoring is saved in
`radio_tuner_state.json` in the game folder, and restoring returns the archive byte for byte.

The Lua block wraps `TppRadio.PlayCommon` for the filter and `TppPlayer.Update` for reading the keys. The mod
contains no game files.

## Development

Needs Python 3.8+ and `luajit`.

```bash
python3 tests/test_tuner.py
```

```bash
python3 tests/test_skip.py
```

```bash
python3 tests/test_cli.py
```

```bash
python3 build_release.py
```

The tests use a synthetic archive and stubs of the game's API, so they check the logic but not the real game.
`python src/radio_tuner.py` opens a settings window if your Python has tkinter. The release zip does not.

## Credits

- [GzsTool](https://github.com/Atvaark/GzsTool) by Atvaark for the archive format.
- [Infinite Heaven](https://github.com/TinManTex/InfiniteHeaven) by TinManTex, whose published scripts were the
  reference for how the game's Lua works.
- Developed with the help of Claude Code, an AI coding assistant.

Not affiliated with or endorsed by Konami. Released under the [MIT License](LICENSE).
