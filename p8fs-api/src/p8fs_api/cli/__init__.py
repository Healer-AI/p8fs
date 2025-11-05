"""P8FS API CLI commands."""

from .device import DeviceCLI, main as device_main

__all__ = ["DeviceCLI", "device_main"]
