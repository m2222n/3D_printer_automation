from __future__ import annotations

from ctypes import POINTER, WinDLL, byref, c_int, c_uint
from pathlib import Path


class AxlResult:
    SUCCESS = 0
    OPEN_ALREADY = 1002


class AxlDll:
    """
    Minimal Python wrapper for AXL.dll functions used by Ajin IO.
    """

    def __init__(self, dll_path: str | Path) -> None:
        path = Path(dll_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"AXL.dll not found: {path}")
        self.path = path
        self._dll = WinDLL(str(path))
        self._bind()

    def _bind(self) -> None:
        self.AxlOpen = self._dll.AxlOpen
        self.AxlOpen.argtypes = [c_int]
        self.AxlOpen.restype = c_uint

        self.AxlClose = self._dll.AxlClose
        self.AxlClose.argtypes = []
        self.AxlClose.restype = c_int

        self.AxlIsOpened = self._dll.AxlIsOpened
        self.AxlIsOpened.argtypes = []
        self.AxlIsOpened.restype = c_int

        self.AxdInfoIsDIOModule = self._dll.AxdInfoIsDIOModule
        self.AxdInfoIsDIOModule.argtypes = [POINTER(c_uint)]
        self.AxdInfoIsDIOModule.restype = c_uint

        self.AxdInfoGetModuleStatus = self._dll.AxdInfoGetModuleStatus
        self.AxdInfoGetModuleStatus.argtypes = [c_int]
        self.AxdInfoGetModuleStatus.restype = c_uint

        self.AxdoWriteOutportBit = self._dll.AxdoWriteOutportBit
        self.AxdoWriteOutportBit.argtypes = [c_int, c_int, c_uint]
        self.AxdoWriteOutportBit.restype = c_uint

        self.AxdoReadOutportBit = self._dll.AxdoReadOutportBit
        self.AxdoReadOutportBit.argtypes = [c_int, c_int, POINTER(c_uint)]
        self.AxdoReadOutportBit.restype = c_uint

        self.AxdiReadInportBit = self._dll.AxdiReadInportBit
        self.AxdiReadInportBit.argtypes = [c_int, c_int, POINTER(c_uint)]
        self.AxdiReadInportBit.restype = c_uint

    def open(self, irq_no: int) -> int:
        return int(self.AxlOpen(int(irq_no)))

    def close(self) -> int:
        return int(self.AxlClose())

    def is_opened(self) -> int:
        return int(self.AxlIsOpened())

    def has_dio_module(self) -> tuple[int, bool]:
        status = c_uint(0)
        rc = int(self.AxdInfoIsDIOModule(byref(status)))
        return rc, bool(status.value)

    def get_module_status(self, module_no: int) -> int:
        return int(self.AxdInfoGetModuleStatus(int(module_no)))

    def write_out_bit(self, board_no: int, offset: int, value: int) -> int:
        return int(self.AxdoWriteOutportBit(int(board_no), int(offset), c_uint(int(value))))

    def read_out_bit(self, board_no: int, offset: int) -> tuple[int, bool]:
        value = c_uint(0)
        rc = int(self.AxdoReadOutportBit(int(board_no), int(offset), byref(value)))
        return rc, bool(value.value)

    def read_in_bit(self, board_no: int, offset: int) -> tuple[int, bool]:
        value = c_uint(0)
        rc = int(self.AxdiReadInportBit(int(board_no), int(offset), byref(value)))
        return rc, bool(value.value)

