# -*- coding: utf-8 -*-
"""
Trading Helper — анализатор торговых сигналов для Android.
Чистый Python + Kivy, без numpy/pandas/matplotlib.
8 источников сигналов, мартингейл, график на Kivy Canvas.
"""

import json
import math
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, timedelta

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.canvas import Color, Line, Rectangle
from kivy.graphics import Color as GColor, Line as GLine, Rectangle as GRect
from kivy.core.window import Window
from kivy.clock import Clock

Window.clearcolor = (0.08, 0.09, 0.12, 1)

# ============================================================
#  ТЕХНИЧЕСКИЕ ИНДИКАТОРЫ (чистый Python)
# ============================================================

def sma(values, period):
    """Simple Moving Average."""
    if len(values) < period:
        return [None] * len(values)
    result = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            window = values[i - period + 1: i + 1]
            result.append(sum(window) / period)
    return result

def ema(values, period):
    """Exponential Moving Average."""
    if not values:
        return []
    k = 2 / (period + 1)
    result = [values[0]]
    for i in range(1, len(values)):
        result.append(values[i] * k + result[-1] * (1 - k))
    return result

def rsi(closes, period=14):
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return [50.0] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result = [None] * period
    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100 - 100 / (1 + rs))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - 100 / (1 + rs))
    return result

def macd(closes, fast=12, slow=26, signal=9):
    """MACD: линия, сигнальная, гистограмма."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram

def bollinger_bands(closes, period=20, num_std=2):
    """Bollinger Bands: верхняя, средняя, нижняя."""
    sma_vals = sma(closes, period)
    upper, lower = [], []
    for i in range(len(closes)):
        if i < period - 1 or sma_vals[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            window = closes[i - period + 1: i + 1]
            mean = sma_vals[i]
            variance = sum((x - mean) ** 2 for x in window) / period
            std = math.sqrt(variance)
            upper.append(mean + num_std * std)
            lower.append(mean - num_std * std)
    return upper, sma_vals, lower

def stochastic(highs, lows, closes, period=14):
    """Stochastic Oscillator %K и %D."""
    k_values = []
    for i in range(len(closes)):
        if i < period - 1:
            k_values.append(50.0)
        else:
            hh = max(highs[i - period + 1: i + 1])
            ll = min(lows[i - period + 1: i + 1])
            if hh == ll:
                k_values.append(50.0)
            else:
                k_values.append((closes[i] - ll) / (hh - ll) * 100)
    d_values = sma(k_values, 3)
    return k_values, d_values

def williams_r(highs, lows, closes, period=14):
    """Williams %R."""
    result = []
    for i in range(len(closes)):
        if i < period - 1:
            result.append(-50.0)
        else:
            hh = max(highs[i - period + 1: i + 1])
            ll = min(lows[i - period + 1: i + 1])
            if hh == ll:
                result.append(-50.0)
            else:
                result.append((hh - closes[i]) / (hh - ll) * -100)
    return result

def atr(highs, lows, closes, period=14):
    """Average True Range."""
    tr_values = []
    for i in range(len(closes)):
        if i == 0:
            tr_values.append(highs[i] - lows[i])
        else:
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
            tr_values.append(tr)
    return sma(tr_values, period)

def adx(highs, lows, closes, period=14):
    """Average Directional Index (упрощённый)."""
    if len(closes) < period * 2:
        return [20.0] * len(closes)
    plus_dm, minus_dm = [], []
    for i in range(1, len(closes)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0)
        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0)

    atr_vals = atr(highs, lows, closes, period)
    result = []
    for i in range(len(closes)):
        if i < period or atr_vals[i] is None or atr_vals[i] == 0:
            result.append(20.0)
        else:
            plus_di = 100 * (sum(plus_dm[max(0, i - period):i]) / period) / atr_vals[i]
            minus_di = 100 * (sum(minus_dm[max(0, i - period):i]) / period) / atr_vals[i]
            if plus_di + minus_di == 0:
                result.append(20.0)
            else:
                dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
                result.append(dx)
    return sma(result, period)

# ============================================================
#  ПОЛУЧЕНИЕ ДАННЫХ (через HTTP, без ccxt/yfinance)
# ============================================================

def fetch_binance_klines(symbol, interval, limit=200):
    """Получить свечи с Binance API."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data  # [[openTime, open, high, low, close, volume, ...], ...]

def fetch_yahoo_klines(symbol, interval, limit=200):
    """Получить свечи с Yahoo Finance."""
    period2 = int(time.time())
    period1 = period2 - limit * 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval={interval}&period1={period1}&period2={period2}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    result = data.get("chart", {}).get("result", [{}])[0]
    timestamps = result.get("timestamp", [])
    quotes = result.get("indicators", {}).get("quote", [{}])[0]
    candles = []
    for i in range(len(timestamps)):
        o = quotes.get("open", [None] * len(timestamps))[i]
        h = quotes.get("high", [None] * len(timestamps))[i]
        l = quotes.get("low", [None] * len(timestamps))[i]
        c = quotes.get("close", [None] * len(timestamps))[i]
        v = quotes.get("volume", [None] * len(timestamps))[i]
        if o and h and l and c:
            candles.append([timestamps[i] * 1000, str(o), str(h), str(l), str(c), str(v or 0)])
    return candles

PAIRS = {
    "BTC/USDT": ("binance", "BTCUSDT"),
    "ETH/USDT": ("binance", "ETHUSDT"),
    "BNB/USDT": ("binance", "BNBUSDT"),
    "XRP/USDT": ("binance", "XRPUSDT"),
    "SOL/USDT": ("binance", "SOLUSDT"),
    "ADA/USDT": ("binance", "ADAUSDT"),
    "DOGE/USDT": ("binance", "DOGEUSDT"),
    "AVAX/USDT": ("binance", "AVAXUSDT"),
    "EUR/USD": ("yahoo", "EURUSD=X"),
    "GBP/USD": ("yahoo", "GBPUSD=X"),
    "USD/JPY": ("yahoo", "USDJPY=X"),
    "AUD/USD": ("yahoo", "AUDUSD=X"),
    "USD/CAD": ("yahoo", "USDCAD=X"),
    "USD/CHF": ("yahoo", "USDCHF=X"),
}

TIMEFRAMES = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

def get_candles(pair_key, tf_key, limit=200):
    source, ticker = PAIRS[pair_key]
    tf = TIMEFRAMES[tf_key]
    if source == "binance":
        raw = fetch_binance_klines(ticker, tf, limit)
    else:
        raw = fetch_yahoo_klines(ticker, tf, limit)
    if not raw:
        raise ValueError("Нет данных")
    opens = [float(c[1]) for c in raw]
    highs = [float(c[2]) for c in raw]
    lows = [float(c[3]) for c in raw]
    closes = [float(c[4]) for c in raw]
    volumes = [float(c[5]) for c in raw]
    return opens, highs, lows, closes, volumes

# ============================================================
#  8 ИСТОЧНИКОВ СИГНАЛОВ
# ============================================================

def analyze_signals(closes, highs, lows, volumes):
    """Возвращает список сигналов: (источник, направление, детали)."""
    signals = []

    # 1. RSI
    rsi_vals = rsi(closes, 14)
    last_rsi = rsi_vals[-1] if rsi_vals and rsi_vals[-1] is not None else 50
    if last_rsi < 30:
        signals.append(("RSI (14)", "BUY", f"RSI = {last_rsi:.1f} (< 30, перепроданность)"))
    elif last_rsi > 70:
        signals.append(("RSI (14)", "SELL", f"RSI = {last_rsi:.1f} (> 70, перекупленность)"))
    else:
        signals.append(("RSI (14)", "NEUTRAL", f"RSI = {last_rsi:.1f}"))

    # 2. MACD
    macd_line, signal_line, hist = macd(closes)
    if len(macd_line) >= 2 and len(signal_line) >= 2:
        if macd_line[-1] > signal_line[-1] and macd_line[-2] <= signal_line[-2]:
            signals.append(("MACD", "BUY", "MACD пересёк сигнальную снизу вверх"))
        elif macd_line[-1] < signal_line[-1] and macd_line[-2] >= signal_line[-2]:
            signals.append(("MACD", "SELL", "MACD пересёк сигнальную сверху вниз"))
        else:
            signals.append(("MACD", "NEUTRAL", f"MACD = {macd_line[-1]:.4f}, Signal = {signal_line[-1]:.4f}"))

    # 3. Bollinger Bands
    bb_upper, bb_mid, bb_lower = bollinger_bands(closes, 20, 2)
    if bb_upper[-1] is not None:
        if closes[-1] <= bb_lower[-1]:
            signals.append(("Bollinger Bands", "BUY", f"Цена у нижней полосы ({bb_lower[-1]:.4f})"))
        elif closes[-1] >= bb_upper[-1]:
            signals.append(("Bollinger Bands", "SELL", f"Цена у верхней полосы ({bb_upper[-1]:.4f})"))
        else:
            signals.append(("Bollinger Bands", "NEUTRAL", f"Цена в канале: {bb_lower[-1]:.4f} – {bb_upper[-1]:.4f}"))

    # 4. Stochastic
    k_vals, d_vals = stochastic(highs, lows, closes, 14)
    last_k = k_vals[-1] if k_vals else 50
    last_d = d_vals[-1] if d_vals and d_vals[-1] is not None else 50
    if last_k < 20:
        signals.append(("Stochastic", "BUY", f"%K = {last_k:.1f} (< 20, перепроданность)"))
    elif last_k > 80:
        signals.append(("Stochastic", "SELL", f"%K = {last_k:.1f} (> 80, перекупленность)"))
    else:
        signals.append(("Stochastic", "NEUTRAL", f"%K = {last_k:.1f}, %D = {last_d:.1f}"))

    # 5. EMA Crossover (9 vs 21)
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    if len(ema9) >= 2 and len(ema21) >= 2:
        if ema9[-1] > ema21[-1] and ema9[-2] <= ema21[-2]:
            signals.append(("EMA 9/21", "BUY", "EMA9 пересекла EMA21 снизу вверх"))
        elif ema9[-1] < ema21[-1] and ema9[-2] >= ema21[-2]:
            signals.append(("EMA 9/21", "SELL", "EMA9 пересекла EMA21 сверху вниз"))
        else:
            diff = ema9[-1] - ema21[-1]
            direction = "выше" if diff > 0 else "ниже"
            signals.append(("EMA 9/21", "NEUTRAL", f"EMA9 {direction} EMA21 (diff={diff:.4f})"))

    # 6. Williams %R
    wr_vals = williams_r(highs, lows, closes, 14)
    last_wr = wr_vals[-1] if wr_vals else -50
    if last_wr <= -80:
        signals.append(("Williams %R", "BUY", f"%R = {last_wr:.1f} (перепроданность)"))
    elif last_wr >= -20:
        signals.append(("Williams %R", "SELL", f"%R = {last_wr:.1f} (перекупленность)"))
    else:
        signals.append(("Williams %R", "NEUTRAL", f"%R = {last_wr:.1f}"))

    # 7. ADX (тренд)
    adx_vals = adx(highs, lows, closes, 14)
    last_adx = adx_vals[-1] if adx_vals and adx_vals[-1] is not None else 20
    ema9_2 = ema(closes, 9)
    ema21_2 = ema(closes, 21)
    if last_adx > 25:
        if ema9_2[-1] > ema21_2[-1]:
            signals.append(("ADX", "BUY", f"ADX = {last_adx:.1f} (сильный восходящий тренд)"))
        else:
            signals.append(("ADX", "SELL", f"ADX = {last_adx:.1f} (сильный нисходящий тренд)"))
    else:
        signals.append(("ADX", "NEUTRAL", f"ADX = {last_adx:.1f} (слабый тренд, < 25)"))

    # 8. Volume Analysis
    if len(volumes) >= 20:
        avg_vol = sum(volumes[-20:]) / 20
        last_vol = volumes[-1]
        price_up = closes[-1] > closes[-2] if len(closes) >= 2 else True
        if last_vol > avg_vol * 1.5 and price_up:
            signals.append(("Volume", "BUY", f"Объём {last_vol/avg_vol:.1f}x выше среднего, цена растёт"))
        elif last_vol > avg_vol * 1.5 and not price_up:
            signals.append(("Volume", "SELL", f"Объём {last_vol/avg_vol:.1f}x выше среднего, цена падает"))
        else:
            signals.append(("Volume", "NEUTRAL", f"Объём {last_vol/avg_vol:.1f}x от среднего"))

    return signals

# ============================================================
#  МАРТИНГЕЙЛ
# ============================================================

def martingale_calc(base_amount, loss_count, multiplier=2.0, max_steps=5):
    """Расчёт ставок мартингейла."""
    steps = []
    current = base_amount
    for i in range(max_steps):
        steps.append(current)
        current = current * multiplier
    total_risk = sum(steps[:loss_count + 1])
    return steps, total_risk

# ============================================================
#  KIVY UI
# ============================================================

class SignalRow(GridLayout):
    """Строка таблицы сигналов."""
    def __init__(self, source, direction, details, **kwargs):
        super().__init__(**kwargs)
        self.cols = 3
        self.size_hint_y = None
        self.height = 50

        dir_colors = {
            "BUY": (0.15, 0.6, 0.2, 1),
            "SELL": (0.6, 0.15, 0.15, 1),
            "NEUTRAL": (0.3, 0.3, 0.35, 1),
        }
        dir_texts = {"BUY": "BUY", "SELL": "SELL", "NEUTRAL": "NEUTRAL"}
        bg = dir_colors.get(direction, (0.3, 0.3, 0.35, 1))

        lbl_src = Label(text=source, color=(1, 1, 1, 1), font_size=14,
                        size_hint_x=0.3, halign="left", valign="middle")
        lbl_src.bind(size=lbl_src.setter("text_size"))
        lbl_dir = Label(text=dir_texts.get(direction, direction), color=(1, 1, 1, 1),
                        font_size=14, bold=True, size_hint_x=0.2)
        lbl_dir.canvas.before.clear()
        with lbl_dir.canvas.before:
            GColor(*bg)
            GRect(pos=lbl_dir.pos, size=lbl_dir.size)
        lbl_dir.bind(pos=lambda inst, val: setattr(lbl_dir.canvas.before.children[-1] if lbl_dir.canvas.before.children else None, "pos", val))
        lbl_det = Label(text=details, color=(0.85, 0.85, 0.85, 1), font_size=12,
                        size_hint_x=0.5, halign="left", valign="middle")
        lbl_det.bind(size=lbl_det.setter("text_size"))

        self.add_widget(lbl_src)
        self.add_widget(lbl_dir)
        self.add_widget(lbl_det)

class ChartWidget(BoxLayout):
    """Простой график свечей через Kivy Canvas."""
    def __init__(self, closes, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint_y = None
        self.closes = closes
        self.height = 300
        self.bind(size=self.draw_chart)
        Clock.schedule_once(self.draw_chart, 0.1)

    def draw_chart(self, *args):
        self.canvas.clear()
        if not self.closes or self.width < 10 or self.height < 10:
            return

        n = len(self.closes)
        if n < 2:
            return

        padding = 20
        w = self.width - 2 * padding
        h = self.height - 2 * padding
        min_p = min(self.closes)
        max_p = max(self.closes)
        if max_p == min_p:
            return

        with self.canvas:
            # Фон
            GColor(0.1, 0.11, 0.14, 1)
            GRect(pos=self.pos, size=self.size)

            # Сетка
            GColor(0.2, 0.2, 0.25, 0.5)
            for i in range(5):
                y = self.y + padding + h * i / 4
                GLine(points=[self.x + padding, y, self.x + self.width - padding, y], width=0.5)

            # Линия цены
            points = []
            for i, c in enumerate(self.closes):
                x = self.x + padding + w * i / (n - 1)
                y = self.y + padding + h * (c - min_p) / (max_p - min_p)
                points.extend([x, y])

            GColor(0.3, 0.7, 0.9, 1)
            GLine(points=points, width=1.2)

            # Последняя цена
            last_x = self.x + padding + w
            last_y = self.y + padding + h * (self.closes[-1] - min_p) / (max_p - min_p)
            GColor(1, 0.85, 0.1, 1)
            GLine(circle=(last_x, last_y, 4), width=1.5)

class TradingApp(App):
    def build(self):
        self.title = "Trading Helper"
        self.root = BoxLayout(orientation="vertical", padding=10, spacing=5)

        # Заголовок
        title = Label(text="Trading Helper — 8 сигналов", font_size=20,
                      color=(0.3, 0.7, 0.9, 1), size_hint_y=0.06, bold=True)
        self.root.add_widget(title)

        # Выбор пары
        pair_row = BoxLayout(size_hint_y=0.06, spacing=5)
        pair_row.add_widget(Label(text="Пара:", size_hint_x=0.2, color=(0.7, 0.7, 0.7, 1), font_size=14))
        self.pair_spinner = Spinner(
            text="BTC/USDT",
            values=list(PAIRS.keys()),
            size_hint_x=0.4,
            background_color=(0.2, 0.3, 0.5, 1),
        )
        pair_row.add_widget(self.pair_spinner)
        pair_row.add_widget(Label(text="ТФ:", size_hint_x=0.1, color=(0.7, 0.7, 0.7, 1), font_size=14))
        self.tf_spinner = Spinner(
            text="15m",
            values=list(TIMEFRAMES.keys()),
            size_hint_x=0.15,
            background_color=(0.2, 0.3, 0.5, 1),
        )
        pair_row.add_widget(self.tf_spinner)
        self.root.add_widget(pair_row)

        # Кнопка анализа
        self.analyze_btn = Button(
            text="Запустить анализ",
            size_hint_y=0.07,
            background_color=(0.15, 0.6, 0.2, 1),
            font_size=16,
            bold=True,
        )
        self.analyze_btn.bind(on_press=self.start_analysis)
        self.root.add_widget(self.analyze_btn)

        # Статус
        self.status_label = Label(
            text="Готов к анализу",
            size_hint_y=0.04,
            color=(0.6, 0.6, 0.6, 1),
            font_size=12,
        )
        self.root.add_widget(self.status_label)

        # Скролл для сигналов
        self.scroll = ScrollView(size_hint_y=0.5)
        self.signals_container = BoxLayout(orientation="vertical", size_hint_y=None, spacing=2)
        self.signals_container.bind(minimum_height=self.signals_container.setter("height"))
        self.scroll.add_widget(self.signals_container)
        self.root.add_widget(self.scroll)

        # Мартингейл
        mart_section = BoxLayout(orientation="vertical", size_hint_y=0.22, spacing=3)

        mart_header = BoxLayout(size_hint_y=0.2, spacing=5)
        mart_header.add_widget(Label(text="Мартингейл", font_size=14, color=(0.9, 0.7, 0.2, 1), bold=True, size_hint_x=0.5))
        self.mart_base = Button(text="Ставка: 100", size_hint_x=0.3, background_color=(0.2, 0.3, 0.5, 1), font_size=12)
        self.mart_base.bind(on_press=self.cycle_mart_base)
        mart_header.add_widget(self.mart_base)
        self.mart_loss = Button(text="Убытков: 0", size_hint_x=0.2, background_color=(0.2, 0.3, 0.5, 1), font_size=12)
        self.mart_loss.bind(on_press=self.cycle_mart_loss)
        mart_header.add_widget(self.mart_loss)
        mart_section.add_widget(mart_header)

        self.mart_label = Label(
            text="Следующая ставка: 100\nОбщий риск: 100",
            font_size=13, color=(1, 1, 1, 1), halign="left", valign="top",
            size_hint_y=0.8,
        )
        self.mart_label.bind(size=self.mart_label.setter("text_size"))
        mart_section.add_widget(self.mart_label)

        self.root.add_widget(mart_section)

        # Состояние
        self.mart_base_val = 100
        self.mart_loss_val = 0
        self.analyzing = False
        self.closes_data = []

    def cycle_mart_base(self, *args):
        values = [10, 25, 50, 100, 200, 500, 1000]
        idx = values.index(self.mart_base_val) if self.mart_base_val in values else 3
        self.mart_base_val = values[(idx + 1) % len(values)]
        self.mart_base.text = f"Ставка: {self.mart_base_val}"
        self.update_martingale()

    def cycle_mart_loss(self, *args):
        self.mart_loss_val = (self.mart_loss_val + 1) % 6
        self.mart_loss.text = f"Убытков: {self.mart_loss_val}"
        self.update_martingale()

    def update_martingale(self):
        steps, total = martingale_calc(self.mart_base_val, self.mart_loss_val)
        next_bet = steps[min(self.mart_loss_val, len(steps) - 1)]
        self.mart_label.text = (
            f"Следующая ставка: {next_bet:.0f}\n"
            f"Общий риск: {total:.0f}\n"
            f"Стратегия: x2 на каждом убытке\n"
            f"Шаг {self.mart_loss_val + 1} из 5"
        )

    def start_analysis(self, *args):
        if self.analyzing:
            return
        self.analyzing = True
        self.analyze_btn.disabled = True
        self.analyze_btn.text = "Анализирую..."
        self.status_label.text = "Получение данных..."
        self.signals_container.clear_widgets()
        self.signals_container.add_widget(Label(
            text="Загрузка...", color=(0.6, 0.6, 0.6, 1), font_size=14, size_hint_y=None, height=40
        ))

        threading.Thread(target=self.do_analysis, daemon=True).start()

    def do_analysis(self):
        try:
            pair = self.pair_spinner.text
            tf = self.tf_spinner.text
            opens, highs, lows, closes, volumes = get_candles(pair, tf, 200)
            self.closes_data = closes
            signals = analyze_signals(closes, highs, lows, volumes)

            buy_count = sum(1 for s in signals if s[1] == "BUY")
            sell_count = sum(1 for s in signals if s[1] == "SELL")
            neutral_count = sum(1 for s in signals if s[1] == "NEUTRAL")

            if buy_count > sell_count and buy_count >= 4:
                verdict = "СИЛЬНЫЙ BUY"
                verdict_color = (0.15, 0.7, 0.2, 1)
            elif buy_count > sell_count:
                verdict = "BUY (умеренный)"
                verdict_color = (0.3, 0.6, 0.3, 1)
            elif sell_count > buy_count and sell_count >= 4:
                verdict = "СИЛЬНЫЙ SELL"
                verdict_color = (0.7, 0.15, 0.15, 1)
            elif sell_count > buy_count:
                verdict = "SELL (умеренный)"
                verdict_color = (0.6, 0.3, 0.3, 1)
            else:
                verdict = "НЕЙТРАЛЬНО"
                verdict_color = (0.4, 0.4, 0.4, 1)

            Clock.schedule_once(lambda dt: self.display_results(signals, verdict, verdict_color, closes, buy_count, sell_count, neutral_count), 0)

        except Exception as e:
            Clock.schedule_once(lambda dt: self.show_error(str(e)), 0)

    def display_results(self, signals, verdict, vcolor, closes, buy_c, sell_c, neut_c):
        self.signals_container.clear_widgets()

        # Вердикт
        verdict_box = BoxLayout(size_hint_y=None, height=60, spacing=5)
        verdict_lbl = Label(
            text=f"{verdict}\nBUY: {buy_c}  SELL: {sell_c}  NEUTRAL: {neut_c}",
            font_size=16, bold=True, color=(1, 1, 1, 1),
        )
        with verdict_lbl.canvas.before:
            GColor(*vcolor)
            GRect(pos=verdict_lbl.pos, size=verdict_lbl.size)
        verdict_lbl.bind(pos=lambda inst, val: setattr(verdict_lbl.canvas.before.children[-1] if verdict_lbl.canvas.before.children else None, "pos", val),
                         size=lambda inst, val: setattr(verdict_lbl.canvas.before.children[-1] if verdict_lbl.canvas.before.children else None, "size", val))
        verdict_box.add_widget(verdict_lbl)
        self.signals_container.add_widget(verdict_box)

        # Заголовок таблицы
        header = GridLayout(cols=3, size_hint_y=None, height=30)
        header.add_widget(Label(text="Источник", font_size=12, color=(0.5, 0.5, 0.5, 1), bold=True))
        header.add_widget(Label(text="Сигнал", font_size=12, color=(0.5, 0.5, 0.5, 1), bold=True))
        header.add_widget(Label(text="Детали", font_size=12, color=(0.5, 0.5, 0.5, 1), bold=True))
        self.signals_container.add_widget(header)

        # Сигналы
        for src, direction, details in signals:
            row = SignalRow(src, direction, details)
            self.signals_container.add_widget(row)

        # График
        chart_label = Label(text="График цены", font_size=13, color=(0.5, 0.5, 0.5, 1),
                           size_hint_y=None, height=25)
        self.signals_container.add_widget(chart_label)
        chart = ChartWidget(closes)
        self.signals_container.add_widget(chart)

        self.status_label.text = f"Анализ завершён: {self.pair_spinner.text} {self.tf_spinner.text}"
        self.analyze_btn.disabled = False
        self.analyze_btn.text = "Запустить анализ"
        self.analyzing = False
        self.update_martingale()

    def show_error(self, error_msg):
        self.signals_container.clear_widgets()
        self.signals_container.add_widget(Label(
            text=f"Ошибка: {error_msg}\n\nПроверьте интернет-соединение или попробуйте другую пару.",
            color=(0.8, 0.3, 0.3, 1), font_size=14, size_hint_y=None, height=100
        ))
        self.status_label.text = "Ошибка анализа"
        self.analyze_btn.disabled = False
        self.analyze_btn.text = "Запустить анализ"
        self.analyzing = False

if __name__ == "__main__":
    TradingApp().run()
