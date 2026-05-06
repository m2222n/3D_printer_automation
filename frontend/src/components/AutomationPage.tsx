import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  controlAutomation,
  createAutomationCommand,
  getAutomationCommands,
  getPresets,
  getAutomationLogs,
  getAutomationQueues,
  getAutomationState,
  setAutomationSimul,
  updateAutomationCommandsUseYn,
  uploadFile,
  type AutomationCommandItem,
  type AutomationLogItem,
  type AutomationQueues,
} from '../services/localApi';
import { getDashboard } from '../services/api';
import type { Preset } from '../types/local';
import type { PrinterSummary } from '../types/printer';

type FormState = {
  file_path: string;
  preset_id: string;
  washing_time: number;
  curing_time: number;
  target_printer: number | ''; // 260410 추가
};
type QueueTab = 'board' | 'job';

const STATUS_LABELS: Record<number, string> = {
  0: 'UPLOADING',
  10: 'QUEUED',
  20: 'CLAIMED',
  30: 'PRINTING',
  40: 'PRINT_FINISHED',
  50: 'POST_PROCESSING',
  90: 'DONE',
  98: 'CANCELED',
  99: 'ERROR',
};

const LOG_TYPE_LABELS: Record<number, string> = {
  10: 'PROGRAM',
  20: 'SEQUENCE',
  30: 'ROBOT',
  40: 'SYSTEM',
};

function parseAllocated(data: unknown): Record<string, unknown> | null {
  if (!data) return null;
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data);
      return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null;
    } catch {
      return null;
    }
  }
  return typeof data === 'object' ? (data as Record<string, unknown>) : null;
}

function printerNicknameFromSerial(serial: unknown): string {
  const raw = String(serial || '').trim();
  if (!raw) return '-';
  return raw.replace(/^Form4-/, '') || raw;
}

function printerStatusTone(printer: PrinterSummary): string {
  if (!printer.is_online) return 'bg-gray-100 text-gray-700';
  if (printer.has_error || printer.status === 'ERROR') return 'bg-red-100 text-red-700';
  if (printer.status === 'PRINTING' || printer.status === 'PREHEAT') return 'bg-blue-100 text-blue-700';
  if (printer.is_ready) return 'bg-green-100 text-green-700';
  return 'bg-yellow-100 text-yellow-700';
}

function OnOffBadge({ on }: { on: boolean }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${on ? 'bg-green-100 text-green-700' : 'bg-gray-200 text-gray-700'
        }`}
    >
      {on ? 'ON' : 'OFF'}
    </span>
  );
}

function QueueChips({ items }: { items: string[] }) {
  if (!items.length) return <span className="text-xs text-gray-400">empty</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((id) => (
        <span key={id} className="px-1.5 py-0.5 rounded bg-slate-100 text-[11px] font-mono text-slate-700">
          {id.slice(0, 8)}
        </span>
      ))}
    </div>
  );
}

export function AutomationPage() {
  const [form, setForm] = useState<FormState>({
    file_path: '',
    preset_id: '',
    washing_time: 360,
    curing_time: 120,
    target_printer: '', // 260410 추가  
  });
  const [presets, setPresets] = useState<Preset[]>([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [state, setState] = useState<{ running: boolean; paused: boolean; simul_mode: boolean }>({
    running: false,
    paused: false,
    simul_mode: false,
  });
  const [items, setItems] = useState<AutomationCommandItem[]>([]);
  const [selectedCmdIds, setSelectedCmdIds] = useState<string[]>([]);
  const [queues, setQueues] = useState<AutomationQueues>({});
  const [logs, setLogs] = useState<AutomationLogItem[]>([]);
  const [printers, setPrinters] = useState<PrinterSummary[]>([]);
  const [queueTab, setQueueTab] = useState<QueueTab>('board');
  const [isBusy, setIsBusy] = useState(false);
  const [message, setMessage] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadAll = useCallback(async () => {
    const [sRes, listRes, qRes, lRes, dRes] = await Promise.allSettled([
      getAutomationState(),
      getAutomationCommands(100),
      getAutomationQueues(),
      getAutomationLogs(200),
      getDashboard(),
    ]);

    if (sRes.status === 'fulfilled') {
      setState(sRes.value);
    }
    if (listRes.status === 'fulfilled') {
      setItems(listRes.value.items);
      setSelectedCmdIds((prev) => prev.filter((id) => listRes.value.items.some((it) => it.cmd_id === id)));
    }
    if (qRes.status === 'fulfilled') {
      setQueues(qRes.value.items || {});
    }
    if (lRes.status === 'fulfilled') {
      setLogs(lRes.value.items || []);
    } else {
      // Keep page usable even when /automation/logs is unavailable (e.g. old web-api process).
      setLogs([]);
    }
    if (dRes.status === 'fulfilled') {
      setPrinters(dRes.value.printers || []);
    } else {
      setPrinters([]);
    }
  }, []);

  useEffect(() => {
    loadAll().catch(() => setMessage('Automation data load failed'));
    const id = setInterval(() => {
      loadAll().catch(() => undefined);
    }, 5000);
    return () => clearInterval(id);
  }, [loadAll]);

  useEffect(() => {
    getPresets()
      .then((res) => setPresets(res.items))
      .catch(() => setPresets([]));
  }, []);

  const onChooseFile = () => {
    fileInputRef.current?.click();
  };

  const onSelectedFile: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setForm((prev) => ({ ...prev, file_path: file.name, preset_id: '' }));
    setIsBusy(true);
    setMessage('Uploading selected file...');
    try {
      const uploaded = await uploadFile(file);
      setForm((prev) => ({ ...prev, file_path: uploaded.path || prev.file_path }));
      setMessage(`File selected: ${uploaded.filename}`);
    } catch (err) {
      setMessage(`File upload failed: ${String(err)}`);
    } finally {
      setIsBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const onCreate = async () => {
    if (!form.preset_id) {
      setMessage('Preset is required. Choose a preset before creating CMD.');
      return;
    }
    if (!Number.isFinite(form.washing_time) || form.washing_time < 1) {
      setMessage('Washing Time (sec) is required (>=1).');
      return;
    }
    if (!Number.isFinite(form.curing_time) || form.curing_time < 1) {
      setMessage('Curing Time (sec) is required (>=1).');
      return;
    }
    setIsBusy(true);
    setMessage('');
    try {
      const r = await createAutomationCommand({
        preset_id: form.preset_id || undefined,
        washing_time: form.washing_time,
        curing_time: form.curing_time,
        target_printer: form.target_printer ? Number(form.target_printer) : undefined, // 260410 추가
      });
      setMessage(`CMD created: ${r.cmd_id}`);
      setShowCreateModal(false);
      await loadAll();
    } catch (e) {
      setMessage(`CMD create failed: ${String(e)}`);
    } finally {
      setIsBusy(false);
    }
  };

  const doControl = async (action: 'start' | 'stop' | 'pause' | 'resume') => {
    setIsBusy(true);
    setMessage('');
    try {
      await controlAutomation(action);
      await loadAll();
    } catch (e) {
      setMessage(`Control failed(${action}): ${String(e)}`);
    } finally {
      setIsBusy(false);
    }
  };

  const toggleSimul = async () => {
    setIsBusy(true);
    setMessage('');
    try {
      await setAutomationSimul(!state.simul_mode);
      await loadAll();
    } catch (e) {
      setMessage(`Simul toggle failed: ${String(e)}`);
    } finally {
      setIsBusy(false);
    }
  };

  const stateText = useMemo(() => {
    if (!state.running) return 'STOPPED';
    if (state.paused) return 'PAUSED';
    return 'RUNNING';
  }, [state]);

  const selectedCount = selectedCmdIds.length;
  const allVisibleSelected = items.length > 0 && selectedCount === items.length;

  const toggleSelectAll = () => {
    if (allVisibleSelected) {
      setSelectedCmdIds([]);
      return;
    }
    setSelectedCmdIds(items.map((it) => it.cmd_id));
  };

  const toggleSelectOne = (cmdId: string) => {
    setSelectedCmdIds((prev) => (prev.includes(cmdId) ? prev.filter((id) => id !== cmdId) : [...prev, cmdId]));
  };

  const markSelectedUseN = async () => {
    if (!selectedCmdIds.length) {
      setMessage('선택된 CMD가 없습니다.');
      return;
    }
    setIsBusy(true);
    setMessage('');
    try {
      const res = await updateAutomationCommandsUseYn(selectedCmdIds, 'N');
      setMessage(`use_yn=N 반영 완료: ${res.updated}건`);
      setSelectedCmdIds([]);
      await loadAll();
    } catch (e) {
      setMessage(`use_yn 변경 실패: ${String(e)}`);
    } finally {
      setIsBusy(false);
    }
  };

  const printerKeys = ['1', '2', '3', '4'];
  const washKeys = ['1', '2'];
  const cureKeys = ['1'];
  const activeJobEntries = Object.entries(queues.active_jobs || {});

  return (
    <div className="bg-gray-100">
      <header className="bg-white border-b">
        <div className="w-full px-[10%] py-2">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Automation</h2>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Simulation</span>
                <div
                  onClick={toggleSimul}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${state.simul_mode ? 'bg-indigo-600' : 'bg-gray-200'
                    }`}
                >
                  <span
                    className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${state.simul_mode ? 'translate-x-5' : 'translate-x-1'
                      }`}
                  />
                </div>
              </label>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowCreateModal(true)}
                className="px-3 py-1.5 text-sm border rounded-lg bg-white hover:bg-gray-50"
              >
                CMD Create
              </button>
              <button onClick={() => loadAll()} className="px-3 py-1.5 text-sm border rounded-lg bg-white hover:bg-gray-50">
                Refresh
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="w-full px-[10%] py-3">
        <div className="grid grid-cols-1 md:grid-cols-[20%_80%] gap-3">
          <section className="bg-white rounded-xl border p-3">
            <h3 className="font-semibold text-gray-900 mb-2">Sequence Control</h3>
            <p className="text-xs mb-2">
              State: <span className="font-semibold">{stateText}</span>
            </p>
            <div className="grid gap-1" style={{ gridTemplateColumns: '20% 80%' }}>
              <div className="text-xs text-gray-600 flex items-center">START</div>
              <button
                className="py-1.5 rounded bg-green-600 text-white text-xs disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isBusy}
                onClick={() => doControl('start')}
              >
                START
              </button>

              <div className="text-xs text-gray-600 flex items-center">STOP</div>
              <button className="py-1.5 rounded bg-red-600 text-white text-xs" disabled={isBusy} onClick={() => doControl('stop')}>STOP</button>

              <div className="text-xs text-gray-600 flex items-center">PAUSE</div>
              <button className="py-1.5 rounded bg-yellow-500 text-white text-xs" disabled={isBusy} onClick={() => doControl('pause')}>PAUSE</button>

              <div className="text-xs text-gray-600 flex items-center">RESUME</div>
              <button
                className="py-1.5 rounded bg-indigo-600 text-white text-xs disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isBusy}
                onClick={() => doControl('resume')}
              >
                RESUME
              </button>
            </div>
            <div className="mt-3 border-t pt-3">
              <div className="text-xs font-semibold text-gray-900 mb-2">Printers</div>
              <div className="space-y-2">
                {printers.length === 0 && (
                  <div className="text-xs text-gray-400">printer status unavailable</div>
                )}
                {printers.map((printer) => (
                  <div key={printer.serial} className="rounded-lg border px-2 py-2 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="font-semibold text-gray-900 truncate">
                          {printer.name || printerNicknameFromSerial(printer.serial)}
                        </div>
                        <div className="text-[11px] text-gray-500 truncate">{printer.serial}</div>
                      </div>
                      <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${printerStatusTone(printer)}`}>
                        {printer.status}
                      </span>
                    </div>
                    <div className="mt-1 grid grid-cols-2 gap-x-2 gap-y-1 text-[11px] text-gray-600">
                      <div>Ready: <span className="font-mono text-gray-800">{printer.ready_to_print || (printer.is_ready ? 'READY' : 'NOT_READY')}</span></div>
                      <div>Online: <span className="font-mono text-gray-800">{printer.is_online ? 'Y' : 'N'}</span></div>
                      <div>Progress: <span className="font-mono text-gray-800">{printer.progress_percent != null ? `${printer.progress_percent.toFixed(1)}%` : '-'}</span></div>
                      <div>Error: <span className="font-mono text-gray-800">{printer.has_error ? 'Y' : 'N'}</span></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="bg-white rounded-xl border p-3">
            <h3 className="font-semibold text-gray-900 mb-2">Queue Board</h3>
            <div className="mb-2 flex gap-2">
              <button
                className={`px-2 py-1 rounded text-xs border ${queueTab === 'board' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700'}`}
                onClick={() => setQueueTab('board')}
              >
                Queue Board
              </button>
              <button
                className={`px-2 py-1 rounded text-xs border ${queueTab === 'job' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700'}`}
                onClick={() => setQueueTab('job')}
              >
                Job Item
              </button>
            </div>

            {queueTab === 'board' && (
              <>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <div className="border rounded p-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600">Running</span>
                      <OnOffBadge on={!!queues.running} />
                    </div>
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-gray-600">Paused</span>
                      <OnOffBadge on={!!queues.paused} />
                    </div>
                  </div>
                  <div className="border rounded p-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-600">Robot Active</span>
                      <span className="font-mono text-[11px]">{queues.robot_active_cmd ? queues.robot_active_cmd.slice(0, 8) : '-'}</span>
                    </div>
                    <div className="mt-1">
                      <span className="text-gray-600">Robot Queue</span>
                      <div className="mt-1"><QueueChips items={(queues.robot_queue || []).map((t) => `${t.task_type}:${t.cmd_id}`)} /></div>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-2">
                  {printerKeys.map((k) => (
                    <div key={k} className="border rounded p-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold">Printer-{k}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-gray-600">Plate</span>
                          <OnOffBadge on={!!queues.printer_has_plate?.[k]} />
                          <span className="text-gray-600">Use</span>
                          <OnOffBadge on={(queues.printer_use?.[k] || 'N') === 'Y'} />
                        </div>
                      </div>
                      <div className="mt-1 flex items-center gap-2">
                        <span className="text-gray-600">Active:</span>
                        <span className="font-mono">{queues.printer_active_cmd?.[k] ? queues.printer_active_cmd?.[k]?.slice(0, 8) : '-'}</span>
                      </div>
                      <div className="mt-1">
                        <span className="text-gray-600">Queue</span>
                        <div className="mt-1"><QueueChips items={queues.printer_queues?.[k] || []} /></div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="grid grid-cols-2 gap-2 mt-2">
                  <div className="border rounded p-2 text-xs">
                    <div className="font-semibold mb-1">Wash</div>
                    <div className="grid grid-cols-2 gap-2">
                      {washKeys.map((k) => (
                        <div key={k} className="border rounded p-1.5 bg-gray-50">
                          <div className="text-[11px] text-gray-600">{`Wash-${k}`}</div>
                          <div className="font-mono">{queues.wash_active_cmd?.[k] ? queues.wash_active_cmd?.[k]?.slice(0, 8) : '-'}</div>
                        </div>
                      ))}
                    </div>
                    <div className="mt-1 text-gray-600">Waiting</div>
                    <div className="mt-1"><QueueChips items={queues.wash_waiting || []} /></div>
                  </div>
                  <div className="border rounded p-2 text-xs">
                    <div className="font-semibold mb-1">Cure</div>
                    <div className="grid grid-cols-2 gap-2">
                      {cureKeys.map((k) => (
                        <div key={k} className="border rounded p-1.5 bg-gray-50">
                          <div className="text-[11px] text-gray-600">{`Cure-${k}`}</div>
                          <div className="font-mono">{queues.cure_active_cmd?.[k] ? queues.cure_active_cmd?.[k]?.slice(0, 8) : '-'}</div>
                        </div>
                      ))}
                    </div>
                    <div className="mt-1 text-gray-600">Waiting</div>
                    <div className="mt-1"><QueueChips items={queues.cure_waiting || []} /></div>
                  </div>
                </div>
              </>
            )}

            {queueTab === 'job' && (
              <div className="space-y-2">
                <div className="border rounded p-2 text-xs">
                  <div className="font-semibold mb-1">RuntimeCtx</div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>running: <span className="font-mono">{String(!!queues.running)}</span></div>
                    <div>paused: <span className="font-mono">{String(!!queues.paused)}</span></div>
                    <div>active_job_count: <span className="font-mono">{queues.runtime_ctx?.active_job_count ?? 0}</span></div>
                    <div>robot_ack_count: <span className="font-mono">{queues.runtime_ctx?.robot_ack_count ?? 0}</span></div>
                  </div>
                </div>
                <div className="border rounded p-2 text-xs">
                  <div className="font-semibold mb-1">JobCtx Items</div>
                  {!activeJobEntries.length && <div className="text-gray-400">empty</div>}
                  {activeJobEntries.map(([cmdId, job]) => (
                    <div key={cmdId} className="border rounded p-2 mb-2 last:mb-0 bg-gray-50">
                      <div className="grid grid-cols-2 gap-2">
                        <div>cmd_id: <span className="font-mono">{job.cmd_id || cmdId}</span></div>
                        <div>file_name: <span className="font-mono">{job.file_name || '-'}</span></div>
                        <div>cmd_status: <span className="font-mono">{STATUS_LABELS[job.cmd_status] ?? job.cmd_status}</span></div>
                        <div>post_proc_stage: <span className="font-mono">{job.post_proc_stage}</span></div>
                        <div>target_printer: <span className="font-mono">{job.target_printer ?? '-'}</span></div>
                        <div>progress: <span className="font-mono">{job.progress ?? 0}%</span></div>
                        <div>washing_time(sec): <span className="font-mono">{job.washing_time ?? '-'}</span></div>
                        <div>curing_time(sec): <span className="font-mono">{job.curing_time ?? '-'}</span></div>
                        <div>preset_name: <span className="font-mono">{(() => { const v = parseAllocated(job.allocated_data)?.preset_name; return typeof v === 'string' ? v : '-'; })()}</span></div>
                        <div>material_code: <span className="font-mono">{(() => { const s = parseAllocated(job.allocated_data)?.print_settings as Record<string, unknown> | undefined; const v = s?.material_code; return typeof v === 'string' ? v : '-'; })()}</span></div>
                        <div>layer_thickness: <span className="font-mono">{(() => { const s = parseAllocated(job.allocated_data)?.print_settings as Record<string, unknown> | undefined; const v = s?.layer_thickness_mm; return typeof v === 'number' ? v : '-'; })()}</span></div>
                        <div className="col-span-2">file_path: <span className="font-mono">{job.file_path || '-'}</span></div>
                        <div className="col-span-2">message: <span className="font-mono">{job.message || '-'}</span></div>
                        <div className="col-span-2">allocated_data: <span className="font-mono">{job.allocated_data ? JSON.stringify(job.allocated_data) : '-'}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="bg-white rounded-xl border p-3 md:col-span-2">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="font-semibold text-gray-900">CMD Table</h3>
              <button
                className="px-3 py-1.5 rounded border text-xs bg-white hover:bg-gray-50 disabled:opacity-50"
                disabled={isBusy || selectedCount === 0}
                onClick={markSelectedUseN}
              >
                선택 항목 Use=N
              </button>
            </div>
            <div className="overflow-x-auto overflow-y-auto max-h-[340px]">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="text-left border-b">
                    <th className="py-2 pr-2">
                      <input type="checkbox" checked={allVisibleSelected} onChange={toggleSelectAll} />
                    </th>
                    <th className="py-2 pr-2">cmd_id</th>
                    <th className="py-2 pr-2">file_path</th>
                    <th className="py-2 pr-2">file_name</th>
                    <th className="py-2 pr-2">cmd_status</th>
                    <th className="py-2 pr-2">post_proc_stage</th>
                    <th className="py-2 pr-2">wash_minutes</th>
                    <th className="py-2 pr-2">washing_time</th>
                    <th className="py-2 pr-2">curing_time</th>
                    <th className="py-2 pr-2">use_yn</th>
                    <th className="py-2 pr-2">preset</th>
                    <th className="py-2 pr-2">material</th>
                    <th className="py-2 pr-2">layer</th>
                    <th className="py-2 pr-2">assigned_printer</th>
                    <th className="py-2 pr-2">assigned_curing</th>
                    <th className="py-2 pr-2">assigned_washing</th>
                    <th className="py-2 pr-2">progress</th>
                    <th className="py-2 pr-2">message</th>
                    <th className="py-2 pr-2">claimed_by</th>
                    <th className="py-2 pr-2">locked_at</th>
                    <th className="py-2 pr-2">created_at</th>
                    <th className="py-2 pr-2">updated_at</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it) => (
                    <tr key={it.cmd_id} className="border-b align-top">
                      <td className="py-2 pr-2">
                        <input
                          type="checkbox"
                          checked={selectedCmdIds.includes(it.cmd_id)}
                          onChange={() => toggleSelectOne(it.cmd_id)}
                        />
                      </td>
                      <td className="py-2 pr-2 font-mono">{it.cmd_id}</td>
                      <td className="py-2 pr-2 max-w-[260px] truncate">{it.file_path}</td>
                      <td className="py-2 pr-2">{it.file_name}</td>
                      <td className="py-2 pr-2">{STATUS_LABELS[it.cmd_status] ?? it.cmd_status}</td>
                      <td className="py-2 pr-2">{it.post_proc_stage}</td>
                      <td className="py-2 pr-2">{it.wash_minutes ?? '-'}</td>
                      <td className="py-2 pr-2">{it.washing_time ?? '-'}</td>
                      <td className="py-2 pr-2">{it.curing_time ?? '-'}</td>
                      <td className="py-2 pr-2">{it.use_yn ?? 'Y'}</td>
                      <td className="py-2 pr-2">{(() => { const v = parseAllocated(it.allocated_data)?.preset_name; return typeof v === 'string' ? v : '-'; })()}</td>
                      <td className="py-2 pr-2">{(() => { const s = parseAllocated(it.allocated_data)?.print_settings as Record<string, unknown> | undefined; const v = s?.material_code; return typeof v === 'string' ? v : '-'; })()}</td>
                      <td className="py-2 pr-2">{(() => { const s = parseAllocated(it.allocated_data)?.print_settings as Record<string, unknown> | undefined; const v = s?.layer_thickness_mm; return typeof v === 'number' ? v : '-'; })()}</td>
                      <td className="py-2 pr-2">{(() => { const v = parseAllocated(it.allocated_data)?.printer_id; return (typeof v === 'number' || typeof v === 'string') ? v : '-'; })()}</td>
                      <td className="py-2 pr-2">{(() => { const v = parseAllocated(it.allocated_data)?.cure_id; return (typeof v === 'number' || typeof v === 'string') ? v : '-'; })()}</td>
                      <td className="py-2 pr-2">{(() => { const v = parseAllocated(it.allocated_data)?.wash_id; return (typeof v === 'number' || typeof v === 'string') ? v : '-'; })()}</td>
                      <td className="py-2 pr-2">{it.progress}%</td>
                      <td className="py-2 pr-2 max-w-[220px] truncate">{it.message ?? '-'}</td>
                      <td className="py-2 pr-2">{it.claimed_by ?? '-'}</td>
                      <td className="py-2 pr-2">{it.locked_at ? new Date(it.locked_at).toLocaleString('ko-KR') : '-'}</td>
                      <td className="py-2 pr-2">{new Date(it.created_at).toLocaleString('ko-KR')}</td>
                      <td className="py-2 pr-2">{new Date(it.updated_at).toLocaleString('ko-KR')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="bg-white rounded-xl border p-3 md:col-span-2">
            <h3 className="font-semibold text-gray-900 mb-2">Automation Logs</h3>
            <div className="overflow-x-auto overflow-y-auto max-h-[240px]">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="text-left border-b">
                    <th className="py-2 pr-2">time</th>
                    <th className="py-2 pr-2">type</th>
                    <th className="py-2 pr-2">source</th>
                    <th className="py-2 pr-2">cmd_id</th>
                    <th className="py-2 pr-2">message</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id} className="border-b align-top">
                      <td className="py-2 pr-2 whitespace-nowrap">{new Date(log.created_at).toLocaleString('ko-KR')}</td>
                      <td className="py-2 pr-2">{LOG_TYPE_LABELS[log.log_type] ?? log.log_type}</td>
                      <td className="py-2 pr-2">{log.source}</td>
                      <td className="py-2 pr-2 font-mono">{log.cmd_id ? log.cmd_id.slice(0, 8) : '-'}</td>
                      <td className="py-2 pr-2">{log.message}</td>
                    </tr>
                  ))}
                  {!logs.length && (
                    <tr>
                      <td className="py-3 text-gray-400" colSpan={5}>no logs</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        {message && <div className="mt-4 text-sm text-gray-700">{message}</div>}
      </main>

      {showCreateModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl border w-full max-w-xl p-4">
            <h3 className="font-semibold text-gray-900 mb-3">CMD Create</h3>
            <div className="space-y-2">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={onChooseFile}
                  disabled
                  className="py-2 rounded-lg border text-sm bg-gray-100 text-gray-400 cursor-not-allowed disabled:opacity-100"
                >
                  Select File
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".stl,.obj,.form"
                  onChange={onSelectedFile}
                />
                <div className="text-xs text-gray-500 flex items-center">CMD Create uses preset only</div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Preset</label>
                <select
                  className="w-full border rounded px-3 py-2 text-sm"
                  value={form.preset_id}
                  onChange={(e) => {
                    const presetId = e.target.value;
                    const preset = presets.find((p) => p.id === presetId);
                    setForm((p) => ({
                      ...p,
                      preset_id: presetId,
                      file_path: preset?.stl_filename || p.file_path,
                    }));
                  }}
                >
                  <option value="">No preset</option>
                  {presets.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.name} / {preset.part_type}{preset.stl_filename ? ` / ${preset.stl_filename}` : ''}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">File Path</label>
                <input
                  className="w-full border rounded px-3 py-2 text-sm bg-gray-50"
                  placeholder="Choose Preset to fill this path"
                  value={form.file_path}
                  readOnly
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1">Washing Time (sec)</label>
                  <input
                    type="number"
                    min={1}
                    className="w-full border rounded px-3 py-2 text-sm"
                    value={form.washing_time}
                    onChange={(e) => setForm((p) => ({ ...p, washing_time: Number(e.target.value || 0) }))}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-600 mb-1">Curing Time (sec)</label>
                  <input
                    type="number"
                    min={1}
                    className="w-full border rounded px-3 py-2 text-sm"
                    value={form.curing_time}
                    onChange={(e) => setForm((p) => ({ ...p, curing_time: Number(e.target.value || 0) }))}
                  />
                </div>
                <div className="col-span-1 sm:col-span-2">
                  <label className="block text-xs font-semibold text-gray-600 mb-1">Target Printer</label>
                  <select
                    className="w-full border rounded px-3 py-2 text-sm"
                    value={form.target_printer}
                    onChange={(e) => setForm((p) => ({ ...p, target_printer: e.target.value === '' ? '' : Number(e.target.value) }))}
                  >
                    <option value="">Any Printer (공용/아무 프린터나)</option>
                    <option value="1">Printer 1 전용</option>
                    <option value="2">Printer 2 전용</option>
                    <option value="3">Printer 3 전용</option>
                    <option value="4">Printer 4 전용</option>
                  </select>
                </div>
              </div>
              <div className="flex gap-2 pt-2">
                <button disabled={isBusy || !form.preset_id} onClick={onCreate} className="flex-1 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50">CMD INSERT</button>
                <button disabled={isBusy} onClick={() => setShowCreateModal(false)} className="px-4 py-2 rounded-lg border text-sm hover:bg-gray-50">Close</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
