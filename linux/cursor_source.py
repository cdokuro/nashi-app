"""
Global imleç konumu kaynağı.

Nashi XWayland (xcb) altında çalışır; imleç bir X11 penceresinin üzerinden
geçmedikçe QCursor.pos() donuk kalır ve her şey yanlış monitörde (DP-1) açılır.
KWin betiği (ipc_and_drag.nashi_kwin_bridge) gerçek konumu
(workspace.cursorPos) D-Bus ile akıtır; burada son değer tutulur.
Akış yoksa (X11 oturumu / betik yüklenmemiş) QCursor.pos()'a düşülür.
"""
from typing import Optional, Tuple

from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor

_last: Optional[Tuple[int, int]] = None


def update(x: float, y: float) -> None:
    """KWin'den gelen son gerçek imleç konumunu kaydeder."""
    global _last
    _last = (int(round(x)), int(round(y)))


def reset() -> None:
    global _last
    _last = None


def global_cursor_pos() -> QPoint:
    """Gerçek global imleç konumu (KWin akışı varsa), yoksa QCursor.pos()."""
    if _last is not None:
        return QPoint(_last[0], _last[1])
    return QCursor.pos()
