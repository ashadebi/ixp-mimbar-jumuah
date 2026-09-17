FROM python:3.12-slim
WORKDIR /app
COPY app /app/app
COPY oui /app/oui
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data API_PORT=5514 SYSLOG_UDP_PORT=514 SYSLOG_TCP_PORT=514
VOLUME ["/data"]
EXPOSE 514/udp 514/tcp 5514/tcp
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5514/health',timeout=2)"
CMD ["python","-m","app.server"]
