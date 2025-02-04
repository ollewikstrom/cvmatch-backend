import os
import sys
import logging

# Number of worker processes (adjust based on CPU cores)
workers = 4

# Use the Uvicorn worker class
worker_class = "uvicorn.workers.UvicornWorker"

# Server bind address and port
bind = "0.0.0.0:8022"

# Log level
loglevel = "info"

# Timeout for workers (default is 30 seconds)
timeout = 60

# Ensure logs are flushed immediately
os.environ["PYTHONUNBUFFERED"] = "1"
sys.stdout = open(sys.stdout.fileno(), mode="w", buffering=1)  # Line buffering
sys.stderr = open(sys.stderr.fileno(), mode="w", buffering=1)  # Line buffering

# Gunicorn logging settings
accesslog = "-"  # Log access logs to stdout
errorlog = "-"
capture_output = True  # Redirect stdout/stderr to Gunicorn logs

# (Optional) Auto-reload for development
reload = True  # Uncomment for debugging
