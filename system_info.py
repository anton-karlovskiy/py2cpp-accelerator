import os
import platform
import shutil
import subprocess
from typing import Any

# ------------------------- helpers -------------------------


def _run(cmd: str | list[str], timeout: int = 3) -> str:
    """Run a command safely. Returns stdout text or ''.
    Accepts either a string (shell) or list (no shell)."""
    try:
        if isinstance(cmd, str):
            return subprocess.check_output(
                cmd, shell=True, text=True, stderr=subprocess.DEVNULL, timeout=timeout
            ).strip()
        else:
            return subprocess.check_output(
                cmd, shell=False, text=True, stderr=subprocess.DEVNULL, timeout=timeout
            ).strip()
    except Exception:
        return ""


def _first_line(s: str) -> str:
    s = (s or "").strip()
    return s.splitlines()[0].strip() if s else ""


def _which(name: str) -> str:
    return shutil.which(name) or ""


def _bool_from_output(s: str) -> bool:
    return s.strip() in {"1", "true", "True", "YES", "Yes", "yes"}


# ------------------------- OS & env -------------------------


def _os_block() -> dict[str, Any]:
    sysname = platform.system()  # 'Windows', 'Darwin', 'Linux'
    machine = platform.machine() or ""
    release = platform.release() or ""
    version = platform.version() or ""
    kernel = release if sysname == "Windows" else (_run(["uname", "-r"]) or release)

    distro = {"name": "", "version": ""}
    if sysname == "Linux":
        # Best-effort parse of /etc/os-release
        try:
            with open("/etc/os-release", "r") as f:
                data = {}
                for line in f:
                    if "=" in line:
                        key, value = line.rstrip().split("=", 1)
                        data[key] = value.strip('"')
                distro["name"] = data.get("PRETTY_NAME") or data.get("NAME", "")
                distro["version"] = data.get("VERSION_ID") or data.get("VERSION", "")
        except Exception:
            pass

    # WSL / Rosetta detection (harmless if not present)
    wsl = False
    if sysname != "Windows":
        try:
            with open("/proc/version", "r") as f:
                proc_version = f.read().lower()
                wsl = ("microsoft" in proc_version) or ("wsl" in proc_version)
        except Exception:
            wsl = False

    rosetta = False
    if sysname == "Darwin":
        rosetta = _bool_from_output(_run(["sysctl", "-in", "sysctl.proc_translated"]))

    # Target triple (best effort)
    target = ""
    for cc in ("clang", "gcc"):
        if _which(cc):
            out = _run([cc, "-dumpmachine"])
            if out:
                target = _first_line(out)
                break

    return {
        "system": sysname,
        "arch": machine,
        "release": release,
        "version": version,
        "kernel": kernel,
        "distro": distro if sysname == "Linux" else None,
        "wsl": wsl,
        "rosetta2_translated": rosetta,
        "target_triple": target,
    }


# ------------------------- package managers -------------------------


def _package_managers() -> list[str]:
    sysname = platform.system()
    managers = []
    if sysname == "Windows":
        for pm in ("winget", "choco", "scoop"):
            if _which(pm):
                managers.append(pm)
    elif sysname == "Darwin":
        if _run(["xcode-select", "-p"]):
            managers.append("xcode-select (CLT)")
        for pm in ("brew", "port"):
            if _which(pm):
                managers.append(pm)
    else:
        for pm in ("apt", "dnf", "yum", "pacman", "zypper", "apk", "emerge"):
            if _which(pm):
                managers.append(pm)
    return managers


# ------------------------- CPU (minimal) -------------------------


def _cpu_block() -> dict[str, Any]:
    sysname = platform.system()
    brand = ""
    # A simple brand/model read per OS; ignore failures
    if sysname == "Linux":
        brand = _run("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2").strip()
    elif sysname == "Darwin":
        brand = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    elif sysname == "Windows":
        brand = _run('powershell -NoProfile -Command "(Get-CimInstance Win32_Processor).Name"')
        if not brand:
            brand = _run("wmic cpu get Name /value").replace("Name=", "").strip()

    # Logical cores always available; physical is best-effort
    cores_logical = os.cpu_count() or 0
    cores_physical = 0
    if sysname == "Darwin":
        cores_physical = int(_run(["sysctl", "-n", "hw.physicalcpu"]) or "0")
    elif sysname == "Windows":
        cores_physical = int(
            _run('powershell -NoProfile -Command "(Get-CimInstance Win32_Processor).NumberOfCores"')
            or "0"
        )
    elif sysname == "Linux":
        # This is a quick approximation; fine for our use (parallel -j suggestions)
        try:
            # Count unique "core id" per physical id
            mapping = _run("LC_ALL=C lscpu -p=CORE,SOCKET | grep -v '^#'").splitlines()
            unique = set(tuple(line.split(",")) for line in mapping if "," in line)
            cores_physical = len(unique) or 0
        except Exception:
            cores_physical = 0

    # A tiny SIMD hint set (best-effort, optional)
    simd = []
    if sysname == "Linux":
        flags = _run("grep -m1 'flags' /proc/cpuinfo | cut -d: -f2")
        if flags:
            flag_set = set(flags.upper().split())
            for x in ("AVX512F", "AVX2", "AVX", "FMA", "SSE4_2", "NEON", "SVE"):
                if x in flag_set:
                    simd.append(x)
    elif sysname == "Darwin":
        features = (
            (
                _run(["sysctl", "-n", "machdep.cpu.features"])
                + " "
                + _run(["sysctl", "-n", "machdep.cpu.leaf7_features"])
            )
            .upper()
            .split()
        )
        for x in ("AVX512F", "AVX2", "AVX", "FMA", "SSE4_2", "NEON", "SVE"):
            if x in features:
                simd.append(x)
    # On Windows, skip flags — brand typically suffices for MSVC /arch choice.

    return {
        "brand": brand.strip(),
        "cores_logical": cores_logical,
        "cores_physical": cores_physical,
        "simd": sorted(set(simd)),
    }


# ------------------------- toolchain presence -------------------------


def _toolchain_block() -> dict[str, Any]:
    def ver_line(exe: str, args: tuple[str, ...] = ("--version",)) -> str:
        exe_path = _which(exe)
        if not exe_path:
            return ""
        out = _run([exe_path, *args])
        return _first_line(out)

    gcc = ver_line("gcc")
    gpp = ver_line("g++")
    clang = ver_line("clang")

    # MSVC cl (only available inside proper dev shell; handle gracefully)
    msvc_cl = ""
    cl_path = _which("cl")
    if cl_path:
        msvc_cl = _first_line(_run("cl 2>&1"))

    # Build tools (presence + short version line)
    cmake = ver_line("cmake")
    ninja = _first_line(_run([_which("ninja"), "--version"])) if _which("ninja") else ""
    make = ver_line("make")

    # Linker (we only care if lld is available)
    lld = ver_line("ld.lld")
    return {
        "compilers": {"gcc": gcc, "g++": gpp, "clang": clang, "msvc_cl": msvc_cl},
        "build_tools": {"cmake": cmake, "ninja": ninja, "make": make},
        "linkers": {"ld_lld": lld},
    }


# ------------------------- public API -------------------------


def retrieve_system_info() -> dict[str, Any]:
    """
    Returns a compact dict with enough info for an LLM to:
      - Pick an install path (winget/choco/scoop, Homebrew/Xcode CLT, apt/dnf/...),
      - Choose a compiler family (MSVC/clang/gcc),
      - Suggest safe optimization flags (e.g., -O3/-march=native or MSVC /O2),
      - Decide on a build system (cmake+ninja) and parallel -j value.
    """
    return {
        "os": _os_block(),
        "package_managers": _package_managers(),
        "cpu": _cpu_block(),
        "toolchain": _toolchain_block(),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(retrieve_system_info(), indent=2))
