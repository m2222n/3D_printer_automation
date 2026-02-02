/**
 * 파일 업로드 컴포넌트
 * STL 파일 드래그앤드롭 또는 클릭 업로드
 */

import { useState, useCallback, useRef } from 'react';
import { uploadFile, getFiles, deleteFile } from '../services/localApi';
import type { UploadedFile } from '../types/local';
import { formatFileSize } from '../types/local';

interface FileUploadProps {
  onFileSelect?: (filename: string) => void;
}

export function FileUpload({ onFileSelect }: FileUploadProps) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 파일 목록 로드
  const loadFiles = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getFiles();
      setFiles(response.files);
    } catch (err) {
      setError(err instanceof Error ? err.message : '파일 목록 조회 실패');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 파일 업로드
  const handleUpload = useCallback(async (file: File) => {
    // 확장자 확인
    const ext = file.name.toLowerCase().split('.').pop();
    if (!['stl', 'obj', 'form'].includes(ext || '')) {
      setError('지원하지 않는 파일 형식입니다. (STL, OBJ, FORM만 가능)');
      return;
    }

    // 크기 확인 (100MB)
    if (file.size > 100 * 1024 * 1024) {
      setError('파일 크기가 너무 큽니다. (최대 100MB)');
      return;
    }

    setIsUploading(true);
    setError(null);
    try {
      await uploadFile(file);
      await loadFiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : '업로드 실패');
    } finally {
      setIsUploading(false);
    }
  }, [loadFiles]);

  // 파일 삭제
  const handleDelete = useCallback(async (filename: string) => {
    if (!confirm(`"${filename}" 파일을 삭제하시겠습니까?`)) return;

    try {
      await deleteFile(filename);
      await loadFiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : '삭제 실패');
    }
  }, [loadFiles]);

  // 드래그 앤 드롭
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      handleUpload(file);
    }
  }, [handleUpload]);

  // 파일 선택
  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleUpload(file);
    }
  }, [handleUpload]);

  // 컴포넌트 마운트 시 파일 목록 로드
  useState(() => {
    loadFiles();
  });

  return (
    <div className="bg-white rounded-xl border shadow-sm p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">STL 파일 업로드</h2>

      {/* 업로드 영역 */}
      <div
        className={`
          border-2 border-dashed rounded-lg p-8 text-center cursor-pointer
          transition-colors duration-200
          ${isDragOver ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'}
          ${isUploading ? 'opacity-50 cursor-not-allowed' : ''}
        `}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".stl,.obj,.form"
          onChange={handleFileChange}
          className="hidden"
          disabled={isUploading}
        />

        {isUploading ? (
          <div className="flex flex-col items-center">
            <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-2" />
            <p className="text-gray-600">업로드 중...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center">
            <svg
              className="w-12 h-12 text-gray-400 mb-3"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <p className="text-gray-600 mb-1">
              파일을 드래그하거나 클릭하여 업로드
            </p>
            <p className="text-sm text-gray-400">
              STL, OBJ, FORM (최대 100MB)
            </p>
          </div>
        )}
      </div>

      {/* 에러 메시지 */}
      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* 파일 목록 */}
      <div className="mt-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-gray-700">업로드된 파일</h3>
          <button
            onClick={loadFiles}
            disabled={isLoading}
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            새로고침
          </button>
        </div>

        {isLoading ? (
          <div className="text-center py-4 text-gray-500">로딩 중...</div>
        ) : files.length === 0 ? (
          <div className="text-center py-4 text-gray-400">
            업로드된 파일이 없습니다
          </div>
        ) : (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {files.map((file) => (
              <div
                key={file.filename}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
              >
                <div
                  className="flex-1 cursor-pointer"
                  onClick={() => onFileSelect?.(file.filename)}
                >
                  <p className="text-sm font-medium text-gray-800 truncate">
                    {file.filename}
                  </p>
                  <p className="text-xs text-gray-500">
                    {formatFileSize(file.size_bytes)}
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(file.filename);
                  }}
                  className="ml-2 p-1 text-gray-400 hover:text-red-500 transition-colors"
                  title="삭제"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
