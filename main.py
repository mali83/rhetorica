import os
import re
import json
import time
import shutil
import smtplib
from datetime import timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import google.auth
from google.auth import impersonated_credentials
from google.cloud import storage
from google import genai
from google.genai import types

# 1. הגדרת אפליקציית FastAPI
app = FastAPI(title="Rhetorica AI Engine - Enterprise Full Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. הגדרות ענן ואחסון Google Cloud
BUCKET_NAME = "rhetorica-videos-teacherai"
SERVICE_ACCOUNT_EMAIL = "470821196040-compute@developer.gserviceaccount.com"

API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6IETgRBkFmmrymgWGXUcr9EDdXo5mIkne70LvijJslidg")
client = genai.Client(api_key=API_KEY)

# 3. הגדרות שרת דואר לשליחת PDF
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "malidavid83@gmail.com"
SMTP_PASSWORD = "הסיסמה_בת_16_האותיות_ללא_רווחים"

# פונקציית עזר לפענוח JSON עמיד
def extract_and_parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r'(\{.*\})', cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise

@app.get("/")
async def home():
    return FileResponse("index.html")

# מודלים של בקשות (Pydantic Models)
class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str = "video/mp4"

class AnalyzeRequest(BaseModel):
    blob_name: str
    audience: str = "בוגרים ומורים"
    gender: str = "male"
    language: str = "he"

# 4. נתיב להפקת כתובת העלאה חתומה ישירות ל-Google Cloud Storage
@app.post("/get-upload-url")
def get_upload_url(req: UploadUrlRequest):
    try:
        source_credentials, _ = google.auth.default()
        target_credentials = impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=SERVICE_ACCOUNT_EMAIL,
            target_scopes=["[https://www.googleapis.com/auth/devstorage.read_write](https://www.googleapis.com/auth/devstorage.read_write)"],
            lifetime=1200
        )

        storage_client = storage.Client(credentials=target_credentials)
        bucket = storage_client.bucket(BUCKET_NAME)

        # יצירת שם קובץ בטוח וייחודי
        safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', req.filename)
        blob_name = f"uploads/{int(time.time())}_{safe_filename}"
        blob = bucket.blob(blob_name)

        # הפקת קישור חתום בתוקף ל-15 דקות
        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15),
            method="PUT",
            content_type=req.content_type,
            credentials=target_credentials,
        )

        return {"upload_url": upload_url, "blob_name": blob_name}

    except Exception as e:
        print(f"[SIGN URL ERROR] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate upload URL: {str(e)}")

# 5. נתיב ניתוח וידאו מתוך Google Cloud Storage
@app.post("/analyze")
async def analyze_video(req: AnalyzeRequest):
    temp_local_path = None
    video_file = None
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(req.blob_name)

    try:
        if not blob.exists():
            raise Exception("קובץ הווידאו לא נמצא במאגר האחסון.")

        temp_local_path = f"/tmp/{os.path.basename(req.blob_name)}"
        print(f"[INFO] מוריד קובץ מ-GCS לנתיב מקומי: {temp_local_path}...")
        blob.download_to_filename(temp_local_path)

        file_size_mb = os.path.getsize(temp_local_path) / (1024 * 1024)
        print(f"[INFO] קובץ הורד בהצלחה ({file_size_mb:.2f} MB). מעלה ל-Google AI...")

        video_file = client.files.upload(file=temp_local_path)
        print(f"[INFO] הקובץ הועלה לענן ({video_file.name}). ממתין לפענוח המדיה...")

        max_wait_seconds = 600
        waited = 0
        while video_file.state.name == "PROCESSING":
            time.sleep(4)
            waited += 4
            video_file = client.files.get(name=video_file.name)
            print(f"[INFO] מעבד וידאו ב-AI... ({waited} שניות)")

            if waited >= max_wait_seconds:
                raise Exception("זמן פענוח הווידאו חרג מהתקרה המותרת.")

        if video_file.state.name == "FAILED":
            raise Exception("פענוח קובץ הווידאו נכשל בשרתי ה-AI.")

        print("[INFO] פענוח הווידאו הסתיים. מריץ ניתוח מומחה...")

        if req.language == "en":
            gender_term = "Speaker (Male)" if req.gender == "male" else "Speaker (Female)"
            pronoun_directive = "Address the speaker directly in professional English."
            lang_instruction = "Return ALL textual feedback, strengths, gaps, timeline descriptions, and the golden tip strictly in English."
            tag_label = "Optimal Delivery"
        else:
            gender_term = "מרצה (זכר)" if req.gender == "male" else "מרצה (נקבה)"
            pronoun_directive = "פנה אל המרצה בלשון זכר בלבד (הקפד, עמוד, שים לב)." if req.gender == "male" else "פני אל המרצה בלשון נקבה בלבד (הקפידי, עמדי, שימי לב)."
            lang_instruction = "החזר את כל הניתוח, הטקסטים, נקודות החוזק, התורפה ויומן האירועים בעברית רהוטה ומדויקת."
            tag_label = "סגנון הוראה"

        prompt = f"""
You are an international expert in rhetoric, body language, public speaking, and pedagogy.
Analyze the attached video from beginning to end.

Calibration Details:
- Target Audience:
{req.audience}
- Speaker Gender:
{gender_term}
- Tone / Directives:
{pronoun_directive}
- Language:
{lang_instruction}

CRITICAL JSON RULES:
- Return strictly VALID JSON without syntax errors.
- NEVER use unescaped double quotes inside text values (use single quotes ' like this instead).
- Ensure all commas and brackets are perfectly formatted.

Required JSON Structure:
{{
    "score": 87.4,
    "duration": "משך הווידאו",
    "presenceTag": "{tag_label}",
    "presenceTagClass": "text-blue-600 bg-blue-50",
    "wpm": 142,
    "wpmPercent": 75,
    "goldenTip": "טיפ זהב ממוקד",
    "pitchBars": [
        {{"h": "50%", "hz": "160Hz", "label": "פתיחה"}},
        {{"h": "85%", "hz": "240Hz", "label": "אתגר"}},
        {{"h": "45%", "hz": "140Hz", "label": "גוף השיעור"}},
        {{"h": "70%", "hz": "210Hz", "label": "דיון"}},
        {{"h": "55%", "hz": "170Hz", "label": "מענה"}},
        {{"h": "90%", "hz": "250Hz", "label": "סיכום"}}
    ],
    "strengths": [
        {{"title": "כותרת חוזק", "desc": "תיאור מה שנצפה בפועל", "metric": "מדד", "icon": "👁️"}}
    ],
    "gaps": [
        {{"title": "נקודת תורפה", "points": "-4.2 נק'", "desc": "מה קרה בסרטון", "fix": "איך לתקן"}}
    ],
    "timeline": [
        {{"time": "02:15", "title": "כותרת אירוע", "desc": "תיאור מה קרה בשלב זה"}}
    ]
}}
"""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[video_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        result_json = extract_and_parse_json(response.text)
        print("[INFO] הניתוח הושלם בהצלחה, שולח נתונים לדפדפן...")
        return result_json

    except Exception as e:
        print(f"[ERROR] תקלה במהלך העיבוד: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # ניקוי מקומי (ZDR)
        if temp_local_path and os.path.exists(temp_local_path):
            try:
                os.remove(temp_local_path)
                print(f"[ZDR] קובץ מקומי {temp_local_path} נמחק בהצלחה.")
            except Exception as err:
                print(f"[ZDR ERROR] {err}")

        # ניקוי משרתי Gemini
        if video_file:
            try:
                client.files.delete(name=video_file.name)
                print(f"[ZDR] קובץ הענן של Gemini ({video_file.name}) הושמד בהצלחה.")
            except Exception as err:
                print(f"[ZDR ERROR] {err}")

        # ניקוי מ-Google Cloud Storage למניעת צבירת קבצים ועלויות
        try:
            if blob.exists():
                blob.delete()
                print(f"[ZDR] קובץ ה-Storage {req.blob_name} נמחק בהצלחה מ-GCS.")
        except Exception as err:
            print(f"[ZDR ERROR GCS] {err}")

# 6. נתיב שליחת דוח PDF למייל
@app.post("/send-email")
async def send_report_email(
    email: str = Form(...),
    pdf_file: UploadFile = File(...),
    language: str = Form("he")
):
    try:
        is_en = language == "en"

        subject = "Rhetorica AI - Official Observation Report (Attached PDF)" if is_en else "Rhetorica AI - דוח תצפית פדגוגי רשמי (קובץ PDF מצורף)"

        body_text = (
            "Hello,\n\nPlease find attached your official Rhetorica AI Pedagogical & Rhetoric Observation Report.\n\nBest regards,\nRhetorica AI Engine"
            if is_en else
            "שלום,\n\nמצורף דוח התצפית הפדגוגי והרטורי המלא שלך כקובץ PDF.\n\nבברכה,\nצוות Rhetorica AI"
        )

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"Rhetorica AI <{SMTP_USER}>"
        msg["To"] = email

        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        pdf_bytes = await pdf_file.read()
        pdf_attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        pdf_attachment.add_header('Content-Disposition', 'attachment', filename="Rhetorica_Observation_Report.pdf")
        msg.attach(pdf_attachment)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, email, msg.as_string())

        return {"status": "success", "message": "Email with PDF attached sent successfully"}

    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email with PDF: {str(e)}")

# 7. נתיב השוואת התקדמות מול דוח עבר
@app.post("/compare-progress")
async def compare_progress(
    past_pdf: UploadFile = File(...),
    current_data: str = Form(...),
    language: str = Form("he")
):
    temp_pdf = None
    cloud_pdf = None

    try:
        ext = os.path.splitext(past_pdf.filename)[1].lower() or ".pdf"
        temp_pdf = f"temp_past_{int(time.time())}{ext}"

        with open(temp_pdf, "wb") as buffer:
            shutil.copyfileobj(past_pdf.file, buffer)

        cloud_pdf = client.files.upload(file=temp_pdf)

        while cloud_pdf.state.name == "PROCESSING":
            time.sleep(2)
            cloud_pdf = client.files.get(name=cloud_pdf.name)

        is_en = language == "en"
        lang_directive = "Return all comparative analysis strictly in English." if is_en else "החזר את כל דוח ההשוואה, המגמות וההמלצות בעברית רהוטה ומקצועית בלבד."

        prompt = f"""
You are an elite Pedagogical Supervisor and Communication Coach.

Task:
Analyze the attached previous PDF observation report and compare it with the teacher's current session data provided below.

Current Session Data:
{current_data}

Instructions:
1. Extract previous score, strengths, and weaknesses from the attached PDF.
2. Compare past vs current performance to identify concrete trajectory.
3. Identify 'Resolved Gaps' (weaknesses from the past report that the speaker successfully fixed).
4. Identify 'Persistent Gaps' (vulnerabilities that still recur and need further coaching).
5. Calculate the growth delta score (e.g., +5.2 pts).
6. Language: {lang_directive}

Return strict JSON only (no markdown, no backticks):
{{
    "pastScore": 82.0,
    "currentScore": 88.4,
    "deltaScore": "+6.4",
    "growthStatus": "שיפור משמעותי בנוכחות הפדגוגית",
    "growthSummary": "סקירה מקיפה של התפתחות המרצה לאורך זמן...",
    "resolvedGaps": [
        {{"title": "הפחתת תנועות עצבניות", "desc": "ביחס לדוח הקודם, נצפתה יציבה שקטה וסמכותית יותר."}}
    ],
    "persistentGaps": [
        {{"title": "גיוון אינטונציה", "desc": "המונוטוניות בשלבי ההסבר המרכזיים עדיין קיימת ודורשת תרגול מכוון."}}
    ],
    "coachingTip": "המלצה פדגוגית ממוקדת לקראת השיעור הבא"
}}
"""

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[cloud_pdf, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        result_json = extract_and_parse_json(response.text)
        return result_json

    except Exception as e:
        print(f"[COMPARE ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if temp_pdf and os.path.exists(temp_pdf):
            try:
                os.remove(temp_pdf)
            except Exception:
                pass
        if cloud_pdf:
            try:
                client.files.delete(name=cloud_pdf.name)
            except Exception:
                pass