import os
import shutil
import pandas as pd
import sqlite3
import threading
import re
import io
import base64
import json
import matplotlib.pyplot as plt
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from chatbot_model import get_chat_response  # Make sure chatbot_model.py exists
from bs4 import BeautifulSoup  # Added for HTML parsing

# === Paths ===
stop_execution_flag = False
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')  # New directory for HTML templates
ALLOWED_EXTENSIONS = {'csv', 'db'}
STATIC_CSV = os.path.join(BASE_DIR, 'patient_details2.csv')  # Default CSV
DB_FILE = os.path.join(BASE_DIR, 'chatbot_data.db')

# === Flask App ===
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'AIzaSyC0gdJDMyBRYTTvY5Kxp8FT4KUSqThMLk0'

# Create templates directory if it doesn't exist
os.makedirs(TEMPLATES_DIR, exist_ok=True)
print(f"Templates directory: {TEMPLATES_DIR}")
print(f"Templates directory exists: {os.path.exists(TEMPLATES_DIR)}")

# Test write permissions
try:
    test_file = os.path.join(TEMPLATES_DIR, 'test.txt')
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    print("Write permission to templates directory: OK")
except Exception as e:
    print(f"Write permission error: {e}")

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

# Change STATIC_CSV path to match where you actually store it in repo
STATIC_CSV = os.path.join(BASE_DIR, 'uploads', 'patient_details2.csv')  

def bootstrap_dataset():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    current = get_current_file()
    current_path = os.path.join(UPLOAD_FOLDER, current) if current else None
    needs_seed = (not current) or (current and not os.path.exists(current_path))
    if needs_seed:
        if os.path.exists(STATIC_CSV):
            dest = os.path.join(UPLOAD_FOLDER, os.path.basename(STATIC_CSV))
            shutil.copy(STATIC_CSV, dest)  # Always overwrite to be safe
            set_current_file(os.path.basename(STATIC_CSV))
            print(f"[INIT] Seed dataset loaded: {dest}")
        else:
            print(f"[INIT] No static CSV found at {STATIC_CSV}")

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
    global stop_execution_flag
    stop_execution_flag = False  # reset at the start of request
    user_input = request.json.get('message')
    with data_lock:
        df = data_cache
    if df is None:
        return jsonify({'response': '⚠ No file uploaded or data loaded. Please upload a CSV first.'})
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message, response FROM chat_history ORDER BY id ASC")
        session_history = cursor.fetchall()
    
    if stop_execution_flag:
        return jsonify({'status': 'stopped', 'response': None})
    
    response = get_chat_response(user_input, df, session_history=session_history)
    
    if stop_execution_flag:
        return jsonify({'status': 'stopped', 'response': None})
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_history (message, response) VALUES (?, ?)", (user_input, response))
        conn.commit()
    
    return jsonify({'response': response})

@app.route('/stop_execution', methods=['POST'])
def stop_execution():
    global stop_execution_flag
    stop_execution_flag = True
    return jsonify({'status': 'stopped'})

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

# === Test Route ===
@app.route('/test_template')
def test_template():
    try:
        # Create a simple test template
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"test_{timestamp}.html"
        filepath = os.path.join(TEMPLATES_DIR, filename)
        
        with open(filepath, 'w') as f:
            f.write("<html><body><h1>Test Template</h1><p>If you see this, the template serving is working!</p></body></html>")
        
        template_url = f"{request.host_url}templates/{filename}"
        
        return jsonify({
            "message": "Test template created",
            "template_url": template_url
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === New Route to Serve Templates ===
@app.route('/templates/<filename>')
def serve_template(filename):
    return send_from_directory(TEMPLATES_DIR, filename)

# === Table API (Modified with Debug Logging) ===
@app.route('/ask_table', methods=['POST'])
def ask_table():
    try:
        data = request.json
        query = data.get("query", "")
        print(f"[DEBUG] Received query: {query}")
        
        with data_lock:
            df = data_cache
        
        if df is None:
            print("[DEBUG] No data loaded")
            return jsonify({"error": "⚠ No data loaded. Please upload a CSV first."}), 400
        
        # Get session history like in the /ask endpoint
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message, response FROM chat_history ORDER BY id ASC")
            session_history = cursor.fetchall()
        
        # Get response from chatbot model with session history
        response_text = get_chat_response(query, df, session_history=session_history)
        print(f"[DEBUG] Raw response: {response_text[:100]}...")  # Print first 100 chars
        
        # Generate a unique filename for the template
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"table_{timestamp}_{unique_id}.html"
        filepath = os.path.join(TEMPLATES_DIR, filename)
        print(f"[DEBUG] Generated filename: {filename}")
        print(f"[DEBUG] Full filepath: {filepath}")
        
        # Create HTML template for the table
        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Patient Data Table</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            text-align: center;
            margin-bottom: 20px;
        }}
        .table-container {{
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        tr:hover {{
            background-color: #f1f1f1;
        }}
        .back-link {{
            display: inline-block;
            margin-top: 20px;
            padding: 10px 15px;
            background-color: #4CAF50;
            color: white;
            text-decoration: none;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Patient Data Table</h1>
        <div class="table-container">
            {response_text}
        </div>
        <a href="#" class="back-link" onclick="window.history.back()">Back</a>
    </div>
</body>
</html>
        """
        
        # Save the HTML template to file
        try:
            with open(filepath, 'w') as f:
                f.write(html_template)
            print(f"[DEBUG] File saved successfully")
            print(f"[DEBUG] File exists: {os.path.exists(filepath)}")
            print(f"[DEBUG] File size: {os.path.getsize(filepath)} bytes")
        except Exception as e:
            print(f"[ERROR] Failed to save file: {e}")
            return jsonify({"error": f"Failed to save template: {str(e)}"}), 500
        
        # Generate the URL for the template
        try:
            template_url = f"{request.host_url}templates/{filename}"
            print(f"[DEBUG] Generated template URL: {template_url}")
        except Exception as e:
            print(f"[ERROR] Failed to generate URL: {e}")
            return jsonify({"error": f"Failed to generate URL: {str(e)}"}), 500
        
        response_data = {
            "template_url": template_url
        }
        print(f"[DEBUG] Returning response: {response_data}")
        
        return jsonify(response_data)
    except Exception as e:
        print(f"[ERROR] General error in /ask_table: {str(e)}")
        return jsonify({"error": str(e)}), 500

# === Chart API (Modified) ===
@app.route('/chart', methods=['POST'])
def chart():
    try:
        data = request.json
        query = data.get("query", "")
        print(f"[DEBUG] Received chart query: {query}")
        
        with data_lock:
            df = data_cache
        
        if df is None:
            print("[DEBUG] No data loaded for chart")
            return jsonify({"error": "⚠ No data loaded. Please upload a CSV first."}), 400
        
        # Get session history like in the /ask endpoint
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT message, response FROM chat_history ORDER BY id ASC")
            session_history = cursor.fetchall()
        
        # Get response from chatbot model with session history
        response_text = get_chat_response(query, df, session_history=session_history)
        print(f"[DEBUG] Raw chart response: {response_text[:100]}...")
        
        chart_json = None
        if "CHART_DATA:" in response_text:
            try:
                # Extract the JSON part after "CHART_DATA:"
                chart_str = response_text.split("CHART_DATA:")[1].strip()
                print(f"[DEBUG] Extracted chart string: {chart_str}")
                
                # Parse the JSON
                chart_json = json.loads(chart_str)
                print(f"[DEBUG] Parsed chart JSON: {chart_json}")
            except json.JSONDecodeError as e:
                print(f"[CHART_PARSE_ERROR] JSON decode error: {e}")
                print(f"[CHART_PARSE_ERROR] Problematic string: {chart_str}")
            except Exception as e:
                print(f"[CHART_PARSE_ERROR] Other error: {e}")
        else:
            print("[DEBUG] No CHART_DATA found in response")
            
        if chart_json:
            labels = chart_json.get("labels", [])
            values = chart_json.get("values", [])
            title = chart_json.get("title", "Chart")
            
            # Generate chart
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.bar(labels, values)
            ax.set_title(title)
            ax.set_xlabel("Category")
            ax.set_ylabel("Value")
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
            # Convert to base64
            img = io.BytesIO()
            plt.savefig(img, format='png')
            img.seek(0)
            plot_url = base64.b64encode(img.getvalue()).decode()
            plt.close(fig)
            
            # Generate a unique filename for the template
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            filename = f"chart_{timestamp}_{unique_id}.html"
            filepath = os.path.join(TEMPLATES_DIR, filename)
            print(f"[DEBUG] Generated chart filename: {filename}")
            print(f"[DEBUG] Full chart filepath: {filepath}")
            
            # Create HTML template for the chart
            html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            text-align: center;
            margin-bottom: 20px;
        }}
        .chart-container {{
            text-align: center;
            margin-top: 20px;
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 4px;
        }}
        .back-link {{
            display: inline-block;
            margin-top: 20px;
            padding: 10px 15px;
            background-color: #4CAF50;
            color: white;
            text-decoration: none;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="chart-container">
            <img src="data:image/png;base64,{plot_url}" alt="{title}">
        </div>
        <a href="#" class="back-link" onclick="window.history.back()">Back</a>
    </div>
</body>
</html>
            """
            
            # Save the HTML template to file
            try:
                with open(filepath, 'w') as f:
                    f.write(html_template)
                print(f"[DEBUG] Chart file saved successfully")
                print(f"[DEBUG] Chart file exists: {os.path.exists(filepath)}")
                print(f"[DEBUG] Chart file size: {os.path.getsize(filepath)} bytes")
            except Exception as e:
                print(f"[ERROR] Failed to save chart file: {e}")
                return jsonify({"error": f"Failed to save chart template: {str(e)}"}), 500
            
            # Generate the URL for the template
            try:
                template_url = f"{request.host_url}templates/{filename}"
                print(f"[DEBUG] Generated chart template URL: {template_url}")
            except Exception as e:
                print(f"[ERROR] Failed to generate chart URL: {e}")
                return jsonify({"error": f"Failed to generate chart URL: {str(e)}"}), 500
            
            response_data = {
                "template_url": template_url
            }
            print(f"[DEBUG] Returning chart response: {response_data}")
            
            return jsonify(response_data)
        
        return jsonify({
            "error": "No chart data found"
        }), 400
    except Exception as e:
        print(f"[ERROR] General error in /chart: {str(e)}")
        return jsonify({"error": str(e)}), 500

# === Entry Point ===
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5004))
    app.run(host='0.0.0.0', port=port, debug=True)