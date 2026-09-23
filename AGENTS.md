# Repository Guidelines

## Project Status & Architecture

This repository implements an offline-capable stock-data agent demonstration on a Windows laptop with an NVIDIA RTX 4070 Laptop GPU (8 GB VRAM). The stack is Ollama, Qwen3.5 4B, Python/FastAPI, and plain HTML/CSS/JavaScript. Local PostgreSQL with pgvector imports the SQLite snapshot; SQLite remains a fallback. News supports keyword and local vector search across 300 articles; the evidence-backed graph covers a smaller subset. See `docs/POSTGRES.md` and `docs/GRAPHRAG.md`.

## Project Structure & Module Organization

- `src/`: application code; separate the Ollama client, agent loop, tool implementations, and interface.
- `tests/`: automated tests, organized to match source modules.
- `data/demo/`: bounded snapshots of user-authorized stock data for reproducible offline demonstrations.
- `assets/`: interface assets and demonstration screenshots.
- `docs/`: setup instructions, architecture notes, and measured results.
- `scripts/`: snapshot export, Windows startup, and real-model smoke checks.
- `models/`: reproducible Ollama templates, never model weights.

Keep downloaded models, virtual environments, credentials, and generated logs out of version control. Use paths relative to the project root rather than personal drive or network-share paths.

## Build, Test, and Development Commands

After installing Ollama, use:

- `ollama pull qwen3:4b-instruct-2507-q4_K_M`: download the pinned demo model; requires network access.
- `ollama create stock-agent:4b -f models/Modelfile`: create the demo alias with its compatible tool template.
- `ollama ps`: inspect loaded models and processor allocation.
- `nvidia-smi`: inspect GPU utilization and available VRAM.

- `uv sync --frozen`: install locked dependencies.
- `start-demo.cmd`: start local services and open the demo on Windows.
- `uv run pytest -q`: run synthetic-data and mocked-model tests.
- `uv run python scripts/smoke_demo.py`: check real-model flows and save private backup evidence.

## Coding Style & Naming Conventions

Use four-space indentation in Python, `snake_case` for functions and modules, and `PascalCase` for classes. Add type hints at tool and service boundaries. Keep tool schemas explicit and validate arguments before execution. No formatter or linter is configured yet.

## Testing Guidelines

Use `pytest` for new Python tests, with files named `test_*.py`. Test tool validation, missing records, tool failures, and agent iteration limits. Mock inference in unit tests; keep real-model smoke tests separate. No coverage threshold exists. Before a demonstration, verify offline operation and record model settings, latency, and tool-call outcomes.

## Commit & Pull Request Guidelines

Use concise, imperative commit subjects, matching the initial `Add repository guidelines and local dependency exclusions` commit. Pull requests should explain behavior changes, validation performed, and relevant limitations. Include screenshots for interface changes and link issues when applicable.

## Security & Demo Constraints

Use user-authorized stock data; never use former-employer tickets. Access PostgreSQL through read-only transactions and parameterized, bounded queries. Supply credentials through environment variables, never source files or logs. Keep demonstration tools read-only and local services bound to localhost. Never execute arbitrary model-generated shell commands. Display tool activity, data sources, and snapshot dates. Distinguish measured results from estimates and remote-data operation from fully offline operation.
