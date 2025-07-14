ARG BUILD_FROM=homeassistant/python3:3.9
FROM ${BUILD_FROM}

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application source
WORKDIR /app
COPY src/ocpp_proxy /app/ocpp_proxy

# Expose WebSocket port
EXPOSE 9000

# Run the proxy server
CMD ["python3", "-m", "ocpp_proxy.main"]
