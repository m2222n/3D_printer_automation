from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from app.core.config import get_settings
from app.io.axl import AxlDll, AxlResult


class IOOnOff(IntEnum):
    OFF = 0
    ON = 1


@dataclass
class AjinIoStatus:
    initialized: bool
    simulation: bool
    opened: bool
    has_dio: bool
    dll_path: str


class AjinIO:
    """
    Python port of C# AjinIOLib behavior.
    - Simulation mode supported
    - Uses AXL.dll in real mode
    """

    def __init__(
        self,
        simulation: bool | None = None,
        irq_no: int | None = None,
        dll_path: str | None = None,
    ) -> None:
        settings = get_settings()
        self.simulation = settings.AJIN_SIMULATION if simulation is None else simulation
        self.irq_no = settings.AJIN_IRQ_NO if irq_no is None else irq_no
        self.dll_path = dll_path or settings.AJIN_DLL_PATH
        self._axl: AxlDll | None = None
        self._initialized = False
        self._opened = False
        self._has_dio = False

    def init_lib(self) -> bool:
        if self.simulation:
            self._initialized = True
            self._opened = True
            self._has_dio = True
            return True

        if self._axl is None:
            self._axl = AxlDll(self._resolve_dll_path())

        rc = self._axl.open(self.irq_no)
        if rc not in (AxlResult.SUCCESS, AxlResult.OPEN_ALREADY):
            return False

        self._initialized = True
        self._opened = self._axl.is_opened() == 1
        dio_rc, has_dio = self._axl.has_dio_module()
        self._has_dio = dio_rc == AxlResult.SUCCESS and has_dio
        return self._opened

    def close(self) -> bool:
        if self.simulation:
            self._opened = False
            return True
        if self._axl is None:
            return True
        rc = self._axl.close()
        self._opened = False
        return rc == AxlResult.SUCCESS

    def check_exists_board(self) -> bool:
        if self.simulation:
            return True
        self._require_ready()
        dio_rc, has_dio = self._axl.has_dio_module()
        return dio_rc == AxlResult.SUCCESS and has_dio

    def check_electric_off(self, module_no: int) -> bool:
        if self.simulation:
            return True
        self._require_ready()
        # C# behavior: status != 0 means power/network issue
        return self._axl.get_module_status(module_no) == 0

    def write_output(self, board_no: int, offset: int, on_off: IOOnOff) -> int:
        if self.simulation:
            return int(on_off)
        self._require_ready()
        self._axl.write_out_bit(board_no, offset, int(on_off))
        return int(on_off)

    def read_output_is_on(self, board_no: int, offset: int) -> bool:
        if self.simulation:
            return True
        self._require_ready()
        rc, value = self._axl.read_out_bit(board_no, offset)
        if rc != AxlResult.SUCCESS:
            return False
        return value

    def read_input_is_on(self, board_no: int, offset: int) -> bool:
        if self.simulation:
            return True
        self._require_ready()
        rc, value = self._axl.read_in_bit(board_no, offset)
        if rc != AxlResult.SUCCESS:
            return False
        return value

    def get_status(self) -> AjinIoStatus:
        return AjinIoStatus(
            initialized=self._initialized,
            simulation=self.simulation,
            opened=self._opened,
            has_dio=self._has_dio,
            dll_path=str(self._resolve_dll_path()),
        )

    def _resolve_dll_path(self) -> Path:
        p = Path(self.dll_path)
        if p.is_absolute():
            return p
        # resolve relative to sequence_service project root
        root = Path(__file__).resolve().parents[2]
        return (root / p).resolve()

    def _require_ready(self) -> None:
        if self._axl is None and not self.simulation:
            ok = self.init_lib()
            if not ok:
                raise RuntimeError("AjinIO init failed")

