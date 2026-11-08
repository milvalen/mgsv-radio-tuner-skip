"""Bad settings must give a clear message, leave no traceback and not touch an installed patch.

Run: python3 tests/test_cli.py
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.dont_write_bytecode = True

import qar  # noqa: E402
import test_tuner  # noqa: E402

APP = os.path.join(HERE, "..", "src", "radio_tuner.py")


def run(*args):
    return subprocess.run([sys.executable, "-B", APP, *args], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        game = os.path.join(tmp, "game")
        os.makedirs(os.path.join(game, "master", "0"))
        with open(os.path.join(HERE, "fixtures", "TppRadioStub.lua"), "rb") as f:
            radio = test_tuner.minify_module_name(f.read())
        data = os.path.join(game, "master", "data1.dat")
        test_tuner.build_archive(data, [(0x0ABCDEF012345678, radio, True, 0xBEEF)])
        conf = os.path.join(tmp, "c.json")

        with open(conf, "w") as f:
            json.dump({}, f)
        r = run("--apply", "--game-dir", game, "--config", conf)
        assert r.returncode == 0, r.stdout + r.stderr
        with open(data, "rb") as f:
            patched = f.read()

        for bad in ('{bad json', '{"chance": 5}', '{"chance": {"common": "lots"}}',
                    '{"mute_labels": ["not a label!"]}', '{"skip_hold_sec": "soon"}'):
            with open(conf, "w") as f:
                f.write(bad)
            r = run("--apply", "--game-dir", game, "--config", conf)
            assert r.returncode == 1, (bad, r.returncode, r.stdout, r.stderr)
            assert "Traceback" not in r.stderr, (bad, r.stderr)
            with open(data, "rb") as f:
                assert f.read() == patched, "bad settings changed the game: %s" % bad

        assert qar.QarArchive(data).entries
        with open(conf, "w") as f:
            json.dump({}, f)
        r = run("--apply", "--game-dir", os.path.join(tmp, "nowhere"), "--config", conf)
        assert r.returncode == 1 and "Traceback" not in r.stderr, r.stderr
    print("ALL OK")


if __name__ == "__main__":
    main()
