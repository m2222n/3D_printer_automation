/**
 * 프린터 상세 정보 모달 (PreForm 스타일)
 * 어떤 탭에서든 프린터 이름 클릭 시 슬라이드-오버 패널로 표시
 * 3탭: Details / Settings / Services
 */

import { useState, useEffect, useRef } from 'react';
import { getPrinterSummary } from '../services/api';
import type { PrinterSummary } from '../types/printer';
import { getStatusLabel, formatResinAmount } from '../types/printer';

type ModalTab = 'details' | 'settings' | 'services';

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

// 상대 시간 포맷 ("a month ago", "2 hours ago" 등)
function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);
  const diffMonth = Math.floor(diffDay / 30);

  if (diffMonth >= 1) return `${diffMonth}개월 전`;
  if (diffDay >= 1) return `${diffDay}일 전`;
  if (diffHr >= 1) return `${diffHr}시간 전`;
  if (diffMin >= 1) return `${diffMin}분 전`;
  return '방금 전';
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

  const tabs: { key: ModalTab; label: string }[] = [
    { key: 'details', label: 'Details' },
    { key: 'settings', label: 'Settings' },
    { key: 'services', label: 'Services' },
  ];

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
        className="relative w-full max-w-lg bg-white shadow-2xl flex flex-col animate-slide-in-right"
      >
        {/* 헤더: 프린터 이름 + 닫기 */}
        <div className="flex items-center justify-between px-6 py-4 border-b flex-shrink-0">
          <h2 className="text-lg font-semibold text-gray-900">
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

        {/* 탭 네비게이션 */}
        <div className="flex border-b flex-shrink-0">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
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
            ) : activeTab === 'settings' ? (
              <SettingsTab printer={printer} />
            ) : (
              <ServicesTab />
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
// Details 탭 (PreForm 스크린샷 1번째)
// ==========================================

function DetailsTab({ printer }: { printer: PrinterSummary }) {
  // 최근 작업 상태 텍스트
  const getJobStatusText = (): string => {
    if (printer.status === 'PRINTING' || printer.status === 'PREHEAT') {
      return `${getStatusLabel(printer.status as any)}...`;
    }
    if (printer.status === 'FINISHED' && printer.last_print_finished_at) {
      return `Printing Completed ${formatRelativeTime(printer.last_print_finished_at)}`;
    }
    if (printer.current_job_name) {
      return getStatusLabel(printer.status as any);
    }
    return '';
  };

  return (
    <div>
      {/* 최근 작업 카드 (PreForm 스타일: 썸네일 + 이름 + 상태 + > 화살표) */}
      {printer.current_job_name && (
        <div className="px-6 py-4 border-b flex items-center gap-3">
          {/* 썸네일 (없으면 플레이스홀더) */}
          <div className="w-12 h-12 rounded-lg bg-gray-100 flex-shrink-0 flex items-center justify-center overflow-hidden">
            {printer.last_print_thumbnail ? (
              <img src={printer.last_print_thumbnail} alt="" className="w-full h-full object-cover" />
            ) : (
              <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{printer.current_job_name}</p>
            <p className="text-xs text-green-600 mt-0.5">{getJobStatusText()}</p>
          </div>
          <svg className="w-4 h-4 text-gray-300 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </div>
      )}

      {/* 상세 정보 리스트 */}
      <div className="divide-y divide-gray-100">
        {/* Status */}
        <DetailRow
          icon={<StatusDot status={printer.status} />}
          label="Status"
          value={printer.is_online ? getStatusLabel(printer.status as any) : 'Offline'}
        />

        {/* Device Type */}
        <DetailRow
          icon={<IconDevice />}
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
          value={printer.tank_serial ? printer.tank_serial : 'Missing'}
          valueClass={!printer.tank_serial ? 'text-gray-400 italic' : undefined}
        />

        {/* Cartridge (특별 레이아웃: 레진 이름 + 잔량 바) */}
        <div className="px-6 py-3.5 flex items-center gap-3">
          <div className="flex-shrink-0 w-5 text-center text-gray-400">
            <IconCartridge />
          </div>
          <span className="text-sm text-gray-600 w-24 flex-shrink-0">Cartridge</span>
          <div className="flex-1 flex items-center gap-2 justify-end">
            {printer.cartridge_material_name ? (
              <>
                {/* 레진 색상 도트 */}
                <ResinColorDot materialCode={printer.cartridge_material_code} />
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

        {/* Location */}
        <DetailRow
          icon={<IconLocation />}
          label="Location"
          value={printer.location || '-'}
          valueClass={!printer.location ? 'text-gray-400 italic' : undefined}
        />
      </div>
    </div>
  );
}

// ==========================================
// Settings 탭 (PreForm 스크린샷 2번째)
// ==========================================

function SettingsTab({ printer }: { printer: PrinterSummary }) {
  return (
    <div className="divide-y divide-gray-100">
      {/* Automatic updates - API 미지원, 표시만 */}
      <DetailRow
        icon={<IconCircleDot />}
        label="Automatic updates"
        value="-"
        valueClass="text-gray-400"
      />

      {/* Firmware */}
      <DetailRow
        icon={<IconCircleDot />}
        label="Firmware"
        value={printer.firmware_version || '-'}
      />

      {/* Notifications - API 미지원, 표시만 */}
      <DetailRow
        icon={<IconNotification />}
        label="Notifications"
        value="-"
        valueClass="text-gray-400"
      />

      {/* Remote Print */}
      <DetailRow
        icon={<IconCloud />}
        label="Remote Print"
        value={printer.is_remote_print_enabled === true ? 'Enabled' : printer.is_remote_print_enabled === false ? 'Disabled' : '-'}
        valueClass={printer.is_remote_print_enabled ? 'text-gray-900' : 'text-gray-400'}
      />

      {/* Printer Group */}
      <DetailRow
        icon={<IconGroup />}
        label="Printer Group"
        value={printer.group_name || '-'}
        valueClass={!printer.group_name ? 'text-gray-400' : undefined}
      />

      {/* Temperature */}
      <DetailRow
        icon={<IconCircleDot />}
        label="Temperature"
        value={printer.temperature !== null && printer.temperature !== undefined
          ? `${printer.temperature.toFixed(1)}°C`
          : '--'}
      />

      {/* Ready to Print */}
      <DetailRow
        icon={<IconCircleDot />}
        label="Ready"
        value={printer.is_ready ? 'Ready' : 'Not Ready'}
        valueClass={printer.is_ready ? 'text-green-600' : 'text-gray-500'}
      />

      {/* Build Platform */}
      <DetailRow
        icon={<IconCircleDot />}
        label="Build Platform"
        value={formatBuildPlatform(printer.build_platform_contents)}
      />

      {/* Resin Remaining */}
      <DetailRow
        icon={<IconCircleDot />}
        label="Resin"
        value={formatResinAmount(printer.resin_remaining_ml)}
        valueClass={printer.is_resin_low ? 'text-red-600' : undefined}
      />

      {/* Tank Print Count */}
      {printer.tank_print_count !== null && (
        <DetailRow
          icon={<IconCircleDot />}
          label="Tank Prints"
          value={`${printer.tank_print_count} prints`}
        />
      )}
    </div>
  );
}

// ==========================================
// Services 탭 (PreForm 스크린샷 3번째)
// ==========================================

function ServicesTab() {
  return (
    <div>
      {/* BETA 안내 배너 */}
      <div className="px-6 py-4 border-b flex items-start gap-3">
        <div className="flex-1">
          <p className="text-sm text-gray-600 font-medium">
            Some information may be outdated or not displayed correctly
          </p>
        </div>
        <span className="px-2 py-0.5 bg-gray-900 text-white text-xs font-bold rounded-full flex-shrink-0">
          BETA
        </span>
      </div>

      {/* Warranty */}
      <div className="px-6 py-4 border-b flex items-center justify-between">
        <span className="text-sm text-gray-700">Warranty</span>
        <span className="text-sm text-gray-900 font-medium">Not Available</span>
      </div>

      {/* Service Plans */}
      <div className="px-6 py-4 border-b flex items-center justify-between gap-4">
        <p className="text-sm text-gray-500 flex-1">
          We didn't find any service plans. If this is incorrect, please contact support.
        </p>
        <a
          href="https://support.formlabs.com"
          target="_blank"
          rel="noopener noreferrer"
          className="px-4 py-1.5 text-sm text-blue-600 border border-blue-200 rounded-full hover:bg-blue-50 transition-colors whitespace-nowrap flex-shrink-0"
        >
          Get in touch
        </a>
      </div>
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
    <div className="px-6 py-3.5 flex items-center gap-3">
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

// 레진 material_code → 색상 도트
function ResinColorDot({ materialCode }: { materialCode: string | null }) {
  const color = getResinColor(materialCode);
  return (
    <div
      className="w-3 h-3 rounded-full flex-shrink-0 border border-gray-200"
      style={{ backgroundColor: color }}
    />
  );
}

function getResinColor(code: string | null): string {
  if (!code) return '#9ca3af';
  const c = code.toUpperCase();
  if (c.includes('GR') || c.includes('GREY')) return '#808080';
  if (c.includes('CL') || c.includes('CLEAR')) return '#d4e6f1';
  if (c.includes('BK') || c.includes('BLACK')) return '#2d2d2d';
  if (c.includes('WH') || c.includes('WHITE')) return '#f5f5f5';
  if (c.includes('TN') || c.includes('TAN')) return '#d2b48c';
  if (c.includes('BL') || c.includes('BLUE')) return '#4a90d9';
  return '#9ca3af';
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
// 아이콘들 (PreForm 스타일 - 라인 아이콘)
// ==========================================

function IconCircleDot() {
  return <div className="w-2.5 h-2.5 rounded-full bg-gray-300 mx-auto" />;
}

function IconDevice() {
  return (
    <svg className="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
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

function IconLocation() {
  return (
    <svg className="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
    </svg>
  );
}

function IconNotification() {
  return (
    <svg className="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
    </svg>
  );
}

function IconCloud() {
  return (
    <svg className="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z" />
    </svg>
  );
}

function IconGroup() {
  return (
    <svg className="w-4 h-4 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6.115 5.19l.319 1.913A6 6 0 008.11 10.36L9.75 12l-.387.775c-.217.433-.132.956.21 1.298l1.348 1.348c.21.21.329.497.329.795v1.089c0 .426.24.815.622 1.006l.153.076c.433.217.956.132 1.298-.21l.723-.723a8.7 8.7 0 002.288-4.042 1.087 1.087 0 00-.358-1.099l-1.33-1.108c-.251-.209-.556-.32-.87-.318l-1.8.012a1.079 1.079 0 01-.758-.312L10.08 9.01a.999.999 0 01-.207-.862l.225-.9a1.078 1.078 0 00-.156-.885L8.698 5.527a1.09 1.09 0 00-.918-.495H6.115z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}
