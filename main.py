import os
import json
import sys
import time
from pathlib import Path
from typing import Optional


def _setup_chromium_flags():
    required_flags = [
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ]
    current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    existing = set(current.split()) if current else set()
    merged = list(existing)
    for flag in required_flags:
        if flag not in existing:
            merged.append(flag)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(merged).strip()


_setup_chromium_flags()

from PyQt5.QtCore import (
    QEvent,
    QObject,
    QRect,
    QTimer,
    Qt,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineScript, QWebEngineView
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QDialog,
    QTextEdit,
)

try:
    from pynput import keyboard
except Exception:
    keyboard = None

try:
    from qfluentwidgets import (
        LineEdit,
        PushButton as FluentButton,
        CheckBox as FluentCheckBox,
        Slider as FluentSlider,
    )

    HAVE_FLUENT = True
except Exception:
    HAVE_FLUENT = False
    LineEdit = QLineEdit
    FluentButton = QPushButton
    FluentCheckBox = QCheckBox
    FluentSlider = QSlider

    def setTheme(*_args, **_kwargs):
        return None


JS_EVENT_BRIDGE_INIT = r"""
(() => {
  const w = window;
  if (w.__subtitleEventBridgeInstalled) return true;

  const state = {
    subtitle: '',
    currentTime: null,
    isPlaying: false,
    title: document.title,
    url: location.href,
    updatedAt: Date.now(),
  };

  let hostBridge = null;
  let trackedMedia = null;
  let heartbeatTimer = null;
  let emitTimer = null;
  let nextMutationCheckAt = 0;

  const norm = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const textOf = (el) => (el ? norm(el.innerText || el.textContent || '') : '');

  const getVueStore = () => {
    const app = document.querySelector('#q-app');
    const vm = app && app.__vue__;
    if (!vm) return null;
    if (vm.$store) return vm.$store;
    if (vm.$root && vm.$root.$store) return vm.$root.$store;
    return null;
  };

  const hasAudioPlayerStore = () => {
    const store = getVueStore();
    return !!(store && store.state && store.state.AudioPlayer);
  };

  const isKikoeru = () => {
    if (hasAudioPlayerStore()) return true;
    return !!(
      document.querySelector('#currentLyricEl') ||
      document.querySelector('.isCurrentLrcLine') ||
      document.querySelector('[class*="currentLyric"]') ||
      document.querySelector('[class*="lyric-current"]')
    );
  };

  const readSubtitleFromStore = () => {
    try {
      const store = getVueStore();
      if (!store || !store.state || !store.state.AudioPlayer) return '';
      const ap = store.state.AudioPlayer;
      const lyric = ap.currentLyric;
      if (typeof lyric === 'string') return norm(lyric);
      if (lyric && typeof lyric.text === 'string') return norm(lyric.text);
    } catch (e) {}
    return '';
  };

  const readPlayingFromStore = () => {
    try {
      const store = getVueStore();
      if (!store || !store.state || !store.state.AudioPlayer) return null;
      const ap = store.state.AudioPlayer;
      return typeof ap.playing === 'boolean' ? ap.playing : null;
    } catch (e) {}
    return null;
  };

  const isBadSubtitle = (text) => {
    const t = String(text || '').toLowerCase();
    if (!t) return true;
    return (
      t.includes('cloud_upload') ||
      t.includes('选择字幕文件') ||
      t.includes('select subtitle file') ||
      t.includes('load local subtitle') ||
      t.includes('字幕文件') ||
      t.includes('翻译任务') ||
      t.includes('translation task')
    );
  };

  const strictKikoeruSelectors = [
    '#currentLyricEl',
    '[id="currentLyricEl"]',
    '.isCurrentLrcLine',
    '[class~="isCurrentLrcLine"]',
    '[id*="currentLyric"]',
    '[class*="currentLyric"]',
    '[class*="lyric-current"]',
    '[class*="current-lyric"]',
  ];

  const genericSelectors = [
    '[aria-live="polite"]',
    '[aria-live="assertive"]',
    '[class*="subtitle-current"]',
  ];

  const readSubtitleFromDom = () => {
    const media = document.querySelector('audio,video');
    const isPlaying = !!(media && !media.paused);
    const storePlaying = readPlayingFromStore();

    const storeText = readSubtitleFromStore();
    if (hasAudioPlayerStore()) {
      if (storePlaying && storeText && !isBadSubtitle(storeText)) return storeText;
      return '';
    }

    if (!isPlaying) return '';

    const selectors = isKikoeru() ? strictKikoeruSelectors : strictKikoeruSelectors.concat(genericSelectors);
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (!el) continue;
      if (el.closest('button,a,[role="button"],li,[class*="menu"],[class*="tab"]')) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 8 || rect.height < 8) continue;
      const t = textOf(el);
      if (t && !isBadSubtitle(t)) return t;
    }

    return '';
  };

  const updateSubtitle = () => {
    const t = readSubtitleFromDom();
    if (t) {
      state.subtitle = t;
    } else if (isKikoeru()) {
      state.subtitle = '';
    }
    state.title = document.title;
    state.url = location.href;
    state.updatedAt = Date.now();
  };

  const updateMediaState = () => {
    const media = document.querySelector('audio,video');
    if (media) {
      state.currentTime = Number.isFinite(media.currentTime) ? media.currentTime : null;
      state.isPlaying = !media.paused;
    }
    const storePlaying = readPlayingFromStore();
    if (typeof storePlaying === 'boolean') state.isPlaying = storePlaying;
    if (!media && storePlaying === null) {
      state.currentTime = null;
      state.isPlaying = false;
    }
  };

  const emitState = () => {
    if (!hostBridge || !hostBridge.pushState) return;
    try {
      hostBridge.pushState(JSON.stringify(state));
    } catch (e) {}
  };

  const scheduleEmit = () => {
    if (emitTimer) return;
    emitTimer = setTimeout(() => {
      emitTimer = null;
      emitState();
    }, 60);
  };

  const onPossibleUpdate = () => {
    updateMediaState();
    updateSubtitle();
    scheduleEmit();
  };

  const bindMedia = () => {
    const media = document.querySelector('audio,video');
    if (!media || media === trackedMedia) return;
    trackedMedia = media;
    const events = ['play', 'pause', 'timeupdate', 'seeking', 'seeked', 'ratechange', 'loadedmetadata'];
    for (const ev of events) {
      media.addEventListener(ev, onPossibleUpdate, { passive: true });
    }
    onPossibleUpdate();
  };

  const mo = new MutationObserver((mutations) => {
    const now = Date.now();
    if (now < nextMutationCheckAt) return;
    nextMutationCheckAt = now + 150;
    for (const m of mutations) {
      const node = m.target && m.target.nodeType === 1 ? m.target : m.target && m.target.parentElement;
      if (!node) continue;
      const cls = String(node.className || '').toLowerCase();
      const id = String(node.id || '').toLowerCase();
      if (cls.includes('lyric') || cls.includes('lrc') || cls.includes('subtitle') || id.includes('lyric') || id.includes('lrc') || id.includes('subtitle') || id === 'currentlyricel') {
        onPossibleUpdate();
        return;
      }
    }
  });

  const setupWebChannel = () => {
    if (!w.qt || !w.qt.webChannelTransport || !w.QWebChannel) return false;
    try {
      new w.QWebChannel(w.qt.webChannelTransport, (channel) => {
        hostBridge = channel.objects.subtitleBridge;
        onPossibleUpdate();
      });
      return true;
    } catch (e) {
      return false;
    }
  };

  const bootChannel = () => {
    if (setupWebChannel()) return;
    setTimeout(bootChannel, 200);
  };

  if (!w.QWebChannel) {
    const script = document.createElement('script');
    script.src = 'qrc:///qtwebchannel/qwebchannel.js';
    script.onload = bootChannel;
    script.onerror = bootChannel;
    (document.head || document.documentElement).appendChild(script);
  } else {
    bootChannel();
  }

  if (document.body) {
    mo.observe(document.body, { childList: true, subtree: true, characterData: false });
  }

  bindMedia();
  onPossibleUpdate();
  heartbeatTimer = setInterval(() => {
    bindMedia();
    onPossibleUpdate();
  }, 450);

  w.__subtitleEventBridgeInstalled = true;
  return true;
})();
"""


JS_AUTO_ENABLE_SUBTITLE = r"""
(() => {
  const visible = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const norm = (t) => (t || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const media = document.querySelector('audio,video');
  if (!media || media.paused) return {clicked: false, reason: 'no-active-media'};

  const hasLyricUi = !!(
    document.querySelector('#currentLyricEl') ||
    document.querySelector('.isCurrentLrcLine') ||
    document.querySelector('[class*="currentLyric"]') ||
    document.querySelector('[class*="lyric-current"]') ||
    document.querySelector('[title*="字幕"]') ||
    document.querySelector('[aria-label*="字幕"]')
  );
  if (!hasLyricUi) return {clicked: false, reason: 'no-lyric-ui'};

  const iconButtons = Array.from(document.querySelectorAll('button,div[role="button"],span[role="button"]'));

  const isSafeCandidate = (el) => {
    if (!el || !visible(el)) return false;
    if (el.closest('a,[href]')) return false;
    const text = norm(el.innerText || el.textContent || '');
    if (!text) return false;
    if (text.includes('翻译任务') || text.includes('translation task')) return false;
    const nearLyric = !!el.closest('[class*="lyric"],[id*="lyric"],[class*="subtitle"],[id*="subtitle"],[class*="player"],[class*="audio"]');
    return nearLyric;
  };

  const byText = iconButtons.find((el) => {
    const t = norm(el.innerText || el.textContent || '');
    if (!t) return false;
    return (t === 'subtitles' || t.includes('subtitle') || t.includes('字幕')) && isSafeCandidate(el);
  });

  let target = byText;
  if (!target) {
    const attrHit = document.querySelector('[aria-label*="subtitle" i], [title*="subtitle" i], [aria-label*="字幕"], [title*="字幕"]');
    if (isSafeCandidate(attrHit)) target = attrHit;
  }
  if (!target) return {clicked: false, reason: 'not-found'};

  for (let i = 0; i < 5 && target; i++) {
    if (typeof target.click === 'function' && isSafeCandidate(target)) {
      target.click();
      return {clicked: true, reason: 'clicked'};
    }
    target = target.parentElement;
  }
  return {clicked: false, reason: 'not-clickable'};
})();
"""

JS_PLAY_MEDIA = r"""
(() => {
  try {
    const app = document.querySelector('#q-app');
    const vm = app && app.__vue__;
    if (vm) {
      const store = vm.$store || (vm.$root && vm.$root.$store);
      if (store && store.state && store.state.AudioPlayer) {
        const ap = store.state.AudioPlayer;
        if (ap.playing === false && ap.currentSong) {
          if (store.dispatch) {
            store.dispatch('AudioPlayer/togglePlay').catch(()=>{});
          }
          store.commit('AudioPlayer/SET_PLAYING', true);
          return 'play via store commit';
        }
      }
    }
  } catch (e) {}

  const playBtn = document.querySelector('button[class*="play"], [class*="play-btn"], .q-btn[class*="play"]');
  if (playBtn) {
    playBtn.click();
    return 'click play button';
  }

  const media = document.querySelector('audio,video');
  if (media && media.paused) {
    media.play().catch(()=>{});
    return 'play via media';
  }
  return 'no action';
})();
"""

JS_PAUSE_MEDIA = r"""
(() => {
  try {
    const app = document.querySelector('#q-app');
    const vm = app && app.__vue__;
    if (vm) {
      const store = vm.$store || (vm.$root && vm.$root.$store);
      if (store && store.state && store.state.AudioPlayer && store.state.AudioPlayer.playing) {
        if (store.dispatch) {
          store.dispatch('AudioPlayer/togglePlay').catch(()=>{});
        }
        store.commit('AudioPlayer/SET_PLAYING', false);
        return 'pause via store';
      }
    }
  } catch (e) {}

  const media = document.querySelector('audio,video');
  if (media && !media.paused) {
    media.pause();
    return 'pause via media';
  }
  return 'no action';
})();
"""

JS_SET_GAIN = r"""
(() => {
  const gain = __GAIN_VALUE__;
  const media = document.querySelector('audio,video');
  if (!media) return 'no media';

  if (window.__gainMedia && window.__gainMedia !== media) {
    try {
      if (window.__gainSource) window.__gainSource.disconnect();
      if (window.__gainNode) window.__gainNode.disconnect();
      if (window.__gainContext) window.__gainContext.close();
    } catch(e) {}
    delete window.__gainContext;
    delete window.__gainSource;
    delete window.__gainNode;
    delete window.__gainMedia;
    delete window.__gainUsingGainNode;
  }

  if (!window.__gainContext) {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      window.__gainContext = new AudioCtx();
      window.__gainMedia = media;
      window.__gainSource = window.__gainContext.createMediaElementSource(media);
      window.__gainNode = window.__gainContext.createGain();
      window.__gainSource.connect(window.__gainContext.destination);
      window.__gainUsingGainNode = false;
    } catch(e) {
      return 'init error: ' + e.message;
    }
  }

  window.__gainNode.gain.value = gain;

  if (gain > 1 && !window.__gainUsingGainNode) {
    try {
      window.__gainSource.disconnect(window.__gainContext.destination);
      window.__gainSource.connect(window.__gainNode);
      window.__gainNode.connect(window.__gainContext.destination);
      window.__gainUsingGainNode = true;
    } catch(e) { return 'connect error: ' + e.message; }
  } else if (gain === 1 && window.__gainUsingGainNode) {
    try {
      window.__gainNode.disconnect(window.__gainContext.destination);
      window.__gainSource.disconnect(window.__gainNode);
      window.__gainSource.connect(window.__gainContext.destination);
      window.__gainUsingGainNode = false;
    } catch(e) { return 'disconnect error: ' + e.message; }
  }

  if (window.__gainContext.state === 'suspended') {
    window.__gainContext.resume();
  }
  return 'gain set to ' + gain;
})();
"""

# 日志收集
DEBUG_LOGS = []

def log_debug(msg):
    import datetime
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    DEBUG_LOGS.append(f"[{ts}] {msg}")
    if len(DEBUG_LOGS) > 200:
        DEBUG_LOGS.pop(0)


class ConfigStore:
    def __init__(self):
        if getattr(sys, "frozen", False):
            base_dir = Path(sys.executable).resolve().parent
        else:
            base_dir = Path(__file__).resolve().parent
        self.path = base_dir / "settings.json"
        self.data = {
            "homepage": "",
            "font_size": 36,
            "bg_alpha": 140,
            "font_color": "#FFFFFF",
            "overlay_width": 900,
            "overlay_height": 180,
            "overlay_visible": True,
            "overlay_locked": False,
            "poll_interval_ms": 180,
            "volume_gain": 1.0,
            "hotkeys": {
                "toggle_overlay": "<ctrl>+<alt>+s",
                "toggle_lock": "<ctrl>+<alt>+l",
                "inc_font": "<ctrl>+<alt>+<up>",
                "dec_font": "<ctrl>+<alt>+<down>",
            },
        }
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.data.update(raw)
        except Exception:
            pass

    def save(self):
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class OutlinedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._text_color = QColor("#FFFFFF")
        self._outline_color = QColor(0, 0, 0, 220)
        self._outline_width = 2

    def setTextColor(self, color: QColor):
        self._text_color = QColor(color)
        self.update()

    def setOutlineColor(self, color: QColor):
        self._outline_color = QColor(color)
        self.update()

    def setOutlineWidth(self, width: int):
        self._outline_width = max(0, int(width))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        flags = int(self.alignment()) | int(Qt.TextWordWrap)
        rect = QRect(0, 0, self.width(), self.height())
        text = self.text()

        if self._outline_width > 0 and text:
            p.setPen(QPen(self._outline_color, 1))
            w = self._outline_width
            offsets = [
                (-w, -w),
                (0, -w),
                (w, -w),
                (-w, 0),
                (w, 0),
                (-w, w),
                (0, w),
                (w, w),
            ]
            for dx, dy in offsets:
                p.drawText(rect.adjusted(dx, dy, dx, dy), flags, text)

        p.setPen(QPen(self._text_color, 1))
        p.drawText(rect, flags, text)


class SubtitleOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.locked = False
        self.drag_pos = None
        self.bg_alpha = 0
        self.font_size = 36
        self.font_color = QColor("#FFFFFF")

        self.setWindowTitle("Subtitle Overlay")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(320, 100)

        shell = QWidget(self)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(20, 14, 20, 14)

        self.label = OutlinedLabel("")
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Microsoft YaHei", 36, QFont.Bold))
        shell_layout.addWidget(self.label)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(shell)

        self.setMinimumSize(320, self.effective_min_height())
        self.set_overlay_size(900, 180)
        self.update_style()

    def effective_min_height(self) -> int:
        return max(100, int(self.minimumSizeHint().height()))

    def set_overlay_size(self, width: int, height: int):
        w = max(320, int(width))
        h = max(self.effective_min_height(), int(height))
        self.resize(w, h)

    def update_style(self):
        self.label.setTextColor(self.font_color)
        self.label.setOutlineColor(QColor(0, 0, 0, 220))
        self.label.setOutlineWidth(2)
        self.label.setStyleSheet("background: transparent;")
        font = self.label.font()
        font.setPointSize(self.font_size)
        self.label.setFont(font)

    def set_text(self, text: str):
        self.label.setText(text or "")

    def set_locked(self, locked: bool):
        self.locked = locked
        self.setAttribute(Qt.WA_TransparentForMouseEvents, locked)

    def mousePressEvent(self, event):
        if self.locked:
            return
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.locked:
            return
        if self.drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None
        event.accept()


class HotkeyBridge(QWidget):
    toggle_overlay = pyqtSignal()
    toggle_lock = pyqtSignal()
    inc_font = pyqtSignal()
    dec_font = pyqtSignal()


class HotkeyManager:
    def __init__(self, bridge: HotkeyBridge, hotkeys_config: dict):
        self.bridge = bridge
        self.hotkeys_config = hotkeys_config
        self.listener = None

    def start(self):
        if keyboard is None:
            return
        hotkeys = {}
        toggle_overlay = self.hotkeys_config.get("toggle_overlay", "<ctrl>+<alt>+s")
        toggle_lock = self.hotkeys_config.get("toggle_lock", "<ctrl>+<alt>+l")
        inc_font = self.hotkeys_config.get("inc_font", "<ctrl>+<alt>+<up>")
        dec_font = self.hotkeys_config.get("dec_font", "<ctrl>+<alt>+<down>")
        if toggle_overlay:
            hotkeys[toggle_overlay] = self.bridge.toggle_overlay.emit
        if toggle_lock:
            hotkeys[toggle_lock] = self.bridge.toggle_lock.emit
        if inc_font:
            hotkeys[inc_font] = self.bridge.inc_font.emit
        if dec_font:
            hotkeys[dec_font] = self.bridge.dec_font.emit
        self.listener = keyboard.GlobalHotKeys(hotkeys)
        self.listener.start()

    def stop(self):
        if self.listener is not None:
            self.listener.stop()


class SubtitlePushBridge(QObject):
    stateReceived = pyqtSignal(dict)

    @pyqtSlot(str)
    def pushState(self, payload: str):
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict):
                self.stateReceived.emit(obj)
        except Exception:
            pass


class QuietWebEnginePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        text = str(message or "")
        noisy = (
            "all ai task loaded",
            "resetLoadedData",
            "freeze scroller",
            "pip canvas init size",
        )
        if any(k in text for k in noisy):
            return
        return


def normalize_url(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return "https://" + text


class BrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = ConfigStore()
        self.last_subtitle = ""
        self.last_subtitle_seen_at = 0.0
        self.was_playing = False
        self.last_auto_enable_ts = 0.0
        self.auto_enable_attempts = 0

        self.overlay = SubtitleOverlay()
        self.overlay.set_overlay_size(
            int(self.config.data["overlay_width"]),
            int(self.config.data["overlay_height"]),
        )
        self.overlay.font_size = int(self.config.data["font_size"])
        self.overlay.bg_alpha = 0
        self.overlay.font_color = QColor(self.config.data["font_color"])
        self.overlay.set_locked(bool(self.config.data["overlay_locked"]))
        self.overlay.update_style()
        self.overlay.setVisible(bool(self.config.data["overlay_visible"]))

        self.setWindowTitle("Kikoeru subtitle --by mz")
        self.resize(1360, 860)

        self.web = QWebEngineView(self)
        self.web.setPage(QuietWebEnginePage(self.web))
        self.web.titleChanged.connect(self.on_title_changed)
        self.web.urlChanged.connect(self.on_url_changed)
        self.web.loadFinished.connect(self.on_page_loaded)
        self.web.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
        self.web.page().setVisible(True)

        self.subtitle_bridge = SubtitlePushBridge()
        self.subtitle_bridge.stateReceived.connect(self.handle_poll_result)
        self.web_channel = QWebChannel(self.web.page())
        self.web_channel.registerObject("subtitleBridge", self.subtitle_bridge)
        self.web.page().setWebChannel(self.web_channel)

        self.bridge_script = QWebEngineScript()
        self.bridge_script.setName("subtitle_event_bridge")
        self.bridge_script.setInjectionPoint(QWebEngineScript.DocumentReady)
        self.bridge_script.setRunsOnSubFrames(False)
        self.bridge_script.setWorldId(QWebEngineScript.MainWorld)
        self.bridge_script.setSourceCode(JS_EVENT_BRIDGE_INIT)
        self.web.page().scripts().insert(self.bridge_script)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(1500)
        self.poll_timer.timeout.connect(self.ensure_event_bridge)
        self.poll_timer.start()

        self.keepalive_timer = QTimer(self)
        self.keepalive_timer.setInterval(1000)
        self.keepalive_timer.timeout.connect(self.ensure_web_active)
        self.keepalive_timer.start()

        self.hotkey_bridge = HotkeyBridge()
        self.hotkey_bridge.toggle_overlay.connect(self.toggle_overlay)
        self.hotkey_bridge.toggle_lock.connect(self.toggle_lock)
        self.hotkey_bridge.inc_font.connect(self.increase_font)
        self.hotkey_bridge.dec_font.connect(self.decrease_font)
        self.hotkeys = HotkeyManager(self.hotkey_bridge, self.config.data.get("hotkeys", {}))
        self.hotkeys.start()

        self._build_ui()
        if not HAVE_FLUENT:
            self.apply_fallback_modern_style()

        self.go_to_url(self.config.data["homepage"])
        self.position_overlay_bottom()
        self.overlay.show()

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        nav_row = QHBoxLayout()
        self.back_btn = FluentButton("<-")
        self.back_btn.clicked.connect(self.web.back)
        self.forward_btn = FluentButton("->")
        self.forward_btn.clicked.connect(self.web.forward)
        self.reload_btn = FluentButton("Reload")
        self.reload_btn.clicked.connect(self.web.reload)

        self.url_input = LineEdit()
        self.url_input.setPlaceholderText("输入网址（支持通用网站字幕检测）")
        self.url_input.returnPressed.connect(
            lambda: self.go_to_url(self.url_input.text())
        )

        self.go_btn = FluentButton("Go")
        self.go_btn.clicked.connect(lambda: self.go_to_url(self.url_input.text()))

        self.settings_btn = FluentButton("字幕设置")
        self.settings_btn.clicked.connect(self.show_subtitle_settings)

        nav_row.addWidget(self.back_btn)
        nav_row.addWidget(self.forward_btn)
        nav_row.addWidget(self.reload_btn)
        nav_row.addWidget(self.url_input, 1)
        nav_row.addWidget(self.go_btn)
        nav_row.addWidget(self.settings_btn)

        # 音量增益滑块
        nav_row.addWidget(QLabel("音量"))
        self.gain_slider = FluentSlider(Qt.Horizontal)
        self.gain_slider.setRange(100, 1000)
        self.gain_slider.setValue(int(self.config.data.get("volume_gain", 1.0) * 100))
        self.gain_slider.setMaximumWidth(100)
        self.gain_slider.valueChanged.connect(self.on_gain_changed)
        nav_row.addWidget(self.gain_slider)
        self.gain_label = QLabel(f"{self.config.data.get('volume_gain', 1.0):.1f}x")
        self.gain_label.setMinimumWidth(35)
        nav_row.addWidget(self.gain_label)

        settings = QWidget()
        form = QFormLayout(settings)
        form.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("等待页面字幕...")
        self.status_label.setWordWrap(True)

        form.addRow(self.status_label)

        layout.addLayout(nav_row)
        layout.addWidget(settings)
        layout.addWidget(self.web, 1)
        self.setCentralWidget(root)

    def show_subtitle_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("字幕设置")
        dlg.setModal(False)
        dlg.resize(460, 450)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(12)

        fsize_row = QHBoxLayout()
        fsize_row.addWidget(QLabel("字体大小"))
        size_slider = FluentSlider(Qt.Horizontal)
        size_slider.setRange(18, 96)
        size_slider.setValue(self.overlay.font_size)
        size_slider.valueChanged.connect(self.on_font_size_changed)
        fsize_row.addWidget(size_slider, 1)
        v.addLayout(fsize_row)

        color_btn = FluentButton("选择字体颜色")
        color_btn.clicked.connect(self.pick_color)
        v.addWidget(color_btn)

        lock_box = FluentCheckBox("锁定穿透")
        lock_box.setChecked(self.overlay.locked)
        lock_box.toggled.connect(self.set_overlay_locked)
        v.addWidget(lock_box)

        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("宽"))
        width_spin = QSpinBox()
        width_spin.setRange(300, 3840)
        width_spin.setValue(self.overlay.width())
        width_spin.valueChanged.connect(self.on_overlay_width_changed)
        width_row.addWidget(width_spin)
        width_row.addWidget(QLabel("高"))
        height_spin = QSpinBox()
        height_spin.setRange(self.overlay.effective_min_height(), 1200)
        height_spin.setValue(self.overlay.height())
        height_spin.valueChanged.connect(self.on_overlay_height_changed)
        width_row.addWidget(height_spin)
        v.addLayout(width_row)

        hotkeys_title = QLabel("快捷键设置 (格式: <ctrl>+<alt>+s)")
        hotkeys_title.setStyleSheet("font-weight: bold; margin-top: 10px;")
        v.addWidget(hotkeys_title)

        self.hotkey_inputs = {}
        hotkey_labels = {
            "toggle_overlay": "显示/隐藏字幕窗",
            "toggle_lock": "锁定/解锁字幕窗",
            "inc_font": "增大字号",
            "dec_font": "减小字号",
        }
        hotkeys_config = self.config.data.get("hotkeys", {})
        for key, label_text in hotkey_labels.items():
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            input_field = LineEdit()
            input_field.setText(hotkeys_config.get(key, ""))
            input_field.setPlaceholderText("例如: <ctrl>+<alt>+s")
            self.hotkey_inputs[key] = input_field
            row.addWidget(input_field, 1)
            v.addLayout(row)

        close_btn = FluentButton("关闭")
        close_btn.clicked.connect(lambda: self._save_and_reload_hotkeys(dlg))
        v.addWidget(close_btn)

        # 日志显示区域
        log_title = QLabel("调试日志")
        log_title.setStyleSheet("font-weight: bold; margin-top: 10px;")
        v.addWidget(log_title)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setPlainText("\n".join(DEBUG_LOGS) or "暂无日志")
        v.addWidget(self.log_text)

        dlg.show()

    def _save_and_reload_hotkeys(self, dlg):
        new_hotkeys = {}
        for key, input_field in self.hotkey_inputs.items():
            new_hotkeys[key] = input_field.text().strip()
        self.config.data["hotkeys"] = new_hotkeys
        self.hotkeys.stop()
        self.hotkeys = HotkeyManager(self.hotkey_bridge, new_hotkeys)
        self.hotkeys.start()
        dlg.close()

    def position_overlay_bottom(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.overlay.width()) // 2
        y = geo.y() + geo.height() - self.overlay.height() - 36
        x = max(geo.x(), min(x, geo.x() + geo.width() - self.overlay.width()))
        y = max(geo.y(), min(y, geo.y() + geo.height() - self.overlay.height()))
        self.overlay.move(x, y)

    def apply_fallback_modern_style(self):
        self.setStyleSheet(
            "QWidget { background: #f6f9ff; color: #1d2b45; }"
            "QLineEdit, QDoubleSpinBox, QSpinBox { background: #ffffff; border: 1px solid #c7d7f2; border-radius: 8px; padding: 6px; }"
            "QPushButton { background: #4f9bff; color: white; border: none; border-radius: 8px; padding: 7px 12px; }"
            "QPushButton:hover { background: #6aaeff; }"
            "QPushButton:pressed { background: #3e86ea; }"
            "QCheckBox { spacing: 6px; }"
        )

    def go_to_url(self, raw: str):
        url = normalize_url(raw)
        self.url_input.setText(url)
        self.web.setUrl(QUrl(url))

    def on_title_changed(self, title: str):
        self.setWindowTitle(f"Kikoeru subtitle --by mz | {title}")

    def on_url_changed(self, qurl):
        self.url_input.setText(qurl.toString())

    def on_page_loaded(self, _ok: bool):
        self.ensure_event_bridge()
        # 延迟应用保存的音量增益设置
        gain = self.config.data.get("volume_gain", 1.0)
        if gain > 1.0:
            QTimer.singleShot(1500, self._apply_saved_gain)

    def ensure_event_bridge(self):
        self.ensure_web_active()
        self.web.page().runJavaScript(JS_EVENT_BRIDGE_INIT)

    def trigger_auto_subtitle_enable(self):
        self.web.page().runJavaScript(JS_AUTO_ENABLE_SUBTITLE)

    def _apply_saved_gain(self):
        gain = self.config.data.get("volume_gain", 1.0)
        log_debug(f"启动应用增益: {gain}")
        js = JS_SET_GAIN.replace("__GAIN_VALUE__", str(gain))
        self.web.page().runJavaScript(js, lambda r: self._log_js_result("启动增益", r))

    def handle_poll_result(self, result):
        if not isinstance(result, dict):
            return

        text = (result.get("subtitle") or "").strip()
        lower_text = text.lower()
        if any(
            bad in lower_text
            for bad in [
                "cloud_upload",
                "选择字幕文件",
                "select subtitle file",
                "load local subtitle",
                "字幕文件",
            ]
        ):
            text = ""
        playing = bool(result.get("isPlaying"))
        current_time = result.get("currentTime")

        if playing and not self.was_playing:
            self.last_subtitle = ""
            self.auto_enable_attempts = 0

        if playing and not text and current_time is not None and current_time > 0:
            now = time.monotonic()
            if self.auto_enable_attempts < 2 and now - self.last_auto_enable_ts > 3.0:
                self.last_auto_enable_ts = now
                self.auto_enable_attempts += 1
                self.trigger_auto_subtitle_enable()

        if text:
            self.last_subtitle = text
            self.last_subtitle_seen_at = time.monotonic()

        if playing and not text and self.last_subtitle:
            if time.monotonic() - self.last_subtitle_seen_at > 0.8:
                self.last_subtitle = ""

        shown = text or self.last_subtitle
        if not playing and not text:
            shown = ""

        self.overlay.set_text(shown)

        if current_time is None:
            self.status_label.setText("已连接页面，等待检测到媒体播放...")
        else:
            self.status_label.setText(f"播放中: {'是' if playing else '否'}")

        self.was_playing = playing

    def ensure_web_active(self):
        page = self.web.page()
        page.setVisible(True)
        if page.lifecycleState() != QWebEnginePage.LifecycleState.Active:
            page.setLifecycleState(QWebEnginePage.LifecycleState.Active)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            self.ensure_web_active()
            if self.isMinimized():
                self.status_label.setText("主窗口最小化，已尝试保持网页播放器活跃")
        super().changeEvent(event)

    def on_font_size_changed(self, value: int):
        self.overlay.font_size = int(value)
        self.overlay.update_style()

    def on_overlay_width_changed(self, value: int):
        self.overlay.set_overlay_size(int(value), self.overlay.height())
        self.overlay.update_style()

    def on_overlay_height_changed(self, value: int):
        self.overlay.set_overlay_size(self.overlay.width(), int(value))
        self.overlay.update_style()

    def set_overlay_locked(self, locked: bool):
        self.overlay.set_locked(bool(locked))

    def on_gain_changed(self, value: int):
        gain = value / 100.0
        self.gain_label.setText(f"{gain:.1f}x")
        self.config.data["volume_gain"] = gain
        log_debug(f"设置音量增益: {gain}")
        js = JS_SET_GAIN.replace("__GAIN_VALUE__", str(gain))
        self.web.page().runJavaScript(js, lambda r: self._log_js_result("增益", r))

    def pick_color(self):
        color = QColorDialog.getColor(self.overlay.font_color, self, "选择字幕颜色")
        if not color.isValid():
            return
        self.overlay.font_color = color
        self.overlay.update_style()

    def toggle_overlay(self):
        visible = not self.overlay.isVisible()
        self.overlay.setVisible(visible)
        log_debug(f"toggle_overlay: visible={visible}")
        if visible:
            log_debug("执行播放脚本...")
            self.web.page().runJavaScript(JS_PLAY_MEDIA, lambda r: self._log_js_result("播放", r))
        else:
            log_debug("执行暂停脚本...")
            self.web.page().runJavaScript(JS_PAUSE_MEDIA, lambda r: self._log_js_result("暂停", r))

    def _log_js_result(self, action, result):
        log_debug(f"{action}结果: {result}")
        if hasattr(self, 'log_text') and self.log_text:
            self.log_text.setPlainText("\n".join(DEBUG_LOGS))

    def toggle_lock(self):
        self.set_overlay_locked(not self.overlay.locked)

    def increase_font(self):
        self.on_font_size_changed(min(96, self.overlay.font_size + 2))

    def decrease_font(self):
        self.on_font_size_changed(max(18, self.overlay.font_size - 2))

    def closeEvent(self, event):
        self.hotkeys.stop()
        self.config.data["homepage"] = self.url_input.text().strip()
        self.config.data["font_size"] = int(self.overlay.font_size)
        self.config.data["bg_alpha"] = int(self.overlay.bg_alpha)
        self.config.data["font_color"] = self.overlay.font_color.name()
        self.config.data["overlay_width"] = self.overlay.width()
        self.config.data["overlay_height"] = self.overlay.height()
        self.config.data["overlay_visible"] = self.overlay.isVisible()
        self.config.data["overlay_locked"] = self.overlay.locked
        self.config.save()
        self.overlay.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Kikoeru subtitle --by mz")
    w = BrowserWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()