# Nashi Linux 2.0

Native Linux port of [Nashi](https://github.com/orkunisitmak/nashi-app) built with Python 3, PySide6 (Qt 6), and deep KDE Plasma / Wayland & X11 integration.

## ✨ Features

- **Dynamic Petal Radial Wheel**: Centered directly under the cursor with gold highlight arc, centroid label calculation, and interactive petal slices matching macOS `WheelGeometry.swift`.
- **Global Drag Mode (`Shift` / `Ctrl` / `Alt`)**:
  - Drag a file from Dolphin, desktop, or any window:
    - Hold `Shift` → Pops **Convert Wheel** (PNG, JPG, WEBP, PDF, MP4, MP3, etc.)
    - Hold `Ctrl` → Pops **Tools Wheel** (Crop, Frame, Speed, Redact, Audio Normalize, etc.)
    - Hold `Alt` → Pops **Actions Wheel** (Float Shelf, Share, Copy Path, Terminal, etc.)
  - Real-time modifier switching during active drag.
  - Wayland sub-30ms cursor tracking across multi-monitor setups.
- **27 Conversion & Transformation Tools**:
  - Image manipulation: crop, rotate, frame, annotate, blur/redact, collage.
  - Video & Audio: trim, speed adjust, snapshots, split, normalize audio, channel remap, audio-to-video.
  - Documents & Archives: PDF reorder/merge/compress, archive extraction, subtitles (SRT/VTT), web media downloader (yt-dlp).
- **Float Shelf**: Edge-snappable floating shelf to stash files while working.
- **Non-Activating Toast HUD**: Elegant bottom toast notification with "Show in Folder" and "Copy" actions.
- **Interactive Editors**: Visual crop dialog with aspect ratio locks, photo editor, and media trimmer.
- **Vector Mascot & Themes**: Custom Asian pear mascot (`NashiArtwork`), FileGarden widget, and 4 themes (`Forest Dark`, `Warm Paper Light`, `Catppuccin Mocha`, `Rose Pine`).

## 🚀 Installation & Running

```bash
# Dependencies
pip install -r linux/requirements.txt

# System utilities for conversions
sudo pacman -S ffmpeg imagemagick poppler yt-dlp  # Arch / Omarchy
# or
sudo apt install ffmpeg imagemagick poppler-utils yt-dlp  # Debian / Ubuntu

# Run
./linux/nashi
```

## ⌨️ Global Shortcuts

| Shortcut | Action |
| --- | --- |
| `Drag + Shift` | Convert Wheel under cursor |
| `Drag + Ctrl` | Tools Wheel under cursor |
| `Drag + Alt` | Actions Wheel under cursor |
| `Shift + Space` or `Alt + Shift + C` | Summon Convert Wheel |
| `Ctrl + Space` or `Alt + Shift + T` | Summon Tools Wheel |
| `Alt + Space` or `Alt + Shift + A` | Summon Actions Wheel |
| `Ctrl + Shift + D` | Quick Download Web Link |
| `Alt + Shift + N` | Toggle Nashi Main Window |
