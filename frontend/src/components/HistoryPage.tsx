/**
 * 이전 작업 내용 페이지
 * 프린트 히스토리 조회, 프린터별 필터, 재출력 버튼
 */

import { useState, useEffect, useCallback } from 'react';
import { getPrintJobs, startPrintJob } from '../services/localApi';
import { getPrintHistory, getDashboard } from '../services/api';
import type { PrintJob } from '../types/local';
import { getJobStatusLabel } from '../types/local';
import type { PrintHistoryItem, PrinterSummary, PrintStatus } from '../types/printer';

type HistoryFilter = 'all' | string; // 'all' or printer serial
type HistorySource = 'local' | 'cloud';

export function HistoryPage() {
  const [localJobs, setLocalJobs] = useState<PrintJob[]>([]);
  const [cloudHistory, setCloudHistory] = useState<PrintHistoryItem[]>([]);
  const [printers, setPrinters] = useState<PrinterSummary[]>([]);
  const [filter, setFilter] = useState<HistoryFilter>('all');
  const [source, setSource] = useState<HistorySource>('local');
  const [isLoading, setIsLoading] = useState(true);
  const [reprintingId, setReprintingId] = useState<string | null>(null);
  const [reprintSuccess, setReprintSuccess] = useState<string | null>(null);
  const [reprintError, setReprintError] = useState<string | null>(null);

  // 데이터 로드
  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [jobList, history, dashboard] = await Promise.all([
        getPrintJobs(0, 100),
        getPrintHistory(1, 50).catch(() => ({ items: [], total_count: 0, page: 1, page_size: 50 })),
        getDashboard(),
      ]);
      setLocalJobs(jobList);
      setCloudHistory(history.items);
      setPrinters(dashboard.printers);
    } catch (err) {
      console.error('히스토리 로드 실패:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

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

  // 클라우드 히스토리 필터
  const filteredCloudHistory = cloudHistory.filter((item) => {
    if (filter === 'all') return true;
    return item.printer_serial === filter;
  });

  // 프린터 이름 가져오기
  const getPrinterName = (serial: string): string => {
    const printer = printers.find((p) => p.serial === serial);
    return printer?.name || serial;
  };

  // 재출력 핸들러
  const handleReprint = useCallback(async (job: PrintJob) => {
    const availablePrinter = printers.find((p) => p.status === 'IDLE');
    if (!availablePrinter) {
      setReprintError('대기 중인 프린터가 없습니다.');
      setTimeout(() => setReprintError(null), 3000);
      return;
    }

    if (!confirm(
      `"${job.stl_filename}"을(를) ${getPrinterName(availablePrinter.serial)}에서 재출력하시겠습니까?`
    )) return;

    setReprintingId(job.id);
    setReprintError(null);
    setReprintSuccess(null);

    try {
      await startPrintJob({
        preset_id: job.preset_id || undefined,
        stl_file: job.stl_filename,
        printer_serial: availablePrinter.serial,
        settings: job.settings,
      });
      setReprintSuccess(`"${job.stl_filename}" 재출력 작업이 대기열에 추가되었습니다.`);
      setTimeout(() => setReprintSuccess(null), 5000);
      await loadData();
    } catch (err) {
      setReprintError(err instanceof Error ? err.message : '재출력 실패');
      setTimeout(() => setReprintError(null), 5000);
    } finally {
      setReprintingId(null);
    }
  }, [printers, loadData]);

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
            <EmptyState message="완료된 작업이 없습니다" />
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
                  onReprint={() => handleReprint(job)}
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
            <div className="space-y-2">
              <p className="text-sm text-gray-500 mb-3">
                총 {filteredCloudHistory.length}건
              </p>
              {filteredCloudHistory.map((item) => (
                <CloudHistoryCard
                  key={item.guid}
                  item={item}
                  printerName={getPrinterName(item.printer_serial)}
                />
              ))}
            </div>
          )
        )}
      </main>
    </div>
  );
}

// 로컬 작업 카드
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

        {/* 재출력 버튼 */}
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
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              재출력
            </span>
          )}
        </button>
      </div>
    </div>
  );
}

// 클라우드 히스토리 카드
function CloudHistoryCard({
  item,
  printerName,
}: {
  item: PrintHistoryItem;
  printerName: string;
}) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-sm transition-shadow">
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="font-medium text-gray-900 truncate">{item.name}</p>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getCloudStatusStyle(item.status)}`}>
              {getCloudStatusLabel(item.status)}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <span className="text-xs text-gray-500">{printerName}</span>
            {item.started_at && (
              <>
                <span className="text-gray-300">|</span>
                <span className="text-xs text-gray-400">
                  {new Date(item.started_at).toLocaleString('ko-KR')}
                </span>
              </>
            )}
            {item.duration_minutes && (
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
            {item.layer_count > 0 && (
              <>
                <span className="text-gray-300">|</span>
                <span className="text-xs text-gray-400">{item.layer_count} 레이어</span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// 빈 상태
function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-16 bg-white rounded-xl border">
      <svg className="w-16 h-16 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <h3 className="text-lg font-medium text-gray-700 mb-2">{message}</h3>
      <p className="text-sm text-gray-500">프린트 제어에서 작업을 시작하면 이곳에 기록됩니다</p>
    </div>
  );
}

function getCloudStatusLabel(status: PrintStatus): string {
  switch (status) {
    case 'PRINTING': return '출력 중';
    case 'FINISHED': return '완료';
    case 'QUEUED': return '대기';
    case 'PREPRINT': return '준비 중';
    case 'PAUSED': return '일시정지';
    case 'ABORTED': return '중단됨';
    case 'ERROR': return '오류';
    default: return status;
  }
}

function getCloudStatusStyle(status: PrintStatus): string {
  switch (status) {
    case 'PRINTING': return 'bg-blue-100 text-blue-700';
    case 'FINISHED': return 'bg-green-100 text-green-700';
    case 'QUEUED': return 'bg-gray-100 text-gray-700';
    case 'PREPRINT': return 'bg-yellow-100 text-yellow-700';
    case 'PAUSED': return 'bg-orange-100 text-orange-700';
    case 'ABORTED': return 'bg-gray-100 text-gray-700';
    case 'ERROR': return 'bg-red-100 text-red-700';
    default: return 'bg-gray-100 text-gray-700';
  }
}
