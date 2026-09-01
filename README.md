# pipelign-diagrams

`pipelign-diagrams` is a FastAPI service for validating and rendering diagrams on
the server. It exposes one API for two first-class source languages:

| Language | SVG | PNG | ASCII |
| --- | --- | --- | --- |
| `plantuml` | Yes | Yes | Yes |
| `mermaid` | Yes | Yes | No |

PlantUML is rendered with the bundled official JAR. Mermaid is rendered with the
official [`@mermaid-js/mermaid-cli`](https://github.com/mermaid-js/mermaid-cli)
and headless Chromium. The service selects a backend from the request's
`language`; it does not translate between diagram languages.

## API

The Docker default base URL is `http://localhost:8080`.

- `GET /` opens a small browser playground for rendering and validation.
- `GET /health` returns `{"status":"ok"}`.
- `POST /render/svg` returns SVG as `image/svg+xml`.
- `POST /render/png` returns PNG bytes as `image/png`.
- `POST /render/ascii` returns PlantUML ASCII output as `text/plain`.
- `POST /validate` validates source without returning rendered output.

All POST endpoints accept the same body:

```json
{
  "language": "mermaid",
  "source": "flowchart LR\n  Client --> API",
  "options": null
}
```

`language` accepts `plantuml` or `mermaid`. It defaults to `plantuml`, so existing
PlantUML requests that only send `source` remain compatible. `options` is reserved
for future renderer-specific settings.

Render a Mermaid diagram to SVG:

```bash
curl --fail-with-body \
  --header 'Content-Type: application/json' \
  --data '{"language":"mermaid","source":"flowchart LR\n  A --> B"}' \
  http://localhost:8080/render/svg \
  --output diagram.svg
```

Render a PlantUML diagram to PNG using the backward-compatible default language:

```bash
curl --fail-with-body \
  --header 'Content-Type: application/json' \
  --data '{"source":"@startuml\nAlice -> Bob: Hi\n@enduml"}' \
  http://localhost:8080/render/png \
  --output diagram.png
```

### Responses and errors

Invalid diagram source returns HTTP 400 with a `ValidationResult`:

```json
{
  "ok": false,
  "errors": [{"message": "Parse error in Mermaid diagram.", "line": 2}],
  "warnings": []
}
```

An unsupported language value is rejected as request validation with HTTP 422.
An unsupported language/format combination, such as Mermaid ASCII, returns HTTP
400 with the same validation schema. Unexpected renderer failures return HTTP 500
with a stable `InternalErrorResponse`; subprocess commands, paths, stack traces,
and raw renderer output are kept out of the response and written only to server
logs where useful.

Responses include `X-Diagram-Error` for service-level failures. PlantUML failures
also retain the existing `X-PlantUML-Error` header for compatibility.

Interactive OpenAPI documentation is available at `/docs` while the service is
running.

### Browser playground

Open `http://localhost:8080/` after starting the service. The playground lets you
switch between PlantUML and Mermaid, load a sample, validate the source, render
SVG or PNG, preview the result, and download it. PlantUML ASCII rendering is also
available. The page is served by the application and has no additional runtime
or frontend build dependencies.

## Architecture

The HTTP application depends on a small renderer contract rather than on either
CLI directly:

```text
render request
    -> DiagramRenderingService registry
        -> PlantUMLRenderer -> plantuml.jar
        -> MermaidRenderer  -> mmdc -> Chromium
```

`app/renderer.py` defines the backend contract and rendered-output model.
`app/diagram_service.py` owns language registration and dispatch. A new language
can be added by implementing `DiagramRenderer` and registering one instance,
without changing the API routes.

Mermaid CLI does not expose a separate validation-only command, so Mermaid
validation performs an SVG render in an isolated temporary directory and discards
the result. PlantUML continues to use its existing syntax-check mode.

## Docker

The image contains Java, Graphviz, and the bundled PlantUML JAR, plus Node.js,
Mermaid CLI, Chromium, and common fonts. Python dependencies are installed from
`uv.lock`.

Build and run the service:

```bash
docker compose build
docker compose up pipelign-diagrams
```

Run the reload-enabled development service:

```bash
docker compose up pipelign-diagrams-dev
```

Run all unit and renderer integration tests inside the complete image:

```bash
docker compose run --rm pipelign-diagrams-tests
```

The Compose image and containers use the `pipelign-diagrams` name. Production and
development services expose port 8080; run one of them at a time unless you change
the host port.

## Local development with uv

Python dependency management, installation, and execution use
[`uv`](https://docs.astral.sh/uv/). From the repository root:

```bash
uv sync --locked
uv run pipelign-diagrams
```

The server listens on `0.0.0.0:8080` by default. Override `HOST` or `PORT` as
needed. Run the test suite with:

```bash
uv run python -m unittest discover -s tests -v
```

Local integration tests require the external renderers:

- Java, Graphviz, and a PlantUML JAR selected by `PLANTUML_JAR_PATH`.
- `mmdc` and a compatible Chromium installation. Set `MERMAID_CMD` and, when
  using a system browser, `MERMAID_PUPPETEER_CONFIG_PATH`.

Tests for an unavailable renderer are skipped automatically. Docker is the
simplest way to run the full integration suite because both backends are already
installed and configured.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | API bind host used by the installed command. |
| `PORT` | `8080` | API bind port used by the installed command. |
| `LOG_LEVEL` | `INFO` | Python root logging level. |
| `PLANTUML_JAR_PATH` | `/app/plantuml/plantuml.jar` | PlantUML JAR path. |
| `PLANTUML_TIMEOUT_SECONDS` | `20` | PlantUML subprocess timeout. |
| `JAVA_CMD` | `java` | Java executable. |
| `MERMAID_CMD` | `mmdc` | Mermaid CLI executable. |
| `MERMAID_TIMEOUT_SECONDS` | `20` | Mermaid subprocess timeout. |
| `MERMAID_PUPPETEER_CONFIG_PATH` | container config when present | Optional Puppeteer launch configuration. |

Invalid timeout values fall back to 20 seconds.

## Repository layout

- `app/main.py` — HTTP routes and safe API error handling.
- `app/models.py` — request, language, format, and response models.
- `app/renderer.py` — generic backend abstraction.
- `app/diagram_service.py` — renderer registry and dispatch.
- `app/plantuml_service.py` — PlantUML subprocess adapter.
- `app/mermaid_service.py` — Mermaid CLI subprocess adapter.
- `deps/` — bundled PlantUML artifact/licenses and Mermaid browser config.
- `scripts/generate-sbom.sh` — generates an SPDX JSON inventory for a built image.
- `tests/` — API, dispatch, unit, and renderer integration tests.
- `pyproject.toml` and `uv.lock` — project metadata and locked Python dependencies.

## Licensing and dependency inventory

The original `pipelign-diagrams` service code is licensed under the
[Apache License 2.0](LICENSE), with copyright held by Pipelign Software, Inc.
Third-party components retain their own licenses. In particular, the bundled
PlantUML JAR is GPL-3.0-or-later; Mermaid CLI is MIT-licensed. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for the direct runtime
inventory, license locations inside the image, PlantUML artifact checksum, and
source-availability notes.

Generate an SPDX JSON SBOM for the exact local image with:

```bash
docker compose build pipelign-diagrams
./scripts/generate-sbom.sh pipelign-diagrams:local
```

The generated report is placed under the ignored `build/` directory. Review
`NOASSERTION` and `NONE` results manually before distributing an image; automated
license detection is useful inventory data, not a legal conclusion.
