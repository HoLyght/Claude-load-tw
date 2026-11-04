FROM --platform=$BUILDPLATFORM node:24.18.0-alpine3.24@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS web-builder
WORKDIR /build
RUN corepack enable && corepack install --global pnpm@11.17.0
COPY upstream/web/package.json upstream/web/pnpm-lock.yaml upstream/web/pnpm-workspace.yaml ./web/
RUN pnpm --dir web install --frozen-lockfile
COPY upstream/internal/webui/page_routes.json upstream/internal/webui/modern_page_routes.json ./internal/webui/
COPY upstream/web ./web
RUN pnpm --dir web run build

FROM --platform=$BUILDPLATFORM golang:1.27.3-alpine3.24@sha256:f2c872bcee949b7be9c490efd02b48a8a2fbf947cdf533f1c58525ec9d8170fd AS go-builder
ARG TARGETOS
ARG TARGETARCH
ENV CGO_ENABLED=0 GOPROXY="https://proxy.golang.org|direct"
WORKDIR /build
COPY upstream/go.mod upstream/go.sum ./
COPY upstream/third_party/cpaembedded/go.mod upstream/third_party/cpaembedded/go.sum ./third_party/cpaembedded/
RUN go mod download
COPY upstream/*.go ./
COPY upstream/internal ./internal
COPY upstream/third_party/cpaembedded ./third_party/cpaembedded
COPY --from=web-builder /build/internal/webui/dist ./internal/webui/dist
RUN go test ./internal/execution/cpa ./internal/subscription/providers/codex
RUN GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build \
    -ldflags "-s -w -X gpt-load/internal/platform/version.Version=2.0.0-rc.59+desktop-count.1" \
    -o gpt-load

FROM docker.io/metacubex/mihomo:v1.19.33 AS mihomo
FROM ghcr.io/tbphp/gpt-load:2.0.0-rc.59

USER root
RUN apk add --no-cache python3 curl
COPY --from=go-builder /build/gpt-load /app/gpt-load
COPY --from=mihomo /mihomo /usr/local/bin/mihomo
COPY start.py /opt/taiwan/start.py
ENV HOST=0.0.0.0 PORT=10000 DATA_DIR=/tmp/gpt-load PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 10000
ENTRYPOINT ["python3", "/opt/taiwan/start.py"]
