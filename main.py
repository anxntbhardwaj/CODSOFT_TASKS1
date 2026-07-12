#!/usr/bin/env python3
"""
=====================================================================================
  TASKFORGE  --  A Full-Featured Command Center for Your To-Do List
=====================================================================================

  Developed by  : @anxntbhardwaj
  Description   : A pure-Python, batteries-included To-Do List desktop application
                   built on Tkinter + SQLite. Zero manual setup required -- on first
                   run it auto-installs a couple of small optional helper packages
                   (tkcalendar for a real calendar widget, plyer for native desktop
                   notifications) and gracefully falls back to built-in equivalents
                   if installation isn't possible (e.g. no internet access).

  Run it with   : python main.py

  FEATURES
  --------
   - Add / Edit / Delete tasks (soft-delete with one-click Undo, Ctrl+Z)
   - Title, rich description, category, tags, priority, due date & time
   - Recurring tasks (Daily / Weekly / Monthly) that auto-regenerate on completion
   - Subtasks / checklists inside every task, with their own progress bar
   - Mark complete / incomplete, bulk complete, duplicate task
   - Powerful search (title/description/tags) + multi-filter (status, priority,
     category) + flexible sorting (due date, priority, created, alphabetical)
   - Desktop reminder notifications for tasks approaching their due time
   - Live statistics dashboard: totals, completion %, overdue count, progress bar
   - Light & Dark themes, instantly toggleable
   - CSV and plain-text export
   - Full keyboard shortcuts for a keyboard-first workflow
   - Persistent local storage via SQLite (todo_data.db, created next to this file)
   - Branded About dialog & window chrome credited to @anxntbhardwaj

=====================================================================================
"""

import os
import sys
import csv
import json
import time
import sqlite3
import subprocess
import threading
import importlib
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------------
# 0. SELF-BOOTSTRAP: make sure optional niceties are available.
#    Everything below is written so the app works perfectly even if this fails.
# ---------------------------------------------------------------------------------

APP_NAME = "TaskForge"
APP_AUTHOR = "@anxntbhardwaj"
APP_VERSION = "1.0.0"

OPTIONAL_PACKAGES = {
    "tkcalendar": "tkcalendar",   # nice calendar date-picker widget
    "plyer": "plyer",             # cross-platform native desktop notifications
}


def _ensure_optional_packages():
    """Try to import optional packages; if missing, attempt a silent pip install.
    Never raises -- the app must still run with plain fallbacks if this fails
    (e.g. offline machine, locked-down environment, etc.)."""
    for module_name, pip_name in OPTIONAL_PACKAGES.items():
        try:
            importlib.import_module(module_name)
            continue
        except ImportError:
            pass
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet",
                 "--disable-pip-version-check", "--break-system-packages", pip_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45,
            )
            importlib.import_module(module_name)
        except Exception:
            # Silent fallback -- feature will be degraded but app keeps working.
            pass


_ensure_optional_packages()

try:
    from tkcalendar import DateEntry
    HAS_TKCALENDAR = True
except Exception:
    HAS_TKCALENDAR = False

try:
    from plyer import notification as desktop_notification
    HAS_PLYER = True
except Exception:
    HAS_PLYER = False

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

# ---------------------------------------------------------------------------------
# 1. CONSTANTS
# ---------------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "todo_data.db")

PRIORITIES = ["Low", "Medium", "High", "Urgent"]
PRIORITY_ORDER = {p: i for i, p in enumerate(PRIORITIES)}
PRIORITY_COLORS = {
    "Low": "#4CAF50",
    "Medium": "#FFC107",
    "High": "#FF7043",
    "Urgent": "#E53935",
}
RECURRENCE_OPTIONS = ["None", "Daily", "Weekly", "Monthly"]
DEFAULT_CATEGORIES = ["Personal", "Work", "Shopping", "Health", "Learning", "Other"]

THEMES = {
    "Light": {
        "bg": "#f4f5f7", "panel": "#ffffff", "text": "#1c1c1e", "subtext": "#6e6e73",
        "accent": "#4361ee", "accent_hover": "#3a56d4", "border": "#e0e0e6",
        "row_alt": "#f0f1f5", "selected": "#dbe4ff", "done": "#9aa0a6",
        "entry_bg": "#ffffff", "danger": "#e53935",
    },
    "Dark": {
        "bg": "#1a1b21", "panel": "#24252c", "text": "#f1f1f4", "subtext": "#9a9ba3",
        "accent": "#6c8bff", "accent_hover": "#8aa0ff", "border": "#33343d",
        "row_alt": "#1f2027", "selected": "#333a5c", "done": "#5f6068",
        "entry_bg": "#2c2d36", "danger": "#ff6b6b",
    },
}


# ---------------------------------------------------------------------------------
# 2. DATA LAYER
# ---------------------------------------------------------------------------------

class Database:
    """All persistence lives here. Pure sqlite3 (standard library) -- no ORM."""

    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        with self.lock, self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    title         TEXT NOT NULL,
                    description   TEXT DEFAULT '',
                    category      TEXT DEFAULT 'Other',
                    tags          TEXT DEFAULT '',
                    priority      TEXT DEFAULT 'Medium',
                    due_date      TEXT DEFAULT '',
                    due_time      TEXT DEFAULT '',
                    status        TEXT DEFAULT 'Pending',
                    recurrence    TEXT DEFAULT 'None',
                    subtasks      TEXT DEFAULT '[]',
                    created_at    TEXT NOT NULL,
                    completed_at  TEXT DEFAULT '',
                    notified      INTEGER DEFAULT 0,
                    deleted       INTEGER DEFAULT 0
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

    # -- CRUD -----------------------------------------------------------------

    def add_task(self, **fields):
        fields.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        fields.setdefault("subtasks", "[]")
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        with self.lock, self.conn:
            cur = self.conn.execute(
                f"INSERT INTO tasks ({cols}) VALUES ({placeholders})",
                list(fields.values()),
            )
            return cur.lastrowid

    def update_task(self, task_id, **fields):
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        with self.lock, self.conn:
            self.conn.execute(
                f"UPDATE tasks SET {set_clause} WHERE id = ?",
                list(fields.values()) + [task_id],
            )

    def soft_delete(self, task_id):
        self.update_task(task_id, deleted=1)

    def restore(self, task_id):
        self.update_task(task_id, deleted=0)

    def hard_delete(self, task_id):
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def get_task(self, task_id):
        with self.lock:
            cur = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            return cur.fetchone()

    def all_tasks(self, include_deleted=False):
        query = "SELECT * FROM tasks"
        if not include_deleted:
            query += " WHERE deleted = 0"
        with self.lock:
            return self.conn.execute(query).fetchall()

    def distinct_categories(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT DISTINCT category FROM tasks WHERE deleted = 0"
            ).fetchall()
        cats = sorted({r["category"] for r in rows if r["category"]})
        for c in DEFAULT_CATEGORIES:
            if c not in cats:
                cats.append(c)
        return sorted(set(cats))

    def get_meta(self, key, default=None):
        with self.lock:
            row = self.conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_meta(self, key, value):
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


# ---------------------------------------------------------------------------------
# 3. TASK EDITOR DIALOG
# ---------------------------------------------------------------------------------

class TaskDialog(tk.Toplevel):
    """Add / Edit dialog. Returns the collected field dict via self.result."""

    def __init__(self, parent, app, task_row=None):
        super().__init__(parent)
        self.app = app
        self.task_row = task_row
        self.result = None
        self.subtasks = []
        if task_row is not None:
            try:
                self.subtasks = json.loads(task_row["subtasks"] or "[]")
            except Exception:
                self.subtasks = []

        self.title(("Edit Task" if task_row else "New Task") + f"  ·  {APP_NAME}")
        self.geometry("520x640")
        self.minsize(480, 560)
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)

        c = app.colors
        self.configure(bg=c["bg"])

        self._build_form()
        if task_row is not None:
            self._populate(task_row)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.bind("<Control-Return>", lambda e: self._on_save())

    # -- UI construction --------------------------------------------------

    def _build_form(self):
        c = self.app.colors
        pad = {"padx": 16, "pady": (10, 0)}

        def label(text):
            return tk.Label(self, text=text, bg=c["bg"], fg=c["subtext"],
                             font=("Segoe UI", 9, "bold"), anchor="w")

        label("TITLE *").pack(fill="x", **pad)
        self.title_var = tk.StringVar()
        tk.Entry(self, textvariable=self.title_var, font=("Segoe UI", 12),
                  bg=c["entry_bg"], fg=c["text"], insertbackground=c["text"],
                  relief="flat", highlightthickness=1,
                  highlightbackground=c["border"], highlightcolor=c["accent"]
                  ).pack(fill="x", padx=16, pady=(2, 0), ipady=6)

        label("DESCRIPTION").pack(fill="x", **pad)
        self.desc_text = tk.Text(self, height=4, font=("Segoe UI", 10), wrap="word",
                                  bg=c["entry_bg"], fg=c["text"], insertbackground=c["text"],
                                  relief="flat", highlightthickness=1,
                                  highlightbackground=c["border"], highlightcolor=c["accent"])
        self.desc_text.pack(fill="x", padx=16, pady=(2, 0))

        row = tk.Frame(self, bg=c["bg"])
        row.pack(fill="x", **pad)
        left = tk.Frame(row, bg=c["bg"])
        left.pack(side="left", fill="x", expand=True, padx=(0, 8))
        right = tk.Frame(row, bg=c["bg"])
        right.pack(side="left", fill="x", expand=True)

        tk.Label(left, text="CATEGORY", bg=c["bg"], fg=c["subtext"],
                  font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        self.category_var = tk.StringVar(value=DEFAULT_CATEGORIES[0])
        ttk.Combobox(left, textvariable=self.category_var,
                      values=self.app.db.distinct_categories(),
                      font=("Segoe UI", 10)).pack(fill="x", pady=(2, 0))

        tk.Label(right, text="PRIORITY", bg=c["bg"], fg=c["subtext"],
                  font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        self.priority_var = tk.StringVar(value="Medium")
        ttk.Combobox(right, textvariable=self.priority_var, values=PRIORITIES,
                      state="readonly", font=("Segoe UI", 10)).pack(fill="x", pady=(2, 0))

        row2 = tk.Frame(self, bg=c["bg"])
        row2.pack(fill="x", **pad)
        left2 = tk.Frame(row2, bg=c["bg"])
        left2.pack(side="left", fill="x", expand=True, padx=(0, 8))
        right2 = tk.Frame(row2, bg=c["bg"])
        right2.pack(side="left", fill="x", expand=True)

        tk.Label(left2, text="DUE DATE", bg=c["bg"], fg=c["subtext"],
                  font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        if HAS_TKCALENDAR:
            self.date_entry = DateEntry(left2, date_pattern="yyyy-mm-dd",
                                          font=("Segoe UI", 10))
            self.date_entry.pack(fill="x", pady=(2, 0), ipady=3)
        else:
            self.date_var = tk.StringVar()
            tk.Entry(left2, textvariable=self.date_var, font=("Segoe UI", 10),
                      bg=c["entry_bg"], fg=c["text"], relief="flat",
                      highlightthickness=1, highlightbackground=c["border"]
                      ).pack(fill="x", pady=(2, 0), ipady=4)
            tk.Label(left2, text="format: YYYY-MM-DD (leave blank for none)",
                      bg=c["bg"], fg=c["subtext"], font=("Segoe UI", 7)).pack(fill="x")

        tk.Label(right2, text="DUE TIME (HH:MM, optional)", bg=c["bg"], fg=c["subtext"],
                  font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        self.time_var = tk.StringVar()
        tk.Entry(right2, textvariable=self.time_var, font=("Segoe UI", 10),
                  bg=c["entry_bg"], fg=c["text"], relief="flat",
                  highlightthickness=1, highlightbackground=c["border"]
                  ).pack(fill="x", pady=(2, 0), ipady=4)

        row3 = tk.Frame(self, bg=c["bg"])
        row3.pack(fill="x", **pad)
        left3 = tk.Frame(row3, bg=c["bg"])
        left3.pack(side="left", fill="x", expand=True, padx=(0, 8))
        right3 = tk.Frame(row3, bg=c["bg"])
        right3.pack(side="left", fill="x", expand=True)

        tk.Label(left3, text="TAGS (comma separated)", bg=c["bg"], fg=c["subtext"],
                  font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        self.tags_var = tk.StringVar()
        tk.Entry(left3, textvariable=self.tags_var, font=("Segoe UI", 10),
                  bg=c["entry_bg"], fg=c["text"], relief="flat",
                  highlightthickness=1, highlightbackground=c["border"]
                  ).pack(fill="x", pady=(2, 0), ipady=4)

        tk.Label(right3, text="REPEAT", bg=c["bg"], fg=c["subtext"],
                  font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        self.recur_var = tk.StringVar(value="None")
        ttk.Combobox(right3, textvariable=self.recur_var, values=RECURRENCE_OPTIONS,
                      state="readonly", font=("Segoe UI", 10)).pack(fill="x", pady=(2, 0))

        # -- Subtasks / checklist --
        tk.Label(self, text="SUBTASKS / CHECKLIST", bg=c["bg"], fg=c["subtext"],
                  font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=16, pady=(14, 0))

        sub_frame = tk.Frame(self, bg=c["bg"])
        sub_frame.pack(fill="both", expand=True, padx=16, pady=(4, 0))

        self.subtask_listbox = tk.Listbox(sub_frame, font=("Segoe UI", 10),
                                            bg=c["entry_bg"], fg=c["text"],
                                            relief="flat", highlightthickness=1,
                                            highlightbackground=c["border"],
                                            selectbackground=c["selected"], height=5)
        self.subtask_listbox.pack(side="left", fill="both", expand=True)
        self._refresh_subtask_listbox()

        sub_btns = tk.Frame(sub_frame, bg=c["bg"])
        sub_btns.pack(side="left", fill="y", padx=(6, 0))
        self._mini_btn(sub_btns, "Toggle", self._toggle_subtask).pack(fill="x", pady=1)
        self._mini_btn(sub_btns, "Remove", self._remove_subtask).pack(fill="x", pady=1)

        add_sub_frame = tk.Frame(self, bg=c["bg"])
        add_sub_frame.pack(fill="x", padx=16, pady=(6, 0))
        self.new_subtask_var = tk.StringVar()
        entry = tk.Entry(add_sub_frame, textvariable=self.new_subtask_var,
                          font=("Segoe UI", 10), bg=c["entry_bg"], fg=c["text"],
                          relief="flat", highlightthickness=1,
                          highlightbackground=c["border"])
        entry.pack(side="left", fill="x", expand=True, ipady=4)
        entry.bind("<Return>", lambda e: self._add_subtask())
        self._mini_btn(add_sub_frame, "+ Add", self._add_subtask, primary=True
                        ).pack(side="left", padx=(6, 0))

        # -- Action buttons --
        btn_frame = tk.Frame(self, bg=c["bg"])
        btn_frame.pack(fill="x", padx=16, pady=16)
        tk.Button(btn_frame, text="Cancel", command=self._on_cancel,
                   bg=c["bg"], fg=c["text"], relief="flat", font=("Segoe UI", 10),
                   activebackground=c["row_alt"], bd=0, padx=14, pady=8
                   ).pack(side="right")
        tk.Button(btn_frame, text="Save Task  (Ctrl+Enter)", command=self._on_save,
                   bg=c["accent"], fg="white", relief="flat", font=("Segoe UI", 10, "bold"),
                   activebackground=c["accent_hover"], activeforeground="white",
                   bd=0, padx=14, pady=8, cursor="hand2"
                   ).pack(side="right", padx=(0, 8))

    def _mini_btn(self, parent, text, cmd, primary=False):
        c = self.app.colors
        bg = c["accent"] if primary else c["panel"]
        fg = "white" if primary else c["text"]
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                          relief="flat", font=("Segoe UI", 9), bd=0,
                          padx=8, pady=4, cursor="hand2",
                          highlightthickness=1, highlightbackground=c["border"])

    # -- Subtask helpers ----------------------------------------------------

    def _refresh_subtask_listbox(self):
        self.subtask_listbox.delete(0, tk.END)
        for st in self.subtasks:
            mark = "[x]" if st.get("done") else "[ ]"
            self.subtask_listbox.insert(tk.END, f"{mark} {st.get('text', '')}")

    def _add_subtask(self):
        text = self.new_subtask_var.get().strip()
        if not text:
            return
        self.subtasks.append({"text": text, "done": False})
        self.new_subtask_var.set("")
        self._refresh_subtask_listbox()

    def _toggle_subtask(self):
        sel = self.subtask_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.subtasks[idx]["done"] = not self.subtasks[idx]["done"]
        self._refresh_subtask_listbox()

    def _remove_subtask(self):
        sel = self.subtask_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        del self.subtasks[idx]
        self._refresh_subtask_listbox()

    # -- Populate for edit mode ----------------------------------------------

    def _populate(self, row):
        self.title_var.set(row["title"])
        self.desc_text.insert("1.0", row["description"] or "")
        self.category_var.set(row["category"] or DEFAULT_CATEGORIES[0])
        self.priority_var.set(row["priority"] or "Medium")
        self.tags_var.set(row["tags"] or "")
        self.recur_var.set(row["recurrence"] or "None")
        self.time_var.set(row["due_time"] or "")
        if row["due_date"]:
            if HAS_TKCALENDAR:
                try:
                    self.date_entry.set_date(row["due_date"])
                except Exception:
                    pass
            else:
                self.date_var.set(row["due_date"])

    # -- Save / Cancel --------------------------------------------------------

    def _on_save(self):
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("Missing title", "Please enter a task title.",
                                     parent=self)
            return

        if HAS_TKCALENDAR:
            try:
                due_date = self.date_entry.get_date().strftime("%Y-%m-%d")
            except Exception:
                due_date = ""
        else:
            due_date = self.date_var.get().strip()
            if due_date:
                try:
                    datetime.strptime(due_date, "%Y-%m-%d")
                except ValueError:
                    messagebox.showwarning(
                        "Invalid date", "Please use the format YYYY-MM-DD.",
                        parent=self)
                    return

        due_time = self.time_var.get().strip()
        if due_time:
            try:
                datetime.strptime(due_time, "%H:%M")
            except ValueError:
                messagebox.showwarning(
                    "Invalid time", "Please use 24-hour format HH:MM.",
                    parent=self)
                return

        self.result = {
            "title": title,
            "description": self.desc_text.get("1.0", "end").strip(),
            "category": self.category_var.get().strip() or "Other",
            "priority": self.priority_var.get(),
            "due_date": due_date,
            "due_time": due_time,
            "tags": ", ".join(t.strip() for t in self.tags_var.get().split(",") if t.strip()),
            "recurrence": self.recur_var.get(),
            "subtasks": json.dumps(self.subtasks),
            "notified": 0,
        }
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


# ---------------------------------------------------------------------------------
# 4. MAIN APPLICATION
# ---------------------------------------------------------------------------------

class TaskForgeApp:
    def __init__(self, root):
        self.root = root
        self.db = Database()
        self.theme_name = self.db.get_meta("theme", "Light")
        self.colors = THEMES[self.theme_name]

        self.deleted_stack = []          # for Undo
        self.current_filter_status = "All"
        self.current_filter_priority = "All"
        self.current_filter_category = "All"
        self.sort_mode = "Due Date"
        self.search_query = ""
        self.id_map = {}                 # treeview item id -> task id

        self._configure_root()
        self._build_menu()
        self._build_layout()
        self._apply_theme()
        self.refresh()

        self._start_reminder_thread()
        self._process_recurring_on_launch()

    # -- Root window ------------------------------------------------------

    def _configure_root(self):
        self.root.title(f"{APP_NAME}  —  To-Do List Manager  ·  by {APP_AUTHOR}")
        self.root.geometry("1180x720")
        self.root.minsize(980, 600)
        try:
            self.root.tk.call("tk", "scaling", 1.2)
        except Exception:
            pass

    # -- Menu bar -----------------------------------------------------------

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Task...        Ctrl+N", command=self.new_task)
        file_menu.add_separator()
        file_menu.add_command(label="Export to CSV...", command=self.export_csv)
        file_menu.add_command(label="Export to Text...", command=self.export_txt)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Undo Delete       Ctrl+Z", command=self.undo_delete)
        edit_menu.add_command(label="Find/Search       Ctrl+F", command=self.focus_search)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Toggle Theme (Light/Dark)", command=self.toggle_theme)
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.show_shortcuts)
        help_menu.add_command(label=f"About {APP_NAME}", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

        self.root.bind("<Control-n>", lambda e: self.new_task())
        self.root.bind("<Control-N>", lambda e: self.new_task())
        self.root.bind("<Control-z>", lambda e: self.undo_delete())
        self.root.bind("<Control-Z>", lambda e: self.undo_delete())
        self.root.bind("<Control-f>", lambda e: self.focus_search())
        self.root.bind("<Control-F>", lambda e: self.focus_search())
        self.root.bind("<Delete>", lambda e: self.delete_selected())

    # -- Layout ---------------------------------------------------------------

    def _build_layout(self):
        c = self.colors
        self.outer = tk.Frame(self.root, bg=c["bg"])
        self.outer.pack(fill="both", expand=True)

        # ---- Header ----
        self.header = tk.Frame(self.outer, bg=c["bg"])
        self.header.pack(fill="x", padx=20, pady=(16, 8))

        self.title_label = tk.Label(
            self.header, text=f"📋 {APP_NAME}", font=("Segoe UI", 20, "bold"),
            bg=c["bg"], fg=c["text"])
        self.title_label.pack(side="left")

        self.brand_label = tk.Label(
            self.header, text=f"developed by {APP_AUTHOR}", font=("Segoe UI", 9, "italic"),
            bg=c["bg"], fg=c["subtext"])
        self.brand_label.pack(side="left", padx=(10, 0), pady=(8, 0))

        self.new_task_btn = tk.Button(
            self.header, text="＋ New Task", command=self.new_task,
            font=("Segoe UI", 10, "bold"), relief="flat", bd=0, cursor="hand2",
            padx=16, pady=8)
        self.new_task_btn.pack(side="right")

        self.theme_btn = tk.Button(
            self.header, text="🌙" if self.theme_name == "Light" else "☀",
            command=self.toggle_theme, font=("Segoe UI", 12), relief="flat",
            bd=0, cursor="hand2", padx=10, pady=6)
        self.theme_btn.pack(side="right", padx=(0, 10))

        # ---- Stats bar ----
        self.stats_frame = tk.Frame(self.outer, bg=c["panel"])
        self.stats_frame.pack(fill="x", padx=20, pady=(0, 10))
        self.stats_label = tk.Label(self.stats_frame, text="", font=("Segoe UI", 10),
                                      bg=c["panel"], fg=c["text"], anchor="w", justify="left")
        self.stats_label.pack(side="left", padx=14, pady=10)

        self.progress = ttk.Progressbar(self.stats_frame, orient="horizontal",
                                          mode="determinate", length=220)
        self.progress.pack(side="right", padx=14, pady=10)

        # ---- Body: sidebar + task list ----
        self.body = tk.Frame(self.outer, bg=c["bg"])
        self.body.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        self._build_sidebar()
        self._build_task_list()

    def _build_sidebar(self):
        c = self.colors
        self.sidebar = tk.Frame(self.body, bg=c["panel"], width=230)
        self.sidebar.pack(side="left", fill="y", padx=(0, 14))
        self.sidebar.pack_propagate(False)

        def section_label(text):
            return tk.Label(self.sidebar, text=text, font=("Segoe UI", 9, "bold"),
                              bg=c["panel"], fg=c["subtext"], anchor="w")

        pad = {"padx": 14, "pady": (14, 2)}

        section_label("SEARCH").pack(fill="x", **pad)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._on_search_change())
        self.search_entry = tk.Entry(self.sidebar, textvariable=self.search_var,
                                       font=("Segoe UI", 10), bg=c["entry_bg"], fg=c["text"],
                                       relief="flat", highlightthickness=1,
                                       highlightbackground=c["border"])
        self.search_entry.pack(fill="x", padx=14, ipady=5)

        section_label("STATUS").pack(fill="x", **pad)
        self.status_var = tk.StringVar(value="All")
        for val in ["All", "Pending", "Completed", "Overdue"]:
            tk.Radiobutton(self.sidebar, text=val, variable=self.status_var, value=val,
                             command=self._on_filter_change, bg=c["panel"], fg=c["text"],
                             selectcolor=c["panel"], activebackground=c["panel"],
                             font=("Segoe UI", 10), anchor="w"
                             ).pack(fill="x", padx=14)

        section_label("PRIORITY").pack(fill="x", **pad)
        self.priority_filter_var = tk.StringVar(value="All")
        vals = ["All"] + PRIORITIES
        ttk.Combobox(self.sidebar, textvariable=self.priority_filter_var, values=vals,
                      state="readonly", font=("Segoe UI", 10)
                      ).pack(fill="x", padx=14)
        self.priority_filter_var.trace_add("write", lambda *a: self._on_filter_change())

        section_label("CATEGORY").pack(fill="x", **pad)
        self.category_filter_var = tk.StringVar(value="All")
        self.category_combo = ttk.Combobox(self.sidebar, textvariable=self.category_filter_var,
                                             values=["All"] + self.db.distinct_categories(),
                                             state="readonly", font=("Segoe UI", 10))
        self.category_combo.pack(fill="x", padx=14)
        self.category_filter_var.trace_add("write", lambda *a: self._on_filter_change())

        section_label("SORT BY").pack(fill="x", **pad)
        self.sort_var = tk.StringVar(value="Due Date")
        ttk.Combobox(self.sidebar, textvariable=self.sort_var,
                      values=["Due Date", "Priority", "Created", "Alphabetical"],
                      state="readonly", font=("Segoe UI", 10)
                      ).pack(fill="x", padx=14, pady=(0, 14))
        self.sort_var.trace_add("write", lambda *a: self._on_filter_change())

        tk.Frame(self.sidebar, bg=c["border"], height=1).pack(fill="x", padx=14, pady=8)

        section_label("QUICK ACTIONS").pack(fill="x", **pad)
        self._sidebar_btn("✔ Mark Complete", self.mark_complete_selected).pack(
            fill="x", padx=14, pady=3)
        self._sidebar_btn("⧉ Duplicate", self.duplicate_selected).pack(
            fill="x", padx=14, pady=3)
        self._sidebar_btn("🗑 Delete", self.delete_selected).pack(
            fill="x", padx=14, pady=3)
        self._sidebar_btn("↺ Undo Delete", self.undo_delete).pack(
            fill="x", padx=14, pady=3)

    def _sidebar_btn(self, text, cmd):
        c = self.colors
        return tk.Button(self.sidebar, text=text, command=cmd, bg=c["panel"], fg=c["text"],
                           relief="flat", bd=0, anchor="w", font=("Segoe UI", 10),
                           activebackground=c["row_alt"], cursor="hand2", padx=6, pady=6)

    def _build_task_list(self):
        c = self.colors
        self.list_frame = tk.Frame(self.body, bg=c["panel"])
        self.list_frame.pack(side="left", fill="both", expand=True)

        columns = ("status", "title", "priority", "due", "category", "tags")
        self.tree = ttk.Treeview(self.list_frame, columns=columns, show="headings",
                                   selectmode="extended")
        self.tree.heading("status", text="✓")
        self.tree.heading("title", text="Task")
        self.tree.heading("priority", text="Priority")
        self.tree.heading("due", text="Due")
        self.tree.heading("category", text="Category")
        self.tree.heading("tags", text="Tags")

        self.tree.column("status", width=36, anchor="center", stretch=False)
        self.tree.column("title", width=340, anchor="w")
        self.tree.column("priority", width=90, anchor="center", stretch=False)
        self.tree.column("due", width=140, anchor="center", stretch=False)
        self.tree.column("category", width=120, anchor="center", stretch=False)
        self.tree.column("tags", width=160, anchor="w")

        vsb = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.tree.bind("<space>", lambda e: self.mark_complete_selected())
        self.tree.bind("<Button-3>", self._show_context_menu)     # Windows/Linux
        self.tree.bind("<Button-2>", self._show_context_menu)     # macOS

        for p, color in PRIORITY_COLORS.items():
            self.tree.tag_configure(f"pri_{p}", foreground=color)
        self.tree.tag_configure("done", foreground=c["done"])
        self.tree.tag_configure("overdue", background="#ffe1e1" if self.theme_name == "Light" else "#3a1f1f")

        self._context_menu = tk.Menu(self.root, tearoff=0)
        self._context_menu.add_command(label="Edit", command=self.edit_selected)
        self._context_menu.add_command(label="Mark Complete/Incomplete",
                                         command=self.mark_complete_selected)
        self._context_menu.add_command(label="Duplicate", command=self.duplicate_selected)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Delete", command=self.delete_selected)

    # -- Theme --------------------------------------------------------------

    def toggle_theme(self):
        self.theme_name = "Dark" if self.theme_name == "Light" else "Light"
        self.colors = THEMES[self.theme_name]
        self.db.set_meta("theme", self.theme_name)
        self._apply_theme()
        self.refresh()

    def _apply_theme(self):
        c = self.colors
        self.root.configure(bg=c["bg"])
        self.outer.configure(bg=c["bg"])
        self.header.configure(bg=c["bg"])
        self.title_label.configure(bg=c["bg"], fg=c["text"])
        self.brand_label.configure(bg=c["bg"], fg=c["subtext"])
        self.new_task_btn.configure(bg=c["accent"], fg="white",
                                      activebackground=c["accent_hover"], activeforeground="white")
        self.theme_btn.configure(bg=c["bg"], fg=c["text"],
                                   text="🌙" if self.theme_name == "Light" else "☀")
        self.stats_frame.configure(bg=c["panel"])
        self.stats_label.configure(bg=c["panel"], fg=c["text"])
        self.body.configure(bg=c["bg"])
        self.sidebar.configure(bg=c["panel"])
        for w in self.sidebar.winfo_children():
            try:
                w.configure(bg=c["panel"])
            except Exception:
                pass
        self.search_entry.configure(bg=c["entry_bg"], fg=c["text"],
                                      highlightbackground=c["border"])
        self.list_frame.configure(bg=c["panel"])

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview", background=c["panel"], fieldbackground=c["panel"],
                          foreground=c["text"], rowheight=28, borderwidth=0,
                          font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=c["row_alt"], foreground=c["text"],
                          font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", c["selected"])])
        style.configure("TCombobox", fieldbackground=c["entry_bg"], background=c["entry_bg"],
                          foreground=c["text"])
        style.configure("TProgressbar", troughcolor=c["row_alt"], background=c["accent"])

        self.tree.tag_configure("done", foreground=c["done"])
        self.tree.tag_configure("overdue",
                                  background="#ffe1e1" if self.theme_name == "Light" else "#3a1f1f")

    # -- Data refresh / filtering ---------------------------------------------

    def _on_search_change(self):
        self.search_query = self.search_var.get().strip().lower()
        self.refresh()

    def _on_filter_change(self):
        self.current_filter_priority = self.priority_filter_var.get()
        self.current_filter_category = self.category_filter_var.get()
        self.sort_mode = self.sort_var.get()
        self.refresh()

    def _get_status_filter(self):
        return self.status_var.get() if hasattr(self, "status_var") else "All"

    def focus_search(self):
        self.search_entry.focus_set()

    def _filtered_sorted_tasks(self):
        rows = self.db.all_tasks()
        now = datetime.now()
        results = []
        status_filter = self._get_status_filter()

        for r in rows:
            if self.search_query:
                haystack = f"{r['title']} {r['description']} {r['tags']}".lower()
                if self.search_query not in haystack:
                    continue
            if self.current_filter_priority != "All" and r["priority"] != self.current_filter_priority:
                continue
            if self.current_filter_category != "All" and r["category"] != self.current_filter_category:
                continue

            is_done = r["status"] == "Completed"
            is_overdue = False
            if not is_done and r["due_date"]:
                try:
                    due_dt = datetime.strptime(
                        r["due_date"] + (" " + r["due_time"] if r["due_time"] else " 23:59"),
                        "%Y-%m-%d %H:%M")
                    is_overdue = due_dt < now
                except ValueError:
                    pass

            if status_filter == "Pending" and is_done:
                continue
            if status_filter == "Completed" and not is_done:
                continue
            if status_filter == "Overdue" and not is_overdue:
                continue

            results.append((r, is_overdue))

        def sort_key(item):
            r, _ = item
            if self.sort_mode == "Priority":
                return -PRIORITY_ORDER.get(r["priority"], 0)
            if self.sort_mode == "Created":
                return r["created_at"]
            if self.sort_mode == "Alphabetical":
                return r["title"].lower()
            # Due Date default: blanks last
            return (r["due_date"] or "9999-99-99") + (r["due_time"] or "99:99")

        results.sort(key=sort_key)
        return results

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.id_map.clear()

        rows = self._filtered_sorted_tasks()
        for r, is_overdue in rows:
            check = "✔" if r["status"] == "Completed" else "☐"
            due_str = r["due_date"] or "—"
            if r["due_time"]:
                due_str += f"  {r['due_time']}"
            subtasks = []
            try:
                subtasks = json.loads(r["subtasks"] or "[]")
            except Exception:
                pass
            title_display = r["title"]
            if subtasks:
                done_n = sum(1 for s in subtasks if s.get("done"))
                title_display += f"   ({done_n}/{len(subtasks)} subtasks)"
            if r["recurrence"] and r["recurrence"] != "None":
                title_display += f"  ↻{r['recurrence'][0]}"

            tags = []
            if r["status"] == "Completed":
                tags.append("done")
            else:
                tags.append(f"pri_{r['priority']}")
            if is_overdue:
                tags.append("overdue")

            item_id = self.tree.insert("", "end", values=(
                check, title_display, r["priority"], due_str, r["category"], r["tags"]
            ), tags=tuple(tags))
            self.id_map[item_id] = r["id"]

        # refresh category filter list in case new categories appeared
        try:
            current = self.category_filter_var.get()
            self.category_combo["values"] = ["All"] + self.db.distinct_categories()
            self.category_filter_var.set(current)
        except Exception:
            pass

        self._update_stats()

    def _update_stats(self):
        all_rows = self.db.all_tasks()
        total = len(all_rows)
        completed = sum(1 for r in all_rows if r["status"] == "Completed")
        pending = total - completed
        now = datetime.now()
        overdue = 0
        for r in all_rows:
            if r["status"] != "Completed" and r["due_date"]:
                try:
                    due_dt = datetime.strptime(
                        r["due_date"] + (" " + r["due_time"] if r["due_time"] else " 23:59"),
                        "%Y-%m-%d %H:%M")
                    if due_dt < now:
                        overdue += 1
                except ValueError:
                    pass
        pct = int((completed / total) * 100) if total else 0
        self.stats_label.configure(
            text=(f"📊  Total: {total}    Pending: {pending}    "
                  f"Completed: {completed}    Overdue: {overdue}    "
                  f"({pct}% done)"))
        self.progress["value"] = pct

    # -- Selection helpers ----------------------------------------------------

    def _selected_task_ids(self):
        return [self.id_map[i] for i in self.tree.selection() if i in self.id_map]

    def _show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            if item not in self.tree.selection():
                self.tree.selection_set(item)
            self._context_menu.tk_popup(event.x_root, event.y_root)

    # -- Task actions -----------------------------------------------------------

    def new_task(self):
        dlg = TaskDialog(self.root, self)
        self.root.wait_window(dlg)
        if dlg.result:
            dlg.result["status"] = "Pending"
            self.db.add_task(**dlg.result)
            self.refresh()

    def edit_selected(self):
        ids = self._selected_task_ids()
        if not ids:
            messagebox.showinfo(APP_NAME, "Select a task to edit first.")
            return
        row = self.db.get_task(ids[0])
        if row is None:
            return
        dlg = TaskDialog(self.root, self, task_row=row)
        self.root.wait_window(dlg)
        if dlg.result:
            self.db.update_task(ids[0], **dlg.result)
            self.refresh()

    def mark_complete_selected(self):
        ids = self._selected_task_ids()
        if not ids:
            return
        for tid in ids:
            row = self.db.get_task(tid)
            if row is None:
                continue
            if row["status"] == "Completed":
                self.db.update_task(tid, status="Pending", completed_at="")
            else:
                self.db.update_task(
                    tid, status="Completed",
                    completed_at=datetime.now().isoformat(timespec="seconds"))
                self._spawn_recurring_if_needed(row)
        self.refresh()

    def duplicate_selected(self):
        ids = self._selected_task_ids()
        for tid in ids:
            row = self.db.get_task(tid)
            if row is None:
                continue
            data = {k: row[k] for k in row.keys() if k not in ("id",)}
            data["title"] = data["title"] + " (copy)"
            data["status"] = "Pending"
            data["completed_at"] = ""
            data["notified"] = 0
            data["created_at"] = datetime.now().isoformat(timespec="seconds")
            self.db.add_task(**data)
        self.refresh()

    def delete_selected(self):
        ids = self._selected_task_ids()
        if not ids:
            return
        if not messagebox.askyesno(
                "Delete task(s)",
                f"Delete {len(ids)} task(s)? You can undo with Ctrl+Z.",
        ):
            return
        for tid in ids:
            self.db.soft_delete(tid)
            self.deleted_stack.append(tid)
        self.refresh()

    def undo_delete(self):
        if not self.deleted_stack:
            messagebox.showinfo(APP_NAME, "Nothing to undo.")
            return
        tid = self.deleted_stack.pop()
        self.db.restore(tid)
        self.refresh()

    # -- Recurrence -------------------------------------------------------------

    def _spawn_recurring_if_needed(self, row):
        recurrence = row["recurrence"]
        if not recurrence or recurrence == "None" or not row["due_date"]:
            return
        try:
            base = datetime.strptime(row["due_date"], "%Y-%m-%d")
        except ValueError:
            return
        if recurrence == "Daily":
            next_date = base + timedelta(days=1)
        elif recurrence == "Weekly":
            next_date = base + timedelta(weeks=1)
        elif recurrence == "Monthly":
            month = base.month % 12 + 1
            year = base.year + (1 if base.month == 12 else 0)
            day = min(base.day, 28)
            next_date = base.replace(year=year, month=month, day=day)
        else:
            return

        self.db.add_task(
            title=row["title"], description=row["description"],
            category=row["category"], tags=row["tags"], priority=row["priority"],
            due_date=next_date.strftime("%Y-%m-%d"), due_time=row["due_time"],
            status="Pending", recurrence=recurrence, subtasks=row["subtasks"],
            notified=0,
        )

    def _process_recurring_on_launch(self):
        # No-op placeholder hook -- recurrence is generated at completion time,
        # kept here for clarity/extensibility (e.g. future "regenerate overdue
        # recurring tasks automatically" behavior).
        pass

    # -- Reminders / notifications ------------------------------------------------

    def _start_reminder_thread(self):
        t = threading.Thread(target=self._reminder_loop, daemon=True)
        t.start()

    def _reminder_loop(self):
        while True:
            try:
                self._check_due_reminders()
            except Exception:
                pass
            time.sleep(30)

    def _check_due_reminders(self):
        now = datetime.now()
        window_end = now + timedelta(minutes=15)
        rows = self.db.all_tasks()
        for r in rows:
            if r["status"] == "Completed" or not r["due_date"] or r["notified"]:
                continue
            try:
                due_dt = datetime.strptime(
                    r["due_date"] + (" " + r["due_time"] if r["due_time"] else " 09:00"),
                    "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if now <= due_dt <= window_end:
                self._notify(r)
                self.db.update_task(r["id"], notified=1)

    def _notify(self, row):
        title = f"⏰ Task due soon — {APP_NAME}"
        message = f"{row['title']}  (due {row['due_date']} {row['due_time']})"
        if HAS_PLYER:
            try:
                desktop_notification.notify(
                    title=title, message=message, app_name=APP_NAME, timeout=10)
                return
            except Exception:
                pass
        # Fallback: schedule a Tk messagebox on the main thread.
        try:
            self.root.after(0, lambda: messagebox.showinfo(title, message))
        except Exception:
            pass

    # -- Export ------------------------------------------------------------------

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV file", "*.csv")],
            initialfile="taskforge_export.csv")
        if not path:
            return
        rows = self.db.all_tasks()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Title", "Description", "Category", "Priority",
                              "Due Date", "Due Time", "Status", "Tags", "Recurrence"])
            for r in rows:
                writer.writerow([r["title"], r["description"], r["category"],
                                  r["priority"], r["due_date"], r["due_time"],
                                  r["status"], r["tags"], r["recurrence"]])
        messagebox.showinfo(APP_NAME, f"Exported {len(rows)} tasks to:\n{path}")

    def export_txt(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text file", "*.txt")],
            initialfile="taskforge_export.txt")
        if not path:
            return
        rows = self.db.all_tasks()
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{APP_NAME} — Task Export\nGenerated by {APP_AUTHOR}\n")
            f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write("=" * 60 + "\n\n")
            for r in rows:
                mark = "[x]" if r["status"] == "Completed" else "[ ]"
                f.write(f"{mark} {r['title']}  (priority: {r['priority']})\n")
                if r["due_date"]:
                    f.write(f"    due: {r['due_date']} {r['due_time']}\n")
                if r["description"]:
                    f.write(f"    notes: {r['description']}\n")
                f.write("\n")
        messagebox.showinfo(APP_NAME, f"Exported {len(rows)} tasks to:\n{path}")

    # -- Help dialogs --------------------------------------------------------------

    def show_shortcuts(self):
        text = (
            "Ctrl+N        New task\n"
            "Ctrl+F        Focus search\n"
            "Ctrl+Z        Undo last delete\n"
            "Delete        Delete selected task(s)\n"
            "Space         Toggle complete on selection\n"
            "Double-click  Edit task\n"
            "Right-click   Context menu\n"
            "Ctrl+Enter    Save task (inside the editor)\n"
            "Esc           Close the editor\n"
        )
        messagebox.showinfo("Keyboard Shortcuts", text)

    def show_about(self):
        text = (
            f"{APP_NAME}  v{APP_VERSION}\n\n"
            f"A full-featured To-Do List manager built with pure Python\n"
            f"(Tkinter + SQLite).\n\n"
            f"Developed by {APP_AUTHOR}\n\n"
            f"Calendar widget: {'enabled' if HAS_TKCALENDAR else 'fallback text entry'}\n"
            f"Desktop notifications: {'enabled' if HAS_PLYER else 'fallback popup'}\n"
        )
        messagebox.showinfo(f"About {APP_NAME}", text)


# ---------------------------------------------------------------------------------
# 5. ENTRY POINT
# ---------------------------------------------------------------------------------

def main():
    root = tk.Tk()
    TaskForgeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
