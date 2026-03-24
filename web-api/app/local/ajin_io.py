from __future__ import annotations

from ctypes import POINTER, WinDLL, byref, c_int, c_uint
from pathlib import Path
from threading import Lock
from typing import Any


AXT_RT_SUCCESS = 0
AXT_RT_OPEN_ALREADY = 1002


class AjinIoGateway:
    """
    Minimal Ajin IO gateway for web-api manual IO screen.
    """

    def __init__(self, simulation: bool, irq_no: int, dll_path: str) -> None:
        self.simulation = simulation
        self.irq_no = irq_no
        self.dll_path = dll_path
        self._lock = Lock()
        self._dll: Any | None = None
        self._opened = False
        self._sim_outputs: dict[tuple[int, int], bool] = {}

    def open(self) -> None:
        if self.simulation:
            self._opened = True
            return
        if self._opened and self._dll is not None:
            return
        dll_abs = self._resolve_dll_path()
        if not dll_abs.exists():
            raise FileNotFoundError(f"AXL.dll not found: {dll_abs}")
        self._dll = WinDLL(str(dll_abs))
        self._bind()
        rc = int(self._dll.AxlOpen(int(self.irq_no)))
        if rc not in (AXT_RT_SUCCESS, AXT_RT_OPEN_ALREADY):
            raise RuntimeError(f"AxlOpen failed rc={rc}")
        self._opened = True

    def close(self) -> None:
        if self.simulation:
            self._opened = False
            return
        if self._dll is None:
            return
        self._dll.AxlClose()
        self._opened = False

    def read_inputs(self, board_no: int, count: int) -> list[bool]:
        with self._lock:
            self.open()
            if self.simulation:
                return [False for _ in range(count)]
            out: list[bool] = []
            for offset in range(count):
                val = c_uint(0)
                rc = int(self._dll.AxdiReadInportBit(int(board_no), int(offset), byref(val)))
                out.append(rc == AXT_RT_SUCCESS and bool(val.value))
            return out

    def read_outputs(self, board_no: int, count: int) -> list[bool]:
        with self._lock:
            self.open()
            if self.simulation:
                return [self._sim_outputs.get((board_no, offset), False) for offset in range(count)]
            out: list[bool] = []
            for offset in range(count):
                val = c_uint(0)
                rc = int(self._dll.AxdoReadOutportBit(int(board_no), int(offset), byref(val)))
                out.append(rc == AXT_RT_SUCCESS and bool(val.value))
            return out

    def write_output(self, board_no: int, offset: int, value: bool) -> bool:
        with self._lock:
            self.open()
            if self.simulation:
                self._sim_outputs[(board_no, offset)] = bool(value)
                return True
            rc = int(self._dll.AxdoWriteOutportBit(int(board_no), int(offset), c_uint(1 if value else 0)))
            return rc == AXT_RT_SUCCESS

    def _resolve_dll_path(self) -> Path:
        p = Path(self.dll_path)
        if p.is_absolute():
            return p
        # resolve relative to web-api project root
        root = Path(__file__).resolve().parents[2]
        return (root / p).resolve()

    def _bind(self) -> None:
        assert self._dll is not None
        self._dll.AxlOpen.argtypes = [c_int]
        self._dll.AxlOpen.restype = c_uint

        self._dll.AxlClose.argtypes = []
        self._dll.AxlClose.restype = c_int

        self._dll.AxdiReadInportBit.argtypes = [c_int, c_int, POINTER(c_uint)]
        self._dll.AxdiReadInportBit.restype = c_uint

        self._dll.AxdoReadOutportBit.argtypes = [c_int, c_int, POINTER(c_uint)]
        self._dll.AxdoReadOutportBit.restype = c_uint

        self._dll.AxdoWriteOutportBit.argtypes = [c_int, c_int, c_uint]
        self._dll.AxdoWriteOutportBit.restype = c_uint


_INSTANCE: AjinIoGateway | None = None


def get_ajin_gateway(simulation: bool, irq_no: int, dll_path: str) -> AjinIoGateway:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = AjinIoGateway(simulation=simulation, irq_no=irq_no, dll_path=dll_path)
    return _INSTANCE
