import os
import shutil
import pandas as pd
import sqlite3
import threading
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from chatbot_model import get_chat_response  # Make sure chatbot_model.py exists

# === Paths ===
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'csv', 'db'}
STATIC_CSV = os.path.join(BASE_DIR, 'patient_details2.csv')  # Default CSV
DB_FILE = os.path.join(BASE_DIR, 'chatbot_data.db')

# === Flask App ===
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'replace_with_your_secret_key'

# === DB Initialization ===
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                        (id INTEGER PRIMARY KEY, message TEXT, response TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS current_file 
                        (id INTEGER PRIMARY KEY, filename TEXT)''')
        conn.commit()

init_db()

# === Cache & Lock ===
data_cache = None
data_lock = threading.Lock()

# === File Utils ===
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_current_file():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM current_file ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
    return result[0] if result else None

def set_current_file(filename):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM current_file")
        cursor.execute("INSERT INTO current_file (filename) VALUES (?)", (filename,))
        conn.commit()

def load_data():
    global data_cache
    current_file = get_current_file()
    if current_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_file)
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path)
                with data_lock:
                    data_cache = df
                print(f"[DATA] Loaded {current_file} into cache")
            except Exception as e:
                print(f"[DATA] Failed to read CSV {file_path}: {e}")
                with data_lock:
                    data_cache = None
        else:
            with data_lock:
                data_cache = None
    else:
        with data_lock:
            data_cache = None

def bootstrap_dataset():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    current = get_current_file()
    current_path = os.path.join(UPLOAD_FOLDER, current) if current else None
    needs_seed = (not current) or (current and not os.path.exists(current_path))

    if needs_seed:
        if os.path.exists(STATIC_CSV):
            dest = os.path.join(UPLOAD_FOLDER, os.path.basename(STATIC_CSV))
            if not os.path.exists(dest):
                shutil.copy(STATIC_CSV, dest)
                print(f"[INIT] Copied {STATIC_CSV} to {dest}")
            set_current_file(os.path.basename(STATIC_CSV))
        else:
            print("[INIT] No static CSV found. Waiting for upload.")

try:
    bootstrap_dataset()
    load_data()
except Exception as e:
    print(f"[INIT] Bootstrap error: {e}")

# === Routes ===
@app.route('/')
def index():
    current_file = get_current_file()
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message, response FROM chat_history")
        history = cursor.fetchall()
    return render_template('index.html', history=history, filename=current_file)

@app.route('/ask', methods=['POST'])
def ask():
    user_input = request.json.get('message')
    with data_lock:
        df = data_cache

    if df is None:
        return jsonify({'response': '⚠ No file uploaded or data loaded. Please upload a CSV first.'})

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message, response FROM chat_history ORDER BY id ASC")
        session_history = cursor.fetchall()

    response = get_chat_response(user_input, df, session_history=session_history)

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_history (message, response) VALUES (?, ?)", (user_input, response))
        conn.commit()

    return jsonify({'response': response})

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('index'))
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        file.save(save_path)
        set_current_file(filename)
        load_data()
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("DELETE FROM chat_history")
            conn.commit()
    return redirect(url_for('index'))

@app.route('/delete_file', methods=['POST'])
def delete_file():
    current_file = get_current_file()
    if current_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_file)
        if os.path.exists(file_path):
            os.remove(file_path)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM current_file")
            cursor.execute("DELETE FROM chat_history")
            conn.commit()
        global data_cache
        with data_lock:
            data_cache = None
    return redirect(url_for('index'))

@app.route('/clear_chat', methods=['POST'])
def clear_chat():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM chat_history")
        conn.commit()
    return jsonify({'status': 'cleared'})

# === Entry Point ===
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
