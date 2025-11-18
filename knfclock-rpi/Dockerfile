FROM python:3.13.7-slim

WORKDIR app


# Dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir     \
    "requests==2.32.5"              \
    "astral==3.2"                   \
    "RPi.GPIO==0.7.1"               \
    "pyserial==3.5"
    

# Project files
COPY . .

CMD ["python3", "-u", "main.py"]
