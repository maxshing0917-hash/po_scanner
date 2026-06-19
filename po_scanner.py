# -*- coding: utf-8 -*-
"""
PO Scanner Desktop App — Pure PyQt5
=====================================

OVERVIEW
--------
Tablet app for scanning package tracking numbers and PO barcodes, then
writing the results to a monthly CSV file that the VBA macro (PO_Import_v2.bas)
pulls into Excel.

APP FLOW
--------
1. App starts → LoadingWindow shown while OCR worker process initialises
2. OCR ready  → MainWindow shown, starts on CarrierSelectPage
3. User picks a carrier → ScanTablePage loads today's saved records from CSV
4. User scans tracking numbers (physical barcode scanner or tap-to-type)
5. User scans PO barcodes (tap PO cell → POCameraDialog → OCR → _POConfirmDialog)
6. User taps Save → records appended to monthly CSV, table resets (saved rows go green)
7. User taps carrier badge → back to CarrierSelectPage to switch carrier

KEY CLASSES
-----------
MainWindow          Root window. QStackedWidget switches between the two pages.
CarrierSelectPage   Carrier picker (USPS / FedEx / UPS / Amazon / FedEx EXP).
                    Emits carrier_selected(str) → MainWindow calls ScanTablePage.reset().
ScanTablePage       Main scan screen. Owns the table, barcode scanner input, and
                    all cell-interaction logic. See class docstring for state variables.
POCameraDialog      Fullscreen camera dialog for scanning PO barcodes.
                    Handles camera init, OCR, manual entry, and Copy Previous PO.
_POConfirmDialog    Floating card shown after OCR — 4 editable PO sub-fields.
WinRTCameraThread   Camera capture via Windows Runtime MediaCapture (runs in a QThread).
OcrThread           Sends image to the OCR worker subprocess and returns results.

FILE STRUCTURE
--------------
po_scanner.py           This file — main app logic and all UI classes
ui/ui_utils.py          Shared UI utilities: palette (P), _s(), _shadow(), _mk_btn() etc.
ui/dialogs.py           All modal dialog classes (_DraggableDialog and subclasses)
src/ocr/                OCR engine
src/preprocessing/      Image preprocessing
src/utils/extractor.py  PO / tracking number extraction logic
config/config.yaml      App configuration (CSV folder path, camera index, autofill rules)
PO_Import_v2.bas        VBA macro — imports today's CSV into Excel
"""

import sys
import os
import re
import logging

# ── Tracking-number patterns for barcode validation ───────────────────────────
_TRK_UPS   = re.compile(r'^1Z[A-Z0-9]{16}$', re.IGNORECASE)
_TRK_FEDEX = re.compile(r'^\d{12}$|^\d{15}$|^\d{20,22}$|^96\d{32}$')
_TRK_USPS  = re.compile(r'^420\d{25,32}$|^9[0-9]{19,21}$')
_TRK_AMZN  = re.compile(r'^TBA\d{9,}$', re.IGNORECASE)

def _is_valid_tracking(text: str) -> bool:
    t = text.strip().upper()
    if len(t) < 8:
        return False
    if _TRK_UPS.match(t) or _TRK_AMZN.match(t) or _TRK_USPS.match(t) or _TRK_FEDEX.match(t):
        return True
    return len(t) >= 15
os.environ['ORT_DISABLE_ALL_LOGS'] = '1'  # silence ONNXRuntime verbose output

import asyncio
import threading
import subprocess
import json
import tempfile
import cv2
import numpy as np
import yaml
from pathlib import Path

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)   # PyInstaller: bundled files live in _internal/
else:
    BASE_DIR = Path(__file__).parent



from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar, QFrame,
    QScrollArea, QSplitter, QGraphicsDropShadowEffect, QSizePolicy,
    QFileDialog, QDialog, QListWidget, QSlider,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QStackedWidget, QAbstractItemView, QStyledItemDelegate,
    QStyle, QStyleOptionViewItem,
)
from PyQt5.QtCore import Qt, QTimer, QRect, QRectF, QThread, pyqtSignal, QEvent, QPoint, QPointF, QObject
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QLinearGradient, QPainterPath, QPixmap,
    QPalette, QImage, QFontMetrics,
)

from ui.ui_utils import _S, _s, P, COL_TRK, COL_PO, COL_NUM, COL_RN, COL_PC, N_COLS
from ui.ui_utils import _shadow, _darken, _force_upper, _mk_btn
import ui.ui_utils as ui_utils
from ui.dialogs import (
    _DraggableDialog, AlertDialog, _SaveWarnDialog, TrackingEditDialog,
    _POEditDialog, _EditAllDialog, _POConfirmDialog, _PCPickerDialog,
)

# ── Carrier definitions (single source of truth) ──────────────────────────────
_CARRIER_DEFS = [
    ('USPS',      'usps',      '#354F7A'),
    ('FedEx',     'fedex',     '#4A3F7A'),
    ('UPS',       'ups',       '#7A5230'),
    ('Amazon',    'amazon',    '#8B6820'),
    ('FedEx EXP', 'fedex_exp', '#8B3A3A'),
]
_CARRIER_LABELS = {key: label for label, key, _ in _CARRIER_DEFS}
_CARRIER_COLORS = {key: color for _, key, color in _CARRIER_DEFS}

# ── Camera thread (WinRT) ─────────────────────────────────────────────────────

class WinRTCameraThread(QThread):
    """Camera thread using Windows Runtime MediaCapture — takes real photos."""

    frame_ready  = pyqtSignal()        # preview frame ready → read _last_bgr
    photo_ready  = pyqtSignal(object)  # high-quality capture: np.ndarray BGR
    error        = pyqtSignal(str)
    cam_info     = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running           = False
        self._paused            = False
        self._last_bgr: np.ndarray | None = None
        self._buf_lock          = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._device_ids: list[str] = []
        self._source_groups     = []
        self._current_dev_idx   = 0
        self._front_idx: int | None = None
        self._rear_idx:  int | None = None
        self._capture_flag      = False
        self._restart_flag      = False

    # ── Public API ────────────────────────────────────────────────────────────

    def start_camera(self, index: int = 0, width: int = 1920, height: int = 1080):
        if self.isRunning():
            self._running = False
            self.wait(3000)
        self._current_dev_idx = index
        self._running = True
        self.start()

    def stop_camera(self):
        self._running = False

    def pause_camera(self):
        """Slow the loop to ~1 fps and stop emitting frames (keep MediaCapture alive)."""
        self._paused = True

    def resume_camera(self):
        """Restore full-speed preview."""
        self._paused = False

    def force_release(self):
        pass  # cleanup is inside the async loop

    def request_capture(self):
        self._capture_flag = True

    def switch_camera(self):
        if self._front_idx is None or self._rear_idx is None:
            self.error.emit('Front/rear camera not available, staying on current.')
            return
        if self._current_dev_idx == self._front_idx:
            self._current_dev_idx = self._rear_idx
        else:
            self._current_dev_idx = self._front_idx
        self._restart_flag = True

    @property
    def current_index(self) -> int:
        return self._current_dev_idx

    @property
    def is_front_camera(self) -> bool:
        return self._current_dev_idx == self._front_idx

    def grab_best(self) -> 'np.ndarray | None':
        with self._buf_lock:
            return self._last_bgr

    # ── Thread entry ──────────────────────────────────────────────────────────

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_run())
        except Exception as e:
            self.error.emit(f'Camera error: {e}')
        finally:
            self._loop.close()
            self._loop = None

    # ── Async core ────────────────────────────────────────────────────────────

    async def _async_run(self):
        import winrt.windows.media.capture as wmc
        import winrt.windows.media.capture.frames as wmcf
        import winrt.windows.media.mediaproperties as wmmp
        import winrt.windows.storage.streams as wss
        import winrt.windows.graphics.imaging as wgi

        # MediaFrameSourceGroup lists all camera devices — no overloaded-method issue
        try:
            groups = await wmcf.MediaFrameSourceGroup.find_all_async()
            self._source_groups = list(groups)
            self._device_ids    = [g.id for g in self._source_groups]
            # Detect front / rear cameras by panel info
            for i, g in enumerate(self._source_groups):
                try:
                    for src in g.source_infos:
                        loc = src.device_information.enclosure_location if src.device_information else None
                        if loc is None:
                            continue
                        if loc.panel == 1 and self._front_idx is None:   # Panel.Front = 1
                            self._front_idx = i
                        elif loc.panel == 2 and self._rear_idx is None:  # Panel.Back  = 2
                            self._rear_idx = i
                except Exception:
                    pass
        except Exception as e:
            self._source_groups = []
            self._device_ids    = []

        capture, reader = await self._open(wmc, wmcf)
        if capture is None:
            return

        try:
            while self._running:
                if self._restart_flag:
                    self._restart_flag = False
                    try:
                        await reader.stop_async()
                        capture.close()
                    except Exception:
                        pass
                    capture, reader = await self._open(wmc, wmcf)
                    if capture is None:
                        return

                if self._paused:
                    await asyncio.sleep(0.1)
                    continue

                if self._capture_flag:
                    self._capture_flag = False
                    try:
                        bgr = await self._snap(capture, wmmp, wss)
                        if bgr is not None:
                            self.photo_ready.emit(bgr)
                    except Exception as e:
                        self.error.emit(f'Capture failed: {e}')
                else:
                    frame_ref = reader.try_acquire_latest_frame()
                    if frame_ref is not None:
                        try:
                            bgr = self._frame_to_bgr(frame_ref, wgi, wss)
                            if bgr is not None:
                                with self._buf_lock:
                                    self._last_bgr = bgr
                                self.frame_ready.emit()
                        finally:
                            frame_ref.close()

                await asyncio.sleep(0.033)  # ~30 fps
        finally:
            try:
                await reader.stop_async()
            except Exception:
                pass
            try:
                capture.close()
            except Exception:
                pass

    async def _open(self, wmc, wmcf):
        try:
            capture = wmc.MediaCapture()
            if self._source_groups and self._current_dev_idx < len(self._source_groups):
                settings = wmc.MediaCaptureInitializationSettings()
                settings.source_group = self._source_groups[self._current_dev_idx]
                settings.memory_preference = wmc.MediaCaptureMemoryPreference.CPU
                await capture.initialize_with_settings_async(settings)
            else:
                await capture.initialize_async()

            source = None
            for s in capture.frame_sources.values():
                if s.info.source_kind == wmcf.MediaFrameSourceKind.COLOR:
                    source = s
                    break
            if source is None:
                self.error.emit('No color frame source found')
                capture.close()
                return None, None

            reader = await capture.create_frame_reader_async(source)
            await reader.start_async()
            n = len(self._device_ids)
            self.cam_info.emit(f'Cam {self._current_dev_idx + 1}/{max(n, 1)}')
            return capture, reader
        except Exception as e:
            self.error.emit(f'Cannot open camera: {e}')
            return None, None

    def _frame_to_bgr(self, frame_ref, wgi, wss) -> 'np.ndarray | None':
        try:
            video_frame = frame_ref.video_media_frame
            if video_frame is None:
                return None
            soft_bm = video_frame.software_bitmap
            if soft_bm is None:
                return None
            if soft_bm.bitmap_pixel_format != wgi.BitmapPixelFormat.BGRA8:
                soft_bm = wgi.SoftwareBitmap.convert(
                    soft_bm, wgi.BitmapPixelFormat.BGRA8
                )
            w, h = soft_bm.pixel_width, soft_bm.pixel_height
            buf = wss.Buffer(w * h * 4)
            soft_bm.copy_to_buffer(buf)
            arr = np.frombuffer(bytearray(buf), dtype=np.uint8).reshape(h, w, 4)
            bgr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            if w > 1280:
                scale = 1280 / w
                bgr = cv2.resize(bgr, (1280, int(h * scale)), interpolation=cv2.INTER_AREA)
            return bgr
        except Exception:
            return None

    async def _snap(self, capture, wmmp, wss) -> 'np.ndarray | None':
        props = wmmp.ImageEncodingProperties.create_jpeg()
        stream = wss.InMemoryRandomAccessStream()
        await capture.capture_photo_to_stream_async(props, stream)
        stream.seek(0)
        size = stream.size
        dr = wss.DataReader(stream)
        await dr.load_async(size)
        buf = dr.read_buffer(size)
        data = bytes(buf)
        arr = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)



# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_worker_exe() -> 'str | None':
    """Return path to ocr_worker.exe when packaged, or None in dev mode."""
    if getattr(sys, 'frozen', False):
        return str(Path(sys.executable).parent / 'ocr_runtime' / 'ocr_core.exe')
    return None

def _sharpness(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _sharpen(frame: np.ndarray) -> np.ndarray:
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    return cv2.filter2D(frame, -1, kernel)




# ── Gradient background widget ────────────────────────────────────────────────

# ── Draggable frameless dialog base ──────────────────────────────────────────

# ── Gradient background widget ────────────────────────────────────────────────

class GradientWidget(QWidget):
    def paintEvent(self, _):
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0.0, QColor(P['bg_start']))
        g.setColorAt(1.0, QColor(P['bg_end']))
        p.fillRect(self.rect(), g)


# ── Zoomable image label ──────────────────────────────────────────────────────

class ZoomableLabel(QLabel):
    """Image display with optional zoom (wheel/pinch) + pan (drag/single-touch)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled   = False
        self._scale     = 1.0
        self._offset_x  = 0.0
        self._offset_y  = 0.0
        self._drag_last = None
        self._orig_pix  = None
        self._touch_dist = None   # last pinch distance

        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet('background: transparent;')
        self.setAttribute(Qt.WA_AcceptTouchEvents)
        self.grabGesture(Qt.PinchGesture)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_enabled(self, v: bool):
        self._enabled = v
        if not v:
            self.reset()

    def reset(self):
        self._scale    = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._render()

    def set_source(self, pix: QPixmap):
        self._orig_pix = pix if (pix and not pix.isNull()) else None
        self.reset()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self):
        if self._orig_pix is None:
            self.clear()
            return
        dpr = self.devicePixelRatio()
        w, h = int(self.width() * dpr), int(self.height() * dpr)
        if w <= 0 or h <= 0:
            return
        base = self._orig_pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if self._scale == 1.0 and self._offset_x == 0 and self._offset_y == 0:
            base.setDevicePixelRatio(dpr)
            self.setPixmap(base)
            return
        sw = int(base.width()  * self._scale)
        sh = int(base.height() * self._scale)
        scaled = self._orig_pix.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        canvas = QPixmap(w, h)
        canvas.fill(Qt.transparent)
        p = QPainter(canvas)
        x = int((w - sw) / 2 + self._offset_x * dpr)
        y = int((h - sh) / 2 + self._offset_y * dpr)
        p.drawPixmap(x, y, scaled)
        p.end()
        canvas.setDevicePixelRatio(dpr)
        self.setPixmap(canvas)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._render()

    # ── Mouse (desktop) ───────────────────────────────────────────────────────

    def wheelEvent(self, e):
        if not self._enabled:
            super().wheelEvent(e)
            return
        factor = 1.12 if e.angleDelta().y() > 0 else 0.88
        self._scale = max(1.0, min(10.0, self._scale * factor))
        self._render()

    def mousePressEvent(self, e):
        if self._enabled and e.button() == Qt.LeftButton:
            self._drag_last = e.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._enabled and self._drag_last is not None:
            self._offset_x += e.x() - self._drag_last.x()
            self._offset_y += e.y() - self._drag_last.y()
            self._drag_last = e.pos()
            self._render()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_last = None
        super().mouseReleaseEvent(e)

    # ── Touch / Gesture (tablet) ──────────────────────────────────────────────

    def event(self, e):
        if e.type() == QEvent.Gesture:
            return self._handle_gesture(e)
        return super().event(e)

    def _handle_gesture(self, e):
        pinch = e.gesture(Qt.PinchGesture)
        if pinch and self._enabled:
            self._scale = max(1.0, min(10.0, self._scale * pinch.scaleFactor()))
            delta = pinch.centerPoint() - pinch.lastCenterPoint()
            self._offset_x += delta.x()
            self._offset_y += delta.y()
            self._render()
        return True



# ── Loading window ────────────────────────────────────────────────────────────

class LoadingWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PO Scanner')
        w, h = _s(480), _s(200)
        self.setFixedSize(w, h)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        card = QWidget(self)
        card.setGeometry(0, 0, w, h)
        card.setStyleSheet(f'background: #FBF7F2; border-radius: {_s(14)}px;')
        _shadow(card, blur=24, dy=8)

        lo = QVBoxLayout(card)
        lo.setContentsMargins(_s(40), _s(32), _s(40), _s(32))
        lo.setSpacing(_s(14))

        title = QLabel('PO Scanner')
        title.setFont(QFont('Segoe UI', _s(26), QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f'color: {P["title"]};')

        self._status = QLabel('Starting up…')
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setFont(QFont('Segoe UI', _s(14)))
        self._status.setStyleSheet(f'color: {P["subtitle"]};')

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(_s(8))
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background: #E8DDD4;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {P['btn_pri']}, stop:1 #C89D68);
                border-radius: 3px;
            }}
        """)

        lo.addWidget(title)
        lo.addWidget(self._status)
        lo.addWidget(self._bar)

    def set_status(self, text: str):
        self._status.setText(text)

    def set_progress(self, value: int):
        self._bar.setValue(value)


# ── OCR init thread ──────────────────────────────────────────────────────────

class InitThread(QThread):
    progress = pyqtSignal(int, str)
    done     = pyqtSignal(bool)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config     = config
        self.worker_proc = None   # subprocess.Popen when ready

    def run(self):
        log_path = os.path.join(os.path.expanduser('~'), 'po_scanner_init.log')
        ok = False
        try:
            worker_exe = _find_worker_exe()
            if worker_exe and not os.path.exists(worker_exe):
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(f'OCR worker not found: {worker_exe}\n'
                            f'Please install PO Scanner OCR Runtime first.\n')
                self.progress.emit(100, 'OCR Runtime not installed')
                self.done.emit(False)
                return

            cmd = [worker_exe] if worker_exe else [sys.executable,
                   str(BASE_DIR / 'ocr_core.py')]

            self.progress.emit(20, 'Starting OCR worker…')
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            )

            # Send config so worker can initialise OCREngine
            proc.stdin.write(json.dumps(self._config) + '\n')
            proc.stdin.flush()

            self.progress.emit(40, 'Loading OCR model…')

            # Block until worker signals ready (may take 30-60 s on first run)
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError('Worker exited before sending ready signal')
            resp = json.loads(line)
            ok   = resp.get('ok', False)

            if ok:
                self.worker_proc = proc
            else:
                err = resp.get('error', '')
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(f'Worker init failed: {err}\n')
                try:
                    proc.terminate()
                except Exception:
                    pass

        except Exception as e:
            import traceback
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f'Exception starting worker:\n{e}\n\n{traceback.format_exc()}')

        self.progress.emit(100, 'Ready!' if ok else 'Init failed')
        self.done.emit(ok)


# ── OCR processing thread ─────────────────────────────────────────────────────

class OcrThread(QThread):
    det_done = pyqtSignal(object)  # emits np.ndarray BGR with det boxes drawn
    done     = pyqtSignal(object)  # emits result dict from worker

    def __init__(self, worker_proc, image: np.ndarray, pre_config: dict,
                 blacklist: list | None = None, parent=None):
        super().__init__(parent)
        self._worker     = worker_proc
        self._image      = image
        self._pre_config = pre_config
        self._blacklist  = blacklist or []

    def run(self):
        tmp_img = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        tmp_img_path = tmp_img.name
        tmp_img.close()
        det_img_path = tmp_img_path + '_det.jpg'

        try:
            cv2.imwrite(tmp_img_path, self._image)

            req = {
                'action':        'recognize',
                'image_path':    tmp_img_path,
                'det_image_path': det_img_path,
                'pre_config':    self._pre_config,
                'blacklist':     self._blacklist,
            }
            self._worker.stdin.write(json.dumps(req) + '\n')
            self._worker.stdin.flush()

            # Read response lines until we get the final result
            while True:
                line = self._worker.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except Exception:
                    continue

                if msg.get('type') == 'det_done':
                    if os.path.exists(det_img_path):
                        det_bgr = cv2.imread(det_img_path)
                        if det_bgr is not None:
                            self.det_done.emit(det_bgr)
                        try:
                            os.unlink(det_img_path)
                        except Exception:
                            pass

                elif msg.get('type') == 'log':
                    print(msg.get('msg', ''), flush=True)

                elif msg.get('type') == 'result':
                    self.done.emit(msg)
                    break

                elif msg.get('type') == 'error':
                    break

        finally:
            try:
                os.unlink(tmp_img_path)
            except Exception:
                pass


# ── cv2 → QPixmap helper ──────────────────────────────────────────────────────

def _cv2_to_pixmap(img) -> 'QPixmap':
    rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)


# ── Resizable crop-frame overlay ─────────────────────────────────────────────

class ResizableFrameOverlay(QWidget):
    """Transparent overlay with a user-draggable scan frame (4 corner handles).
    Stores position as normalized fractions so window resize is safe."""

    _DEFAULT_NORM = (0.13, 0.21, 0.87, 0.79)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._norm:        tuple          = self._DEFAULT_NORM
        self._drag_corner: str | None     = None
        self._drag_start:  QPointF | None = None
        self._norm_start:  tuple | None   = None

    def set_norm(self, lf, tf, rf, bf):
        self._norm = (lf, tf, rf, bf)
        self.update()

    def norm_rect(self):
        return self._norm

    def frame_rect(self) -> QRect:
        return self._pixel_rect().toRect()

    def _pixel_rect(self) -> QRectF:
        w, h = float(self.width()), float(self.height())
        lf, tf, rf, bf = self._norm
        return QRectF(lf * w, tf * h, (rf - lf) * w, (bf - tf) * h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.update()

    def paintEvent(self, _):
        if self.width() <= 0 or self.height() <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = self._pixel_rect()

        outer = QPainterPath()
        outer.addRect(0, 0, w, h)
        inner = QPainterPath()
        inner.addRoundedRect(r, 4, 4)
        p.fillPath(outer.subtracted(inner), QColor(0, 0, 0, 120))

        pen = QPen(QColor('#4ADE80'), 3, Qt.SolidLine, Qt.SquareCap)
        p.setPen(pen)
        arm = _s(36)
        for cx, cy in [(r.left(), r.top()), (r.right(), r.top()),
                       (r.left(), r.bottom()), (r.right(), r.bottom())]:
            sx = 1 if cx == r.left() else -1
            sy = 1 if cy == r.top()  else -1
            p.drawLine(int(cx), int(cy), int(cx + sx * arm), int(cy))
            p.drawLine(int(cx), int(cy), int(cx), int(cy + sy * arm))

        p.setPen(QColor(255, 255, 255, 180))
        p.setFont(QFont('Segoe UI', _s(9), QFont.Bold))
        p.drawText(QRect(int(r.left()), int(r.bottom()) + _s(8), int(r.width()), _s(20)),
                   Qt.AlignCenter, 'Align label within frame')

    def _handle_r(self):
        return _s(26)

    def _corner_at(self, pos: QPoint):
        r  = self._pixel_rect()
        hr = self._handle_r()
        for name, (cx, cy) in [('TL', (r.left(), r.top())),   ('TR', (r.right(), r.top())),
                                ('BL', (r.left(), r.bottom())), ('BR', (r.right(), r.bottom()))]:
            if abs(pos.x() - cx) < hr and abs(pos.y() - cy) < hr:
                return name
        return None

    def mousePressEvent(self, e):
        corner = self._corner_at(e.pos())
        if corner:
            self._drag_corner = corner
            self._drag_start  = QPointF(e.pos())
            self._norm_start  = self._norm
            e.accept()
        else:
            e.ignore()

    def mouseMoveEvent(self, e):
        if self._drag_corner is None:
            corner = self._corner_at(e.pos())
            self.setCursor(Qt.SizeFDiagCursor if corner in ('TL', 'BR') else
                           Qt.SizeBDiagCursor if corner in ('TR', 'BL') else Qt.ArrowCursor)
            e.ignore()
            return
        W, H = float(self.width()), float(self.height())
        lf0, tf0, rf0, bf0 = self._norm_start
        r  = QRectF(lf0 * W, tf0 * H, (rf0 - lf0) * W, (bf0 - tf0) * H)
        dx = e.pos().x() - self._drag_start.x()
        dy = e.pos().y() - self._drag_start.y()
        mn, mg = _s(80), 4.0
        if   self._drag_corner == 'TL': r.setLeft(min(r.left()+dx, r.right()-mn));  r.setTop(min(r.top()+dy, r.bottom()-mn))
        elif self._drag_corner == 'TR': r.setRight(max(r.right()+dx, r.left()+mn)); r.setTop(min(r.top()+dy, r.bottom()-mn))
        elif self._drag_corner == 'BL': r.setLeft(min(r.left()+dx, r.right()-mn));  r.setBottom(max(r.bottom()+dy, r.top()+mn))
        elif self._drag_corner == 'BR': r.setRight(max(r.right()+dx, r.left()+mn)); r.setBottom(max(r.bottom()+dy, r.top()+mn))
        r.setLeft(max(mg, r.left()));   r.setTop(max(mg, r.top()))
        r.setRight(min(W-mg, r.right())); r.setBottom(min(H-mg, r.bottom()))
        self._norm = (r.left()/W, r.top()/H, r.right()/W, r.bottom()/H)
        self.update()
        e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_corner = None
        e.accept()


# ── PO camera dialog ──────────────────────────────────────────────────────────

class POCameraDialog(QDialog):
    """Fullscreen camera dialog for scanning a PO barcode.

    Flow:
        Open → camera starts (buttons disabled until first frame)
             → user taps Capture → OcrThread runs → _POConfirmDialog shown
             → user taps Manual Entry → _POConfirmDialog shown (empty)
             → user taps Copy Previous PO → _POConfirmDialog shown (preset filled)
             → camera fails to start (3s timeout) → _show_startup_failure()
                 → Enter PO Manually → _POConfirmDialog shown (empty)

    Batch mode: batch_info=(current, total) shows progress. If camera_failed=True
    after accept, _batch_po_scan switches subsequent packages to _POConfirmDialog directly.

    Result attributes (readable after exec_() == Accepted):
        po_value, number_value, rn_value, pc_value
    """

    _ZOOM_MIN = 10
    _ZOOM_MAX = 30

    def __init__(self, worker_proc, config: dict, cam_index: int, parent=None,
                 package_num: int = 0, tracking_tail: str = '',
                 batch_info: tuple = (), last_po_parts: dict = {},
                 prefill: dict = None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.po_value     = ''
        self.number_value = ''
        self.rn_value     = ''
        self.pc_value     = ''
        self._worker     = worker_proc
        self._config     = config
        self._cam_idx    = cam_index
        self._ocr_thread = None
        self._zoom       = 1.0
        self._cam_stopped = True
        self._package_num    = package_num
        self._tracking_tail  = tracking_tail
        self._batch_info     = batch_info  # (current, total) or ()
        self._last_po_parts  = last_po_parts
        self._prefill        = prefill
        self._cam_ok         = False   # True once first frame arrives
        self._failure_shown  = False   # prevent duplicate startup-failure dialogs
        self.camera_failed   = False   # set True if camera never started
        self._build_ui()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── body: camera area + right panel ──────────────────────────────────
        body    = QWidget()
        body_lo = QHBoxLayout(body)
        body_lo.setContentsMargins(0, 0, 0, 0)
        body_lo.setSpacing(0)

        self._cam_area = QWidget()
        self._cam_area.setStyleSheet('background: black;')
        self._feed_lbl = QLabel(self._cam_area)
        self._feed_lbl.setAlignment(Qt.AlignCenter)
        self._feed_lbl.setStyleSheet('background: black;')
        self._overlay = ResizableFrameOverlay(self._cam_area)

        # ── Package info overlay (top-left, always visible) ───────────────────
        pkg_line = f'Package  #{self._package_num}' if self._package_num else 'Package'
        trk_part = f'···{self._tracking_tail}' if self._tracking_tail else '—'
        batch_part = f'   ·   {self._batch_info[0]} / {self._batch_info[1]}' if self._batch_info else ''
        trk_line = f'Tracking  {trk_part}{batch_part}'
        self._info_lbl = QLabel(f'{pkg_line}\n{trk_line}', self._cam_area)
        self._info_lbl.setFont(QFont('Segoe UI', _s(22), QFont.Bold))
        self._info_lbl.setStyleSheet(f"""
            color: white;
            background: rgba(0, 0, 0, 170);
            border-radius: {_s(10)}px;
            padding: {_s(10)}px {_s(18)}px;
        """)
        self._info_lbl.adjustSize()
        self._info_lbl.move(_s(16), _s(16))
        self._info_lbl.raise_()

        self._cam_area.resizeEvent = self._sync_cam_area
        body_lo.addWidget(self._cam_area, 1)

        right = QWidget()
        right.setFixedWidth(_s(64))
        right.setStyleSheet('background: #1E1E1E;')
        r_lo = QVBoxLayout(right)
        r_lo.setContentsMargins(_s(10), _s(14), _s(10), _s(14))
        r_lo.setSpacing(_s(10))

        self._zoom_slider = QSlider(Qt.Vertical)
        self._zoom_slider.setRange(self._ZOOM_MIN, self._ZOOM_MAX)
        self._zoom_slider.setValue(self._ZOOM_MIN)
        self._zoom_slider.setStyleSheet(f"""
            QSlider::groove:vertical {{
                background: #555;
                width: {_s(8)}px;
                border-radius: {_s(4)}px;
            }}
            QSlider::handle:vertical {{
                background: #4ADE80;
                width: {_s(44)}px;
                height: {_s(52)}px;
                margin: 0 -{_s(18)}px;
                border-radius: {_s(6)}px;
            }}
            QSlider::handle:vertical:hover {{
                background: #3BC870;
            }}
            QSlider::sub-page:vertical {{
                background: #4ADE80;
                border-radius: {_s(4)}px;
            }}
        """)
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        r_lo.addWidget(self._zoom_slider, 1, Qt.AlignHCenter)

        self._zoom_lbl = QLabel('1.0×')
        self._zoom_lbl.setAlignment(Qt.AlignCenter)
        self._zoom_lbl.setFont(QFont('Segoe UI', _s(14)))
        self._zoom_lbl.setStyleSheet('color: #AAAAAA; background: transparent;')
        r_lo.addWidget(self._zoom_lbl, 0, Qt.AlignHCenter)

        body_lo.addWidget(right)
        root.addWidget(body, 1)

        # ── bottom bar ────────────────────────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(_s(126))
        bar.setStyleSheet('background: #1A1A1A;')
        bar_lo = QHBoxLayout(bar)
        bar_lo.setContentsMargins(_s(30), 0, _s(30), 0)
        bar_lo.setSpacing(_s(18))

        cancel_btn = QPushButton('Cancel')
        cancel_btn.setFixedSize(_s(195), _s(81))
        cancel_btn.setFont(QFont('Segoe UI', _s(21), QFont.Bold))
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: #8B3A3A; color: white; border: none; border-radius: {_s(12)}px; }}
            QPushButton:hover {{ background: #A04040; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        bar_lo.addWidget(cancel_btn)

        # center: status only
        center    = QWidget()
        center.setStyleSheet('background: transparent;')
        center_lo = QVBoxLayout(center)
        center_lo.setContentsMargins(0, 0, 0, 0)
        center_lo.setAlignment(Qt.AlignCenter)

        self._status = QLabel('Starting camera…')
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setFont(QFont('Segoe UI', _s(18)))
        self._status.setStyleSheet('color: #CCCCCC; background: transparent;')
        center_lo.addWidget(self._status)

        self._ocr_progress = QProgressBar()
        self._ocr_progress.setRange(0, 100)
        self._ocr_progress.setValue(0)
        self._ocr_progress.setFixedHeight(_s(10))
        self._ocr_progress.setTextVisible(False)
        self._ocr_progress.setStyleSheet(f"""
            QProgressBar {{
                background: #333333;
                border-radius: {_s(5)}px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: #4ADE80;
                border-radius: {_s(5)}px;
            }}
        """)
        self._ocr_progress.hide()
        center_lo.addWidget(self._ocr_progress)
        bar_lo.addWidget(center, 1)

        self._enter_btn = QPushButton('Manual Entry')
        self._enter_btn.setFixedHeight(_s(81))
        self._enter_btn.setMinimumWidth(_s(195))
        self._enter_btn.setFont(QFont('Segoe UI', _s(21), QFont.Bold))
        self._enter_btn.setEnabled(False)
        self._enter_btn.setStyleSheet(f"""
            QPushButton          {{ background: #F97316; color: white; border: none; border-radius: {_s(12)}px; }}
            QPushButton:hover    {{ background: #EA580C; color: white; }}
            QPushButton:disabled {{ background: #4A3A2A; color: #777777; }}
        """)
        self._enter_btn.clicked.connect(self._on_enter_manually)
        bar_lo.addWidget(self._enter_btn)

        self._copy_last_btn = QPushButton('Copy Previous PO')
        self._copy_last_btn.setFixedHeight(_s(81))
        self._copy_last_btn.setMinimumWidth(_s(240))
        self._copy_last_btn.setFont(QFont('Segoe UI', _s(19), QFont.Bold))
        self._copy_last_btn.setVisible(bool(self._last_po_parts))
        self._copy_last_btn.setEnabled(False)
        self._copy_last_btn.setStyleSheet(f"""
            QPushButton          {{ background: #3B82F6; color: white; border: none; border-radius: {_s(12)}px; }}
            QPushButton:hover    {{ background: #2563EB; color: white; }}
            QPushButton:disabled {{ background: #2A3A4A; color: #777777; }}
        """)
        self._copy_last_btn.clicked.connect(self._on_copy_previous_po)
        bar_lo.addWidget(self._copy_last_btn)

        self._capture_btn = QPushButton('Capture')
        self._capture_btn.setFixedSize(_s(195), _s(81))
        self._capture_btn.setFont(QFont('Segoe UI', _s(21), QFont.Bold))
        self._capture_btn.setEnabled(False)
        self._capture_btn.setStyleSheet(f"""
            QPushButton         {{ background: #4ADE80; color: #111111; border: none; border-radius: {_s(12)}px; }}
            QPushButton:hover   {{ background: #3BC870; color: #111111; }}
            QPushButton:disabled{{ background: #3A4A3A; color: #777777; }}
        """)
        self._capture_btn.clicked.connect(self._on_capture)
        bar_lo.addWidget(self._capture_btn)

        root.addWidget(bar)

    # ── Camera ────────────────────────────────────────────────────────────────

    def showEvent(self, e):
        super().showEvent(e)
        if self.parent():
            self.setGeometry(self.parent().window().geometry())
        else:
            self.showFullScreen()
        if self._cam_stopped:
            self._cam_stopped = False
            self._cam = WinRTCameraThread()
            self._cam.frame_ready.connect(self._on_frame)
            self._cam.photo_ready.connect(self._on_photo)
            self._cam.error.connect(self._on_cam_error)
            self._cam.start_camera(self._cam_idx)
    def _stop_cam(self):
        if self._cam_stopped:
            return
        self._cam_stopped = True
        self._cam.stop_camera()
        # don't block — thread cleans up asynchronously in its finally block

    def _sync_cam_area(self, e=None):
        if e:
            QWidget.resizeEvent(self._cam_area, e)
        r = self._cam_area.rect()
        self._feed_lbl.setGeometry(r)
        self._overlay.setGeometry(r)
        self._info_lbl.raise_()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_zoom_changed(self, value: int):
        self._zoom = value / self._ZOOM_MIN
        self._zoom_lbl.setText(f'{self._zoom:.1f}×')

    def _on_frame(self):
        if not self._cam_ok:
            self._cam_ok = True
            self._capture_btn.setEnabled(True)
            self._enter_btn.setEnabled(True)
            self._copy_last_btn.setEnabled(True)
            self._status.setText('Ready — press Capture')
        bgr = self._cam._last_bgr
        if bgr is None:
            return
        if self._zoom > 1.0:
            h, w = bgr.shape[:2]
            f  = 1.0 / self._zoom
            cx, cy = w // 2, h // 2
            cw, ch = int(w * f), int(h * f)
            bgr = bgr[max(0, cy - ch // 2):max(0, cy - ch // 2) + ch,
                      max(0, cx - cw // 2):max(0, cx - cw // 2) + cw]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        ih, iw = rgb.shape[:2]
        dpr = self._feed_lbl.devicePixelRatio()
        W = int(self._feed_lbl.width() * dpr)
        H = int(self._feed_lbl.height() * dpr)
        if W > 0 and H > 0:
            scale = min(W / iw, H / ih)
            tw, th = int(iw * scale), int(ih * scale)
            rgb = cv2.resize(rgb, (tw, th),
                             interpolation=cv2.INTER_LANCZOS4 if scale > 1.0 else cv2.INTER_AREA)
            ih, iw = rgb.shape[:2]
        qimg = QImage(rgb.data, iw, ih, iw * 3, QImage.Format_RGB888).copy()
        pix  = QPixmap.fromImage(qimg)
        pix.setDevicePixelRatio(dpr)
        self._feed_lbl.setPixmap(pix)
        if not self._capture_btn.isEnabled():
            self._capture_btn.setEnabled(True)
            self._enter_btn.setEnabled(True)
            self._copy_last_btn.setEnabled(True)
            self._status.setText('Ready — press Capture')

    def _on_cam_error(self, err: str):
        self._status.setText(f'Camera error: {err}')
        if self._cam_ok or self._failure_shown:
            return
        self._failure_shown = True
        QTimer.singleShot(3000, lambda: self._show_startup_failure(err)
                          if not self._cam_ok and self.isVisible()
                          else None)

    def _show_startup_failure(self, err: str):
        self.camera_failed = True
        dlg = QDialog(self)
        dlg.setModal(True)
        dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        dlg.setAttribute(Qt.WA_TranslucentBackground)

        p = _s(30)
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(p, p, p, p + _s(12))

        card = QWidget()
        card.setStyleSheet(f'background: #222222; border-radius: {_s(36)}px;')
        _shadow(card, blur=40, dy=12)
        outer.addWidget(card)

        lo = QVBoxLayout(card)
        lo.setContentsMargins(_s(72), _s(66), _s(72), _s(66))
        lo.setSpacing(_s(36))

        title_lbl = QLabel('Camera Failed to Start')
        title_lbl.setFont(QFont('Segoe UI', _s(39), QFont.Bold))
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet('color: #FF6B6B; background: transparent;')
        lo.addWidget(title_lbl)

        err_lbl = QLabel(err)
        err_lbl.setFont(QFont('Segoe UI', _s(24)))
        err_lbl.setAlignment(Qt.AlignCenter)
        err_lbl.setWordWrap(True)
        err_lbl.setStyleSheet('color: #888888; background: transparent;')
        lo.addWidget(err_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(_s(30))
        back_btn  = QPushButton('Cancel')
        enter_btn = QPushButton('Enter PO Manually')
        for btn in (back_btn, enter_btn):
            btn.setFixedHeight(_s(120))
            btn.setFont(QFont('Segoe UI', _s(30), QFont.Bold))
            btn.setAutoDefault(False)
        back_btn.setMinimumWidth(_s(300))
        enter_btn.setMinimumWidth(_s(390))
        back_btn.setStyleSheet(f"""
            QPushButton       {{ background: #555555; color: white; border: none; border-radius: {_s(21)}px; }}
            QPushButton:hover {{ background: #666666; }}
        """)
        enter_btn.setStyleSheet(f"""
            QPushButton       {{ background: #F97316; color: white; border: none; border-radius: {_s(21)}px; }}
            QPushButton:hover {{ background: #EA580C; }}
        """)
        back_btn.clicked.connect(dlg.reject)
        enter_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(back_btn)
        btn_row.addStretch()
        btn_row.addWidget(enter_btn)
        lo.addLayout(btn_row)

        pg = self.geometry()
        dlg.adjustSize()
        dlg.move(pg.x() + (pg.width()  - dlg.width())  // 2,
                 pg.y() + (pg.height() - dlg.height()) // 2)

        if dlg.exec_() == QDialog.Accepted:
            po_dlg = _POConfirmDialog('', self,
                                      package_num=self._package_num,
                                      tracking_tail=self._tracking_tail,
                                      autofill_rules=self._config.get('po_autofill', []),
                                      retake_label='Cancel')
            if po_dlg.exec_() == QDialog.Accepted:
                self.po_value     = po_dlg.po_value
                self.number_value = po_dlg.number_value
                self.rn_value     = po_dlg.rn_value
                self.pc_value     = po_dlg.pc_value
                self.accept()
            else:
                self.reject()
        else:
            self.reject()

    def _on_enter_manually(self):
        if not self._cam_stopped:
            self._cam.pause_camera()
        self._enter_btn.setEnabled(False)
        self._copy_last_btn.setEnabled(False)
        self._capture_btn.setEnabled(False)
        dlg = _POConfirmDialog('', self,
                               package_num=self._package_num,
                               tracking_tail=self._tracking_tail,
                               autofill_rules=self._config.get('po_autofill', []),
                               preset=self._prefill,
                               retake_label='Cancel')
        if dlg.exec_() == QDialog.Accepted:
            self.po_value     = dlg.po_value
            self.number_value = dlg.number_value
            self.rn_value     = dlg.rn_value
            self.pc_value     = dlg.pc_value
            self.accept()
        else:
            if not self._cam_stopped:
                self._cam.resume_camera()
            self._enter_btn.setEnabled(True)
            self._copy_last_btn.setEnabled(True)
            self._capture_btn.setEnabled(True)

    def _on_copy_previous_po(self):
        if not self._cam_stopped:
            self._cam.pause_camera()
        self._enter_btn.setEnabled(False)
        self._copy_last_btn.setEnabled(False)
        self._capture_btn.setEnabled(False)
        dlg = _POConfirmDialog('', self,
                               package_num=self._package_num,
                               tracking_tail=self._tracking_tail,
                               autofill_rules=self._config.get('po_autofill', []),
                               preset=self._last_po_parts,
                               retake_label='Cancel')
        if dlg.exec_() == QDialog.Accepted:
            self.po_value     = dlg.po_value
            self.number_value = dlg.number_value
            self.rn_value     = dlg.rn_value
            self.pc_value     = dlg.pc_value
            self.accept()
        else:
            if not self._cam_stopped:
                self._cam.resume_camera()
            self._enter_btn.setEnabled(True)
            self._copy_last_btn.setEnabled(True)
            self._capture_btn.setEnabled(True)

    def _on_capture(self):
        self._capture_btn.setEnabled(False)
        self._status.setText('Capturing…')
        self._cam.request_capture()

    def _on_photo(self, bgr: np.ndarray):
        self._cam.pause_camera()

        # apply digital zoom crop to full-res photo
        if self._zoom > 1.0:
            h, w = bgr.shape[:2]
            f  = 1.0 / self._zoom
            cx, cy = w // 2, h // 2
            cw, ch = int(w * f), int(h * f)
            x1 = max(0, cx - cw // 2); y1 = max(0, cy - ch // 2)
            bgr = bgr[y1:y1 + ch, x1:x1 + cw].copy()

        # map overlay frame_rect → pixel coords
        fr = self._overlay.frame_rect()
        W_w, H_w = self._feed_lbl.width(), self._feed_lbl.height()
        ih, iw = bgr.shape[:2]
        if W_w > 0 and H_w > 0 and fr.width() > 0 and fr.height() > 0:
            s  = min(W_w / iw, H_w / ih)
            ox = (W_w - iw * s) / 2; oy = (H_w - ih * s) / 2
            cx = max(0, int((fr.x() - ox) / s))
            cy = max(0, int((fr.y() - oy) / s))
            cw = min(int(fr.width()  / s), iw - cx)
            ch = min(int(fr.height() / s), ih - cy)
            if cw > 0 and ch > 0:
                bgr = bgr[cy:cy + ch, cx:cx + cw].copy()

        # show captured image in feed, hide overlay
        pix = _cv2_to_pixmap(bgr).scaled(
            self._feed_lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._feed_lbl.setPixmap(pix)
        self._overlay.hide()

        self._status.setText('Detecting text…')
        self._ocr_progress.setValue(0)
        self._ocr_progress.show()
        blacklist = self._config.get('extraction', {}).get('po_blacklist', [])
        self._ocr_thread = OcrThread(
            self._worker, bgr,
            self._config.get('preprocessing', {}),
            blacklist=blacklist,
        )
        self._ocr_thread.det_done.connect(lambda _: (
            self._status.setText('Reading text…'),
            self._ocr_progress.setValue(50),
        ))
        self._ocr_thread.done.connect(self._on_ocr_done)
        self._ocr_thread.start()

    def _on_ocr_done(self, msg: dict):
        candidates = msg.get('po_candidates', [])
        po = candidates[0] if candidates else msg.get('po', '')
        self._ocr_progress.setValue(100)
        self._ocr_progress.hide()
        self._status.setText('PO recognized')
        self._enter_btn.setEnabled(False)
        self._copy_last_btn.setEnabled(False)
        dlg = _POConfirmDialog(po, self,
                               package_num=self._package_num,
                               tracking_tail=self._tracking_tail,
                               autofill_rules=self._config.get('po_autofill', []))
        if dlg.exec_() == QDialog.Accepted:
            self.po_value     = dlg.po_value
            self.number_value = dlg.number_value
            self.rn_value     = dlg.rn_value
            self.pc_value     = dlg.pc_value
            self.accept()
        else:
            self._on_retake()

    def _on_retake(self):
        self._cam.resume_camera()
        self._overlay.show()
        self._capture_btn.setEnabled(True)
        self._enter_btn.setEnabled(True)
        self._copy_last_btn.setEnabled(True)
        self._status.setText('Ready — press Capture')

    def accept(self):
        self._stop_cam()
        # Wait for camera thread to fully release hardware before returning —
        # batch mode opens a new dialog immediately after, and WinRT MediaCapture
        # is exclusive; without this wait the next dialog hangs in initialize_async().
        if hasattr(self, '_cam') and self._cam.isRunning():
            self._cam.wait(5000)
        if self._ocr_thread and self._ocr_thread.isRunning():
            self._ocr_thread.wait(5000)
        super().accept()

    def reject(self):
        self._stop_cam()
        super().reject()

    def closeEvent(self, e):
        self._stop_cam()
        super().closeEvent(e)


# ── Carrier select page ───────────────────────────────────────────────────────

class CarrierSelectPage(GradientWidget):
    """First screen — lets user pick a carrier to begin scanning.

    Emits carrier_selected(key: str) where key is one of:
        'usps' | 'fedex' | 'ups' | 'amazon' | 'fedex_exp'
    MainWindow catches this signal, calls ScanTablePage.set_carrier() + reset(),
    then switches the stack to ScanTablePage.
    """
    carrier_selected = pyqtSignal(str)

    _CARRIERS = _CARRIER_DEFS

    def __init__(self, parent=None):
        super().__init__(parent)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(_s(90), _s(90), _s(90), _s(90))
        lo.setSpacing(_s(21))

        title = QLabel('PO Scanner')
        title.setFont(QFont('Segoe UI', _s(48), QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f'color: {P["title"]}; background: transparent;')

        sub = QLabel('Select a carrier to begin')
        sub.setFont(QFont('Segoe UI', _s(22)))
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f'color: {P["subtitle"]}; background: transparent;')

        lo.addStretch(1)
        lo.addWidget(title)
        lo.addWidget(sub)
        lo.addSpacing(_s(72))

        grid = QWidget()
        grid.setStyleSheet('background: transparent;')
        gl = QHBoxLayout(grid)
        gl.setSpacing(_s(30))
        gl.setContentsMargins(0, 0, 0, 0)

        for label, key, color in self._CARRIERS:
            btn = QPushButton(label)
            btn.setFixedSize(_s(270), _s(135))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(QFont('Segoe UI', _s(24), QFont.Bold))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    color: white;
                    border: none;
                    border-radius: {_s(21)}px;
                }}
                QPushButton:hover   {{ background: {_darken(color, 20)}; }}
                QPushButton:pressed {{ background: {_darken(color, 35)}; }}
            """)
            _shadow(btn, blur=27, dy=8)
            btn.clicked.connect(lambda _, k=key: self.carrier_selected.emit(k))
            gl.addWidget(btn)

        lo.addWidget(grid, 0, Qt.AlignCenter)
        lo.addSpacing(_s(48))

        help_btn = QPushButton('▶  How to Use')
        help_btn.setCursor(Qt.PointingHandCursor)
        help_btn.setFont(QFont('Segoe UI', _s(18)))
        help_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {P['subtitle']};
                border: {_s(2)}px solid {P['border']};
                border-radius: {_s(10)}px;
                padding: {_s(10)}px {_s(28)}px;
            }}
            QPushButton:hover {{ color: {P['title']}; border-color: {P['subtitle']}; }}
        """)
        help_btn.clicked.connect(self._open_guide)
        help_row = QHBoxLayout()
        help_row.addStretch()
        help_row.addWidget(help_btn)
        help_row.addStretch()
        lo.addLayout(help_row)
        lo.addStretch(1)


    def _open_guide(self):
        if getattr(sys, 'frozen', False):
            path = Path(sys.executable).parent / 'Guide video' / 'How to use PO scanner guide.mov'
        else:
            path = BASE_DIR / 'How to use PO scanner guide.mov'
        if path.exists():
            os.startfile(str(path))


# ── Table drag-to-scroll (damped, no kinetic) ────────────────────────────────

class _TableDragScroll(QObject):
    _THRESH = 8    # px movement before drag mode activates (distinguishes tap vs drag)
    _SPEED  = 0.7  # scroll distance per drag pixel (requires ScrollPerPixel mode)

    def __init__(self, table):
        super().__init__(table)
        self._table    = table
        self._press_y  = None
        self._start_v  = 0
        self._dragging = False
        table.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is not self._table.viewport():
            return False
        t = event.type()
        if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._press_y  = event.pos().y()
            self._start_v  = self._table.verticalScrollBar().value()
            self._dragging = False
            return False                     # let cell clicks pass through
        if t == QEvent.MouseMove and self._press_y is not None:
            dy = event.pos().y() - self._press_y
            if not self._dragging and abs(dy) > _s(self._THRESH):
                self._dragging = True
            if self._dragging:
                self._table.verticalScrollBar().setValue(
                    int(self._start_v - dy * self._SPEED))
                return True                  # consume move so Qt kinetic doesn't also fire
        if t == QEvent.MouseButtonRelease:
            was = self._dragging
            self._press_y  = None
            self._dragging = False
            return was                       # consume release if dragging (no accidental cell click)
        return False


# ── Row-header highlight (subclass so paintSection can be overridden) ─────────

class _HighlightedVHeader(QHeaderView):
    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self._hl_rows: set = set()
        self._scan_rows: set = set()

    def set_highlighted(self, rows: set):
        self._hl_rows = rows
        self.viewport().update()

    def set_scan_row(self, rows: set):
        self._scan_rows = rows
        self.viewport().update()

    def paintSection(self, painter, rect, logical_index):
        if logical_index in self._hl_rows:
            painter.save()
            painter.fillRect(rect, QColor('#CC2222'))
            painter.setPen(QColor('white'))
            f = QFont('Segoe UI')
            f.setPixelSize(_s(28))
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(rect, Qt.AlignCenter, str(logical_index + 1))
            painter.restore()
        elif logical_index in self._scan_rows:
            painter.save()
            painter.fillRect(rect, QColor(P['btn_pri']))
            painter.setPen(QColor('white'))
            f = QFont('Segoe UI')
            f.setPixelSize(_s(24))
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(rect, Qt.AlignCenter, f'▶ {logical_index + 1}')
            painter.restore()
        else:
            super().paintSection(painter, rect, logical_index)


# ── Cell-border highlight delegate ───────────────────────────────────────────

class _RowHighlightDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._hl_rows: set = set()
        self._scan_rows: set = set()

    def set_highlighted(self, rows: set):
        self._hl_rows = rows

    def set_scan_row(self, rows: set):
        self._scan_rows = rows

    def paint(self, painter, option, index):
        if index.column() == COL_TRK:
            text = index.data(Qt.DisplayRole) or ''
            is_placeholder = bool(index.data(Qt.UserRole))
            if index.row() in self._scan_rows:
                self._paint_scan_row_cell(painter, option, index, text, is_placeholder)
            elif text.strip() and not is_placeholder:
                self._paint_tracking_cell(painter, option, index, text)
            else:
                super().paint(painter, option, index)
        else:
            super().paint(painter, option, index)

        if index.row() in self._hl_rows:
            painter.save()
            rect = option.rect
            bw = max(1, _s(3))
            painter.setPen(QPen(QColor('#FF4444'), bw))
            painter.drawLine(rect.right() - bw // 2, rect.top(),
                             rect.right() - bw // 2, rect.bottom())
            painter.drawLine(rect.left(), rect.bottom() - bw // 2,
                             rect.right(), rect.bottom() - bw // 2)
            painter.restore()

    def _paint_scan_row_cell(self, painter, option, index, text, is_placeholder):
        """Column 0 of the scan row: amber background + text, bypassing stylesheet."""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        bw = max(1, _s(3))
        r  = option.rect

        painter.save()
        painter.fillRect(r, QColor('#FFF3E0'))

        # borders matching the stylesheet
        painter.setPen(QPen(QColor('#C8A882'), bw))
        painter.drawLine(r.right() - bw//2, r.top(), r.right() - bw//2, r.bottom())
        painter.drawLine(r.left(), r.bottom() - bw//2, r.right(), r.bottom() - bw//2)

        if text.strip() and not is_placeholder:
            # actual tracking text — split-font render on amber
            fg_data = index.data(Qt.ForegroundRole)
            color = (fg_data if isinstance(fg_data, QColor) else QColor(fg_data)) if fg_data else QColor(P['text'])
            prefix, last4 = text[:-4], text[-4:]
            pad_x = _s(16)
            adj = r.adjusted(pad_x, 0, -_s(8), 0)
            sf = QFont(opt.font); sf.setPixelSize(_s(36)); sf.setBold(False)
            bf = QFont(opt.font); bf.setPixelSize(_s(75)); bf.setBold(True)
            pw = QFontMetrics(sf).horizontalAdvance(prefix)
            dim = QColor(color); dim.setAlphaF(0.3)
            painter.setFont(sf); painter.setPen(dim)
            painter.drawText(QRect(adj.left(), adj.top(), pw, adj.height()),
                             Qt.AlignVCenter | Qt.AlignLeft, prefix)
            painter.setFont(bf); painter.setPen(color)
            painter.drawText(QRect(adj.left() + pw, adj.top(), adj.width() - pw, adj.height()),
                             Qt.AlignVCenter | Qt.AlignLeft, last4)
        elif text:
            # placeholder text
            fg_data = index.data(Qt.ForegroundRole)
            color = (fg_data if isinstance(fg_data, QColor) else QColor(fg_data)) if fg_data else QColor(P['subtitle'])
            painter.setPen(color)
            painter.setFont(opt.font)
            painter.drawText(r.adjusted(_s(16), 0, -_s(8), 0),
                             Qt.AlignVCenter | Qt.AlignLeft, text)

        painter.restore()

    def _paint_tracking_cell(self, painter, option, index, text):
        # Draw background (hover, etc.) without text
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ''
        QApplication.style().drawControl(QStyle.CE_ItemViewItem, opt, painter)

        fg_data = index.data(Qt.ForegroundRole)
        if fg_data is not None:
            color = fg_data if isinstance(fg_data, QColor) else QColor(fg_data)
        else:
            color = QColor(P['text'])

        prefix = text[:-4]
        last4  = text[-4:]

        pad_x = _s(16)
        rect  = option.rect.adjusted(pad_x, 0, -_s(8), 0)

        small_font = QFont(opt.font)
        small_font.setPixelSize(_s(36))
        small_font.setBold(False)

        big_font = QFont(opt.font)
        big_font.setPixelSize(_s(75))
        big_font.setBold(True)

        prefix_w = QFontMetrics(small_font).horizontalAdvance(prefix)

        painter.save()

        dim_color = QColor(color)
        dim_color.setAlphaF(0.3)
        painter.setFont(small_font)
        painter.setPen(dim_color)
        painter.drawText(
            QRect(rect.left(), rect.top(), prefix_w, rect.height()),
            Qt.AlignVCenter | Qt.AlignLeft, prefix
        )

        painter.setFont(big_font)
        painter.setPen(color)
        painter.drawText(
            QRect(rect.left() + prefix_w, rect.top(), rect.width() - prefix_w, rect.height()),
            Qt.AlignVCenter | Qt.AlignLeft, last4
        )

        painter.restore()

        # Restore the stylesheet cell borders eaten by CE_ItemViewItem
        bw = max(1, _s(3))
        r = option.rect
        painter.save()
        painter.setPen(QPen(QColor('#C8A882'), bw))
        painter.drawLine(r.right() - bw // 2, r.top(), r.right() - bw // 2, r.bottom())
        painter.drawLine(r.left(), r.bottom() - bw // 2, r.right(), r.bottom() - bw // 2)
        painter.restore()


# ── Scan table page ───────────────────────────────────────────────────────────

class ScanTablePage(GradientWidget):
    """Main scan screen — table of tracking + PO records for the selected carrier.

    Input paths:
        A. Physical barcode scanner → eventFilter buffers keystrokes → _commit_tracking()
        B. Tap Tracking cell (empty) → _handle_tracking_cell() → TrackingEditDialog
        C. Tap PO cell (empty)       → _handle_po_cell()       → POCameraDialog
        D. Tap row number            → _on_action_delete() (via action bar)

    Batch scan: 'Scan All PO' button visible when tracking is gap-free and
    at least one row is missing a PO. Runs POCameraDialog sequentially;
    falls back to _POConfirmDialog if camera fails mid-batch.

    Save: appends new rows to monthly CSV, then calls reset() to reload
    the table (saved rows become green read-only).

    Emits back_requested() when user switches carrier or save-and-leave.
    """
    back_requested = pyqtSignal()


    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config        = config
        self._carrier       = ''

        # _scan_row: index of the next empty row where a new tracking scan will land.
        #            Always kept at least 3 rows ahead of the last filled row.
        self._scan_row      = 0

        # _loaded_count: number of rows loaded from CSV on page entry (read-only, shown in green).
        #                New scans are appended after this index.
        self._loaded_count  = 0

        # _bcode_buf: accumulates keystrokes from a physical barcode scanner (keyboard emulation).
        #             Flushed to the table when Enter/Return is received.
        self._bcode_buf     = ''

        self._worker_proc   = None
        self._cam_index     = _load_cam_state().get('cam_index', 0)
        # _trk_gap_warned: True after user confirms a gap warning — suppresses repeat warnings
        #                  until user cancels a tracking dialog (which re-arms it to False).
        self._trk_gap_warned = False
        self._hl_row: int = -1

        self._build_ui()
        QApplication.instance().installEventFilter(self)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(_s(20), _s(16), _s(20), _s(16))
        lo.setSpacing(_s(12))
        lo.addWidget(self._build_header())
        lo.addWidget(self._build_table(), 1)
        lo.addWidget(self._build_footer())

    def _build_steps(self):
        w = QWidget()
        w.setFixedHeight(_s(52))
        w.setStyleSheet(f'background: {P["bg_end"]}; border-radius: {_s(8)}px;')
        lo = QHBoxLayout(w)
        lo.setContentsMargins(_s(12), 0, _s(12), 0)
        lo.setSpacing(_s(8))

        self._action_bar = QWidget()
        ab_lo = QHBoxLayout(self._action_bar)
        ab_lo.setContentsMargins(0, 0, 0, 0)
        ab_lo.setSpacing(_s(8))
        self._edit_action_btn = _mk_btn('Edit',   P['btn_pri'], h=44, fs=18, min_w=120)
        self._del_action_btn  = _mk_btn('Delete', '#CC2222',   h=44, fs=18, min_w=120)
        self._edit_action_btn.clicked.connect(self._on_action_edit)
        self._del_action_btn.clicked.connect(self._on_action_delete)
        ab_lo.addWidget(self._edit_action_btn)
        ab_lo.addWidget(self._del_action_btn)
        self._action_bar.hide()
        lo.addWidget(self._action_bar)

        lo.addStretch(1)
        lo.addSpacing(_s(8))
        return w



    def _build_header(self):
        w = QWidget()
        w.setStyleSheet('background: transparent;')
        w.setFixedHeight(_s(76))
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(_s(12))

        self._carrier_badge = QPushButton('')
        self._carrier_badge.setFont(QFont('Segoe UI', _s(36), QFont.Bold))
        self._carrier_badge.setStyleSheet(f"""
            QPushButton {{
                color: white;
                background: {P['btn_pri']};
                border-radius: {_s(10)}px;
                padding: {_s(6)}px {_s(18)}px;
                border: none;
            }}
            QPushButton:pressed {{
                background: {P['btn_pri_pressed'] if 'btn_pri_pressed' in P else P['btn_pri']};
                opacity: 0.85;
            }}
        """)
        self._carrier_badge.clicked.connect(self._on_change_carrier_clicked)

        h.addWidget(self._carrier_badge)
        h.addSpacing(_s(12))
        h.addWidget(self._build_steps(), 1)
        h.addSpacing(_s(140))
        return w

    def _build_table(self):
        self._table = QTableWidget(0, N_COLS)
        self._table.setHorizontalHeaderLabels(['Tracking Number', 'PO', 'Number', 'RN', 'PC'])

        hdr = self._table.horizontalHeader()
        for _c in range(N_COLS):
            hdr.setSectionResizeMode(_c, QHeaderView.Fixed)
        hdr.setStretchLastSection(False)

        self._vheader = _HighlightedVHeader(self._table)
        self._vheader.setDefaultSectionSize(_s(90))
        self._vheader.setMinimumWidth(_s(62))
        self._vheader.setDefaultAlignment(Qt.AlignCenter)
        self._vheader.setSectionResizeMode(QHeaderView.Fixed)
        self._table.setVerticalHeader(self._vheader)

        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setFocusPolicy(Qt.NoFocus)

        self._table.setShowGrid(False)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background: white;
                border: {_s(2)}px solid {P['border']};
                border-radius: {_s(10)}px;
                outline: none;
                font-size: {_s(50)}px;
            }}
            QTableWidget::item {{
                padding: {_s(8)}px {_s(16)}px;
                border-right: {_s(3)}px solid #C8A882;
                border-bottom: {_s(3)}px solid #C8A882;
            }}
            QTableWidget::item:hover {{ background: #FFF3E8; }}
            QHeaderView::section {{
                background: {P['bg_start']};
                color: {P['title']};
                font-weight: bold;
                font-size: {_s(38)}px;
                border: none;
                border-bottom: {_s(2)}px solid {P['btn_pri']};
                padding: {_s(8)}px {_s(14)}px;
            }}
            QHeaderView::section:vertical {{
                background: {P['bg_end']};
                color: {P['subtitle']};
                font-size: {_s(28)}px;
                border: none;
                border-right: 1px solid {P['border']};
                border-bottom: 1px solid {P['border']};
            }}
            QTableCornerButton::section {{
                background: {P['bg_start']};
                border: none;
                border-right: 1px solid {P['border']};
                border-bottom: {_s(2)}px solid {P['btn_pri']};
            }}
        """)

        self._table.verticalScrollBar().setStyleSheet(f"""
            QScrollBar:vertical {{
                background: {P['bg_end']};
                width: {_s(44)}px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {P['btn_pri']};
                min-height: {_s(52)}px;
                border-radius: {_s(6)}px;
                margin: {_s(4)}px {_s(4)}px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_darken(P['btn_pri'], 15)};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._table.cellClicked.connect(self._on_cell_clicked)
        self._drag_scroll = _TableDragScroll(self._table)
        self._cell_delegate = _RowHighlightDelegate(self._table)
        self._table.setItemDelegate(self._cell_delegate)
        self._vheader.setSectionsClickable(False)

        for _ in range(6):
            self._append_row()

        self._highlight_scan_row()
        return self._table

    def _build_footer(self):
        w = QWidget()
        w.setStyleSheet('background: transparent;')
        w.setFixedHeight(_s(96))
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(_s(16))

        self._count_label = QLabel('')
        self._count_label.setFont(QFont('Segoe UI', _s(24)))
        self._count_label.setStyleSheet(f'color: {P["subtitle"]}; background: transparent;')

        self._batch_btn = _mk_btn('Scan All PO', P['btn_pri'], h=84, fs=22, min_w=260)
        self._batch_btn.clicked.connect(self._batch_po_scan)
        _shadow(self._batch_btn, blur=24, dy=7)
        self._batch_btn.setVisible(False)

        save_btn = _mk_btn('Save', P['btn_suc'], h=84, fs=22, min_w=300)
        save_btn.clicked.connect(self._on_save)
        _shadow(save_btn, blur=30, dy=9)

        h.addWidget(self._count_label)
        h.addStretch()
        h.addWidget(self._batch_btn)
        h.addWidget(save_btn)
        return w

    # ── Row helpers ───────────────────────────────────────────────────────────

    def _append_row(self):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setVerticalHeaderItem(row, QTableWidgetItem(str(row + 1)))
        for c in range(N_COLS):
            item = QTableWidgetItem('')
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            item.setForeground(QColor(P['text']))
            self._table.setItem(row, c, item)

    # Placeholder text for each column when the row is empty
    _PLACEHOLDER_TEXT = ['Scan directly or tap to enter manually', 'Tap to open camera', '—', '—', '—']

    def _set_highlight(self, row: int):
        """Tap-select a row: red background, action bar, hide scan indicator."""
        self._hl_row = row
        for r in range(self._table.rowCount()):
            bg = QColor('#FF9999') if r == row else QColor('white')
            for c in range(N_COLS):
                item = self._table.item(r, c)
                if item:
                    item.setBackground(bg)
        self._vheader.set_highlighted({row})
        self._vheader.set_scan_row(set())
        self._cell_delegate.set_highlighted({row})
        self._cell_delegate.set_scan_row(set())
        self._action_bar.show()
        self._table.viewport().update()

    def _clear_highlight(self):
        """Clear tap-row selection only. Scan indicator is not changed."""
        self._hl_row = -1
        for r in range(self._table.rowCount()):
            for c in range(N_COLS):
                item = self._table.item(r, c)
                if item:
                    item.setBackground(QColor('white'))
        self._vheader.set_highlighted(set())
        self._cell_delegate.set_highlighted(set())
        self._action_bar.hide()

    def _highlight_scan_row(self):
        """Reset to scan state: clear tap selection, refresh placeholders and scan indicator."""
        self._clear_highlight()
        self._update_placeholders()
        self._vheader.set_scan_row({self._scan_row})
        self._cell_delegate.set_scan_row({self._scan_row})
        self._table.viewport().update()

    def _on_action_edit(self):
        row = self._hl_row
        if row < 0:
            return
        if row < self._loaded_count:
            AlertDialog('Saved records cannot be edited here.\nPlease edit directly in Excel.', self).exec_()
            return

        def _cell_val(c):
            it = self._table.item(row, c)
            return it.text().strip() if (it and not it.data(Qt.UserRole)) else ''

        edit_dlg = _EditAllDialog(
            tracking=_cell_val(0),
            po_parts={'po': _cell_val(1), 'number': _cell_val(2),
                      'rn': _cell_val(3), 'pc':     _cell_val(4)},
            parent=self, package_num=row + 1,
        )
        if edit_dlg.exec_() != QDialog.Accepted:
            return

        for col_idx, val in enumerate(
                [edit_dlg.tracking_value, edit_dlg.po_value,
                 edit_dlg.number_value,   edit_dlg.rn_value, edit_dlg.pc_value]):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            item.setForeground(QColor(P['text']))
            item.setData(Qt.UserRole, False)    
            self._table.setItem(row, col_idx, item)

        self._set_highlight(row)
        self._update_placeholders()
        self._update_count()

    def _on_action_delete(self):
        row = self._hl_row
        if row < 0:
            return
        if row < self._loaded_count:
            AlertDialog('Saved records cannot be deleted here.\nPlease edit directly in Excel.', self).exec_()
            return
        def _val(col):
            it = self._table.item(row, col)
            return it.text().strip() if it and it.text().strip() and not it.data(Qt.UserRole) else ''
        trk_text = _val(COL_TRK) or '—'
        po_text  = ' '.join(v for v in (_val(COL_PO), _val(COL_NUM), _val(COL_RN), _val(COL_PC)) if v) or '—'
        has_trk  = trk_text != '—'
        dlg = _SaveWarnDialog(
            f'Delete Package <b>#{row + 1}</b>?<br><br>'
            f'Tracking:&nbsp;&nbsp;{trk_text}<br>'
            f'PO:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{po_text}',
            self,
            confirm_text='Delete',
            confirm_color='#CC2222',
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        self._clear_highlight()
        self._table.removeRow(row)
        for r in range(self._table.rowCount()):
            hdr = self._table.verticalHeaderItem(r)
            if hdr:
                hdr.setText(str(r + 1))
        if row < self._scan_row:
            self._scan_row = max(0, self._scan_row - 1)
        while self._scan_row + 3 > self._table.rowCount():
            self._append_row()
        self._highlight_scan_row()
        self._update_count()

    def _update_placeholders(self):
        # Show greyed-out hint text on the "next expected" empty cell.
        # Tracking placeholder → always at _scan_row (next scan target).
        # PO placeholder → first row that has tracking but no PO yet (falls back to _scan_row).
        po_ph_row = self._scan_row
        for r in range(self._loaded_count, self._table.rowCount()):
            trk = self._table.item(r, COL_TRK)
            po  = self._table.item(r, COL_PO)
            has_trk = trk and trk.text().strip() and not trk.data(Qt.UserRole)
            has_po  = po  and po.text().strip()  and not po.data(Qt.UserRole)
            if has_trk and not has_po:
                po_ph_row = r
                break

        for r in range(self._loaded_count, self._table.rowCount()):
            for c in range(N_COLS):
                item = self._table.item(r, c)
                if item is None:
                    continue
                is_ph    = bool(item.data(Qt.UserRole))
                ph_row   = self._scan_row if c == COL_TRK else po_ph_row
                if r == ph_row and (not item.text() or is_ph):
                    item.setText(self._PLACEHOLDER_TEXT[c])
                    item.setForeground(QColor('#C0B5AA'))
                    item.setData(Qt.UserRole, True)
                elif is_ph:
                    item.setText('')
                    item.setForeground(QColor(P['text']))
                    item.setData(Qt.UserRole, False)

    def _update_count(self):
        # Recount real tracking entries and show/hide Scan All PO button based on batch eligibility.
        n = sum(
            1 for r in range(self._table.rowCount())
            if self._table.item(r, COL_TRK)
            and self._table.item(r, COL_TRK).text().strip()
            and not self._table.item(r, COL_TRK).data(Qt.UserRole)
        )
        self._count_label.setText(
            f'{n} tracking number{"s" if n != 1 else ""} scanned'
        )
        eligible, _ = self._check_batch_eligible()
        self._batch_btn.setVisible(eligible)

    def _check_batch_eligible(self) -> tuple:
        """Return (eligible, target_rows).
        Eligible only when tracking and PO are both gap-free from row 0,
        and more than 2 trailing rows have tracking but no PO."""
        rows = self._table.rowCount()
        def _row_has_po(r):
            for c in (COL_PO, COL_NUM, COL_RN, COL_PC):
                it = self._table.item(r, c)
                if it and it.text().strip() and not it.data(Qt.UserRole):
                    return True
            return False

        has_trk, has_po = [], []
        for r in range(rows):
            t = self._table.item(r, COL_TRK)
            has_trk.append(bool(t and t.text().strip() and not t.data(Qt.UserRole)))
            has_po.append(_row_has_po(r))

        # Tracking must be a solid block from row 0 — no gaps
        last_trk = -1
        seen_gap = False
        for r, ht in enumerate(has_trk):
            if ht:
                if seen_gap:
                    return False, []
                last_trk = r
            else:
                seen_gap = True

        if last_trk < 0:
            return False, []

        # PO must also be a solid block from row 0 — no gaps within tracking rows
        last_po = -1
        seen_gap = False
        for r in range(last_trk + 1):
            if has_po[r]:
                if seen_gap:
                    return False, []
                last_po = r
            else:
                seen_gap = True

        targets = list(range(last_po + 1, last_trk + 1))
        if len(targets) <= 2:
            return False, []
        return True, targets

    def _batch_po_scan(self):
        eligible, targets = self._check_batch_eligible()
        if not eligible:
            return
        if self._worker_proc is None:
            AlertDialog('OCR is not ready yet.', self).exec_()
            return

        total = len(targets)
        last_po_parts: dict = {}

        # cam_failed: once camera fails on any package, all subsequent packages skip
        # the camera entirely and go straight to _POConfirmDialog (manual entry).
        # This avoids a 3-second timeout wait per package when the camera is broken.
        # The "Copy Previous PO" button in _POConfirmDialog lets the user re-use the last confirmed PO without typing, making same-PO batches fast even without camera.
        cam_failed = False

        for i, row in enumerate(targets):
            t_item = self._table.item(row, COL_TRK)
            trk_raw = t_item.text().strip() if t_item else ''
            trk_tail = trk_raw[-4:] if len(trk_raw) >= 4 else trk_raw

            if cam_failed:
                # Camera already confirmed broken — skip straight to manual entry
                dlg = _POConfirmDialog('', self,
                                       package_num=row + 1,
                                       tracking_tail=trk_tail,
                                       autofill_rules=self._config.get('po_autofill', []),
                                       prev_po_parts=last_po_parts if last_po_parts else None,
                                       retake_label='Cancel',
                                       batch_info=(i + 1, total))
            else:
                dlg = POCameraDialog(
                    self._worker_proc, self._config, self._cam_index, self,
                    package_num=row + 1,
                    tracking_tail=trk_tail,
                    batch_info=(i + 1, total),
                    last_po_parts=last_po_parts,
                )

            if dlg.exec_() != QDialog.Accepted:
                break

            # Check if this was the first camera failure — flip flag for remaining packages
            if not cam_failed and dlg.camera_failed:
                cam_failed = True
            last_po_parts = {
                'po': dlg.po_value, 'number': dlg.number_value,
                'rn': dlg.rn_value, 'pc':     dlg.pc_value,
            }
            self._apply_po_to_row(row, dlg)

    # ── Public API ────────────────────────────────────────────────────────────

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._resize_columns)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._resize_columns()

    def _resize_columns(self):
        vhdr_w = self._table.verticalHeader().width()
        avail  = self._table.width() - vhdr_w - _s(44) - 4  # subtract scrollbar + border
        if avail > 100:
            self._table.setColumnWidth(COL_TRK, int(avail * 0.50))
            self._table.setColumnWidth(COL_PO,  int(avail * 0.10))
            self._table.setColumnWidth(COL_NUM, int(avail * 0.22))
            self._table.setColumnWidth(COL_RN,  int(avail * 0.07))
            self._table.setColumnWidth(COL_PC,  int(avail * 0.11))

    def set_carrier(self, carrier: str):
        self._carrier = carrier
        self._carrier_badge.setText(_CARRIER_LABELS.get(carrier, carrier.upper()))
        color = _CARRIER_COLORS.get(carrier, P['btn_pri'])
        self._carrier_badge.setStyleSheet(f"""
            QPushButton {{
                color: white;
                background: {color};
                border-radius: {_s(10)}px;
                padding: {_s(6)}px {_s(18)}px;
                border: none;
            }}
            QPushButton:pressed {{ background: {_darken(color, 30)}; }}
        """)

    def set_worker(self, proc):
        self._worker_proc = proc

    def _has_unsaved_data(self) -> bool:
        for r in range(self._loaded_count, self._table.rowCount()):
            item = self._table.item(r, COL_TRK)
            if item and item.text().strip() and not item.data(Qt.UserRole):
                return True
        return False

    def _on_change_carrier_clicked(self):
        if self._has_unsaved_data():
            dlg = _SaveWarnDialog(
                'You have unsaved records.<br>Would you like to save before switching carrier?',
                self,
                confirm_text='Yes, save && switch',  # && renders as literal & in Qt button text
                confirm_color=P['btn_suc'],
            )
            if dlg.exec_() != QDialog.Accepted:
                return
            if not self._do_save():
                return
        self.back_requested.emit()

    def reset(self, carrier: str = ''):
        self._scan_row       = 0
        self._loaded_count   = 0
        self._bcode_buf      = ''
        self._trk_gap_warned = False
        self._table.setRowCount(0)

        records = _load_csv_carrier(self._config, carrier) if carrier else []
        for tracking, po, number, rn, pc in records:
            self._append_row()
            r = self._table.rowCount() - 1
            for col_idx, val in enumerate([tracking, po, number, rn, pc]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                item.setForeground(QColor('#16A34A'))
                item.setData(Qt.UserRole, False)
                self._table.setItem(r, col_idx, item)

        self._loaded_count = len(records)
        self._scan_row = self._loaded_count
        while self._scan_row + 3 > self._table.rowCount():
            self._append_row()
        self._highlight_scan_row()
        self._update_count()

    # ── Barcode scanner event filter ──────────────────────────────────────────

    def eventFilter(self, obj, event):
        if not self.isVisible():
            return False
        if QApplication.activeModalWidget() is not None:
            return False
        if event.type() == QEvent.KeyPress:
            key  = event.key()
            text = event.text()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                buf = self._bcode_buf.strip()
                self._bcode_buf = ''
                if buf and _is_valid_tracking(buf):
                    self._commit_tracking(buf)
                return True
            if text and text.isprintable() and len(text) == 1:
                self._bcode_buf += text
                return True
        return False

    def _commit_tracking(self, tracking: str):
        # Called by the barcode scanner event filter after a valid tracking is received.
        # Writes to _scan_row, advances it, and keeps 3 empty buffer rows below.
        row = self._scan_row
        while row >= self._table.rowCount():
            self._append_row()

        item = QTableWidgetItem(tracking)
        item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        item.setForeground(QColor(P['text']))
        item.setData(Qt.UserRole, False)
        self._table.setItem(row, COL_TRK, item)

        self._scan_row += 1
        while self._scan_row + 3 > self._table.rowCount():
            self._append_row()

        self._table.scrollToItem(self._table.item(self._scan_row, 0))
        self._highlight_scan_row()
        self._update_count()

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _apply_po_to_row(self, row: int, dlg):
        for col_idx, val in enumerate(
                [dlg.po_value, dlg.number_value, dlg.rn_value, dlg.pc_value], COL_PO):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            item.setForeground(QColor(P['text']))
            item.setData(Qt.UserRole, False)
            self._table.setItem(row, col_idx, item)
        self._update_placeholders()
        self._update_count()
        self._table.scrollToItem(self._table.item(row, COL_PO))

    # ── Cell click ────────────────────────────────────────────────────────────

    def _on_cell_clicked(self, row: int, col: int):
        if row < self._loaded_count:
            return
        clicked = self._table.item(row, col)
        cell_has_value = bool(clicked and clicked.text().strip() and not clicked.data(Qt.UserRole))
        if cell_has_value:
            if self._hl_row == row:
                self._highlight_scan_row()
            else:
                self._set_highlight(row)
            return

        self._highlight_scan_row()

        if col == COL_TRK:
            self._handle_tracking_cell(row)
        elif col in (COL_PO, COL_NUM, COL_RN, COL_PC):
            self._handle_po_cell(row)

    def _handle_tracking_cell(self, row: int):
        # Gap warning state machine:
        #   - Warn once when user skips rows (e.g. fills row 5 before row 3)
        #   - _trk_gap_warned = True after user clicks Continue → no repeat warnings
        #   - _trk_gap_warned = False again if user cancels the TrackingEditDialog
        #     (they abandoned the fill, so next attempt should warn again)
        if row > 0 and not self._trk_gap_warned:
            empty_rows = [
                r + 1 for r in range(row)
                if not (self._table.item(r, COL_TRK)
                        and self._table.item(r, COL_TRK).text().strip()
                        and not self._table.item(r, COL_TRK).data(Qt.UserRole))
            ]
            if empty_rows:
                nums = ', '.join(f'#{n}' for n in empty_rows)
                warn = _SaveWarnDialog(
                    f'Package(s) {nums} have <span style="color:#EF4444;">no tracking number</span>.<br>'
                    f'Are you sure you want to fill Package #{row + 1}?',
                    self, confirm_text='Continue', confirm_color=P['btn_pri'],
                )
                if warn.exec_() != QDialog.Accepted:
                    return
                self._trk_gap_warned = True

        # Read existing value to pre-fill dialog (UserRole=True means placeholder, treat as empty)
        cur_item = self._table.item(row, COL_TRK)
        cur = '' if (cur_item is None or cur_item.data(Qt.UserRole)) else cur_item.text()
        def _cell(r, c):
            it = self._table.item(r, c)
            return it.text().strip() if it and it.text().strip() and not it.data(Qt.UserRole) else ''
        po_full = ' '.join(v for v in (
            _cell(row, COL_PO), _cell(row, COL_NUM),
            _cell(row, COL_RN), _cell(row, COL_PC),
        ) if v)
        po_ctx = f'PO: {po_full}' if po_full else ''

        # Open dialog
        dlg = TrackingEditDialog(cur, self, title='Enter Tracking',
                                 package_num=row + 1, context_label=po_ctx)

        # Write result, or re-arm gap warning on cancel
        if dlg.exec_() == QDialog.Accepted and dlg.value:
            item = QTableWidgetItem(dlg.value)
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            item.setForeground(QColor(P['text']))
            item.setData(Qt.UserRole, False)
            self._table.setItem(row, COL_TRK, item)
            # Advance scan row if user filled the current scan position
            if row == self._scan_row:
                self._scan_row = row + 1
                while self._scan_row + 3 > self._table.rowCount():
                    self._append_row()
            self._highlight_scan_row()
            self._update_count()
        else:
            self._trk_gap_warned = False

    def _handle_po_cell(self, row: int):
        # Warn if the previous row's PO is still empty (check all PO sub-columns)
        if row > 0:
            prev_filled = any(
                (lambda it: it and it.text().strip() and not it.data(Qt.UserRole))(
                    self._table.item(row - 1, c))
                for c in (COL_PO, COL_NUM, COL_RN, COL_PC)
            )
            if not prev_filled:
                warn = _SaveWarnDialog(
                    f'Package #{row} <span style="color:#EF4444;">PO is empty</span>.<br>'
                    f'Are you sure you want to fill Package #{row + 1}?',
                    self, confirm_text='Continue', confirm_color=P['btn_pri'],
                )
                if warn.exec_() != QDialog.Accepted:
                    return

        if self._worker_proc is None:
            AlertDialog('OCR is not ready yet.', self).exec_()
            return

        # Read tracking tail for display in camera dialog (last 4 chars)
        t_item = self._table.item(row, COL_TRK)
        trk_raw = (t_item.text().strip()
                   if t_item and t_item.text().strip() and not t_item.data(Qt.UserRole)
                   else '')
        trk_tail = trk_raw[-4:] if len(trk_raw) >= 4 else trk_raw

        # Read existing PO sub-fields to pre-fill manual entry
        def _cell_val(col):
            it = self._table.item(row, col)
            return it.text().strip() if it and it.text().strip() and not it.data(Qt.UserRole) else ''
        existing = {'po': _cell_val(COL_PO), 'number': _cell_val(COL_NUM),
                    'rn': _cell_val(COL_RN),  'pc':     _cell_val(COL_PC)}
        prefill = existing if any(existing.values()) else None

        # Open camera dialog and write result
        dlg = POCameraDialog(self._worker_proc, self._config, self._cam_index, self,
                             package_num=row + 1, tracking_tail=trk_tail, prefill=prefill)
        if dlg.exec_() == QDialog.Accepted:
            self._apply_po_to_row(row, dlg)
            self._highlight_scan_row()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _do_save(self) -> bool:
        """Collect new rows, show warnings + confirm, write CSV. Returns True on success."""
        rows = []
        missing_po = []
        orphan_po  = []

        for r in range(self._loaded_count, self._table.rowCount()):
            def _v(c, _r=r):
                it = self._table.item(_r, c)
                return it.text().strip() if (it and not it.data(Qt.UserRole)) else ''
            trk    = _v(0)
            po     = _v(1)
            number = _v(2)
            rn     = _v(3)
            pc     = _v(4)
            has_trk = bool(trk)
            has_po  = bool(po or number or rn or pc)
            if has_trk:
                rows.append((trk, po, number, rn, pc))
                if not has_po:
                    missing_po.append(r + 1)
            elif has_po:
                orphan_po.append(r + 1)
                rows.append(('', po, number, rn, pc))

        if not rows:
            AlertDialog('No new records to save.', self).exec_()
            return False

        warnings = []
        if missing_po:
            nums = ', '.join(f'#{n}' for n in missing_po)
            warnings.append(f'Package(s) {nums} have tracking but <span style="color:#EF4444;">no PO number</span>.')
        if orphan_po:
            nums = ', '.join(f'#{n}' for n in orphan_po)
            warnings.append(f'Package(s) {nums} have a PO but <span style="color:#EF4444;">no tracking number</span>.')

        if warnings:
            if _SaveWarnDialog('<br><br>'.join(warnings), self,
                               confirm_text='Continue to Save').exec_() != QDialog.Accepted:
                return False

        carrier_label = self._carrier.upper() if self._carrier else 'current carrier'
        n = len(rows)
        if _SaveWarnDialog(
            f'Save <b>{n}</b> new package{"s" if n != 1 else ""} for <b>{carrier_label}</b>?'
            f'<br><br><span style="color:#9B9B9B;font-size:90%;">Saved records cannot be edited in this app.<br>To make corrections, edit directly in Excel.</span>',
            self,
            confirm_text='Confirm Save',
            confirm_color=P['btn_suc'],
        ).exec_() != QDialog.Accepted:
            return False

        ok, err = _save_csv(self._config, self._carrier, rows)
        if not ok:
            AlertDialog(f'Cannot save.\n{err}', self).exec_()
            return False
        return True

    def _on_save(self):
        if self._do_save():
            self.reset(self._carrier)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """Root window — manages navigation between CarrierSelectPage and ScanTablePage.

    Uses a QStackedWidget to switch between the two pages.
    Floating close (✕) and minimise (—) buttons replace window chrome (app runs fullscreen).
    Intercepts closeEvent to prompt save if there are unsaved records.
    """
    def __init__(self, config: dict):
        super().__init__()
        self.setWindowTitle(config.get('ui', {}).get('window_title', 'PO Scanner'))
        self._stack         = QStackedWidget()
        self._carrier_page  = CarrierSelectPage()
        self._scan_page     = ScanTablePage(config)
        self._stack.addWidget(self._carrier_page)
        self._stack.addWidget(self._scan_page)
        self._stack.setCurrentWidget(self._carrier_page)
        self.setCentralWidget(self._stack)

        self._carrier_page.carrier_selected.connect(self._on_carrier_selected)
        self._scan_page.back_requested.connect(self._go_carrier)

        # Floating close button (fullscreen has no window chrome)
        self._close_btn = QPushButton('✕')
        self._close_btn.setParent(self)
        self._close_btn.setFixedSize(_s(52), _s(52))
        self._close_btn.setFont(QFont('Segoe UI', _s(16), QFont.Bold))
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(180,60,60,220); color: white;
                border-radius: {_s(10)}px; border: none;
            }}
            QPushButton:hover {{ background: rgba(210,50,50,255); }}
        """)
        self._close_btn.clicked.connect(self.close)
        self._close_btn.raise_()

        # Floating minimize button
        self._min_btn = QPushButton('—')
        self._min_btn.setParent(self)
        self._min_btn.setFixedSize(_s(52), _s(52))
        self._min_btn.setFont(QFont('Segoe UI', _s(16), QFont.Bold))
        self._min_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(100,100,100,200); color: white;
                border-radius: {_s(10)}px; border: none;
            }}
            QPushButton:hover {{ background: rgba(130,130,130,255); }}
        """)
        self._min_btn.clicked.connect(self.showMinimized)
        self._min_btn.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        m = _s(12)
        self._close_btn.move(self.width() - self._close_btn.width() - m, m)
        self._min_btn.move(self.width() - self._close_btn.width() - self._min_btn.width() - m * 2, m)
        self._close_btn.raise_()
        self._min_btn.raise_()

    def bring_to_front(self):
        self.showFullScreen()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, e):
        if (self._stack.currentWidget() is self._scan_page
                and self._scan_page._has_unsaved_data()):
            dlg = _SaveWarnDialog(
                'You have unsaved records.<br>Would you like to save before closing?',
                parent=self,
                confirm_text='Yes, save && exit',  # && renders as literal & in Qt button text
            )
            pg = self.geometry()
            dlg.adjustSize()
            dlg.move(
                pg.x() + (pg.width()  - dlg.width())  // 2,
                pg.y() + (pg.height() - dlg.height()) // 2,
            )
            result = dlg.exec_()
            if result == QDialog.Accepted:
                if not self._scan_page._do_save():
                    e.ignore()
                    return
            elif result == QDialog.Rejected:
                e.ignore()
                return
        e.accept()

    def set_worker(self, proc):
        self._scan_page.set_worker(proc)

    def _on_carrier_selected(self, carrier: str):
        self._scan_page.set_carrier(carrier)
        self._scan_page.reset(carrier)
        self._stack.setCurrentWidget(self._scan_page)

    def _go_carrier(self):
        self._stack.setCurrentWidget(self._carrier_page)


# ── CSV helpers ───────────────────────────────────────────────────────────────

_CSV_FIELDNAMES = ['Date', 'Carrier', 'Package#', 'Tracking', 'PO', 'Number', 'RN', 'PC']


def _csv_path(config: dict) -> 'Path':
    import calendar
    from datetime import date
    folder = config.get('csv', {}).get('folder', '')
    today = date.today()
    month_name = calendar.month_name[today.month]
    return Path(folder) / f'PO_{month_name}_{today.year}.csv'


def _norm_date(s: str) -> str:
    """Normalise date string to YYYY-MM-DD, accepting 2026-05-27 / 5/27/2026 / 2026/5/27."""
    from datetime import datetime
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return s.strip()


def _save_csv(config: dict, carrier: str, new_rows: list) -> 'tuple[bool, str]':
    """Append new rows to monthly CSV, skipping tracking numbers already saved today."""
    import csv
    from datetime import date

    if not config.get('csv', {}).get('folder', ''):
        return False, 'CSV folder not configured.'

    today_str = date.today().isoformat()
    p = _csv_path(config)

    existing_trackings: set = set()
    pkg_count = 0
    file_has_content = p.exists() and p.stat().st_size > 0

    if file_has_content:
        try:
            with open(p, 'r', newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    if _norm_date(row.get('Date', '')) == today_str and row.get('Carrier', '').lower() == carrier.lower():
                        pkg_count += 1
                        t = row.get('Tracking', '').strip().lstrip("'")
                        if t:
                            existing_trackings.add(t)
        except Exception as e:
            return False, str(e)

    to_append = [r for r in new_rows if not r[0] or r[0] not in existing_trackings]
    if not to_append:
        return True, ''

    try:
        mode = 'a' if file_has_content else 'w'
        with open(p, mode, newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES)
            if mode == 'w':
                writer.writeheader()
            for i, (tracking, po, number, rn, pc) in enumerate(to_append):
                writer.writerow({
                    'Date':     today_str,
                    'Carrier':  carrier,
                    'Package#': pkg_count + i + 1,
                    'Tracking': ("'" + tracking) if tracking else '',
                    'PO':       po,
                    'Number':   number,
                    'RN':       rn,
                    'PC':       pc,
                })
        return True, ''
    except Exception as e:
        return False, str(e)


def _load_csv_carrier(config: dict, carrier: str) -> list:
    """Read today's CSV rows for the given carrier. Returns [(tracking, po, number, rn, pc), ...]"""
    import csv
    from datetime import date

    today_str = date.today().isoformat()
    p = _csv_path(config)
    if not p.exists():
        return []
    try:
        with open(p, 'r', newline='', encoding='utf-8') as f:
            result = []
            for row in csv.DictReader(f):
                if _norm_date(row.get('Date', '')) == today_str and row.get('Carrier', '').lower() == carrier.lower():
                    tracking = row.get('Tracking', '').strip().lstrip("'")
                    if tracking:
                        result.append((
                            tracking,
                            row.get('PO',     '').strip(),
                            row.get('Number', '').strip(),
                            row.get('RN',     '').strip(),
                            row.get('PC',     '').strip(),
                        ))
        return result
    except Exception:
        return []



def _load_cam_state() -> dict:
    try:
        p = BASE_DIR / 'config' / 'camera_state.json'
        with open(p, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


# ── Entry point ───────────────────────────────────────────────────────────────

_INSTANCE_KEY = 'POScanner_SingleInstance_v1'

def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName('PO Scanner')

    # Single-instance check: try to connect to an existing instance
    _sock = QLocalSocket()
    _sock.connectToServer(_INSTANCE_KEY)
    if _sock.waitForConnected(500):
        _sock.write(b'RAISE')
        _sock.flush()
        _sock.waitForBytesWritten(1000)
        _sock.disconnectFromServer()
        sys.exit(0)
    _screen = QApplication.primaryScreen()
    _geo    = _screen.availableGeometry()
    _dpr    = _screen.devicePixelRatio()   # 1.0 @ 100%, 1.25 @ 125%, etc.
    # availableGeometry() may return physical pixels on some Qt/Windows combos;
    # dividing by dpr normalises to logical pixels in either case.
    ui_utils._S = min((_geo.width() / _dpr) / 1920.0, (_geo.height() / _dpr) / 1080.0)
    app.setFont(QFont('Segoe UI', max(6, round(10 * ui_utils._S))))

    config_path = BASE_DIR / 'config' / 'config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    loading  = LoadingWindow()
    loading.show()

    main_win = MainWindow(config)

    # Start single-instance server
    _server = QLocalServer(app)
    QLocalServer.removeServer(_INSTANCE_KEY)
    _server.listen(_INSTANCE_KEY)

    def _on_new_connection():
        conn = _server.nextPendingConnection()
        if conn:
            conn.waitForReadyRead(500)
            conn.close()
            main_win.bring_to_front()

    _server.newConnection.connect(_on_new_connection)

    init_thread = InitThread(config)

    def _on_progress(val, msg):
        loading.set_progress(val)
        loading.set_status(msg)

    _ocr_ok = [True]

    def _on_init_done(ok):
        _ocr_ok[0] = ok
        if ok:
            main_win.set_worker(init_thread.worker_proc)
        else:
            loading.set_status('⚠  OCR init failed — see logs')
        QTimer.singleShot(300, _launch)

    def _launch():
        loading.close()
        main_win.showFullScreen()
        if not _ocr_ok[0]:
            QTimer.singleShot(200, lambda: AlertDialog(
                'OCR failed to start.\n\n'
                'The app is open, but PO barcode scanning will not work.\n'
                'Please restart the app.',
                main_win
            ).exec_())

    init_thread.progress.connect(_on_progress)
    init_thread.done.connect(_on_init_done)
    loading.set_status('Loading configuration…')
    loading.set_progress(10)
    init_thread.start()

    ret = app.exec_()
    os._exit(ret)


if __name__ == '__main__':
    main()
