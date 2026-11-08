"""Patcher logic: finding the game, applying settings, restoring."""

import copy
import json
import os
import sys

import luapatch
from qar import QarArchive, QarError

STATE_NAME = "radio_tuner_state.json"
CONFIG_NAME = "radio_tuner.json"


class TunerError(Exception):
    pass


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_config(path=None):
    path = path or os.path.join(app_dir(), CONFIG_NAME)
    cfg = copy.deepcopy(luapatch.DEFAULT_CONFIG)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if k == "chance":
                cfg["chance"].update(v)
            else:
                cfg[k] = v
    return cfg


def save_config(cfg, path=None):
    path = path or os.path.join(app_dir(), CONFIG_NAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# --- finding the game folder ---

def _steam_roots():
    roots = []
    if sys.platform == "win32":
        try:
            import winreg
            for hive, key, name in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            ):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        roots.append(winreg.QueryValueEx(k, name)[0])
                except OSError:
                    pass
        except ImportError:
            pass
        roots += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    else:
        home = os.path.expanduser("~")
        roots += [os.path.join(home, ".steam", "steam"), os.path.join(home, ".local", "share", "Steam")]
    libs = []
    for r in roots:
        libs.append(r)
        vdf = os.path.join(r, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.strip().split('"')
                    if len(parts) >= 4 and parts[1] == "path":
                        libs.append(parts[3].replace("\\\\", "\\"))
    return libs


def is_game_dir(path):
    return bool(path) and os.path.isdir(os.path.join(path, "master"))


def find_game_dir():
    for lib in _steam_roots():
        cand = os.path.join(lib, "steamapps", "common", "MGS_TPP")
        if is_game_dir(cand):
            return os.path.normpath(cand)
    return ""


def list_archives(game_dir):
    master = os.path.join(game_dir, "master")
    out = []
    for sub in ("0", ""):
        d = os.path.join(master, sub) if sub else master
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if name.lower().endswith(".dat"):
                    out.append(os.path.join(d, name))
    return out


# --- state (what is patched, how to undo it) ---

def _state_path(game_dir):
    return os.path.join(game_dir, STATE_NAME)


def _load_state(game_dir):
    p = _state_path(game_dir)
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(game_dir, state):
    p = _state_path(game_dir)
    if not state:
        if os.path.exists(p):
            os.remove(p)
        return
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _looks_like_text(prefix):
    if not prefix or b"\0" in prefix:
        return False
    printable = sum(1 for b in prefix if 32 <= b < 127 or b in (9, 10, 13))
    return printable >= len(prefix) * 0.95


def restore(game_dir, log=print):
    state = _load_state(game_dir)
    if not state:
        log("The patch is not installed, nothing to restore.")
        return
    left = {}
    for rel, infos in state.items():
        path = os.path.join(game_dir, rel)
        arc = QarArchive(path)
        try:
            for info in reversed(infos):
                arc.restore_entry(info)
            log("Restored: %s" % rel)
        except QarError as e:
            log("Could not restore %s: %s" % (rel, e))
            left[rel] = infos
    _save_state(game_dir, left)
    if left:
        raise TunerError("Some files were not restored. In Steam: game Properties > "
                         "Installed Files > Verify integrity of game files.")


def apply(game_dir, cfg, log=print):
    if not is_game_dir(game_dir):
        raise TunerError("This is not the MGS_TPP folder (no master subfolder): %s" % game_dir)
    luapatch.build_filter("M", cfg)  # validate the config before touching any file
    if _load_state(game_dir):
        log("Removing the previous version of the patch...")
        try:
            restore(game_dir, log)
        except TunerError:
            # Steam may have updated the archive, so the old state is stale
            _save_state(game_dir, {})

    state = {}
    patched = 0
    for path in list_archives(game_dir):
        rel = os.path.relpath(path, game_dir)
        try:
            arc = QarArchive(path)
        except QarError as e:
            log("Skipping %s: %s" % (rel, e))
            continue
        log("Looking for TppRadio.lua in %s (%d files)..." % (rel, len(arc.entries)))
        hits = []

        def pred(prefix, read_full, hits=hits):
            if not _looks_like_text(prefix):
                return False
            try:
                data = read_full()
            except Exception:
                return False
            if luapatch.is_tpp_radio(data):
                hits.append(data)
                return True
            return False

        entries = arc.find_entries(pred)
        for e, data in zip(entries, hits):
            new = luapatch.apply_patch(data, cfg)
            info = arc.replace_entry(e, new)
            state.setdefault(rel, []).append(info)
            _save_state(game_dir, state)  # save right away so restoring works even after a crash
            check = QarArchive(path)
            with open(path, "rb") as f:
                got = check.read_entry(f, check.entries[e.index])
            if got != new:
                restore(game_dir, log)
                raise TunerError("Verification after writing failed in %s, everything was restored" % rel)
            patched += 1
            log("  patched (entry #%d)" % e.index)
    if not patched:
        raise TunerError("TppRadio.lua was not found in any archive. This may be a different game version.")
    log("Done. Patched copies of TppRadio.lua: %d" % patched)
