FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn gliner
WORKDIR /app
COPY server.py .
RUN useradd -r neruser
USER neruser
EXPOSE 8091
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8091"]
