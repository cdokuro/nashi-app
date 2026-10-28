# Nashi Linux Architecture & Implementation Plan

## 1. Executive Summary
Nashi is an open-source macOS/Windows file processing utility originally inspired by Tangerine.
This project ports Nashi's core wheel/file processing experience and native desktop workflow to Linux using **PySide6 (Qt6)**, utilizing system tools (**ImageMagick**, **FFmpeg**, **qrencode**, **zbarimg**) along with python media/document toolchains.

## 2. Supported Core Capabilities
- **File Ingestion:** Drag-and-drop file garden, file browser picker, clipboard paste.
- **Radial/Tool Wheel:** Nashi's signature circular conversion & tool wheel.
- **Image Conversions:** JPG, PNG, WEBP, TIFF, AVIF, BMP, PDF, SVG.
- **Audio/Video Media Operations:** Video to MP4, MP3, WAV, GIF, WebM; trim and extract audio.
- **PDF & Document Tools:** Merge PDFs, extract pages, convert images to PDF.
- **QR Operations:** Generate QR codes, read/decode QR from uploaded files or screen.
- **Library Store:** Keeps history of recent exports with single-click open & locate in file manager.
- **Theme & Branding:** Authentic Nashi gold accents, dark/light theme, and pear iconography.

## 3. Subagents & Division of Work
1. **Engine Core (`engine.py`):** File conversions, format matrix parser, and external tool execution.
2. **Library & Config (`store.py`):** History persistence (`~/.local/share/nashi/library.json`) and settings.
3. **UI Wheel Widget (`wheel_widget.py`):** Interactive radial menu with smooth animations and tool slots.
4. **Main Window (`main_window.py`):** Home view, drag-and-drop dropzone, Library tab, and notifications.
5. **Desktop Packaging & CLI:** `nashi` executable wrapper + `nashi.desktop` Linux desktop entry.
