import multiprocessing

# Gunicorn configuration for production
bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 30
keepalive = 5
graceful_timeout = 30

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process management
preload_app = True
daemon = False
pidfile = "/tmp/gunicorn.pid"
tmp_upload_dir = "/tmp"

# Security
limit_request_fields = 100
limit_request_field_size = 8190
limit_request_line = 4094

# Worker recycling
worker_max_tasks_per_child = 100

# SSL (configure if needed)
# keyfile = "/path/to/key.pem"
# certfile = "/path/to/cert.pem"