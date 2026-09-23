"""BI Care — обработка обращений жителей через Gemini."""

import json
import os
from html import escape
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener


load_dotenv()
register_heif_opener()

st.set_page_config(page_title="BI Care", page_icon="BI", layout="centered")

REACTION_TIMES = {
    "низкая": "до 3 рабочих дней",
    "средняя": "в течение 24 часов",
    "высокая": "в течение 2 часов",
}
DATA_DIR = Path("data")
PHOTO_DIR = DATA_DIR / "photos"


def normalize_image(uploaded_file):
    """Открывает в том числе HEIC/HEIF и сжимает фото для Gemini."""
    uploaded_file.seek(0)
    image = ImageOps.exif_transpose(Image.open(uploaded_file)).convert("RGB")
    image.thumbnail((1600, 1600))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue(), "image/jpeg"


def estimate_request(description: str) -> dict[str, str]:
    """Рабочий резервный сценарий, когда ключ Gemini ещё не настроен."""
    text = description.lower()
    if any(word in text for word in ("люк", "яма", "утеч", "провал", "искр", "газ")):
        category, urgency, service = "Опасность на территории", "высокая", "аварийная служба"
    elif any(word in text for word in ("мусор", "гряз", "урна", "подъезд", "уборк")):
        category, urgency, service = "Уборка территории", "средняя", "клининговая компания"
    elif any(word in text for word in ("дорог", "асфальт", "бордюр", "тротуар")):
        category, urgency, service = "Дорожное покрытие", "средняя", "дорожная служба"
    else:
        category, urgency, service = "Обслуживание жилого комплекса", "средняя", "управляющая компания"
    appeal = (
        f"Прошу обратить внимание на проблему: {description.strip() or category.lower()}. "
        "Прошу организовать проверку и сообщить о сроках устранения. Спасибо."
    )
    return {"category": category, "urgency": urgency, "service": service, "appeal_text": appeal}


def save_request(image_bytes: bytes, description: str, result: dict[str, str], mode: str) -> str:
    """Регистрирует обращение локально, не теряя фото и результат анализа."""
    request_id = uuid4().hex[:8].upper()
    DATA_DIR.mkdir(exist_ok=True)
    PHOTO_DIR.mkdir(exist_ok=True)
    photo_path = PHOTO_DIR / f"{request_id}.jpg"
    photo_path.write_bytes(image_bytes)
    record = {
        "id": request_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "photo": str(photo_path),
        "analysis_mode": mode,
        **result,
    }
    with (DATA_DIR / "requests.jsonl").open("a", encoding="utf-8") as requests_file:
        requests_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return request_id


def analyze_request(image_bytes: bytes, mime_type: str, description: str) -> dict[str, str]:
    """Запрашивает у Gemini строго структурированный результат анализа."""
    api_key = os.getenv("GEMINI_API_KEY")
    prompt = f"""
Ты — диспетчер обращений жителей жилого комплекса. Проанализируй фотографию и описание.
Описание жителя: {description or "Описание не добавлено"}

Верни только JSON по этой схеме:
{{
  "category": "краткая категория проблемы на русском",
  "urgency": "низкая | средняя | высокая",
  "service": "клининговая компания | аварийная служба | управляющая компания | дорожная служба",
  "appeal_text": "готовый вежливый текст обращения на русском"
}}

Оценивай срочность реалистично. Если есть риск травмы, утечка, открытый люк,
провал или опасная неисправность — выбирай высокую срочность.
"""
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "category": {"type": "STRING"},
                    "urgency": {"type": "STRING", "enum": ["низкая", "средняя", "высокая"]},
                    "service": {"type": "STRING"},
                    "appeal_text": {"type": "STRING"},
                },
                "required": ["category", "urgency", "service", "appeal_text"],
            },
        ),
    )
    result = json.loads(response.text)
    return {key: str(result[key]).strip() for key in ("category", "urgency", "service", "appeal_text")}


st.markdown(
    """
    <style>
      :root {--bi-blue:#3155e7; --bi-navy:#263a8e; --bi-ink:#182137; --bi-muted:#657086;}
      .stApp {background:#f7f8fc; color:var(--bi-ink);}
      .block-container {max-width:930px; padding-top:1rem; padding-bottom:4rem;}
      .top-line {height:8px; background:#263943; position:fixed; top:0; left:0; right:0; z-index:999999;}
      .nav {display:flex; align-items:center; justify-content:space-between; padding:1rem 0 1.3rem;
            border-bottom:1px solid #dfe3eb; color:var(--bi-ink); margin-bottom:2.2rem;}
      .brand {display:flex; align-items:center; gap:.55rem; font-size:1.42rem; font-weight:750; color:var(--bi-navy);}
      .brand-mark {display:inline-flex; align-items:center; justify-content:center; width:35px; height:35px;
                   border-radius:50%; background:var(--bi-navy); color:white; font-size:.9rem; letter-spacing:-1px;}
      .nav-note {font-size:.92rem; color:var(--bi-muted);}
      .hero {padding:2.35rem 2.5rem; border-radius:22px; color:#fff;
             background:linear-gradient(118deg,#253b98 0%,#3155e7 64%,#4169ed 100%);
             margin-bottom:1.5rem; box-shadow:0 14px 32px rgba(40,70,180,.2);}
      .hero h1 {margin:0; font-size:2.35rem; letter-spacing:-.04em;}
      .hero p {margin:.65rem 0 0; opacity:.9; font-size:1.05rem; max-width:580px;}
      .form-hint {font-size:.94rem; color:var(--bi-muted); margin:.35rem 0 1.2rem;}
      [data-testid="stFileUploader"] {background:#fff; border-radius:16px; padding:.65rem .9rem; border:1px solid #dbe0ed;}
      [data-testid="stFileUploader"] section {border:1.5px dashed #8094ec !important; background:#f8f9ff !important; border-radius:12px !important;}
      [data-testid="stFileUploader"] button, .stButton button {border-radius:10px !important;}
      .stButton button[kind="primary"], [data-testid="stFormSubmitButton"] button {background:var(--bi-blue) !important; border-color:var(--bi-blue) !important; font-weight:600;}
      .preview-label {color:var(--bi-muted); font-size:.86rem; margin:.85rem 0 .3rem;}
      .result-card {background:#fff; border:1px solid #e0e4ef; border-radius:16px; padding:1.15rem 1.25rem; min-height:110px; box-shadow:0 5px 15px rgba(32,47,93,.04);}
      .card-label {color:var(--bi-muted); font-size:.76rem; font-weight:650; letter-spacing:.06em; margin-bottom:.4rem;}
      .card-value {font-size:1.08rem; font-weight:650; color:var(--bi-ink); line-height:1.35;}
      .sent {border-radius:16px; padding:1.2rem 1.4rem; margin-top:1.5rem; background:#eef2ff; border:1px solid #c7d1ff; color:#202f76;}
      @media (max-width:640px) {.hero {padding:1.7rem 1.4rem;} .hero h1 {font-size:1.9rem;} .nav-note {display:none;}}
    </style>
    <div class="top-line"></div>
    <div class="nav"><div class="brand"><span class="brand-mark">BI</span> BI GROUP</div><div class="nav-note">Сервис для жителей</div></div>
    <div class="hero"><h1>BI Care</h1><p>Сообщите о проблеме в вашем жилом комплексе — поможем направить обращение нужной службе.</p></div>
    """,
    unsafe_allow_html=True,
)

with st.form("complaint_form"):
    st.markdown('<div class="form-hint">Прикрепите фото и кратко опишите, что произошло.</div>', unsafe_allow_html=True)
    if os.getenv("GEMINI_API_KEY"):
        st.caption("✦ Gemini подключён: используем анализ фотографии и описания.")
    else:
        st.caption("✦ Режим регистрации: заявка сохранится локально. Для анализа изображения Gemini добавьте ключ в .env.")
    photo = st.file_uploader(
        "Фото проблемы",
        type=None,
        help="Можно выбрать фотографию с любого устройства. JPG, PNG, WEBP, HEIC/HEIF и другие форматы будут проверены после загрузки.",
    )
    if photo:
        st.markdown('<div class="preview-label">Предпросмотр загруженного фото</div>', unsafe_allow_html=True)
        try:
            preview, _ = normalize_image(photo)
            st.image(preview, width=320)
        except (UnidentifiedImageError, OSError):
            st.caption("Файл прикреплён. Предпросмотр недоступен — попробуйте отправить JPG, PNG, WEBP или HEIC/HEIF.")
    description = st.text_area(
        "Коротко опишите проблему",
        placeholder="Например: у второго подъезда переполнена урна",
        max_chars=500,
    )
    submitted = st.form_submit_button("Определить проблему", type="primary", use_container_width=True)

if submitted:
    if not photo:
        st.warning("Пожалуйста, прикрепите фотографию проблемы.")
    else:
        try:
            image_bytes, mime_type = normalize_image(photo)
            if os.getenv("GEMINI_API_KEY"):
                with st.spinner("Анализируем обращение…"):
                    result = analyze_request(image_bytes, mime_type, description)
                mode = "gemini"
            else:
                result = estimate_request(description)
                mode = "local_fallback"
            st.session_state.result = result
            st.session_state.request_id = save_request(image_bytes, description, result, mode)
        except (UnidentifiedImageError, OSError):
            st.error("Не удалось открыть это фото. Выберите JPG, PNG, WEBP или HEIC/HEIF и повторите попытку.")
        except Exception as error:
            st.error(f"Не удалось обработать заявку: {error}")

if result := st.session_state.get("result"):
    st.subheader("Результат анализа")
    columns = st.columns(3)
    for column, label, value in zip(
        columns,
        ("КАТЕГОРИЯ", "СРОЧНОСТЬ", "СЛУЖБА"),
        (result["category"], result["urgency"].capitalize(), result["service"]),
    ):
        with column:
            st.markdown(
                f'<div class="result-card"><div class="card-label">{label}</div><div class="card-value">{escape(value)}</div></div>',
                unsafe_allow_html=True,
            )
    st.markdown("#### Готовый текст обращения")
    st.info(result["appeal_text"], icon="📝")
    reaction_time = REACTION_TIMES.get(result["urgency"].lower(), "в ближайшее время")
    request_id = st.session_state.get("request_id", "—")
    st.markdown(
        f'<div class="sent"><strong>✓ Заявка зарегистрирована № {request_id}</strong><br>Служба: {escape(result["service"])}<br>'
        f'Ориентировочное время реакции: {reaction_time}<br><small>Фото и данные заявки сохранены локально.</small></div>',
        unsafe_allow_html=True,
    )
