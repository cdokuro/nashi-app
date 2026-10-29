"""
Nashi Linux - Complete Conversion Engine & 27-Tool Pipeline
Matching Nashi's FeatureCatalog.json (45 input formats, 27 tools, 6 file actions, web media).
"""

import csv
import gzip
import html
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple


IMAGE_FORMATS = {
    "jpg", "jpeg", "png", "webp", "heic", "tiff", "tif",
    "avif", "bmp", "svg", "ico", "gif"
}

AUDIO_FORMATS = {
    "mp3", "m4a", "wav", "flac", "ogg", "opus", "aiff", "wma", "aac"
}

VIDEO_FORMATS = {
    "mp4", "mov", "mkv", "webm", "avi", "wmv", "m4v", "flv"
}

ARCHIVE_FORMATS = {
    "zip", "tar", "gz", "tgz", "bz2", "rar"
}

DOC_FORMATS = {
    "pdf", "txt", "md", "html", "docx", "pages", "rtf", "rtfd", "textclipping",
    "epub", "ppt", "pptx", "xlsx", "xls", "ods", "csv", "tsv", "srt", "vtt"
}

TOOL_SYMBOLS: Dict[str, str] = {
    "compress": "⚡",
    "removeMetadata": "🛡️",
    "editImage": "🎨",
    "annotateImage": "✏️",
    "frameImage": "🖼️",
    "cropImage": "✂️",
    "normalizeAudio": "🔊",
    "muteVideo": "🔇",
    "trimVideo": "⏱️",
    "splitPDF": "📄",
    "organizePDF": "📑",
    "extractArchive": "📦",
    "createPDF": "📕",
    "mergePDF": "📚",
    "cropVideo": "✂️",
    "changeVideoSpeed": "⏩",
    "joinVideos": "🎞️",
    "videoSnapshots": "📸",
    "splitVideo": "➗",
    "audioToVideo": "〰️",
    "trimAudio": "⏱️",
    "audioChannels": "🎧",
    "createCollage": "🧩",
    "redactImage": "🕶️",
    "redactVideo": "🕶️",
    "redactAudio": "🔕",
    "readQRCode": "🏁",
}

TOOL_TR_NAMES: Dict[str, str] = {
    "compress": "Sıkıştır",
    "removeMetadata": "Meta Veri Sil",
    "editImage": "Fotoğraf Düzenle",
    "annotateImage": "Çizim / Not",
    "frameImage": "Arka Plan Ekle",
    "cropImage": "Görseli Kırp",
    "normalizeAudio": "SesiDengele",
    "muteVideo": "Sesi Kaldır",
    "trimVideo": "Videoyu Kes",
    "splitPDF": "PDF Böl",
    "organizePDF": "PDF Düzenle",
    "extractArchive": "Arşivi Çıkar",
    "createPDF": "PDF Oluştur",
    "mergePDF": "PDF Birleştir",
    "cropVideo": "Videoyu Kırp",
    "changeVideoSpeed": "Video Hızı",
    "joinVideos": "Video Birleştir",
    "videoSnapshots": "Kare Yakala",
    "splitVideo": "Videoyu Böl",
    "audioToVideo": "Ses Görselleştir",
    "trimAudio": "Sesi Kes",
    "audioChannels": "Ses Kanalı",
    "createCollage": "Kolaj Yap",
    "redactImage": "Görsel Gizle",
    "redactVideo": "Video Gizle",
    "redactAudio": "Sesi Sansürle",
    "readQRCode": "QR Kod Oku",
}

ACTION_DEFS: List[Dict[str, str]] = [
    {"id": "float", "title_tr": "Yüzen Raf (Float)", "title_en": "Float", "symbol": "📎"},
    {"id": "copy", "title_tr": "Kopyala", "title_en": "Copy", "symbol": "📋"},
    {"id": "move", "title_tr": "Taşı…", "title_en": "Move…", "symbol": "📂"},
    {"id": "copyPath", "title_tr": "Yolu Kopyala", "title_en": "Copy Path", "symbol": "🔗"},
    {"id": "terminal", "title_tr": "Terminalde Aç", "title_en": "Terminal", "symbol": ">_"},
    {"id": "share", "title_tr": "Klasörde Göster", "title_en": "Show in Folder", "symbol": "🔍"},
]


class NashiEngine:
    """Core file conversion and 27-tool media/document utility engine for Nashi Linux."""

    def __init__(self, catalog_path: Optional[str] = None):
        self.catalog_path = self._resolve_catalog_path(catalog_path)
        self.catalog_data: Dict[str, Any] = {}
        self.conversion_matrix: Dict[str, List[str]] = {}
        self.single_tools: Dict[str, List[str]] = {}
        self.multiple_tools: Dict[str, List[str]] = {}
        self.tool_names: Dict[str, str] = {}
        self.file_actions: List[str] = []

        self._load_catalog()

    def _resolve_catalog_path(self, catalog_path: Optional[str]) -> Path:
        if catalog_path:
            p = Path(catalog_path).expanduser().resolve()
            if p.exists():
                return p

        candidates = [
            Path(__file__).resolve().parent / "assets" / "FeatureCatalog.json",
            Path.cwd() / "assets" / "FeatureCatalog.json",
            Path.cwd() / "nashi-linux" / "assets" / "FeatureCatalog.json",
            Path.home() / ".local" / "share" / "nashi" / "FeatureCatalog.json",
        ]
        for c in candidates:
            if c.exists():
                return c.resolve()

        return Path(__file__).resolve().parent / "assets" / "FeatureCatalog.json"

    def _load_catalog(self):
        if self.catalog_path and self.catalog_path.exists():
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    self.catalog_data = json.load(f)
                    self.conversion_matrix = self.catalog_data.get("conversionMatrix", {})
                    self.single_tools = self.catalog_data.get("singleTools", {})
                    self.multiple_tools = self.catalog_data.get("multipleTools", {})
                    self.tool_names = self.catalog_data.get("toolNames", {})
                    self.file_actions = self.catalog_data.get("fileActions", [])
                    return
            except Exception as e:
                print(f"[NashiEngine] Warning: Could not read {self.catalog_path}: {e}")

        self._load_default_matrix()

    def _load_default_matrix(self):
        self.conversion_matrix = {
            "jpg": ["png", "webp", "tiff", "avif", "bmp", "pdf"],
            "png": ["jpg", "webp", "tiff", "avif", "bmp", "pdf"],
            "webp": ["jpg", "png", "tiff", "avif", "bmp", "pdf"],
            "svg": ["png", "jpg", "webp", "pdf"],
            "bmp": ["png", "jpg", "webp", "pdf"],
            "tiff": ["png", "jpg", "webp", "pdf"],
            "avif": ["png", "jpg", "webp", "pdf"],
            "mp4": ["mov", "mkv", "webm", "avi", "gif", "mp3"],
            "mov": ["mp4", "mkv", "webm", "avi", "gif", "mp3"],
            "webm": ["mp4", "mov", "mkv", "avi", "gif", "mp3"],
            "gif": ["mp4", "webm"],
            "mp3": ["wav", "flac", "ogg", "opus", "m4a"],
            "wav": ["mp3", "flac", "ogg", "opus", "m4a"],
            "flac": ["mp3", "wav", "ogg", "opus", "m4a"],
            "ogg": ["mp3", "wav", "flac", "opus", "m4a"],
            "pdf": ["png", "jpg", "txt", "md"]
        }
        self.tool_names = dict(TOOL_TR_NAMES)
        self.file_actions = ["share", "float", "copy", "move", "copyPath", "terminal"]

    @staticmethod
    def normalize_extension(ext_or_path: str) -> str:
        name = os.path.basename(ext_or_path)
        if name.lower().endswith(".tar.gz"):
            return "gz"
        ext = os.path.splitext(name)[1].lower().lstrip(".")
        if not ext and not os.path.splitext(name)[1]:
            ext = ext_or_path.lower().lstrip(".")

        aliases = {
            "jpeg": "jpg",
            "tif": "tiff",
            "m4v": "mp4",
            "wave": "wav",
            "tgz": "gz",
            "htm": "html",
            "markdown": "md",
        }
        return aliases.get(ext, ext)

    @staticmethod
    def is_web_url(text: str) -> bool:
        if not text:
            return False
        s = text.strip()
        return s.startswith("http://") or s.startswith("https://")

    def get_available_targets(self, file_path: str) -> List[str]:
        ext = self.normalize_extension(file_path)
        return list(self.conversion_matrix.get(ext, []))

    def get_available_targets_for_files(self, file_paths: List[str]) -> List[str]:
        """Returns ordered intersection of conversion targets across all input files."""
        if not file_paths:
            return ["png", "jpg", "webp", "pdf", "mp4", "mp3", "gif", "zip"]
        first_targets = self.get_available_targets(file_paths[0])
        if len(file_paths) == 1:
            return first_targets
        common_set = set(first_targets)
        for fp in file_paths[1:]:
            common_set.intersection_update(self.get_available_targets(fp))
        return [t for t in first_targets if t in common_set]

    def get_available_tools(self, file_path: str) -> List[str]:
        ext = self.normalize_extension(file_path)
        tools = list(self.single_tools.get(ext, []))
        if ext in IMAGE_FORMATS or ext == "pdf":
            if "readQRCode" not in tools:
                tools.append("readQRCode")
        return tools

    def get_available_multiple_tools(self, file_paths: List[str]) -> List[str]:
        if not file_paths:
            return []
        first_ext = self.normalize_extension(file_paths[0])
        first_list = list(self.multiple_tools.get(first_ext, []))
        common_set = set(first_list)
        for fp in file_paths[1:]:
            ext = self.normalize_extension(fp)
            common_set.intersection_update(self.multiple_tools.get(ext, []))
        return [t for t in first_list if t in common_set]

    def get_available_tools_for_files(self, file_paths: List[str]) -> List[str]:
        """Unified helper matching FeatureCatalog.tools(for: inputs)."""
        if not file_paths:
            return ["compress", "removeMetadata", "cropImage", "editImage", "trimVideo", "createPDF", "mergePDF", "readQRCode"]
        if len(file_paths) == 1:
            tools = self.get_available_tools(file_paths[0])
            return tools if tools else ["compress", "removeMetadata"]
        multi = self.get_available_multiple_tools(file_paths)
        return multi if multi else ["compress", "removeMetadata"]

    def get_tool_name(self, tool_id: str, lang: str = "tr") -> str:
        if lang == "tr" and tool_id in TOOL_TR_NAMES:
            return TOOL_TR_NAMES[tool_id]
        return self.tool_names.get(tool_id, tool_id)

    def get_tool_symbol(self, tool_id: str) -> str:
        return TOOL_SYMBOLS.get(tool_id, "⚙️")

    def get_file_actions(self, lang: str = "tr") -> List[Dict[str, str]]:
        result = []
        for a in ACTION_DEFS:
            result.append({
                "id": a["id"],
                "title": a["title_tr"] if lang == "tr" else a["title_en"],
                "symbol": a["symbol"],
            })
        return result

    def _resolve_output_path(self, input_path: str, target_format: str, output_dir: Optional[str] = None, suffix: str = "") -> str:
        """Constructs collision-safe target file path without overwriting existing files."""
        inp = Path(input_path).resolve()
        target_ext = target_format.lower().lstrip(".")

        dest_dir = Path(output_dir).expanduser().resolve() if (output_dir and str(output_dir).strip()) else inp.parent
        dest_dir.mkdir(parents=True, exist_ok=True)

        stem = f"{inp.stem}{suffix}"
        candidate = dest_dir / f"{stem}.{target_ext}"

        if candidate == inp:
            stem = f"{inp.stem}{suffix or '_converted'}"
            candidate = dest_dir / f"{stem}.{target_ext}"

        counter = 2
        while candidate.exists() and candidate != inp:
            candidate = dest_dir / f"{stem}_{counter}.{target_ext}"
            counter += 1

        return str(candidate)

    def _run_cmd(self, cmd: List[str], desc: str = "Command") -> str:
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() if e.stderr else e.stdout.strip()
            raise RuntimeError(f"{desc} failed (exit code {e.returncode}): {err_msg}") from e
        except FileNotFoundError as e:
            binary = cmd[0] if cmd else "executable"
            raise RuntimeError(f"Required system tool '{binary}' is not installed or not in PATH.") from e

    # ----------------------------------------------------------------------
    # Main Conversion Dispatcher
    # ----------------------------------------------------------------------
    def convert(self, input_path: str, target_format: str, output_dir: Optional[str] = None) -> str:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file does not exist: {input_path}")

        src_ext = self.normalize_extension(input_path)
        tgt_ext = self.normalize_extension(target_format)
        out_path = self._resolve_output_path(input_path, tgt_ext, output_dir)

        # 1. Subtitles (SRT <-> VTT <-> TXT)
        if src_ext in ("srt", "vtt") or tgt_ext in ("srt", "vtt"):
            return self.convert_subtitle(input_path, tgt_ext, out_path)

        # 2. Archives (ZIP <-> TAR <-> GZ)
        if src_ext in ARCHIVE_FORMATS and tgt_ext in ARCHIVE_FORMATS:
            return self.convert_archive(input_path, tgt_ext, out_path)

        # 3. Spreadsheets (CSV <-> TSV <-> HTML/TXT/PDF)
        if src_ext in ("csv", "tsv") or tgt_ext in ("csv", "tsv"):
            return self._convert_tabular(input_path, out_path, src_ext, tgt_ext)

        # 4. Video -> GIF
        if src_ext in VIDEO_FORMATS and tgt_ext == "gif":
            return self._convert_video_to_gif(input_path, out_path)

        # 5. GIF -> Video
        if src_ext == "gif" and tgt_ext in VIDEO_FORMATS:
            return self._convert_gif_to_video(input_path, out_path, tgt_ext)

        # 6. Video -> Audio
        if src_ext in VIDEO_FORMATS and tgt_ext in AUDIO_FORMATS:
            return self.extract_audio(input_path, format=tgt_ext, output_path=out_path)

        # 7. Media -> Media
        if (src_ext in VIDEO_FORMATS and tgt_ext in VIDEO_FORMATS) or \
           (src_ext in AUDIO_FORMATS and tgt_ext in AUDIO_FORMATS):
            return self._convert_media_ffmpeg(input_path, out_path, tgt_ext)

        # 8. Image -> Image / PDF
        if src_ext in IMAGE_FORMATS and (tgt_ext in IMAGE_FORMATS or tgt_ext == "pdf"):
            return self._convert_image_magick(input_path, out_path, tgt_ext)

        # 9. PDF -> Image
        if src_ext == "pdf" and tgt_ext in IMAGE_FORMATS:
            return self._convert_pdf_to_image(input_path, out_path, tgt_ext)

        # 10. Document / Text Conversions
        if src_ext in DOC_FORMATS or tgt_ext in DOC_FORMATS:
            return self._convert_document(input_path, out_path, src_ext, tgt_ext)

        if src_ext in IMAGE_FORMATS:
            return self._convert_image_magick(input_path, out_path, tgt_ext)
        return self._convert_media_ffmpeg(input_path, out_path, tgt_ext)

    # ----------------------------------------------------------------------
    # Image Conversions & Image Tools (ImageMagick)
    # ----------------------------------------------------------------------
    def _convert_image_magick(self, input_path: str, output_path: str, target_format: str) -> str:
        cmd = ["magick"]
        if input_path.lower().endswith(".svg"):
            cmd.extend(["-background", "none", "-density", "300"])
        cmd.append(input_path)
        if target_format in ("jpg", "jpeg", "bmp"):
            cmd.extend(["-background", "white", "-alpha", "remove", "-alpha", "off"])
        cmd.append(output_path)
        self._run_cmd(cmd, desc="Image conversion")
        return output_path

    def _convert_pdf_to_image(self, input_path: str, output_path: str, target_format: str) -> str:
        cmd = [
            "magick",
            "-density", "250",
            f"{input_path}[0]",
            "-background", "white",
            "-alpha", "remove",
            "-alpha", "off",
            output_path
        ]
        self._run_cmd(cmd, desc="PDF to image conversion")
        return output_path

    def get_image_dimensions(self, image_path: str) -> Tuple[int, int]:
        out = self._run_cmd(["magick", "identify", "-format", "%w %h", f"{image_path}[0]"], desc="Identify image")
        parts = out.strip().split()
        return int(parts[0]), int(parts[1])

    def crop_image(
        self,
        input_path: str,
        x: int = 0,
        y: int = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        aspect_ratio: Optional[Tuple[int, int]] = None,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Crops an image by explicit geometry (x, y, width, height) or centered aspect ratio."""
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Image not found: {input_path}")

        ext = self.normalize_extension(input_path)
        if not output_path:
            output_path = self._resolve_output_path(input_path, ext, output_dir, suffix="_cropped")

        img_w, img_h = self.get_image_dimensions(input_path)

        if width is None or height is None:
            if aspect_ratio:
                aw, ah = aspect_ratio
                target_ratio = aw / float(ah)
                curr_ratio = img_w / float(max(1, img_h))
                if curr_ratio > target_ratio:
                    height = img_h
                    width = int(round(img_h * target_ratio))
                else:
                    width = img_w
                    height = int(round(img_w / target_ratio))
                x = max(0, (img_w - width) // 2)
                y = max(0, (img_h - height) // 2)
            else:
                # Default 85% center crop if no params given
                width = max(1, int(img_w * 0.85))
                height = max(1, int(img_h * 0.85))
                x = max(0, (img_w - width) // 2)
                y = max(0, (img_h - height) // 2)

        width = max(1, min(int(width), img_w))
        height = max(1, min(int(height), img_h))
        x = max(0, min(int(x), img_w - 1))
        y = max(0, min(int(y), img_h - 1))

        geom = f"{width}x{height}+{x}+{y}"
        cmd = ["magick", input_path, "-crop", geom, "+repage", output_path]
        self._run_cmd(cmd, desc="Crop image")
        return output_path

    def edit_image(
        self,
        input_path: str,
        rotate_deg: int = 0,
        flip_horizontal: bool = False,
        flip_vertical: bool = False,
        scale_percent: int = 100,
        brightness: int = 0,
        contrast: int = 0,
        saturation: int = 100,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Adjusts rotation, flip, scale, brightness, contrast, and saturation of an image."""
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Image not found: {input_path}")

        ext = self.normalize_extension(input_path)
        if not output_path:
            output_path = self._resolve_output_path(input_path, ext, output_dir, suffix="_edited")

        cmd = ["magick", input_path]
        if rotate_deg:
            cmd.extend(["-rotate", str(rotate_deg)])
        if flip_horizontal:
            cmd.append("-flop")
        if flip_vertical:
            cmd.append("-flip")
        if scale_percent and scale_percent != 100:
            cmd.extend(["-resize", f"{scale_percent}%"])
        if brightness != 0 or contrast != 0:
            cmd.extend(["-brightness-contrast", f"{brightness}x{contrast}"])
        if saturation != 100:
            cmd.extend(["-modulate", f"100,{saturation},100"])

        cmd.append(output_path)
        self._run_cmd(cmd, desc="Edit image")
        return output_path

    def frame_image(
        self,
        input_path: str,
        padding: int = 48,
        bg_color: str = "#F9F6ED",
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Adds a clean background frame / border padding around an image ('Add BG' tool)."""
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Image not found: {input_path}")

        ext = self.normalize_extension(input_path)
        out_ext = "png" if ext in ("svg", "webp") else ext
        if not output_path:
            output_path = self._resolve_output_path(input_path, out_ext, output_dir, suffix="_framed")

        cmd = [
            "magick", input_path,
            "-bordercolor", bg_color,
            "-border", f"{max(4, int(padding))}x{max(4, int(padding))}",
            output_path
        ]
        self._run_cmd(cmd, desc="Frame image")
        return output_path

    def annotate_image(
        self,
        input_path: str,
        text: str = "Nashi",
        color: str = "#E3B859",
        position: str = "South",
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Adds an annotation banner/caption or highlight border onto an image."""
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Image not found: {input_path}")

        ext = self.normalize_extension(input_path)
        if not output_path:
            output_path = self._resolve_output_path(input_path, ext, output_dir, suffix="_annotated")

        img_w, img_h = self.get_image_dimensions(input_path)
        pt_size = max(16, min(72, img_w // 18))

        cmd = [
            "magick", input_path,
            "-gravity", position,
            "-undercolor", "#111A14CC",
            "-fill", color,
            "-pointsize", str(pt_size),
            "-annotate", "+0+20", f" {text} ",
            output_path
        ]
        self._run_cmd(cmd, desc="Annotate image")
        return output_path

    def redact_image(
        self,
        input_path: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        mode: str = "pixelate",
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Redacts a region (or center band) of an image via pixelate, blur, or solid fill."""
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Image not found: {input_path}")

        ext = self.normalize_extension(input_path)
        if not output_path:
            output_path = self._resolve_output_path(input_path, ext, output_dir, suffix="_redacted")

        img_w, img_h = self.get_image_dimensions(input_path)
        rw = width or max(20, int(img_w * 0.5))
        rh = height or max(20, int(img_h * 0.25))
        rx = x if x is not None else (img_w - rw) // 2
        ry = y if y is not None else (img_h - rh) // 2

        if mode == "solid":
            cmd = [
                "magick", input_path,
                "-fill", "#111A14",
                "-draw", f"rectangle {rx},{ry} {rx + rw},{ry + rh}",
                output_path
            ]
        elif mode == "blur":
            cmd = [
                "magick", input_path,
                "-region", f"{rw}x{rh}+{rx}+{ry}",
                "-blur", "0x18",
                "+region",
                output_path
            ]
        else:
            # Pixelate region
            cmd = [
                "magick", input_path,
                "-region", f"{rw}x{rh}+{rx}+{ry}",
                "-scale", "10%", "-scale", "1000%",
                "+region",
                output_path
            ]
        self._run_cmd(cmd, desc="Redact image")
        return output_path

    def create_collage(
        self,
        image_paths: List[str],
        columns: int = 2,
        padding: int = 16,
        bg_color: str = "#F9F6ED",
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Combines multiple images into a clean grid collage."""
        if not image_paths:
            raise ValueError("No images provided for collage.")
        for p in image_paths:
            if not os.path.exists(p):
                raise FileNotFoundError(f"Image not found: {p}")

        if not output_path:
            output_path = self._resolve_output_path(image_paths[0], "png", output_dir, suffix="_collage")

        cols = max(1, min(columns, len(image_paths)))
        cmd = [
            "magick", "montage",
            *image_paths,
            "-tile", f"{cols}x",
            "-geometry", f"480x480+{padding}+{padding}",
            "-background", bg_color,
            output_path
        ]
        self._run_cmd(cmd, desc="Create collage")
        return output_path

    # ----------------------------------------------------------------------
    # Media Conversions & Media Tools (FFmpeg)
    # ----------------------------------------------------------------------
    def _convert_media_ffmpeg(self, input_path: str, output_path: str, target_format: str) -> str:
        cmd = ["ffmpeg", "-y", "-i", input_path]

        if target_format in ("mp4", "mov", "m4v"):
            cmd.extend([
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:a", "aac", "-b:a", "192k"
            ])
        elif target_format == "webm":
            cmd.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus"])
        elif target_format == "mkv":
            cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"])
        elif target_format == "avi":
            cmd.extend(["-c:v", "mpeg4", "-q:v", "4", "-c:a", "libmp3lame"])
        elif target_format == "wmv":
            cmd.extend(["-c:v", "wmv2", "-b:v", "2M", "-c:a", "wmav2"])
        elif target_format == "mp3":
            cmd.extend(["-vn", "-c:a", "libmp3lame", "-q:a", "2"])
        elif target_format == "wav":
            cmd.extend(["-vn", "-c:a", "pcm_s16le"])
        elif target_format == "flac":
            cmd.extend(["-vn", "-c:a", "flac"])
        elif target_format in ("aac", "m4a"):
            cmd.extend(["-vn", "-c:a", "aac", "-b:a", "192k"])
        elif target_format == "ogg":
            cmd.extend(["-vn", "-c:a", "libvorbis", "-q:a", "4"])
        elif target_format == "opus":
            cmd.extend(["-vn", "-c:a", "libopus", "-b:a", "128k"])
        elif target_format == "aiff":
            cmd.extend(["-vn", "-c:a", "pcm_s16be"])
        elif target_format == "wma":
            cmd.extend(["-vn", "-c:a", "wmav2", "-b:a", "160k"])

        cmd.append(output_path)
        self._run_cmd(cmd, desc="Media conversion")
        return output_path

    def _convert_video_to_gif(self, input_path: str, output_path: str) -> str:
        filter_spec = "fps=12,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", filter_spec, output_path]
        self._run_cmd(cmd, desc="Video to GIF conversion")
        return output_path

    def _convert_gif_to_video(self, input_path: str, output_path: str, target_format: str = "mp4") -> str:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-movflags", "faststart",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            output_path
        ]
        self._run_cmd(cmd, desc="GIF to video conversion")
        return output_path

    def get_media_duration(self, media_path: str) -> float:
        """Returns media duration in seconds using ffprobe."""
        if not shutil.which("ffprobe"):
            return 10.0
        try:
            out = self._run_cmd([
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                media_path
            ], desc="Probe media duration")
            return max(0.1, float(out.strip()))
        except Exception:
            return 10.0

    def extract_audio(self, video_path: str, format: str = "mp3", output_path: Optional[str] = None, output_dir: Optional[str] = None) -> str:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file does not exist: {video_path}")

        fmt = self.normalize_extension(format)
        if not output_path:
            output_path = self._resolve_output_path(video_path, fmt, output_dir)

        cmd = ["ffmpeg", "-y", "-i", video_path, "-vn"]
        if fmt == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
        elif fmt == "wav":
            cmd.extend(["-c:a", "pcm_s16le"])
        elif fmt == "flac":
            cmd.extend(["-c:a", "flac"])
        elif fmt in ("aac", "m4a"):
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            cmd.extend(["-c:a", "copy"])

        cmd.append(output_path)
        self._run_cmd(cmd, desc="Audio extraction")
        return output_path

    def change_video_speed(
        self,
        video_path: str,
        speed: float = 1.5,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Changes video playback speed (0.5x to 2.0x)."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        speed = max(0.5, min(2.0, float(speed)))
        ext = self.normalize_extension(video_path)
        if not output_path:
            output_path = self._resolve_output_path(video_path, ext, output_dir, suffix=f"_{speed:g}x")

        pts_mult = 1.0 / speed
        # Check if audio stream exists
        has_audio = False
        if shutil.which("ffprobe"):
            try:
                streams = self._run_cmd([
                    "ffprobe", "-v", "error", "-select_streams", "a",
                    "-show_entries", "stream=index", "-of", "csv=p=0", video_path
                ])
                has_audio = bool(streams.strip())
            except Exception:
                has_audio = False

        cmd = ["ffmpeg", "-y", "-i", video_path, "-vf", f"setpts={pts_mult:.4f}*PTS"]
        if has_audio:
            cmd.extend(["-af", f"atempo={speed:.4f}"])
        cmd.append(output_path)
        self._run_cmd(cmd, desc="Change video speed")
        return output_path

    def crop_video(
        self,
        video_path: str,
        aspect_ratio: Tuple[int, int] = (1, 1),
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Crops video to target aspect ratio centered."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        ext = self.normalize_extension(video_path)
        if not output_path:
            output_path = self._resolve_output_path(video_path, ext, output_dir, suffix="_cropped")

        aw, ah = aspect_ratio
        vf = f"crop='min(iw,ih*{aw}/{ah})':'min(ih,iw*{ah}/{aw})'"
        cmd = ["ffmpeg", "-y", "-i", video_path, "-vf", vf, "-c:a", "copy", output_path]
        self._run_cmd(cmd, desc="Crop video")
        return output_path

    def video_snapshots(
        self,
        video_path: str,
        count: int = 4,
        output_dir: Optional[str] = None,
    ) -> List[str]:
        """Captures evenly spaced snapshots from a video file."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        vp = Path(video_path).resolve()
        dest_dir = Path(output_dir).resolve() if output_dir else vp.parent / f"{vp.stem}_snapshots"
        dest_dir.mkdir(parents=True, exist_ok=True)

        duration = self.get_media_duration(video_path)
        count = max(1, min(12, int(count)))
        outputs = []
        for i in range(count):
            t = (duration * (i + 0.5)) / count
            out_img = dest_dir / f"{vp.stem}_snap_{i+1:02d}.png"
            cmd = [
                "ffmpeg", "-y", "-ss", f"{t:.2f}",
                "-i", video_path,
                "-frames:v", "1",
                str(out_img)
            ]
            self._run_cmd(cmd, desc="Video snapshot")
            if out_img.exists():
                outputs.append(str(out_img))
        return outputs

    def split_video(
        self,
        video_path: str,
        parts: int = 2,
        output_dir: Optional[str] = None,
    ) -> List[str]:
        """Splits a video into `parts` equal segments."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        vp = Path(video_path).resolve()
        ext = self.normalize_extension(video_path)
        dest_dir = Path(output_dir).resolve() if output_dir else vp.parent
        dest_dir.mkdir(parents=True, exist_ok=True)

        duration = self.get_media_duration(video_path)
        parts = max(2, min(10, int(parts)))
        seg_len = duration / parts
        outputs = []
        for i in range(parts):
            start_t = i * seg_len
            out_file = self._resolve_output_path(video_path, ext, str(dest_dir), suffix=f"_part{i+1}")
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{start_t:.2f}",
                "-t", f"{seg_len:.2f}",
                "-i", video_path,
                "-c", "copy",
                out_file
            ]
            self._run_cmd(cmd, desc="Split video")
            outputs.append(out_file)
        return outputs

    def normalize_audio(
        self,
        audio_path: str,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Normalizes audio loudness using FFmpeg EBU R128 loudnorm filter."""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio not found: {audio_path}")

        ext = self.normalize_extension(audio_path)
        if not output_path:
            output_path = self._resolve_output_path(audio_path, ext, output_dir, suffix="_normalized")

        cmd = ["ffmpeg", "-y", "-i", audio_path, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", output_path]
        self._run_cmd(cmd, desc="Normalize audio")
        return output_path

    def convert_audio_channels(
        self,
        audio_path: str,
        channels: int = 1,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Converts audio between Mono (1) and Stereo (2)."""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio not found: {audio_path}")

        ext = self.normalize_extension(audio_path)
        ch = 1 if int(channels) <= 1 else 2
        suffix = "_mono" if ch == 1 else "_stereo"
        if not output_path:
            output_path = self._resolve_output_path(audio_path, ext, output_dir, suffix=suffix)

        cmd = ["ffmpeg", "-y", "-i", audio_path, "-ac", str(ch), output_path]
        self._run_cmd(cmd, desc="Convert audio channels")
        return output_path

    def audio_to_video(
        self,
        audio_path: str,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Generates an MP4 waveform visualizer video from an audio file."""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio not found: {audio_path}")

        if not output_path:
            output_path = self._resolve_output_path(audio_path, "mp4", output_dir, suffix="_visualizer")

        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-filter_complex", "[0:a]showwaves=s=854x480:mode=line:colors=0xE3B859,format=yuv420p[v]",
            "-map", "[v]", "-map", "0:a",
            "-c:v", "libx264", "-c:a", "aac", "-shortest",
            output_path
        ]
        self._run_cmd(cmd, desc="Audio visualizer")
        return output_path

    def redact_video(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Redacts center region of a video using boxblur."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        ext = self.normalize_extension(video_path)
        if not output_path:
            output_path = self._resolve_output_path(video_path, ext, output_dir, suffix="_redacted")

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", "boxblur=15:2",
            "-c:a", "copy",
            output_path
        ]
        self._run_cmd(cmd, desc="Redact video")
        return output_path

    def redact_audio(
        self,
        audio_path: str,
        start_sec: float = 0.0,
        duration_sec: float = 2.0,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Mutes/bleeps a segment of an audio file."""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio not found: {audio_path}")

        ext = self.normalize_extension(audio_path)
        if not output_path:
            output_path = self._resolve_output_path(audio_path, ext, output_dir, suffix="_bleeped")

        end_sec = start_sec + max(0.5, duration_sec)
        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-af", f"volume=enable='between(t,{start_sec:.2f},{end_sec:.2f})':volume=0",
            output_path
        ]
        self._run_cmd(cmd, desc="Redact audio")
        return output_path

    # ----------------------------------------------------------------------
    # QR Operations (qrencode & zbarimg)
    # ----------------------------------------------------------------------
    def generate_qr(self, text: str, output_path: Optional[str] = None) -> str:
        if not output_path:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                output_path = tmp.name

        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        if shutil.which("qrencode"):
            cmd = ["qrencode", "-o", str(out), "-s", "10", "-m", "2", text]
            self._run_cmd(cmd, desc="QR generation")
            return str(out)
        elif shutil.which("magick"):
            cmd = [
                "magick", "-size", "400x400", "xc:white",
                "-fill", "black", "-gravity", "center",
                "-pointsize", "18", f"label:{text}",
                str(out)
            ]
            self._run_cmd(cmd, desc="QR fallback generation")
            return str(out)
        else:
            raise RuntimeError("Neither 'qrencode' nor 'magick' is installed for QR generation.")

    def read_qr(self, image_path: str) -> str:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        if not shutil.which("zbarimg"):
            raise RuntimeError("Required tool 'zbarimg' (zbar-tools) is not installed.")

        cmd = ["zbarimg", "--quiet", "--raw", image_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            decoded = result.stdout.strip()
            if decoded:
                return decoded
            raise ValueError("Görselde QR kod bulunamadı.")
        raise ValueError(f"Görselde QR veya barkod bulunamadı: '{os.path.basename(image_path)}'")

    # ----------------------------------------------------------------------
    # PDF Operations
    # ----------------------------------------------------------------------
    def create_pdf(self, image_paths: List[str], output_path: Optional[str] = None, output_dir: Optional[str] = None) -> str:
        if not image_paths:
            raise ValueError("No images provided to create PDF.")

        for p in image_paths:
            if not os.path.exists(p):
                raise FileNotFoundError(f"Image file does not exist: {p}")

        if not output_path:
            output_path = self._resolve_output_path(image_paths[0], "pdf", output_dir, suffix="_combined")

        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        cmd = ["magick"] + list(image_paths) + [str(out)]
        self._run_cmd(cmd, desc="PDF creation from images")
        return str(out)

    def merge_pdfs(self, pdf_paths: List[str], output_path: Optional[str] = None, output_dir: Optional[str] = None) -> str:
        if len(pdf_paths) < 2:
            raise ValueError("En az 2 PDF dosyası seçilmelidir.")

        for p in pdf_paths:
            if not os.path.exists(p):
                raise FileNotFoundError(f"PDF file does not exist: {p}")

        if not output_path:
            output_path = self._resolve_output_path(pdf_paths[0], "pdf", output_dir, suffix="_merged")

        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        if shutil.which("pdfunite"):
            cmd = ["pdfunite"] + list(pdf_paths) + [str(out)]
            self._run_cmd(cmd, desc="PDF merge (pdfunite)")
            return str(out)
        elif shutil.which("gs"):
            cmd = [
                "gs", "-dBATCH", "-dNOPAUSE", "-q",
                "-sDEVICE=pdfwrite", f"-sOutputFile={str(out)}"
            ] + list(pdf_paths)
            self._run_cmd(cmd, desc="PDF merge (ghostscript)")
            return str(out)
        else:
            cmd = ["magick"] + list(pdf_paths) + [str(out)]
            self._run_cmd(cmd, desc="PDF merge (magick)")
            return str(out)

    def split_pdf(self, pdf_path: str, output_dir: Optional[str] = None) -> List[str]:
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        pdf_p = Path(pdf_path).resolve()
        out_dir = Path(output_dir).resolve() if output_dir else pdf_p.parent / f"{pdf_p.stem}_pages"
        out_dir.mkdir(parents=True, exist_ok=True)

        if shutil.which("pdfseparate"):
            pattern = str(out_dir / f"{pdf_p.stem}_page_%d.pdf")
            cmd = ["pdfseparate", str(pdf_p), pattern]
            self._run_cmd(cmd, desc="PDF split")
            return sorted([str(p) for p in out_dir.glob("*.pdf")])
        else:
            pattern = str(out_dir / f"{pdf_p.stem}_page_%d.pdf")
            cmd = ["magick", str(pdf_p), pattern]
            self._run_cmd(cmd, desc="PDF split (magick)")
            return sorted([str(p) for p in out_dir.glob("*.pdf")])

    def organize_pdf(
        self,
        pdf_path: str,
        rotate_deg: int = 90,
        reverse_pages: bool = False,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Rotates or reverses pages in a PDF document."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        if not output_path:
            output_path = self._resolve_output_path(pdf_path, "pdf", output_dir, suffix="_organized")

        cmd = ["magick", "-density", "150", pdf_path]
        if rotate_deg:
            cmd.extend(["-rotate", str(rotate_deg)])
        if reverse_pages:
            cmd.append("-reverse")
        cmd.append(output_path)
        self._run_cmd(cmd, desc="Organize PDF")
        return output_path

    # ----------------------------------------------------------------------
    # Core Tools: Compress, Metadata, Mute, Trim, Join
    # ----------------------------------------------------------------------
    def compress(self, input_path: str, output_path: Optional[str] = None, output_dir: Optional[str] = None, quality: int = 75) -> str:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"File not found: {input_path}")

        ext = self.normalize_extension(input_path)
        if not output_path:
            output_path = self._resolve_output_path(input_path, ext, output_dir, suffix="_compressed")

        if ext in IMAGE_FORMATS:
            cmd = ["magick", input_path, "-strip", "-quality", str(quality), output_path]
            self._run_cmd(cmd, desc="Image compression")
        elif ext in VIDEO_FORMATS:
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-vcodec", "libx264", "-crf", "28",
                "-preset", "fast", "-c:a", "aac", "-b:a", "128k",
                output_path
            ]
            self._run_cmd(cmd, desc="Video compression")
        elif ext in AUDIO_FORMATS:
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-vn", "-b:a", "128k", output_path
            ]
            self._run_cmd(cmd, desc="Audio compression")
        elif ext == "pdf":
            if shutil.which("gs"):
                cmd = [
                    "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
                    "-dPDFSETTINGS=/ebook", "-dNOPAUSE", "-dQUIET", "-dBATCH",
                    f"-sOutputFile={output_path}", input_path
                ]
                self._run_cmd(cmd, desc="PDF compression (gs)")
            else:
                cmd = ["magick", input_path, "-compress", "jpeg", "-quality", str(quality), output_path]
                self._run_cmd(cmd, desc="PDF compression")
        else:
            raise NotImplementedError(f"Compression not implemented for format: {ext}")

        return output_path

    def remove_metadata(self, input_path: str, output_path: Optional[str] = None, output_dir: Optional[str] = None) -> str:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"File not found: {input_path}")

        ext = self.normalize_extension(input_path)
        if not output_path:
            output_path = self._resolve_output_path(input_path, ext, output_dir, suffix="_clean")

        if ext in IMAGE_FORMATS:
            cmd = ["magick", input_path, "-strip", output_path]
            self._run_cmd(cmd, desc="Metadata removal (image)")
        elif ext in VIDEO_FORMATS or ext in AUDIO_FORMATS:
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-map_metadata", "-1", "-c", "copy",
                output_path
            ]
            self._run_cmd(cmd, desc="Metadata removal (media)")
        elif ext == "pdf":
            if shutil.which("gs"):
                cmd = [
                    "gs", "-sDEVICE=pdfwrite", "-dNOPAUSE", "-dQUIET", "-dBATCH",
                    f"-sOutputFile={output_path}", input_path
                ]
                self._run_cmd(cmd, desc="Metadata removal (PDF)")
            else:
                shutil.copy2(input_path, output_path)
        else:
            raise NotImplementedError(f"Remove metadata not implemented for format: {ext}")

        return output_path

    def mute_video(self, video_path: str, output_path: Optional[str] = None, output_dir: Optional[str] = None) -> str:
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        ext = self.normalize_extension(video_path)
        if not output_path:
            output_path = self._resolve_output_path(video_path, ext, output_dir, suffix="_muted")

        cmd = ["ffmpeg", "-y", "-i", video_path, "-an", "-c:v", "copy", output_path]
        self._run_cmd(cmd, desc="Mute video")
        return output_path

    def trim_media(
        self,
        input_path: str,
        start_time: str = "0",
        duration: Optional[str] = None,
        end_time: Optional[str] = None,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"File not found: {input_path}")

        ext = self.normalize_extension(input_path)
        if not output_path:
            output_path = self._resolve_output_path(input_path, ext, output_dir, suffix="_trimmed")

        cmd = ["ffmpeg", "-y", "-ss", str(start_time), "-i", input_path]
        if duration:
            cmd.extend(["-t", str(duration)])
        elif end_time:
            cmd.extend(["-to", str(end_time)])

        cmd.extend(["-c", "copy", output_path])
        self._run_cmd(cmd, desc="Trim media")
        return output_path

    def join_videos(self, video_paths: List[str], output_path: Optional[str] = None, output_dir: Optional[str] = None) -> str:
        if len(video_paths) < 2:
            raise ValueError("En az 2 video dosyası gereklidir.")

        for v in video_paths:
            if not os.path.exists(v):
                raise FileNotFoundError(f"Video file not found: {v}")

        ext = self.normalize_extension(video_paths[0])
        if not output_path:
            output_path = self._resolve_output_path(video_paths[0], ext, output_dir, suffix="_joined")

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            for vp in video_paths:
                escaped = os.path.abspath(vp).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")
            concat_list = f.name

        try:
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list, "-c", "copy", output_path
            ]
            self._run_cmd(cmd, desc="Join videos")
            return output_path
        finally:
            if os.path.exists(concat_list):
                os.remove(concat_list)

    # ----------------------------------------------------------------------
    # Archives, Subtitles, Tabular & Document Conversions
    # ----------------------------------------------------------------------
    def extract_archive(self, archive_path: str, output_dir: Optional[str] = None) -> str:
        if not os.path.exists(archive_path):
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        arch = Path(archive_path).resolve()
        dest = Path(output_dir).resolve() if output_dir else arch.parent / f"{arch.stem}_extracted"
        dest.mkdir(parents=True, exist_ok=True)

        if zipfile.is_zipfile(arch):
            with zipfile.ZipFile(arch, "r") as z:
                z.extractall(dest)
        elif tarfile.is_tarfile(arch):
            with tarfile.open(arch, "r:*") as t:
                t.extractall(dest)
        elif str(arch).lower().endswith(".gz"):
            out_file = dest / arch.stem
            with gzip.open(arch, "rb") as f_in, open(out_file, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            shutil.unpack_archive(str(arch), str(dest))

        return str(dest)

    def convert_archive(self, archive_path: str, target_format: str, output_path: str) -> str:
        """Converts between ZIP, TAR, and GZ archive formats."""
        with tempfile.TemporaryDirectory() as tmp_extract:
            self.extract_archive(archive_path, tmp_extract)
            tgt = target_format.lower().lstrip(".")
            if tgt == "zip":
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, _, files in os.walk(tmp_extract):
                        for file in files:
                            full = os.path.join(root, file)
                            rel = os.path.relpath(full, tmp_extract)
                            zf.write(full, rel)
            elif tgt == "tar":
                with tarfile.open(output_path, "w") as tf:
                    tf.add(tmp_extract, arcname="")
            elif tgt == "gz":
                with tarfile.open(output_path, "w:gz") as tf:
                    tf.add(tmp_extract, arcname="")
            else:
                raise NotImplementedError(f"Unsupported archive target: {tgt}")
        return output_path

    def convert_subtitle(self, input_path: str, target_format: str, output_path: str) -> str:
        """Converts between SRT, VTT, and plain text."""
        with open(input_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        src_ext = self.normalize_extension(input_path)
        tgt = target_format.lower().lstrip(".")

        if tgt == "vtt":
            lines = content.splitlines()
            out_lines = ["WEBVTT", ""]
            for line in lines:
                if "-->" in line:
                    line = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", line)
                out_lines.append(line)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(out_lines) + "\n")
            return output_path

        if tgt == "srt":
            lines = content.splitlines()
            out_lines = []
            for line in lines:
                if line.strip().startswith("WEBVTT"):
                    continue
                if "-->" in line:
                    line = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", line)
                out_lines.append(line)
            cleaned = "\n".join(out_lines).strip()
            # Ensure cue numbering if coming from simple VTT
            blocks = [b.strip() for b in re.split(r"\n\s*\n", cleaned) if b.strip()]
            numbered = []
            for idx, b in enumerate(blocks, 1):
                b_lines = b.splitlines()
                if b_lines and not b_lines[0].strip().isdigit():
                    numbered.append(f"{idx}\n{b}")
                else:
                    numbered.append(b)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(numbered) + "\n")
            return output_path

        if tgt == "txt":
            lines = content.splitlines()
            txt_lines = []
            for line in lines:
                s = line.strip()
                if not s or s.startswith("WEBVTT") or s.isdigit() or "-->" in s:
                    continue
                txt_lines.append(re.sub(r"<[^>]+>", "", s))
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(txt_lines) + "\n")
            return output_path

        raise NotImplementedError(f"Unsupported subtitle conversion {src_ext} -> {tgt}")

    def _convert_tabular(self, input_path: str, output_path: str, src_ext: str, tgt_ext: str) -> str:
        """Converts CSV <-> TSV <-> PDF/HTML."""
        in_delim = "\t" if src_ext == "tsv" else ","
        with open(input_path, "r", encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv.reader(f, delimiter=in_delim))

        if tgt_ext in ("csv", "tsv"):
            out_delim = "\t" if tgt_ext == "tsv" else ","
            with open(output_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, delimiter=out_delim)
                writer.writerows(rows)
            return output_path

        if tgt_ext == "pdf":
            text_repr = "\n".join(["  |  ".join(r) for r in rows])
            with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as tf:
                tf.write(text_repr)
                tmp_txt = tf.name
            try:
                self._run_cmd(["magick", "-size", "800x1100", f"caption:{text_repr[:2000]}", output_path], desc="CSV/TSV to PDF")
                return output_path
            finally:
                if os.path.exists(tmp_txt):
                    os.remove(tmp_txt)

        raise NotImplementedError(f"Tabular conversion {src_ext} -> {tgt_ext} not supported.")

    def _convert_document(self, input_path: str, output_path: str, src_ext: str, tgt_ext: str) -> str:
        """Converts Markdown, Text, HTML, and PDF documents."""
        if src_ext == "pdf" and tgt_ext in ("txt", "md", "html"):
            if shutil.which("pdftotext"):
                with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
                    tmp_txt = tf.name
                try:
                    self._run_cmd(["pdftotext", input_path, tmp_txt], desc="PDF to text")
                    with open(tmp_txt, "r", encoding="utf-8", errors="replace") as f:
                        txt = f.read()
                    if tgt_ext == "html":
                        body = "<br>\n".join(html.escape(line) for line in txt.splitlines())
                        out_str = f"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body><p>{body}</p></body></html>"
                    else:
                        out_str = txt
                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(out_str)
                    return output_path
                finally:
                    if os.path.exists(tmp_txt):
                        os.remove(tmp_txt)

        if src_ext in ("txt", "md", "rtf", "html"):
            with open(input_path, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read()

            if tgt_ext == "txt":
                clean = re.sub(r"<[^>]+>", "", raw) if src_ext == "html" else raw
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(clean)
                return output_path

            if tgt_ext == "md":
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(raw)
                return output_path

            if tgt_ext == "html":
                lines = []
                for line in raw.splitlines():
                    if line.startswith("# "):
                        lines.append(f"<h1>{html.escape(line[2:])}</h1>")
                    elif line.startswith("## "):
                        lines.append(f"<h2>{html.escape(line[3:])}</h2>")
                    elif line.startswith("### "):
                        lines.append(f"<h3>{html.escape(line[4:])}</h3>")
                    elif line.startswith("- "):
                        lines.append(f"<li>{html.escape(line[2:])}</li>")
                    else:
                        lines.append(f"<p>{html.escape(line)}</p>")
                doc = "<!DOCTYPE html>\n<html><head><meta charset='utf-8'><style>body{font-family:sans-serif;max-width:720px;margin:2rem auto;line-height:1.6;}</style></head><body>\n" + "\n".join(lines) + "\n</body></html>"
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(doc)
                return output_path

            if tgt_ext in ("pdf", "png", "jpg"):
                snippet = raw[:3000] if raw.strip() else " "
                cmd = [
                    "magick", "-size", "800x1100",
                    "-background", "white", "-fill", "#243B2B",
                    "-pointsize", "16",
                    f"caption:{snippet}",
                    output_path
                ]
                self._run_cmd(cmd, desc=f"{src_ext.upper()} to {tgt_ext.upper()}")
                return output_path

        raise NotImplementedError(f"Conversion from {src_ext} to {tgt_ext} is not supported directly.")

    # ----------------------------------------------------------------------
    # Unified Tool Execution Dispatcher (for quick 1-click tools)
    # ----------------------------------------------------------------------
    def execute_tool(
        self,
        tool_id: str,
        file_paths: List[str],
        output_dir: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Executes any of the 27 FeatureCatalog tools and returns output file paths."""
        if not file_paths:
            raise ValueError("İşlem için dosya seçilmedi.")
        params = params or {}
        outputs: List[str] = []

        # Multi-file tools
        if tool_id == "createPDF":
            outputs.append(self.create_pdf(file_paths, output_dir=output_dir))
            return outputs
        if tool_id == "mergePDF":
            outputs.append(self.merge_pdfs(file_paths, output_dir=output_dir))
            return outputs
        if tool_id == "joinVideos":
            outputs.append(self.join_videos(file_paths, output_dir=output_dir))
            return outputs
        if tool_id == "createCollage":
            outputs.append(self.create_collage(
                file_paths,
                columns=params.get("columns", 2),
                padding=params.get("padding", 16),
                bg_color=params.get("bg_color", "#F9F6ED"),
                output_dir=output_dir,
            ))
            return outputs

        # Per-file tools
        for fp in file_paths:
            if tool_id == "compress":
                outputs.append(self.compress(fp, output_dir=output_dir, quality=params.get("quality", 75)))
            elif tool_id == "removeMetadata":
                outputs.append(self.remove_metadata(fp, output_dir=output_dir))
            elif tool_id == "cropImage":
                outputs.append(self.crop_image(
                    fp,
                    x=params.get("x", 0),
                    y=params.get("y", 0),
                    width=params.get("width"),
                    height=params.get("height"),
                    aspect_ratio=params.get("aspect_ratio"),
                    output_dir=output_dir,
                ))
            elif tool_id == "editImage":
                outputs.append(self.edit_image(
                    fp,
                    rotate_deg=params.get("rotate_deg", 90),
                    flip_horizontal=params.get("flip_horizontal", False),
                    flip_vertical=params.get("flip_vertical", False),
                    scale_percent=params.get("scale_percent", 100),
                    brightness=params.get("brightness", 0),
                    contrast=params.get("contrast", 0),
                    saturation=params.get("saturation", 100),
                    output_dir=output_dir,
                ))
            elif tool_id == "frameImage":
                outputs.append(self.frame_image(
                    fp,
                    padding=params.get("padding", 48),
                    bg_color=params.get("bg_color", "#F9F6ED"),
                    output_dir=output_dir,
                ))
            elif tool_id == "annotateImage":
                outputs.append(self.annotate_image(
                    fp,
                    text=params.get("text", "Nashi"),
                    color=params.get("color", "#E3B859"),
                    output_dir=output_dir,
                ))
            elif tool_id == "redactImage":
                outputs.append(self.redact_image(
                    fp,
                    x=params.get("x"),
                    y=params.get("y"),
                    width=params.get("width"),
                    height=params.get("height"),
                    mode=params.get("mode", "pixelate"),
                    output_dir=output_dir,
                ))
            elif tool_id == "muteVideo":
                outputs.append(self.mute_video(fp, output_dir=output_dir))
            elif tool_id in ("trimVideo", "trimAudio"):
                outputs.append(self.trim_media(
                    fp,
                    start_time=str(params.get("start_time", "0")),
                    duration=str(params["duration"]) if params.get("duration") else None,
                    end_time=str(params["end_time"]) if params.get("end_time") else None,
                    output_dir=output_dir,
                ))
            elif tool_id == "cropVideo":
                outputs.append(self.crop_video(
                    fp,
                    aspect_ratio=params.get("aspect_ratio", (1, 1)),
                    output_dir=output_dir,
                ))
            elif tool_id == "changeVideoSpeed":
                outputs.append(self.change_video_speed(
                    fp,
                    speed=params.get("speed", 1.5),
                    output_dir=output_dir,
                ))
            elif tool_id == "videoSnapshots":
                outputs.extend(self.video_snapshots(fp, count=params.get("count", 4), output_dir=output_dir))
            elif tool_id == "splitVideo":
                outputs.extend(self.split_video(fp, parts=params.get("parts", 2), output_dir=output_dir))
            elif tool_id == "normalizeAudio":
                outputs.append(self.normalize_audio(fp, output_dir=output_dir))
            elif tool_id == "audioChannels":
                outputs.append(self.convert_audio_channels(fp, channels=params.get("channels", 1), output_dir=output_dir))
            elif tool_id == "audioToVideo":
                outputs.append(self.audio_to_video(fp, output_dir=output_dir))
            elif tool_id == "redactVideo":
                outputs.append(self.redact_video(fp, output_dir=output_dir))
            elif tool_id == "redactAudio":
                outputs.append(self.redact_audio(
                    fp,
                    start_sec=params.get("start_sec", 0.0),
                    duration_sec=params.get("duration_sec", 2.0),
                    output_dir=output_dir,
                ))
            elif tool_id == "splitPDF":
                outputs.extend(self.split_pdf(fp, output_dir=output_dir))
            elif tool_id == "organizePDF":
                outputs.append(self.organize_pdf(
                    fp,
                    rotate_deg=params.get("rotate_deg", 90),
                    reverse_pages=params.get("reverse_pages", False),
                    output_dir=output_dir,
                ))
            elif tool_id == "extractArchive":
                outputs.append(self.extract_archive(fp, output_dir=output_dir))
            else:
                raise NotImplementedError(f"Tool '{tool_id}' is not supported.")

        return outputs

    # ----------------------------------------------------------------------
    # Web Link Probing & Deep Crawler (IDM / macOS WebDownloadEngine Parity)
    # ----------------------------------------------------------------------
    # ----------------------------------------------------------------------
    # Web Link Probing & Deep Crawler (IDM / macOS WebDownloadEngine Parity)
    # ----------------------------------------------------------------------
    def _extract_obfuscated_player_stream(self, embed_url: str, parent_referer: str) -> Optional[str]:
        """Resolves obfuscated custom streaming players (e.g. Rapidrame / HDFilmCehennemi / Playmix)."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Referer": parent_referer,
            }
            req = urllib.request.Request(embed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                embed_html = resp.read().decode("utf-8", errors="ignore")

            # Look for sources: [{file: <variable_name>, type: "hls"}]
            m = re.search(r'sources:\s*\[\{\s*file:\s*([a-zA-Z0-9_]+)', embed_html)
            if not m:
                return None
            var_name = m.group(1)

            v_idx = embed_html.find(f"var {var_name}")
            if v_idx == -1:
                return None

            s_idx = embed_html.rfind("<script", 0, v_idx)
            e_idx = embed_html.find("</script>", v_idx)
            js_part = embed_html[s_idx:e_idx]
            js_part = re.sub(r"<script[^>]*>", "", js_part)

            embed_parsed = urllib.parse.urlparse(embed_url)
            mock_browser = f"""
            const location = {{
                hostname: "{embed_parsed.netloc}",
                host: "{embed_parsed.netloc}",
                href: "{embed_url}",
                protocol: "{embed_parsed.scheme}:"
            }};
            const document = {{ location: location }};
            const window = {{ location: location, document: document }};
            """
            full_js = mock_browser + js_part + f"\nconsole.log({var_name});\n"
            proc = subprocess.run(["node", "-e", full_js], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8)
            resolved_url = proc.stdout.strip()
            if resolved_url.startswith("http"):
                return resolved_url
        except Exception:
            pass
        return None

    def inspect_web_link(self, url: str) -> Dict[str, Any]:
        """Probes a web page, streaming site, or direct file URL to extract available media qualities."""
        if not self.is_web_url(url):
            raise ValueError(f"Geçersiz bağlantı: {url}")

        yt_dlp_bin = shutil.which("yt-dlp") or str(Path.home() / ".local/bin/yt-dlp")
        has_yt_dlp = os.path.exists(yt_dlp_bin) and os.access(yt_dlp_bin, os.X_OK)

        # 1. Deep Crawler: Inspect if this is a streaming/film page with iframe embed player
        film_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        film_resolved_stream = None
        film_title = "Web Filmi / Medyası"
        film_poster = ""
        film_referer = url

        try:
            req_init = urllib.request.Request(url, headers=film_headers)
            with urllib.request.urlopen(req_init, timeout=12) as resp:
                top_html = resp.read(512 * 1024).decode("utf-8", errors="ignore")
                t_m = re.search(r'<title[^>]*>([^<]+)</title>', top_html, re.I)
                if t_m:
                    film_title = t_m.group(1).split("—")[0].split("-")[0].strip()

                # Look for iframe embed player
                iframes = re.findall(r'<iframe[^>]+src=[\"\']([^\"\']+)[\"\']', top_html, re.I)
                for ifr in iframes:
                    if ifr.startswith("//"):
                        ifr = "https:" + ifr
                    elif ifr.startswith("/"):
                        ifr = urllib.parse.urljoin(url, ifr)
                    if any(k in ifr for k in ["embed", "video", "player", "rapid", "mobi", "stream"]):
                        stream_found = self._extract_obfuscated_player_stream(ifr, parent_referer=url)
                        if stream_found:
                            film_resolved_stream = stream_found
                            film_referer = ifr
                            break
        except Exception:
            pass

        # If a decrypted HLS stream was extracted from the custom player
        probe_target = film_resolved_stream if film_resolved_stream else url
        probe_referer = film_referer if film_resolved_stream else url

        # 2. Try yt-dlp JSON dump on the target (covers YouTube, direct HLS streams, Vimeo, etc.)
        if has_yt_dlp:
            cmd = [
                yt_dlp_bin,
                "-J",
                "--no-playlist",
                "--no-colors",
                "--no-warnings",
                "--socket-timeout", "15",
                "--referer", probe_referer,
                probe_target,
            ]
            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
                if proc.returncode == 0 and proc.stdout.strip():
                    info = json.loads(proc.stdout)
                    item = info.get("entries", [info])[0] if "entries" in info else info
                    title = item.get("title") or film_title
                    if title in ("master", "playlist", "video") and film_title:
                        title = film_title
                    duration = item.get("duration")
                    thumbnail = item.get("thumbnail") or ""
                    extractor = item.get("extractor_key") or urllib.parse.urlparse(url).netloc
                    raw_formats = item.get("formats", [])

                    # Parse unique video resolutions
                    qualities = {}
                    for f in raw_formats:
                        h = f.get("height")
                        fid = f.get("format_id")
                        ext = f.get("ext", "mp4")
                        vcodec = f.get("vcodec", "none")
                        filesize = f.get("filesize") or f.get("filesize_approx")
                        if h and isinstance(h, int) and h > 0 and vcodec != "none":
                            label = f"{h}p ({ext.upper()})"
                            if h not in qualities or (filesize and not qualities[h].get("filesize")):
                                qualities[h] = {
                                    "format_id": fid,
                                    "height": h,
                                    "ext": ext,
                                    "label": label,
                                    "filesize": filesize,
                                }

                    sorted_heights = sorted(qualities.keys(), reverse=True)
                    format_list = [qualities[h] for h in sorted_heights]

                    return {
                        "url": probe_target,
                        "title": title,
                        "duration": duration,
                        "thumbnail": thumbnail,
                        "site": extractor,
                        "kind": "video" if format_list or item.get("vcodec") != "none" else "audio",
                        "formats": format_list,
                        "has_audio": any(f.get("acodec") != "none" for f in raw_formats),
                        "referer": probe_referer,
                    }
            except Exception:
                pass

        # 3. Direct file fallback or generic crawler
        parsed = urllib.parse.urlparse(url)
        return {
            "url": probe_target,
            "title": film_title or os.path.basename(parsed.path) or parsed.netloc,
            "duration": None,
            "thumbnail": "",
            "site": parsed.netloc,
            "kind": "video",
            "formats": [{"format_id": "best", "height": 0, "ext": "mp4", "label": "En Yüksek Kalite (Otomatik)"}],
            "has_audio": True,
            "referer": probe_referer,
        }

    # ----------------------------------------------------------------------
    # Web Link Download (yt-dlp / direct HTTP download)
    # ----------------------------------------------------------------------
    def download_web_link(
        self,
        url: str,
        mode: str = "video",
        max_height: Optional[int] = None,
        format_id: Optional[str] = None,
        output_dir: Optional[str] = None,
        referer: Optional[str] = None,
    ) -> str:
        """Downloads a public media URL or direct image/file into output_dir with targeted quality."""
        if not self.is_web_url(url):
            raise ValueError(f"Geçersiz bağlantı: {url}")

        dest_dir = Path(output_dir).expanduser().resolve() if output_dir else Path.home() / "Downloads"
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Detect direct static file extension
        parsed = urllib.parse.urlparse(url)
        path_lower = parsed.path.lower()
        direct_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".mp4", ".mov", ".webm", ".mkv", ".mp3", ".wav", ".m4a", ".flac", ".pdf", ".zip")
        is_direct_file = any(path_lower.endswith(ext) for ext in direct_exts)

        yt_dlp_bin = shutil.which("yt-dlp") or str(Path.home() / ".local/bin/yt-dlp")
        has_yt_dlp = os.path.exists(yt_dlp_bin) and os.access(yt_dlp_bin, os.X_OK)

        # If URL is an HTML page rather than a direct stream, probe it first to resolve hidden stream
        active_url = url
        active_referer = referer or url
        if not is_direct_file and ("txt/master.txt" not in url and ".m3u8" not in url):
            try:
                inspected = self.inspect_web_link(url)
                if inspected and inspected.get("url") and inspected["url"] != url:
                    active_url = inspected["url"]
                    active_referer = inspected.get("referer", active_referer)
            except Exception:
                pass

        # Use yt-dlp for all video/audio pages, youtube, social media or when direct file not evident
        if has_yt_dlp and not is_direct_file:
            out_tmpl = str(dest_dir / "%(title).80s [%(id).20s].%(ext)s")
            cmd = [
                yt_dlp_bin,
                "--no-playlist",
                "--no-colors",
                "--windows-filenames",
                "--trim-filenames", "160",
                "--downloader", "native",
                "--hls-use-mpegts",
                "-o", out_tmpl,
            ]
            if active_referer:
                cmd.extend(["--referer", active_referer])

            if mode == "audio":
                cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
            elif mode == "thumbnail":
                cmd.extend(["--write-thumbnail", "--skip-download"])
            else:
                # Video: check if specific format_id or max_height is requested
                if format_id and format_id not in ("best", "direct"):
                    fmt_spec = f"{format_id}+bestaudio/best"
                elif max_height and max_height > 0:
                    fmt_spec = f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={max_height}][ext=mp4]/bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]"
                else:
                    fmt_spec = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

                cmd.extend([
                    "--format", fmt_spec,
                    "--merge-output-format", "mp4",
                ])
            cmd.extend(["--print", "after_move:filepath", active_url])
            try:
                out = self._run_cmd(cmd, desc="yt-dlp media download")
                lines = [l.strip() for l in out.splitlines() if l.strip() and os.path.exists(l.strip())]
                if lines:
                    return lines[-1]
            except Exception as e:
                if any(k in active_url.lower() for k in ["youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "cdn", "hls", "master"]):
                    raise RuntimeError(f"Medya indirilemedi ({active_url}): {e}")

        # Direct HTTP/HTTPS download fallback (only for direct files or when yt-dlp is unavailable)
        fname = os.path.basename(parsed.path) or "downloaded_media"
        if "." not in fname:
            if mode == "image":
                fname += ".png"
            elif mode == "audio":
                fname += ".mp3"
            else:
                fname += ".mp4"
        target = dest_dir / fname
        counter = 2
        while target.exists():
            stem, ext = os.path.splitext(fname)
            target = dest_dir / f"{stem}_{counter}{ext}"
            counter += 1

        req = urllib.request.Request(active_url, headers={"User-Agent": "Nashi/2.0 (Linux)"})
        with urllib.request.urlopen(req, timeout=15) as resp, open(target, "wb") as f_out:
            shutil.copyfileobj(resp, f_out)
        return str(target)


if __name__ == "__main__":
    engine = NashiEngine()
    print("NashiEngine 2.0 initialized successfully.")
    print("Targets for ['a.jpg', 'b.png']:", engine.get_available_targets_for_files(["a.jpg", "b.png"]))
    print("Tools for ['a.jpg']:", engine.get_available_tools_for_files(["a.jpg"]))
    print("Tools for ['a.jpg', 'b.jpg']:", engine.get_available_tools_for_files(["a.jpg", "b.jpg"]))
