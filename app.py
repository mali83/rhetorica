import streamlit as st
import cv2
import mediapipe as mp
import google.generativeai as genai
import tempfile
import os
from PIL import Image
import re
from datetime import datetime
from fpdf import FPDF

# ==========================================
# 1. הגדרות שפה ותרגומים
# ==========================================
translations = {
    "English": {
        "title": "Rhetor-AI-ca Pro",
        "sidebar_header": "Analysis Settings",
        "purpose": "What is the goal?",
        "purposes": ["Job Interview", "Public Speaking", "Sales Pitch", "General"],
        "upload_label": "Upload Video (MP4, MOV)",
        "analyze_btn": " Start Professional Analysis",
        "spinner": "AI is analyzing your performance...",
        "score_label": "Performance Score",
        "download_pdf": " Download PDF Report",
        "wait_msg": "Waiting for video upload...",
        "dir": "ltr",
        "align": "left",
        "prompt_lang": "English"
    },
    "עברית": {
        "title": "Rhetor-AI-ca Pro",
        "sidebar_header": "הגדרות ניתוח",
        "purpose": "מהי מטרת הסרטון?",
        "purposes": ["ראיון עבודה", "דיבור מול קהל", "שיחת מכירה", "כללי"],
        "upload_label": "העלה קובץ וידאו (MP4, MOV)",
        "analyze_btn": " התחל ניתוח מקצועי",
        "spinner": "ה-AI מנתח את שפת הגוף שלך...",
        "score_label": "ציון ביצוע",
        "download_pdf": " הורד דו\"ח PDF",
        "wait_msg": "ממתין להעלאת קובץ וידאו...",
        "dir": "rtl",
        "align": "right",
        "prompt_lang": "Hebrew"
    }
}

# ==========================================
# 2. אתחול ממשק והגדרות API
# ==========================================
st.set_page_config(page_title="Rhetor-AI-ca Pro", layout="wide")

selected_lang = st.sidebar.radio("Language / שפה", ["English", "עברית"], index=0)
t = translations[selected_lang]

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
except Exception as e:
    st.error(f"API Configuration Error: {e}")
    st.stop()

# הזרקת CSS מותאם
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;400;700&display=swap');
    html, body, [data-testid="stSidebar"], .main {{
        font-family: 'Assistant', sans-serif;
        direction: {t['dir']};
        text-align: {t['align']};
    }}
    .analysis-card {{
        background-color: #1f2937;
        padding: 25px;
        border-radius: 15px;
        border-{t['align']}: 5px solid #10b981;
        margin-bottom: 20px;
        color: white;
    }}
    .main-title {{
        font-size: 45px;
        font-weight: 800;
        background: linear-gradient(to right, #3b82f6, #10b981);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 20px;
    }}
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 3. מנוע ניתוח (החלק שעבד בדיבאג)
# ==========================================
def get_working_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for target in ['models/gemini-1.5-flash', 'models/gemini-1.5-pro']:
            if target in models: return target
        return models[0]
    except:
        return 'gemini-1.5-flash'

def process_video_and_analyze(video_path, context_goal, lang_name):
    cap = cv2.VideoCapture(video_path)
    frames = []
    # חילוץ 3 פרימים לאורך הסרטון
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for i in range(3):
        cap.set(cv2.CAP_PROP_POS_FRAMES, (total // 3) * i)
        ret, frame = cap.read()
        if ret:
            frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    cap.release()

    model = genai.GenerativeModel(get_working_model())
    prompt = f"Expert body language analysis for {context_goal}. Language: {lang_name}. Return SCORE: [0-100] and ANALYSIS: [detailed feedback]."
    response = model.generate_content([prompt] + frames)
    return response.text

from bidi.algorithm import get_display

def create_pdf(analysis_text, score, ctx):
    pdf = FPDF()
    pdf.add_page()

    # הגדרת שוליים ברורה למניעת שגיאות חישוב
    pdf.set_left_margin(10)
    pdf.set_right_margin(10)

    # חישוב רוחב הדף הזמין (רוחב דף פחות שוליים)
    effective_page_width = pdf.w - 20

    font_path = "Assistant-Regular.ttf"
    if os.path.exists(font_path):
        pdf.add_font("Assistant", "", font_path)
        pdf.set_font("Assistant", "", 12)
    else:
        pdf.set_font('Arial', 'B', 14)

    # כותרת
    title = get_display("דו\"ח ניתוח Rhetor-AI-ca Pro")
    pdf.cell(effective_page_width, 10, title, 0, 1, 'C')
    pdf.ln(10)

    # הכנת הטקסט - שימוש ב-get_display
    # הוספת "נקיון" לטקסט למניעת תווים בלתי נראים שגורמים לשגיאה
    clean_text = analysis_text.replace('\n', ' ').strip()

    display_score = get_display(f"ציון: {score}/100")
    display_context = get_display(f"הקשר: {ctx}")
    display_analysis = get_display(clean_text)

    # כתיבה ל-PDF עם רוחב מוגדר מראש (במקום 0)
    pdf.multi_cell(effective_page_width, 10, txt=display_score, align='R')
    pdf.multi_cell(effective_page_width, 10, txt=display_context, align='R')
    pdf.ln(5)

    # כאן מתבצע התיקון הקריטי: רוחב קבוע למניעת שגיאת ה-Space
    pdf.multi_cell(effective_page_width, 10, txt=display_analysis, align='R')

    return pdf.output()
# ==========================================
# 4. ממשק המשתמש (UI)
# ==========================================
st.markdown(f'<h1 class="main-title">{t["title"]}</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown(f"### {t['sidebar_header']}")
    context = st.selectbox(t["purpose"], t["purposes"])
    st.markdown("---")
    video_file = st.file_uploader(t["upload_label"], type=['mp4', 'mov'])

if video_file:
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tfile:
        tfile.write(video_file.read())
        temp_path = tfile.name

    col_v, col_r = st.columns([1, 1])
    with col_v:
        st.video(video_file)
        if st.button(t["analyze_btn"]):
            with st.spinner(t["spinner"]):
                try:
                    result_text = process_video_and_analyze(temp_path, context, t['prompt_lang'])

                    # חילוץ ציון וטקסט מהתשובה
                    score_match = re.search(r"SCORE:\s*(\d+)", result_text)
                    score = score_match.group(1) if score_match else "70"
                    analysis = result_text.split("ANALYSIS:")[1] if "ANALYSIS:" in result_text else result_text

                    with col_r:
                        st.markdown(f"""
                        <div class="analysis-card">
                            <h2 style="color: #10b981;">{t['score_label']}: {score}/100</h2>
                            <hr style="border-color: #374151;">
                            <p style="font-size: 1.1em; line-height: 1.6;">{analysis}</p>
                        </div>
                        """, unsafe_allow_html=True)

                        pdf_data = create_pdf(analysis, score, context)
                        st.download_button(t["download_pdf"], bytes(pdf_data), "Rhetorica_Report.pdf", "application/pdf")
                except Exception as e:
                    st.error(f"Analysis Error: {e}")
                finally:
                    if os.path.exists(temp_path): os.remove(temp_path)
else:
    st.info(t["wait_msg"])