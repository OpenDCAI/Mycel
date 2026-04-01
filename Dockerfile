FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies (cached layer before source copy)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Install backend-specific deps not in pyproject.toml
COPY backend/web/requirements.txt ./backend/web/requirements.txt
RUN uv pip install -r backend/web/requirements.txt

# Copy source and install project
COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8001

CMD ["uvicorn", "backend.web.main:app", "--host", "0.0.0.0", "--port", "8001"]
