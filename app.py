import os
import threading
import configparser

from flask import Flask, redirect, render_template_string, request, jsonify
from bot_engine import GKTraderBot, get_state, request_stop, clear_stop, CONFIG_FILE

app = Flask(__name__)
bot_thread = None

PARES_OTC_FIJOS = "EURUSD-OTC,GBPUSD-OTC,USDCHF-OTC"

HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>GKTraderBot</title>

<style>

body{
    background:#0f172a;
    color:white;
    font-family:Arial;
    margin:0;
    padding:0;
}

.container{
    width:95%;
    max-width:1200px;
    margin:auto;
    padding:20px;
}

.title{
    font-size:42px;
    font-weight:bold;
    margin-bottom:5px;
}

.subtitle{
    color:#94a3b8;
    margin-bottom:30px;
}

.grid{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
    gap:20px;
}

.card{
    background:#1e293b;
    border-radius:18px;
    padding:20px;
    box-shadow:0 0 20px rgba(0,0,0,0.3);
}

.card h2{
    margin-top:0;
    font-size:18px;
    color:#38bdf8;
}

.stat{
    font-size:34px;
    font-weight:bold;
}

form{
    margin-top:20px;
}

input,select{
    width:100%;
    padding:12px;
    border:none;
    border-radius:10px;
    margin-top:8px;
    margin-bottom:18px;
    background:#334155;
    color:white;
    font-size:15px;
    box-sizing:border-box;
}

button{
    padding:14px 22px;
    border:none;
    border-radius:12px;
    font-size:16px;
    cursor:pointer;
    font-weight:bold;
}

.btn-start{
    background:#22c55e;
    color:white;
}

.btn-stop{
    background:#ef4444;
    color:white;
}

.actions{
    display:flex;
    gap:10px;
    margin-bottom:30px;
}

label{
    color:#cbd5e1;
    font-size:14px;
}

.info-box{
    background:#0f172a;
    border:1px solid #334155;
    border-radius:12px;
    padding:15px;
    color:#cbd5e1;
    margin-bottom:20px;
}

</style>
</head>

<body>

<div class="container">

<div class="title">GKTraderBot</div>

<div class="subtitle">
Panel profesional para IQ Option OTC
</div>

<div class="actions">

<form method="POST" action="/start" style="margin:0;">
<button type="submit" class="btn-start">
▶ Iniciar Bot
</button>
</form>

<form method="POST" action="/stop" style="margin:0;">
<button type="submit" class="btn-stop">
■ Detener Bot
</button>
</form>

</div>

<div class="grid">

<div class="card">
<h2>Estado</h2>
<div class="stat">{{state.get("estado","DETENIDO")}}</div>
</div>

<div class="card">
<h2>Operaciones</h2>
<div class="stat">{{state.get("operaciones",0)}}</div>
</div>

<div class="card">
<h2>Ganadas</h2>
<div class="stat">{{state.get("ganadas",0)}}</div>
</div>

<div class="card">
<h2>Perdidas</h2>
<div class="stat">{{state.get("perdidas",0)}}</div>
</div>

</div>

<form method="POST" action="/save">

<div class="card" style="margin-top:30px;">

<h2>Configuración</h2>

<label>Email IQ Option</label>
<input type="text" name="email" value="{{email}}">

<label>Password IQ Option</label>
<input type="password" name="password" value="{{password}}">

<label>Cuenta</label>

<select name="cuenta">

<option value="PRACTICE"
{% if cuenta == "PRACTICE" %}
selected
{% endif %}
>
PRACTICE
</option>

<option value="REAL"
{% if cuenta == "REAL" %}
selected
{% endif %}
>
REAL
</option>

</select>

<label>Monto</label>
<input type="text" name="monto" value="{{monto}}">

<label>Expiración (min)</label>
<input type="text" name="tiempo_orden" value="{{tiempo_orden}}">

<label>Pares OTC fijos</label>

<div class="info-box">
EURUSD-OTC<br>
GBPUSD-OTC<br>
USDCHF-OTC
</div>

<button type="submit" class="btn-start">
Guardar Configuración
</button>

</div>

</form>

</div>

</body>
</html>
"""


def read_config():

    cfg = configparser.ConfigParser()

    cfg.read(CONFIG_FILE, encoding="utf-8")

    if "IQOPTION" not in cfg:
        cfg["IQOPTION"] = {}

    if "GENERAL" not in cfg:
        cfg["GENERAL"] = {}

    if "ACTIVOS" not in cfg:
        cfg["ACTIVOS"] = {}

    return cfg


def save_config(cfg):

    cfg["ACTIVOS"]["pares"] = PARES_OTC_FIJOS

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)


@app.route("/")
def index():

    cfg = read_config()

    return render_template_string(
        HTML,
        state=get_state(),
        email=cfg["IQOPTION"].get("email", ""),
        password=cfg["IQOPTION"].get("password", ""),
        cuenta=cfg["GENERAL"].get("cuenta", "PRACTICE"),
        monto=cfg["GENERAL"].get("monto", "1.20"),
        tiempo_orden=cfg["GENERAL"].get("tiempo_orden", "1")
    )


@app.route("/state")
def state():
    return jsonify(get_state())


@app.route("/start", methods=["POST"])
def start():

    global bot_thread

    cfg = read_config()

    save_config(cfg)

    clear_stop()

    if bot_thread and bot_thread.is_alive():
        return redirect("/")

    def runner():

        print("BOT INICIADO")

        GKTraderBot().run_forever()

    bot_thread = threading.Thread(
        target=runner,
        daemon=True
    )

    bot_thread.start()

    return redirect("/")


@app.route("/stop", methods=["POST"])
def stop():

    print("BOT DETENIDO")

    request_stop()

    return redirect("/")


@app.route("/save", methods=["POST"])
def save():

    cfg = read_config()

    cfg["IQOPTION"]["email"] = request.form.get("email", "")
    cfg["IQOPTION"]["password"] = request.form.get("password", "")
    cfg["GENERAL"]["cuenta"] = request.form.get("cuenta", "PRACTICE")
    cfg["GENERAL"]["monto"] = request.form.get("monto", "1.20")
    cfg["GENERAL"]["tiempo_orden"] = request.form.get("tiempo_orden", "1")

    cfg["ACTIVOS"]["pares"] = PARES_OTC_FIJOS

    save_config(cfg)

    print("CONFIG GUARDADA")

    return redirect("/")


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
