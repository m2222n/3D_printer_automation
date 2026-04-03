import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getAutomationIoState,
  getAutomationState,
  getManualCommConfig,
  getManualModbusRegisters,
  getManualRobotStatus,
  updateManualCommConfig,
  writeAutomationIoOutput,
  writeManualModbusRegister,
} from '../services/localApi';

type TabKey = 'communication' | 'io';

const MODBUS_MIN_ADDR = 130;
const MODBUS_MAX_ADDR = 255;
const MODBUS_CHUNK_SIZE = 50;

function OnOffPill({ on }: { on: boolean }) {
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold ${on ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-700'}`}>
      {on ? 'ON' : 'OFF'}
    </span>
  );
}

function wrapIoLabel(label: string, chunkSize: number = 14): string {
  const src = (label || '').replace(/\r/g, '');
  return src
    .split('\n')
    .map((line) => {
      if (line.length <= chunkSize) return line;
      const parts: string[] = [];
      for (let i = 0; i < line.length; i += chunkSize) parts.push(line.slice(i, i + chunkSize));
      return parts.join('\n');
    })
    .join('\n');
}

export function AutomationManualPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('communication');

  const [robotConnected, setRobotConnected] = useState<boolean>(false);
  const [robotConnText, setRobotConnText] = useState<string>('checking...');
  const [automationRunning, setAutomationRunning] = useState<boolean>(false);
  const [robotHost, setRobotHost] = useState<string>('127.0.0.1');
  const [robotPort, setRobotPort] = useState<number>(502);
  const [visionHost, setVisionHost] = useState<string>('127.0.0.1');
  const [visionPort, setVisionPort] = useState<number>(9200);
  const [commConfigSaving, setCommConfigSaving] = useState<boolean>(false);
  const [commConfigMessage, setCommConfigMessage] = useState<string>('');

  const [modbusBusy, setModbusBusy] = useState<boolean>(false);
  const [modbusMessage, setModbusMessage] = useState<string>('');
  const [modbusValues, setModbusValues] = useState<Record<number, number>>({});
  const [modbusChunkIndex, setModbusChunkIndex] = useState<number>(0);
  const [writeAddress, setWriteAddress] = useState<number>(200);
  const [writeValue, setWriteValue] = useState<number>(1);

  const [ioBusy, setIoBusy] = useState(false);
  const [ioMessage, setIoMessage] = useState('');
  const [ioSimulation, setIoSimulation] = useState<boolean>(true);
  const [inputBoardNo, setInputBoardNo] = useState<number>(0);
  const [outputBoardNo, setOutputBoardNo] = useState<number>(0);
  const [inputAvailableBoards, setInputAvailableBoards] = useState<number[]>([0]);
  const [outputAvailableBoards, setOutputAvailableBoards] = useState<number[]>([0]);
  const [inputs, setInputs] = useState<boolean[]>(Array.from({ length: 32 }, () => false));
  const [outputs, setOutputs] = useState<boolean[]>(Array.from({ length: 32 }, () => false));
  const [inputLabels, setInputLabels] = useState<string[]>(Array.from({ length: 32 }, (_, i) => `IN${i}`));
  const [outputLabels, setOutputLabels] = useState<string[]>(Array.from({ length: 32 }, (_, i) => `OUT${i}`));
  const ioPollingBusyRef = useRef(false);
  const inputBoardNoRef = useRef(0);
  const outputBoardNoRef = useRef(0);
  const inputReqSeqRef = useRef(0);
  const outputReqSeqRef = useRef(0);
  const ioSwitchCooldownUntilRef = useRef(0);

  const boolArrayEqual = (a: boolean[], b: boolean[]): boolean => {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return false;
    return true;
  };

  const strArrayEqual = (a: string[], b: string[]): boolean => {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return false;
    return true;
  };

  const numArrayEqual = (a: number[], b: number[]): boolean => {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return false;
    return true;
  };

  const maxChunkCount = Math.ceil((MODBUS_MAX_ADDR - MODBUS_MIN_ADDR + 1) / MODBUS_CHUNK_SIZE);
  const currentChunkStart = MODBUS_MIN_ADDR + modbusChunkIndex * MODBUS_CHUNK_SIZE;
  const currentChunkEnd = Math.min(MODBUS_MAX_ADDR, currentChunkStart + MODBUS_CHUNK_SIZE - 1);
  const currentChunkAddresses = Array.from(
    { length: currentChunkEnd - currentChunkStart + 1 },
    (_, i) => currentChunkStart + i
  );

  const loadInputIo = useCallback(async (targetBoardNo?: number, syncMeta: boolean = true) => {
    const reqSeq = ++inputReqSeqRef.current;
    try {
      const reqBoard = targetBoardNo ?? inputBoardNoRef.current;
      const r = await getAutomationIoState(reqBoard, 32, 'input');
      if (reqSeq !== inputReqSeqRef.current) return;
      const nextInputs = (r.inputs || []).slice(0, 32);
      setInputs((prev) => (boolArrayEqual(prev, nextInputs) ? prev : nextInputs));
      setIoSimulation(!!r.simulation);
      if (syncMeta) {
        const nextBoard = r.board_no ?? 0;
        setInputBoardNo((prev) => (prev === nextBoard ? prev : nextBoard));
        inputBoardNoRef.current = nextBoard;
        const nextBoards = (r.available_input_boards || r.available_boards || [0]).slice().sort((a, b) => a - b);
        setInputAvailableBoards((prev) => (numArrayEqual(prev, nextBoards) ? prev : nextBoards));
        const nextLabels = (r.input_labels || Array.from({ length: 32 }, (_, i) => `IN${i}`)).slice(0, 32);
        setInputLabels((prev) => (strArrayEqual(prev, nextLabels) ? prev : nextLabels));
      }
    } catch (e) {
      setIoMessage(`Input IO state load failed: ${String(e)}`);
    }
  }, []);

  const loadOutputIo = useCallback(async (targetBoardNo?: number, syncMeta: boolean = true) => {
    const reqSeq = ++outputReqSeqRef.current;
    try {
      const reqBoard = targetBoardNo ?? outputBoardNoRef.current;
      const r = await getAutomationIoState(reqBoard, 32, 'output');
      if (reqSeq !== outputReqSeqRef.current) return;
      const nextOutputs = (r.outputs || []).slice(0, 32);
      setOutputs((prev) => (boolArrayEqual(prev, nextOutputs) ? prev : nextOutputs));
      setIoSimulation(!!r.simulation);
      if (syncMeta) {
        const nextBoard = r.board_no ?? 0;
        setOutputBoardNo((prev) => (prev === nextBoard ? prev : nextBoard));
        outputBoardNoRef.current = nextBoard;
        const nextBoards = (r.available_output_boards || r.available_boards || [0]).slice().sort((a, b) => a - b);
        setOutputAvailableBoards((prev) => (numArrayEqual(prev, nextBoards) ? prev : nextBoards));
        const nextLabels = (r.output_labels || Array.from({ length: 32 }, (_, i) => `OUT${i}`)).slice(0, 32);
        setOutputLabels((prev) => (strArrayEqual(prev, nextLabels) ? prev : nextLabels));
      }
    } catch (e) {
      setIoMessage(`Output IO state load failed: ${String(e)}`);
    }
  }, []);

  const loadCommConfig = useCallback(async () => {
    try {
      const cfg = await getManualCommConfig();
      setRobotHost(cfg.robot_host || '127.0.0.1');
      setRobotPort(Number(cfg.robot_port || 502));
      setVisionHost(cfg.vision_host || '127.0.0.1');
      setVisionPort(Number(cfg.vision_port || 9200));
    } catch {
      // keep current values
    }
  }, []);

  const checkRobotStatus = useCallback(async () => {
    try {
      const s = await getManualRobotStatus();
      const ok = !!s.connected;
      setRobotConnected(ok);
      setRobotConnText(ok ? `connected (${s.host}:${s.port})` : `disconnected (${s.host}:${s.port})`);
    } catch {
      setRobotConnected(false);
      setRobotConnText('disconnected');
    }
  }, []);

  const loadModbusRegisters = useCallback(async () => {
    try {
      const r = await getManualModbusRegisters(MODBUS_MIN_ADDR, MODBUS_MAX_ADDR);
      const m: Record<number, number> = {};
      for (const it of r.items || []) m[it.address] = Number(it.value ?? 0);
      setModbusValues(m);
    } catch (e) {
      setModbusMessage(`Read failed: ${String(e)}`);
    }
  }, []);

  useEffect(() => {
    loadCommConfig().catch(() => undefined);
    const poll = async () => {
      try {
        const state = await getAutomationState();
        setAutomationRunning(!!state.running);
      } catch {
        setAutomationRunning(false);
      }
      if (activeTab === 'communication') {
        await checkRobotStatus();
        await loadModbusRegisters();
      }
    };
    poll().catch(() => undefined);
    const id = setInterval(() => {
      poll().catch(() => undefined);
    }, 3000);
    return () => clearInterval(id);
  }, [activeTab, checkRobotStatus, loadCommConfig, loadModbusRegisters]);

  useEffect(() => {
    if (activeTab !== 'io') return;
    loadInputIo(undefined, true).catch(() => undefined);
    loadOutputIo(undefined, true).catch(() => undefined);
    const id = setInterval(() => {
      if (Date.now() < ioSwitchCooldownUntilRef.current) return;
      if (ioPollingBusyRef.current) return;
      ioPollingBusyRef.current = true;
      Promise.all([loadInputIo(undefined, false), loadOutputIo(undefined, false)])
        .catch(() => undefined)
        .finally(() => {
          ioPollingBusyRef.current = false;
        });
    }, 700);
    return () => clearInterval(id);
  }, [activeTab, loadInputIo, loadOutputIo]);

  const saveCommConfig = async () => {
    if (!robotHost.trim() || !visionHost.trim()) {
      setCommConfigMessage('Host is required.');
      return;
    }
    if (robotPort < 1 || robotPort > 65535 || visionPort < 1 || visionPort > 65535) {
      setCommConfigMessage('Port must be 1..65535.');
      return;
    }
    setCommConfigSaving(true);
    setCommConfigMessage('');
    try {
      const saved = await updateManualCommConfig(
        robotHost.trim(),
        Number(robotPort),
        visionHost.trim(),
        Number(visionPort)
      );
      setRobotHost(saved.robot_host);
      setRobotPort(Number(saved.robot_port));
      setVisionHost(saved.vision_host);
      setVisionPort(Number(saved.vision_port));
      await checkRobotStatus();
      await loadModbusRegisters();
      setCommConfigMessage('Saved. Sequence runtime and manual Modbus use this target.');
    } catch (e) {
      setCommConfigMessage(`Save failed: ${String(e)}`);
    } finally {
      setCommConfigSaving(false);
    }
  };

  const writeModbusRegister = async () => {
    if (writeAddress < MODBUS_MIN_ADDR || writeAddress > MODBUS_MAX_ADDR) {
      setModbusMessage(`Address must be ${MODBUS_MIN_ADDR}..${MODBUS_MAX_ADDR}`);
      return;
    }
    if (writeValue < 0 || writeValue > 65535) {
      setModbusMessage('Value must be 0..65535');
      return;
    }
    setModbusBusy(true);
    setModbusMessage('');
    try {
      const res = await writeManualModbusRegister(writeAddress, writeValue);
      const readBack = res.read_back ?? writeValue;
      setModbusValues((prev) => ({ ...prev, [writeAddress]: Number(readBack) }));
      setModbusMessage(`WRITE OK: addr=${writeAddress}, value=${writeValue}, read_back=${readBack}`);
    } catch (e) {
      setModbusMessage(`Write failed: ${String(e)}`);
    } finally {
      setModbusBusy(false);
    }
  };

  const setOutput = async (offset: number, next: boolean) => {
    setIoBusy(true);
    setIoMessage('');
    try {
      await writeAutomationIoOutput(outputBoardNo, offset, next);
      await loadOutputIo(undefined, false);
    } catch (e) {
      setIoMessage(`IO output write failed: ${String(e)}`);
    } finally {
      setIoBusy(false);
    }
  };

  const getNextBoard = (boards: number[], currentBoard: number, delta: -1 | 1): number | null => {
    if (!boards.length) return null;
    const sorted = boards.slice().sort((a, b) => a - b);
    const idx = sorted.indexOf(currentBoard);
    if (idx < 0) return delta > 0 ? sorted[0] : sorted[sorted.length - 1];
    const nextIdx = idx + delta;
    if (nextIdx < 0 || nextIdx >= sorted.length) return null;
    return sorted[nextIdx];
  };

  const getBoardIndexText = (boards: number[], currentBoard: number): string => {
    if (!boards.length) return '1/1';
    const sorted = boards.slice().sort((a, b) => a - b);
    const idx = sorted.indexOf(currentBoard);
    if (idx < 0) return `1/${sorted.length}`;
    return `${idx + 1}/${sorted.length}`;
  };

  const moveInputBoard = async (delta: -1 | 1) => {
    const nextBoard = getNextBoard(inputAvailableBoards, inputBoardNo, delta);
    if (nextBoard === null) return;
    setInputBoardNo(nextBoard);
    inputBoardNoRef.current = nextBoard;
    ioSwitchCooldownUntilRef.current = Date.now() + 1200;
    await loadInputIo(nextBoard, true);
  };

  const moveOutputBoard = async (delta: -1 | 1) => {
    const nextBoard = getNextBoard(outputAvailableBoards, outputBoardNo, delta);
    if (nextBoard === null) return;
    setOutputBoardNo(nextBoard);
    outputBoardNoRef.current = nextBoard;
    ioSwitchCooldownUntilRef.current = Date.now() + 1200;
    await loadOutputIo(nextBoard, true);
  };

  return (
    <div className="bg-gray-100">
      <header className="bg-white border-b">
        <div className="w-full px-[10%] py-3">
          <h2 className="text-lg font-semibold text-gray-900">Automation_Manual</h2>
        </div>
      </header>

      <main className="w-full px-[10%] py-4">
        <div className="bg-white border rounded-xl p-2 mb-3">
          <div className="flex gap-2">
            <button
              className={`px-3 py-1.5 rounded text-sm border ${activeTab === 'communication' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700'}`}
              onClick={() => setActiveTab('communication')}
            >
              Communication
            </button>
            <button
              className={`px-3 py-1.5 rounded text-sm border ${activeTab === 'io' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700'} disabled:opacity-50 disabled:cursor-not-allowed`}
              onClick={() => setActiveTab('io')}
              disabled
              title="IO List is currently disabled"
            >
              IO List
            </button>
          </div>
        </div>

        {activeTab === 'communication' && (
          <>
            <section className="bg-white rounded-xl border p-4 mb-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-gray-900">Robot Modbus Target</h3>
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${robotConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                  {robotConnected ? 'CONNECTED' : 'DISCONNECTED'}
                </span>
              </div>
              <div className="text-[11px] text-gray-600 mb-2">{robotConnText}</div>
              <div className="text-[11px] text-gray-600 mb-2">Sequence: {automationRunning ? 'RUNNING' : 'STOPPED'}</div>
              <div className="grid grid-cols-[1fr_140px_auto_auto] gap-2">
                <input
                  value={robotHost}
                  onChange={(e) => setRobotHost(e.target.value)}
                  className="border rounded px-2 py-1.5 text-sm"
                  placeholder="Robot IP"
                />
                <input
                  type="number"
                  min={1}
                  max={65535}
                  value={robotPort}
                  onChange={(e) => setRobotPort(Number(e.target.value || 0))}
                  className="border rounded px-2 py-1.5 text-sm"
                />
                <button
                  className="px-3 py-1.5 rounded bg-blue-600 text-white text-sm disabled:opacity-50"
                  disabled={commConfigSaving}
                  onClick={saveCommConfig}
                >
                  Save Target
                </button>
                <button
                  className="px-3 py-1.5 rounded border text-sm disabled:opacity-50"
                  disabled={commConfigSaving}
                  onClick={() => {
                    loadCommConfig().catch(() => undefined);
                    checkRobotStatus().catch(() => undefined);
                  }}
                >
                  Reload
                </button>
              </div>
              {commConfigMessage && <div className="mt-2 text-xs text-gray-700">{commConfigMessage}</div>}
            </section>

            <section className="bg-white rounded-xl border p-4">
              <h3 className="font-semibold text-gray-900 mb-3">Robot Modbus Registers (130..255)</h3>

              <div className="grid grid-cols-[180px_180px_auto_auto] gap-2 mb-3 items-center">
                <input
                  type="number"
                  min={MODBUS_MIN_ADDR}
                  max={MODBUS_MAX_ADDR}
                  value={writeAddress}
                  onChange={(e) => setWriteAddress(Number(e.target.value || MODBUS_MIN_ADDR))}
                  className="border rounded px-2 py-1.5 text-sm"
                  placeholder="Address"
                />
                <input
                  type="number"
                  min={0}
                  max={65535}
                  value={writeValue}
                  onChange={(e) => setWriteValue(Number(e.target.value || 0))}
                  className="border rounded px-2 py-1.5 text-sm"
                  placeholder="Value"
                />
                <button
                  className="px-3 py-1.5 rounded bg-blue-600 text-white text-sm disabled:opacity-50"
                  disabled={modbusBusy}
                  onClick={writeModbusRegister}
                >
                  Write
                </button>
                <button
                  className="px-3 py-1.5 rounded border text-sm disabled:opacity-50"
                  disabled={modbusBusy}
                  onClick={() => loadModbusRegisters().catch(() => undefined)}
                >
                  Refresh
                </button>
              </div>

              <div className="text-xs text-gray-600 mb-2">
                Chunk {modbusChunkIndex + 1}/{maxChunkCount} | Address {currentChunkStart}..{currentChunkEnd}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
                {currentChunkAddresses.map((addr) => (
                  <div key={addr} className="border rounded px-2 py-2 text-sm flex items-center justify-between bg-gray-50">
                    <span className="font-medium text-gray-700">{addr}</span>
                    <span className="font-semibold text-gray-900">{modbusValues[addr] ?? '-'}</span>
                  </div>
                ))}
              </div>

              <div className="mt-3 flex items-center justify-center gap-2">
                <button
                  className="px-3 py-1.5 border rounded text-sm disabled:opacity-40"
                  disabled={modbusChunkIndex <= 0}
                  onClick={() => setModbusChunkIndex((v) => Math.max(0, v - 1))}
                >
                  Prev 50
                </button>
                <button
                  className="px-3 py-1.5 border rounded text-sm disabled:opacity-40"
                  disabled={modbusChunkIndex >= maxChunkCount - 1}
                  onClick={() => setModbusChunkIndex((v) => Math.min(maxChunkCount - 1, v + 1))}
                >
                  Next 50
                </button>
              </div>

              {modbusMessage && <div className="mt-3 text-sm text-gray-700">{modbusMessage}</div>}
            </section>
          </>
        )}

        {activeTab === 'io' && (
          <section className="bg-white rounded-xl border p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-gray-900">IO List</h3>
              <div className="text-xs text-gray-600 flex items-center gap-2">
                <span>Mode</span>
                <OnOffPill on={!ioSimulation} />
                <span>{ioSimulation ? 'SIMULATION' : 'REAL'}</span>
                <button className="ml-2 px-2 py-1 border rounded text-xs" onClick={() => { loadInputIo(undefined, true).catch(() => undefined); loadOutputIo(undefined, true).catch(() => undefined); }} disabled={ioBusy}>Refresh</button>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="border rounded p-3 min-h-[620px] flex flex-col">
                <h4 className="font-semibold text-sm mb-2">{`Input (Board ${inputBoardNo}, 32ch)`}</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 flex-1 content-start">
                  {Array.from({ length: 32 }).map((_, i) => (
                    <div key={`in-${i}`} className="border rounded px-2 py-2.5 text-sm min-h-[42px] flex items-center justify-between">
                      <span className="pr-2 whitespace-pre-line break-words leading-tight" title={inputLabels[i] || `IN${i}`}>
                        {wrapIoLabel(inputLabels[i] || `IN${i}`)}
                      </span>
                      <OnOffPill on={!!inputs[i]} />
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex items-center justify-center gap-2">
                  <button
                    className="px-3 py-1.5 border rounded text-sm disabled:opacity-40"
                    disabled={getNextBoard(inputAvailableBoards, inputBoardNo, -1) === null || ioBusy}
                    onClick={() => moveInputBoard(-1)}
                  >
                    Prev Board
                  </button>
                  <span className="text-xs text-gray-600">{`${getBoardIndexText(inputAvailableBoards, inputBoardNo)} (Input, Board ${inputBoardNo})`}</span>
                  <button
                    className="px-3 py-1.5 border rounded text-sm disabled:opacity-40"
                    disabled={getNextBoard(inputAvailableBoards, inputBoardNo, 1) === null || ioBusy}
                    onClick={() => moveInputBoard(1)}
                  >
                    Next Board
                  </button>
                </div>
              </div>

              <div className="border rounded p-3 min-h-[620px] flex flex-col">
                <h4 className="font-semibold text-sm mb-2">{`Output (Board ${outputBoardNo}, 32ch)`}</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 flex-1 content-start">
                  {Array.from({ length: 32 }).map((_, i) => (
                    <div
                      key={`out-${i}`}
                      className={`border rounded px-2 py-2 text-sm min-h-[56px] flex items-start justify-between gap-2 ${outputs[i] ? 'bg-green-50 border-green-300' : 'bg-gray-50'}`}
                    >
                      <span className="pr-2 whitespace-pre-line break-words leading-tight text-xs flex-1" title={outputLabels[i] || `OUT${i}`}>
                        {wrapIoLabel(outputLabels[i] || `OUT${i}`)}
                      </span>
                      <div className="flex flex-col items-end gap-1">
                        <OnOffPill on={!!outputs[i]} />
                        <div className="grid grid-cols-2 gap-1 min-w-[84px]">
                          <button
                            className="py-1 rounded text-[11px] font-semibold bg-green-600 text-white disabled:opacity-40"
                            disabled={ioBusy || outputs[i]}
                            onClick={() => setOutput(i, true)}
                          >
                            ON
                          </button>
                          <button
                            className="py-1 rounded text-[11px] font-semibold bg-gray-700 text-white disabled:opacity-40"
                            disabled={ioBusy || !outputs[i]}
                            onClick={() => setOutput(i, false)}
                          >
                            OFF
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex items-center justify-center gap-2">
                  <button
                    className="px-3 py-1.5 border rounded text-sm disabled:opacity-40"
                    disabled={getNextBoard(outputAvailableBoards, outputBoardNo, -1) === null || ioBusy}
                    onClick={() => moveOutputBoard(-1)}
                  >
                    Prev Board
                  </button>
                  <span className="text-xs text-gray-600">{`${getBoardIndexText(outputAvailableBoards, outputBoardNo)} (Output, Board ${outputBoardNo})`}</span>
                  <button
                    className="px-3 py-1.5 border rounded text-sm disabled:opacity-40"
                    disabled={getNextBoard(outputAvailableBoards, outputBoardNo, 1) === null || ioBusy}
                    onClick={() => moveOutputBoard(1)}
                  >
                    Next Board
                  </button>
                </div>
              </div>
            </div>

            {ioMessage && <div className="mt-3 text-sm text-gray-700">{ioMessage}</div>}
          </section>
        )}
      </main>
    </div>
  );
}
