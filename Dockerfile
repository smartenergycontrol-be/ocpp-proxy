ARG BUILD_FROM=homeassistant/python3:3.9
FROM ${BUILD_FROM}

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application source
WORKDIR /app
COPY src/ev_charger_proxy /app/ev_charger_proxy

# Expose WebSocket port
EXPOSE 9000

# Run the proxy server
CMD ["python3", "-m", "ev_charger_proxy.main"]
