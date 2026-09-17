FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLCONFIGDIR=/tmp/sonarnet-matplotlib

RUN useradd --create-home --uid 1000 appuser
WORKDIR /home/appuser/app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser assets/ ./assets/
COPY --chown=appuser:appuser .streamlit/config.toml ./.streamlit/config.toml
USER appuser
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/_stcore/health', timeout=3)"
CMD ["python", "-m", "streamlit", "run", "scripts/demo_app.py", "--server.address=0.0.0.0", "--server.port=7860", "--server.headless=true", "--server.fileWatcherType=none"]
