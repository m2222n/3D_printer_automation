/**
 * 개별 프린터 프린트 제어 컴포넌트
 * 프린터별 독립 컨테이너: 파일 업로드 + 프리셋 + 슬라이스 미리보기 + 프린트 시작
 */

import { useState, useCallback } from 'react';
import { FileUpload } from './FileUpload';
import { PresetManager } from './PresetManager';
import { startPrintJob, prepareScene, printPreparedScene, deleteScene } from '../services/localApi';
import type { Preset, SceneEstimate } from '../types/local';
import type { PrinterSummary } from '../types/printer';
import { getStatusLabel, formatDuration } from '../types/printer';
import { MATERIAL_NAMES, type MaterialCode } from '../types/local';

interface PrinterPrintControlProps {
  printer: PrinterSummary;
  isPreformConnected: boolean;
}

/** 밀리초를 "X시간 Y분" 형태로 변환 */
function formatMs(ms: number): string {
  const minutes = Math.round(ms / 60000);
  return formatDuration(minutes);
}

export function PrinterPrintControl({
  printer,
  isPreformConnected,
}: PrinterPrintControlProps) {
  const [selectedFile, setSelectedFile] = useState<string | undefined>();
  const [selectedPreset, setSelectedPreset] = useState<Preset | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isPreparing, setIsPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 슬라이스 예측 결과
  const [estimate, setEstimate] = useState<SceneEstimate | null>(null);

  const isIdle = printer.status === 'IDLE';
  const isPrinting = printer.status === 'PRINTING';
  const isPreheat = printer.status === 'PREHEAT';
  const isPaused = printer.status === 'PAUSED' || printer.status === 'PAUSING';
  const isAborting = printer.status === 'ABORTING';
  const hasActiveJob = ['PRINTING', 'PREHEAT', 'PAUSING', 'PAUSED', 'ABORTING'].includes(printer.status);
  const canPrepare = isPreformConnected && (!!selectedPreset || !!selectedFile) && !estimate;
  const canPrint = isIdle && isPreformConnected && !!estimate;

  const handleFileSelect = (filename: string) => {
    setSelectedFile(filename);
    setSelectedPreset(null);
    setEstimate(null); // 파일 변경 시 예측 초기화
    setError(null);
    setSuccess(null);
  };

  const handlePresetSelect = (preset: Preset) => {
    setSelectedPreset(preset);
    if (preset.stl_filename) {
      setSelectedFile(preset.stl_filename);
    }
    setEstimate(null); // 프리셋 변경 시 예측 초기화
    setError(null);
    setSuccess(null);
  };

  // 슬라이스 미리보기 (Scene 준비 + 예측)
  const handlePrepare = useCallback(async () => {
    const stlFile = selectedPreset?.stl_filename || selectedFile;
    if (!stlFile) {
      setError('STL 파일을 먼저 선택해주세요.');
      return;
    }

    setIsPreparing(true);
    setError(null);
    setSuccess(null);

    try {
      const settings = selectedPreset?.settings;
      const result = await prepareScene({
        stl_file: stlFile,
        machine_type: settings?.machine_type || 'FORM-4-0',
        material_code: settings?.material_code || 'FLGPGR05',
        layer_thickness_mm: settings?.layer_thickness_mm || 0.05,
        support_density: settings?.support.density || 'normal',
        touchpoint_size: settings?.support.touchpoint_size || 0.5,
      });
      setEstimate(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '슬라이스 준비 실패');
    } finally {
      setIsPreparing(false);
    }
  }, [selectedPreset, selectedFile]);

  // 슬라이스 취소 (Scene 삭제)
  const handleCancelPrepare = useCallback(async () => {
    if (estimate?.scene_id) {
      try {
        await deleteScene(estimate.scene_id);
      } catch {
        // 삭제 실패해도 UI에서는 초기화
      }
    }
    setEstimate(null);
    setError(null);
    setSuccess(null);
  }, [estimate]);

  // 프린터로 전송 (기존 Scene 사용)
  const handleSendToPrinter = useCallback(async () => {
    if (!estimate?.scene_id) return;

    setIsLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const jobName = selectedPreset?.name || selectedFile?.replace(/\.[^.]+$/, '') || 'print-job';
      await printPreparedScene(estimate.scene_id, printer.serial, jobName);
      setSuccess('프린트 작업이 프린터로 전송되었습니다!');
      setEstimate(null);
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '프린터 전송 실패');
    } finally {
      setIsLoading(false);
    }
  }, [estimate, printer.serial, selectedPreset, selectedFile]);

  // 기존 방식 (프리셋 기반 바로 프린트 - 예측 건너뛰기)
  const handleQuickPrint = useCallback(async () => {
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
    isPreheat ? 'border-orange-300' :
    isPaused ? 'border-yellow-300' :
    isAborting ? 'border-red-300' :
    printer.status === 'ERROR' ? 'border-red-300' :
    'border-gray-200';

  const statusBgColor = isPrinting ? 'bg-blue-50' :
    isPreheat ? 'bg-orange-50' :
    isPaused ? 'bg-yellow-50' :
    isAborting ? 'bg-red-50' :
    printer.status === 'ERROR' ? 'bg-red-50' :
    printer.status === 'FINISHED' ? 'bg-green-50' : 'bg-white';

  const dotColor = isPrinting ? 'bg-blue-500 animate-pulse' :
    isPreheat ? 'bg-orange-500 animate-pulse' :
    isPaused ? 'bg-yellow-500' :
    isAborting ? 'bg-red-500 animate-pulse' :
    printer.status === 'ERROR' ? 'bg-red-500' :
    isIdle ? 'bg-green-500' :
    printer.status === 'FINISHED' ? 'bg-green-500' : 'bg-gray-400';

  const badgeColor = isPrinting ? 'bg-blue-100 text-blue-700' :
    isPreheat ? 'bg-orange-100 text-orange-700' :
    isPaused ? 'bg-yellow-100 text-yellow-700' :
    isAborting ? 'bg-red-100 text-red-700' :
    printer.status === 'ERROR' ? 'bg-red-100 text-red-700' :
    isIdle ? 'bg-green-100 text-green-700' :
    printer.status === 'FINISHED' ? 'bg-green-100 text-green-700' :
    'bg-gray-100 text-gray-700';

  const progressColor = isPreheat ? 'bg-orange-500' :
    isPaused ? 'bg-yellow-500' :
    isAborting ? 'bg-red-500' : 'bg-blue-500';

  const progressTextClr = isPreheat ? 'text-orange-600' :
    isPaused ? 'text-yellow-700' :
    isAborting ? 'text-red-600' : 'text-blue-600';

  return (
    <div className={`rounded-xl border-2 shadow-sm overflow-hidden ${borderColor}`}>
      {/* 프린터 헤더 */}
      <div className={`px-6 py-4 border-b flex items-center justify-between ${statusBgColor}`}>
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${dotColor}`} />
          <div>
            <h4 className="font-semibold text-gray-900">{printer.name}</h4>
            <p className="text-xs text-gray-500">{printer.serial}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${badgeColor}`}>
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
        {/* 활성 작업 진행 상태 표시 (출력 중/예열/일시정지/중단) */}
        {hasActiveJob && printer.current_job_name && (
          <div className={`px-6 py-4 border-b ${
            isPreheat ? 'bg-orange-50/50' :
            isPaused ? 'bg-yellow-50/50' :
            isAborting ? 'bg-red-50/50' : 'bg-blue-50/50'
          }`}>
            {/* 작업명 + 진행률 */}
            <div className="flex justify-between text-sm mb-1">
              <span className={`font-medium ${progressTextClr}`}>{printer.current_job_name}</span>
              <span className={`font-bold ${progressTextClr}`}>{printer.progress_percent?.toFixed(1)}%</span>
            </div>

            {/* 프린트 단계 */}
            {printer.print_phase && (
              <div className={`text-xs font-medium ${progressTextClr} mb-2 flex items-center gap-1`}>
                {(isPreheat || isPrinting) && <span className={`inline-block w-1.5 h-1.5 rounded-full ${progressColor} animate-pulse`} />}
                {printer.print_phase}
                {printer.temperature !== null && printer.temperature !== undefined && (
                  <span className="text-gray-400 ml-1">({printer.temperature.toFixed(1)}°C)</span>
                )}
              </div>
            )}

            {/* 진행 바 */}
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${progressColor} ${isPreheat ? 'animate-pulse' : ''}`}
                style={{ width: `${printer.progress_percent || 0}%` }}
              />
            </div>

            {/* 레이어 + 시작 시각 */}
            <div className="flex justify-between text-xs text-gray-500 mt-1.5">
              <span>레이어 {printer.current_layer}/{printer.total_layers}</span>
              {printer.print_started_at && (
                <span>시작: {new Date(printer.print_started_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}</span>
              )}
            </div>

            {/* 시간 정보 카드 */}
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <div className="bg-white/70 rounded-lg px-2 py-1.5">
                <div className="text-xs text-gray-500">경과</div>
                <div className="text-sm font-medium text-gray-700">
                  {printer.elapsed_minutes !== null && printer.elapsed_minutes !== undefined
                    ? formatDuration(printer.elapsed_minutes)
                    : '-'}
                </div>
              </div>
              <div className="bg-white/70 rounded-lg px-2 py-1.5">
                <div className="text-xs text-gray-500">남은 시간</div>
                <div className={`text-sm font-medium ${progressTextClr}`}>
                  {printer.remaining_minutes ? formatDuration(printer.remaining_minutes) : '-'}
                </div>
              </div>
              <div className="bg-white/70 rounded-lg px-2 py-1.5">
                <div className="text-xs text-gray-500">전체 예상</div>
                <div className="text-sm font-medium text-gray-700">
                  {printer.estimated_total_minutes ? formatDuration(printer.estimated_total_minutes) : '-'}
                </div>
              </div>
            </div>

            {/* 일시정지/중단 안내 */}
            {isPaused && (
              <div className="mt-3 text-xs text-yellow-800 bg-yellow-100 border border-yellow-200 rounded-lg px-3 py-2">
                일시정지됨 — 프린터 터치스크린에서 재개할 수 있습니다
              </div>
            )}
            {isAborting && (
              <div className="mt-3 text-xs text-red-800 bg-red-100 border border-red-200 rounded-lg px-3 py-2">
                프린트를 중단하고 있습니다...
              </div>
            )}
            {(isPrinting || isPreheat) && (
              <div className="mt-3 text-xs text-gray-500 bg-gray-100 border border-gray-200 rounded-lg px-3 py-2">
                일시정지 / 중단은 프린터 터치스크린에서 조작할 수 있습니다
              </div>
            )}
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

          {/* 슬라이스 예측 결과 카드 */}
          {estimate && (
            <div className="mb-4 p-4 bg-indigo-50 border border-indigo-200 rounded-lg">
              <div className="flex items-center justify-between mb-3">
                <h5 className="text-sm font-semibold text-indigo-800">슬라이스 미리보기</h5>
                <button
                  onClick={handleCancelPrepare}
                  className="text-xs text-indigo-600 hover:text-indigo-800 underline"
                >
                  다시 설정
                </button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {estimate.estimated_print_time_ms && (
                  <div className="bg-white rounded-lg px-3 py-2">
                    <div className="text-xs text-gray-500">예상 출력 시간</div>
                    <div className="text-sm font-bold text-indigo-700">
                      {formatMs(estimate.estimated_print_time_ms)}
                    </div>
                  </div>
                )}
                {estimate.estimated_material_ml !== null && (
                  <div className="bg-white rounded-lg px-3 py-2">
                    <div className="text-xs text-gray-500">예상 재료 사용량</div>
                    <div className="text-sm font-bold text-indigo-700">
                      {estimate.estimated_material_ml.toFixed(1)} ml
                    </div>
                  </div>
                )}
                <div className="bg-white rounded-lg px-3 py-2">
                  <div className="text-xs text-gray-500">레진 종류</div>
                  <div className="text-sm font-medium text-gray-700">
                    {MATERIAL_NAMES[estimate.material_code as MaterialCode] || estimate.material_code}
                  </div>
                </div>
                <div className="bg-white rounded-lg px-3 py-2">
                  <div className="text-xs text-gray-500">모델 수</div>
                  <div className="text-sm font-medium text-gray-700">
                    {estimate.model_count}개
                  </div>
                </div>
              </div>

              {/* 레진 잔량 대비 경고 */}
              {estimate.estimated_material_ml !== null && printer.resin_remaining_ml !== null &&
                estimate.estimated_material_ml > printer.resin_remaining_ml && (
                <div className="mt-3 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  예상 재료 사용량({estimate.estimated_material_ml.toFixed(1)}ml)이 현재 레진 잔량({printer.resin_remaining_ml.toFixed(0)}ml)보다 많습니다. 레진 교체가 필요할 수 있습니다.
                </div>
              )}
            </div>
          )}

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

          {/* 프린터 준비 상태 안내 */}
          {isIdle && !printer.is_ready && (
            <div className="mb-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <div className="text-sm font-medium text-amber-800 mb-1">프린터 준비 필요</div>
              <div className="text-xs text-amber-700">
                {printer.build_platform_contents === 'BUILD_PLATFORM_CONTENTS_MISSING'
                  ? '빌드 플레이트가 설치되지 않았습니다.'
                  : printer.build_platform_contents === 'BUILD_PLATFORM_CONTENTS_HAS_PARTS' || printer.build_platform_contents === 'HAS_PARTS'
                  ? '빌드 플레이트에 부품이 남아있습니다. 제거해주세요.'
                  : '레진 탱크, 카트리지 또는 빌드 플레이트를 확인해주세요.'}
              </div>
              <div className="text-xs text-amber-600 mt-1">
                소모품 설치 후 자동으로 상태가 업데이트됩니다.
              </div>
            </div>
          )}

          {/* 버튼 영역 */}
          <div className="flex gap-2">
            {/* 슬라이스 미리보기 버튼 */}
            {!estimate && (
              <button
                onClick={handlePrepare}
                disabled={!canPrepare || isPreparing}
                className={`flex-1 py-2.5 rounded-lg font-medium text-sm transition-colors ${
                  canPrepare && !isPreparing
                    ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                }`}
              >
                {isPreparing ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    슬라이스 준비 중...
                  </span>
                ) : !isPreformConnected ? (
                  'PreFormServer 연결 대기'
                ) : !selectedPreset && !selectedFile ? (
                  '파일/프리셋 선택 필요'
                ) : (
                  '슬라이스 미리보기'
                )}
              </button>
            )}

            {/* 프린트 전송 버튼 (예측 결과가 있을 때) */}
            {estimate && (
              <>
                <button
                  onClick={handleSendToPrinter}
                  disabled={!canPrint || isLoading}
                  className={`flex-1 py-2.5 rounded-lg font-medium text-sm transition-colors ${
                    canPrint && !isLoading
                      ? 'bg-blue-600 text-white hover:bg-blue-700'
                      : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                  }`}
                >
                  {isLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      프린터 전송 중...
                    </span>
                  ) : !isIdle ? (
                    `현재 상태: ${getStatusLabel(printer.status)}`
                  ) : (
                    '프린터로 전송'
                  )}
                </button>
                <button
                  onClick={handleCancelPrepare}
                  disabled={isLoading}
                  className="px-4 py-2.5 rounded-lg font-medium text-sm border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  취소
                </button>
              </>
            )}
          </div>

          {/* 빠른 프린트 (프리셋 기반, 슬라이스 건너뛰기) */}
          {!estimate && selectedPreset && isIdle && isPreformConnected && (
            <button
              onClick={handleQuickPrint}
              disabled={isLoading || isPreparing}
              className="mt-2 w-full py-2 rounded-lg font-medium text-xs text-gray-500 border border-gray-200 hover:bg-gray-50 transition-colors"
            >
              {isLoading ? '전송 중...' : '미리보기 없이 바로 프린트'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
