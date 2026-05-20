import configparser
import json
import os
import time
from datetime import datetime

import pandas as pd
import requests

try:
    from iqoptionapi.stable_api import IQ_Option
except Exception:
    IQ_Option = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
STATE_FILE = os.path.join(BASE_DIR, "estado.json")
STOP_FILE = os.path.join(BASE_DIR, "stop.flag")


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding="utf-8")
    return config


def get_state():
    if not os.path.exists(STATE_FILE):
        return {
            "running": False,
            "status": "Detenido",
            "operaciones": 0,
            "wins": 0,
            "losses": 0,
            "ganancia": 0.0,
            "ultima_senal": ""
        }
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def set_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def stop_requested():
    return os.path.exists(STOP_FILE)


def request_stop():
    with open(STOP_FILE, "w", encoding="utf-8") as f:
        f.write("stop")


def clear_stop():
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)


def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def adx(df, period=14):
    high = df["max"]
    low = df["min"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).abs()) * 100
    return dx.rolling(period).mean()


class GKTraderBot:
    def __init__(self):
        self.config = load_config()
        self.iq = None

    def connect(self):
        if IQ_Option is None:
            raise RuntimeError("No está instalado iqoptionapi. Ejecutá: pip install iqoptionapi websocket-client --upgrade")

        email = self.config["IQOPTION"].get("email", "").strip()
        password = self.config["IQOPTION"].get("password", "").strip()
        cuenta = self.config["GENERAL"].get("cuenta", "PRACTICE").strip().upper()

        if not email or email == "TU_EMAIL_IQ" or not password or password == "TU_PASSWORD_IQ":
            raise RuntimeError("Falta configurar email y password en config.ini")

        self.iq = IQ_Option(email, password)
        check, reason = self.iq.connect()

        if not check:
            raise RuntimeError(f"No se pudo conectar a IQ Option: {reason}")

        self.iq.change_balance(cuenta)
        return True

    def enviar_telegram(self, mensaje):
        token = self.config["TELEGRAM"].get("token", "").strip()
        chat_id = self.config["TELEGRAM"].get("chat_id", "").strip()

        if not token or token == "TU_TOKEN_TELEGRAM" or not chat_id or chat_id == "TU_CHAT_ID":
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            r = requests.post(url, data={"chat_id": chat_id, "text": mensaje}, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def obtener_velas(self, activo):
        timeframe = int(self.config["ESTRATEGIA"].get("timeframe", 60))
        cantidad = int(self.config["ESTRATEGIA"].get("cantidad_velas", 250))
        candles = self.iq.get_candles(activo, timeframe, cantidad, time.time())
        df = pd.DataFrame(candles)
        return df.sort_values("from").reset_index(drop=True)

    def analizar(self, activo):
        df = self.obtener_velas(activo)
        if len(df) < 100:
            return None

        df["EMA9"] = ema(df["close"], 9)
        df["EMA21"] = ema(df["close"], 21)
        df["EMA50"] = ema(df["close"], 50)
        df["EMA200"] = ema(df["close"], 200)
        df["RSI"] = rsi(df["close"], 14)
        df["ADX"] = adx(df, 14)

        ultima = df.iloc[-2]
        anterior = df.iloc[-3]

        precio = float(ultima["close"])
        vela_alcista = ultima["close"] > ultima["open"]
        vela_bajista = ultima["close"] < ultima["open"]

        adx_minimo = float(self.config["ESTRATEGIA"].get("adx_minimo", 18))
        rsi_call_min = float(self.config["ESTRATEGIA"].get("rsi_call_min", 55))
        rsi_call_max = float(self.config["ESTRATEGIA"].get("rsi_call_max", 70))
        rsi_put_min = float(self.config["ESTRATEGIA"].get("rsi_put_min", 30))
        rsi_put_max = float(self.config["ESTRATEGIA"].get("rsi_put_max", 45))

        call_ok = (
            precio > ultima["EMA200"]
            and ultima["EMA9"] > ultima["EMA21"] > ultima["EMA50"]
            and precio > ultima["EMA9"]
            and precio > anterior["close"]
            and rsi_call_min <= ultima["RSI"] <= rsi_call_max
            and ultima["ADX"] >= adx_minimo
            and vela_alcista
        )

        put_ok = (
            precio < ultima["EMA200"]
            and ultima["EMA9"] < ultima["EMA21"] < ultima["EMA50"]
            and precio < ultima["EMA9"]
            and precio < anterior["close"]
            and rsi_put_min <= ultima["RSI"] <= rsi_put_max
            and ultima["ADX"] >= adx_minimo
            and vela_bajista
        )

        fuerza = min(99, int(ultima["ADX"] + abs(ultima["RSI"] - 50)))

        if call_ok:
            return {
                "activo": activo,
                "direccion": "call",
                "texto": "ARRIBA",
                "precio": precio,
                "rsi": float(ultima["RSI"]),
                "adx": float(ultima["ADX"]),
                "fuerza": fuerza
            }

        if put_ok:
            return {
                "activo": activo,
                "direccion": "put",
                "texto": "ABAJO",
                "precio": precio,
                "rsi": float(ultima["RSI"]),
                "adx": float(ultima["ADX"]),
                "fuerza": fuerza
            }

        return None

    def operar(self, senal):
        auto_operar = self.config["GENERAL"].get("auto_operar", "N").strip().upper()
        if auto_operar != "S":
            return {"status": "signal_only", "profit": 0.0}

        cuenta = self.config["GENERAL"].get("cuenta", "PRACTICE").strip().upper()
        if cuenta != "PRACTICE":
            return {"status": "blocked_real", "profit": 0.0}

        monto = float(self.config["GENERAL"].get("monto", 1.2))
        expiracion = int(self.config["GENERAL"].get("tiempo_orden", 1))

        self.iq.change_balance("PRACTICE")
        status, trade_id = self.iq.buy(monto, senal["activo"], senal["direccion"], expiracion)

        if not status:
            return {"status": "rejected", "profit": 0.0}

        resultado = None
        while resultado is None and not stop_requested():
            resultado = self.iq.check_win_v4(trade_id)
            time.sleep(1)

        return {"status": "closed", "profit": float(resultado or 0.0), "trade_id": trade_id}

    def run_forever(self):
        clear_stop()
        state = get_state()
        state.update({"running": True, "status": "Conectando..."})
        set_state(state)

        try:
            self.connect()
        except Exception as e:
            state = get_state()
            state.update({"running": False, "status": str(e)})
            set_state(state)
            return

        activos = [x.strip() for x in self.config["ACTIVOS"].get("pares", "").split(",") if x.strip()]
        cooldown = int(self.config["GENERAL"].get("cooldown_segundos", 120))
        ultimo_envio = 0

        state = get_state()
        state.update({"running": True, "status": "Bot iniciado"})
        set_state(state)
        self.enviar_telegram("🚀 GKTraderBot iniciado en modo DEMO/PRACTICE")

        while not stop_requested():
            for activo in activos:
                if stop_requested():
                    break

                state = get_state()
                state["status"] = f"Analizando {activo}..."
                set_state(state)

                try:
                    senal = self.analizar(activo)
                except Exception as e:
                    state = get_state()
                    state["status"] = f"Error analizando {activo}: {e}"
                    set_state(state)
                    time.sleep(2)
                    continue

                if senal and time.time() - ultimo_envio >= cooldown:
                    hora = datetime.now().strftime("%H:%M:%S")
                    mensaje = (
                        f"📊 GKTraderBot Señal OTC\n"
                        f"Activo: {senal['activo']}\n"
                        f"Dirección: {senal['texto']}\n"
                        f"Hora: {hora}\n"
                        f"RSI: {senal['rsi']:.2f}\n"
                        f"ADX: {senal['adx']:.2f}\n"
                        f"Fuerza estimada: {senal['fuerza']}%\n"
                        f"Modo: señal filtrada"
                    )
                    self.enviar_telegram(mensaje)
                    resultado = self.operar(senal)

                    state = get_state()
                    state["operaciones"] = int(state.get("operaciones", 0)) + 1
                    profit = float(resultado.get("profit", 0.0))
                    state["ganancia"] = round(float(state.get("ganancia", 0.0)) + profit, 2)
                    if resultado["status"] == "closed":
                        if profit > 0:
                            state["wins"] = int(state.get("wins", 0)) + 1
                        elif profit < 0:
                            state["losses"] = int(state.get("losses", 0)) + 1
                    state["ultima_senal"] = mensaje
                    state["status"] = f"Última señal: {senal['activo']} {senal['texto']}"
                    set_state(state)
                    ultimo_envio = time.time()

                time.sleep(1)

            time.sleep(3)

        state = get_state()
        state.update({"running": False, "status": "Detenido"})
        set_state(state)
        self.enviar_telegram("🛑 GKTraderBot detenido")
