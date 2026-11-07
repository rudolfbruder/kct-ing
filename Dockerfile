# One image for the API and for JupyterLab. See README: "Run with Docker".
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt jupyterlab==4.4.10 pandas==2.3.3

COPY . .

EXPOSE 8000 8888

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
