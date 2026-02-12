import { useState } from 'react';
import { Dashboard } from './components';
import { PrintPage } from './components/PrintPage';
import { QueuePage } from './components/QueuePage';
import { HistoryPage } from './components/HistoryPage';
import './App.css';

type TabType = 'monitoring' | 'print' | 'queue' | 'history';

interface TabConfig {
  key: TabType;
  label: string;
}

const TABS: TabConfig[] = [
  { key: 'monitoring', label: '모니터링' },
  { key: 'print', label: '프린트 제어' },
  { key: 'queue', label: '대기 중인 작업' },
  { key: 'history', label: '이전 작업 내용' },
];

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('monitoring');

  const renderContent = () => {
    switch (activeTab) {
      case 'monitoring':
        return <Dashboard />;
      case 'print':
        return <PrintPage />;
      case 'queue':
        return <QueuePage />;
      case 'history':
        return <HistoryPage />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* 헤더 */}
      <header className="bg-white border-b shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <h1 className="text-lg font-bold text-gray-900">
              3D 프린터 자동화 시스템
            </h1>
            <span className="text-xs text-gray-400 hidden sm:block">
              Formlabs Form 4
            </span>
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
                onClick={() => setActiveTab(tab.key)}
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
    </div>
  );
}

export default App;
