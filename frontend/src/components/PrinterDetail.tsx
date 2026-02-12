/**
 * 프린터 상세 정보 컴포넌트
 * 개별 프린터의 전체 상태를 표시
 */

import type { PrinterSummary } from '../types/printer';
import { getStatusLabel, formatDuration, formatResinAmount } from '../types/printer';

interface PrinterDetailProps {
  printer: PrinterSummary;
  onBack: () => void;
}

export function PrinterDetail({ printer, onBack }: PrinterDetailProps) {
  const isPrinting = printer.status === 'PRINTING';
  const isOffline = printer.status === 'OFFLINE';

  return (
    <div>
      {/* 뒤로가기 */}
      <button
        onClick={onBack}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        전체 보기
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 왼쪽: 프린터 정보 */}
        <div className="space-y-4">
          {/* 프린터 기본 정보 카드 */}
          <div className="bg-white rounded-xl border shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold text-gray-900">{printer.name}</h3>
              <StatusBadge status={printer.status} />
            </div>

            <div className="space-y-3">
              <InfoRow label="시리얼 번호" value={printer.serial} />
              <InfoRow label="온라인" value={printer.is_online ? '연결됨' : '연결 안 됨'} />
              <InfoRow label="프린트 준비" value={printer.is_ready ? '준비 완료' : '준비 안 됨'} />
              <InfoRow
                label="마지막 업데이트"
                value={new Date(printer.last_update).toLocaleString('ko-KR')}
              />
            </div>
          </div>

          {/* 레진 정보 */}
          <div className="bg-white rounded-xl border shadow-sm p-6">
            <h4 className="font-semibold text-gray-800 mb-4">레진 정보</h4>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-sm mb-1.5">
                  <span className="text-gray-600">잔량</span>
                  <span className={`font-medium ${printer.is_resin_low ? 'text-red-600' : 'text-gray-900'}`}>
                    {formatResinAmount(printer.resin_remaining_ml)}
                    {printer.resin_remaining_percent !== null && (
                      <span className="text-gray-400 ml-1">
                        ({printer.resin_remaining_percent.toFixed(0)}%)
                      </span>
                    )}
                  </span>
                </div>
                {printer.resin_remaining_percent !== null && (
                  <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        printer.is_resin_low ? 'bg-red-500' : 'bg-emerald-500'
                      }`}
                      style={{ width: `${printer.resin_remaining_percent}%` }}
                    />
                  </div>
                )}
              </div>
              {printer.is_resin_low && (
                <div className="flex items-center gap-2 p-2 bg-red-50 rounded-lg text-sm text-red-700">
                  <span>!</span>
                  <span>레진 잔량이 부족합니다. 교체가 필요합니다.</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 오른쪽: 출력 상태 */}
        <div className="space-y-4">
          {/* 현재 작업 */}
          <div className="bg-white rounded-xl border shadow-sm p-6">
            <h4 className="font-semibold text-gray-800 mb-4">현재 작업</h4>
            {isPrinting && printer.current_job_name ? (
              <div className="space-y-4">
                <div>
                  <p className="text-sm text-gray-500 mb-1">작업명</p>
                  <p className="font-medium text-gray-900">{printer.current_job_name}</p>
                </div>

                {/* 진행률 */}
                <div>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-600">진행률</span>
                    <span className="font-bold text-blue-600 text-lg">
                      {printer.progress_percent?.toFixed(1)}%
                    </span>
                  </div>
                  <div className="h-4 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all duration-500"
                      style={{ width: `${printer.progress_percent || 0}%` }}
                    />
                  </div>
                </div>

                {/* 레이어 정보 */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-gray-500">현재 레이어</p>
                    <p className="text-lg font-semibold text-gray-900">
                      {printer.current_layer} / {printer.total_layers}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">남은 시간</p>
                    <p className="text-lg font-semibold text-gray-900">
                      {printer.remaining_minutes ? formatDuration(printer.remaining_minutes) : '-'}
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8">
                <div className="text-4xl mb-3 text-gray-300">
                  {isOffline ? (
                    <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18.364 5.636a9 9 0 010 12.728M5.636 5.636a9 9 0 000 12.728M12 12v.01" />
                    </svg>
                  ) : (
                    <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  )}
                </div>
                <p className="text-gray-500">
                  {printer.status === 'FINISHED' && '출력 완료 - 빌드 플레이트를 회수해주세요'}
                  {printer.status === 'IDLE' && '대기 중 - 프린트 제어에서 작업을 시작하세요'}
                  {printer.status === 'ERROR' && '오류 발생 - 프린터를 확인해주세요'}
                  {printer.status === 'OFFLINE' && '프린터가 오프라인입니다'}
                </p>
              </div>
            )}
          </div>

          {/* 프린터 상태 요약 */}
          <div className="bg-white rounded-xl border shadow-sm p-6">
            <h4 className="font-semibold text-gray-800 mb-4">상태 요약</h4>
            <div className="grid grid-cols-2 gap-3">
              <StatusItem
                label="연결"
                value={printer.is_online ? '온라인' : '오프라인'}
                isOk={printer.is_online}
              />
              <StatusItem
                label="프린트 준비"
                value={printer.is_ready ? '준비' : '미준비'}
                isOk={printer.is_ready}
              />
              <StatusItem
                label="레진"
                value={printer.is_resin_low ? '부족' : '충분'}
                isOk={!printer.is_resin_low}
              />
              <StatusItem
                label="오류"
                value={printer.has_error ? '발생' : '없음'}
                isOk={!printer.has_error}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// 상태 뱃지
function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    PRINTING: 'bg-blue-100 text-blue-700',
    FINISHED: 'bg-green-100 text-green-700',
    IDLE: 'bg-gray-100 text-gray-700',
    ERROR: 'bg-red-100 text-red-700',
    OFFLINE: 'bg-gray-100 text-gray-500',
  };

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${styles[status] || styles.IDLE}`}>
      {getStatusLabel(status as any)}
    </span>
  );
}

// 정보 행
function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-gray-100 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className="text-sm font-medium text-gray-900">{value}</span>
    </div>
  );
}

// 상태 아이템
function StatusItem({ label, value, isOk }: { label: string; value: string; isOk: boolean }) {
  return (
    <div className={`p-3 rounded-lg ${isOk ? 'bg-green-50' : 'bg-red-50'}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`font-medium ${isOk ? 'text-green-700' : 'text-red-700'}`}>{value}</p>
    </div>
  );
}
