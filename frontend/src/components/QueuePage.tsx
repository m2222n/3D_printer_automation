/**
 * 대기 중인 작업 페이지
 * 프린트 대기 큐 관리, 드래그 앤 드롭 순서 변경
 */

import { useState, useEffect, useCallback } from 'react';
import { getPrintJobs } from '../services/localApi';
import { getDashboard } from '../services/api';
import type { PrintJob, PrintJobStatus } from '../types/local';
import { getJobStatusLabel } from '../types/local';
import type { PrinterSummary } from '../types/printer';

type QueueFilter = 'all' | string; // 'all' or printer serial

interface QueuePageProps {
  onOpenPrinterModal?: (serial: string) => void;
}

export function QueuePage({ onOpenPrinterModal }: QueuePageProps) {
  const [jobs, setJobs] = useState<PrintJob[]>([]);
  const [printers, setPrinters] = useState<PrinterSummary[]>([]);
  const [filter, setFilter] = useState<QueueFilter>('all');
  const [isLoading, setIsLoading] = useState(true);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  // 데이터 로드
  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [jobList, dashboard] = await Promise.all([
        getPrintJobs(0, 100),
        getDashboard(),
      ]);
      setJobs(jobList);
      setPrinters(dashboard.printers);
    } catch (err) {
      console.error('데이터 로드 실패:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    // 30초마다 자동 새로고침
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  // 대기 중인 작업만 필터 (pending, preparing, ready, sending)
  const queueJobs = jobs.filter((job) => {
    const isQueued = ['pending', 'preparing', 'ready', 'sending'].includes(job.status);
    if (!isQueued) return false;
    if (filter === 'all') return true;
    return job.printer_serial === filter;
  });

  // 드래그 앤 드롭 핸들러
  const handleDragStart = (index: number) => {
    setDraggedIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    setDragOverIndex(index);
  };

  const handleDragLeave = () => {
    setDragOverIndex(null);
  };

  const handleDrop = (targetIndex: number) => {
    if (draggedIndex === null || draggedIndex === targetIndex) {
      setDraggedIndex(null);
      setDragOverIndex(null);
      return;
    }

    const newJobs = [...jobs];
    const queuedJobs = newJobs.filter((job) =>
      ['pending', 'preparing', 'ready', 'sending'].includes(job.status)
    );
    const [movedJob] = queuedJobs.splice(draggedIndex, 1);
    queuedJobs.splice(targetIndex, 0, movedJob);

    // 대기 작업 순서만 교체하고 나머지 유지
    const nonQueueJobs = newJobs.filter((job) =>
      !['pending', 'preparing', 'ready', 'sending'].includes(job.status)
    );
    setJobs([...queuedJobs, ...nonQueueJobs]);
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  // 프린터 이름 가져오기
  const getPrinterName = (serial: string): string => {
    const printer = printers.find((p) => p.serial === serial);
    return printer?.name || serial;
  };

  return (
    <div className="bg-gray-100">
      {/* 서브 헤더 */}
      <header className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">
              대기 중인 작업
            </h2>
            <button
              onClick={loadData}
              disabled={isLoading}
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
              title="새로고침"
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
        {isLoading && queueJobs.length === 0 ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-3 text-gray-500">작업 목록을 불러오는 중...</p>
          </div>
        ) : queueJobs.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-xl border">
            <svg className="w-16 h-16 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <h3 className="text-lg font-medium text-gray-700 mb-2">대기 중인 작업이 없습니다</h3>
            <p className="text-sm text-gray-500">프린트 제어에서 새 작업을 시작하세요</p>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-sm text-gray-500 mb-3">
              드래그하여 순서를 변경할 수 있습니다 ({queueJobs.length}건)
            </p>
            {queueJobs.map((job, index) => (
              <div
                key={job.id}
                draggable
                onDragStart={() => handleDragStart(index)}
                onDragOver={(e) => handleDragOver(e, index)}
                onDragLeave={handleDragLeave}
                onDrop={() => handleDrop(index)}
                onDragEnd={handleDragEnd}
                className={`bg-white rounded-lg border p-4 cursor-move transition-all ${
                  draggedIndex === index ? 'opacity-50 scale-95' : ''
                } ${
                  dragOverIndex === index ? 'border-blue-400 shadow-md' : 'border-gray-200'
                } hover:shadow-sm`}
              >
                <div className="flex items-center gap-4">
                  {/* 드래그 핸들 */}
                  <div className="flex-shrink-0 text-gray-400 cursor-grab active:cursor-grabbing">
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M7 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4z" />
                    </svg>
                  </div>

                  {/* 순서 번호 */}
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-sm font-bold">
                    {index + 1}
                  </div>

                  {/* 작업 정보 */}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-gray-900 truncate">{job.stl_filename}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <button
                        onClick={(e) => { e.stopPropagation(); onOpenPrinterModal?.(job.printer_serial); }}
                        className="text-xs text-blue-600 hover:text-blue-800 hover:underline"
                      >
                        {getPrinterName(job.printer_serial)}
                      </button>
                      <span className="text-gray-300">|</span>
                      <span className="text-xs text-gray-400">
                        {new Date(job.created_at).toLocaleString('ko-KR')}
                      </span>
                      {job.scheduled_at && (
                        <>
                          <span className="text-gray-300">|</span>
                          <span className="text-xs text-blue-600 font-medium">
                            {new Date(job.scheduled_at).toLocaleString('ko-KR', {
                              month: 'short', day: 'numeric',
                              hour: '2-digit', minute: '2-digit', hour12: true
                            })} 예약
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* 상태 뱃지 */}
                  <div className="flex-shrink-0">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${getJobStatusStyle(job.status)}`}>
                      {getJobStatusLabel(job.status)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function getJobStatusStyle(status: PrintJobStatus): string {
  switch (status) {
    case 'pending': return 'bg-gray-100 text-gray-700';
    case 'preparing': return 'bg-yellow-100 text-yellow-700';
    case 'ready': return 'bg-blue-100 text-blue-700';
    case 'sending': return 'bg-blue-100 text-blue-700';
    case 'sent': return 'bg-green-100 text-green-700';
    case 'failed': return 'bg-red-100 text-red-700';
    default: return 'bg-gray-100 text-gray-700';
  }
}
