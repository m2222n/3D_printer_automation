/**
 * 프린트 제어 컴포넌트
 * 프린터 선택 및 프린트 작업 시작
 */

import { useState, useEffect, useCallback } from 'react';
import { startPrintJob, getLocalApiHealth, getPrintJobs } from '../services/localApi';
import { getDashboard } from '../services/api';
import type { Preset, PrintJob, LocalApiHealth, PrintJobStatus } from '../types/local';
import type { PrinterSummary } from '../types/printer';
import { getJobStatusLabel } from '../types/local';

// 작업 상태별 스타일 (Tailwind purge 대응)
function getJobStatusStyle(status: PrintJobStatus): string {
  switch (status) {
    case 'pending': return 'text-gray-700 bg-gray-100';
    case 'preparing': return 'text-yellow-700 bg-yellow-100';
    case 'ready': return 'text-blue-700 bg-blue-100';
    case 'sending': return 'text-blue-700 bg-blue-100';
    case 'sent': return 'text-green-700 bg-green-100';
    case 'failed': return 'text-red-700 bg-red-100';
    default: return 'text-gray-700 bg-gray-100';
  }
}

interface PrintControlProps {
  selectedPreset?: Preset | null;
  selectedFile?: string;
}

export function PrintControl({ selectedPreset, selectedFile }: PrintControlProps) {
  const [printers, setPrinters] = useState<PrinterSummary[]>([]);
  const [selectedPrinter, setSelectedPrinter] = useState<string>('');
  const [jobs, setJobs] = useState<PrintJob[]>([]);
  const [apiHealth, setApiHealth] = useState<LocalApiHealth | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 프린터 목록 로드 (Dashboard API에서 PrinterSummary 가져옴)
  const loadPrinters = useCallback(async () => {
    try {
      const dashboard = await getDashboard();
      setPrinters(dashboard.printers);
      if (dashboard.printers.length > 0 && !selectedPrinter) {
        setSelectedPrinter(dashboard.printers[0].serial);
      }
    } catch (err) {
      console.error('프린터 목록 로드 실패:', err);
    }
  }, [selectedPrinter]);

  // Local API 상태 확인
  const checkApiHealth = useCallback(async () => {
    try {
      const health = await getLocalApiHealth();
      setApiHealth(health);
    } catch (err) {
      setApiHealth(null);
    }
  }, []);

  // 최근 작업 목록 로드
  const loadJobs = useCallback(async () => {
    try {
      const jobList = await getPrintJobs(0, 5);
      setJobs(jobList);
    } catch (err) {
      console.error('작업 목록 로드 실패:', err);
    }
  }, []);

  // 프린트 시작
  const handleStartPrint = useCallback(async () => {
    if (!selectedPrinter) {
      setError('프린터를 선택해주세요.');
      return;
    }

    const stlFile = selectedPreset?.stl_filename || selectedFile;
    if (!stlFile && !selectedPreset) {
      setError('STL 파일 또는 프리셋을 선택해주세요.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setSuccess(null);

    try {
      await startPrintJob({
        preset_id: selectedPreset?.id,
        stl_file: stlFile || undefined,
        printer_serial: selectedPrinter,
        settings: selectedPreset?.settings,
      });
      setSuccess('프린트 작업이 시작되었습니다!');
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : '프린트 시작 실패');
    } finally {
      setIsLoading(false);
    }
  }, [selectedPrinter, selectedPreset, selectedFile, loadJobs]);

  // 초기 로드
  useEffect(() => {
    loadPrinters();
    checkApiHealth();
    loadJobs();
  }, [loadPrinters, checkApiHealth, loadJobs]);

  // PreFormServer 연결 상태
  const isPreformConnected = apiHealth?.preform_server === 'connected';

  return (
    <div className="bg-white rounded-xl border shadow-sm p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">프린트 제어</h2>

      {/* PreFormServer 상태 */}
      <div className={`mb-4 p-3 rounded-lg text-sm ${isPreformConnected ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-700'}`}>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${isPreformConnected ? 'bg-green-500' : 'bg-yellow-500'}`} />
          <span>
            PreFormServer: {isPreformConnected ? '연결됨' : '연결 안 됨'}
          </span>
        </div>
        {!isPreformConnected && (
          <p className="mt-1 text-xs">
            공장 Windows PC에서 PreFormServer가 실행 중이어야 합니다.
          </p>
        )}
      </div>

      {/* 에러/성공 메시지 */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
          {success}
        </div>
      )}

      {/* 선택된 설정 표시 */}
      <div className="mb-4 p-3 bg-gray-50 rounded-lg">
        <h3 className="text-sm font-medium text-gray-700 mb-2">프린트 설정</h3>
        {selectedPreset ? (
          <div className="text-sm text-gray-600">
            <p><strong>프리셋:</strong> {selectedPreset.name}</p>
            <p><strong>부품:</strong> {selectedPreset.part_type}</p>
            {selectedPreset.stl_filename && (
              <p><strong>파일:</strong> {selectedPreset.stl_filename}</p>
            )}
          </div>
        ) : selectedFile ? (
          <div className="text-sm text-gray-600">
            <p><strong>파일:</strong> {selectedFile}</p>
            <p className="text-xs text-gray-400 mt-1">프리셋 없이 기본 설정으로 출력됩니다.</p>
          </div>
        ) : (
          <p className="text-sm text-gray-400">파일 또는 프리셋을 선택해주세요</p>
        )}
      </div>

      {/* 프린터 선택 */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">프린터 선택</label>
        <select
          value={selectedPrinter}
          onChange={(e) => setSelectedPrinter(e.target.value)}
          className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="">프린터를 선택하세요</option>
          {printers.map((printer) => (
            <option
              key={printer.serial}
              value={printer.serial}
              disabled={printer.status !== 'IDLE'}
            >
              {printer.name} ({printer.status === 'IDLE' ? '대기 중' : printer.status})
            </option>
          ))}
        </select>
      </div>

      {/* 프린트 시작 버튼 */}
      <button
        onClick={handleStartPrint}
        disabled={isLoading || !isPreformConnected || !selectedPrinter || (!selectedPreset && !selectedFile)}
        className={`
          w-full py-3 rounded-lg font-medium text-white transition-colors
          ${isLoading || !isPreformConnected || !selectedPrinter || (!selectedPreset && !selectedFile)
            ? 'bg-gray-400 cursor-not-allowed'
            : 'bg-blue-600 hover:bg-blue-700'
          }
        `}
      >
        {isLoading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            전송 중...
          </span>
        ) : (
          '프린트 시작'
        )}
      </button>

      {/* 최근 작업 */}
      <div className="mt-6">
        <h3 className="text-sm font-medium text-gray-700 mb-2">최근 작업</h3>
        {jobs.length === 0 ? (
          <p className="text-sm text-gray-400">최근 작업이 없습니다</p>
        ) : (
          <div className="space-y-2">
            {jobs.map((job) => (
              <div key={job.id} className="flex items-center justify-between p-2 bg-gray-50 rounded text-sm">
                <div>
                  <p className="font-medium text-gray-700">{job.stl_filename}</p>
                  <p className="text-xs text-gray-500">{job.printer_serial}</p>
                </div>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${getJobStatusStyle(job.status)}`}>
                  {getJobStatusLabel(job.status)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
