"""Nashi Linux - Storage & State Management.

Manages persistent application state, user preferences, and export history
(Nashi Library) following XDG Base Directory specifications.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("nashi.store")

# Default user configuration matching official Nashi desktop preferences
DEFAULT_CONFIG: Dict[str, Any] = {
    "theme": "dark",               # 'dark', 'light', 'catppuccin', 'rosepine'
    "wheel_finish": "glass",       # 'glass', 'metallic'
    "wheel_scale": 1.0,            # 0.85 (compact), 1.0 (normal), 1.15 (large)
    "convert_modifier": "Shift",   # Drag modifier for Convert wheel
    "tools_modifier": "Ctrl",      # Drag modifier for Tools wheel
    "actions_modifier": "Alt",     # Drag modifier for File Actions wheel
    "drag_wheel_enabled": True,    # Enable global drag + modifier wheel trigger
    "sound_feedback": True,        # Subtle audio/visual feedback
    "animations": True,            # Smooth entrance/hover animations
    "default_output_dir": "",      # Empty string = save next to original file (Nashi/Tangerine default); or custom dir
    "download_dir": str(Path.home() / "Downloads"),
    "language": "tr",              # 'tr' or 'en'
}

MAX_HISTORY_ENTRIES = 50


def get_default_data_dir() -> Path:
    """Return XDG compliant data directory for Nashi (~/.local/share/nashi)."""
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        base = Path(xdg_data)
    else:
        base = Path.home() / ".local" / "share"
    return base / "nashi"


class NashiStore:
    """Persistent storage manager for Nashi Linux."""

    def __init__(self, data_dir: Optional[Union[str, Path]] = None):
        if data_dir is not None:
            self.data_dir = Path(data_dir).expanduser().resolve()
        else:
            self.data_dir = get_default_data_dir().expanduser().resolve()

        self.library_path = self.data_dir / "library.json"
        self.config_path = self.data_dir / "config.json"

        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._library: List[Dict[str, Any]] = self._load_library()
        self._config: Dict[str, Any] = self._load_config()

    def _atomic_write_json(self, file_path: Path, data: Any) -> None:
        """Write JSON data to a file atomically to prevent corruption."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.data_dir,
                delete=False,
            ) as tf:
                temp_file = Path(tf.name)
                json.dump(data, tf, indent=2, ensure_ascii=False)
                tf.flush()
                os.fsync(tf.fileno())

            os.replace(temp_file, file_path)
            temp_file = None
        except Exception as e:
            logger.error("Failed to write to %s: %s", file_path, e)
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            raise

    def _load_library(self) -> List[Dict[str, Any]]:
        if not self.library_path.exists():
            return []
        try:
            with open(self.library_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data[:MAX_HISTORY_ENTRIES]
                return []
        except Exception as e:
            logger.warning("Could not read library.json (%s), starting fresh.", e)
            return []

    def _load_config(self) -> Dict[str, Any]:
        config = dict(DEFAULT_CONFIG)
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                    if isinstance(user_data, dict):
                        config.update(user_data)
            except Exception as e:
                logger.warning("Could not read config.json (%s), using defaults.", e)
        return config

    def reload(self) -> None:
        """Reload library and config from disk."""
        self._library = self._load_library()
        self._config = self._load_config()

    # -------------------------------------------------------------------------
    # Library / Export History API
    # -------------------------------------------------------------------------

    def add_export(
        self,
        source_name: str,
        output_path: str,
        fmt: str,
        file_size: Optional[int] = None,
        action_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an export or tool operation entry into library history."""
        resolved_output = Path(output_path).expanduser().resolve()
        resolved_str = str(resolved_output)

        if file_size is None:
            try:
                if resolved_output.exists():
                    if resolved_output.is_dir():
                        file_size = sum(
                            f.stat().st_size for f in resolved_output.rglob("*") if f.is_file()
                        )
                    else:
                        file_size = resolved_output.stat().st_size
                else:
                    file_size = 0
            except OSError:
                file_size = 0

        entry = {
            "id": uuid.uuid4().hex,
            "source_name": str(source_name),
            "output_path": resolved_str,
            "format": str(fmt).lower().lstrip("."),
            "action_title": action_title or f"→ {str(fmt).upper().lstrip('.')}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_size": file_size,
        }

        # Deduplicate identical consecutive output_path if re-exported
        self._library = [e for e in self._library if e.get("output_path") != resolved_str]
        self._library.insert(0, entry)

        if len(self._library) > MAX_HISTORY_ENTRIES:
            self._library = self._library[:MAX_HISTORY_ENTRIES]

        self._atomic_write_json(self.library_path, self._library)
        return entry

    def get_recent_exports(self, query: str = "") -> List[Dict[str, Any]]:
        """Return recent exports (up to 50), optionally filtered by search query."""
        items = list(self._library)
        for item in items:
            out_p = item.get("output_path", "")
            item["exists"] = bool(out_p and os.path.exists(out_p))
        if not query or not query.strip():
            return items
        q = query.strip().lower()
        filtered = []
        for item in items:
            haystack = " ".join([
                str(item.get("source_name", "")),
                str(os.path.basename(item.get("output_path", ""))),
                str(item.get("format", "")),
                str(item.get("action_title", "")),
            ]).lower()
            if q in haystack:
                filtered.append(item)
        return filtered

    def remove_export(self, export_id: str) -> bool:
        initial_len = len(self._library)
        self._library = [e for e in self._library if e.get("id") != export_id]
        if len(self._library) != initial_len:
            self._atomic_write_json(self.library_path, self._library)
            return True
        return False

    def clear_history(self) -> None:
        self._library = []
        self._atomic_write_json(self.library_path, self._library)

    # -------------------------------------------------------------------------
    # Preferences / Configuration API
    # -------------------------------------------------------------------------

    def get_preference(self, key: str, default: Any = None) -> Any:
        if key in self._config:
            return self._config[key]
        if default is not None:
            return default
        return DEFAULT_CONFIG.get(key)

    def set_preference(self, key: str, value: Any) -> None:
        self._config[key] = value
        self._atomic_write_json(self.config_path, self._config)

    def set_drag_modifier(self, wheel_kind: str, modifier: str) -> bool:
        """Assign a distinct drag modifier ('Shift', 'Ctrl', 'Alt') to a wheel kind.
        Automatically swaps if another wheel already uses that modifier.
        """
        key_map = {
            "convert": "convert_modifier",
            "tools": "tools_modifier",
            "actions": "actions_modifier",
        }
        target_key = key_map.get(wheel_kind)
        if not target_key or modifier not in ("Shift", "Ctrl", "Alt", "Ctrl+Shift", "Alt+Shift"):
            return False

        old_val = self._config.get(target_key, DEFAULT_CONFIG[target_key])
        for k in key_map.values():
            if k != target_key and self._config.get(k) == modifier:
                self._config[k] = old_val

        self._config[target_key] = modifier
        self._atomic_write_json(self.config_path, self._config)
        return True

    def get_all_preferences(self) -> Dict[str, Any]:
        return dict(self._config)

    def reset_preferences(self) -> None:
        self._config = dict(DEFAULT_CONFIG)
        self._atomic_write_json(self.config_path, self._config)


_default_store: Optional[NashiStore] = None


def get_store() -> NashiStore:
    global _default_store
    if _default_store is None:
        _default_store = NashiStore()
    return _default_store
