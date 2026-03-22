"""
Tests for modules/system_monitor.py
"""

import types
import pytest
from unittest.mock import MagicMock, patch

from modules.system_monitor import SystemMonitorModule


@pytest.fixture
def module():
    return SystemMonitorModule()


# ---------------------------------------------------------------------------
# Helpers to build mock psutil objects
# ---------------------------------------------------------------------------


def _vm(total_gb=64.0, used_gb=18.2, percent=28.4):
    vm = MagicMock()
    vm.total = int(total_gb * 1024 ** 3)
    vm.used = int(used_gb * 1024 ** 3)
    vm.percent = percent
    return vm


def _disk(total_gb=1000.0, used_gb=234.5, percent=23.4):
    du = MagicMock()
    du.total = int(total_gb * 1024 ** 3)
    du.used = int(used_gb * 1024 ** 3)
    du.percent = percent
    return du


def _gpu(name="NVIDIA RTX 5070", mem_used_mb=4301, mem_total_mb=12288, temperature=52):
    gpu = MagicMock()
    gpu.name = name
    gpu.memoryUsed = mem_used_mb
    gpu.memoryTotal = mem_total_mb
    gpu.temperature = temperature
    return gpu


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resource_all_returns_all_sections(module):
    """resource='all' returns CPU, RAM, GPU, and Disk lines."""
    with (
        patch("modules.system_monitor.psutil.cpu_percent", return_value=12.3),
        patch("modules.system_monitor.psutil.cpu_count", return_value=16),
        patch("modules.system_monitor.psutil.virtual_memory", return_value=_vm()),
        patch("modules.system_monitor.psutil.disk_usage", return_value=_disk()),
    ):
        fake_gputil = types.ModuleType("GPUtil")
        fake_gputil.getGPUs = MagicMock(return_value=[_gpu()])
        with patch.dict("sys.modules", {"GPUtil": fake_gputil}):
            result = await module.run(resource="all")

    assert "CPU:" in result
    assert "RAM:" in result
    assert "GPU:" in result
    assert "Disk" in result


@pytest.mark.asyncio
async def test_resource_cpu_returns_only_cpu(module):
    """resource='cpu' returns only CPU information."""
    with (
        patch("modules.system_monitor.psutil.cpu_percent", return_value=5.0),
        patch("modules.system_monitor.psutil.cpu_count", return_value=8),
    ):
        result = await module.run(resource="cpu")

    assert "CPU:" in result
    assert "5.0%" in result
    assert "8 cores" in result
    # Should NOT contain other sections
    assert "RAM:" not in result
    assert "Disk" not in result


@pytest.mark.asyncio
async def test_resource_ram_returns_only_ram(module):
    """resource='ram' returns only RAM information."""
    with patch("modules.system_monitor.psutil.virtual_memory", return_value=_vm()):
        result = await module.run(resource="ram")

    assert "RAM:" in result
    assert "CPU:" not in result
    assert "Disk" not in result


@pytest.mark.asyncio
async def test_resource_disk_returns_only_disk(module):
    """resource='disk' returns only disk information."""
    with patch("modules.system_monitor.psutil.disk_usage", return_value=_disk()):
        result = await module.run(resource="disk")

    assert "Disk" in result
    assert "CPU:" not in result
    assert "RAM:" not in result


@pytest.mark.asyncio
async def test_resource_gpu_success(module):
    """resource='gpu' returns GPU VRAM and temperature."""
    fake_gputil = types.ModuleType("GPUtil")
    fake_gputil.getGPUs = MagicMock(return_value=[_gpu()])
    with patch.dict("sys.modules", {"GPUtil": fake_gputil}):
        result = await module.run(resource="gpu")

    assert "GPU:" in result
    assert "RTX 5070" in result
    assert "52°C" in result


@pytest.mark.asyncio
async def test_gputil_import_error_returns_unavailable(module):
    """If GPUtil raises on import, GPU line is 'GPU: unavailable'."""
    with patch.dict("sys.modules", {"GPUtil": None}):
        result = await module.run(resource="gpu")

    assert "GPU: unavailable" in result


@pytest.mark.asyncio
async def test_gputil_getgpus_exception_returns_unavailable(module):
    """If GPUtil.getGPUs() raises, GPU line is 'GPU: unavailable'."""
    fake_gputil = types.ModuleType("GPUtil")
    fake_gputil.getGPUs = MagicMock(side_effect=RuntimeError("driver error"))
    with patch.dict("sys.modules", {"GPUtil": fake_gputil}):
        result = await module.run(resource="gpu")

    assert "GPU: unavailable" in result


@pytest.mark.asyncio
async def test_gputil_no_gpus_detected(module):
    """If GPUtil returns an empty list, a friendly message is returned."""
    fake_gputil = types.ModuleType("GPUtil")
    fake_gputil.getGPUs = MagicMock(return_value=[])
    with patch.dict("sys.modules", {"GPUtil": fake_gputil}):
        result = await module.run(resource="gpu")

    assert "GPU:" in result
    assert "no NVIDIA GPU detected" in result


@pytest.mark.asyncio
async def test_default_resource_is_all(module):
    """Omitting 'resource' kwarg behaves the same as resource='all'."""
    with (
        patch("modules.system_monitor.psutil.cpu_percent", return_value=1.0),
        patch("modules.system_monitor.psutil.cpu_count", return_value=8),
        patch("modules.system_monitor.psutil.virtual_memory", return_value=_vm()),
        patch("modules.system_monitor.psutil.disk_usage", return_value=_disk()),
    ):
        fake_gputil = types.ModuleType("GPUtil")
        fake_gputil.getGPUs = MagicMock(return_value=[_gpu()])
        with patch.dict("sys.modules", {"GPUtil": fake_gputil}):
            result = await module.run()

    assert "CPU:" in result
    assert "RAM:" in result
    assert "Disk" in result
