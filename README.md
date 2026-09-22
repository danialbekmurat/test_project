# BI Care

Веб-приложение на Python и Streamlit для обращений жителей жилого комплекса. Загрузите фотографию проблемы и короткое описание — Gemini определит категорию, срочность, ответственную службу и подготовит текст обращения на русском языке.

Поддерживаются JPG, PNG, WEBP и фотографии с iPhone в HEIC/HEIF. Блок «Заявка отправлена» — демонстрационный: реальная заявка не создаётся.

## Запуск

Нужен Python 3.10 или новее.

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
~~~

Откройте файл .env и замените значение GEMINI_API_KEY на свой ключ Gemini API. После запуска приложение будет доступно по адресу http://localhost:8501.

Файл .env добавлен в .gitignore и не попадёт в репозиторий.
