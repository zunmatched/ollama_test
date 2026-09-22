# Repository Guidelines

## Project Status & Architecture

This workspace is intended for an offline-capable LLM agent demonstration on a Windows laptop with an NVIDIA RTX 4070 Laptop GPU (8 GB VRAM). The planned stack is Ollama, Qwen3 4B, Python, and a lightweight web interface. No application code, dependency manifest, test suite, or Git history exists yet. Treat the structure below as a convention for new development, not an inventory of implemented features.

## Project Structure & Module Organization

- `src/`: application code; separate the Ollama client, agent loop, tool implementations, and interface.
- `tests/`: automated tests, organized to match source modules.
- `data/demo/`: bounded snapshots of user-authorized stock data for reproducible offline demonstrations.
- `assets/`: interface assets and demonstration screenshots.
- `docs/`: setup instructions, architecture notes, and measured results.

Keep downloaded models, virtual environments, credentials, and generated logs out of version control. Use paths relative to the project root rather than personal drive or network-share paths.

## Build, Test, and Development Commands

After installing Ollama, use:

- `ollama pull qwen3:4b`: download the initial demonstration model; requires network access.
- `ollama run qwen3:4b`: check interactive model responses.
- `ollama ps`: inspect loaded models and processor allocation.
- `nvidia-smi`: inspect GPU utilization and available VRAM.

Application launch, dependency installation, and test commands are not configured. Document their exact commands when adding the corresponding files. Do not present proposed commands as working entry points.

## Coding Style & Naming Conventions

Use four-space indentation in Python, `snake_case` for functions and modules, and `PascalCase` for classes. Add type hints at tool and service boundaries. Keep tool schemas explicit and validate arguments before execution. No formatter or linter is configured yet.

## Testing Guidelines

Use `pytest` for new Python tests, with files named `test_*.py`. Test tool validation, missing records, tool failures, and agent iteration limits. Mock inference in unit tests; keep real-model smoke tests separate. No coverage threshold exists. Before a demonstration, verify offline operation and record model settings, latency, and tool-call outcomes.

## Commit & Pull Request Guidelines

There is no existing commit convention. Use concise, imperative subjects such as `Add read-only stock lookup tool`. Pull requests should explain behavior changes, validation performed, and relevant limitations. Include screenshots for interface changes and link issues when applicable.

## Security & Demo Constraints

Use user-authorized stock data; never use former-employer tickets. Access PostgreSQL through read-only transactions and parameterized, bounded queries. Supply credentials through environment variables, never source files or logs. Keep demonstration tools read-only and local services bound to localhost. Never execute arbitrary model-generated shell commands. Display tool activity, data sources, and snapshot dates. Distinguish measured results from estimates and remote-data operation from fully offline operation.
