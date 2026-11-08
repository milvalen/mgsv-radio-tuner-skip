"""MGSV Radio Tuner: controls Ocelot/Miller radio chatter and adds a mission and side op skip
to Metal Gear Solid V: The Phantom Pain.

Without arguments opens the settings window (needs tkinter). CLI:
    radio_tuner.py --apply [--game-dir DIR] [--config FILE]
    radio_tuner.py --restore [--game-dir DIR]
"""

import argparse
import queue
import sys
import threading

import luapatch
import tuner
from qar import QarError


def ask_game_dir(args, cfg):
    """Asks for the game folder when it is not in Steam's default locations, and remembers it."""
    if not sys.stdin or not sys.stdin.isatty():
        return ""
    print("Could not find the game automatically.")
    print(r'Paste the game folder (the one with the "master" folder), e.g. D:\Games\MGS_TPP')
    while True:
        try:
            path = input("> ").strip().strip('"')
        except EOFError:
            return ""
        if not path:
            return ""
        if tuner.is_game_dir(path):
            cfg["game_dir"] = path
            tuner.save_config(cfg, args.config)
            return path
        print('No "master" folder there. Try again, or press Enter to cancel.')


def run_cli(args):
    try:
        cfg = tuner.load_config(args.config)
    except (OSError, ValueError, TypeError) as e:
        print("Could not read the settings file: %s" % e)
        return 1
    game_dir = args.game_dir or cfg.get("game_dir") or tuner.find_game_dir()
    if not game_dir:
        game_dir = ask_game_dir(args, cfg)
    if not game_dir:
        print("Game folder not found. Pass it with --game-dir.")
        return 2
    try:
        if args.restore:
            tuner.restore(game_dir)
        else:
            tuner.apply(game_dir, cfg)
    except (tuner.TunerError, luapatch.PatchError, QarError, OSError, ValueError, TypeError, AttributeError) as e:
        print("Error: %s" % e)
        return 1
    return 0


def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    cfg = tuner.load_config()
    if not tuner.is_game_dir(cfg.get("game_dir")):
        cfg["game_dir"] = tuner.find_game_dir()

    root = tk.Tk()
    root.title("MGSV Radio Tuner")
    root.minsize(560, 0)
    frm = ttk.Frame(root, padding=12)
    frm.grid(sticky="nsew")
    root.columnconfigure(0, weight=1)
    frm.columnconfigure(1, weight=1)

    row = 0
    ttk.Label(frm, text="Game folder (MGS_TPP):").grid(row=row, column=0, sticky="w")
    game_var = tk.StringVar(value=cfg.get("game_dir", ""))
    ttk.Entry(frm, textvariable=game_var).grid(row=row, column=1, sticky="ew", padx=6)

    def browse():
        d = filedialog.askdirectory(title="MGS_TPP folder")
        if d:
            game_var.set(d)

    ttk.Button(frm, text="Browse…", command=browse).grid(row=row, column=2)
    row += 1

    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="ew", pady=10)
    row += 1
    ttk.Label(frm, text="How many lines to keep (0% = off, 100% = vanilla)",
              font=("", 10, "bold")).grid(row=row, column=0, columnspan=3, sticky="w")
    row += 1

    chance_vars = {}
    for cat, (title, hint, _) in luapatch.CATEGORIES.items():
        var = tk.IntVar(value=int(cfg["chance"].get(cat, 100)))
        chance_vars[cat] = var
        ttk.Label(frm, text=title).grid(row=row, column=0, sticky="w", pady=(6, 0))
        val = ttk.Label(frm, width=5)
        ttk.Scale(frm, from_=0, to=100, variable=var,
                  command=lambda v, var=var, val=val: (var.set(round(float(v) / 5) * 5),
                                                       val.config(text="%d%%" % var.get()))
                  ).grid(row=row, column=1, sticky="ew", padx=6, pady=(6, 0))
        val.config(text="%d%%" % var.get())
        val.grid(row=row, column=2, pady=(6, 0))
        row += 1
        ttk.Label(frm, text=hint, foreground="gray", wraplength=520).grid(
            row=row, column=0, columnspan=3, sticky="w")
        row += 1

    ttk.Separator(frm).grid(row=row, column=0, columnspan=3, sticky="ew", pady=10)
    row += 1
    ttk.Label(frm, text="Pause between lines, seconds").grid(row=row, column=0, sticky="w")
    cd_var = tk.IntVar(value=int(cfg.get("cooldown_sec", 0)))
    cd_val = ttk.Label(frm, width=5)
    ttk.Scale(frm, from_=0, to=300, variable=cd_var,
              command=lambda v: (cd_var.set(round(float(v) / 5) * 5), cd_val.config(text=str(cd_var.get())))
              ).grid(row=row, column=1, sticky="ew", padx=6)
    cd_val.config(text=str(cd_var.get()))
    cd_val.grid(row=row, column=2)
    row += 1
    ttk.Label(frm, text="After a comment, the next one (common or mission) waits at least this long. "
                        "Story radio is not affected.",
              foreground="gray", wraplength=520).grid(row=row, column=0, columnspan=3, sticky="w")
    row += 1

    adv = ttk.LabelFrame(frm, text="Advanced: specific radio labels (comma separated)", padding=6)
    adv.grid(row=row, column=0, columnspan=3, sticky="ew", pady=10)
    adv.columnconfigure(1, weight=1)
    ttk.Label(adv, text="Always mute:").grid(row=0, column=0, sticky="w")
    mute_var = tk.StringVar(value=", ".join(cfg.get("mute_labels", [])))
    ttk.Entry(adv, textvariable=mute_var).grid(row=0, column=1, sticky="ew", padx=6)
    ttk.Label(adv, text="Always keep:").grid(row=1, column=0, sticky="w")
    allow_var = tk.StringVar(value=", ".join(cfg.get("allow_labels", [])))
    ttk.Entry(adv, textvariable=allow_var).grid(row=1, column=1, sticky="ew", padx=6)
    row += 1

    log = tk.Text(frm, height=8, width=70, state="disabled")
    log.grid(row=row, column=0, columnspan=3, sticky="ew")
    row += 1

    btns = ttk.Frame(frm)
    btns.grid(row=row, column=0, columnspan=3, sticky="e", pady=(8, 0))
    apply_btn = ttk.Button(btns, text="Apply")
    restore_btn = ttk.Button(btns, text="Restore original")
    restore_btn.pack(side="left", padx=4)
    apply_btn.pack(side="left")

    msgs = queue.Queue()

    def write_log(text):
        log.config(state="normal")
        log.insert("end", text + "\n")
        log.see("end")
        log.config(state="disabled")

    def pump():
        try:
            while True:
                kind, text = msgs.get_nowait()
                if kind == "log":
                    write_log(text)
                else:
                    apply_btn.config(state="normal")
                    restore_btn.config(state="normal")
                    if kind == "error":
                        write_log("ERROR: " + text)
                        messagebox.showerror("Radio Tuner", text)
                    else:
                        messagebox.showinfo("Radio Tuner", text)
        except queue.Empty:
            pass
        root.after(100, pump)

    def split(s):
        return [x.strip() for x in s.replace("\n", ",").split(",") if x.strip()]

    def collect():
        cfg["game_dir"] = game_var.get().strip()
        cfg["chance"] = {c: v.get() for c, v in chance_vars.items()}
        cfg["cooldown_sec"] = cd_var.get()
        cfg["mute_labels"] = split(mute_var.get())
        cfg["allow_labels"] = split(allow_var.get())
        tuner.save_config(cfg)

    def run(job, done_text):
        collect()
        apply_btn.config(state="disabled")
        restore_btn.config(state="disabled")

        def worker():
            try:
                job(cfg["game_dir"], lambda t: msgs.put(("log", t)))
                msgs.put(("done", done_text))
            except Exception as e:  # show any error to the user
                msgs.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    apply_btn.config(command=lambda: run(lambda d, lg: tuner.apply(d, cfg, lg),
                                         "Settings applied. You can start the game."))
    restore_btn.config(command=lambda: run(tuner.restore, "The game is back to its original state."))

    if not cfg["game_dir"]:
        write_log("Could not find the game folder automatically. Pick it with Browse.")
    write_log("The game must be closed when you press Apply.")
    pump()
    root.mainloop()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--restore", action="store_true")
    p.add_argument("--game-dir")
    p.add_argument("--config")
    args = p.parse_args()
    if args.apply or args.restore:
        return run_cli(args)
    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
