# Ajin IO Wrapper

This folder contains a Python wrapper for Ajin `AXL.dll`, modeled after C# `AjinIOLib`.

## Files

- `axl.py`: low-level `ctypes` bindings (`AxlOpen`, `AxdiReadInportBit`, `AxdoWriteOutportBit`, etc.)
- `ajin_io.py`: high-level wrapper (`AjinIO`) with simulation mode and helper methods

## Config

Set these in `.env` or defaults in `app/core/config.py`:

- `AJIN_SIMULATION=true|false`
- `AJIN_IRQ_NO=7`
- `AJIN_DLL_PATH=app/io/bin/AXL.dll`
- `AJIN_AUTO_OPEN=false`

## Note

In real mode, `AXL.dll` and its runtime dependencies must exist on the target PC.

