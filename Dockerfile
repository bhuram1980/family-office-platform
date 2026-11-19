FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FLASK_APP=app:create_app
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "flask db upgrade && gunicorn -w ${WEB_CONCURRENCY:-3} -b 0.0.0.0:${PORT:-8000} wsgi:app"]
