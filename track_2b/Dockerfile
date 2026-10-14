FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1 MPLBACKEND=Agg MPLCONFIGDIR=/tmp/mpl
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY data ./data
ENTRYPOINT ["python", "-m", "concordance"]
CMD ["--llm-mode", "replay", "demo", "--max-articles", "60", "--max-per-type", "12"]
