from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol


class HardwareGateway(Protocol):
    """Backend-agnostic contract every K3 hardware kernel must implement.

    The agent only talks to this surface; the concrete kernel is selected at
    startup based on ``hardware_mode`` (``simulated`` vs ``k3``) so the rest of
    the codebase never imports a driver directly. On the developer machine
    the default kernel is :class:`SimulatedHardwareKernel`, which always
    reports ``ok=False`` and refuses to execute real motion. On K3,
    :class:`K3HardwareKernel` provides the implementation that calls into
    real camera / serial / GPIO drivers.
    """

    async def status(self) -> dict[str, Any]: ...

    async def command(
        self, device: str, action: str, parameters: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def capture(self, camera: str = "main") -> dict[str, Any]: ...


class SimulatedHardwareKernel:
    """Safe placeholder until K3 GPIO/serial/CAN/camera drivers are selected.

    Every method reports ``ok=False`` so the agent (or any UI) can clearly see
    the kernel refused to act. Replace with :class:`K3HardwareKernel` once the
    on-device drivers are wired up.
    """

    adapter_name = "simulated"

    def __init__(self, enabled: bool = False, mode: str = "simulated") -> None:
        self.enabled = enabled
        self.mode = mode

    async def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "adapter": self.adapter_name,
            "camera": {"available": False, "backend": "none"},
            "actuators": [],
            "vision": {"available": False, "backend": "yolo-placeholder"},
            "message": "硬件驱动尚未连接，当前仅支持安全模拟模式。",
        }

    async def command(
        self, device: str, action: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "simulated": True,
            "device": device,
            "action": action,
            "parameters": parameters,
            "message": "硬件控制尚未启用；未执行任何物理动作。",
        }

    async def capture(self, camera: str = "main") -> dict[str, Any]:
        return {
            "ok": False,
            "camera": camera,
            "captured_at": datetime.now(UTC).isoformat(),
            "message": "摄像头驱动尚未连接；没有采集图像。",
        }


class K3HardwareKernel:
    """Stub for the real K3 implementation. Replace each method's body with
    driver calls (``cv2.VideoCapture``, ``pyserial.Serial``, ``lgpio``, ...) once
    the on-device packaging is finalised. Until then the kernel refuses every
    action and reports the missing drivers, so the agent sees a clear
    "hardware unavailable" status rather than a silent no-op.
    """

    adapter_name = "k3"

    def __init__(self, settings: Any) -> None:
        # ``settings`` is intentionally untyped here so the deployer can wire
        # whatever driver config they need without touching the agent core.
        self.settings = settings

    async def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "mode": "k3",
            "adapter": self.adapter_name,
            "camera": {"available": False, "backend": "pending"},
            "actuators": [],
            "vision": {"available": False, "backend": "pending"},
            "message": (
                "K3 硬件内核骨架已就位，但真实驱动（cv2 / pyserial / lgpio）尚未"
                "实现。请在 K3HardwareKernel 中填写真实 driver 调用。"
            ),
        }

    async def command(
        self, device: str, action: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "adapter": self.adapter_name,
            "device": device,
            "action": action,
            "parameters": parameters,
            "message": (
                f"K3 硬件驱动未实现：接到 device={device} action={action} 后拒绝执行，"
                "等待真实 driver 接入。"
            ),
        }

    async def capture(self, camera: str = "main") -> dict[str, Any]:
        return {
            "ok": False,
            "adapter": self.adapter_name,
            "camera": camera,
            "captured_at": datetime.now(UTC).isoformat(),
            "message": "K3 摄像头驱动未实现：返回占位。",
        }


def build_hardware_kernel(settings: Any) -> HardwareGateway:
    """Factory that picks the right kernel based on settings.

    ``settings.hardware_mode`` selects between ``simulated`` (developer
    machine) and ``k3`` (on-device deployment). When K3 mode is requested
    but the kernel is not yet wired up, we still return
    :class:`SimulatedHardwareKernel` and surface a clear message in
    ``status()`` so the operator can tell which mode they are actually
    running. This avoids pretending the K3 driver exists before it does.
    """
    mode = getattr(settings, "hardware_mode", "simulated")
    if mode == "k3":
        try:
            return K3HardwareKernel(settings)
        except Exception as exc:  # pragma: no cover - defensive fallback
            import logging

            logging.getLogger(__name__).warning(
                "K3HardwareKernel unavailable (%s); using simulated kernel", exc
            )
    return SimulatedHardwareKernel(
        enabled=getattr(settings, "hardware_enabled", False),
        mode=mode,
    )