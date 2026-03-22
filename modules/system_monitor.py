"""
System monitor module for Nova — reports CPU, RAM, GPU, and disk usage.
"""

import asyncio
import logging

import psutil

from modules.base import NovaModule

logger = logging.getLogger(__name__)


class SystemMonitorModule(NovaModule):
    """Get current system resource usage: CPU, RAM, GPU, and disk."""

    name: str = "system_monitor"
    description: str = (
        "Get current system resource usage: CPU, RAM, GPU, and disk. Use this when "
        "the user asks about system performance, resource usage, or hardware stats."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "resource": {
                "type": "string",
                "enum": ["all", "cpu", "ram", "gpu", "disk"],
                "description": "Which resource to check (default: all)",
            }
        },
        "required": [],
    }

    # ------------------------------------------------------------------
    # Internal helpers (each runs in an executor to avoid blocking)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_cpu() -> str:
        percent = psutil.cpu_percent(interval=0.5)
        count = psutil.cpu_count(logical=True)
        return f"CPU: {percent:.1f}% usage ({count} cores)"

    @staticmethod
    def _get_ram() -> str:
        vm = psutil.virtual_memory()
        total_gb = vm.total / (1024 ** 3)
        used_gb = vm.used / (1024 ** 3)
        return f"RAM: {used_gb:.1f} GB / {total_gb:.1f} GB ({vm.percent:.1f}% used)"

    @staticmethod
    def _get_disk() -> str:
        du = psutil.disk_usage("/")
        total_gb = du.total / (1024 ** 3)
        used_gb = du.used / (1024 ** 3)
        return f"Disk (/): {used_gb:.1f} GB / {total_gb:.1f} GB ({du.percent:.1f}% used)"

    @staticmethod
    def _get_gpu() -> str:
        try:
            import GPUtil  # noqa: PLC0415 — optional dependency
            gpus = GPUtil.getGPUs()
            if not gpus:
                return "GPU: no NVIDIA GPU detected"
            lines = []
            for gpu in gpus:
                vram_used = gpu.memoryUsed / 1024  # MB → GB
                vram_total = gpu.memoryTotal / 1024
                vram_pct = (gpu.memoryUsed / gpu.memoryTotal * 100) if gpu.memoryTotal else 0
                temp = f", {gpu.temperature:.0f}°C" if gpu.temperature is not None else ""
                lines.append(
                    f"GPU: {gpu.name} — "
                    f"{vram_used:.1f} GB / {vram_total:.1f} GB VRAM "
                    f"({vram_pct:.1f}% used){temp}"
                )
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("GPUtil error: %s", exc)
            return "GPU: unavailable"

    # ------------------------------------------------------------------
    # run()
    # ------------------------------------------------------------------

    async def run(self, **kwargs) -> str:
        try:
            resource: str = kwargs.get("resource", "all").lower()

            loop = asyncio.get_event_loop()

            if resource == "cpu":
                return await loop.run_in_executor(None, self._get_cpu)

            if resource == "ram":
                return await loop.run_in_executor(None, self._get_ram)

            if resource == "disk":
                return await loop.run_in_executor(None, self._get_disk)

            if resource == "gpu":
                return await loop.run_in_executor(None, self._get_gpu)

            # "all" — gather concurrently
            cpu_str, ram_str, gpu_str, disk_str = await asyncio.gather(
                loop.run_in_executor(None, self._get_cpu),
                loop.run_in_executor(None, self._get_ram),
                loop.run_in_executor(None, self._get_gpu),
                loop.run_in_executor(None, self._get_disk),
            )
            return "\n".join([cpu_str, ram_str, gpu_str, disk_str])

        except Exception as exc:
            logger.exception("SystemMonitorModule error")
            return f"System monitor failed: {exc}"
