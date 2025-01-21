# gunicorn.conf.py

# Number of worker processes (adjust based on your CPU cores)
workers = 4

# Use the Uvicorn worker class
worker_class = "uvicorn.workers.UvicornWorker"

# Server bind address and port
bind = "0.0.0.0:8000"

# Log level
loglevel = "info"

# Timeout for workers (default is 30 seconds)
timeout = 60
