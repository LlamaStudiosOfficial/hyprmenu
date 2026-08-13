# Walker Desktop Editor

A GTK4 application for browsing and editing `.desktop` files for
[Walker](https://github.com/abenz1267/walker), the keyboard-driven
application launcher for Hyprland. The interface is modelled after
KDE's *KMenuEdit*.

## Features

- **Application browser** — scans `~/.local/share/applications`,
  `/usr/local/share/applications` and `/usr/share/applications`
  (plus Flatpak and NixOS paths), with live search across names,
  comments and exec lines.
- **KMenuEdit-style editor**:
  - *General* column: icon, name, generic name, comment, show/hide options
  - *Command* column: executable (with Browse…), work path, run-in-terminal
  - *Advanced* section: `StartupWMClass`, `Categories`, `Keywords`,
    `MimeType`, `Actions`, and any other property you add or remove
- **Raw-text fallback** — files that are not valid INI still open and
  can be saved verbatim.
- **Read-only safety** — saving to system directories is blocked with a
  hint to use *Save As…*; *Save As* defaults to `~/.local/share/applications`
  so user entries shadow system ones.
- **Unsaved-change guard** — prompts before switching or discarding edits.
- **New / Delete** — create a fresh entry or remove an existing one.
- Keyboard shortcuts: `Ctrl+N`, `Ctrl+S`, `Ctrl+Shift+S`, `F5`, `Ctrl+Q`.

## Requirements

- Python 3.10+
- GTK 4 and PyGObject: on Arch
  `sudo pacman -S python-gobject gtk4`

## Usage

```sh
./hyprmenu.py
```

Run directly, or add it to your Hyprland keybinds:

```ini
bind = SUPER, E, exec, hyprmenu.py
```

## Notes

- Values are written with `key = value` syntax; unknown keys are
  preserved in insertion order.
- Comments inside `.desktop` files are **not** preserved on save.
- Walker reads your user `.desktop` files at `~/.local/share/applications`
  and caches them; run `walker --reload` or restart it after editing.

---

Made with [Opencode](https://opencode.ai)
