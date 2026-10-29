FROM docker.io/metacubex/mihomo:v1.19.33 AS mihomo
FROM ghcr.io/tbphp/gpt-load:2.0.0-rc.44

USER root
RUN apk add --no-cache python3 curl
COPY --from=mihomo /mihomo /usr/local/bin/mihomo
COPY start.py /opt/taiwan/start.py
ENV HOST=0.0.0.0 PORT=10000 DATA_DIR=/tmp/gpt-load PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 10000
ENTRYPOINT ["python3", "/opt/taiwan/start.py"]
