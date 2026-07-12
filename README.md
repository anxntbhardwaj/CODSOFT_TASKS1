# 📋 TaskForge — A Full-Featured To-Do List App

**Developed by [@anxntbhardwaj](https://github.com/anxntbhardwaj)**

A pure-Python, single-file, desktop To-Do List application built entirely with
Tkinter (GUI) and SQLite (storage) from the standard library. It self-installs
a couple of optional helper packages the first time you run it, so setup is
just one command.

---

## ✨ Features

| Category | Details |
|---|---|
| **Task fields** | Title, description, category, tags, priority, due date, due time |
| **Organization** | Search, filter by status/priority/category, sort by due date/priority/created/alphabetical |
| **Subtasks** | Add a checklist inside any task; progress shown inline (`3/5 subtasks`) |
| **Recurrence** | Daily / Weekly / Monthly tasks auto-regenerate when completed |
| **Reminders** | Native desktop notifications ~15 minutes before a task is due |
| **Bulk actions** | Multi-select, mark complete, duplicate, delete |
| **Safety net** | Soft-delete with one-click **Undo** (`Ctrl+Z`) |
| **Dashboard** | Live stats bar: total / pending / completed / overdue + progress bar |
| **Themes** | Light and Dark mode, toggle anytime |
| **Export** | CSV and plain-text export of your full task list |
| **Keyboard-first** | Shortcuts for nearly every action (see below) |
| **Storage** | Local SQLite database (`todo_data.db`), created automatically next to the script — no server, no account, fully offline-capable |

## 🚀 Getting Started

Requires **Python 3.8+** with Tkinter (bundled with most Python installs;
on Debian/Ubuntu you may need `sudo apt install python3-tk`).

```bash
python main.py
```

That's it. On first launch the app tries to silently install two small
optional packages (`tkcalendar` for a calendar picker and `plyer` for native
notifications). If you're offline or installation isn't possible, the app
detects this automatically and falls back to plain text-entry dates and
in-app popup reminders — every core feature still works.

Prefer to install dependencies yourself first?

```bash
pip install -r requirements.txt
python main.py
```

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N` | New task |
| `Ctrl+F` | Focus search box |
| `Ctrl+Z` | Undo last delete |
| `Delete` | Delete selected task(s) |
| `Space` | Toggle complete on selected task(s) |
| Double-click a row | Edit that task |
| Right-click a row | Context menu (edit / complete / duplicate / delete) |
| `Ctrl+Enter` | Save task (inside the editor window) |
| `Esc` | Close the editor window |

## 🗂 Project Structure

```
todo_app/
├── main.py             # the entire application
├── requirements.txt    # optional dependencies (auto-installed on first run)
├── README.md            # this file
└── todo_data.db         # created automatically on first run (your tasks)
```

## 🛠 Tech Notes

- **GUI:** Tkinter + ttk (standard library — no framework lock-in)
- **Storage:** SQLite3 (standard library), soft-deletes for safe undo
- **Notifications:** [`plyer`](https://pypi.org/project/plyer/) when available, graceful popup fallback otherwise


<img width="1920" height="966" alt="Python 3 9 12-07-2026 07_28_26" src="https://github.com/user-attachments/assets/d7c4c19b-73bd-49dd-9d87-e658e18bde52" />
<img width="1920" height="966" alt="Python 3 9 12-07-2026 07_28_22" src="https://github.com/user-attachments/assets/fccf1b4e-e81b-41ed-922b-642891ff853a" />
<img width="650" height="800" alt="Python 3 9 12-07-2026 07_25_46" src="https://github.com/user-attachments/assets/517aacf2-2514-4adc-b401-75e381f3596a" />
<img width="1920" height="966" alt="Python 3 9 12-07-2026 07_25_15" src="https://github.com/user-attachments/assets/5c651242-482d-45e5-b863-397fd7dc3edf" />


- **Date picker:** [`tkcalendar`](https://pypi.org/project/tkcalendar/) when available, graceful text-entry fallback otherwise
- Background thread checks for tasks due within 15 minutes every 30 seconds and fires a single reminder per task

---

Made with ☕ and Tkinter by **@anxntbhardwaj**

MIT License

Copyright (c) 2026 @anxntbhardwaj

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
