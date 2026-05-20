import os
import subprocess
import sys
import threading
import configparser

from flask import Flask, redirect, render_template_string, request, jsonify

from bot_engine import GKTraderBot, get_state, request_stop, clear_stop, CONFIG_FILE

app = Flask(__name__)
bot_thread = None


HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>GKTraderBot</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body{margin:0;font-family:Arial;background:#0b1020;color:#fff}
    .wrap{max-width:1100px;margin:auto;padding:24px}
    .card{background:#141b34;border:1px solid #26345e;border-radius:16px;padding:20px;margin-bottom:18px;box-shadow:0 8px 24px #0005}
    h1{margin:0 0 8px;font-size:34px}
    .brand{color:#00e5ff}
    input,select,textarea{width:100%;padding:12px;border-radius:10px;border:1px solid #32446f;background:#0b1020;color:#fff;margin:6px 0 12px}
    label{font-size:14px;color:#b8c7ff}
    button{border:0;border-radius:12px;padding:13px 18px;font-weight:bold;cursor:pointer;margin-right:8px}
    .start{background:#00e676;color:#001b0b}
    .stop{background:#ff5252;color:#fff}
    .save{background:#40c4ff;color:#00131a}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}
    .stat{background:#0b1020;border-radius:14px;padding:16px;border:1px solid #26345e}
    .stat b{font-size:24px;color:#00e5ff}
    pre{white-space:pre-wrap;background:#080c18;border-radius:12px;padding:14px;color:#d7e1ff}
    .warn{color:#ffd54f}
  </style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1><span class="brand">GK</span>TraderBot</h1>
    <p>Panel web local para señales OTC / IQ Option. Recomendado usar siempre en PRACTICE.</p>
    <form method="post" action="/start" style="display:inline"><button class="start">▶ Iniciar bot</button></form>
    <form method="post" action="/stop" style="display:inline"><button class="stop">■ Detener bot</button></form>
  </div>

  <div class="grid">
    <div class="stat">Estado<br><b id="status">{{state.status}}</b></div>
    <div class="stat">Operaciones<br><b id="operaciones">{{state.operaciones}}</b></div>
    <div class="stat">Ganadas<br><b id="wins">{{state.wins}}</b></div>
    <div class="stat">Perdidas<br><b id="losses">{{state.losses}}</b></div>
    <div class="stat">Ganancia<br><b id="ganancia">{{state.ganancia}}</b></div>
  </div>

  <div class="card">
    <h2>Configuración</h2>
    <p class="warn">Auto operar queda bloqueado para REAL. Solo opera automático si cuenta = PRACTICE.</p>
    <form method="post" action="/save">
      <div class="grid">
        <div>
          <label>Email IQ Option</label>
          <input name="email" value="{{cfg['IQOPTION']['email']}}">
        </div>
        <div>
          <label>Password IQ Option</label>
          <input name="password" type="password" value="{{cfg['IQOPTION']['password']}}">
        </div>
        <div>
          <label>Cuenta</label>
          <select name="cuenta">
            <option value="PRACTICE" {% if cfg['GENERAL']['cuenta']=='PRACTICE' %}selected{% endif %}>PRACTICE / DEMO</option>
            <option value="REAL" {% if cfg['GENERAL']['cuenta']=='REAL' %}selected{% endif %}>REAL</option>
          </select>
        </div>
        <div>
          <label>Auto operar</label>
          <select name="auto_operar">
            <option value="N" {% if cfg['GENERAL']['auto_operar']=='N' %}selected{% endif %}>No, solo señales</option>
            <option value="S" {% if cfg['GENERAL']['auto_operar']=='S' %}selected{% endif %}>Sí, solo demo</option>
          </select>
        </div>
        <div>
          <label>Monto</label>
          <input name="monto" value="{{cfg['GENERAL']['monto']}}">
        </div>
        <div>
          <label>Expiración minutos</label>
          <input name="tiempo_orden" value="{{cfg['GENERAL']['tiempo_orden']}}">
        </div>
        <div>
          <label>Token Telegram</label>
          <input name="token" value="{{cfg['TELEGRAM']['token']}}">
        </div>
        <div>
          <label>Chat ID Telegram</label>
          <input name="chat_id" value="{{cfg['TELEGRAM']['chat_id']}}">
        </div>
      </div>
      <label>Activos</label>
      <textarea name="pares" rows="3">{{cfg['ACTIVOS']['pares']}}</textarea>
      <button class="save">Guardar configuración</button>
    </form>
  </div>

  <div class="card">
    <h2>Última señal</h2>
    <pre id="ultima">{{state.ultima_senal}}</pre>
  </div>
</div>
<script>
async function refresh(){
  const r = await fetch('/state');
  const s = await r.json();
  document.getElementById('status').innerText = s.status || '';
  document.getElementById('operaciones').innerText = s.operaciones || 0;
  document.getElementById('wins').innerText = s.wins || 0;
  document.getElementById('losses').innerText = s.losses || 0;
  document.getElementById('ganancia').innerText = s.ganancia || 0;
  document.getElementById('ultima').innerText = s.ultima_senal || '';
}
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


def read_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE, encoding="utf-8")
    return cfg


@app.route("/")
def index():
    return render_template_string(HTML, state=get_state(), cfg=read_config())


@app.route("/state")
def state():
    return jsonify(get_state())


@app.route("/start", methods=["POST"])
def start():
    global bot_thread
    clear_stop()
    if bot_thread and bot_thread.is_alive():
        return redirect("/")

    def runner():
        GKTraderBot().run_forever()

    bot_thread = threading.Thread(target=runner, daemon=True)
    bot_thread.start()
    return redirect("/")


@app.route("/stop", methods=["POST"])
def stop():
    request_stop()
    return redirect("/")


@app.route("/save", methods=["POST"])
def save():
    cfg = read_config()
    cfg["IQOPTION"]["email"] = request.form.get("email", "")
    cfg["IQOPTION"]["password"] = request.form.get("password", "")
    cfg["GENERAL"]["cuenta"] = request.form.get("cuenta", "PRACTICE")
    cfg["GENERAL"]["auto_operar"] = request.form.get("auto_operar", "N")
    cfg["GENERAL"]["monto"] = request.form.get("monto", "1.20")
    cfg["GENERAL"]["tiempo_orden"] = request.form.get("tiempo_orden", "1")
    cfg["TELEGRAM"]["token"] = request.form.get("token", "")
    cfg["TELEGRAM"]["chat_id"] = request.form.get("chat_id", "")
    cfg["ACTIVOS"]["pares"] = request.form.get("pares", "")
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)
    return redirect("/")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
