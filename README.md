# Desktop Entry Editor

A GTK4 application for browsing and editing `.desktop` files. The
interface is modelled after KDE's *KMenuEdit*.

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
- **Icon picker** — searchable dialog over every icon in the current
  theme; absolute icon paths are also rendered.
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

---

Made with [Opencode](https://opencode.ai)
