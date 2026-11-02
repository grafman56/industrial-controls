FROM python:3.12.11-slim-bookworm

# No third party package is installed. The poller speaks Modbus/TCP and the
# InfluxDB write API with the standard library only, so the image has nothing
# to drift.
WORKDIR /app
COPY poller.py /app/poller.py

CMD ["python", "/app/poller.py"]
