
import pandas as pd
import google.generativeai as genai

# ✅ Replace this with your actual Gemini API key
GEMINI_API_KEY = "AIzaSyDXB538kTAfi6dILexYffuoXrmEhXl8hqc"

# Configure the Gemini model
genai.configure(api_key=GEMINI_API_KEY)

# Load the Gemini model
model = genai.GenerativeModel("gemini-2.5-flash")

def get_chat_response(user_message, df):
    """
    Generate a Gemini-powered response based on the user's question and the CSV data.
    """
    try:
        # Extract info
        columns = df.columns.tolist()
        row_count = len(df)
        data_preview = df.to_dict(orient='records')  # Full dataset

        prompt = f"""
You are a cricket data analyst assistant. A user has uploaded a dataset related to cricket.

🔢 The dataset contains **{row_count} rows**.
📊 The available columns are: {columns}

Here is the full dataset content (as JSON records):
{data_preview}

📌 Answer the user's question based strictly on the data above.
✅ Be accurate with numbers (e.g., row count, stats).
🚫 If a player's info or stat is missing, clearly say it's not available.

User's Question: "{user_message}"
"""

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        return f"Error generating response: {str(e)}"
