# Multi-stage build supporting both standalone and Home Assistant add-on
ARG BUILD_FROM=ghcr.io/hassio-addons/base-python:14.1.0
FROM ${BUILD_FROM}

# Set shell for add-on compatibility
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install Poetry
RUN pip3 install poetry

# Copy dependency files
WORKDIR /app
COPY pyproject.toml poetry.lock* ./

# Install Python dependencies
RUN \
    apk add --no-cache --virtual .build-dependencies \
        gcc \
        musl-dev \
        python3-dev \
    && poetry config virtualenvs.create false \
    && poetry install --only=main --no-dev \
    && apk del .build-dependencies

# Copy application source
COPY src/ /app/src/

# Copy Home Assistant add-on run script (if exists)
COPY .hacs/run.sh /run.sh 2>/dev/null || echo "#!/bin/bash\nexec python3 -m src.ocpp_proxy.main" > /run.sh
RUN chmod a+x /run.sh

# Expose WebSocket port
EXPOSE 9000

# Labels for Home Assistant add-on
LABEL \
    io.hass.name="OCPP Proxy" \
    io.hass.description="Multi-version OCPP proxy for secure EV charger sharing" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    maintainer="OpenChargeHub" \
    org.opencontainers.image.title="OCPP Proxy" \
    org.opencontainers.image.description="Multi-version OCPP proxy for secure EV charger sharing" \
    org.opencontainers.image.vendor="OpenChargeHub" \
    org.opencontainers.image.authors="OpenChargeHub" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://github.com/openchargehub/ocpp-proxy" \
    org.opencontainers.image.source="https://github.com/openchargehub/ocpp-proxy" \
    org.opencontainers.image.documentation="https://github.com/openchargehub/ocpp-proxy" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.revision="${BUILD_REF}" \
    org.opencontainers.image.version="${BUILD_VERSION}"

# Default command (can be overridden by run script)
CMD ["/run.sh"]
