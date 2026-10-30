#!/usr/bin/env python3
"""One-button station UI: runs a backend tool configured in a JSON file.

The window shows the config's title, a big Start button and a square status panel
(plus an optional log pane). Start runs the backend with the configured arguments;
the panel follows the backend's output through the "progress" rules and ends on
PASS/FAIL by the backend's exit code. The config is re-read on every Start.

Usage:
  run_ui.py                  # config.json next to this script
  run_ui.py station.json
  run_ui.py --config station.json

Config (paths are relative to the JSON's directory; see README.md):
  {
    "title": "HVF FW programming",
    "backend": "../../tools/stflash/stflash.py",
    "args": ["--wle-fw", "wle.hex", "--wba-fw", "wba.hex"],
    "show_log": true,
    "states": {"idle": {"text": "Ready", "color": "gray"}, ...},
    "progress": [{"match": "^\\\\[INFO\\\\] \\\\[WLE\\\\]", "text": "WLE: programming...", "color": "dodger blue"}]
  }

Optional "inputs" add an IC picker ("ics") and a scanned label ("label"); the args then use the
placeholders "{ics}" (one arg per selected IC) and "{label}". Start is enabled only when every
configured input is set, and it consumes the label. See README.md.
"""

import argparse
import importlib.util
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_STATES = {
    "idle": {"text": "Ready", "color": "gray"},
    "running": {"text": "Running…", "color": "gold"},
    "pass": {"text": "PASS", "color": "green"},
    "fail": {"text": "FAIL", "color": "red"},
}

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

PANEL_SIZE = 280  # px, the status panel is square; the button is as tall

ICS_PLACEHOLDER = "{ics}"      # an arg that is exactly this expands to one arg per selected IC
LABEL_PLACEHOLDER = "{label}"  # replaced by the scanned label inside any arg
SCAN_MAX_LEN = 64


class ConfigError(Exception):
    pass


@dataclass
class Rule:
    regex: re.Pattern
    text: str
    color: str


@dataclass
class IcsInput:
    title: str
    choices: list


@dataclass
class LabelInput:
    title: str
    regex: re.Pattern


@dataclass
class Config:
    path: str
    title: str
    backend: str  # resolved
    args: list
    cwd: str
    show_log: bool = True
    states: dict = field(default_factory=dict)
    progress: list = field(default_factory=list)
    ics: IcsInput = None
    label: LabelInput = None


# ---------------------------------------------------------------------------
# Config and backend logic (no Tk)
# ---------------------------------------------------------------------------

def _state(name, value):
    if not isinstance(value, dict) or not isinstance(value.get("text", ""), str) \
            or not isinstance(value.get("color", ""), str):
        raise ConfigError(f"states.{name} must be {{\"text\": str, \"color\": str}}")
    return value


def _resolve_backend(backend, base_dir):
    if os.path.isabs(backend):
        if not os.path.isfile(backend):
            raise ConfigError(f"backend not found: {backend}")
        return backend
    local = os.path.normpath(os.path.join(base_dir, backend))
    if os.path.isfile(local):
        return local
    found = shutil.which(backend)
    if found:
        return found
    raise ConfigError(f"backend not found: {backend} (looked in {base_dir} and PATH)")


def _load_from(spec, base_dir, where):
    """The object named spec["name"] in the Python file spec["file"] (relative to the JSON)."""
    if not isinstance(spec, dict) or not all(isinstance(spec.get(k), str) and spec[k] for k in ("file", "name")):
        raise ConfigError(f"{where} must be {{\"file\": str, \"name\": str}}")
    path = os.path.normpath(os.path.join(base_dir, spec["file"]))
    if not os.path.isfile(path):
        raise ConfigError(f"{where}.file not found: {path}")
    try:
        mod_spec = importlib.util.spec_from_file_location(f"run_ui_input_{abs(hash(path))}", path)
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)
    except Exception as e:  # anything the file raises while loading
        raise ConfigError(f"{where}: cannot load {path}: {e}")
    if not hasattr(module, spec["name"]):
        raise ConfigError(f"{where}: {spec['name']} not found in {path}")
    return getattr(module, spec["name"])


def _one_of(item, key, where):
    has_value, has_from = key in item, f"{key}_from" in item
    if has_value == has_from:
        raise ConfigError(f"{where}: give exactly one of \"{key}\" and \"{key}_from\"")
    return has_from


def _parse_ics(item, base_dir):
    where = "inputs.ics"
    if not isinstance(item, dict):
        raise ConfigError(f"{where} must be an object")
    if _one_of(item, "choices", where):
        choices = _load_from(item["choices_from"], base_dir, f"{where}.choices_from")
        choices = list(choices.keys()) if isinstance(choices, dict) else choices
    else:
        choices = item["choices"]
    if not isinstance(choices, (list, tuple)) or not choices or not all(isinstance(c, str) and c for c in choices):
        raise ConfigError(f"{where}: choices must be a non-empty list of strings")
    title = item.get("label", "ICs")
    if not isinstance(title, str):
        raise ConfigError(f"{where}.label must be a string")
    return IcsInput(title, list(dict.fromkeys(choices)))


def _parse_label(item, base_dir):
    where = "inputs.label"
    if not isinstance(item, dict):
        raise ConfigError(f"{where} must be an object")
    if _one_of(item, "pattern", where):
        pattern = _load_from(item["pattern_from"], base_dir, f"{where}.pattern_from")
    else:
        pattern = item["pattern"]
    if isinstance(pattern, str):
        try:
            pattern = re.compile(pattern)
        except re.error as e:
            raise ConfigError(f"{where}: bad regex: {e}")
    if not isinstance(pattern, re.Pattern):
        raise ConfigError(f"{where}: pattern must be a regex string or a compiled regex")
    title = item.get("label", "Label")
    if not isinstance(title, str):
        raise ConfigError(f"{where}.label must be a string")
    return LabelInput(title, pattern)


def _parse_inputs(raw, args, base_dir):
    inputs = raw.get("inputs", {})
    if not isinstance(inputs, dict):
        raise ConfigError("\"inputs\" must be an object")
    unknown = set(inputs) - {"ics", "label"}
    if unknown:
        raise ConfigError(f"unknown inputs: {', '.join(sorted(unknown))} (known: ics, label)")
    ics = _parse_ics(inputs["ics"], base_dir) if "ics" in inputs else None
    label = _parse_label(inputs["label"], base_dir) if "label" in inputs else None

    for a in args:
        if ICS_PLACEHOLDER in a and a != ICS_PLACEHOLDER:
            raise ConfigError(f"\"{ICS_PLACEHOLDER}\" must be a whole arg, not part of \"{a}\"")
    for name, given, used in (("ics", ics, ICS_PLACEHOLDER in args),
                              ("label", label, any(LABEL_PLACEHOLDER in a for a in args))):
        placeholder = "{" + name + "}"
        if used and not given:
            raise ConfigError(f"args use \"{placeholder}\" but inputs.{name} is not set")
        if given and not used:
            raise ConfigError(f"inputs.{name} is set but no arg uses \"{placeholder}\"")
    return ics, label


def load_config(path):
    """Read and validate the JSON config. Raises ConfigError."""
    path = os.path.abspath(path)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e.strerror}")
    except json.JSONDecodeError as e:
        raise ConfigError(f"{os.path.basename(path)}: bad JSON at line {e.lineno} col {e.colno}: {e.msg}")
    if not isinstance(raw, dict):
        raise ConfigError(f"{os.path.basename(path)}: top level must be an object")

    for key in ("title", "backend"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise ConfigError(f"\"{key}\" is missing or not a string")
    args = raw.get("args")
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise ConfigError("\"args\" must be a list of strings")
    show_log = raw.get("show_log", True)
    if not isinstance(show_log, bool):
        raise ConfigError("\"show_log\" must be true or false")

    base_dir = os.path.dirname(path)
    cwd = raw.get("cwd", ".")
    if not isinstance(cwd, str):
        raise ConfigError("\"cwd\" must be a string")
    cwd = os.path.normpath(os.path.join(base_dir, cwd))
    if not os.path.isdir(cwd):
        raise ConfigError(f"cwd not found: {cwd}")

    states_raw = raw.get("states", {})
    if not isinstance(states_raw, dict):
        raise ConfigError("\"states\" must be an object")
    unknown = set(states_raw) - set(DEFAULT_STATES)
    if unknown:
        raise ConfigError(f"unknown states: {', '.join(sorted(unknown))} (known: {', '.join(DEFAULT_STATES)})")
    states = {name: {**default, **_state(name, states_raw.get(name, {}))} for name, default in DEFAULT_STATES.items()}

    progress_raw = raw.get("progress", [])
    if not isinstance(progress_raw, list):
        raise ConfigError("\"progress\" must be a list")
    progress = []
    for i, item in enumerate(progress_raw):
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("match", "text", "color")):
            raise ConfigError(f"progress[{i}] must be {{\"match\": str, \"text\": str, \"color\": str}}")
        try:
            regex = re.compile(item["match"])
        except re.error as e:
            raise ConfigError(f"progress[{i}].match: bad regex: {e}")
        try:  # catch stray braces / bad group numbers now, not mid-run
            item["text"].format(*[""] * (regex.groups + 1), line="")
        except (IndexError, KeyError, ValueError) as e:
            raise ConfigError(f"progress[{i}].text: bad placeholder ({e}); use {{1}}.. for groups, {{line}}, {{{{ }}}} for braces")
        progress.append(Rule(regex, item["text"], item["color"]))

    ics, label = _parse_inputs(raw, args, base_dir)

    return Config(path=path, title=raw["title"], backend=_resolve_backend(raw["backend"], base_dir),
                  args=list(args), cwd=cwd, show_log=show_log, states=states, progress=progress,
                  ics=ics, label=label)


def expand_args(cfg, ics=(), label=None):
    """cfg.args with "{ics}" expanded to one arg per IC and "{label}" replaced."""
    out = []
    for a in cfg.args:
        if a == ICS_PLACEHOLDER:
            out.extend(ics)
        else:
            out.append(a.replace(LABEL_PLACEHOLDER, label) if label is not None else a)
    return out


def check_label(cfg, text):
    """The scanned text, stripped, if it is a valid label for cfg; else None."""
    text = text.strip()
    if cfg.label is None or not text or not cfg.label.regex.fullmatch(text):
        return None
    return text


def can_start(cfg, ics, label, running):
    """Start is allowed when nothing runs and every configured input is set."""
    if cfg is None or running:
        return False
    if cfg.ics is not None and not ics:
        return False
    if cfg.label is not None and not label:
        return False
    return True


def build_command(cfg, ics=(), label=None):
    """(argv, cwd) for the backend; a .py runs with this interpreter, unbuffered."""
    if cfg.backend.lower().endswith(".py"):
        argv = [sys.executable, "-u", cfg.backend]
    else:
        argv = [cfg.backend]
    return argv + expand_args(cfg, ics, label), cfg.cwd


def match_progress(rules, line):
    """(text, color) of the first rule matching the line, else None."""
    for rule in rules:
        m = rule.regex.search(line)
        if m:
            groups = [g if g is not None else "" for g in m.groups()]
            return rule.text.format(m.group(0), *groups, line=line), rule.color
    return None


def final_state(cfg, rc):
    """(text, color) for a finished backend."""
    if rc == 0:
        return cfg.states["pass"]["text"], cfg.states["pass"]["color"]
    return f"{cfg.states['fail']['text']}\n(exit {rc})", cfg.states["fail"]["color"]


class Runner:
    """Runs the backend; posts ("line", str), then ("done", rc) or ("error", msg) to the queue."""

    def __init__(self, argv, cwd, q):
        self.argv, self.cwd, self.q = argv, cwd, q
        self.proc = None

    def start(self):
        # UTF-8 to match _read(): a Windows pipe defaults to cp1252, which cannot print the CLI's progress bar
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        # own process group, so stop() reaches the backend's children too (e.g. STM32_Programmer_CLI)
        if os.name == "nt":
            group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            group = {"start_new_session": True}
        try:
            self.proc = subprocess.Popen(self.argv, cwd=self.cwd, env=env,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **group)
        except OSError as e:
            self.q.put(("error", f"cannot start {self.argv[0]}: {e.strerror or e}"))
            return
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        with self.proc.stdout:
            for raw in self.proc.stdout:
                # progress bars redraw with \r: keep what is left on screen
                line = ANSI_RE.sub("", raw.decode(errors="replace")).rstrip("\r\n").split("\r")[-1]
                self.q.put(("line", line))
        self.q.put(("done", self.proc.wait()))

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self, timeout=3):
        """Stop the backend and every process it started, and wait until they are gone.

        Terminates the whole process group; whatever is still there after `timeout` seconds is killed.
        Stopping only the backend would leave its children running, e.g. a STM32_Programmer_CLI write."""
        if self.proc is None:
            return
        if os.name == "nt":
            # no group signals on Windows: taskkill /T kills the backend and every process it started
            if self.proc.poll() is None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.proc.wait()
            return
        import signal
        pgid = self.proc.pid  # start_new_session: the backend leads its own process group
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                break
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                self.proc.poll()  # reap the backend so it does not keep the group alive as a zombie
                if not self._group_alive(pgid):
                    break
                time.sleep(0.05)
            else:
                continue  # still there: kill
            break
        self.proc.wait()

    @staticmethod
    def _group_alive(pgid):
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


# ---------------------------------------------------------------------------
# Tk window
# ---------------------------------------------------------------------------

class RunnerApp:
    POLL_MS = 50

    def __init__(self, root, config_path):
        import tkinter as tk
        from tkinter import font, scrolledtext
        self.tk = tk
        self.root = root
        self.config_path = config_path
        self.cfg = None
        self.runner = None
        self.q = queue.Queue()
        self.ics = []          # selected ICs, kept for the session
        self.label = None      # last valid scanned label, consumed by Start
        self.scan_buf = ""
        self.dialog_open = False

        self.family = family = font.nametofont("TkDefaultFont").actual("family")
        root.minsize(2 * PANEL_SIZE + 60, PANEL_SIZE + 100)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.title = tk.Label(root, font=(family, 22, "bold"))
        self.title.pack(side="top", padx=16, pady=(16, 8))

        # optional inputs, packed by _apply_layout() when the config has them
        self.inputs = tk.Frame(root)
        self.ics_row = tk.Frame(self.inputs)
        self.ics_title = tk.Label(self.ics_row, font=(family, 14, "bold"))
        self.ics_title.pack(side="left")
        self.ics_value = tk.Label(self.ics_row, font=(family, 14), anchor="w", justify="left",
                                  wraplength=2 * PANEL_SIZE - 120)
        self.ics_value.pack(side="left", padx=8, fill="x", expand=True)
        tk.Button(self.ics_row, text="Select…", font=(family, 14), command=self.on_select_ics,
                  takefocus=False).pack(side="right")
        self.label_row = tk.Frame(self.inputs)
        self.label_title = tk.Label(self.label_row, font=(family, 14, "bold"))
        self.label_title.pack(side="left")
        self.label_value = tk.Label(self.label_row, font=(family, 28, "bold"), anchor="w")
        self.label_value.pack(side="left", padx=8, fill="x", expand=True)
        root.bind_all("<Key>", self.on_key)
        # Tab is Tk's <<NextWindow>> (focus traversal), which would swallow it; a scanner may end codes with Tab
        root.event_delete("<<NextWindow>>", "<Tab>")

        row = tk.Frame(root)
        row.pack(side="top", padx=16, pady=8)
        self.main_row = row
        btn_box = tk.Frame(row, width=PANEL_SIZE, height=PANEL_SIZE)
        btn_box.pack_propagate(False)
        btn_box.pack(side="left", padx=(0, 16))
        self.button = tk.Button(btn_box, text="Start", font=(family, 32, "bold"), command=self.on_start,
                                takefocus=False)
        self.button.pack(fill="both", expand=True)

        self.panel = tk.Frame(row, width=PANEL_SIZE, height=PANEL_SIZE, relief="sunken", borderwidth=2)
        self.panel.pack_propagate(False)
        self.panel.pack(side="left")
        self.status = tk.Label(self.panel, font=(family, 22, "bold"), wraplength=PANEL_SIZE - 24, justify="center")
        self.status.pack(fill="both", expand=True)

        self.log = scrolledtext.ScrolledText(root, height=12, state="disabled", font="TkFixedFont")

        try:
            self.cfg = self._load()
            self._apply_layout()
            self.set_status(*self._state("idle"))
        except ConfigError as e:
            self.title.config(text=os.path.basename(config_path))
            self.root.title("run_ui")
            self.set_status(f"Config error:\n{e}", "red", small=True)
        self.update_start()
        self.root.after(self.POLL_MS, self.poll)

    # -- helpers --

    def _load(self):
        cfg = load_config(self.config_path)
        colors = [s["color"] for s in cfg.states.values()] + [r.color for r in cfg.progress]
        for color in colors:
            try:
                self.root.winfo_rgb(color)
            except self.tk.TclError:
                raise ConfigError(f"unknown color: {color!r}")
        return cfg

    def _apply_layout(self):
        self.title.config(text=self.cfg.title)
        self.root.title(self.cfg.title)
        cfg = self.cfg
        if cfg.ics is not None or cfg.label is not None:
            self.inputs.pack(side="top", fill="x", padx=16, pady=4, before=self.main_row)
        else:
            self.inputs.pack_forget()
        if cfg.ics is not None:
            self.ics = [c for c in self.ics if c in cfg.ics.choices]  # choices may change on reload
            self.ics_title.config(text=cfg.ics.title + ":")
            self.ics_row.pack(side="top", fill="x", pady=2)
        else:
            self.ics_row.pack_forget()
        if cfg.label is not None:
            self.label_title.config(text=cfg.label.title + ":")
            self.label_row.pack(side="top", fill="x", pady=2)
        else:
            self.label_row.pack_forget()
        self.show_inputs()
        if self.cfg.show_log:
            self.log.pack(side="top", fill="both", expand=True, padx=16, pady=(8, 16))
        else:
            self.log.pack_forget()

    def _state(self, name):
        return self.cfg.states[name]["text"], self.cfg.states[name]["color"]

    def set_status(self, text, color, small=False):
        r, g, b = (c / 65535 for c in self.root.winfo_rgb(color))
        fg = "black" if 0.299 * r + 0.587 * g + 0.114 * b > 0.55 else "white"
        size = 12 if small or len(text) > 60 else 22
        self.panel.config(bg=color)
        self.status.config(text=text, bg=color, fg=fg, font=(self.family, size, "bold"))

    def show_inputs(self, invalid=None):
        """Refresh the IC and label displays; invalid = a rejected scan to show in red."""
        if self.ics:
            self.ics_value.config(text=", ".join(self.ics), fg="black")
        else:
            self.ics_value.config(text="none selected", fg="red")
        if invalid is not None:
            self.label_value.config(text=f"Invalid code: {invalid}", fg="red", font=(self.family, 16, "bold"))
        elif self.label:
            self.label_value.config(text=self.label, fg="black", font=(self.family, 28, "bold"))
        else:
            self.label_value.config(text="Scan label…", fg="gray", font=(self.family, 28, "bold"))

    def update_start(self):
        running = self.runner is not None and self.runner.running()
        ok = can_start(self.cfg, self.ics, self.label, running)
        self.button.config(state="normal" if ok else "disabled")

    def append_log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    # -- events --

    def on_start(self):
        if self.runner and self.runner.running():
            return
        try:
            self.cfg = self._load()
        except ConfigError as e:
            self.set_status(f"Config error:\n{e}", "red", small=True)
            return
        self._apply_layout()
        if not can_start(self.cfg, self.ics, self.label, False):
            self.update_start()
            return
        self._clear_log()
        argv, cwd = build_command(self.cfg, self.ics, self.label)
        self.label = None  # one scan per device
        self.show_inputs()
        self.append_log(f"$ {' '.join(argv)}   (in {cwd})")
        self.button.config(state="disabled")
        self.set_status(*self._state("running"))
        self.runner = Runner(argv, cwd, self.q)
        self.runner.start()

    def poll(self):
        try:
            for _ in range(500):
                kind, value = self.q.get_nowait()
                if kind == "line":
                    self.append_log(value)
                    hit = match_progress(self.cfg.progress, value)
                    if hit:
                        self.set_status(*hit)
                elif kind == "done":
                    self.append_log(f"[exit {value}]")
                    self.set_status(*final_state(self.cfg, value))
                    self.update_start()
                elif kind == "error":
                    self.append_log(value)
                    self.set_status(f"{self.cfg.states['fail']['text']}\n{value}", self.cfg.states["fail"]["color"])
                    self.runner = None
                    self.update_start()
        except queue.Empty:
            pass
        self.root.after(self.POLL_MS, self.poll)

    def on_key(self, event):
        """Keyboard-wedge scanner: printable keys build a code, Return/Enter/Tab ends it, Escape clears."""
        if self.cfg is None or self.cfg.label is None or self.dialog_open:
            return
        if event.keysym in ("Return", "KP_Enter", "Tab"):
            code, self.scan_buf = self.scan_buf, ""
            if not code.strip():
                return
            self.label = check_label(self.cfg, code)
            self.show_inputs(invalid=None if self.label else code.strip())
            self.update_start()
        elif event.keysym == "Escape":
            self.scan_buf = ""
        elif len(event.char) == 1 and event.char.isprintable():
            self.scan_buf = (self.scan_buf + event.char)[-SCAN_MAX_LEN:]

    def on_select_ics(self):
        if self.cfg is None or self.cfg.ics is None or self.dialog_open:
            return
        tk = self.tk
        dlg = tk.Toplevel(self.root)
        dlg.title(self.cfg.ics.title)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        boxes = tk.Frame(dlg)
        boxes.pack(side="top", padx=16, pady=12)
        choices = self.cfg.ics.choices
        per_col = (len(choices) + 1) // 2
        vars_ = {}
        for i, choice in enumerate(choices):
            vars_[choice] = tk.BooleanVar(value=choice in self.ics)
            tk.Checkbutton(boxes, text=choice, variable=vars_[choice], font=(self.family, 14), anchor="w") \
                .grid(row=i % per_col, column=i // per_col, sticky="w", padx=8, pady=2)

        def done(ok):
            if ok:
                self.ics = [c for c in choices if vars_[c].get()]
            self.dialog_open = False
            dlg.grab_release()
            dlg.destroy()
            self.scan_buf = ""
            self.show_inputs()
            self.update_start()

        buttons = tk.Frame(dlg)
        buttons.pack(side="top", pady=(0, 12))
        tk.Button(buttons, text="OK", width=10, font=(self.family, 14), command=lambda: done(True)).pack(side="left", padx=8)
        tk.Button(buttons, text="Cancel", width=10, font=(self.family, 14), command=lambda: done(False)).pack(side="left", padx=8)
        dlg.protocol("WM_DELETE_WINDOW", lambda: done(False))
        self.dialog_open = True
        dlg.wait_visibility()
        dlg.grab_set()

    def on_close(self):
        if self.runner and self.runner.running():
            from tkinter import messagebox
            if not messagebox.askyesno("Backend running", "The backend is still running. Stop it and quit?",
                                       icon="warning", parent=self.root):
                return
            self.runner.stop()
        self.root.destroy()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("config", nargs="?", help=f"JSON config (default: {DEFAULT_CONFIG})")
    p.add_argument("-c", "--config", dest="config_opt", metavar="CONFIG", help="JSON config, same as the positional")
    args = p.parse_args(argv)
    if args.config and args.config_opt:
        p.error("give the config either as an argument or with --config, not both")
    args.config = args.config or args.config_opt or DEFAULT_CONFIG

    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as e:
        print(f"[ERROR] cannot open a window: {e}")
        return 1
    RunnerApp(root, args.config)
    root.mainloop()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
