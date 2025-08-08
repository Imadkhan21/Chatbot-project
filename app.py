import os
import shutil
import pandas as pd
import sqlite3
import threading
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from chatbot_model import get_chat_response

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'db'}
STATIC_CSV = 'patient_details2.csv'  # CSV stored in repo root for Render

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'replace_with_your_secret'

# DB init
DB_FILE = 'chatbot_data.db'
conn = sqlite3.connect(DB_FILE)
conn.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                (id INTEGER PRIMARY KEY, message TEXT, response TEXT)''')
conn.execute('''CREATE TABLE IF NOT EXISTS current_file 
                (id INTEGER PRIMARY KEY, filename TEXT)''')
conn.commit()
conn.close()

# Cache & lock
data_cache = None
data_lock = threading.Lock()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_file():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM current_file ORDER BY id DESC LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def set_current_file(filename):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM current_file")
    cursor.execute("INSERT INTO current_file (filename) VALUES (?)", (filename,))
    conn.commit()
    conn.close()


def load_data():
    global data_cache
    current_file = get_current_file()
    if current_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_file)
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            with data_lock:
                data_cache = df
            print(f"[DATA] Loaded {current_file} into cache")
        else:
            with data_lock:
                data_cache = None
    else:
        with data_lock:
            data_cache = None


@app.route('/')
def index():
    current_file = get_current_file()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT message, response FROM chat_history")
    history = cursor.fetchall()
    conn.close()
    return render_template('index.html', history=history, filename=current_file)


@app.route('/ask', methods=['POST'])
def ask():
    user_input = request.json.get('message')

    with data_lock:
        df = data_cache

    if df is None:
        return jsonify({'response': '⚠ No file uploaded or data loaded. Please upload a CSV first.'})

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT message, response FROM chat_history ORDER BY id ASC")
    session_history = cursor.fetchall()
    conn.close()

    response = get_chat_response(user_input, df, session_history=session_history)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (message, response) VALUES (?, ?)", (user_input, response))
    conn.commit()
    conn.close()

    return jsonify({'response': response})


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(url_for('index'))
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        set_current_file(filename)
        load_data()
        conn = sqlite3.connect(DB_FILE)
        conn.execute("DELETE FROM chat_history")
        conn.commit()
        conn.close()
    return redirect(url_for('index'))


@app.route('/delete_file', methods=['POST'])
def delete_file():
    current_file = get_current_file()
    if current_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_file)
        if os.path.exists(file_path):
            os.remove(file_path)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM current_file")
        cursor.execute("DELETE FROM chat_history")
        conn.commit()
        conn.close()
        with data_lock:
            global data_cache
            data_cache = None
    return redirect(url_for('index'))


@app.route('/clear_chat', methods=['POST'])
def clear_chat():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM chat_history")
    conn.commit()
    conn.close()
    return jsonify({'status': 'cleared'})


if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Auto-copy CSV from repo root if uploads folder is empty
    if not any(fname.endswith('.csv') for fname in os.listdir(UPLOAD_FOLDER)):
        if os.path.exists(STATIC_CSV):
            shutil.copy(STATIC_CSV, os.path.join(UPLOAD_FOLDER, os.path.basename(STATIC_CSV)))
            set_current_file(os.path.basename(STATIC_CSV))
            print(f"[INIT] Copied {STATIC_CSV} to uploads/")
        else:
            print("[INIT] No static CSV found in repo root!")

    load_data()

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
