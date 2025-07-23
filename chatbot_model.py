# def get_chat_response(message, df):
#     message = message.lower()

#     if "top scorer" in message:
#         col = [c for c in df.columns if 'run' in c.lower()]
#         if col:
#             top_player = df.sort_values(by=col[0], ascending=False).iloc[0]
#             return f"Top scorer is {top_player['Player']} with {top_player[col[0]]} runs."
#         else:
#             return "Couldn't find a 'runs' column."

#     elif "average" in message:
#         col = [c for c in df.columns if 'avg' in c.lower()]
#         if col:
#             avg_val = df[col[0]].mean()
#             return f"Average {col[0]} is {avg_val:.2f}"
#         else:
#             return "No average column found."

#     else:
#         return "Sorry, I couldn't understand. Try asking about top scorer or average."


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
        # Extract column names
        columns = df.columns.tolist()

        # Use only a portion of the data for context to avoid overloading the model
        data_preview = df.head(30).to_dict(orient='records')

        prompt = f"""
You are a cricket data analyst assistant. A user has uploaded a dataset related to cricket.

The columns available in the dataset are: {columns}

Here is a sample of the data:
{data_preview}

Now answer the user's question based only on the provided dataset.
If a player or statistic is asked for, extract the correct value from the sample data.
If the information is missing, say so politely.

User's Question: "{user_message}"
"""

        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        return f"Error generating response: {str(e)}"
