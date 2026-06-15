# py2cpp-accelerator

Convert Python code to optimized C++ using frontier LLMs, achieving up to 60,000x performance gains.

## How it works

1. You provide Python code (or use the built-in pi approximation example)
2. An LLM (OpenAI, Anthropic, Gemini, or Grok) generates equivalent, highly optimized C++
3. The C++ is compiled with aggressive optimization flags and executed
4. You see the speedup

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- A C++ compiler: `clang++`, `g++`, or MSVC `cl` (auto-detected)

## Setup

```bash
git clone https://github.com/anton-karlovskiy/py2cpp-accelerator.git
cd py2cpp-accelerator
cp .env.example .env   # fill in your API keys
uv sync
```

### API keys

Edit `.env` with the keys for the models you want to use:

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GROK_API_KEY=xai-...
```

Only the key for your chosen `--model` is required.

## Usage

```bash
# Run the built-in pi example with OpenAI (default)
uv run python main.py

# Show Python baseline timing alongside the C++ result
uv run python main.py --python-baseline

# Use a specific model
uv run python main.py --model anthropic
uv run python main.py --model gemini
uv run python main.py --model grok

# Race all four models against each other
uv run python main.py --model all --python-baseline

# Convert your own Python file
uv run python main.py --input my_script.py --model openai

# Generate C++ only — skip compile and run
uv run python main.py --input my_script.py --no-compile
```

## Models

| Flag         | Provider   | Model                  |
|--------------|------------|------------------------|
| `openai`     | OpenAI     | gpt-5                  |
| `anthropic`  | Anthropic  | claude-sonnet-4-6      |
| `gemini`     | Google     | gemini-2.5-pro         |
| `grok`       | xAI        | grok-4                 |

## Performance

The built-in example approximates π using 200 million iterations of the Leibniz formula.
Typical results on the same hardware:

| Implementation | Time     | Speedup  |
|----------------|----------|----------|
| Python         | ~19 s    | 1×       |
| C++ (best)     | ~0.013 s | ~1,450×  |

With vectorization and `-Ofast`, the best models have demonstrated speedups exceeding **60,000×** on compute-bound loops.

## Project structure

```
py2cpp-accelerator/
├── main.py          # CLI entrypoint
├── system_info.py   # detects OS, CPU, and available compilers
├── pyproject.toml
├── .env.example
└── .gitignore
```
