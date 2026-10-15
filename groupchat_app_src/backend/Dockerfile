FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /workspace/groupchat_app_src/backend
COPY backend/requirements.lock.txt ./requirements.lock.txt
RUN python -m pip install --no-cache-dir -r requirements.lock.txt
COPY backend/*.py ./
COPY frontend/ ../frontend/
COPY knowledge/ ../knowledge/
EXPOSE 8000
CMD ["sh", "-c", "python bootstrap_library.py && exec python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload --reload-dir /workspace/groupchat_app_src/backend --reload-exclude '.venv/*'"]
