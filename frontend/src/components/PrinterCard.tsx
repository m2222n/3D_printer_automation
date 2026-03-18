import type { PrinterSummary } from '../types/printer';
import { getStatusLabel, formatDuration, formatResinAmount } from '../types/printer';

interface PrinterCardProps {
  printer: PrinterSummary;
  onNameClick?: (serial: string) => void;
}

function getStatusStyles(status: string): { bg: string; text: string; dot: string } {
  switch (status) {
    case 'PRINTING':
      return { bg: 'bg-blue-50', text: 'text-blue-700', dot: 'bg-blue-500' };
    case 'PREHEAT':
      return { bg: 'bg-orange-50', text: 'text-orange-700', dot: 'bg-orange-500' };
    case 'PAUSING':
    case 'PAUSED':
      return { bg: 'bg-yellow-50', text: 'text-yellow-700', dot: 'bg-yellow-500' };
    case 'ABORTING':
      return { bg: 'bg-red-50', text: 'text-red-700', dot: 'bg-red-500' };
    case 'FINISHED':
      return { bg: 'bg-green-50', text: 'text-green-700', dot: 'bg-green-500' };
    case 'IDLE':
      return { bg: 'bg-gray-50', text: 'text-gray-700', dot: 'bg-gray-400' };
    case 'ERROR':
      return { bg: 'bg-red-50', text: 'text-red-700', dot: 'bg-red-500' };
    case 'OFFLINE':
      return { bg: 'bg-gray-100', text: 'text-gray-500', dot: 'bg-gray-300' };
    default:
      return { bg: 'bg-gray-50', text: 'text-gray-700', dot: 'bg-gray-400' };
  }
}

export default function PrinterCard({ printer, onNameClick }: PrinterCardProps) {
  const statusStyles = getStatusStyles(printer.status);
  const isOffline = printer.status === 'OFFLINE';
  // 활성 작업이 있는 상태들
  const hasActiveJob = ['PRINTING', 'PREHEAT', 'PAUSING', 'PAUSED', 'ABORTING'].includes(printer.status);
  const isPrinting = printer.status === 'PRINTING';
  const isPreheat = printer.status === 'PREHEAT';
  const isPaused = printer.status === 'PAUSED' || printer.status === 'PAUSING';
  const isAborting = printer.status === 'ABORTING';

  // 프로그레스 바 색상
  const progressBarColor = isPreheat ? 'bg-orange-500' : isPaused ? 'bg-yellow-500' : isAborting ? 'bg-red-500' : 'bg-blue-500';
  const progressTextColor = isPreheat ? 'text-orange-600' : isPaused ? 'text-yellow-600' : isAborting ? 'text-red-600' : 'text-blue-600';

  return (
    <div className={`rounded-xl border shadow-sm overflow-hidden ${isOffline ? 'opacity-60' : ''} ${statusStyles.bg}`}>
      {/* 헤더 */}
      <div className="px-4 py-3 border-b bg-white/50">
        <div className="flex items-center justify-between">
          {onNameClick ? (
            <button
              onClick={(e) => { e.stopPropagation(); onNameClick(printer.serial); }}
              className="font-semibold text-blue-600 hover:text-blue-800 hover:underline truncate text-left"
            >
              {printer.name}
            </button>
          ) : (
            <h3 className="font-semibold text-gray-900 truncate">{printer.name}</h3>
          )}
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${statusStyles.bg} ${statusStyles.text}`}>
            <span className={`w-2 h-2 rounded-full ${statusStyles.dot} ${(isPrinting || isPreheat) ? 'animate-pulse' : ''}`}></span>
            {getStatusLabel(printer.status)}
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-0.5">{printer.serial}</p>
      </div>

      {/* 본문 */}
      <div className="px-4 py-3 space-y-3">
        {/* 활성 작업 진행 정보 (출력 중/예열/일시정지/중단) */}
        {hasActiveJob && printer.current_job_name && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600 truncate flex-1">{printer.current_job_name}</span>
              <span className={`font-medium ${progressTextColor} ml-2`}>
                {printer.progress_percent?.toFixed(1)}%
              </span>
            </div>

            {/* 프린트 단계 표시 */}
            {printer.print_phase && (
              <div className={`text-xs font-medium ${progressTextColor} flex items-center gap-1`}>
                {isPreheat && <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse" />}
                {printer.print_phase}
                {printer.temperature !== null && printer.temperature !== undefined && (
                  <span className="text-gray-400 ml-1">({printer.temperature.toFixed(1)}°C)</span>
                )}
              </div>
            )}

            {/* 진행 바 */}
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${progressBarColor} ${isPreheat ? 'animate-pulse' : ''}`}
                style={{ width: `${printer.progress_percent || 0}%` }}
              />
            </div>

            {/* 레이어 정보 */}
            <div className="flex items-center justify-between text-xs text-gray-500">
              <span>
                레이어: {printer.current_layer} / {printer.total_layers}
              </span>
              {printer.print_started_at && (
                <span>
                  시작: {new Date(printer.print_started_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
            </div>

            {/* 시간 정보 강화 */}
            <div className="bg-white/60 rounded-lg px-3 py-2 space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">경과</span>
                <span className="font-medium text-gray-700">
                  {printer.elapsed_minutes !== null && printer.elapsed_minutes !== undefined
                    ? formatDuration(printer.elapsed_minutes)
                    : '-'}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">남은 시간</span>
                <span className={`font-medium ${progressTextColor}`}>
                  {printer.remaining_minutes ? formatDuration(printer.remaining_minutes) : '-'}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">전체 예상</span>
                <span className="font-medium text-gray-700">
                  {printer.estimated_total_minutes ? formatDuration(printer.estimated_total_minutes) : '-'}
                </span>
              </div>
            </div>

            {/* 일시정지/중단 안내 */}
            {isPaused && (
              <div className="text-xs text-yellow-700 bg-yellow-100 rounded-lg px-3 py-2">
                일시정지됨 — 프린터 터치스크린에서 재개해주세요
              </div>
            )}
            {isAborting && (
              <div className="text-xs text-red-700 bg-red-100 rounded-lg px-3 py-2">
                프린트 중단 중...
              </div>
            )}
          </div>
        )}

        {/* 비활성 상태 메시지 */}
        {!hasActiveJob && (
          <div className="space-y-1.5">
            <div className="text-sm text-gray-500">
              {printer.status === 'FINISHED' && '출력 완료 — 빌드 플레이트 회수 필요'}
              {printer.status === 'IDLE' && (printer.is_ready ? '출력 대기 중' : '출력 준비 필요')}
              {printer.status === 'ERROR' && '오류 발생 — 확인 필요'}
              {printer.status === 'OFFLINE' && '프린터 오프라인'}
            </div>
            {/* 준비 안 됨 상세 안내 */}
            {printer.status === 'IDLE' && !printer.is_ready && (
              <div className="text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-1.5">
                {printer.build_platform_contents === 'BUILD_PLATFORM_CONTENTS_MISSING'
                  ? '빌드 플레이트가 설치되지 않았습니다'
                  : printer.build_platform_contents === 'BUILD_PLATFORM_CONTENTS_HAS_PARTS' || printer.build_platform_contents === 'HAS_PARTS'
                  ? '빌드 플레이트에 부품이 남아있습니다'
                  : '레진 탱크, 카트리지 또는 빌드 플레이트를 확인해주세요'}
              </div>
            )}
          </div>
        )}

        {/* 소모품 정보 (PreForm 스타일) */}
        <div className="pt-2 border-t border-gray-200/50 space-y-2">
          {/* 레진 탱크 */}
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 flex-shrink-0 text-blue-500" viewBox="0 0 16 16" fill="currentColor">
              <rect x="4" y="2" width="8" height="12" rx="1.5" opacity="0.2" />
              <rect x="4" y={2 + 12 * (1 - (printer.resin_remaining_percent ?? 0) / 100)} width="8" height={12 * ((printer.resin_remaining_percent ?? 0) / 100)} rx="0" />
              <rect x="4" y="2" width="8" height="12" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1" />
            </svg>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className={`text-sm font-medium truncate ${printer.is_tank_missing ? 'text-gray-400' : 'text-gray-800'}`}>
                  {printer.is_tank_missing
                    ? '탱크 없음'
                    : printer.cartridge_material_name || printer.cartridge_material_code || '레진 정보 없음'}
                </span>
                {printer.resin_remaining_ml !== null && !printer.is_cartridge_missing && (
                  <span className={`text-xs ml-2 flex-shrink-0 ${printer.is_resin_low ? 'text-red-600 font-medium' : 'text-gray-400'}`}>
                    {formatResinAmount(printer.resin_remaining_ml)}
                  </span>
                )}
              </div>
              {/* 잔량 바 (PreForm 스타일 — 파란색) */}
              {printer.resin_remaining_percent !== null && !printer.is_cartridge_missing && (
                <div className="mt-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      printer.is_resin_low ? 'bg-red-500' : 'bg-blue-500'
                    }`}
                    style={{ width: `${printer.resin_remaining_percent}%` }}
                  />
                </div>
              )}
            </div>
          </div>

          {/* 카트리지 상태 */}
          {printer.is_cartridge_missing && (
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 flex-shrink-0 text-red-500" viewBox="0 0 16 16" fill="currentColor">
                <path d="M5 1.5A1.5 1.5 0 016.5 0h3A1.5 1.5 0 0111 1.5v1a.5.5 0 01-.5.5h-5a.5.5 0 01-.5-.5v-1zM4 4h8v9.5a2.5 2.5 0 01-2.5 2.5h-3A2.5 2.5 0 014 13.5V4z" />
              </svg>
              <span className="text-sm font-medium text-red-600">Missing</span>
            </div>
          )}
        </div>
      </div>

      {/* 푸터 - 마지막 업데이트 */}
      <div className="px-4 py-2 bg-white/30 border-t text-xs text-gray-400">
        마지막 업데이트: {new Date(printer.last_update).toLocaleTimeString('ko-KR')}
      </div>
    </div>
  );
}
