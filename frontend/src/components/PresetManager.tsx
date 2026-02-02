/**
 * 프리셋 관리 컴포넌트
 * 부품별 프린트 설정 저장/관리
 */

import { useState, useEffect, useCallback } from 'react';
import { getPresets, createPreset, deletePreset } from '../services/localApi';
import type { Preset, PresetCreate, MaterialCode } from '../types/local';
import { MATERIAL_NAMES } from '../types/local';

interface PresetManagerProps {
  onPresetSelect?: (preset: Preset) => void;
  selectedFile?: string;
}

export function PresetManager({ onPresetSelect, selectedFile }: PresetManagerProps) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);

  // 새 프리셋 폼 상태
  const [newPreset, setNewPreset] = useState<PresetCreate>({
    name: '',
    part_type: '',
    description: '',
    settings: {
      machine_type: 'FORM-4-0',
      material_code: 'FLGPGR05',
      layer_thickness_mm: 0.05,
      orientation: { x_rotation: 0, y_rotation: 0, z_rotation: 0 },
      support: { density: 'normal', touchpoint_size: 0.5, internal_supports: false },
    },
    stl_filename: selectedFile || '',
  });

  // 프리셋 목록 로드
  const loadPresets = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getPresets();
      setPresets(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : '프리셋 목록 조회 실패');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 프리셋 생성
  const handleCreate = useCallback(async () => {
    if (!newPreset.name.trim() || !newPreset.part_type.trim()) {
      setError('이름과 부품 타입을 입력해주세요.');
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      await createPreset({
        ...newPreset,
        stl_filename: selectedFile || newPreset.stl_filename,
      });
      await loadPresets();
      setShowCreateForm(false);
      setNewPreset({
        name: '',
        part_type: '',
        description: '',
        settings: {
          machine_type: 'FORM-4-0',
          material_code: 'FLGPGR05',
          layer_thickness_mm: 0.05,
          orientation: { x_rotation: 0, y_rotation: 0, z_rotation: 0 },
          support: { density: 'normal', touchpoint_size: 0.5, internal_supports: false },
        },
        stl_filename: '',
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '프리셋 생성 실패');
    } finally {
      setIsLoading(false);
    }
  }, [newPreset, selectedFile, loadPresets]);

  // 프리셋 삭제
  const handleDelete = useCallback(async (preset: Preset) => {
    if (!confirm(`"${preset.name}" 프리셋을 삭제하시겠습니까?`)) return;

    try {
      await deletePreset(preset.id);
      await loadPresets();
    } catch (err) {
      setError(err instanceof Error ? err.message : '프리셋 삭제 실패');
    }
  }, [loadPresets]);

  // 컴포넌트 마운트 시 로드
  useEffect(() => {
    loadPresets();
  }, [loadPresets]);

  // 선택된 파일 변경 시 폼 업데이트
  useEffect(() => {
    if (selectedFile) {
      setNewPreset(prev => ({ ...prev, stl_filename: selectedFile }));
    }
  }, [selectedFile]);

  return (
    <div className="bg-white rounded-xl border shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">프리셋 관리</h2>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          {showCreateForm ? '취소' : '+ 새 프리셋'}
        </button>
      </div>

      {/* 에러 메시지 */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* 생성 폼 */}
      {showCreateForm && (
        <div className="mb-6 p-4 bg-gray-50 rounded-lg">
          <h3 className="text-sm font-medium text-gray-700 mb-3">새 프리셋 생성</h3>

          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">프리셋 이름 *</label>
              <input
                type="text"
                value={newPreset.name}
                onChange={(e) => setNewPreset(prev => ({ ...prev, name: e.target.value }))}
                placeholder="예: 점자프린터 커버 A"
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-xs text-gray-600 mb-1">부품 타입 *</label>
              <input
                type="text"
                value={newPreset.part_type}
                onChange={(e) => setNewPreset(prev => ({ ...prev, part_type: e.target.value }))}
                placeholder="예: cover_a"
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-xs text-gray-600 mb-1">설명</label>
              <input
                type="text"
                value={newPreset.description || ''}
                onChange={(e) => setNewPreset(prev => ({ ...prev, description: e.target.value }))}
                placeholder="선택사항"
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-600 mb-1">레진</label>
                <select
                  value={newPreset.settings?.material_code || 'FLGPGR05'}
                  onChange={(e) => setNewPreset(prev => ({
                    ...prev,
                    settings: { ...prev.settings!, material_code: e.target.value as MaterialCode }
                  }))}
                  className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  {Object.entries(MATERIAL_NAMES).map(([code, name]) => (
                    <option key={code} value={code}>{name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-600 mb-1">레이어 두께</label>
                <select
                  value={newPreset.settings?.layer_thickness_mm || 0.05}
                  onChange={(e) => setNewPreset(prev => ({
                    ...prev,
                    settings: { ...prev.settings!, layer_thickness_mm: parseFloat(e.target.value) }
                  }))}
                  className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value={0.025}>25 µm (정밀)</option>
                  <option value={0.05}>50 µm (표준)</option>
                  <option value={0.1}>100 µm (고속)</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs text-gray-600 mb-1">서포트 밀도</label>
              <select
                value={newPreset.settings?.support?.density || 'normal'}
                onChange={(e) => setNewPreset(prev => ({
                  ...prev,
                  settings: {
                    ...prev.settings!,
                    support: { ...prev.settings!.support, density: e.target.value as 'light' | 'normal' | 'heavy' }
                  }
                }))}
                className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="light">가벼움</option>
                <option value="normal">보통</option>
                <option value="heavy">촘촘함</option>
              </select>
            </div>

            {selectedFile && (
              <div className="p-2 bg-blue-50 rounded text-sm text-blue-700">
                연결된 파일: {selectedFile}
              </div>
            )}

            <button
              onClick={handleCreate}
              disabled={isLoading}
              className="w-full py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
            >
              {isLoading ? '생성 중...' : '프리셋 생성'}
            </button>
          </div>
        </div>
      )}

      {/* 프리셋 목록 */}
      <div>
        {isLoading && !showCreateForm ? (
          <div className="text-center py-4 text-gray-500">로딩 중...</div>
        ) : presets.length === 0 ? (
          <div className="text-center py-8 text-gray-400">
            <p>저장된 프리셋이 없습니다</p>
            <p className="text-sm mt-1">새 프리셋을 만들어 부품별 설정을 저장하세요</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {presets.map((preset) => (
              <div
                key={preset.id}
                className="p-3 border rounded-lg hover:border-blue-300 hover:bg-blue-50 transition-colors cursor-pointer"
                onClick={() => onPresetSelect?.(preset)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h4 className="font-medium text-gray-800">{preset.name}</h4>
                      <span className="px-2 py-0.5 text-xs bg-gray-200 text-gray-600 rounded">
                        {preset.part_type}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      {MATERIAL_NAMES[preset.settings.material_code as MaterialCode] || preset.settings.material_code}
                      {' • '}
                      {preset.settings.layer_thickness_mm * 1000}µm
                      {preset.stl_filename && ` • ${preset.stl_filename}`}
                    </div>
                    {preset.description && (
                      <p className="mt-1 text-xs text-gray-400">{preset.description}</p>
                    )}
                    <div className="mt-1 text-xs text-gray-400">
                      사용 횟수: {preset.print_count}회
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(preset);
                    }}
                    className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                    title="삭제"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
