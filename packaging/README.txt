MGSV Radio Tuner and Mission Skip
For Metal Gear Solid V: The Phantom Pain on Windows. Offline only.

INSTALL
1. Close the game.
2. Run Install.bat and allow administrator rights.
3. If the game is not found, paste the folder that contains "master".

To remove it, run Uninstall.bat. Keep this folder: it is what restores the game.
If a game update changes the files, run Install.bat again. If restoring fails,
use Steam: Properties > Installed Files > Verify integrity of game files.

IN THE GAME
About 8 seconds after loading you see:
"Radio Tuner: hold V+R+E 3 sec = skip mission / side op"
If this message never appears, the patch is not active.

Hold V + R + E for 3 seconds:
- in a story mission: the mission counts as cleared;
- in free roam near a loaded side op: the side op counts as cleared;
- anywhere else: a story check tells you what mission 43 still needs.

Save first. Skipping can lose cutscenes, lowers your rank, and may break story
progress in some missions.

SETTINGS (radio_tuner.json, run Install.bat again after changing it)
chance         how many lines to keep, in percent: common, mission, story, gameover
               Keep story at 100, muting it can stall a mission.
cooldown_sec   minimum pause between common and mission comments
mute_labels    radio labels to always mute
allow_labels   radio labels to always keep
skip_mission   false turns off the skip and the story check
skip_hold_sec  how long to hold the keys, 1 second or more

Source code: https://github.com/milvalen/mgsv-radio-tuner-skip
