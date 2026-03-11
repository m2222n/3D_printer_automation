/**
 * 프린터 타임라인 (간트 차트)
 * PreForm Dashboard의 Timeline 뷰 구현
 * - 24시간 시간축, 프린터별 작업 바 표시
 * - 현재 진행 중인 작업은 Now 선까지 연장
 */

import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { getPrintHistory } from '../services/api';
import type { PrinterSummary, PrintHistoryItem } from '../types/printer';

interface PrinterTimelineProps {
  printers: PrinterSummary[];
  historyItems: PrintHistoryItem[];
  onPrinterClick: (serial: string) => void;
}

// 타임라인 설정
const ROW_HEIGHT = 40;
const LABEL_WIDTH = 140;
const HEADER_HEIGHT = 32;
const HOUR_MARKS = [0, 3, 6, 9, 12, 15, 18, 21, 24];

// 작업 바 색상
function getBarColor(status: string): { fill: string; stroke: string } {
  switch (status) {
    case 'FINISHED':
      return { fill: '#22c55e', stroke: '#16a34a' };
    case 'PRINTING':
    case 'PREHEAT':
    case 'PRECOAT':
    case 'POSTCOAT':
      return { fill: '#3b82f6', stroke: '#2563eb' };
    case 'ERROR':
      return { fill: '#ef4444', stroke: '#dc2626' };
    case 'ABORTED':
    case 'ABORTING':
      return { fill: '#9ca3af', stroke: '#6b7280' };
    case 'PAUSED':
    case 'PAUSING':
      return { fill: '#f59e0b', stroke: '#d97706' };
    default:
      return { fill: '#6b7280', stroke: '#4b5563' };
  }
}

function formatHour(hour: number): string {
  if (hour === 0 || hour === 24) return '12 AM';
  if (hour === 12) return '12 PM';
  if (hour < 12) return `${hour} AM`;
  return `${hour - 12} PM`;
}

function formatTimeKST(date: Date): string {
  return date.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function PrinterTimeline({ printers, historyItems, onPrinterClick }: PrinterTimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const calendarRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(600);
  const [dayOffset, setDayOffset] = useState(0); // 0 = 오늘, -1 = 어제, ...
  const [showCalendar, setShowCalendar] = useState(false);
  const [localHistoryItems, setLocalHistoryItems] = useState<PrintHistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  // 과거 날짜일 때 해당 날짜의 이력을 직접 fetch
  const loadHistoryForDate = useCallback(async (offset: number) => {
    if (offset === 0) {
      // 오늘이면 props로 받은 데이터 사용
      setLocalHistoryItems([]);
      return;
    }
    setIsLoadingHistory(true);
    try {
      const dateFrom = new Date();
      dateFrom.setDate(dateFrom.getDate() + offset);
      dateFrom.setHours(0, 0, 0, 0);
      const dateTo = new Date(dateFrom);
      dateTo.setDate(dateTo.getDate() + 1);
      const res = await getPrintHistory(1, 200, {
        date_from: dateFrom.toISOString(),
        date_to: dateTo.toISOString(),
      });
      setLocalHistoryItems(res.items);
    } catch {
      setLocalHistoryItems([]);
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    loadHistoryForDate(dayOffset);
  }, [dayOffset, loadHistoryForDate]);

  // 실제 사용할 이력: 오늘이면 props, 과거면 직접 fetch한 데이터
  const effectiveHistoryItems = dayOffset === 0 ? historyItems : localHistoryItems;
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    name: string;
    status: string;
    time: string;
  } | null>(null);

  // 달력 외부 클릭 시 닫기
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (calendarRef.current && !calendarRef.current.contains(e.target as Node)) {
        setShowCalendar(false);
      }
    };
    if (showCalendar) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showCalendar]);

  // 현재 선택된 날짜
  const selectedDate = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + dayOffset);
    return d;
  }, [dayOffset]);

  // 출력 기록이 있는 날짜 세트 (달력 마킹용)
  const [printDates, setPrintDates] = useState<Set<string>>(new Set());

  // 달력이 열리거나 월이 바뀔 때 해당 월의 출력 기록 fetch
  const loadPrintDatesForMonth = useCallback(async (year: number, month: number) => {
    try {
      const dateFrom = new Date(year, month, 1);
      const dateTo = new Date(year, month + 1, 1);
      const res = await getPrintHistory(1, 500, {
        date_from: dateFrom.toISOString(),
        date_to: dateTo.toISOString(),
      });
      const dates = new Set<string>();
      for (const item of res.items) {
        if (item.started_at) {
          const d = new Date(item.started_at);
          dates.add(`${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`);
        }
      }
      setPrintDates(dates);
    } catch {
      setPrintDates(new Set());
    }
  }, []);

  // 달력 열 때 해당 월로 이동
  const openCalendar = () => {
    setCalendarMonth({ year: selectedDate.getFullYear(), month: selectedDate.getMonth() });
    setShowCalendar((v) => {
      if (!v) loadPrintDatesForMonth(selectedDate.getFullYear(), selectedDate.getMonth());
      return !v;
    });
  };

  // 달력에서 날짜 선택
  const selectDate = (date: Date) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const target = new Date(date);
    target.setHours(0, 0, 0, 0);
    const diff = Math.round((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
    if (diff <= 0) {
      setDayOffset(diff);
      setShowCalendar(false);
    }
  };

  // 컨테이너 너비 추적
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0].contentRect.width - LABEL_WIDTH - 16;
      setChartWidth(Math.max(width, 300));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 기준 시간 범위 (dayOffset 기준 24시간)
  const { rangeStart, rangeEnd } = useMemo(() => {
    const now = new Date();
    const startOfDay = new Date(now);
    startOfDay.setHours(0, 0, 0, 0);
    startOfDay.setDate(startOfDay.getDate() + dayOffset);
    const endOfDay = new Date(startOfDay);
    endOfDay.setDate(endOfDay.getDate() + 1);
    return { rangeStart: startOfDay, rangeEnd: endOfDay };
  }, [dayOffset]);

  const now = new Date();
  const isToday = dayOffset === 0;

  // 시간 → X 좌표 변환
  const timeToX = (date: Date): number => {
    const totalMs = rangeEnd.getTime() - rangeStart.getTime();
    const elapsed = date.getTime() - rangeStart.getTime();
    return Math.max(0, Math.min(chartWidth, (elapsed / totalMs) * chartWidth));
  };

  // 프린터별 작업 바 계산
  const printerBars = useMemo(() => {
    const result: Record<string, Array<{
      x: number;
      width: number;
      name: string;
      status: string;
      startTime: string;
      endTime: string;
      isActive: boolean;
    }>> = {};

    for (const printer of printers) {
      result[printer.serial] = [];
    }

    // 이력 데이터에서 바 생성
    for (const item of effectiveHistoryItems) {
      if (!item.started_at) continue;

      const start = new Date(item.started_at);
      const end = item.finished_at ? new Date(item.finished_at) : now;

      // 범위 밖이면 스킵
      if (end < rangeStart || start > rangeEnd) continue;

      const clampedStart = start < rangeStart ? rangeStart : start;
      const clampedEnd = end > rangeEnd ? rangeEnd : end;

      const x = timeToX(clampedStart);
      const xEnd = timeToX(clampedEnd);
      const width = Math.max(xEnd - x, 2); // 최소 2px

      if (!result[item.printer_serial]) {
        result[item.printer_serial] = [];
      }

      result[item.printer_serial].push({
        x,
        width,
        name: item.name,
        status: item.status,
        startTime: formatTimeKST(start),
        endTime: item.finished_at ? formatTimeKST(new Date(item.finished_at)) : '진행 중',
        isActive: !item.finished_at,
      });
    }

    // 현재 진행 중인 작업 (대시보드에서)
    for (const printer of printers) {
      const activeStatuses = ['PRINTING', 'PREHEAT', 'PRECOAT', 'POSTCOAT', 'PAUSING', 'PAUSED'];
      if (activeStatuses.includes(printer.status) && printer.print_started_at) {
        const start = new Date(printer.print_started_at);
        if (start < rangeEnd && now > rangeStart) {
          const clampedStart = start < rangeStart ? rangeStart : start;
          const clampedEnd = now > rangeEnd ? rangeEnd : now;
          const x = timeToX(clampedStart);
          const xEnd = timeToX(clampedEnd);
          const width = Math.max(xEnd - x, 2);

          // 이력에 이미 같은 작업이 있으면 스킵
          const existing = result[printer.serial]?.find(
            (b) => b.isActive && Math.abs(b.x - x) < 5
          );
          if (!existing) {
            if (!result[printer.serial]) result[printer.serial] = [];
            result[printer.serial].push({
              x,
              width,
              name: printer.current_job_name || '작업 진행 중',
              status: printer.status,
              startTime: formatTimeKST(start),
              endTime: '진행 중',
              isActive: true,
            });
          }
        }
      }
    }

    return result;
  }, [printers, effectiveHistoryItems, rangeStart, rangeEnd, chartWidth, now]);

  // Now 수직선 위치
  const nowX = isToday ? timeToX(now) : null;

  // 날짜 표시
  const dateLabel = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + dayOffset);
    return d.toLocaleDateString('ko-KR', {
      month: 'short',
      day: 'numeric',
      weekday: 'short',
    });
  }, [dayOffset]);

  const svgHeight = HEADER_HEIGHT + printers.length * ROW_HEIGHT + 4;

  return (
    <div className="mt-6 bg-white rounded-xl border" ref={containerRef}>
      {/* 헤더 */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <h3 className="text-sm font-semibold text-gray-900">타임라인</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setDayOffset((d) => d - 1)}
            className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
            title="이전 날"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>

          {/* 날짜 클릭 → 달력 */}
          <div className="relative" ref={calendarRef}>
            <button
              onClick={openCalendar}
              className="text-sm text-gray-600 min-w-[100px] text-center font-medium hover:text-blue-600 hover:bg-blue-50 px-2 py-1 rounded transition-colors flex items-center gap-1.5 justify-center"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              {dateLabel}
            </button>

            {showCalendar && (
              <MiniCalendar
                year={calendarMonth.year}
                month={calendarMonth.month}
                selectedDate={selectedDate}
                onSelect={selectDate}
                onMonthChange={(year, month) => {
                  setCalendarMonth({ year, month });
                  loadPrintDatesForMonth(year, month);
                }}
                printDates={printDates}
              />
            )}
          </div>

          <button
            onClick={() => setDayOffset((d) => Math.min(d + 1, 0))}
            disabled={dayOffset >= 0}
            className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="다음 날"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
          {dayOffset !== 0 && (
            <button
              onClick={() => setDayOffset(0)}
              className="ml-1 px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 rounded transition-colors font-medium"
            >
              오늘
            </button>
          )}
        </div>
      </div>

      {/* 차트 영역 */}
      <div className="px-4 pb-4 pt-2 overflow-x-auto relative">
        {isLoadingHistory && (
          <div className="absolute inset-0 bg-white/60 z-20 flex items-center justify-center">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          </div>
        )}
        <div className="flex" style={{ minWidth: LABEL_WIDTH + chartWidth }}>
          {/* 프린터 이름 열 */}
          <div className="flex-shrink-0" style={{ width: LABEL_WIDTH }}>
            <div style={{ height: HEADER_HEIGHT }} />
            {printers.map((printer) => (
              <button
                key={printer.serial}
                onClick={() => onPrinterClick(printer.serial)}
                className="flex items-center gap-2 w-full text-left px-2 hover:bg-gray-50 rounded transition-colors"
                style={{ height: ROW_HEIGHT }}
              >
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${getStatusDot(printer.status)}`} />
                <span className="text-sm text-gray-700 truncate font-medium">
                  {printer.name}
                </span>
              </button>
            ))}
          </div>

          {/* SVG 차트 */}
          <div className="flex-1 relative">
            <svg
              width={chartWidth}
              height={svgHeight}
              className="select-none"
              onMouseLeave={() => setTooltip(null)}
            >
              {/* 시간축 눈금 */}
              {HOUR_MARKS.map((hour) => {
                const x = (hour / 24) * chartWidth;
                return (
                  <g key={hour}>
                    <line
                      x1={x}
                      y1={HEADER_HEIGHT}
                      x2={x}
                      y2={svgHeight}
                      stroke="#e5e7eb"
                      strokeWidth={1}
                    />
                    <text
                      x={x}
                      y={HEADER_HEIGHT - 8}
                      textAnchor="middle"
                      className="text-[10px] fill-gray-400"
                    >
                      {formatHour(hour)}
                    </text>
                  </g>
                );
              })}

              {/* 행 배경 (교대 줄무늬) */}
              {printers.map((_, i) => (
                <rect
                  key={i}
                  x={0}
                  y={HEADER_HEIGHT + i * ROW_HEIGHT}
                  width={chartWidth}
                  height={ROW_HEIGHT}
                  fill={i % 2 === 0 ? '#fafafa' : '#ffffff'}
                />
              ))}

              {/* 행 구분선 */}
              {printers.map((_, i) => (
                <line
                  key={`line-${i}`}
                  x1={0}
                  y1={HEADER_HEIGHT + (i + 1) * ROW_HEIGHT}
                  x2={chartWidth}
                  y2={HEADER_HEIGHT + (i + 1) * ROW_HEIGHT}
                  stroke="#f3f4f6"
                  strokeWidth={1}
                />
              ))}

              {/* 작업 바 */}
              {printers.map((printer, rowIndex) => {
                const bars = printerBars[printer.serial] || [];
                const y = HEADER_HEIGHT + rowIndex * ROW_HEIGHT + 8;
                const barHeight = ROW_HEIGHT - 16;

                return bars.map((bar, barIndex) => {
                  const { fill, stroke } = getBarColor(bar.status);
                  return (
                    <g
                      key={`${printer.serial}-${barIndex}`}
                      onMouseEnter={(e) => {
                        const svgRect = (e.target as SVGElement).closest('svg')?.getBoundingClientRect();
                        if (svgRect) {
                          setTooltip({
                            x: bar.x + bar.width / 2,
                            y: y - 4,
                            name: bar.name,
                            status: bar.status,
                            time: `${bar.startTime} ~ ${bar.endTime}`,
                          });
                        }
                      }}
                      onMouseLeave={() => setTooltip(null)}
                      className="cursor-pointer"
                    >
                      <rect
                        x={bar.x}
                        y={y}
                        width={bar.width}
                        height={barHeight}
                        rx={4}
                        fill={fill}
                        stroke={stroke}
                        strokeWidth={1}
                        opacity={0.85}
                      />
                      {/* 진행 중 펄스 애니메이션 */}
                      {bar.isActive && (
                        <rect
                          x={bar.x}
                          y={y}
                          width={bar.width}
                          height={barHeight}
                          rx={4}
                          fill={fill}
                          opacity={0.3}
                        >
                          <animate
                            attributeName="opacity"
                            values="0.3;0.1;0.3"
                            dur="2s"
                            repeatCount="indefinite"
                          />
                        </rect>
                      )}
                      {/* 바 안에 작업명 (충분히 넓을 때만) */}
                      {bar.width > 60 && (
                        <text
                          x={bar.x + bar.width / 2}
                          y={y + barHeight / 2 + 1}
                          textAnchor="middle"
                          dominantBaseline="middle"
                          className="text-[10px] fill-white font-medium pointer-events-none"
                        >
                          {bar.name.length > Math.floor(bar.width / 7)
                            ? bar.name.slice(0, Math.floor(bar.width / 7) - 1) + '…'
                            : bar.name}
                        </text>
                      )}
                    </g>
                  );
                });
              })}

              {/* Now 수직선 */}
              {nowX !== null && (
                <g>
                  <line
                    x1={nowX}
                    y1={HEADER_HEIGHT - 4}
                    x2={nowX}
                    y2={svgHeight}
                    stroke="#ef4444"
                    strokeWidth={1.5}
                    strokeDasharray="4 2"
                  />
                  <text
                    x={nowX}
                    y={HEADER_HEIGHT - 8}
                    textAnchor="middle"
                    className="text-[10px] fill-red-500 font-semibold"
                  >
                    Now
                  </text>
                </g>
              )}
            </svg>

            {/* 툴팁 */}
            {tooltip && (
              <div
                className="absolute bg-gray-900 text-white text-xs rounded-lg px-3 py-2 pointer-events-none shadow-lg z-10"
                style={{
                  left: tooltip.x,
                  top: tooltip.y,
                  transform: 'translate(-50%, -100%)',
                }}
              >
                <p className="font-medium">{tooltip.name}</p>
                <p className="text-gray-300 mt-0.5">{tooltip.time}</p>
              </div>
            )}
          </div>
        </div>

        {/* 범례 */}
        <div className="flex items-center gap-4 mt-3 pt-3 border-t">
          <span className="text-xs text-gray-400">범례:</span>
          {[
            { label: '완료', color: '#22c55e' },
            { label: '진행 중', color: '#3b82f6' },
            { label: '오류', color: '#ef4444' },
            { label: '중단', color: '#9ca3af' },
          ].map((item) => (
            <div key={item.label} className="flex items-center gap-1.5">
              <div className="w-3 h-2 rounded-sm" style={{ backgroundColor: item.color }} />
              <span className="text-xs text-gray-500">{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// 미니 달력 컴포넌트
interface MiniCalendarProps {
  year: number;
  month: number; // 0-indexed
  selectedDate: Date;
  onSelect: (date: Date) => void;
  onMonthChange: (year: number, month: number) => void;
  printDates?: Set<string>;
}

function MiniCalendar({ year, month, selectedDate, onSelect, onMonthChange, printDates }: MiniCalendarProps) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const selected = new Date(selectedDate);
  selected.setHours(0, 0, 0, 0);

  // 해당 월의 첫날과 마지막날
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const startDayOfWeek = firstDay.getDay(); // 0=일, 1=월, ...

  // 달력 셀 생성
  const cells: (Date | null)[] = [];
  for (let i = 0; i < startDayOfWeek; i++) cells.push(null);
  for (let d = 1; d <= lastDay.getDate(); d++) cells.push(new Date(year, month, d));

  const monthLabel = `${year}년 ${month + 1}월`;

  const prevMonth = () => {
    if (month === 0) onMonthChange(year - 1, 11);
    else onMonthChange(year, month - 1);
  };

  const nextMonth = () => {
    // 미래 월로는 제한
    const nextM = month === 11 ? 0 : month + 1;
    const nextY = month === 11 ? year + 1 : year;
    const nextFirst = new Date(nextY, nextM, 1);
    if (nextFirst <= today) {
      onMonthChange(nextY, nextM);
    }
  };

  const isNextDisabled = (() => {
    const nextM = month === 11 ? 0 : month + 1;
    const nextY = month === 11 ? year + 1 : year;
    return new Date(nextY, nextM, 1) > today;
  })();

  return (
    <div className="absolute right-0 top-full mt-1 bg-white rounded-xl shadow-xl border z-50 p-3 w-64">
      {/* 월 네비게이션 */}
      <div className="flex items-center justify-between mb-2">
        <button
          onClick={prevMonth}
          className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <span className="text-sm font-semibold text-gray-900">{monthLabel}</span>
        <button
          onClick={nextMonth}
          disabled={isNextDisabled}
          className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {/* 요일 헤더 */}
      <div className="grid grid-cols-7 mb-1">
        {['일', '월', '화', '수', '목', '금', '토'].map((d) => (
          <div key={d} className="text-center text-[10px] text-gray-400 font-medium py-1">
            {d}
          </div>
        ))}
      </div>

      {/* 날짜 그리드 */}
      <div className="grid grid-cols-7">
        {cells.map((date, i) => {
          if (!date) return <div key={`empty-${i}`} />;

          const isFuture = date > today;
          const isToday = date.getTime() === today.getTime();
          const isSelected = date.getTime() === selected.getTime();
          const hasPrints = printDates?.has(`${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`);

          return (
            <button
              key={date.getDate()}
              onClick={() => !isFuture && onSelect(date)}
              disabled={isFuture}
              className={`relative w-8 h-8 mx-auto rounded-full text-xs font-medium transition-colors ${
                isSelected
                  ? 'bg-blue-500 text-white'
                  : isToday
                  ? 'bg-blue-100 text-blue-700 font-bold'
                  : isFuture
                  ? 'text-gray-300 cursor-not-allowed'
                  : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              {date.getDate()}
              {hasPrints && (
                <span className={`absolute bottom-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full ${
                  isSelected ? 'bg-white' : 'bg-blue-500'
                }`} />
              )}
            </button>
          );
        })}
      </div>

      {/* 오늘 바로가기 */}
      <div className="mt-2 pt-2 border-t">
        <button
          onClick={() => onSelect(today)}
          className="w-full text-xs text-blue-600 hover:bg-blue-50 rounded py-1 font-medium transition-colors"
        >
          오늘로 이동
        </button>
      </div>
    </div>
  );
}

function getStatusDot(status: string): string {
  switch (status) {
    case 'PRINTING': return 'bg-blue-500 animate-pulse';
    case 'FINISHED': return 'bg-green-500';
    case 'IDLE': return 'bg-gray-400';
    case 'ERROR': return 'bg-red-500';
    case 'OFFLINE': return 'bg-gray-300';
    default: return 'bg-gray-400';
  }
}
