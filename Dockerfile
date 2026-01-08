FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install Playwright browsers
RUN playwright install chromium

EXPOSE 8501

# Use Python launcher that reads PORT env var directly (no shell expansion needed)
CMD ["python", "run.py"]
