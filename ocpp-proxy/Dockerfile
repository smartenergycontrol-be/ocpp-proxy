# Home Assistant add-on Dockerfile
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM ${BUILD_FROM}

# Set shell for add-on compatibility
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies and Python packages
RUN \
    apk add --no-cache \
        python3 \
        py3-pip \
        py3-setuptools \
        py3-wheel \
    && apk add --no-cache --virtual .build-dependencies \
        gcc \
        musl-dev \
        python3-dev

# Copy application source to /app
WORKDIR /app
COPY src/ ./src/
COPY pyproject.toml poetry.lock* ./

# Install Python dependencies with break-system-packages flag
RUN \
    pip3 install --break-system-packages \
        "ocpp>=2.0.0" \
        "aiohttp>=3.9.0" \
        "websockets>=12.0" \
        "PyYAML>=6.0.0" \
    && apk del .build-dependencies

# Create s6-overlay service script for Home Assistant add-on
RUN mkdir -p /etc/services.d/ocpp-proxy
RUN echo '#!/usr/bin/with-contenv bashio' > /etc/services.d/ocpp-proxy/run && \
    echo 'bashio::log.info "Starting OCPP Proxy..."' >> /etc/services.d/ocpp-proxy/run && \
    echo 'cd /app' >> /etc/services.d/ocpp-proxy/run && \
    echo 'exec python3 -m ocpp_proxy.main' >> /etc/services.d/ocpp-proxy/run && \
    chmod a+x /etc/services.d/ocpp-proxy/run

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
