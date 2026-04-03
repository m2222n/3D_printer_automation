import { useState, useEffect, useCallback, useRef } from 'react';
import { Dashboard } from './components';
import { PrintPage } from './components/PrintPage';
import { QueuePage } from './components/QueuePage';
import { HistoryPage } from './components/HistoryPage';
import { StatisticsPage } from './components/StatisticsPage';
import { AutomationPage } from './components/AutomationPage';
import { AutomationManualPage } from './components/AutomationManualPage';
import { PrinterInfoModal } from './components/PrinterInfoModal';
import { getNotifications, markNotificationsRead } from './services/localApi';
import type { NotificationEventItem } from './services/localApi';
import './App.css';

type TabType = 'monitoring' | 'print' | 'queue' | 'history' | 'statistics' | 'automation' | 'automation_manual';

interface TabConfig {
  key: TabType;
  label: string;
}

const TABS: TabConfig[] = [
  { key: 'monitoring', label: '모니터링' },
  { key: 'print', label: '프린트 제어' },
  { key: 'queue', label: '대기 중인 작업' },
  { key: 'history', label: '이전 작업 내용' },
  { key: 'statistics', label: '통계' },
  { key: 'automation', label: '자동화' },
  { key: 'automation_manual', label: '자동화 수동제어' },
];

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('monitoring');
  const [tabResetKey, setTabResetKey] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState<NotificationEventItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);

  const [notifError, setNotifError] = useState(false);
  const [modalPrinterSerial, setModalPrinterSerial] = useState<string | null>(null);

  // 알림 로드
  const loadNotifications = useCallback(async () => {
    try {
      const data = await getNotifications(50);
      setNotifications(data.events);
      setUnreadCount(data.unread_count);
      setNotifError(false);
    } catch {
      setNotifError(true);
    }
  }, []);

  // 30초마다 알림 폴링
  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 30000);
    return () => clearInterval(interval);
  }, [loadNotifications]);

  // 패널 외부 클릭 시 닫기
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setShowNotifications(false);
      }
    };
    if (showNotifications) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showNotifications]);

  // 전체 읽음 처리
  const handleMarkAllRead = async () => {
    try {
      const result = await markNotificationsRead();
      setUnreadCount(result.unread_count);
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch { /* ignore */ }
  };

  const openPrinterModal = useCallback((serial: string) => {
    setModalPrinterSerial(serial);
  }, []);

  const renderContent = () => {
    switch (activeTab) {
      case 'monitoring':
        return <Dashboard key={tabResetKey} onOpenPrinterModal={openPrinterModal} />;
      case 'print':
        return <PrintPage key={tabResetKey} onOpenPrinterModal={openPrinterModal} />;
      case 'queue':
        return <QueuePage key={tabResetKey} onOpenPrinterModal={openPrinterModal} />;
      case 'history':
        return <HistoryPage key={tabResetKey} onOpenPrinterModal={openPrinterModal} />;
      case 'statistics':
        return <StatisticsPage key={tabResetKey} />;
      case 'automation':
        return <AutomationPage key={tabResetKey} />;
      case 'automation_manual':
        return <AutomationManualPage key={tabResetKey} />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* 헤더 */}
      <header className="bg-white border-b shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <button
              onClick={() => {
                setActiveTab('monitoring');
                setTabResetKey((k) => k + 1);
              }}
              className="text-lg font-bold text-gray-900 hover:text-blue-600 transition-colors"
            >
              3D 프린터 자동화 시스템
            </button>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-400 hidden sm:block">
                Formlabs Form 4
              </span>

              {/* 알림 벨 아이콘 */}
              <div className="relative" ref={panelRef}>
                <button
                  onClick={() => { setShowNotifications(!showNotifications); if (!showNotifications) loadNotifications(); }}
                  className="relative p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                  </svg>
                  {notifError ? (
                    <span className="absolute -top-0.5 -right-0.5 w-5 h-5 bg-orange-400 text-white text-[10px] font-bold rounded-full flex items-center justify-center" title="알림 서버 연결 실패">
                      !
                    </span>
                  ) : unreadCount > 0 ? (
                    <span className="absolute -top-0.5 -right-0.5 w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                      {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                  ) : null}
                </button>

                {/* 알림 패널 */}
                {showNotifications && (
                  <div className="absolute right-0 top-full mt-2 w-96 bg-white rounded-xl shadow-xl border z-50 max-h-[70vh] flex flex-col">
                    <div className="px-4 py-3 border-b flex items-center justify-between flex-shrink-0">
                      <h3 className="font-semibold text-gray-900 text-sm">알림</h3>
                      {unreadCount > 0 && (
                        <button
                          onClick={handleMarkAllRead}
                          className="text-xs text-blue-600 hover:text-blue-700 font-medium"
                        >
                          모두 읽음
                        </button>
                      )}
                    </div>

                    <div className="overflow-y-auto flex-1">
                      {notifications.length === 0 ? (
                        <div className="py-12 text-center text-gray-400 text-sm">
                          알림이 없습니다
                        </div>
                      ) : (
                        <div className="divide-y divide-gray-50">
                          {notifications.map((n) => (
                            <NotificationItem key={n.id} item={n} />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* 탭 네비게이션 */}
      <nav className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-1 sm:space-x-6 overflow-x-auto scrollbar-hide">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => {
                  if (activeTab === tab.key) {
                    // 같은 탭 재클릭 → 컴포넌트 리셋 (전체 뷰로 돌아가기)
                    setTabResetKey((k) => k + 1);
                  } else {
                    setActiveTab(tab.key);
                  }
                }}
                className={`py-3 px-2 sm:px-1 border-b-2 font-medium text-sm whitespace-nowrap transition-colors ${
                  activeTab === tab.key
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* 탭 컨텐츠 */}
      {renderContent()}

      {/* 프린터 상세 모달 (글로벌) */}
      {modalPrinterSerial && (
        <PrinterInfoModal
          serial={modalPrinterSerial}
          onClose={() => setModalPrinterSerial(null)}
        />
      )}
    </div>
  );
}

// 알림 아이템
function NotificationItem({ item }: { item: NotificationEventItem }) {
  const getIcon = (type: string) => {
    switch (type) {
      case 'PRINT_COMPLETE': return { icon: '✓', color: 'text-green-500 bg-green-50' };
      case 'PRINT_ERROR': return { icon: '!', color: 'text-red-500 bg-red-50' };
      case 'LOW_RESIN': return { icon: '▼', color: 'text-yellow-500 bg-yellow-50' };
      case 'PRINTER_OFFLINE': return { icon: '○', color: 'text-gray-500 bg-gray-50' };
      default: return { icon: '•', color: 'text-blue-500 bg-blue-50' };
    }
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case 'PRINT_COMPLETE': return '출력 완료';
      case 'PRINT_ERROR': return '출력 오류';
      case 'LOW_RESIN': return '레진 부족';
      case 'PRINTER_OFFLINE': return '프린터 오프라인';
      case 'PRINT_STARTED': return '출력 시작';
      default: return type;
    }
  };

  const timeAgo = (dateStr: string | null) => {
    if (!dateStr) return '';
    const diff = Date.now() - new Date(dateStr).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return '방금';
    if (minutes < 60) return `${minutes}분 전`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}시간 전`;
    const days = Math.floor(hours / 24);
    return `${days}일 전`;
  };

  const { icon, color } = getIcon(item.event_type);

  return (
    <div className={`px-4 py-3 hover:bg-gray-50 transition-colors ${!item.is_read ? 'bg-blue-50/30' : ''}`}>
      <div className="flex gap-3">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold ${color}`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-900">
            {item.job_name ? (
              <><span className="font-medium">{item.job_name}</span> {getTypeLabel(item.event_type).toLowerCase()}</>
            ) : (
              <span className="font-medium">{getTypeLabel(item.event_type)}</span>
            )}
            {item.printer_name && (
              <span className="text-gray-500"> on {item.printer_name}</span>
            )}
          </p>
          {item.message && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">{item.message}</p>
          )}
          <p className="text-xs text-gray-400 mt-0.5">{timeAgo(item.created_at)}</p>
        </div>
        {!item.is_read && (
          <div className="w-2 h-2 bg-blue-500 rounded-full flex-shrink-0 mt-2" />
        )}
      </div>
    </div>
  );
}

export default App;
