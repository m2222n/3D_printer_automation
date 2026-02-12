/**
 * 프린트 제어 페이지
 * 프린터 4대 각각 독립 컨테이너로 관리
 * 각 컨테이너에 파일 업로드 + 프리셋 + 프린트 제어 포함
 * 상단 탭으로 빠른 이동 (스크롤 앵커)
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { PrinterPrintControl } from './PrinterPrintControl';
import { getLocalApiHealth } from '../services/localApi';
import { getDashboard } from '../services/api';
import type { LocalApiHealth } from '../types/local';
import type { PrinterSummary } from '../types/printer';

export function PrintPage() {
  const [printers, setPrinters] = useState<PrinterSummary[]>([]);
  const [apiHealth, setApiHealth] = useState<LocalApiHealth | null>(null);
  const [activePrinterSerial, setActivePrinterSerial] = useState<string | null>(null);
  const printerRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // 프린터 목록 및 API 상태 로드
  const loadData = useCallback(async () => {
    try {
      const [dashboard, health] = await Promise.all([
        getDashboard(),
        getLocalApiHealth().catch(() => null),
      ]);
      setPrinters(dashboard.printers);
      setApiHealth(health);
    } catch (err) {
      console.error('데이터 로드 실패:', err);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 프린터 탭 클릭 시 해당 컨테이너로 스크롤
  const scrollToPrinter = (serial: string) => {
    setActivePrinterSerial(serial);
    const ref = printerRefs.current[serial];
    if (ref) {
      ref.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const isPreformConnected = apiHealth?.preform_server === 'connected';

  return (
    <div className="bg-gray-100">
      {/* 서브 헤더 */}
      <header className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">
              프린트 제어
            </h2>
            {/* PreFormServer 상태 */}
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${
              isPreformConnected ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
            }`}>
              <span className={`w-2 h-2 rounded-full ${
                isPreformConnected ? 'bg-green-500' : 'bg-yellow-500'
              }`} />
              PreFormServer: {isPreformConnected ? '연결됨' : '연결 안 됨'}
            </div>
          </div>
        </div>
      </header>

      {/* 프린터 퀵 점프 탭 */}
      {printers.length > 0 && (
        <div className="bg-white border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex space-x-1 overflow-x-auto scrollbar-hide">
              {printers.map((printer) => (
                <button
                  key={printer.serial}
                  onClick={() => scrollToPrinter(printer.serial)}
                  className={`py-2.5 px-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors flex items-center gap-1.5 ${
                    activePrinterSerial === printer.serial
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${
                    printer.status === 'IDLE' ? 'bg-green-500' :
                    printer.status === 'PRINTING' ? 'bg-blue-500 animate-pulse' :
                    printer.status === 'ERROR' ? 'bg-red-500' : 'bg-gray-400'
                  }`}></span>
                  {printer.name}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {printers.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-xl border">
            <p className="text-gray-500">프린터 정보를 불러오는 중...</p>
          </div>
        ) : (
          <div className="space-y-8">
            {printers.map((printer) => (
              <div
                key={printer.serial}
                ref={(el) => { printerRefs.current[printer.serial] = el; }}
                className="scroll-mt-32"
              >
                <PrinterPrintControl
                  printer={printer}
                  isPreformConnected={isPreformConnected}
                />
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
