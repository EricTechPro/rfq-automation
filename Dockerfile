FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install Playwright browsers
RUN playwright install chromium

# Railway assigns PORT dynamically, default to 8501 for local dev
ENV PORT=8501
EXPOSE $PORT

# Run Streamlit with dynamic port
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
