<div align="center">
  <img src="hyprmenu.png" width="150">
  <h1 align="center">Hyprmenu</h1>
  <p align="center">A .desktop file editor inspired by <i>KMenuEdit</i>.</p>
</div>

## Requirements
- Python
- [CurlFolder](https://github.com/MeltingReactor/curlFolder/)

## Installation
Either run the installer or run the command below:
```bash
cd ~/ && mkdir .hyprmenu && curlFolder https://raw.githubusercontent.com/LlamaStudiosOfficial/hyprmenu/refs/heads/main/hyprmenu.py .hyprmenu && curlFolder 'https://github.com/LlamaStudiosOfficial/hyprmenu/blob/main/hyprmenu.png?raw=true' .hyprmenu && touch Hyprmenu.desktop && echo "[Desktop Entry]
Type=Application
Name=Hyprmenu
GenericName=Hyprland .deskop editor.
Icon=~/.hyprmenu/hyprmenu.png
Exec=python3 ~/.hyprmenu/hyprmenu.py" > ~/.local/share/applications/Hyprmenu.desktop
```

Made with [Opencode](https://opencode.ai)
