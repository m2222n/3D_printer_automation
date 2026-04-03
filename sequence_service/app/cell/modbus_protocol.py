from __future__ import annotations

import time
from collections.abc import Callable

try:
    from pymodbus.client import ModbusTcpClient
except Exception:
    ModbusTcpClient = None  # type: ignore[assignment]


class ModbusHandshakeClient:
    """
    Modbus TCP client wrapper for the robot handshake used by SequenceService.

    PC-side flow implemented here:
    1. Wait until robot_ready_reg == 1
    2. Write pc_ready_reg = 1
    3. Wait until robot_moved_reg == 0
    4. Write pc_ready_reg = 0
    5. Write command register and parameter registers
    6. Write send_reg = 1
    7. Wait until robot_moved_reg == 1
    8. Write send_reg = 0
    """

    def __init__(self, host: str, port: int, timeout_seconds: float = 5.0, slave_id: int = 1):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.slave_id = slave_id

    def execute_command(
        self,
        robot_ready_reg: int,
        robot_moved_reg: int,
        pc_ready_reg: int,
        send_reg: int,
        cmd_reg: int,
        command_value: int,
        param_start_reg: int,
        params: list[int] | tuple[int, ...],
        param_count: int = 5,
        pc_ready_off_delay_seconds: float = 0.0,
        trace: Callable[[str], None] | None = None,
    ) -> tuple[bool, str]:
        # This method performs one complete robot command transaction.
        def _trace(message: str) -> None:
            if trace is not None:
                try:
                    trace(message)
                except Exception:
                    pass

        if ModbusTcpClient is None:
            return False, 'pymodbus is not installed'

        timeout_sec = max(1.0, float(self.timeout_seconds))
        client = ModbusTcpClient(self.host, port=int(self.port), timeout=timeout_sec)
        try:
            if not client.connect():
                return False, f'connect failed {self.host}:{self.port}'
            _trace(f'MODBUS CONNECT OK: {self.host}:{self.port}')

            # Step 1: wait until the robot advertises it is ready to accept a command.
            _trace(f'MODBUS CHECK: reg={robot_ready_reg} expected=1')
            deadline = time.time() + timeout_sec
            if not self._wait_value(client, robot_ready_reg, 1, deadline, trace=_trace):
                return False, f'robot_ready timeout: reg={robot_ready_reg} expected=1'
            _trace(f'MODBUS CHECK OK: reg={robot_ready_reg} value=1')

            # Step 2: tell the robot that the PC side is ready.
            _trace(f'MODBUS WRITE: reg={pc_ready_reg} value=1')
            if not self._write_register(client, pc_ready_reg, 1):
                return False, f'write failed: pc_ready_reg={pc_ready_reg} value=1'

            # Step 3: wait until the robot's "moved/done" flag is back to idle(0).
            _trace(f'MODBUS CHECK: reg={robot_moved_reg} expected=0')
            deadline = time.time() + timeout_sec
            if not self._wait_value(client, robot_moved_reg, 0, deadline, trace=_trace):
                return False, f'robot_moved timeout: reg={robot_moved_reg} expected=0 before send'
            _trace(f'MODBUS CHECK OK: reg={robot_moved_reg} value=0')

            # Step 4: lower the PC ready flag before sending the actual command payload.
            delay_sec = max(0.0, float(pc_ready_off_delay_seconds))
            if delay_sec > 0:
                _trace(f'MODBUS WAIT: before reg={pc_ready_reg} value=0 delay={delay_sec:.1f}s')
                time.sleep(delay_sec)
            _trace(f'MODBUS WRITE: reg={pc_ready_reg} value=0')
            if not self._write_register(client, pc_ready_reg, 0):
                return False, f'write failed: pc_ready_reg={pc_ready_reg} value=0'

            # Step 5: write command value to 130 and parameters to 131..N.
            _trace(f'MODBUS WRITE: reg={cmd_reg} value={command_value}')
            if not self._write_register(client, cmd_reg, command_value):
                return False, f'write failed: cmd_reg={cmd_reg} value={command_value}'

            normalized_params = [int(v) for v in list(params)[: max(0, int(param_count))]]
            while len(normalized_params) < int(param_count):
                normalized_params.append(0)
            for idx, value in enumerate(normalized_params):
                reg = int(param_start_reg) + idx
                _trace(f'MODBUS WRITE: reg={reg} value={value}')
                if not self._write_register(client, reg, value):
                    return False, f'write failed: param_reg={reg} value={value}'

            # Step 6: raise the send flag so the robot consumes the registers we just wrote.
            _trace(f'MODBUS WRITE: reg={send_reg} value=1')
            if not self._write_register(client, send_reg, 1):
                return False, f'write failed: send_reg={send_reg} value=1'

            # Step 7: wait until the robot reports motion complete.
            _trace(f'MODBUS CHECK: reg={robot_moved_reg} expected=1')
            deadline = time.time() + timeout_sec
            if not self._wait_value(client, robot_moved_reg, 1, deadline, trace=_trace):
                return False, f'robot_moved timeout: reg={robot_moved_reg} expected=1 after send'
            _trace(f'MODBUS CHECK OK: reg={robot_moved_reg} value=1')

            # Step 8: lower the send flag to complete the handshake cycle.
            _trace(f'MODBUS WRITE: reg={send_reg} value=0')
            if not self._write_register(client, send_reg, 0):
                return False, f'write failed: send_reg={send_reg} value=0'

            _trace(f'MODBUS COMMAND DONE: cmd={command_value} params={normalized_params}')
            return True, f'ok cmd={command_value} params={normalized_params}'
        finally:
            try:
                client.close()
            except Exception:
                pass

    def read_range(self, start_addr: int, end_addr: int, block_size: int = 100) -> tuple[bool, list[dict[str, int]] | str]:
        # Used by the manual UI to read blocks of holding registers.
        if ModbusTcpClient is None:
            return False, 'pymodbus is not installed'
        if end_addr < start_addr:
            return False, 'end_addr must be >= start_addr'

        timeout_sec = max(1.0, float(self.timeout_seconds))
        client = ModbusTcpClient(self.host, port=int(self.port), timeout=timeout_sec)
        try:
            if not client.connect():
                return False, f'connect failed {self.host}:{self.port}'

            items: list[dict[str, int]] = []
            addr = int(start_addr)
            last = int(end_addr)
            step = max(1, int(block_size))
            while addr <= last:
                count = min(step, last - addr + 1)
                res = client.read_holding_registers(int(addr), count=int(count))
                if res is None or res.isError():
                    return False, f'read failed at address {addr}'
                regs = list(getattr(res, 'registers', []) or [])
                if len(regs) < count:
                    return False, f'short read at address {addr}'
                for i, v in enumerate(regs):
                    items.append({"address": addr + i, "value": int(v)})
                addr += count

            return True, items
        finally:
            try:
                client.close()
            except Exception:
                pass

    def write_single(self, address: int, value: int) -> tuple[bool, int | str]:
        # Used by the manual UI to write a single holding register and read it back.
        if ModbusTcpClient is None:
            return False, 'pymodbus is not installed'

        timeout_sec = max(1.0, float(self.timeout_seconds))
        client = ModbusTcpClient(self.host, port=int(self.port), timeout=timeout_sec)
        try:
            if not client.connect():
                return False, f'connect failed {self.host}:{self.port}'

            if not self._write_register(client, int(address), int(value)):
                return False, f'write failed at address {address}'

            ok, read_back = self._read_register(client, int(address))
            if not ok:
                return True, int(value)
            return True, int(read_back)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def read_single(self, address: int, trace: Callable[[str], None] | None = None) -> tuple[bool, int | str]:
        # Used by the sequence logic when the handshake must advance one step at a time.
        if ModbusTcpClient is None:
            return False, 'pymodbus is not installed'

        timeout_sec = max(1.0, float(self.timeout_seconds))
        client = ModbusTcpClient(self.host, port=int(self.port), timeout=timeout_sec)
        try:
            if not client.connect():
                return False, f'connect failed {self.host}:{self.port}'

            ok, value = self._read_register(client, int(address), trace=trace)
            if not ok:
                return False, f'read failed at address {address}'
            return True, int(value)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _read_register(self, client, addr: int, trace: Callable[[str], None] | None = None) -> tuple[bool, int]:
        res = client.read_holding_registers(int(addr), count=1)
        if res is None or res.isError():
            if trace is not None:
                trace(f'MODBUS READ FAIL: reg={int(addr)}')
            return False, 0
        regs = list(getattr(res, 'registers', []) or [])
        if not regs:
            if trace is not None:
                trace(f'MODBUS READ EMPTY: reg={int(addr)}')
            return False, 0
        if trace is not None:
            trace(f'MODBUS READ: reg={int(addr)} value={int(regs[0])}')
        return True, int(regs[0])

    def _write_register(self, client, addr: int, value: int) -> bool:
        wr = client.write_register(int(addr), int(value))
        return wr is not None and (not wr.isError())

    def _wait_value(
        self,
        client,
        addr: int,
        value: int,
        deadline: float,
        trace: Callable[[str], None] | None = None,
    ) -> bool:
        while time.time() < deadline:
            ok, got = self._read_register(client, addr, trace=trace)
            if ok and got == value:
                return True
            time.sleep(0.1)
        return False

    def _wait_pair(
        self,
        client,
        reg_a: int,
        val_a: int,
        reg_b: int,
        val_b: int,
        deadline: float,
    ) -> bool:
        while time.time() < deadline:
            ok_a, got_a = self._read_register(client, reg_a)
            ok_b, got_b = self._read_register(client, reg_b)
            if ok_a and ok_b and got_a == val_a and got_b == val_b:
                return True
            time.sleep(0.1)
        return False
