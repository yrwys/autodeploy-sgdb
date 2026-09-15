import re

SIDECAR_DEFAULT_LIMIT_CPU_MILLIS = 250
SIDECAR_DEFAULT_LIMIT_MEMORY_MI = 512
SIDECAR_CONTAINER_COUNT = 4
RESERVED_CPU_MILLIS = SIDECAR_DEFAULT_LIMIT_CPU_MILLIS * SIDECAR_CONTAINER_COUNT
RESERVED_MEMORY_MI = SIDECAR_DEFAULT_LIMIT_MEMORY_MI * SIDECAR_CONTAINER_COUNT
SETUP_FILESYSTEM_CPU = "200m"
SETUP_FILESYSTEM_MEMORY = "384Mi"
MINIMUM_CPU_MILLIS = 2000
MINIMUM_MEMORY_MI = 3072


def parse_cpu_to_millis(cpu: str) -> int:
    """'2000m' -> 2000, '2' -> 2000."""
    cpu = cpu.strip()
    if cpu.endswith("m"):
        return int(cpu[:-1])
    return int(float(cpu) * 1000)


def format_millis_to_cpu(millis: int) -> str:
    return f"{millis}m"


_MEMORY_UNITS_TO_MI = {
    "Ei": 1024 ** 5 / 1024 ** 2, "Pi": 1024 ** 4 / 1024 ** 2,
    "Ti": 1024 ** 3 / 1024 ** 2, "Gi": 1024, "Mi": 1, "Ki": 1 / 1024,
}


def parse_memory_to_mi(memory: str) -> int:
    """'3Gi' -> 3072, '512Mi' -> 512."""
    match = re.match(r"^([0-9.]+)([A-Za-z]*)$", memory.strip())
    if not match:
        raise ValueError(f"Unrecognized memory format: {memory!r}")
    value, unit = match.groups()
    unit = unit or "Mi"
    if unit not in _MEMORY_UNITS_TO_MI:
        raise ValueError(f"Unsupported memory unit: {unit!r} in {memory!r}")
    return int(float(value) * _MEMORY_UNITS_TO_MI[unit])


def format_mi_to_memory(mi: int) -> str:
    if mi % 1024 == 0:
        return f"{mi // 1024}Gi"
    return f"{mi}Mi"


def split_patroni_share(total_cpu: str, total_memory: str) -> tuple[str, str]:
    total_cpu_millis = parse_cpu_to_millis(total_cpu)
    total_memory_mi = parse_memory_to_mi(total_memory)

    if total_cpu_millis < MINIMUM_CPU_MILLIS or total_memory_mi < MINIMUM_MEMORY_MI:
        raise ValueError(
            f"Selected cpu/memory ({total_cpu}/{total_memory}) is below the "
            f"portal minimum ({MINIMUM_CPU_MILLIS}m/{MINIMUM_MEMORY_MI}Mi) "
            f"required to leave room for sidecar containers."
        )

    patroni_cpu_millis = total_cpu_millis - RESERVED_CPU_MILLIS
    patroni_memory_mi = total_memory_mi - RESERVED_MEMORY_MI

    if patroni_cpu_millis <= 0 or patroni_memory_mi <= 0:
        raise ValueError(
            f"Selected cpu/memory ({total_cpu}/{total_memory}) leaves no "
            f"budget for the database container after reserving "
            f"{RESERVED_CPU_MILLIS}m/{RESERVED_MEMORY_MI}Mi for sidecars. "
            f"Raise MINIMUM_CPU_MILLIS/MINIMUM_MEMORY_MI or pick a larger value."
        )

    return format_millis_to_cpu(patroni_cpu_millis), format_mi_to_memory(patroni_memory_mi)