FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY . .

# Install dependencies from pyproject.toml
RUN uv sync --frozen || uv sync

# Cloud Run expects PORT
ENV PORT=8080

CMD ["uv", "run", "gunicorn", "-b", "0.0.0.0:8080", "app:app", "--timeout", "900"]