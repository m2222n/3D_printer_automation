/**
 * 개별 프린터 프린트 제어 컴포넌트
 * 프린터별 독립 컨테이너: 파일 업로드 + 프리셋 + 프린트 시작
 */

import { useState, useCallback } from 'react';
import { FileUpload } from './FileUpload';
import { PresetManager } from './PresetManager';
import { startPrintJob } from '../services/localApi';
import type { Preset } from '../types/local';
import type { PrinterSummary } from '../types/printer';
import { getStatusLabel } from '../types/printer';

interface PrinterPrintControlProps {
  printer: PrinterSummary;
  isPreformConnected: boolean;
}

export function PrinterPrintControl({
  printer,
  isPreformConnected,
}: PrinterPrintControlProps) {
  const [selectedFile, setSelectedFile] = useState<string | undefined>();
  const [selectedPreset, setSelectedPreset] = useState<Preset | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const isIdle = printer.status === 'IDLE';
  const isPrinting = printer.status === 'PRINTING';
  const canPrint = isIdle && isPreformConnected && (!!selectedPreset || !!selectedFile);

  const handleFileSelect = (filename: string) => {
    setSelectedFile(filename);
    setSelectedPreset(null);
  };

  const handlePresetSelect = (preset: Preset) => {
    setSelectedPreset(preset);
    if (preset.stl_filename) {
      setSelectedFile(preset.stl_filename);
    }
  };

  const handleStartPrint = useCallback(async () => {
    const stlFile = selectedPreset?.stl_filename || selectedFile;
    if (!stlFile && !selectedPreset) {
      setError('STL 파일 또는 프리셋을 먼저 선택해주세요.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setSuccess(null);

    try {
      await startPrintJob({
        preset_id: selectedPreset?.id,
        stl_file: stlFile || undefined,
        printer_serial: printer.serial,
        settings: selectedPreset?.settings,
      });
      setSuccess('프린트 작업이 시작되었습니다!');
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '프린트 시작 실패');
    } finally {
      setIsLoading(false);
    }
  }, [printer.serial, selectedPreset, selectedFile]);

  // 상태별 테두리 색상
  const borderColor = isPrinting ? 'border-blue-300' :
    printer.status === 'ERROR' ? 'border-red-300' :
    isIdle ? 'border-gray-200' : 'border-gray-200';

  const statusBgColor = isPrinting ? 'bg-blue-50' :
    printer.status === 'ERROR' ? 'bg-red-50' :
    printer.status === 'FINISHED' ? 'bg-green-50' : 'bg-white';

  return (
    <div className={`rounded-xl border-2 shadow-sm overflow-hidden ${borderColor}`}>
      {/* 프린터 헤더 */}
      <div className={`px-6 py-4 border-b flex items-center justify-between ${statusBgColor}`}>
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${
            isPrinting ? 'bg-blue-500 animate-pulse' :
            printer.status === 'ERROR' ? 'bg-red-500' :
            isIdle ? 'bg-green-500' :
            printer.status === 'FINISHED' ? 'bg-green-500' : 'bg-gray-400'
          }`} />
          <div>
            <h4 className="font-semibold text-gray-900">{printer.name}</h4>
            <p className="text-xs text-gray-500">{printer.serial}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${
            isPrinting ? 'bg-blue-100 text-blue-700' :
            printer.status === 'ERROR' ? 'bg-red-100 text-red-700' :
            isIdle ? 'bg-green-100 text-green-700' :
            printer.status === 'FINISHED' ? 'bg-green-100 text-green-700' :
            'bg-gray-100 text-gray-700'
          }`}>
            {getStatusLabel(printer.status)}
          </span>
          {printer.resin_remaining_percent !== null && (
            <span className={`text-xs ${printer.is_resin_low ? 'text-red-600' : 'text-gray-500'}`}>
              레진 {printer.resin_remaining_percent.toFixed(0)}%
            </span>
          )}
        </div>
      </div>

      {/* 본문 */}
      <div className="bg-white">
        {/* 출력 중인 경우 진행 상태 표시 */}
        {isPrinting && printer.current_job_name && (
          <div className="px-6 py-4 border-b bg-blue-50/50">
            <div className="flex justify-between text-sm mb-2">
              <span className="text-blue-700 font-medium">{printer.current_job_name}</span>
              <span className="text-blue-600 font-bold">{printer.progress_percent?.toFixed(1)}%</span>
            </div>
            <div className="h-2 bg-blue-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-500"
                style={{ width: `${printer.progress_percent || 0}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-blue-500 mt-1">
              <span>레이어 {printer.current_layer}/{printer.total_layers}</span>
              <span>남은 시간: {printer.remaining_minutes ? `${Math.floor(printer.remaining_minutes / 60)}시간 ${printer.remaining_minutes % 60}분` : '-'}</span>
            </div>
          </div>
        )}

        {/* 파일 업로드 + 프리셋 */}
        <div className="px-6 py-4 border-b">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <FileUpload onFileSelect={handleFileSelect} />
            <PresetManager onPresetSelect={handlePresetSelect} selectedFile={selectedFile} />
          </div>
        </div>

        {/* 프린트 제어 영역 */}
        <div className="px-6 py-4">
          {/* 선택된 설정 */}
          <div className="mb-4 p-3 bg-gray-50 rounded-lg">
            <h5 className="text-xs font-medium text-gray-500 mb-2">선택된 설정</h5>
            {selectedPreset ? (
              <div className="text-sm text-gray-700">
                <span className="font-medium">{selectedPreset.name}</span>
                {selectedPreset.stl_filename && (
                  <span className="text-gray-400 ml-2">({selectedPreset.stl_filename})</span>
                )}
              </div>
            ) : selectedFile ? (
              <div className="text-sm text-gray-700">{selectedFile}</div>
            ) : (
              <p className="text-sm text-gray-400">위에서 파일 또는 프리셋을 선택하세요</p>
            )}
          </div>

          {/* 에러/성공 메시지 */}
          {error && (
            <div className="mb-3 p-2 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {error}
            </div>
          )}
          {success && (
            <div className="mb-3 p-2 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
              {success}
            </div>
          )}

          {/* 프린트 시작 버튼 */}
          <button
            onClick={handleStartPrint}
            disabled={!canPrint || isLoading}
            className={`w-full py-2.5 rounded-lg font-medium text-sm transition-colors ${
              canPrint && !isLoading
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
            }`}
          >
            {isLoading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                전송 중...
              </span>
            ) : isPrinting ? (
              '출력 중...'
            ) : !isPreformConnected ? (
              'PreFormServer 연결 대기'
            ) : !selectedPreset && !selectedFile ? (
              '파일/프리셋 선택 필요'
            ) : !isIdle ? (
              `현재 상태: ${getStatusLabel(printer.status)}`
            ) : (
              '프린트 시작'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
