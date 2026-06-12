FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cache-friendly).
COPY provisioning/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared gRPC core — placed at /app/ so it is importable as
# 'chirpstack_client' with PYTHONPATH=/app. Also kept under scripts/
# to match the development layout (provisioning.py probes that path).
COPY scripts/chirpstack_client.py /app/chirpstack_client.py
COPY scripts/chirpstack_client.py /app/scripts/chirpstack_client.py

# Copy provisioning app.
COPY provisioning/app.py /app/app.py
COPY provisioning/provisioning.py /app/provisioning.py
COPY provisioning/validators.py /app/validators.py
COPY provisioning/templates /app/templates
COPY provisioning/static /app/static

ENV PYTHONPATH=/app

EXPOSE 8092

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8092"]
