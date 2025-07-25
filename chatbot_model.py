import pandas as pd
import google.generativeai as genai
import re
from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0  # to make language detection consistent

# Gemini API key
GEMINI_API_KEY = "AIzaSyDXB538kTAfi6dILexYffuoXrmEhXl8hqc"
genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-2.5-flash")

def is_urdu(text):
    """Detect Urdu language using Unicode and langdetect (for Roman Urdu)."""
    try:
        lang = detect(text)
    except:
        lang = ""
    
    urdu_chars = re.findall(r'[\u0600-\u06FF]', text)
    has_urdu_script = len(urdu_chars) > 5
    is_probably_roman_urdu = lang in ["ur", "hi", "fa"]  # Urdu, Hindi, Persian often match Roman Urdu
    
    return has_urdu_script or is_probably_roman_urdu

def get_chat_response(user_message, df):
    try:
        columns = df.columns.tolist()
        row_count = len(df)
        data_preview = df.to_dict(orient='records')

        # Detect if the user message is in Urdu or Roman Urdu
        urdu_requested = is_urdu(user_message)

        # Add Urdu-only instruction if Urdu is detected
        language_instruction = (
            "جواب صرف اردو میں دیں۔ انگریزی استعمال نہ کریں۔\n\n" if urdu_requested else ""
        )

        prompt = f"""
You are a cricket data analyst assistant. A user has uploaded a dataset related to cricket.

🔢 The dataset contains {row_count} rows.
📊 The available columns are: {columns}

Here is the dataset (as JSON records):
{data_preview}

📌 Answer the user's question based strictly on the data above.
✅ Be accurate with numbers (e.g., row count, stats).
🚫 If a player's info or stat is missing, clearly say it's not available.

{language_instruction}
User's Question: "{user_message}"
"""

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        return f"Error generating response: {str(e)}"
