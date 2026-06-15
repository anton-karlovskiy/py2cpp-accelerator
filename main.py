import os
import shutil
import platform
import argparse
import subprocess

from dotenv import load_dotenv
from openai import OpenAI

from system_info import retrieve_system_info

load_dotenv(override=True)

# -- API clients --
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
anthropic_client = OpenAI(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url="https://api.anthropic.com/v1/",
)
gemini_client = OpenAI(
    api_key=os.getenv("GOOGLE_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)
grok_client = OpenAI(
    api_key=os.getenv("GROK_API_KEY"),
    base_url="https://api.x.ai/v1",
)

MODELS = {
    "openai":    (openai_client,    "gpt-5"),
    "anthropic": (anthropic_client, "claude-sonnet-4-6"),
    "gemini":    (gemini_client,    "gemini-2.5-pro"),
    "grok":      (grok_client,      "grok-4"),
}

# -- Compile/run commands: auto-detect sensible defaults per OS --
def _default_commands(out_name: str = "main_out"):
    sysname = platform.system()
    if sysname == "Windows":
        if shutil.which("cl"):
            return (
                ["cl", "/O2", "/std:c++17", "/EHsc", f"/Fe:{out_name}.exe", "main.cpp"],
                [f"{out_name}.exe"],
            )
        elif shutil.which("clang++"):
            return (
                ["clang++", "-std=c++17", "-Ofast", "-march=native", "-DNDEBUG", "main.cpp", "-o", f"{out_name}.exe"],
                [f"{out_name}.exe"],
            )
        elif shutil.which("g++"):
            return (
                ["g++", "-std=c++17", "-O3", "-march=native", "-DNDEBUG", "main.cpp", "-o", f"{out_name}.exe"],
                [f"{out_name}.exe"],
            )
    elif shutil.which("clang++"):
        return (
            ["clang++", "-std=c++17", "-Ofast", "-march=native", "-flto", "-DNDEBUG", "main.cpp", "-o", out_name],
            [f"./{out_name}"],
        )
    elif shutil.which("g++"):
        return (
            ["g++", "-std=c++17", "-O3", "-march=native", "-DNDEBUG", "main.cpp", "-o", out_name],
            [f"./{out_name}"],
        )
    raise RuntimeError("No C++ compiler found. Install clang++, g++, or MSVC cl.")


SYSTEM_PROMPT = """
Your task is to convert Python code into high performance C++ code.
Respond only with C++ code. Do not provide any explanation other than occasional comments.
The C++ response needs to produce an identical output in the fastest possible time.
"""

PI_EXAMPLE = """\
import time

def calculate(iterations, param1, param2):
    result = 1.0
    for i in range(1, iterations + 1):
        j = i * param1 - param2
        result -= (1 / j)
        j = i * param1 + param2
        result += (1 / j)
    return result

start_time = time.time()
result = calculate(200_000_000, 4, 1) * 4
end_time = time.time()

print(f"Result: {result:.12f}")
print(f"Execution Time: {(end_time - start_time):.6f} seconds")
"""


def user_prompt_for(python: str, system_info: dict, compile_command: list) -> str:
    return f"""
Port this Python code to C++ with the fastest possible implementation that produces identical output in the least time.
The system information is:
{system_info}
Your response will be written to a file called main.cpp and then compiled and executed; the compilation command is:
{compile_command}
Respond only with C++ code.
Python code to port:

```python
{python}
```
"""


def generate_cpp(client: OpenAI, model: str, python: str, system_info: dict, compile_command: list) -> str:
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt_for(python, system_info, compile_command)},
        ],
    }
    if "gpt" in model:
        kwargs["reasoning_effort"] = "high"
    response = client.chat.completions.create(**kwargs)
    cpp = response.choices[0].message.content
    return cpp.replace("```cpp", "").replace("```c++", "").replace("```c", "").replace("```", "").strip()


def compile_and_run(compile_cmd: list, run_cmd: list) -> str:
    subprocess.run(compile_cmd, check=True, text=True, capture_output=True)
    result = subprocess.run(run_cmd, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def run_python(code: str) -> None:
    exec(compile(code, "<string>", "exec"), {"__builtins__": __builtins__})


def main():
    parser = argparse.ArgumentParser(
        description="Convert Python to optimized C++ using LLMs for massive performance gains."
    )
    parser.add_argument(
        "--input", "-i",
        help="Path to a Python file to convert (default: built-in pi approximation example)",
    )
    parser.add_argument(
        "--model", "-m",
        choices=list(MODELS.keys()) + ["all"],
        default="openai",
        help="LLM to use for conversion (default: openai)",
    )
    parser.add_argument(
        "--no-compile",
        action="store_true",
        help="Write the C++ file(s) but skip compilation and execution",
    )
    parser.add_argument(
        "--python-baseline",
        action="store_true",
        help="Run the Python code first to establish a baseline time",
    )
    args = parser.parse_args()

    python_code = PI_EXAMPLE
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            python_code = f.read()

    system_info = retrieve_system_info()
    targets = list(MODELS.keys()) if args.model == "all" else [args.model]

    if args.python_baseline:
        print("=== Python baseline ===")
        run_python(python_code)
        print()

    for name in targets:
        client, model = MODELS[name]
        out_stem = f"main_{name}"
        compile_cmd, run_cmd = _default_commands(out_stem)

        print(f"=== [{name.upper()}] {model} ===")
        print(f"Generating C++...", end=" ", flush=True)

        cpp = generate_cpp(client, model, python_code, system_info, compile_cmd)
        cpp_file = f"{out_stem}.cpp"
        with open(cpp_file, "w", encoding="utf-8") as f:
            f.write(cpp)
        print(f"written to {cpp_file}")

        if not args.no_compile:
            # Patch compile command to use the named output file
            try:
                print("Compiling and running...")
                actual_compile = [a.replace("main.cpp", cpp_file) for a in compile_cmd]
                output = compile_and_run(actual_compile, run_cmd)
                print(output)
            except subprocess.CalledProcessError as e:
                print(f"Error: {e.stderr or e.stdout}")
        print()


if __name__ == "__main__":
    main()
