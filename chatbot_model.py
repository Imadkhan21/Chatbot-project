import pandas as pd
import google.generativeai as genai
import re
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0  # to make language detection consistent

# 🔑 Gemini API key
GEMINI_API_KEY = "AIzaSyDXB538kTAfi6dILexYffuoXrmEhXl8hqc"
genai.configure(api_key=GEMINI_API_KEY)

# 📦 Load Gemini model
model = genai.GenerativeModel("gemini-2.5-flash")

# ✅ Urdu/Roman Urdu detection
def is_urdu(text):
    try:
        lang = detect(text)
    except:
        lang = ""

    urdu_chars = re.findall(r'[\u0600-\u06FF]', text)
    has_urdu_script = len(urdu_chars) > 5
    is_probably_roman_urdu = lang in ["ur", "hi", "fa"]

    return has_urdu_script or is_probably_roman_urdu

# ✅ Format Gemini response to look clean
def format_response(response_text: str) -> str:
    # Remove code blocks
    response_text = re.sub(r'```python.*?```', '', response_text, flags=re.DOTALL)
    response_text = re.sub(r'```.*?```', '', response_text, flags=re.DOTALL)

    # Normalize spacing
    response_text = re.sub(r'\n\s*\n', '\n\n', response_text)
    response_text = re.sub(r'\s{2,}', ' ', response_text)

    # Bullet formatting
    response_text = re.sub(r'(\*\s+)', r'\n\1', response_text)
    response_text = re.sub(r'(-\s+)', r'\n\1', response_text)
    response_text = re.sub(r'(\d+\.\s+)', r'\n\1', response_text)  # Add newline before numbered items

    # Bold headers
    response_text = re.sub(r'(\*\*.*?\*\*)', r'\n\1', response_text)

    # Extra: split records by Name (if Gemini doesn't number them properly)
    response_text = re.sub(r'(\*\*Name\*\*:)', r'\n\n\1', response_text)

    return response_text.strip()

def get_chat_response(user_message, df):
    try:
        # Limit to first 500 rows to stay within Gemini token quota
        df_sample = df.head(500)

        columns = df_sample.columns.tolist()
        row_count = len(df_sample)
        data_preview = df_sample.to_dict(orient='records')

        urdu_requested = is_urdu(user_message)

        language_instruction = (
            "جواب صرف اردو میں دیں۔ انگریزی استعمال نہ کریں۔\n\n" if urdu_requested else ""
        )

        prompt = f"""
You are a dental clinic data assistant. A user has uploaded a dataset containing dental clinic records.

🔢 The dataset contains {row_count} rows.
📊 The available columns are: {columns}

Here is a sample of the dataset (first 500 rows only) as JSON records:
{data_preview}
📄 Show each record in a readable list format, not a paragraph.

📌 Answer the user's question based strictly on the data above.
✅ Be accurate with numbers (e.g., patient count, revenue, invoices, appointments).
🦷 Provide answers related to patients, treatments, invoices, payments, doctors, and appointments if asked.
💬 If the user asks general questions (e.g., "how are you?"), respond politely and stay helpful.
🚫 If any info is missing in the dataset, clearly say it's not available.

{language_instruction}
User's Question: "{user_message}"
"""

        response = model.generate_content(prompt)
        return format_response(response.text)

    except Exception as e:
        return f"Error generating response: {str(e)}"
