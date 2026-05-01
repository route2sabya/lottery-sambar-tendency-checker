FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App + data pipeline scripts
COPY app.py scorer.py update_data.py scrape_history.py parse_pdfs.py ./
COPY templates/ templates/
COPY static/ static/

# Baked-in historical data (PDFs excluded — only the parsed CSV + index)
COPY input_history/results.csv input_history/results.csv
COPY input_history/index.csv   input_history/index.csv

# Directory for newly downloaded PDFs (created at runtime by update_data.py)
RUN mkdir -p input_history/pdfs

EXPOSE 8080

# 1 worker: scorer is a module-level singleton.
# 120s timeout covers the cold-start CSV load and the first-ever update run.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120", "app:app"]
