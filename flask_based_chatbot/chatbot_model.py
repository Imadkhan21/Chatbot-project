import pandas as pd
import google.generativeai as genai

# ✅ Set your Gemini API key
GEMINI_API_KEY = "AIzaSyDXB538kTAfi6dILexYffuoXrmEhXl8hqc"

# Configure Gemini model
genai.configure(api_key=GEMINI_API_KEY)

# Load Gemini model (use flash for speed)
model = genai.GenerativeModel("gemini-2.5-flash")

def get_chat_response(user_message, df):
    """
    Use Gemini to answer user questions based on cricket dataset (CSV).
    """
    try:
        # Get column names
        columns = df.columns.tolist()

        # Sample data for context (avoid overload)
        sample_data = df.head(30).to_dict(orient='records')

        # Build prompt
        prompt = f"""
You are a smart cricket data assistant.
Analyze the given dataset and answer the user's question only from the data.

Dataset Columns: {columns}

Sample Data:
{sample_data}

User Question: "{user_message}"

Answer clearly and briefly using data values.
If data is not available, reply: "Sorry, I couldn't find that in the dataset."
"""

        # Generate Gemini response
        response = model.generate_content(prompt)

        # Return plain text
        return response.text.strip()

    except Exception as e:
        return f"❌ Gemini Error: {str(e)}"
