import os
import threading
import traceback
import configparser

from flask import Flask, render_template, request, redirect, jsonify

from bot_engine import (
    GKTraderBot,
    get_state,
    set_state,
    request_stop,
    clear_stop
)

app = Flask(__name__)
bot_thread = None
CONFIG_FILE = "config.ini"


def read_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE, encoding="utf-8")

    if "IQOPTION" not in cfg:
        cfg["IQOPTION"] = {}

    if "GENERAL" not in cfg:
        cfg["GENERAL"] = {}

    if "ESTRATEGIA" not in cfg:
        cfg["ESTRATEGIA"] = {}

    if "ACTIVOS" not in cfg:
        cfg["ACTIVOS"] = {}

    if "TELEGRAM" not in cfg:
        cfg["TELEGRAM"] = {}

    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)


@app.route("/")
def index():
    cfg = read_config()
    state = get_state()

    return render_template(
        "index.html",
        state=state,
        email=cfg["IQOPTION"].get("email", ""),
        password=cfg["IQOPTION"].get("password", ""),
        cuenta=cfg["GENERAL"].get("cuenta", "PRACTICE"),
        monto=cfg["GENERAL"].get("monto", "1.20"),
        tiempo_orden=cfg["GENERAL"].get("tiempo_orden", "1")
    )


@app.route("/state")
def state():
    return jsonify(get_state())


@app.route("/save", methods=["POST"])
def save():
    cfg = read_config()

    cfg["IQOPTION"]["email"] = request.form.get("email", "")
    cfg["IQOPTION"]["password"] = request.form.get("password", "")

    cfg["GENERAL"]["cuenta"] = request.form.get("cuenta", "PRACTICE")
    cfg["GENERAL"]["auto_operar"] = "S"
    cfg["GENERAL"]["monto"] = request.form.get("monto", "1.20")
    cfg["GENERAL"]["tiempo_orden"] = request.form.get("tiempo_orden", "1")
    cfg["GENERAL"]["cooldown_segundos"] = "120"

    cfg["ESTRATEGIA"]["timeframe"] = "60"
    cfg["ESTRATEGIA"]["cantidad_velas"] = "250"
    cfg["ESTRATEGIA"]["adx_minimo"] = "18"
    cfg["ESTRATEGIA"]["rsi_call_min"] = "55"
    cfg["ESTRATEGIA"]["rsi_call_max"] = "70"
    cfg["ESTRATEGIA"]["rsi_put_min"] = "30"
    cfg["ESTRATEGIA"]["rsi_put_max"] = "45"

    cfg["ACTIVOS"]["pares"] = "EURUSD-OTC,GBPUSD-OTC,USDCHF-OTC"

    save_config(cfg)

    print("CONFIG GUARDADA", flush=True)

    return redirect("/")


@app.route("/start")
def start():
    global bot_thread

    try:
        clear_stop()

        if bot_thread and bot_thread.is_alive():
            print("BOT YA ESTABA ACTIVO", flush=True)
            return redirect("/")

        print("ARRANCANDO HILO DEL BOT...", flush=True)

        bot = GKTraderBot()

        bot_thread = threading.Thread(
            target=bot.run_forever,
            daemon=True
        )

        bot_thread.start()

        print("BOT THREAD LANZADO", flush=True)

        state = get_state()
        state.update({
            "running": True,
            "estado": "ACTIVO",
            "status": "Bot iniciado"
        })
        set_state(state)

    except Exception as e:
        print("ERROR START:", e, flush=True)
        traceback.print_exc()

        state = get_state()
        state.update({
            "running": False,
            "estado": "ERROR",
            "status": str(e)
        })
        set_state(state)

    return redirect("/")


@app.route("/stop")
def stop():
    request_stop()

    state = get_state()
    state.update({
        "running": False,
        "estado": "DETENIDO",
        "status": "Bot detenido"
    })
    set_state(state)

    print("BOT DETENIDO", flush=True)

    return redirect("/")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        debug=False
    )
