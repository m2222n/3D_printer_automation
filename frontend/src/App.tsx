import { useState } from 'react';
import { Dashboard } from './components';
import { PrintPage } from './components/PrintPage';
import './App.css';

type TabType = 'monitoring' | 'print';

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('monitoring');

  return (
    <div className="min-h-screen bg-gray-100">
      {/* 탭 네비게이션 */}
      <nav className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8">
            <button
              onClick={() => setActiveTab('monitoring')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'monitoring'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              모니터링
            </button>
            <button
              onClick={() => setActiveTab('print')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'print'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              프린트 제어
            </button>
          </div>
        </div>
      </nav>

      {/* 탭 컨텐츠 */}
      {activeTab === 'monitoring' ? <Dashboard /> : <PrintPage />}
    </div>
  );
}

export default App;
