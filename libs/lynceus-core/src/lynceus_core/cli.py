# libs/lynceus-core/src/lynceus_core/cli.py

import math
import os

import click


class MemoryLimit(click.ParamType):
    name = "memory_limit"

    def convert(self, value, param, ctx):
        if not value:
            return None

        val_str = str(value).strip()

        # Convert K8s 'Gi'/'Mi'/'Ki' to DuckDB 'GiB'/'MiB'/'KiB'
        if val_str.endswith("i"):
            return f"{val_str}B"

        # Convert K8s 'G'/'M'/'K' to DuckDB 'GB'/'MB'/'KB'
        if not val_str.endswith("B") and val_str[-1].isalpha():
            return f"{val_str}B"

        return val_str


def _get_container_cpu_limit():
    if os.path.exists("/sys/fs/cgroup/cpu.max"):
        with open("/sys/fs/cgroup/cpu.max") as f:
            quota, period = f.read().strip().split()
            if quota != "max":
                return math.ceil(float(quota) / float(period))

    quota_path = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
    period_path = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
    if os.path.exists(quota_path) and os.path.exists(period_path):
        with open(quota_path) as f_q, open(period_path) as f_p:
            quota = int(f_q.read().strip())
            period = int(f_p.read().strip())
            if quota > 0:
                return math.ceil(quota / period)

    return (
        len(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else (os.cpu_count() or 1)
    )


class NumWorkers(click.ParamType):
    name = "num_workers"

    def convert(self, value, param, ctx):
        val_str = str(value).lower().strip()
        if val_str == "auto":
            return _get_container_cpu_limit() or 1
        try:
            n = int(val_str)
            if n < 1:
                self.fail("workers must be >= 1", param, ctx)
            return n
        except ValueError:
            self.fail(
                f"'{value}' is not 'auto' or a valid positive integer", param, ctx
            )


PATH_SEPARATOR = ","


def split_paths(ctx: click.Context, param: click.Parameter, value: str) -> list[str]:
    return [path for path in value.split(PATH_SEPARATOR) if path]
