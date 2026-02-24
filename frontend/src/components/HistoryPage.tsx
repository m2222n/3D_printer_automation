/**
 * 이전 작업 내용 페이지
 * 프린트 히스토리 조회, 프린터별 필터, 재출력 기능
 * - 클라우드 이력: 상세 정보(오류/중단 메시지, 파트 목록) + 재출력
 * - 로컬 작업: 이 시스템으로 시작한 작업 이력
 */

import { useState, useEffect, useCallback } from 'react';
import { getPrintJobs, startPrintJob, getFiles, getNotesBulk, createNote, updateNote, deleteNote } from '../services/localApi';
import type { PrintNoteItem } from '../services/localApi';
import { getPrintHistory, getDashboard } from '../services/api';
import type { PrintJob, MaterialCode } from '../types/local';
import { getJobStatusLabel, MATERIAL_NAMES } from '../types/local';
import type { PrintHistoryItem, PrinterSummary, PrintStatus } from '../types/printer';

type HistoryFilter = 'all' | string; // 'all' or printer serial
type HistorySource = 'local' | 'cloud';
type OutcomeFilter = 'all' | 'success' | 'failed' | 'aborted';

export function HistoryPage() {
  const [localJobs, setLocalJobs] = useState<PrintJob[]>([]);
  const [cloudHistory, setCloudHistory] = useState<PrintHistoryItem[]>([]);
  const [cloudTotalCount, setCloudTotalCount] = useState(0);
  const [printers, setPrinters] = useState<PrinterSummary[]>([]);
  const [filter, setFilter] = useState<HistoryFilter>('all');
  const [source, setSource] = useState<HistorySource>('cloud');
  const [isLoading, setIsLoading] = useState(true);
  const [reprintingId, setReprintingId] = useState<string | null>(null);
  const [reprintSuccess, setReprintSuccess] = useState<string | null>(null);
  const [reprintError, setReprintError] = useState<string | null>(null);
  // 날짜 범위 필터
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  // Outcome 필터
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>('all');
  // Notes 메모
  const [notesMap, setNotesMap] = useState<Record<string, PrintNoteItem[]>>({});
  // 재출력 모달 상태 (클라우드 + 로컬 공용)
  const [reprintModal, setReprintModal] = useState<{
    item: PrintHistoryItem;
    selectedPrinter: string;
    mode: 'now' | 'queue';
    scheduledAt: string; // datetime-local 값 (KST)
    stlFile: string; // STL 파일명
    materialCode: string; // 재료 코드
    layerThickness: number; // 레이어 두께
  } | null>(null);
  // 로컬 재출력 모달 상태
  const [localReprintModal, setLocalReprintModal] = useState<{
    job: PrintJob;
    selectedPrinter: string;
    mode: 'now' | 'queue';
    scheduledAt: string;
    stlFile: string;
    materialCode: string;
    layerThickness: number;
  } | null>(null);
  // 업로드된 파일 목록 (STL 변경용)
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);

  // 데이터 로드
  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      // 백엔드 필터 구성
      const apiFilters: { printer_serial?: string; status?: string; date_from?: string; date_to?: string } = {};
      if (filter !== 'all') apiFilters.printer_serial = filter;
      if (outcomeFilter === 'success') apiFilters.status = 'FINISHED';
      else if (outcomeFilter === 'failed') apiFilters.status = 'ERROR';
      else if (outcomeFilter === 'aborted') apiFilters.status = 'ABORTED';
      if (dateFrom) apiFilters.date_from = new Date(dateFrom + 'T00:00:00+09:00').toISOString();
      if (dateTo) apiFilters.date_to = new Date(dateTo + 'T23:59:59+09:00').toISOString();

      const [jobList, history, dashboard, fileList] = await Promise.all([
        getPrintJobs(0, 100),
        getPrintHistory(1, 100, apiFilters).catch(() => ({ items: [], total_count: 0, page: 1, page_size: 100 })),
        getDashboard(),
        getFiles().catch(() => ({ files: [] })),
      ]);
      setLocalJobs(jobList);
      setCloudHistory(history.items);
      setCloudTotalCount(history.total_count);
      setPrinters(dashboard.printers);
      setUploadedFiles(fileList.files.map((f) => f.filename));

      // 클라우드 이력의 메모 일괄 조회
      if (history.items.length > 0) {
        const guids = history.items.map((item) => item.guid);
        getNotesBulk(guids).then(setNotesMap).catch(() => {});
      }
    } catch (err) {
      console.error('히스토리 로드 실패:', err);
    } finally {
      setIsLoading(false);
    }
  }, [filter, outcomeFilter, dateFrom, dateTo]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 완료/실패된 작업만 (local)
  const completedLocalJobs = localJobs.filter((job) => {
    const isDone = ['sent', 'failed'].includes(job.status);
    if (!isDone) return false;
    if (filter === 'all') return true;
    return job.printer_serial === filter;
  });

  // 클라우드 히스토리 (백엔드에서 필터링됨, 로컬 Outcome 추가 필터)
  const filteredCloudHistory = cloudHistory.filter((item) => {
    // 로컬 작업의 경우 프론트에서 Outcome 필터 적용 (날짜/프린터는 백엔드 처리)
    if (outcomeFilter === 'success' && item.status !== 'FINISHED') return false;
    if (outcomeFilter === 'failed' && item.status !== 'ERROR') return false;
    if (outcomeFilter === 'aborted' && item.status !== 'ABORTED') return false;
    return true;
  });

  // CSV Export
  const handleExportCSV = useCallback(() => {
    const items = source === 'cloud' ? filteredCloudHistory : completedLocalJobs;
    if (items.length === 0) return;

    const headers = ['작업명', '프린터', '상태', '시작 시간', '소요 시간(분)', '재료', '사용량(ml)', '레이어'];
    const rows = source === 'cloud'
      ? (items as PrintHistoryItem[]).map((item) => [
          item.name,
          getPrinterName(item.printer_serial),
          getCloudStatusLabel(item.status),
          item.started_at ? new Date(item.started_at).toLocaleString('ko-KR') : '',
          item.duration_minutes?.toString() || '',
          item.material_name || '',
          item.volume_ml?.toFixed(1) || '',
          item.layer_count.toString(),
        ])
      : (items as PrintJob[]).map((job) => [
          job.stl_filename,
          getPrinterName(job.printer_serial),
          getJobStatusLabel(job.status),
          new Date(job.created_at).toLocaleString('ko-KR'),
          '',
          MATERIAL_NAMES[job.settings.material_code as keyof typeof MATERIAL_NAMES] || '',
          '',
          '',
        ]);

    const bom = '\uFEFF';
    const csv = bom + [headers, ...rows].map((row) => row.map((cell) => `"${cell}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const dateStr = new Date().toISOString().slice(0, 10);
    a.download = `print_history_${dateStr}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [source, filteredCloudHistory, completedLocalJobs, printers]);

  // 날짜 퀵 필터
  const setQuickDateRange = useCallback((days: number) => {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - days);
    setDateFrom(from.toISOString().slice(0, 10));
    setDateTo(to.toISOString().slice(0, 10));
  }, []);

  const clearDateRange = useCallback(() => {
    setDateFrom('');
    setDateTo('');
  }, []);

  // 프린터 이름 가져오기
  const getPrinterName = (serial: string): string => {
    const printer = printers.find((p) => p.serial === serial);
    return printer?.name || serial;
  };

  // 로컬 작업 재출력 모달 열기
  const handleLocalReprint = useCallback((job: PrintJob) => {
    if (printers.length === 0) {
      setReprintError('등록된 프린터가 없습니다.');
      setTimeout(() => setReprintError(null), 3000);
      return;
    }

    setLocalReprintModal({
      job,
      selectedPrinter: job.printer_serial,
      mode: 'now',
      scheduledAt: '',
      stlFile: job.stl_filename,
      materialCode: job.settings.material_code || 'FLGPGR05',
      layerThickness: job.settings.layer_thickness_mm || 0.05,
    });
  }, [printers]);

  // 로컬 작업 재출력 실행
  const handleLocalReprintConfirm = useCallback(async () => {
    if (!localReprintModal) return;
    const { job, selectedPrinter, mode, scheduledAt, stlFile, materialCode, layerThickness } = localReprintModal;

    const printerInfo = printers.find((p) => p.serial === selectedPrinter);
    if (mode === 'now' && printerInfo?.status !== 'IDLE') {
      setReprintError(`${getPrinterName(selectedPrinter)}은(는) 현재 대기 중이 아닙니다. 예약을 사용하세요.`);
      setTimeout(() => setReprintError(null), 5000);
      return;
    }

    if (mode === 'queue' && scheduledAt) {
      const scheduledDate = new Date(scheduledAt);
      if (scheduledDate <= new Date()) {
        setReprintError('예약 시간은 현재 시간 이후여야 합니다.');
        setTimeout(() => setReprintError(null), 5000);
        return;
      }
    }

    setReprintingId(job.id);
    setReprintError(null);
    setReprintSuccess(null);
    setLocalReprintModal(null);

    try {
      let scheduledAtISO: string | undefined;
      if (mode === 'queue' && scheduledAt) {
        scheduledAtISO = scheduledAt + ':00+09:00';
      }

      await startPrintJob({
        preset_id: job.preset_id || undefined,
        stl_file: stlFile,
        printer_serial: selectedPrinter,
        scheduled_at: scheduledAtISO,
        settings: {
          ...job.settings,
          material_code: materialCode as MaterialCode,
          layer_thickness_mm: layerThickness,
        },
      });

      const actionLabel = mode === 'now' ? '재출력 작업이 시작되었습니다' : '예약 작업이 대기열에 추가되었습니다';
      setReprintSuccess(`"${stlFile}" ${actionLabel}.`);
      setTimeout(() => setReprintSuccess(null), 5000);
      await loadData();
    } catch (err) {
      setReprintError(err instanceof Error ? err.message : '재출력 실패');
      setTimeout(() => setReprintError(null), 5000);
    } finally {
      setReprintingId(null);
    }
  }, [localReprintModal, printers, loadData]);

  // 클라우드 이력 재출력 모달 열기
  const openReprintModal = (item: PrintHistoryItem) => {
    if (printers.length === 0) {
      setReprintError('등록된 프린터가 없습니다.');
      setTimeout(() => setReprintError(null), 3000);
      return;
    }
    // 기본 STL 파일명 추출
    const defaultStl = item.parts.length > 0
      ? item.parts[0].display_name + '.stl'
      : item.name + '.stl';

    // 기본: 같은 프린터, 모드: 바로 출력
    setReprintModal({
      item,
      selectedPrinter: item.printer_serial,
      mode: 'now',
      scheduledAt: '',
      stlFile: defaultStl,
      materialCode: item.material_code || 'FLGPGR05',
      layerThickness: 0.05,
    });
  };

  // 클라우드 이력 재출력 실행
  const handleCloudReprint = useCallback(async () => {
    if (!reprintModal) return;
    const { item, selectedPrinter, mode, scheduledAt, stlFile, materialCode, layerThickness } = reprintModal;

    const printerInfo = printers.find((p) => p.serial === selectedPrinter);
    if (mode === 'now' && printerInfo?.status !== 'IDLE') {
      setReprintError(`${getPrinterName(selectedPrinter)}은(는) 현재 대기 중이 아닙니다. 예약을 사용하세요.`);
      setTimeout(() => setReprintError(null), 5000);
      return;
    }

    // 예약 모드에서 시간 미지정 시 경고
    if (mode === 'queue' && scheduledAt) {
      const scheduledDate = new Date(scheduledAt);
      if (scheduledDate <= new Date()) {
        setReprintError('예약 시간은 현재 시간 이후여야 합니다.');
        setTimeout(() => setReprintError(null), 5000);
        return;
      }
    }

    setReprintingId(item.guid);
    setReprintError(null);
    setReprintSuccess(null);
    setReprintModal(null);

    try {
      // 예약 시간 처리 (KST → ISO 문자열)
      let scheduledAtISO: string | undefined;
      if (mode === 'queue' && scheduledAt) {
        // datetime-local은 로컬 시간이므로 KST로 간주하여 +09:00 추가
        scheduledAtISO = scheduledAt + ':00+09:00';
      }

      await startPrintJob({
        stl_file: stlFile,
        printer_serial: selectedPrinter,
        scheduled_at: scheduledAtISO,
        settings: {
          material_code: materialCode,
          layer_thickness_mm: layerThickness,
          source: 'cloud_reprint',
          original_guid: item.guid,
        } as unknown as import('../types/local').PrintSettings,
      });

      const actionLabel = mode === 'now' ? '재출력 작업이 시작되었습니다' : '예약 작업이 대기열에 추가되었습니다';
      setReprintSuccess(`"${item.name}" ${actionLabel}.`);
      setTimeout(() => setReprintSuccess(null), 5000);
      await loadData();
    } catch (err) {
      setReprintError(err instanceof Error ? err.message : '재출력 실패');
      setTimeout(() => setReprintError(null), 5000);
    } finally {
      setReprintingId(null);
    }
  }, [reprintModal, printers, loadData]);

  return (
    <div className="bg-gray-100">
      {/* 서브 헤더 */}
      <header className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">
              이전 작업 내용
            </h2>
            <div className="flex items-center gap-2">
              {/* 소스 토글 */}
              <div className="flex bg-gray-100 rounded-lg p-0.5">
                <button
                  onClick={() => setSource('local')}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    source === 'local' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'
                  }`}
                >
                  로컬 작업
                </button>
                <button
                  onClick={() => setSource('cloud')}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    source === 'cloud' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'
                  }`}
                >
                  클라우드 이력
                </button>
              </div>
              <button
                onClick={loadData}
                disabled={isLoading}
                className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
              >
                <svg
                  className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* 프린터 필터 탭 */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-1 overflow-x-auto scrollbar-hide">
            <button
              onClick={() => setFilter('all')}
              className={`py-2.5 px-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                filter === 'all'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              전체
            </button>
            {printers.map((printer) => (
              <button
                key={printer.serial}
                onClick={() => setFilter(printer.serial)}
                className={`py-2.5 px-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                  filter === printer.serial
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {printer.name}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 필터 바 */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex flex-wrap items-center gap-3">
            {/* 날짜 범위 */}
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                placeholder="시작일"
              />
              <span className="text-gray-400 text-sm">~</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                placeholder="종료일"
              />
            </div>

            {/* 퀵 날짜 버튼 */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => setQuickDateRange(30)}
                className={`px-2.5 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                  dateFrom && dateTo ? 'border-gray-200 text-gray-500 hover:bg-gray-50' : 'border-gray-200 text-gray-500 hover:bg-gray-50'
                }`}
              >
                Last 30 Days
              </button>
              <button
                onClick={() => setQuickDateRange(90)}
                className="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors"
              >
                Last 90 Days
              </button>
              {(dateFrom || dateTo) && (
                <button
                  onClick={clearDateRange}
                  className="px-2.5 py-1.5 text-xs font-medium rounded-lg text-red-500 hover:bg-red-50 transition-colors"
                >
                  초기화
                </button>
              )}
            </div>

            {/* 구분선 */}
            <div className="h-6 w-px bg-gray-200 hidden sm:block" />

            {/* Outcome 필터 */}
            <div className="flex items-center gap-1">
              {([
                { key: 'all', label: '전체' },
                { key: 'success', label: '성공' },
                { key: 'failed', label: '실패' },
                { key: 'aborted', label: '중단' },
              ] as const).map((opt) => (
                <button
                  key={opt.key}
                  onClick={() => setOutcomeFilter(opt.key)}
                  className={`px-2.5 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                    outcomeFilter === opt.key
                      ? opt.key === 'success' ? 'border-green-500 bg-green-50 text-green-700'
                        : opt.key === 'failed' ? 'border-red-500 bg-red-50 text-red-700'
                        : opt.key === 'aborted' ? 'border-orange-500 bg-orange-50 text-orange-700'
                        : 'border-blue-500 bg-blue-50 text-blue-700'
                      : 'border-gray-200 text-gray-500 hover:bg-gray-50'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {/* 구분선 */}
            <div className="flex-1" />

            {/* CSV Export */}
            <button
              onClick={handleExportCSV}
              disabled={
                (source === 'cloud' ? filteredCloudHistory.length : completedLocalJobs.length) === 0
              }
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              CSV Export
            </button>
          </div>
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* 알림 메시지 */}
        {reprintSuccess && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
            {reprintSuccess}
          </div>
        )}
        {reprintError && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {reprintError}
          </div>
        )}

        {isLoading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-3 text-gray-500">이전 작업을 불러오는 중...</p>
          </div>
        ) : source === 'local' ? (
          /* 로컬 작업 히스토리 */
          completedLocalJobs.length === 0 ? (
            <EmptyState message="완료된 로컬 작업이 없습니다" sub="이 시스템으로 프린트를 시작하면 이곳에 기록됩니다" />
          ) : (
            <div className="space-y-2">
              <p className="text-sm text-gray-500 mb-3">
                총 {completedLocalJobs.length}건
              </p>
              {completedLocalJobs.map((job) => (
                <LocalJobCard
                  key={job.id}
                  job={job}
                  printerName={getPrinterName(job.printer_serial)}
                  onReprint={() => handleLocalReprint(job)}
                  isReprinting={reprintingId === job.id}
                />
              ))}
            </div>
          )
        ) : (
          /* 클라우드 이력 */
          filteredCloudHistory.length === 0 ? (
            <EmptyState message="클라우드 프린트 이력이 없습니다" />
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-gray-500 mb-3">
                총 {cloudTotalCount}건{filteredCloudHistory.length !== cloudTotalCount ? ` (표시: ${filteredCloudHistory.length}건)` : ''}
                {(dateFrom || dateTo || outcomeFilter !== 'all' || filter !== 'all') && (
                  <span className="text-blue-500 ml-2">필터 적용됨</span>
                )}
              </p>
              {filteredCloudHistory.map((item) => (
                <CloudHistoryCard
                  key={item.guid}
                  item={item}
                  printerName={getPrinterName(item.printer_serial)}
                  onReprint={() => openReprintModal(item)}
                  isReprinting={reprintingId === item.guid}
                  notes={notesMap[item.guid] || []}
                  onAddNote={async (content) => {
                    const note = await createNote(item.guid, content);
                    setNotesMap((prev) => ({
                      ...prev,
                      [item.guid]: [note, ...(prev[item.guid] || [])],
                    }));
                  }}
                  onUpdateNote={async (noteId, content) => {
                    const updated = await updateNote(noteId, content);
                    setNotesMap((prev) => ({
                      ...prev,
                      [item.guid]: (prev[item.guid] || []).map((n) =>
                        n.id === noteId ? { ...n, content: updated.content, updated_at: updated.updated_at } : n
                      ),
                    }));
                  }}
                  onDeleteNote={async (noteId) => {
                    await deleteNote(noteId);
                    setNotesMap((prev) => ({
                      ...prev,
                      [item.guid]: (prev[item.guid] || []).filter((n) => n.id !== noteId),
                    }));
                  }}
                />
              ))}
            </div>
          )
        )}
      </main>

      {/* 클라우드 재출력 모달 */}
      {reprintModal && (
        <ReprintModal
          title={reprintModal.item.name}
          printers={printers}
          selectedPrinter={reprintModal.selectedPrinter}
          mode={reprintModal.mode}
          scheduledAt={reprintModal.scheduledAt}
          stlFile={reprintModal.stlFile}
          materialCode={reprintModal.materialCode}
          layerThickness={reprintModal.layerThickness}
          uploadedFiles={uploadedFiles}
          partInfo={reprintModal.item.parts.length > 0 ? reprintModal.item.parts.map((p) => p.display_name).join(', ') : undefined}
          onPrinterChange={(serial) => {
            const printer = printers.find((p) => p.serial === serial);
            setReprintModal({
              ...reprintModal,
              selectedPrinter: serial,
              ...(printer?.cartridge_material_code ? { materialCode: printer.cartridge_material_code } : {}),
            });
          }}
          onModeChange={(mode) => setReprintModal({ ...reprintModal, mode })}
          onScheduledAtChange={(val) => setReprintModal({ ...reprintModal, scheduledAt: val })}
          onStlFileChange={(val) => setReprintModal({ ...reprintModal, stlFile: val })}
          onMaterialCodeChange={(val) => setReprintModal({ ...reprintModal, materialCode: val })}
          onLayerThicknessChange={(val) => setReprintModal({ ...reprintModal, layerThickness: val })}
          onConfirm={handleCloudReprint}
          onCancel={() => setReprintModal(null)}
        />
      )}

      {/* 로컬 재출력 모달 */}
      {localReprintModal && (
        <ReprintModal
          title={localReprintModal.job.stl_filename}
          printers={printers}
          selectedPrinter={localReprintModal.selectedPrinter}
          mode={localReprintModal.mode}
          scheduledAt={localReprintModal.scheduledAt}
          stlFile={localReprintModal.stlFile}
          materialCode={localReprintModal.materialCode}
          layerThickness={localReprintModal.layerThickness}
          uploadedFiles={uploadedFiles}
          onPrinterChange={(serial) => {
            const printer = printers.find((p) => p.serial === serial);
            setLocalReprintModal({
              ...localReprintModal,
              selectedPrinter: serial,
              ...(printer?.cartridge_material_code ? { materialCode: printer.cartridge_material_code } : {}),
            });
          }}
          onModeChange={(mode) => setLocalReprintModal({ ...localReprintModal, mode })}
          onScheduledAtChange={(val) => setLocalReprintModal({ ...localReprintModal, scheduledAt: val })}
          onStlFileChange={(val) => setLocalReprintModal({ ...localReprintModal, stlFile: val })}
          onMaterialCodeChange={(val) => setLocalReprintModal({ ...localReprintModal, materialCode: val })}
          onLayerThicknessChange={(val) => setLocalReprintModal({ ...localReprintModal, layerThickness: val })}
          onConfirm={handleLocalReprintConfirm}
          onCancel={() => setLocalReprintModal(null)}
        />
      )}
    </div>
  );
}

// ===========================================
// 로컬 작업 카드
// ===========================================

function LocalJobCard({
  job,
  printerName,
  onReprint,
  isReprinting,
}: {
  job: PrintJob;
  printerName: string;
  onReprint: () => void;
  isReprinting: boolean;
}) {
  const isSent = job.status === 'sent';
  const isFailed = job.status === 'failed';

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-sm transition-shadow">
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="font-medium text-gray-900 truncate">{job.stl_filename}</p>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
              isSent ? 'bg-green-100 text-green-700' :
              isFailed ? 'bg-red-100 text-red-700' :
              'bg-gray-100 text-gray-700'
            }`}>
              {getJobStatusLabel(job.status)}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-xs text-gray-500">{printerName}</span>
            <span className="text-gray-300">|</span>
            <span className="text-xs text-gray-400">
              {new Date(job.created_at).toLocaleString('ko-KR')}
            </span>
            {job.error_message && (
              <>
                <span className="text-gray-300">|</span>
                <span className="text-xs text-red-500">{job.error_message}</span>
              </>
            )}
          </div>
        </div>

        <button
          onClick={onReprint}
          disabled={isReprinting}
          className={`flex-shrink-0 ml-4 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            isReprinting
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-blue-50 text-blue-600 hover:bg-blue-100'
          }`}
        >
          {isReprinting ? (
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
              처리 중
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <ReprintIcon />
              재출력
            </span>
          )}
        </button>
      </div>
    </div>
  );
}

// ===========================================
// 클라우드 히스토리 카드 (상세 정보 포함)
// ===========================================

function CloudHistoryCard({
  item,
  printerName,
  onReprint,
  isReprinting,
  notes,
  onAddNote,
  onUpdateNote,
  onDeleteNote,
}: {
  item: PrintHistoryItem;
  printerName: string;
  onReprint: () => void;
  isReprinting: boolean;
  notes: PrintNoteItem[];
  onAddNote: (content: string) => Promise<void>;
  onUpdateNote: (noteId: string, content: string) => Promise<void>;
  onDeleteNote: (noteId: string) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [newNote, setNewNote] = useState('');
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);
  const isError = item.status === 'ERROR';
  const isAborted = item.status === 'ABORTED';
  const hasIssue = isError || isAborted;

  const borderColor = isError ? 'border-red-200' :
    isAborted ? 'border-orange-200' : 'border-gray-200';

  return (
    <div className={`bg-white rounded-lg border ${borderColor} overflow-hidden hover:shadow-sm transition-shadow`}>
      {/* 메인 영역 */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          {/* 좌측: 썸네일 + 정보 */}
          <div className="flex gap-3 flex-1 min-w-0">
            {/* 썸네일 */}
            {item.thumbnail_url && (
              <div className="flex-shrink-0 w-14 h-14 rounded-lg overflow-hidden bg-gray-100 border">
                <img
                  src={item.thumbnail_url}
                  alt={item.name}
                  className="w-full h-full object-cover"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
              </div>
            )}

            <div className="flex-1 min-w-0">
              {/* 제목 + 상태 */}
              <div className="flex items-center gap-2 flex-wrap">
                <p className="font-medium text-gray-900 truncate">{item.name}</p>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${getCloudStatusStyle(item.status)}`}>
                  {getCloudStatusLabel(item.status)}
                </span>
                {item.print_run_success === 'SUCCESS' && (
                  <span className="text-green-500 text-xs flex-shrink-0">&#10003;</span>
                )}
              </div>

              {/* 메타 정보 */}
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <span className="text-xs text-gray-500">{printerName}</span>
                {item.started_at && (
                  <>
                    <span className="text-gray-300">|</span>
                    <span className="text-xs text-gray-400">
                      {new Date(item.started_at).toLocaleString('ko-KR')}
                    </span>
                  </>
                )}
                {item.duration_minutes != null && item.duration_minutes > 0 && (
                  <>
                    <span className="text-gray-300">|</span>
                    <span className="text-xs text-gray-400">
                      {item.duration_minutes < 60
                        ? `${item.duration_minutes}분`
                        : `${Math.floor(item.duration_minutes / 60)}시간 ${item.duration_minutes % 60}분`
                      }
                    </span>
                  </>
                )}
                {item.material_name && (
                  <>
                    <span className="text-gray-300">|</span>
                    <span className="text-xs text-gray-400">{item.material_name}</span>
                  </>
                )}
                {item.volume_ml != null && (
                  <>
                    <span className="text-gray-300">|</span>
                    <span className="text-xs text-gray-400">{item.volume_ml.toFixed(1)}ml</span>
                  </>
                )}
                {item.layer_count > 0 && (
                  <>
                    <span className="text-gray-300">|</span>
                    <span className="text-xs text-gray-400">{item.layer_count} 레이어</span>
                  </>
                )}
              </div>

              {/* 오류/중단 메시지 - 항상 표시 */}
              {hasIssue && (
                <div className={`mt-2 px-2.5 py-1.5 rounded text-xs ${
                  isError ? 'bg-red-50 text-red-700' : 'bg-orange-50 text-orange-700'
                }`}>
                  <span className="font-medium">{isError ? '오류' : '중단'}:</span>{' '}
                  {item.message || (isError ? '상세 오류 정보가 없습니다' : '사용자에 의해 중단되었습니다')}
                </div>
              )}
            </div>
          </div>

          {/* 우측: 버튼 영역 */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {/* 메모 버튼 */}
            <button
              onClick={() => setShowNotes(!showNotes)}
              className={`p-1.5 rounded transition-colors ${
                showNotes ? 'text-blue-600 bg-blue-50' : notes.length > 0 ? 'text-blue-500 hover:text-blue-600' : 'text-gray-400 hover:text-gray-600'
              }`}
              title={`메모 ${notes.length > 0 ? `(${notes.length})` : ''}`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
              </svg>
              {notes.length > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-blue-500 text-white text-[10px] rounded-full flex items-center justify-center">
                  {notes.length}
                </span>
              )}
            </button>

            {/* 상세 보기 토글 */}
            {item.parts.length > 0 && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="p-1.5 text-gray-400 hover:text-gray-600 rounded transition-colors"
                title="상세 보기"
              >
                <svg className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            )}

            {/* 재출력 버튼 */}
            <button
              onClick={onReprint}
              disabled={isReprinting}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                isReprinting
                  ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  : 'bg-blue-50 text-blue-600 hover:bg-blue-100'
              }`}
            >
              {isReprinting ? (
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                  처리 중
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <ReprintIcon />
                  재출력
                </span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* 확장: 상세 정보 (Activity Log + 파트) */}
      {expanded && (
        <div className="border-t bg-gray-50 px-4 py-3 space-y-3">
          {/* Activity Log 타임라인 */}
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">Activity Log</p>
            <div className="space-y-0">
              {buildActivityLog(item).map((event, idx) => (
                <div key={idx} className="flex gap-3 items-start">
                  <div className="flex flex-col items-center">
                    <div className={`w-2 h-2 rounded-full mt-1.5 ${event.color}`} />
                    {idx < buildActivityLog(item).length - 1 && <div className="w-px h-6 bg-gray-200" />}
                  </div>
                  <div className="flex-1 pb-2">
                    <p className="text-xs text-gray-700">{event.label}</p>
                    {event.time && <p className="text-[10px] text-gray-400">{event.time}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 파트 목록 */}
          {item.parts.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2">포함된 파트 ({item.parts.length}개)</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                {item.parts.map((part, idx) => (
                  <div key={idx} className="flex items-center justify-between text-xs bg-white rounded px-2.5 py-1.5 border border-gray-100">
                    <span className="text-gray-700 truncate">{part.display_name}</span>
                    {part.volume_ml != null && (
                      <span className="text-gray-400 ml-2 flex-shrink-0">{part.volume_ml.toFixed(1)}ml</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 메모 패널 */}
      {showNotes && (
        <div className="border-t bg-blue-50/50 px-4 py-3">
          <p className="text-xs font-medium text-gray-600 mb-2">메모</p>

          {/* 기존 메모 목록 */}
          {notes.length > 0 && (
            <div className="space-y-1.5 mb-2">
              {notes.map((note) => (
                <div key={note.id} className="flex items-start gap-2 text-xs bg-white rounded-lg px-3 py-2 border border-gray-100">
                  {editingNoteId === note.id ? (
                    <div className="flex-1">
                      <textarea
                        value={editingContent}
                        onChange={(e) => setEditingContent(e.target.value)}
                        className="w-full px-2 py-1 border border-blue-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
                        rows={2}
                      />
                      <div className="flex gap-1 mt-1">
                        <button
                          onClick={async () => {
                            if (!editingContent.trim()) return;
                            setNoteLoading(true);
                            try {
                              await onUpdateNote(note.id, editingContent.trim());
                              setEditingNoteId(null);
                            } finally {
                              setNoteLoading(false);
                            }
                          }}
                          disabled={noteLoading}
                          className="px-2 py-0.5 bg-blue-500 text-white rounded text-xs hover:bg-blue-600 disabled:opacity-50"
                        >
                          저장
                        </button>
                        <button
                          onClick={() => setEditingNoteId(null)}
                          className="px-2 py-0.5 text-gray-500 hover:text-gray-700 text-xs"
                        >
                          취소
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <p className="flex-1 text-gray-700 whitespace-pre-wrap">{note.content}</p>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <span className="text-gray-400 text-[10px]">
                          {note.created_at ? new Date(note.created_at).toLocaleDateString('ko-KR') : ''}
                        </span>
                        <button
                          onClick={() => { setEditingNoteId(note.id); setEditingContent(note.content); }}
                          className="p-0.5 text-gray-400 hover:text-blue-500"
                          title="수정"
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                          </svg>
                        </button>
                        <button
                          onClick={async () => {
                            setNoteLoading(true);
                            try { await onDeleteNote(note.id); } finally { setNoteLoading(false); }
                          }}
                          className="p-0.5 text-gray-400 hover:text-red-500"
                          title="삭제"
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* 새 메모 입력 */}
          <div className="flex gap-2">
            <input
              type="text"
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newNote.trim()) {
                  setNoteLoading(true);
                  onAddNote(newNote.trim()).then(() => setNewNote('')).finally(() => setNoteLoading(false));
                }
              }}
              placeholder="메모 추가..."
              className="flex-1 px-2.5 py-1.5 border border-gray-200 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white"
            />
            <button
              onClick={async () => {
                if (!newNote.trim()) return;
                setNoteLoading(true);
                try {
                  await onAddNote(newNote.trim());
                  setNewNote('');
                } finally {
                  setNoteLoading(false);
                }
              }}
              disabled={!newNote.trim() || noteLoading}
              className="px-3 py-1.5 bg-blue-500 text-white text-xs rounded-lg hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              추가
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ===========================================
// 재출력 모달
// ===========================================

function ReprintModal({
  title,
  printers,
  selectedPrinter,
  mode,
  scheduledAt,
  stlFile,
  materialCode,
  layerThickness,
  uploadedFiles,
  partInfo,
  onPrinterChange,
  onModeChange,
  onScheduledAtChange,
  onStlFileChange,
  onMaterialCodeChange,
  onLayerThicknessChange,
  onConfirm,
  onCancel,
}: {
  title: string;
  printers: PrinterSummary[];
  selectedPrinter: string;
  mode: 'now' | 'queue';
  scheduledAt: string;
  stlFile: string;
  materialCode: string;
  layerThickness: number;
  uploadedFiles: string[];
  partInfo?: string;
  onPrinterChange: (serial: string) => void;
  onModeChange: (mode: 'now' | 'queue') => void;
  onScheduledAtChange: (val: string) => void;
  onStlFileChange: (val: string) => void;
  onMaterialCodeChange: (val: string) => void;
  onLayerThicknessChange: (val: number) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [showSettings, setShowSettings] = useState(false);
  const selectedPrinterInfo = printers.find((p) => p.serial === selectedPrinter);
  const canPrintNow = selectedPrinterInfo?.status === 'IDLE';

  // KST 시간 picker 로컬 상태
  const now = new Date();
  const [schedDate, setSchedDate] = useState(() => {
    if (scheduledAt) return scheduledAt.slice(0, 10);
    // 기본: 오늘 날짜 (KST)
    const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
    return kst.toISOString().slice(0, 10);
  });
  const [schedAmPm, setSchedAmPm] = useState<'AM' | 'PM'>(() => {
    if (scheduledAt) {
      const h = parseInt(scheduledAt.slice(11, 13), 10);
      return h >= 12 ? 'PM' : 'AM';
    }
    return 'AM';
  });
  const [schedHour, setSchedHour] = useState(() => {
    if (scheduledAt) {
      let h = parseInt(scheduledAt.slice(11, 13), 10);
      if (h === 0) h = 12;
      else if (h > 12) h -= 12;
      return h;
    }
    return 9; // 기본 오전 9시
  });
  const [schedMinute, setSchedMinute] = useState(() => {
    if (scheduledAt) return parseInt(scheduledAt.slice(14, 16), 10);
    return 0;
  });
  const [schedEnabled, setSchedEnabled] = useState(!!scheduledAt);

  // 로컬 state → 부모에 전달
  useEffect(() => {
    if (!schedEnabled) {
      if (scheduledAt !== '') onScheduledAtChange('');
      return;
    }
    // 12시간 → 24시간 변환
    let h24 = schedHour;
    if (schedAmPm === 'AM') {
      if (h24 === 12) h24 = 0;
    } else {
      if (h24 !== 12) h24 += 12;
    }
    const hh = h24.toString().padStart(2, '0');
    const mm = schedMinute.toString().padStart(2, '0');
    const val = `${schedDate}T${hh}:${mm}`;
    if (val !== scheduledAt) onScheduledAtChange(val);
  }, [schedEnabled, schedDate, schedAmPm, schedHour, schedMinute]);

  // 오늘 날짜 (KST, date input min용)
  const todayKST = new Date(now.getTime() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);

  // 재료 목록
  const materialOptions: { code: string; name: string }[] = Object.entries(MATERIAL_NAMES).map(
    ([code, name]) => ({ code, name })
  );

  // 레이어 두께 옵션
  const layerOptions = [
    { value: 0.025, label: '25μm (최고 품질)' },
    { value: 0.05, label: '50μm (고품질)' },
    { value: 0.1, label: '100μm (표준)' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 overflow-hidden max-h-[90vh] flex flex-col">
        {/* 헤더 */}
        <div className="px-6 py-4 border-b bg-gray-50 flex-shrink-0">
          <h3 className="font-semibold text-gray-900">재출력</h3>
          <p className="text-sm text-gray-500 mt-0.5 truncate">{title}</p>
        </div>

        <div className="px-6 py-4 space-y-4 overflow-y-auto flex-1">
          {/* 프린터 선택 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">프린터 선택</label>
            <div className="space-y-1.5">
              {printers.map((printer) => (
                <label
                  key={printer.serial}
                  className={`flex items-center gap-3 p-2.5 rounded-lg border cursor-pointer transition-colors ${
                    selectedPrinter === printer.serial
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <input
                    type="radio"
                    name="printer"
                    value={printer.serial}
                    checked={selectedPrinter === printer.serial}
                    onChange={() => onPrinterChange(printer.serial)}
                    className="text-blue-600"
                  />
                  <div className="flex-1">
                    <div className="flex items-center">
                      <span className="text-sm font-medium text-gray-900">{printer.name}</span>
                      <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${
                        printer.status === 'IDLE' ? 'bg-green-100 text-green-700' :
                        printer.status === 'PRINTING' ? 'bg-blue-100 text-blue-700' :
                        'bg-gray-100 text-gray-700'
                      }`}>
                        {printer.status === 'IDLE' ? '대기 중' :
                         printer.status === 'PRINTING' ? '출력 중' : printer.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500">
                      {printer.cartridge_material_name && (
                        <span>레진: {printer.cartridge_material_name}</span>
                      )}
                      {printer.resin_remaining_ml != null && (
                        <span className={printer.is_resin_low ? 'text-red-500 font-medium' : ''}>
                          잔량: {printer.resin_remaining_ml.toFixed(0)}ml
                          {printer.resin_remaining_percent != null && ` (${printer.resin_remaining_percent.toFixed(0)}%)`}
                        </span>
                      )}
                      {!printer.cartridge_material_name && printer.resin_remaining_ml == null && (
                        <span className="text-gray-400">카트리지 정보 없음</span>
                      )}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* 출력 모드 선택 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">출력 방식</label>
            <div className="flex gap-2">
              <button
                onClick={() => onModeChange('now')}
                className={`flex-1 py-2.5 px-3 rounded-lg text-sm font-medium border transition-colors ${
                  mode === 'now'
                    ? 'border-blue-500 bg-blue-50 text-blue-700'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                }`}
              >
                바로 출력
                {!canPrintNow && mode === 'now' && (
                  <p className="text-xs text-red-500 mt-0.5">프린터가 대기 중이 아닙니다</p>
                )}
              </button>
              <button
                onClick={() => onModeChange('queue')}
                className={`flex-1 py-2.5 px-3 rounded-lg text-sm font-medium border transition-colors ${
                  mode === 'queue'
                    ? 'border-blue-500 bg-blue-50 text-blue-700'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                }`}
              >
                예약 (대기열)
              </button>
            </div>
          </div>

          {/* 예약 시간 선택 (예약 모드일 때만) */}
          {mode === 'queue' && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-sm font-medium text-gray-700">
                  예약 날짜 (KST)
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={schedEnabled}
                    onChange={(e) => setSchedEnabled(e.target.checked)}
                    className="rounded text-blue-600"
                  />
                  <span className="text-xs text-gray-500">시간 지정</span>
                </label>
              </div>

              {schedEnabled ? (
                <div className="space-y-2">
                  {/* 예약 날짜 (달력) */}
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">예약 날짜</label>
                    <input
                      type="date"
                      value={schedDate}
                      onChange={(e) => setSchedDate(e.target.value)}
                      min={todayKST}
                      className="w-full px-2.5 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                    />
                  </div>

                  {/* 시간 선택: 오전/오후 + 시 + 분 */}
                  <div className="flex gap-2">
                    {/* 오전/오후 */}
                    <select
                      value={schedAmPm}
                      onChange={(e) => setSchedAmPm(e.target.value as 'AM' | 'PM')}
                      className="px-2.5 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      <option value="AM">오전</option>
                      <option value="PM">오후</option>
                    </select>

                    {/* 시 (1~12) */}
                    <select
                      value={schedHour}
                      onChange={(e) => setSchedHour(parseInt(e.target.value, 10))}
                      className="flex-1 px-2.5 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      {Array.from({ length: 12 }, (_, i) => i + 1).map((h) => (
                        <option key={h} value={h}>{h}시</option>
                      ))}
                    </select>

                    {/* 분 (00~50, 10분 단위) */}
                    <select
                      value={schedMinute}
                      onChange={(e) => setSchedMinute(parseInt(e.target.value, 10))}
                      className="flex-1 px-2.5 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      {[0, 10, 20, 30, 40, 50].map((m) => (
                        <option key={m} value={m}>{m.toString().padStart(2, '0')}분</option>
                      ))}
                    </select>
                  </div>

                  {/* 선택된 시간 미리보기 */}
                  {scheduledAt && (
                    <p className="text-xs text-blue-600">
                      {new Date(scheduledAt).toLocaleString('ko-KR', {
                        year: 'numeric', month: 'long', day: 'numeric',
                        hour: '2-digit', minute: '2-digit', hour12: true
                      })} 에 출력 시작
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-xs text-gray-400">시간 미지정 시 즉시 대기열에 추가됩니다</p>
              )}
            </div>
          )}

          {/* 설정 변경 토글 */}
          <div>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              <svg className={`w-4 h-4 transition-transform ${showSettings ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <span className="font-medium">STL / 설정 변경</span>
              <span className="text-xs text-gray-400">(기존 설정 그대로 출력하려면 접어두세요)</span>
            </button>
          </div>

          {/* STL + 설정 변경 영역 */}
          {showSettings && (
            <div className="space-y-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
              {/* STL 파일 변경 */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">STL 파일</label>
                {uploadedFiles.length > 0 ? (
                  <select
                    value={stlFile}
                    onChange={(e) => onStlFileChange(e.target.value)}
                    className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                  >
                    {/* 기존 파일이 업로드 목록에 없으면 별도 옵션으로 표시 */}
                    {!uploadedFiles.includes(stlFile) && (
                      <option value={stlFile}>{stlFile} (원본)</option>
                    )}
                    {uploadedFiles.map((f) => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                ) : (
                  <div className="text-xs text-gray-500 p-2 bg-white rounded border">
                    <span className="font-medium">{stlFile}</span>
                    <span className="text-gray-400 ml-1">(업로드된 파일 없음)</span>
                  </div>
                )}
              </div>

              {/* 재료 변경 */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">재료 (레진)</label>
                <select
                  value={materialCode}
                  onChange={(e) => onMaterialCodeChange(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  {materialOptions.map((mat) => (
                    <option key={mat.code} value={mat.code}>
                      {mat.name} ({mat.code})
                    </option>
                  ))}
                </select>
              </div>

              {/* 레이어 두께 */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">레이어 두께</label>
                <select
                  value={layerThickness}
                  onChange={(e) => onLayerThicknessChange(parseFloat(e.target.value))}
                  className="w-full px-2.5 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  {layerOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* 파트 정보 */}
          {partInfo && (
            <div className="text-xs text-gray-500 bg-gray-50 rounded-lg p-2.5">
              <span className="font-medium">원본 파트:</span>{' '}
              {partInfo}
            </div>
          )}
        </div>

        {/* 하단 버튼 */}
        <div className="px-6 py-3 border-t bg-gray-50 flex justify-end gap-2 flex-shrink-0">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 rounded-lg transition-colors"
          >
            취소
          </button>
          <button
            onClick={onConfirm}
            disabled={mode === 'now' && !canPrintNow}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              mode === 'now' && !canPrintNow
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            {mode === 'now' ? '바로 출력' : scheduledAt ? '예약 추가' : '대기열 추가'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ===========================================
// 공통 컴포넌트
// ===========================================

function EmptyState({ message, sub }: { message: string; sub?: string }) {
  return (
    <div className="text-center py-16 bg-white rounded-xl border">
      <svg className="w-16 h-16 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <h3 className="text-lg font-medium text-gray-700 mb-2">{message}</h3>
      <p className="text-sm text-gray-500">{sub || '프린트 제어에서 작업을 시작하면 이곳에 기록됩니다'}</p>
    </div>
  );
}

function ReprintIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  );
}

// ===========================================
// 유틸 함수
// ===========================================

function getCloudStatusLabel(status: PrintStatus): string {
  switch (status) {
    case 'PRINTING': return '출력 중';
    case 'PREHEAT': return '예열 중';
    case 'PRECOAT': return '초기 코팅';
    case 'POSTCOAT': return '후처리 코팅';
    case 'FINISHED': return '완료';
    case 'QUEUED': return '대기';
    case 'PREPRINT': return '준비 중';
    case 'PAUSING': return '일시정지 중';
    case 'PAUSED': return '일시정지';
    case 'ABORTING': return '중단 중';
    case 'ABORTED': return '중단됨';
    case 'ERROR': return '오류';
    default: return status;
  }
}

function buildActivityLog(item: PrintHistoryItem): { label: string; time: string; color: string }[] {
  const log: { label: string; time: string; color: string }[] = [];
  const fmt = (iso: string | null) => {
    if (!iso) return '';
    return new Date(iso).toLocaleString('ko-KR', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
    });
  };

  // 시작
  if (item.started_at) {
    log.push({ label: '프린트 시작', time: fmt(item.started_at), color: 'bg-blue-500' });
  }

  // 재료 정보
  if (item.material_name) {
    log.push({
      label: `재료: ${item.material_name}${item.volume_ml ? ` (${item.volume_ml.toFixed(1)}ml)` : ''}`,
      time: '',
      color: 'bg-gray-300',
    });
  }

  // 레이어 정보
  if (item.layer_count > 0) {
    log.push({
      label: `총 ${item.layer_count} 레이어`,
      time: '',
      color: 'bg-gray-300',
    });
  }

  // 소요 시간
  if (item.duration_minutes != null && item.duration_minutes > 0) {
    const h = Math.floor(item.duration_minutes / 60);
    const m = item.duration_minutes % 60;
    const dur = h > 0 ? `${h}시간 ${m}분` : `${m}분`;
    log.push({ label: `소요 시간: ${dur}`, time: '', color: 'bg-gray-300' });
  }

  // 완료/오류/중단
  if (item.finished_at || item.status === 'FINISHED') {
    log.push({ label: '프린트 완료', time: fmt(item.finished_at), color: 'bg-green-500' });
  } else if (item.status === 'ERROR') {
    log.push({
      label: `오류 발생${item.message ? ': ' + item.message : ''}`,
      time: fmt(item.finished_at),
      color: 'bg-red-500',
    });
  } else if (item.status === 'ABORTED') {
    log.push({
      label: `사용자에 의해 중단${item.message ? ': ' + item.message : ''}`,
      time: fmt(item.finished_at),
      color: 'bg-orange-500',
    });
  }

  return log;
}

function getCloudStatusStyle(status: PrintStatus): string {
  switch (status) {
    case 'PRINTING': return 'bg-blue-100 text-blue-700';
    case 'PREHEAT': return 'bg-orange-100 text-orange-700';
    case 'PRECOAT': return 'bg-blue-100 text-blue-700';
    case 'POSTCOAT': return 'bg-blue-100 text-blue-700';
    case 'FINISHED': return 'bg-green-100 text-green-700';
    case 'QUEUED': return 'bg-gray-100 text-gray-700';
    case 'PREPRINT': return 'bg-yellow-100 text-yellow-700';
    case 'PAUSING': return 'bg-yellow-100 text-yellow-700';
    case 'PAUSED': return 'bg-yellow-100 text-yellow-700';
    case 'ABORTING': return 'bg-red-100 text-red-700';
    case 'ABORTED': return 'bg-orange-100 text-orange-700';
    case 'ERROR': return 'bg-red-100 text-red-700';
    case 'WAITING_FOR_RESOLUTION': return 'bg-amber-100 text-amber-700';
    default: return 'bg-gray-100 text-gray-700';
  }
}
