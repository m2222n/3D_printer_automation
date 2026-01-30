import type { PrinterSummary } from '../types/printer';
import { getStatusLabel, formatDuration, formatResinAmount } from '../types/printer';

interface PrinterCardProps {
  printer: PrinterSummary;
}

function getStatusStyles(status: string): { bg: string; text: string; dot: string } {
  switch (status) {
    case 'PRINTING':
      return { bg: 'bg-blue-50', text: 'text-blue-700', dot: 'bg-blue-500' };
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

export default function PrinterCard({ printer }: PrinterCardProps) {
  const statusStyles = getStatusStyles(printer.status);
  const isPrinting = printer.status === 'PRINTING';
  const isOffline = printer.status === 'OFFLINE';

  return (
    <div className={`rounded-xl border shadow-sm overflow-hidden ${isOffline ? 'opacity-60' : ''} ${statusStyles.bg}`}>
      {/* 헤더 */}
      <div className="px-4 py-3 border-b bg-white/50">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900 truncate">{printer.name}</h3>
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${statusStyles.bg} ${statusStyles.text}`}>
            <span className={`w-2 h-2 rounded-full ${statusStyles.dot} ${isPrinting ? 'animate-pulse' : ''}`}></span>
            {getStatusLabel(printer.status)}
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-0.5">{printer.serial}</p>
      </div>

      {/* 본문 */}
      <div className="px-4 py-3 space-y-3">
        {/* 출력 진행 정보 */}
        {isPrinting && printer.current_job_name && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600 truncate flex-1">{printer.current_job_name}</span>
              <span className="font-medium text-blue-600 ml-2">
                {printer.progress_percent?.toFixed(1)}%
              </span>
            </div>

            {/* 진행 바 */}
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-500"
                style={{ width: `${printer.progress_percent || 0}%` }}
              />
            </div>

            {/* 레이어 및 남은 시간 */}
            <div className="flex items-center justify-between text-xs text-gray-500">
              <span>
                레이어: {printer.current_layer} / {printer.total_layers}
              </span>
              <span>
                남은 시간: {printer.remaining_minutes ? formatDuration(printer.remaining_minutes) : '-'}
              </span>
            </div>
          </div>
        )}

        {/* 대기 중 또는 완료 상태 메시지 */}
        {!isPrinting && (
          <div className="text-sm text-gray-500">
            {printer.status === 'FINISHED' && '출력 완료 - 빌드 플레이트 회수 필요'}
            {printer.status === 'IDLE' && '출력 대기 중'}
            {printer.status === 'ERROR' && '오류 발생 - 확인 필요'}
            {printer.status === 'OFFLINE' && '프린터 오프라인'}
          </div>
        )}

        {/* 레진 잔량 */}
        <div className="pt-2 border-t border-gray-200/50">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600">레진 잔량</span>
            <span className={`font-medium ${printer.is_resin_low ? 'text-red-600' : 'text-gray-900'}`}>
              {formatResinAmount(printer.resin_remaining_ml)}
              {printer.resin_remaining_percent !== null && (
                <span className="text-gray-400 ml-1">
                  ({printer.resin_remaining_percent.toFixed(0)}%)
                </span>
              )}
              {printer.is_resin_low && (
                <span className="ml-1 text-red-500">⚠</span>
              )}
            </span>
          </div>

          {/* 레진 잔량 바 */}
          {printer.resin_remaining_percent !== null && (
            <div className="mt-1.5 h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  printer.is_resin_low ? 'bg-red-500' : 'bg-emerald-500'
                }`}
                style={{ width: `${printer.resin_remaining_percent}%` }}
              />
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
