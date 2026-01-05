import streamlit as st
import google.generativeai as genai
import cv2
import tempfile
import os
from PIL import Image

st.set_page_config(page_title="Rhetor-AI-ca Fix", layout="wide")

# טעינת מפתח
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
    st.sidebar.success("✅ מפתח API נטען בהצלחה")
except Exception as e:
    st.sidebar.error(f"❌ שגיאה במפתח: {e}")
    st.stop()

def get_working_model():
    """חיפוש מודל זמין באופן דינמי למניעת שגיאת 404"""
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # עדיפות ל-Flash 1.5
        for target in ['models/gemini-1.5-flash', 'models/gemini-pro-vision', 'models/gemini-1.0-pro']:
            if target in models:
                return target
        return models[0] if models else "models/gemini-1.5-flash"
    except:
        return "models/gemini-1.5-flash"

def run_analysis(frames):
    try:
        model_name = get_working_model()
        model = genai.GenerativeModel(model_name)

        prompt = "נתח את שפת הגוף בתמונות אלו. החזר ציון SCORE: [0-100] וניתוח ANALYSIS: [טקסט בעברית]."
        response = model.generate_content([prompt] + frames)

        return response.text if response else "לא התקבלה תשובה."
    except Exception as e:
        return f"שגיאת API: {str(e)}"

st.title("Rhetor-AI-ca - פתרון סופי")

video_file = st.file_uploader("העלי וידאו לבדיקה", type=['mp4', 'mov'])

if video_file:
    st.video(video_file)
    if st.button("🚀 הרץ ניתוח סופי"):
        with st.spinner("מנתח..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tfile:
                tfile.write(video_file.read())
                temp_path = tfile.name

            cap = cv2.VideoCapture(temp_path)
            ret, frame = cap.read()
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # שליחת פריים אחד לבדיקה מהירה
                result = run_analysis([Image.fromarray(frame_rgb)])
                st.markdown("### תוצאות הניתוח:")
                st.write(result)

            cap.release()
            if os.path.exists(temp_path): os.remove(temp_path)