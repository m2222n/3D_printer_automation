/**
 * 대시보드 컴포넌트
 * 프린터 4대 상태 모니터링
 * - 전체 뷰: 4개 카드 요약
 * - 프린터별 탭: 상세 정보
 */

import { useState, useEffect, useCallback } from 'react';
import { useDashboard } from '../hooks/useDashboard';
import PrinterCard from './PrinterCard';
import { PrinterDetail } from './PrinterDetail';
import { PrinterTimeline } from './PrinterTimeline';
import { getPrintHistory } from '../services/api';
import type { PrintHistoryItem } from '../types/printer';

type MonitoringTab = 'all' | string; // 'all' or printer serial

interface DashboardProps {
  onOpenPrinterModal?: (serial: string) => void;
}

export default function Dashboard({ onOpenPrinterModal }: DashboardProps) {
  const { dashboard, isLoading, error, isConnected, refresh } = useDashboard();
  const [activeMonitorTab, setActiveMonitorTab] = useState<MonitoringTab>('all');
  const [historyItems, setHistoryItems] = useState<PrintHistoryItem[]>([]);

  // 최근 48시간 프린트 이력 로드
  const loadHistory = useCallback(async () => {
    try {
      const dateFrom = new Date();
      dateFrom.setHours(dateFrom.getHours() - 48);
      const res = await getPrintHistory(1, 200, {
        date_from: dateFrom.toISOString(),
      });
      setHistoryItems(res.items);
    } catch {
      // 이력 로드 실패 시 타임라인만 비어있음
    }
  }, []);

  // 초기 로드 + 5분마다 갱신
  useEffect(() => {
    loadHistory();
    const interval = setInterval(loadHistory, 300000);
    return () => clearInterval(interval);
  }, [loadHistory]);

  // 로딩 상태
  if (isLoading && !dashboard) {
    return (
      <div className="min-h-[60vh] bg-gray-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">프린터 상태를 불러오는 중...</p>
        </div>
      </div>
    );
  }

  // 에러 상태
  if (error && !dashboard) {
    return (
      <div className="min-h-[60vh] bg-gray-100 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-lg p-6 max-w-md w-full text-center">
          <div className="text-red-500 text-5xl mb-4">!</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">연결 오류</h2>
          <p className="text-gray-600 mb-4">{error}</p>
          <button
            onClick={refresh}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            다시 시도
          </button>
        </div>
      </div>
    );
  }

  const selectedPrinter = dashboard?.printers.find(
    (p) => p.serial === activeMonitorTab
  );

  return (
    <div className="bg-gray-100">
      {/* 서브 헤더 */}
      <header className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                프린터 모니터링
              </h2>
            </div>

            {/* 연결 상태 */}
            <div className="flex items-center gap-3">
              <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm ${
                isConnected
                  ? 'bg-green-100 text-green-700'
                  : 'bg-yellow-100 text-yellow-700'
              }`}>
                <span className={`w-2 h-2 rounded-full ${
                  isConnected ? 'bg-green-500' : 'bg-yellow-500 animate-pulse'
                }`}></span>
                {isConnected ? '실시간' : '폴링'}
              </div>

              <button
                onClick={refresh}
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
        </div>
      </header>

      {/* 프린터 서브 탭 */}
      {dashboard && dashboard.printers.length > 0 && (
        <div className="bg-white border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex space-x-1 overflow-x-auto scrollbar-hide">
              <button
                onClick={() => setActiveMonitorTab('all')}
                className={`py-2.5 px-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                  activeMonitorTab === 'all'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                전체
              </button>
              {dashboard.printers.map((printer) => (
                <div key={printer.serial} className="flex items-center">
                  <button
                    onClick={() => setActiveMonitorTab(printer.serial)}
                    className={`py-2.5 px-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors flex items-center gap-1.5 ${
                      activeMonitorTab === printer.serial
                        ? 'border-blue-500 text-blue-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    <span className={`w-2 h-2 rounded-full ${getStatusDotColor(printer.status)}`}></span>
                    {printer.name}
                  </button>
                  <button
                    onClick={() => onOpenPrinterModal?.(printer.serial)}
                    className="p-1 text-gray-400 hover:text-blue-600 transition-colors"
                    title="프린터 상세 정보"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeMonitorTab === 'all' ? (
          <>
            {/* 요약 통계 */}
            {dashboard && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mb-6">
                <StatCard label="전체" value={dashboard.total_printers} color="gray" />
                <StatCard label="출력 중" value={dashboard.printers_printing} color="blue" />
                <StatCard label="대기 중" value={dashboard.printers_idle} color="gray" />
                <StatCard label="오류/오프라인" value={dashboard.printers_error + dashboard.printers_offline} color="red" />
              </div>
            )}

            {/* 프린터 카드 그리드 */}
            {dashboard && dashboard.printers.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {dashboard.printers.map((printer) => (
                  <div
                    key={printer.serial}
                    className="cursor-pointer"
                    onClick={() => setActiveMonitorTab(printer.serial)}
                  >
                    <PrinterCard printer={printer} onNameClick={onOpenPrinterModal} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-gray-500">등록된 프린터가 없습니다.</p>
              </div>
            )}

            {/* 타임라인 간트 차트 */}
            {dashboard && dashboard.printers.length > 0 && (
              <PrinterTimeline
                printers={dashboard.printers}
                historyItems={historyItems}
                onPrinterClick={(serial) => onOpenPrinterModal ? onOpenPrinterModal(serial) : setActiveMonitorTab(serial)}
              />
            )}
          </>
        ) : (
          /* 프린터 상세 뷰 */
          selectedPrinter && (
            <PrinterDetail
              printer={selectedPrinter}
              onBack={() => setActiveMonitorTab('all')}
              onNameClick={onOpenPrinterModal}
            />
          )
        )}

        {/* 에러 배너 (데이터는 있지만 에러 발생 시) */}
        {error && dashboard && (
          <div className="fixed bottom-4 left-4 right-4 sm:left-auto sm:right-4 sm:w-96 bg-red-50 border border-red-200 rounded-lg p-4 shadow-lg">
            <div className="flex items-start gap-3">
              <span className="text-red-500">!</span>
              <div className="flex-1">
                <p className="text-sm text-red-700">{error}</p>
                <button
                  onClick={refresh}
                  className="mt-2 text-sm text-red-600 hover:text-red-800 font-medium"
                >
                  다시 시도
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 마지막 업데이트 시간 */}
        {dashboard && (
          <div className="mt-6 text-center text-sm text-gray-400">
            마지막 업데이트: {new Date(dashboard.last_update).toLocaleString('ko-KR')}
          </div>
        )}
      </main>
    </div>
  );
}

// 상태별 도트 색상
function getStatusDotColor(status: string): string {
  switch (status) {
    case 'PRINTING': return 'bg-blue-500 animate-pulse';
    case 'FINISHED': return 'bg-green-500';
    case 'IDLE': return 'bg-gray-400';
    case 'ERROR': return 'bg-red-500';
    case 'OFFLINE': return 'bg-gray-300';
    default: return 'bg-gray-400';
  }
}

// 통계 카드 컴포넌트
interface StatCardProps {
  label: string;
  value: number;
  color: 'gray' | 'blue' | 'green' | 'red';
}

function StatCard({ label, value, color }: StatCardProps) {
  const colorStyles = {
    gray: 'bg-gray-50 border-gray-200 text-gray-900',
    blue: 'bg-blue-50 border-blue-200 text-blue-600',
    green: 'bg-green-50 border-green-200 text-green-600',
    red: 'bg-red-50 border-red-200 text-red-600',
  };

  return (
    <div className={`rounded-lg border p-3 sm:p-4 ${colorStyles[color]}`}>
      <p className="text-xs sm:text-sm text-gray-500">{label}</p>
      <p className="text-2xl sm:text-3xl font-bold mt-1">{value}</p>
    </div>
  );
}
