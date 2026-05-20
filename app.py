from flask import Flask, render_template, request, redirect
import threading
import traceback

from bot_engine import (
    GKTraderBot,
    get_state,
    set_state,
    request_stop,
    clear_stop
)

app = Flask(__name__)

bot_thread = None


@app.route("/")
def index():
    state = get_state()
    return render_template("index.html", state=state)


@app.route("/save", methods=["POST"])
def save():

    import configparser

    config = configparser.ConfigParser()

    config["IQOPTION"] = {
        "email": request.form.get("email", ""),
        "password": request.form.get("password", "")
    }

    config["GENERAL"] = {
        "cuenta": request.form.get("cuenta", "PRACTICE"),
        "auto_operar": "S",
        "monto": "1.20",
        "tiempo_orden": "1",
        "cooldown_segundos": "120"
    }

    config["ESTRATEGIA"] = {
        "timeframe": "60",
        "cantidad_velas": "250",
        "adx_minimo": "18",
        "rsi_call_min": "55",
        "rsi_call_max": "70",
        "rsi_put_min": "30",
        "rsi_put_max": "45"
    }

    config["TELEGRAM"] = {
        "token": request.form.get("token", ""),
        "chat_id": request.form.get("chat_id", "")
    }

    config["ACTIVOS"] = {
        "pares": "EURUSD-OTC,GBPUSD-OTC,USDCHF-OTC"
    }

    with open("config.ini", "w", encoding="utf-8") as f:
        config.write(f)

    print("CONFIG GUARDADA", flush=True)

    return redirect("/")


@app.route("/start")
def start():

    global bot_thread

    try:

        clear_stop()

        state = get_state()

        if state.get("running"):
            return redirect("/")

        print("ARRANCANDO HILO DEL BOT...", flush=True)

        bot = GKTraderBot()

        bot_thread = threading.Thread(
            target=bot.run_forever,
            daemon=True
        )

        bot_thread.start()

        print("BOT THREAD LANZADO", flush=True)

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
    app.run(host="0.0.0.0", port=10000)
