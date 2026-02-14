FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Install OCR and PDF rendering dependencies
RUN apt-get update && apt-get install -y tesseract-ocr poppler-utils && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install Playwright browsers
RUN playwright install chromium

EXPOSE 8000

# Launches FastAPI via uvicorn, reading PORT from Railway env var
CMD ["python", "run.py"]
