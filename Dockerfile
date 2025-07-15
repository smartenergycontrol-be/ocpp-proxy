ARG BUILD_FROM=homeassistant/python3:3.11
FROM ${BUILD_FROM}

# Install Poetry
RUN pip install --no-cache-dir poetry

# Configure Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copy dependency files
WORKDIR /app
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry install --only=main && rm -rf $POETRY_CACHE_DIR

# Copy application source
COPY src/ocpp_proxy /app/ocpp_proxy

# Expose WebSocket port
EXPOSE 9000

# Run the proxy server
CMD ["poetry", "run", "python3", "-m", "ocpp_proxy.main"]
