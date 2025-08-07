import pandas as pd
import google.generativeai as genai
import re
from langdetect import detect, DetectorFactory
import logging
import io

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DetectorFactory.seed = 0  # to make language detection consistent

# 🔑 Gemini API key
GEMINI_API_KEY = "AIzaSyC0gdJDMyBRYTTvY5Kxp8FT4KUSqThMLk0"
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
# ---------- Formatting Functions ----------
def format_response_table(response_text: str):
    """
    Converts markdown or tab-separated table to styled HTML table.
    Removes markdown separator lines with only dashes.
    """
    table_lines = []
    in_table = False

    for line in response_text.splitlines():
        if "|" in line or "\t" in line:
            if re.match(r"^\s*[-\s|]+\s*$", line):  # Skip separator row
                continue
            table_lines.append(line.strip())
            in_table = True
        elif in_table and line.strip() == "":
            break  # End of table

    if table_lines:
        # Detect separator type
        sep = "|" if "|" in table_lines[0] else "\t"

        # Normalize rows
        normalized_lines = []
        for line in table_lines:
            if sep == "|":
                cells = [cell.strip() for cell in line.strip('|').split('|')]
            else:
                cells = [cell.strip() for cell in line.split('\t')]
            normalized_lines.append('\t'.join(cells))  # Normalize to tab

        fixed_table = "\n".join(normalized_lines)

        try:
            df = pd.read_csv(io.StringIO(fixed_table), sep="\t")
            df = df.dropna(how='all')  # Drop empty rows
            df.columns = [col.strip() for col in df.columns]

            # Generate HTML table
            html_table = '''
<style>
.table-container {
    max-width: 100%;
    overflow-x: auto;
}
.solid-table {
    border-collapse: collapse;
    width: 100%;
}
.solid-table th, .solid-table td {
    border: 1px solid #ccc;
    padding: 8px;
    text-align: left;
}
.solid-table th {
    background-color: #f2f2f2;
}
.solid-table tr.dash-row {
    display: none; /* hide dashed rows if any */
}
</style>
<div class="table-container">
<table class="solid-table">
<thead><tr>
'''
            # Headers
            for col in df.columns:
                html_table += f"<th>{col}</th>"
            html_table += "</tr></thead><tbody>"

            # Rows
            for _, row in df.iterrows():
                row_values = list(row)
                if all(re.match(r"^-+$", str(cell).strip()) for cell in row_values):
                    html_table += '<tr class="dash-row">'
                else:
                    html_table += '<tr>'
                for cell in row:
                    html_table += f"<td>{cell}</td>"
                html_table += "</tr>"

            html_table += "</tbody></table></div>"
            return html_table

        except Exception as e:
            logger.error(f"Error parsing table: {str(e)}")
            return "<pre>" + fixed_table + "</pre>"

    return None

def format_response_list(response_text: str) -> str:
    logger.info(f"Formatting response as list: {response_text[:100]}...")
    if not response_text or response_text.strip() == "":
        return "I'm sorry, I couldn't generate a response. Please try again."
    # Remove markdown code blocks
    response_text = re.sub(r'```.*?```', '', response_text, flags=re.DOTALL)
    # REMOVE BOLD MARKDOWN (**text**) globally!
    response_text = re.sub(r'\*\*(.*?)\*\*', r'\1', response_text)
    # Proceed as before
    records = re.split(r'(?=Patient:|MRN:)', response_text)
    formatted_records = []
    for record in records:
        if not record.strip():
            continue
        record = record.strip()
        record = re.sub(r'^-+\s*', '', record)
        # This regex may be unnecessary for your city list, so just add as bullet
        formatted_records.append(f"- {record}")
    result = '\n'.join(formatted_records).strip()
    return result if result else response_text

def format_response_paragraph(response_text: str) -> str:
    logger.info(f"Formatting response as paragraph: {response_text[:100]}...")
    response_text = re.sub(r'```.*?```', '', response_text, flags=re.DOTALL)
    response_text = re.sub(r'\*\*(.*?)\*\*', r'\1', response_text)
    return response_text.replace("\n", " ").strip()

# ---------- Main Chat Function ----------
def get_chat_response(user_message, df, session_history=None, answer_format='auto'):
    """
    Merged function supporting:
    - HTML table output (if markdown table detected and answer_format='auto' or 'table')
    - List format (if answer_format='list')
    - Paragraph format (if answer_format='paragraph')
    - Session history
    """
    try:
        logger.info(f"Processing user message: {user_message}")
        # Data cleaning
        df = df.dropna(axis=0, how='all')
        df = df.dropna(axis=1, how='all')
        df_sample = df.head(300)
        columns = df_sample.columns.tolist()
        row_count = len(df_sample)
        data_preview = df_sample.to_dict(orient='records')
        urdu_requested = is_urdu(user_message)
        language_instruction = (
            "جواب صرف اردو میں دیں۔ انگریزی استعمال نہ کریں۔\n\n" if urdu_requested else ""
        )
        # Session history
        history_text = ""
        if session_history:
            history_text = "\n\nRECENT CHAT HISTORY:\n"
            for user_msg, bot_resp in session_history[-5:]:
                user_msg = user_msg[:200] + "..." if len(user_msg) > 200 else user_msg
                bot_resp = bot_resp[:200] + "..." if len(bot_resp) > 200 else bot_resp
                history_text += f"User: {user_msg}\nBot: {bot_resp}\n\n"
        
        prompt = f"""

You are a helpful assistant. Always respond in short and concise answers. Keep replies under 2–3 sentences. Prioritize fast response generation (within 3–5 seconds). Avoid unnecessary explanations.
You are a dental clinic data assistant with memory of recent conversations. A user has uploaded a dataset containing dental clinic records.
🔢 The dataset contains {row_count} rows (showing first 500 rows).
📊 The available columns are: {columns}
Here is a sample of the dataset (first 500 rows only) as JSON records:
{data_preview}
{history_text}
📄 Prefer to show tabular data as a clean, readable table if appropriate, otherwise use bullet points or a short paragraph depending on the question.
📌 Answer the user's question based strictly on the data above.
Do not say things like "based on the dataset" or use bold text or emojis.
Do not use symbol like " * * " .
✅ Be accurate with numbers (e.g., patient count, revenue, invoices, appointments).
🦷 Provide answers related to patients, treatments, invoices, payments, doctors, and appointments if asked.
💬 If the user asks general questions (e.g., "how are you?"), respond politely and stay helpful.
🚫 If any info is missing in the dataset, clearly say it's not available.

You are a helpful assistant. Always respond in short and concise answers. Keep replies under 2–3 sentences. Prioritize fast response generation (within 3–5 seconds). Avoid unnecessary explanations.
 

{language_instruction}
User's Question: "{user_message}"
"""
        logger.info(f"Sending prompt to Gemini: {prompt[:200]}...")
        response = model.generate_content(prompt)
        logger.info(f"Received response: {response.text[:100]}...")
        
        if answer_format == 'auto' or answer_format == 'table':
            table_html = format_response_table(response.text)
            if table_html:
                return table_html
            # Fallback: try list style if table is not detected
            if answer_format == 'table':
                # If forced to return table but no table found, return plain text
                return response.text.strip()
            # Else try list style
            return format_response_list(response.text)
        elif answer_format == 'list':
            return format_response_list(response.text)
        elif answer_format == 'paragraph':
            return format_response_paragraph(response.text)
        else:
            # fallback
            return response.text.strip()
    except Exception as e:
        logger.error(f"Error in get_chat_response: {str(e)}")
        return f"Error generating response: {str(e)}"