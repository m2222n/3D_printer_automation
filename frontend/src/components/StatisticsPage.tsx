/**
 * 통계 페이지
 * PreForm Dashboard 수준의 Material Usage, Prints Over Time, 프린터별 통계
 */

import { useState, useEffect, useCallback } from 'react';
import { getStatistics, getDashboard } from '../services/api';
import type { StatisticsData } from '../services/api';
import type { PrinterSummary } from '../types/printer';

type PrinterFilter = 'all' | string;

// 레진 양 포맷 (소수점 이하 적절히 표시)
function formatNumber(n: number): string {
  if (n === 0) return '0';
  if (n < 1) return n.toFixed(2);
  if (n < 10) return n.toFixed(1);
  return Math.round(n).toLocaleString('en-US').replace(/,/g, ' ');
}

export function StatisticsPage() {
  const [stats, setStats] = useState<StatisticsData | null>(null);
  const [printers, setPrinters] = useState<PrinterSummary[]>([]);
  const [printerFilter, setPrinterFilter] = useState<PrinterFilter>('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const filters: { printer_serial?: string; date_from?: string; date_to?: string } = {};
      if (printerFilter !== 'all') filters.printer_serial = printerFilter;
      if (dateFrom) filters.date_from = new Date(dateFrom + 'T00:00:00+09:00').toISOString();
      if (dateTo) filters.date_to = new Date(dateTo + 'T23:59:59+09:00').toISOString();

      const [statsData, dashboard] = await Promise.all([
        getStatistics(filters),
        getDashboard(),
      ]);
      setStats(statsData);
      setPrinters(dashboard.printers);
    } catch (err) {
      console.error('통계 로드 실패:', err);
    } finally {
      setIsLoading(false);
    }
  }, [printerFilter, dateFrom, dateTo]);

  useEffect(() => { loadData(); }, [loadData]);

  const setQuickDateRange = useCallback((days: number) => {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - days);
    setDateFrom(from.toISOString().slice(0, 10));
    setDateTo(to.toISOString().slice(0, 10));
  }, []);

  return (
    <div className="bg-gray-100 min-h-[60vh]">
      {/* 프린터 필터 + 날짜 필터 */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div className="flex space-x-1 overflow-x-auto scrollbar-hide">
              <button
                onClick={() => setPrinterFilter('all')}
                className={`py-2.5 px-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                  printerFilter === 'all' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                All Printers
              </button>
              {printers.map((p) => (
                <button
                  key={p.serial}
                  onClick={() => setPrinterFilter(p.serial)}
                  className={`py-2.5 px-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                    printerFilter === p.serial ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {p.name}
                </button>
              ))}
            </div>

            {/* 날짜 필터 */}
            <div className="flex items-center gap-2 flex-shrink-0 ml-4">
              <div className="flex items-center gap-1.5 bg-gray-50 border rounded-lg px-2.5 py-1.5">
                <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="bg-transparent text-sm focus:outline-none w-28"
                />
                <span className="text-gray-400 text-xs">-</span>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="bg-transparent text-sm focus:outline-none w-28"
                />
              </div>
              <button onClick={() => setQuickDateRange(1)} className="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors">
                1D
              </button>
              <button onClick={() => setQuickDateRange(7)} className="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors">
                1W
              </button>
              <button onClick={() => setQuickDateRange(30)} className="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors">
                1M
              </button>
              <button onClick={() => setQuickDateRange(90)} className="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors">
                3M
              </button>
              {(dateFrom || dateTo) && (
                <button onClick={() => { setDateFrom(''); setDateTo(''); }} className="px-2 py-1.5 text-xs text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                  ✕
                </button>
              )}
              <button
                onClick={loadData}
                disabled={isLoading}
                className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
              >
                <svg className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {isLoading ? (
          <div className="text-center py-16">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-3 text-gray-500 text-sm">통계를 불러오는 중...</p>
          </div>
        ) : !stats ? (
          <div className="text-center py-16 bg-white rounded-xl border">
            <p className="text-gray-500">통계 데이터를 불러올 수 없습니다</p>
          </div>
        ) : (
          <div className="space-y-8">
            {/* ============================================ */}
            {/* Material Usage */}
            {/* ============================================ */}
            <section>
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Material Usage</h2>
              <div className="bg-white rounded-xl border p-8">
                {stats.material_usage.length > 0 ? (
                  <div className="flex items-center gap-16">
                    <DonutChart
                      data={stats.material_usage.map((m) => ({ label: m.name, value: m.total_ml }))}
                      total={stats.total_material_ml}
                    />
                    {/* Material Table */}
                    <div className="flex-1">
                      <table className="w-full">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left text-sm font-semibold text-gray-500 pb-3">Material</th>
                            <th className="text-right text-sm font-semibold text-gray-500 pb-3">Material Used</th>
                          </tr>
                        </thead>
                        <tbody>
                          {stats.material_usage.map((m, i) => (
                            <tr key={m.code} className="border-b border-gray-50">
                              <td className="py-3">
                                <div className="flex items-center gap-3">
                                  <div
                                    className="w-4 h-4 rounded-full border-2"
                                    style={{ borderColor: CHART_COLORS[i % CHART_COLORS.length], backgroundColor: `${CHART_COLORS[i % CHART_COLORS.length]}30` }}
                                  />
                                  <span className="text-sm text-gray-800 font-medium">{m.name}</span>
                                </div>
                              </td>
                              <td className="py-3 text-right text-sm font-semibold text-gray-900">
                                {formatNumber(m.total_ml)} mL
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <p className="text-gray-400 text-sm text-center py-12">데이터 없음</p>
                )}
              </div>
            </section>

            {/* ============================================ */}
            {/* Prints Over Time */}
            {/* ============================================ */}
            <section>
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Prints Over Time</h2>
              <div className="bg-white rounded-xl border p-8">
                {stats.prints_over_time.length > 0 ? (
                  <BarChart data={stats.prints_over_time} />
                ) : (
                  <p className="text-gray-400 text-sm text-center py-12">데이터 없음</p>
                )}
              </div>
            </section>

            {/* ============================================ */}
            {/* Printer Stats Table */}
            {/* ============================================ */}
            <section>
              {stats.printer_stats.length > 0 && (
                <div className="bg-white rounded-xl border overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b bg-gray-50/50">
                        <th className="px-6 py-4 text-left text-sm font-semibold text-gray-500">Printer Name</th>
                        <th className="px-6 py-4 text-center text-sm font-semibold text-gray-500">Hours Printing</th>
                        <th className="px-6 py-4 text-center text-sm font-semibold text-gray-500">Utilization</th>
                        <th className="px-6 py-4 text-center text-sm font-semibold text-gray-500">Days Printed</th>
                        <th className="px-6 py-4 text-center text-sm font-semibold text-gray-500">Prints Completed</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {stats.printer_stats.map((ps, idx) => (
                        <tr key={ps.serial} className="hover:bg-gray-50/50">
                          <td className="px-6 py-5">
                            <div className="flex items-center gap-3">
                              <div
                                className="w-4 h-4 rounded-sm flex-shrink-0"
                                style={{ backgroundColor: PRINTER_COLORS[idx % PRINTER_COLORS.length] }}
                              />
                              <span className="text-sm font-medium text-gray-900">{ps.name}</span>
                            </div>
                          </td>
                          <td className="px-6 py-5 text-center text-sm text-gray-600">
                            {formatHoursMinutes(Math.max(ps.total_duration_minutes, 0))}
                          </td>
                          <td className="px-6 py-5 text-center text-sm text-gray-600">
                            {Math.max(ps.utilization_percent, 0)}%
                          </td>
                          <td className="px-6 py-5 text-center">
                            <span className="text-xl font-bold text-blue-600">{ps.days_printed}</span>
                            <span className="text-sm text-gray-400">/{ps.total_days}</span>
                          </td>
                          <td className="px-6 py-5 text-center">
                            <span className="text-xl font-bold text-blue-600">{ps.completed}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

// ===========================================
// 차트 색상
// ===========================================

const CHART_COLORS = ['#94a3b8', '#cbd5e1', '#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4', '#8b5cf6'];
const PRINTER_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#06b6d4'];

// ===========================================
// Donut Chart
// ===========================================

function DonutChart({ data, total }: { data: { label: string; value: number }[]; total: number }) {
  const size = 220;
  const strokeWidth = 32;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  let offset = 0;
  const segments = data.map((d, i) => {
    const pct = total > 0 ? d.value / total : 0;
    const dashLength = pct * circumference;
    const seg = {
      color: CHART_COLORS[i % CHART_COLORS.length],
      dasharray: `${dashLength} ${circumference - dashLength}`,
      offset: -offset,
    };
    offset += dashLength;
    return seg;
  });

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* 배경 원 */}
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e5e7eb" strokeWidth={strokeWidth} />
        {/* 데이터 세그먼트 */}
        {segments.map((seg, i) => (
          <circle
            key={i}
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={seg.color}
            strokeWidth={strokeWidth}
            strokeDasharray={seg.dasharray}
            strokeDashoffset={seg.offset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            strokeLinecap="butt"
          />
        ))}
      </svg>
      {/* 중앙 텍스트 */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold text-gray-900">{formatNumber(total)} mL</span>
        <span className="text-xs text-gray-500 mt-0.5">Total Material Used</span>
      </div>
    </div>
  );
}

// ===========================================
// Bar Chart (SVG 기반, Y축 + 그리드라인)
// ===========================================

function BarChart({ data }: { data: { date: string; count: number }[] }) {
  const displayData = data.length > 60 ? data.slice(-60) : data;
  const maxCount = Math.max(...displayData.map((d) => d.count), 1);

  // Y축 눈금 계산 (깔끔한 단위)
  const yStep = maxCount <= 5 ? 1 : maxCount <= 10 ? 2 : maxCount <= 25 ? 5 : 10;
  const yMax = Math.ceil(maxCount / yStep) * yStep;
  const yTicks: number[] = [];
  for (let i = 0; i <= yMax; i += yStep) yTicks.push(i);

  // X축 라벨 (5개 균등 배분)
  const xLabelCount = Math.min(5, displayData.length);
  const xLabelIndices: number[] = [];
  if (displayData.length > 0) {
    for (let i = 0; i < xLabelCount; i++) {
      xLabelIndices.push(Math.round((i / Math.max(xLabelCount - 1, 1)) * (displayData.length - 1)));
    }
  }

  // 차트 영역 치수
  const chartWidth = 900;
  const chartHeight = 240;
  const marginLeft = 36;
  const marginRight = 10;
  const marginTop = 10;
  const marginBottom = 30;
  const plotW = chartWidth - marginLeft - marginRight;
  const plotH = chartHeight - marginTop - marginBottom;

  const barWidth = Math.max(Math.min(plotW / displayData.length * 0.6, 20), 3);
  const barGap = plotW / displayData.length;

  return (
    <svg
      viewBox={`0 0 ${chartWidth} ${chartHeight}`}
      className="w-full"
      style={{ maxHeight: 280 }}
    >
      {/* 수평 그리드라인 + Y축 라벨 */}
      {yTicks.map((tick) => {
        const y = marginTop + plotH - (tick / yMax) * plotH;
        return (
          <g key={tick}>
            <line
              x1={marginLeft}
              y1={y}
              x2={chartWidth - marginRight}
              y2={y}
              stroke="#e5e7eb"
              strokeWidth={1}
            />
            <text
              x={marginLeft - 8}
              y={y + 4}
              textAnchor="end"
              className="fill-gray-400"
              fontSize={11}
            >
              {tick}
            </text>
          </g>
        );
      })}

      {/* 바 */}
      {displayData.map((d, i) => {
        const barH = yMax > 0 ? (d.count / yMax) * plotH : 0;
        const x = marginLeft + i * barGap + (barGap - barWidth) / 2;
        const y = marginTop + plotH - barH;
        return (
          <g key={d.date}>
            <rect
              x={x}
              y={y}
              width={barWidth}
              height={Math.max(barH, 0)}
              fill="#3b82f6"
              rx={1}
            >
              <title>{d.date.slice(5)}: {d.count}건</title>
            </rect>
          </g>
        );
      })}

      {/* X축 라벨 */}
      {xLabelIndices.map((idx) => {
        const x = marginLeft + idx * barGap + barGap / 2;
        return (
          <text
            key={idx}
            x={x}
            y={chartHeight - 6}
            textAnchor="middle"
            className="fill-gray-400"
            fontSize={11}
          >
            {displayData[idx].date.slice(5)}
          </text>
        );
      })}
    </svg>
  );
}

// ===========================================
// 유틸
// ===========================================

function formatHoursMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return `${h}h ${String(m).padStart(2, '0')}m`;
}
