FROM node:22-bookworm-slim AS mermaid-cli

ARG MERMAID_CLI_VERSION=11.16.0
ENV PUPPETEER_SKIP_DOWNLOAD=true

RUN npm install --global --prefix /opt/mermaid-cli \
        "@mermaid-js/mermaid-cli@${MERMAID_CLI_VERSION}"


FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/
COPY --from=mermaid-cli /usr/local/bin/node /usr/local/bin/node
COPY --from=mermaid-cli /usr/local/LICENSE /usr/share/licenses/node/LICENSE
COPY --from=mermaid-cli /opt/mermaid-cli /opt/mermaid-cli

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        fontconfig \
        fonts-dejavu-core \
        fonts-liberation \
        fonts-noto-color-emoji \
        graphviz \
        openjdk-17-jre-headless \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md LICENSE NOTICE THIRD_PARTY_NOTICES.md ./
RUN uv sync --locked --no-install-project --no-dev

COPY app ./app
COPY deps/plantuml/plantuml*.jar /app/plantuml/plantuml.jar
COPY deps/plantuml/license*.txt /app/plantuml/
COPY deps/mermaid/puppeteer-config.json /app/mermaid/puppeteer-config.json
COPY deps/mermaid/mermaid-config.json /app/mermaid/mermaid-config.json
COPY deps/uv/LICENSE-MIT /usr/share/licenses/uv/LICENSE-MIT
RUN uv sync --locked --no-dev \
    && python -m app.manifest \
    && groupadd --system pipelign \
    && useradd --system --gid pipelign --create-home pipelign

ENV PLANTUML_JAR_PATH=/app/plantuml/plantuml.jar \
    MERMAID_CMD=/opt/mermaid-cli/bin/mmdc \
    MERMAID_PUPPETEER_CONFIG_PATH=/app/mermaid/puppeteer-config.json

USER pipelign

EXPOSE 8080

CMD ["pipelign-diagrams"]


FROM runtime AS test

USER root
RUN uv sync --locked
COPY tests ./tests
USER pipelign

CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]


FROM runtime AS production
