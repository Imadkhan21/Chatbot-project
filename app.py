import os
import pandas as pd
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from chatbot_model import get_chat_response

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialize DB
DB_FILE = 'chatbot_data.db'
conn = sqlite3.connect(DB_FILE)
conn.execute('''CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY, message TEXT, response TEXT)''')
conn.execute('''CREATE TABLE IF NOT EXISTS current_file (id INTEGER PRIMARY KEY, filename TEXT)''')
conn.commit()
conn.close()

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

@app.route('/')
def index():
    current_file = get_current_file()

    # Get chat history
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT message, response FROM chat_history")
    history = cursor.fetchall()
    conn.close()

    return render_template('index.html', history=history, filename=current_file)

@app.route('/ask', methods=['POST'])
def ask():
    user_input = request.json.get('message')
    current_file = get_current_file()

    if not current_file:
        return jsonify({'response': '⚠️ No file uploaded. Please upload a CSV first.'})

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], current_file)
    df = pd.read_csv(file_path)
    response = get_chat_response(user_input, df)

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

        # Clear file + chat history
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM current_file")
        cursor.execute("DELETE FROM chat_history")
        conn.commit()
        conn.close()

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
    app.run(debug=True)
