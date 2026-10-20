FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /uvx /bin/
WORKDIR /service
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/service/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable
RUN useradd --create-home --uid 10001 mediflow
USER mediflow
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "mediflow.main:app", "--host", "0.0.0.0", "--port", "8000"]
