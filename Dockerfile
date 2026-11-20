# Written by blitz.cloud for this project. It is yours now: blitz.cloud
# builds from it as it is, and you can change it like any other file.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HOME=/app
WORKDIR /app
RUN chown 1000:1000 /app
COPY --chown=1000:1000 . .
RUN pip install --no-cache-dir -r requirements.txt
ENV PORT=8080
USER 1000:1000
CMD ["sh", "-c", "exec python main.py"]
