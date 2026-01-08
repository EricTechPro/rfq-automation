FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install Playwright browsers
RUN playwright install chromium

# Copy and make start script executable
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8501

# Run via bash script that properly expands $PORT
CMD ["/bin/bash", "/app/start.sh"]
