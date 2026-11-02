FROM python:3.12.11-slim-bookworm

# tcpdump and iproute2 are here for the same reason as in the Modbus lab: the
# point of a protocol lab is to look at the wire, and a capture needs no extra
# tooling on the host.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 tcpdump \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /lab

# No third-party package. The codec is the deliverable, so the bytes in the
# image are the bytes in the repository.
COPY bacnet_codec.py /lab/bacnet_codec.py
COPY bacnet_device.py /lab/bacnet_device.py
COPY ahu.py /lab/ahu.py
COPY supervisor.py /lab/supervisor.py

CMD ["sleep", "infinity"]
