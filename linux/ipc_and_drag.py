"""
Nashi Linux - Global Drag-Mode Controller, Single-Instance IPC & KDE Wayland Global Shortcuts
Solves:
1. Global drag + modifier detection (LMB held + >=8px drag + Shift/Ctrl/Alt) across KDE Wayland/X11
2. Live wheel mode switching while dragging (Shift -> Convert, Ctrl -> Tools, Alt -> Actions)
3. Single-instance Unix domain socket IPC (/run/user/1000/nashi-ipc.sock) + DBus (org.nashi.App)
4. Automatic KDE Global Shortcuts registration (kglobalshortcutsrc + KWin Scripting with exact Wayland cursorPos).
"""

import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Optional, Callable, Tuple

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from store import NashiStore, get_store


def get_ipc_socket_path() -> str:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return os.path.join(runtime_dir, "nashi-ipc.sock")


def send_ipc_command(cmd: str, mode: str = "", files: Optional[list] = None, timeout_ms: int = 800) -> bool:
    """Sends a JSON command to an already-running Nashi instance. Returns True if delivered."""
    sock_path = get_ipc_socket_path()
    if not os.path.exists(sock_path):
        return False

    payload = json.dumps({
        "cmd": cmd,
        "mode": mode,
        "files": files or [],
    }).encode("utf-8")

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout_ms / 1000.0)
            s.connect(sock_path)
            s.sendall(payload)
        return True
    except Exception:
        return False


def ensure_kde_xwayland_eavesdrop():
    """
    Configures KWin Wayland so XWayland receives modifier + mouse button state
    during global drags, and registers Nashi global shortcuts in kglobalshortcutsrc.
    """
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return

    try:
        cur_mode = subprocess.run(
            ["kreadconfig6", "--file", "kwinrc", "--group", "Xwayland", "--key", "XwaylandEavesdrops"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
        ).stdout.strip()
        cur_mouse = subprocess.run(
            ["kreadconfig6", "--file", "kwinrc", "--group", "Xwayland", "--key", "XwaylandEavesdropsMouse"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
        ).stdout.strip()

        need_reconf = False
        if cur_mode not in ("Modifiers", "All"):
            subprocess.run(
                ["kwriteconfig6", "--file", "kwinrc", "--group", "Xwayland", "--key", "XwaylandEavesdrops", "All"],
                stderr=subprocess.DEVNULL
            )
            need_reconf = True
        if cur_mouse.lower() != "true":
            subprocess.run(
                ["kwriteconfig6", "--file", "kwinrc", "--group", "Xwayland", "--key", "XwaylandEavesdropsMouse", "true"],
                stderr=subprocess.DEVNULL
            )
            need_reconf = True

        if need_reconf:
            subprocess.run(["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"], stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[NashiIPC] KWin Xwayland config warning: {e}")


def register_kde_global_shortcuts(nashi_bin_path: str):
    """
    Registers Nashi desktop services and KWin Scripting global shortcuts so hotkeys
    work anywhere on KDE Plasma Wayland with exact cursor coordinates.
    """
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    icon_path = Path(nashi_bin_path).resolve().parent / "assets" / "NashiIcon.png"

    desktop_entries = {
        "nashi.desktop": (
            "Nashi",
            f'"{nashi_bin_path}" --toggle',
            "Meta+Space",
        ),
        "nashi-convert.desktop": (
            "Nashi Convert Wheel",
            f'"{nashi_bin_path}" --convert',
            "Alt+Shift+C",
        ),
        "nashi-tools.desktop": (
            "Nashi Tools Wheel",
            f'"{nashi_bin_path}" --tools',
            "Alt+Shift+T",
        ),
        "nashi-actions.desktop": (
            "Nashi Actions Wheel",
            f'"{nashi_bin_path}" --actions',
            "Alt+Shift+A",
        ),
    }

    for fname, (title, exec_cmd, _) in desktop_entries.items():
        d_file = apps_dir / fname
        content = (
            "[Desktop Entry]\n"
            f"Name={title}\n"
            "GenericName=File Converter & Toolkit\n"
            f"Exec={exec_cmd}\n"
            f"Icon={icon_path}\n"
            "Terminal=false\n"
            "Type=Application\n"
            "Categories=Utility;\n"
            "NoDisplay=false\n"
        )
        try:
            d_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

    # Register KWin Script that hooks global shortcuts AND sends exact Wayland workspace.cursorPos over DBus
    kwin_js_path = Path(get_ipc_socket_path()).parent / "nashi_kwin_bridge.js"
    kwin_js = """
function notifyNashi(mode) {
    var p = workspace.cursorPos;
    callDBus("org.nashi.App", "/Nashi", "local.nashi.NashiDBusBridge", "triggerWheelAt", mode, Math.round(p.x), Math.round(p.y));
}

var lastCurSent = 0;
workspace.cursorPosChanged.connect(function() {
    var now = Date.now();
    if (now - lastCurSent >= 30) {
        lastCurSent = now;
        var p = workspace.cursorPos;
        callDBus("org.nashi.App", "/Nashi", "local.nashi.NashiDBusBridge", "updateCursorPos", Math.round(p.x), Math.round(p.y));
    }
});

registerShortcut("NashiConvertWheel", "Nashi: Dönüştürme Çarkı (Shift+Space)", "Shift+Space", function() {
    notifyNashi("convert");
});
registerShortcut("NashiToolsWheel", "Nashi: Araçlar Çarkı (Ctrl+Space)", "Ctrl+Space", function() {
    notifyNashi("tools");
});
registerShortcut("NashiActionsWheel", "Nashi: Dosya İşlemleri Çarkı (Alt+Space)", "Alt+Space", function() {
    notifyNashi("actions");
});
registerShortcut("NashiAltConvertWheel", "Nashi: Dönüştürme Çarkı (Alt+Shift+C)", "Alt+Shift+C", function() {
    notifyNashi("convert");
});
registerShortcut("NashiAltToolsWheel", "Nashi: Araçlar Çarkı (Alt+Shift+T)", "Alt+Shift+T", function() {
    notifyNashi("tools");
});
registerShortcut("NashiAltActionsWheel", "Nashi: İşlemler Çarkı (Alt+Shift+A)", "Alt+Shift+A", function() {
    notifyNashi("actions");
});
registerShortcut("NashiDownloadLink", "Nashi: Bağlantı İndir (Ctrl+Shift+D)", "Ctrl+Shift+D", function() {
    var p = workspace.cursorPos;
    callDBus("org.nashi.App", "/Nashi", "local.nashi.NashiDBusBridge", "triggerWheelAt", "download_link", Math.round(p.x), Math.round(p.y));
});
registerShortcut("NashiToggleWindow", "Nashi: Ana Pencere Aç/Gizle (Alt+Shift+N)", "Alt+Shift+N", function() {
    var p = workspace.cursorPos;
    callDBus("org.nashi.App", "/Nashi", "local.nashi.NashiDBusBridge", "triggerWheelAt", "toggle_window", Math.round(p.x), Math.round(p.y));
});
"""
    try:
        kwin_js_path.write_text(kwin_js, encoding="utf-8")
        subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", "nashi_kwin_bridge"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", str(kwin_js_path), "nashi_kwin_bridge"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.start"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"[NashiIPC] KWin script registration warning: {e}")


class NashiDBusBridge(QObject):
    """DBus endpoint (`org.nashi.App` at `/Nashi`) receiving KWin script triggers with exact Wayland cursor coords."""

    triggered = Signal(str, int, int)
    cursor_updated = Signal(int, int)

    @Slot(str, int, int)
    def triggerWheelAt(self, mode: str, x: int, y: int):
        self.triggered.emit(mode, x, y)

    @Slot(int, int)
    def updateCursorPos(self, x: int, y: int):
        self.cursor_updated.emit(x, y)


class GlobalDragController(QObject):
    """
    Port of Nashi's GlobalDragController.cs for Linux (X11 / XWayland + KDE Wayland):
    Polls pointer state & modifier keymap every 40ms:
    - Detects when Left Mouse Button is held and moved >= 8px (active drag gesture)
    - Detects when Shift (Convert), Ctrl (Tools), or Alt (Actions) is pressed during drag
    - Pops the radial wheel right under the cursor (`drag_wheel_requested`)
    - Live switches wheel mode if user presses another modifier while still dragging
    - Tracks cursor movement and auto-dismisses the wheel 180ms after mouse button release if no drop occurred.
    """

    drag_wheel_requested = Signal(str, int, int)   # (mode, cursor_x, cursor_y)
    drag_mode_switched = Signal(str)               # (new_mode)
    drag_cursor_moved = Signal(int, int)           # (cursor_x, cursor_y)
    drag_released = Signal()

    def __init__(self, store: Optional[NashiStore] = None, parent=None, start_polling: bool = True):
        super().__init__(parent)
        self.store = store or get_store()

        self._display = None
        self._root = None
        self._xdnd_atom = None
        self._keycodes = {}
        self._wayland_cursor: Optional[Tuple[int, int]] = None
        self._init_xlib()

        self._down: bool = False
        self._start_pos: Tuple[int, int] = (0, 0)
        self._opened: bool = False
        self._active_mode: Optional[str] = None

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._poll)
        if start_polling:
            self._timer.start()

    def update_wayland_cursor(self, x: int, y: int):
        self._wayland_cursor = (int(x), int(y))

    def _init_xlib(self):
        try:
            from Xlib import display, XK
            self._display = display.Display()
            self._root = self._display.screen().root
            self._xdnd_atom = self._display.intern_atom("XdndSelection")
            for name in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Meta_L", "Super_L", "Escape"):
                ks = XK.string_to_keysym(name)
                kc = self._display.keysym_to_keycode(ks)
                if kc:
                    self._keycodes[name] = kc
        except Exception as e:
            print(f"[GlobalDragController] Xlib init warning: {e}")
            self._display = None

    def _is_key_down(self, keymap: bytes, *names: str) -> bool:
        for name in names:
            kc = self._keycodes.get(name, 0)
            if kc and (kc // 8) < len(keymap):
                if keymap[kc // 8] & (1 << (kc % 8)):
                    return True
        return False

    def is_escape_down(self) -> bool:
        if self._display is None:
            return False
        try:
            km = self._display.query_keymap()
            return self._is_key_down(km, "Escape")
        except Exception:
            return False

    def query_pointer_and_chord(self) -> Tuple[bool, int, int, str, bool]:
        """Returns (left_button_held, root_x, root_y, modifier_chord_str, xdnd_active)."""
        if self._display is None or self._root is None:
            return False, 0, 0, "", False

        try:
            from Xlib import X
            qp = self._root.query_pointer()
            mask = qp.mask
            left_held = bool(mask & X.Button1Mask)

            xdnd_active = False
            if self._xdnd_atom:
                owner = self._display.get_selection_owner(self._xdnd_atom)
                xdnd_active = bool(owner and owner.id != 0)

            km = self._display.query_keymap()
            ctrl = bool(mask & X.ControlMask) or self._is_key_down(km, "Control_L", "Control_R")
            shift = bool(mask & X.ShiftMask) or self._is_key_down(km, "Shift_L", "Shift_R")
            alt = bool(mask & X.Mod1Mask) or self._is_key_down(km, "Alt_L", "Alt_R")

            parts = []
            if ctrl:
                parts.append("Ctrl")
            if alt:
                parts.append("Alt")
            if shift:
                parts.append("Shift")
            chord = "+".join(parts)
            return left_held, int(qp.root_x), int(qp.root_y), chord, xdnd_active
        except Exception:
            return False, 0, 0, "", False

    def resolve_mode_for_chord(self, chord: str) -> Optional[str]:
        if not chord:
            return None
        conv_mod = self.store.get_preference("convert_modifier", "Shift")
        tools_mod = self.store.get_preference("tools_modifier", "Ctrl")
        act_mod = self.store.get_preference("actions_modifier", "Alt")

        if chord == conv_mod:
            return "convert"
        if chord == tools_mod:
            return "tools"
        if chord == act_mod:
            return "actions"
        # Fallback if multiple modifiers or default keys pressed
        if "Shift" in chord and "Ctrl" not in chord and "Alt" not in chord:
            return "convert"
        if "Ctrl" in chord and "Shift" not in chord:
            return "tools"
        if "Alt" in chord and "Shift" not in chord:
            return "actions"
        return None

    def simulate_drag_step(
        self,
        left_held: bool,
        x: int,
        y: int,
        chord: str,
        xdnd_active: bool = False,
        escape: bool = False,
    ):
        """Testable state-machine step used by both real 40ms poll and automated unit tests."""
        if not self.store.get_preference("drag_wheel_enabled", True):
            return

        if escape:
            if self._opened:
                self._down = False
                self._opened = False
                self._active_mode = None
                self.drag_released.emit()
            return

        is_dragging = left_held or xdnd_active

        if not is_dragging:
            if self._down:
                self._down = False
                was_opened = self._opened
                self._opened = False
                self._active_mode = None
                if was_opened:
                    self.drag_released.emit()
            return

        if not self._down:
            self._down = True
            self._start_pos = (x, y)
            self._opened = False
            self._active_mode = None
            if not xdnd_active:
                return

        dist = abs(x - self._start_pos[0]) + abs(y - self._start_pos[1])
        if dist < 8 and not xdnd_active:
            return

        target_x, target_y = self._wayland_cursor if self._wayland_cursor else (x, y)
        mode = self.resolve_mode_for_chord(chord)
        if not self._opened:
            if mode is not None:
                self._opened = True
                self._active_mode = mode
                print(f"[GlobalDragController] Drag chord match: mode={mode} at ({target_x}, {target_y}) [wayland={self._wayland_cursor is not None}], emitting drag_wheel_requested", flush=True)
                self.drag_wheel_requested.emit(mode, target_x, target_y)
        else:
            self.drag_cursor_moved.emit(target_x, target_y)
            if mode is not None and mode != self._active_mode:
                self._active_mode = mode
                self.drag_mode_switched.emit(mode)

    def _poll(self):
        esc = self.is_escape_down()
        left_held, x, y, chord, xdnd_active = self.query_pointer_and_chord()
        self.simulate_drag_step(left_held, x, y, chord, xdnd_active=xdnd_active, escape=esc)


class NashiIPCServer(QObject):
    """Single-instance Unix domain socket & DBus server for Nashi Linux."""

    command_received = Signal(str, str, list, object)  # (cmd, mode, files, cursor_tuple_or_none)
    cursor_updated = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sock_path = get_ipc_socket_path()
        self.server = QLocalServer(self)
        self.dbus_bridge = NashiDBusBridge(self)
        self.dbus_bridge.triggered.connect(self._on_dbus_triggered)
        self.dbus_bridge.cursor_updated.connect(self.cursor_updated)

    def start(self) -> bool:
        if os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass

        ok = self.server.listen(self.sock_path)
        if ok:
            self.server.newConnection.connect(self._on_new_connection)

        # Also register on session DBus for KWin Script instant callbacks
        try:
            from PySide6.QtDBus import QDBusConnection
            bus = QDBusConnection.sessionBus()
            if bus.isConnected():
                bus.registerService("org.nashi.App")
                bus.registerObject(
                    "/Nashi",
                    self.dbus_bridge,
                    QDBusConnection.RegisterOption.ExportAllSlots,
                )
        except Exception as e:
            print(f"[NashiIPC] DBus registration warning: {e}")

        return ok

    def _on_new_connection(self):
        conn: QLocalSocket = self.server.nextPendingConnection()
        if not conn:
            return
        conn.readyRead.connect(lambda c=conn: self._read_socket(c))

    def _read_socket(self, conn: QLocalSocket):
        raw = bytes(conn.readAll()).decode("utf-8", errors="replace").strip()
        conn.close()
        if not raw:
            return
        try:
            data = json.loads(raw)
            cmd = data.get("cmd", "wheel")
            mode = data.get("mode", "convert")
            files = data.get("files", [])
            self.command_received.emit(cmd, mode, files, None)
        except Exception:
            self.command_received.emit("wheel", raw, [], None)

    def _on_dbus_triggered(self, mode: str, x: int, y: int):
        if mode == "toggle_window":
            self.command_received.emit("toggle", "", [], (x, y))
        elif mode == "download_link":
            self.command_received.emit("download_link", "", [], (x, y))
        else:
            self.command_received.emit("wheel", mode, [], (x, y))
