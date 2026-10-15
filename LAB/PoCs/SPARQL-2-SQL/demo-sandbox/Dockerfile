FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ddl ./ddl
COPY seed_duckdb.py ui.py queries.py ./
RUN python seed_duckdb.py /app/fiben_demo.duckdb
ENV COMPILER_URL=http://sparql2sql-service:8000 DUCKDB_PATH=/app/fiben_demo.duckdb
EXPOSE 8501
CMD ["streamlit", "run", "ui.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.gatherUsageStats=false"]
