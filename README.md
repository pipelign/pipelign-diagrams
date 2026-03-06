## PlantUML Renderer

FastAPI-based microservice for validating and rendering [PlantUML](https://plantuml.com/) diagrams.

The service runs the official `plantuml.jar` inside a container and exposes a simple HTTP API to:

- **Validate** PlantUML source and return structured errors.
- **Render** diagrams to **PNG**, **SVG**, or **ASCII**.

---

### API overview

Base URL (Docker default): `http://localhost:8080`

- **`GET /health`**
  - **Purpose**: Lightweight liveness check.
  - **Response**: `{"status": "ok"}` when the server is healthy.

- **`POST /render/png`**
  - **Body**: `RenderRequest`
  - **Response 200**: Raw PNG bytes (`image/png`).
  - **Response 400**: `ValidationResult` if the diagram is invalid.
  - **Response 500**: `InternalErrorResponse` on unexpected PlantUML/Java errors.

- **`POST /render/svg`**
  - **Body**: `RenderRequest`
  - **Response 200**: SVG XML (`image/svg+xml`).
  - Error handling is identical to `/render/png`.

- **`POST /render/ascii`**
  - **Body**: `RenderRequest`
  - **Response 200**: Text/plain ASCII art representation of the diagram.
  - Error handling is identical to `/render/png`.

- **`POST /validate`**
  - **Body**: `RenderRequest`
  - **Response 200**: `ValidationResult` with `ok=true` and empty `errors`/`warnings`.
  - **Response 400**: `ValidationResult` with `ok=false` and one or more `ValidationIssue` entries.
  - **Response 500**: `InternalErrorResponse` on unexpected PlantUML/Java errors.

---

### Data models

Defined in `app/models.py`:

- **`RenderRequest`**
  - `source: str` – the raw PlantUML diagram text.
  - `options: dict | None` – reserved for future tuning / renderer options.

- **`ValidationIssue`**
  - `message: str` – human-readable description of the problem.
  - `line: int | None` – 1-based line number where PlantUML reported the issue, if available.

- **`ValidationResult`**
  - `ok: bool` – `true` when the diagram is valid.
  - `errors: list[ValidationIssue]` – syntax or structural errors.
  - `warnings: list[ValidationIssue]` – non-fatal issues (currently unused, reserved for future use).

- **`InternalErrorResponse`**
  - `ok: bool` – always `false`.
  - `errorType: str` – fixed to `"internal_error"`.
  - `message: str` – summary of the failure.
  - `details: dict | None` – implementation-specific debugging information.

---

### Validation behaviour

Validation happens in two layers inside `app/plantuml_service.py`:

- **Basic structure check** (before calling Java)
  - Enforced by `_ensure_basic_uml_structure`:
    - First non-empty line must be `@startuml`.
    - Last non-empty line must be `@enduml`.
    - There must be at least one non-empty line in between.
  - If this fails, the service raises `PlantUMLValidationError` with a single `ValidationIssue`
    explaining the structural problem. Java is not invoked.

- **PlantUML syntax check**
  - For `/validate`, PlantUML is called with `-check-syntax -pipe`.
  - Non-zero exit codes and stderr output are parsed by `_parse_validation_output` into
    a `ValidationResult`.
  - Each block of:
    - `ERROR`
    - `<line number>`
    - `<message>`
    becomes one `ValidationIssue`.

The FastAPI exception handlers in `app/main.py` convert `PlantUMLValidationError` and
`PlantUMLInternalError` into consistent HTTP responses.

---

### Running with Docker

Requirements:

- Docker
- Docker Compose v2 (`docker compose` CLI)

#### Build images

```bash
docker compose build
```

#### Run the API (production-style)

```bash
docker compose up pipelign-plantuml
```

This starts the server on port **8080**:

```bash
curl http://localhost:8080/health
```

#### Run the API in dev mode (auto-reload)

There is a dev-oriented service that mounts your local `app/` and `tests/` into the container
and runs uvicorn with `--reload`:

```bash
docker compose up pipelign-plantuml-dev
```

Changes to Python files under `app/` or `tests/` will automatically trigger a reload.

#### Run the test suite inside Docker

One-off test container:

```bash
docker compose run --rm pipelign-plantuml-tests
```

Or run tests inside a long-lived app container:

```bash
docker compose up -d pipelign-plantuml
docker compose exec pipelign-plantuml python -m unittest discover -s tests
```

---

### Configuration

Most behaviour is controlled via environment variables; see `app/logging_config.py`
and `app/plantuml_service.py` for details.

- **`PLANTUML_JAR_PATH`**
  - Path to the `plantuml.jar` inside the container.
  - Default: `/app/plantuml/plantuml.jar`.

- **`PLANTUML_TIMEOUT_SECONDS`**
  - Maximum time (in seconds) to wait for the PlantUML subprocess.
  - Default: `20`.

- **`JAVA_CMD`**
  - Java executable to run (`java`, `java17`, etc.).
  - Default: `java`.

- **`LOG_LEVEL`**
  - Python logging level applied to the root logger.
  - Common values: `DEBUG`, `INFO`, `WARNING`, `ERROR`.
  - Default: `INFO`.

These can be overridden in `docker-compose.yml` under the relevant service.

---

### Logging and debugging

Logging is configured centrally in `app/logging_config.py`. Key points:

- Root logger level comes from `LOG_LEVEL`.
- If no handlers exist, a simple STDERR handler is attached with a readable format.
- `app/plantuml_service.py` logs:
  - The exact Java command and diagram source (truncated at debug level).
  - Subprocess start/finish, timeouts, and OS-level failures.
  - Parsed validation errors (including counts and stderr text).
- `app/main.py` logs:
  - Incoming render/validate calls (including approximate source length).
  - All validation and internal errors before sending HTTP responses.

Set `LOG_LEVEL=DEBUG` on the service to see the PlantUML command, diagram source, and
stdout/stderr previews, which is very useful when diagnosing tricky diagrams.

---

### Local development (without Docker)

Create and activate a virtual environment, then install dependencies:

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Make sure `plantuml.jar` exists at the path expected by `PLANTUML_JAR_PATH`, then run:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Run tests:

```bash
python -m unittest discover -s tests
```

---

### Project structure

- `app/__init__.py` – package marker for the FastAPI application.
- `app/main.py` – FastAPI app, routes, and HTTP-level error handling.
- `app/models.py` – Pydantic models for requests and responses.
- `app/plantuml_service.py` – subprocess integration, validation logic, and rendering.
- `app/logging_config.py` – central logging configuration based on `LOG_LEVEL`.
- `tests/` – unit and integration tests for endpoints, models, and PlantUML integration.

---

### Notes and limitations

- The service expects PlantUML-compatible diagrams and currently assumes UTF‑8 source.
- Validation is focused on syntax and basic structure; semantic or style checks are not performed.
- Warnings are supported structurally but are not yet populated from PlantUML output.

Contributions and extensions (e.g. more detailed error parsing, option handling,
or additional output formats) can be added by extending `app/plantuml_service.py`
and the corresponding tests.
