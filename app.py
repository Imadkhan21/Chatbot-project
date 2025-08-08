import os
import pandas as pd
import sqlite3
import threading
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from chatbot_model import get_chat_response

# --- CONFIG ---
STATIC_CSV = os.path.join(os.path.dirname(__file__), "patient_details2.csv")  # keep in repo
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'db'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = '...'  # Replace with your own key

# --- INIT DATABASE ---
DB_FILE = 'chatbot_data.db'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
conn = sqlite3.connect(DB_FILE)
conn.execute('''CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY,
    message TEXT,
    response TEXT
)''')
conn.execute('''CREATE TABLE IF NOT EXISTS current_file (
    id INTEGER PRIMARY KEY,
    filename TEXT
)''')
conn.commit()
conn.close()

# --- GLOBAL CACHE ---
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
    """
    Always try to load the bundled CSV if no uploaded file exists.
    """
    global data_cache
    current_file = get_current_file()

    # If a user uploaded file exists, load it
    if current_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_file)
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            with data_lock:
                data_cache = df
            return

    # Fallback: load the static CSV bundled in repo
    if os.path.exists(STATIC_CSV):
        df = pd.read_csv(STATIC_CSV)
        with data_lock:
            data_cache = df
        # Store in DB as current file reference (not uploads)
        set_current_file(os.path.basename(STATIC_CSV))
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
        return jsonify({'response': '⚠ Data could not be loaded.'})

    # Get chat history
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT message, response FROM chat_history ORDER BY id ASC")
    session_history = cursor.fetchall()
    conn.close()

    # Generate response
    response = get_chat_response(user_input, df, session_history=session_history)

    # Save to DB
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
        load_data()  # Refresh cache
        # Clear chat history
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
        # Clear DB
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
    load_data()  # Load CSV at startup (either uploaded or static)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
