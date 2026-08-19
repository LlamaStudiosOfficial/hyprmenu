# Desktop Entry Editor

A GTK4 application for browsing and editing `.desktop` files. The
interface is modelled after KDE's *KMenuEdit*.

## Features

- **Application browser** — scans `~/.local/share/applications`,
  `/usr/local/share/applications` and `/usr/share/applications`
  (plus Flatpak and NixOS paths), with live search across names,
  comments and exec lines.
- **Icon picker** — searchable dialog over every icon in the current
  theme; absolute icon paths are also rendered.
- **Raw-text fallback** — files that are not valid INI still open and
  can be saved verbatim.

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
