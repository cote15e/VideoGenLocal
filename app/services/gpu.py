import shutil
import subprocess


def detect_gpu() -> dict:
    nvidia = _nvidia_smi()
    if nvidia is not None:
        return nvidia
    torch_gpu = _torch_gpu()
    if torch_gpu is not None:
        return torch_gpu
    return {"available": False, "name": None, "memory_gb": 0.0, "source": None}


def _nvidia_smi() -> dict | None:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"available": False, "name": None, "memory_gb": 0.0, "source": "nvidia-smi"}
    best_name = None
    best_gb = 0.0
    for line in proc.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        name, memory = parts[0], parts[1]
        try:
            memory_gb = float(memory) / 1024
        except ValueError:
            continue
        if memory_gb >= best_gb:
            best_gb = memory_gb
            best_name = name
    if best_name is None:
        return {"available": False, "name": None, "memory_gb": 0.0, "source": "nvidia-smi"}
    return {"available": True, "name": best_name, "memory_gb": round(best_gb, 2), "source": "nvidia-smi"}


def _torch_gpu() -> dict | None:
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return {"available": False, "name": None, "memory_gb": 0.0, "source": "torch"}
    index = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(index)
    memory_gb = props.total_memory / (1024 ** 3)
    return {
        "available": True,
        "name": props.name,
        "memory_gb": round(memory_gb, 2),
        "source": "torch",
    }
