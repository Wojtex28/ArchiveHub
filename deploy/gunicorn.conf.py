# Konfiguracja serwera aplikacji. Kilka procesów z wątkami wystarcza
# z dużym zapasem dla rodzinnego archiwum.
bind = "0.0.0.0:8000"
workers = 2
threads = 4
worker_class = "gthread"
timeout = 120
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
loglevel = "info"
forwarded_allow_ips = "*"
