/**
 * 프린터 상세 정보 모달 (PreForm 스타일)
 * 어떤 탭에서든 프린터 이름 클릭 시 슬라이드-오버 패널로 표시
 */

import { useState, useEffect, useRef } from 'react';
import { getPrinterSummary } from '../services/api';
import type { PrinterSummary } from '../types/printer';
import { getStatusLabel, formatResinAmount } from '../types/printer';

type ModalTab = 'details' | 'settings';

interface PrinterInfoModalProps {
  serial: string;
  onClose: () => void;
}

// machine_type → 표시용 이름
function formatMachineType(type: string | null): string {
  if (!type) return '-';
  switch (type) {
    case 'FORM-4-0': return 'Form 4';
    case 'FORM-3-0': return 'Form 3';
    case 'FORM-3L-0': return 'Form 3L';
    case 'FORM-3BL-0': return 'Form 3BL';
    default: return type;
  }
}

// 상태별 도트 색상
function getStatusDotClass(status: string): string {
  switch (status) {
    case 'PRINTING': return 'bg-blue-500';
    case 'PREHEAT': return 'bg-orange-500';
    case 'FINISHED': return 'bg-green-500';
    case 'ERROR': return 'bg-red-500';
    case 'OFFLINE': return 'bg-gray-400';
    case 'IDLE': return 'bg-green-400';
    default: return 'bg-gray-400';
  }
}

export function PrinterInfoModal({ serial, onClose }: PrinterInfoModalProps) {
  const [printer, setPrinter] = useState<PrinterSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<ModalTab>('details');
  const panelRef = useRef<HTMLDivElement>(null);

  // 프린터 데이터 로드
  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    getPrinterSummary(serial)
      .then((data) => {
        if (!cancelled) setPrinter(data);
      })
      .catch(() => {
        // 로드 실패 시 모달 닫기
        if (!cancelled) onClose();
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, [serial, onClose]);

  // ESC 키로 닫기
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // 백드롭 클릭으로 닫기
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      onClick={handleBackdropClick}
    >
      {/* 반투명 백드롭 */}
      <div className="absolute inset-0 bg-black/30 transition-opacity" />

      {/* 슬라이드 패널 */}
      <div
        ref={panelRef}
        className="relative w-full max-w-md bg-white shadow-2xl flex flex-col animate-slide-in-right"
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0">
          <h2 className="text-lg font-bold text-gray-900">
            {printer?.name || serial}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 탭 */}
        <div className="flex border-b flex-shrink-0">
          {(['details', 'settings'] as ModalTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab === 'details' ? 'Details' : 'Settings'}
            </button>
          ))}
        </div>

        {/* 본문 */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center h-48">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
            </div>
          ) : printer ? (
            activeTab === 'details' ? (
              <DetailsTab printer={printer} />
            ) : (
              <SettingsTab printer={printer} />
            )
          ) : null}
        </div>
      </div>

      {/* 슬라이드 애니메이션 CSS */}
      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slide-in-right {
          animation: slideInRight 0.2s ease-out;
        }
      `}</style>
    </div>
  );
}

// ==========================================
// Details 탭
// ==========================================

function DetailsTab({ printer }: { printer: PrinterSummary }) {
  return (
    <div>
      {/* 최근 작업 */}
      {printer.current_job_name && (
        <div className="px-5 py-4 border-b bg-gray-50">
          <p className="text-sm font-medium text-gray-900 truncate">
            {printer.current_job_name}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">
            {printer.status === 'PRINTING' || printer.status === 'PREHEAT'
              ? `${getStatusLabel(printer.status as any)}...`
              : printer.status === 'FINISHED'
              ? '출력 완료'
              : getStatusLabel(printer.status as any)}
          </p>
        </div>
      )}

      {/* 상세 정보 리스트 */}
      <div className="divide-y divide-gray-100">
        {/* Status */}
        <DetailRow
          icon={<StatusDot status={printer.status} />}
          label="Status"
          value={getStatusLabel(printer.status as any)}
        />

        {/* Device Type */}
        <DetailRow
          icon={<IconPrinter />}
          label="Device Type"
          value={formatMachineType(printer.machine_type)}
        />

        {/* Serial Name */}
        <DetailRow
          icon={<IconSerial />}
          label="Serial Name"
          value={printer.name}
        />

        {/* Tank */}
        <DetailRow
          icon={<IconTank />}
          label="Tank"
          value={printer.tank_serial ? `${printer.tank_serial}` : 'Missing'}
          valueClass={!printer.tank_serial ? 'text-gray-400 italic' : undefined}
        />

        {/* Cartridge */}
        <div className="px-5 py-3.5 flex items-center gap-3">
          <div className="flex-shrink-0 w-5 text-center text-gray-400">
            <IconCartridge />
          </div>
          <span className="text-sm text-gray-600 w-24 flex-shrink-0">Cartridge</span>
          <div className="flex-1 flex items-center gap-2 justify-end">
            {printer.cartridge_material_name ? (
              <>
                <span className="text-sm font-medium text-gray-900">
                  {printer.cartridge_material_name}
                </span>
                {printer.resin_remaining_percent !== null && (
                  <div className="w-20 h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        printer.is_resin_low ? 'bg-orange-500' : 'bg-gray-400'
                      }`}
                      style={{ width: `${printer.resin_remaining_percent}%` }}
                    />
                  </div>
                )}
              </>
            ) : (
              <span className="text-sm text-gray-400 italic">Missing</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ==========================================
// Settings 탭
// ==========================================

function SettingsTab({ printer }: { printer: PrinterSummary }) {
  return (
    <div className="divide-y divide-gray-100">
      {/* Firmware */}
      <DetailRow
        icon={<IconCircle />}
        label="Firmware"
        value={printer.firmware_version || '-'}
      />

      {/* Temperature */}
      <DetailRow
        icon={<IconCircle />}
        label="Temperature"
        value={printer.temperature !== null && printer.temperature !== undefined
          ? `${printer.temperature.toFixed(1)}°C`
          : '--'}
      />

      {/* Ready to Print */}
      <DetailRow
        icon={<IconCircle />}
        label="Ready"
        value={printer.is_ready ? 'Ready' : 'Not Ready'}
        valueClass={printer.is_ready ? 'text-green-600' : 'text-gray-500'}
      />

      {/* Build Platform */}
      <DetailRow
        icon={<IconCircle />}
        label="Build Platform"
        value={formatBuildPlatform(printer.build_platform_contents)}
      />

      {/* Resin Remaining */}
      <DetailRow
        icon={<IconCircle />}
        label="Resin"
        value={formatResinAmount(printer.resin_remaining_ml)}
        valueClass={printer.is_resin_low ? 'text-red-600' : undefined}
      />

      {/* Tank Print Count */}
      {printer.tank_print_count !== null && (
        <DetailRow
          icon={<IconCircle />}
          label="Tank Prints"
          value={`${printer.tank_print_count} prints`}
        />
      )}
    </div>
  );
}

// ==========================================
// 공통 컴포넌트
// ==========================================

function DetailRow({
  icon,
  label,
  value,
  valueClass,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="px-5 py-3.5 flex items-center gap-3">
      <div className="flex-shrink-0 w-5 text-center text-gray-400">{icon}</div>
      <span className="text-sm text-gray-600 flex-1">{label}</span>
      <span className={`text-sm font-medium text-right ${valueClass || 'text-gray-900'}`}>
        {value}
      </span>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  return <div className={`w-3 h-3 rounded-full mx-auto ${getStatusDotClass(status)}`} />;
}

function formatBuildPlatform(state: string | null): string {
  if (!state) return '-';
  switch (state) {
    case 'EMPTY':
    case 'BUILD_PLATFORM_CONTENTS_EMPTY':
    case 'BUILD_PLATFORM_CONTENTS_CONFIRMED_CLEAR':
      return 'Empty';
    case 'HAS_PARTS':
    case 'BUILD_PLATFORM_CONTENTS_HAS_PARTS':
      return 'Has Parts';
    case 'BUILD_PLATFORM_CONTENTS_MISSING':
      return 'Missing';
    case 'BUILD_PLATFORM_CONTENTS_UNCONFIRMED':
      return 'Unconfirmed';
    default:
      return state;
  }
}

// ==========================================
// 아이콘들
// ==========================================

function IconPrinter() {
  return (
    <svg className="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2M6 14h12v8H6v-8z" />
    </svg>
  );
}

function IconSerial() {
  return (
    <svg className="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function IconTank() {
  return (
    <svg className="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  );
}

function IconCartridge() {
  return (
    <svg className="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function IconCircle() {
  return <div className="w-2.5 h-2.5 rounded-full bg-gray-300 mx-auto" />;
}
