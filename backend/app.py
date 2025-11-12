import os
import json
import pickle
import threading
import time
import base64
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.cloud import dialogflow_v2 as dialogflow

# -------------------------
# 🔹 RESTAURAR CREDENCIALES DIALOGFLOW
# -------------------------
token_b64 = os.getenv("TOKEN_PKL_BASE64")
if token_b64:
    token_path = "/tmp/dialogflow.json"  # Archivo temporal en Render
    with open(token_path, "wb") as f:
        f.write(base64.b64decode(token_b64))
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = token_path
    print("✅ Token de Dialogflow restaurado correctamente desde variable de entorno.")
else:
    raise Exception("❌ No se encontró la variable TOKEN_PKL_BASE64.")

# -------------------------
# 🔐 FIREBASE
# -------------------------
firebase_config_json = os.getenv("FIREBASE_CONFIG")
if not firebase_config_json:
    raise Exception("❌ No se encontró la variable FIREBASE_CONFIG")

try:
    cred_dict = json.loads(firebase_config_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
except Exception as e:
    raise Exception(f"Error al inicializar Firebase: {e}")

db = firestore.client()

# -------------------------
# ⚙️ APP FLASK
# -------------------------
app = Flask(__name__, template_folder="templates")
CORS(app)

# -------------------------
# 🔹 GOOGLE CLASSROOM
# -------------------------
TOKEN_FILE = 'token_secondary.pkl'
with open(TOKEN_FILE, 'rb') as token_file:
    creds = pickle.load(token_file)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
service = build('classroom', 'v1', credentials=creds)

# -------------------------
# 🔹 DIALOGFLOW
# -------------------------
PROJECT_ID = "chatbot-web-n9tj"
SESSION_ID = "arturo123"
session_client = dialogflow.SessionsClient()
session = session_client.session_path(PROJECT_ID, SESSION_ID)

# -------------------------
# 🏠 SERVIR FRONTEND
# -------------------------
@app.route("/")
def home():
    return render_template("index.html")

# -------------------------
# 📋 OBTENER TAREAS
# -------------------------
@app.route("/tareas", methods=["GET"])
def get_tareas():
    tareas_ref = db.collection("tareas")
    docs = tareas_ref.stream()
    resultado = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    return jsonify(resultado)

# -------------------------
# ➕ AGREGAR TAREA
# -------------------------
@app.route("/agregar_tarea", methods=["POST"])
def agregar_tarea():
    data = request.get_json()
    if not data or "titulo" not in data:
        return jsonify({"error": "Falta el campo 'titulo'"}), 400

    nueva_tarea = {
        "titulo": data.get("titulo"),
        "descripcion": data.get("descripcion", "")
    }
    db.collection("tareas").add(nueva_tarea)
    return jsonify({"mensaje": "Tarea agregada correctamente"}), 201

# -------------------------
# 📚 LISTAR CLASES DE CLASSROOM
# -------------------------
@app.route("/list_classes", methods=["GET"])
def list_classes():
    try:
        results = service.courses().list().execute()
        courses = results.get('courses', [])
        return jsonify(courses)
    except Exception as e:
        return jsonify({"error": str(e)})

# -------------------------
# 🔄 SINCRONIZAR CLASE
# -------------------------
@app.route("/sync_classroom", methods=["GET"])
def sync_classroom():
    course_id = "820099525378"
    try:
        curso = service.courses().get(id=course_id).execute()
        coursework = service.courses().courseWork().list(courseId=course_id).execute()
        tasks = coursework.get('courseWork', [])
        total = 0
        for work in tasks:
            db.collection('tareas').document(work['id']).set({
                'titulo': work['title'],
                'descripcion': work.get('description', ''),
                'curso': curso['name']
            })
            total += 1
        return jsonify({"mensaje": f"✅ Se sincronizaron {total} tareas de '{curso['name']}' a Firestore."})
    except Exception as e:
        return jsonify({"error": str(e)})

# -------------------------
# 💬 CHAT CON DIALOGFLOW
# -------------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    mensaje_usuario = data.get("mensaje", "")

    if "tareas" in mensaje_usuario.lower():
        tareas_ref = db.collection("tareas")
        docs = tareas_ref.stream()
        tareas = [
            f"📝 {doc.to_dict().get('titulo','(sin título)')} ({doc.to_dict().get('curso','')})"
            for doc in docs
        ]
        if tareas:
            return jsonify({"respuesta": "Estas son tus tareas:\n" + "\n".join(tareas)})
        else:
            return jsonify({"respuesta": "No tienes tareas disponibles."})

    text_input = dialogflow.TextInput(text=mensaje_usuario, language_code="es")
    query_input = dialogflow.QueryInput(text=text_input)
    response = session_client.detect_intent(request={"session": session, "query_input": query_input})

    return jsonify({"respuesta": response.query_result.fulfillment_text})

# -------------------------
# 🔄 SINCRONIZACIÓN AUTOMÁTICA
# -------------------------
SYNC_INTERVAL = 30  # segundos

def sync_classroom_automaticamente():
    course_id = "820099525378"
    while True:
        try:
            curso = service.courses().get(id=course_id).execute()
            coursework = service.courses().courseWork().list(courseId=course_id).execute()
            tasks = coursework.get('courseWork', [])
            classroom_ids = {task['id'] for task in tasks}
            firebase_docs = db.collection('tareas').stream()
            firebase_ids = {doc.id for doc in firebase_docs}

            # Agregar nuevas
            total_nuevas = 0
            for work in tasks:
                if work['id'] not in firebase_ids:
                    db.collection('tareas').document(work['id']).set({
                        'titulo': work['title'],
                        'descripcion': work.get('description', ''),
                        'curso': curso['name']
                    })
                    total_nuevas += 1

            # Eliminar viejas
            total_eliminadas = 0
            for fid in firebase_ids:
                if fid not in classroom_ids:
                    db.collection('tareas').document(fid).delete()
                    total_eliminadas += 1

            if total_nuevas or total_eliminadas:
                print(f"🔄 Sincronización: +{total_nuevas}, -{total_eliminadas} ({curso['name']})")

        except Exception as e:
            print("⚠️ Error al sincronizar:", e)

        time.sleep(SYNC_INTERVAL)

threading.Thread(target=sync_classroom_automaticamente, daemon=True).start()

# -------------------------
# 🚀 EJECUTAR SERVIDOR
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
