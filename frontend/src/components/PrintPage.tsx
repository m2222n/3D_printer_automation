/**
 * 프린트 제어 페이지
 * STL 업로드, 프리셋 관리, 프린트 작업 시작
 */

import { useState } from 'react';
import { FileUpload } from './FileUpload';
import { PresetManager } from './PresetManager';
import { PrintControl } from './PrintControl';
import type { Preset } from '../types/local';

export function PrintPage() {
  const [selectedFile, setSelectedFile] = useState<string | undefined>();
  const [selectedPreset, setSelectedPreset] = useState<Preset | null>(null);

  const handleFileSelect = (filename: string) => {
    setSelectedFile(filename);
    // 파일 선택 시 프리셋 선택 해제
    setSelectedPreset(null);
  };

  const handlePresetSelect = (preset: Preset) => {
    setSelectedPreset(preset);
    // 프리셋에 STL 파일이 있으면 자동 선택
    if (preset.stl_filename) {
      setSelectedFile(preset.stl_filename);
    }
  };

  return (
    <div className="bg-gray-100">
      {/* 서브 헤더 */}
      <header className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3">
          <h2 className="text-lg font-semibold text-gray-900">
            STL 업로드 및 프린트 작업 관리
          </h2>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 왼쪽: 파일 업로드 & 프리셋 */}
          <div className="lg:col-span-2 space-y-6">
            <FileUpload onFileSelect={handleFileSelect} />
            <PresetManager onPresetSelect={handlePresetSelect} />
          </div>

          {/* 오른쪽: 프린트 제어 */}
          <div className="lg:col-span-1">
            <PrintControl
              selectedPreset={selectedPreset}
              selectedFile={selectedFile}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
