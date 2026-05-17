FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Default: run the one-shot daily job
ENV RUN_ONCE=true
ENV PYTHONUNBUFFERED=1

CMD ["python", "pixel_square_daily.py"]
