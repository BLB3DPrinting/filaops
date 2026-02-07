/**
 * DocumentUploadPanel - Multi-file document management for Purchase Orders
 * 
 * Features:
 * - Drag & drop file upload
 * - Multiple file support
 * - Document type categorization (invoice, receipt, packing slip, etc.)
 * - Google Drive integration (when available)
 * - Preview/download functionality
 */
import React, { useState, useCallback, useRef } from 'react';
import {
  Upload,
  File,
  FileText,
  Image,
  X,
  Download,
  Trash2,
  Loader2,
  Plus,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import api from '../../api/axios';

// Document type options with icons
const DOCUMENT_TYPES = [
  { value: 'invoice', label: 'Invoice', icon: '📄' },
  { value: 'packing_slip', label: 'Packing Slip', icon: '📦' },
  { value: 'receipt', label: 'Receipt', icon: '🧾' },
  { value: 'quote', label: 'Quote', icon: '📋' },
  { value: 'shipping_label', label: 'Shipping Label', icon: '🏷️' },
  { value: 'other', label: 'Other', icon: '📎' },
];

// File type icons
const getFileIcon = (mimeType) => {
  if (mimeType?.startsWith('image/')) return <Image className="w-5 h-5" />;
  if (mimeType === 'application/pdf') return <FileText className="w-5 h-5 text-red-400" />;
  return <File className="w-5 h-5" />;
};

// Format file size
const formatFileSize = (bytes) => {
  if (!bytes) return 'Unknown size';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

// Format date
const formatDate = (dateString) => {
  if (!dateString) return '';
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

export default function DocumentUploadPanel({ poId, onDocumentsChange }) {
  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState({});
  const [error, setError] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedType, setSelectedType] = useState('invoice');
  const fileInputRef = useRef(null);

  // Load documents
  const loadDocuments = useCallback(async () => {
    if (!poId) return;
    
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await api.get(`/purchase-orders/${poId}/documents`);
      setDocuments(response.data || []);
      onDocumentsChange?.(response.data || []);
    } catch (err) {
      console.error('Failed to load documents:', err);
      setError('Failed to load documents');
    } finally {
      setIsLoading(false);
    }
  }, [poId, onDocumentsChange]);

  // Load on mount and when poId changes
  React.useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  // Handle file selection
  const handleFileSelect = async (files) => {
    if (!files || files.length === 0) return;

    setIsUploading(true);
    setError(null);

    const uploadPromises = Array.from(files).map(async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', selectedType);

      try {
        setUploadProgress((prev) => ({ ...prev, [file.name]: 0 }));

        const response = await api.post(`/purchase-orders/${poId}/documents`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: (progressEvent) => {
            const percentCompleted = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            setUploadProgress((prev) => ({ ...prev, [file.name]: percentCompleted }));
          },
        });

        setUploadProgress((prev) => ({ ...prev, [file.name]: 100 }));
        return { success: true, data: response.data, fileName: file.name };
      } catch (err) {
        console.error(`Failed to upload ${file.name}:`, err);
        return {
          success: false,
          fileName: file.name,
          error: err.response?.data?.detail || 'Upload failed',
        };
      }
    });

    try {
      const results = await Promise.all(uploadPromises);

      // Clear progress after a delay
      setTimeout(() => setUploadProgress({}), 2000);

      // Handle results
      const failures = results.filter((r) => !r.success);
      if (failures.length > 0) {
        setError(`Failed to upload: ${failures.map((f) => f.fileName).join(', ')}`);
      }

      // Reload documents
      await loadDocuments();
    } catch (err) {
      console.error("Failed to upload documents:", err);
      setError("Failed to upload one or more documents");
    } finally {
      setUploadProgress({});
      setIsUploading(false);
    }
  };

  // Handle drag events
  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer?.files;
    if (files) {
      handleFileSelect(files);
    }
  };

  // Handle delete
  const handleDelete = async (docId) => {
    if (!confirm('Delete this document?')) return;

    try {
      await api.delete(`/purchase-orders/${poId}/documents/${docId}`);
      await loadDocuments();
    } catch (err) {
      console.error('Failed to delete document:', err);
      setError('Failed to delete document');
    }
  };

  // Handle download
  const handleDownload = (doc) => {
    if (doc.download_url) {
      window.open(doc.download_url, '_blank');
    } else {
      // Fallback to API endpoint
      window.open(`/api/v1/purchase-orders/${poId}/documents/${doc.id}/download`, '_blank');
    }
  };

  // Get type info
  const getTypeInfo = (type) => {
    return DOCUMENT_TYPES.find((t) => t.value === type) || DOCUMENT_TYPES[5]; // Default to 'other'
  };

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">📎</span>
          <h3 className="font-medium text-white">Documents</h3>
          {documents.length > 0 && (
            <span className="text-xs bg-gray-700 px-2 py-0.5 rounded-full text-gray-300">
              {documents.length}
            </span>
          )}
        </div>

        {/* Document type selector + Upload button */}
        <div className="flex items-center gap-2">
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="text-sm bg-gray-700 border border-gray-600 rounded px-2 py-1 text-gray-200"
          >
            {DOCUMENT_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.icon} {type.label}
              </option>
            ))}
          </select>

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-sm font-medium text-white transition-colors"
          >
            {isUploading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            Upload
          </button>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png,.webp,.gif,.xlsx,.xls,.csv,.doc,.docx"
            onChange={(e) => handleFileSelect(e.target.files)}
            className="hidden"
          />
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div className="px-4 py-2 bg-red-900/30 border-b border-red-800 flex items-center gap-2 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
          <button onClick={() => setError(null)} className="ml-auto hover:text-red-300">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Drag & Drop Zone */}
      <div
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={`p-4 transition-colors ${
          isDragging ? 'bg-blue-900/20 border-2 border-dashed border-blue-500' : ''
        }`}
      >
        {/* Upload progress */}
        {Object.keys(uploadProgress).length > 0 && (
          <div className="mb-4 space-y-2">
            {Object.entries(uploadProgress).map(([fileName, progress]) => (
              <div key={fileName} className="flex items-center gap-2">
                <div className="flex-1">
                  <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                    <span className="truncate max-w-[200px]">{fileName}</span>
                    <span>{progress}%</span>
                  </div>
                  <div className="h-1 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all duration-300"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
                {progress === 100 && <CheckCircle2 className="w-4 h-4 text-green-500" />}
              </div>
            ))}
          </div>
        )}

        {/* Documents list */}
        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin mr-2" />
            Loading documents...
          </div>
        ) : documents.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Upload className="w-10 h-10 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No documents attached</p>
            <p className="text-xs mt-1">
              Drag & drop files here or click Upload
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {documents.map((doc) => {
              const typeInfo = getTypeInfo(doc.document_type);
              return (
                <div
                  key={doc.id}
                  className="flex items-center gap-3 p-3 bg-gray-750 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors group"
                >
                  {/* Icon */}
                  <div className="flex-shrink-0 text-gray-400">
                    {getFileIcon(doc.mime_type)}
                  </div>

                  {/* Type badge */}
                  <span className="text-lg flex-shrink-0" title={typeInfo.label}>
                    {typeInfo.icon}
                  </span>

                  {/* File info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-200 truncate">
                      {doc.original_file_name || doc.file_name}
                    </p>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <span>{formatFileSize(doc.file_size)}</span>
                      <span>•</span>
                      <span>{formatDate(doc.uploaded_at)}</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {/* Download */}
                    <button
                      onClick={() => handleDownload(doc)}
                      className="p-1.5 hover:bg-gray-700 rounded text-gray-400 hover:text-green-400"
                      title="Download"
                    >
                      <Download className="w-4 h-4" />
                    </button>

                    {/* Delete */}
                    <button
                      onClick={() => handleDelete(doc.id)}
                      className="p-1.5 hover:bg-gray-700 rounded text-gray-400 hover:text-red-400"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Drag hint when dragging */}
        {isDragging && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-900/80 rounded-lg z-10">
            <div className="text-center">
              <Upload className="w-12 h-12 mx-auto mb-2 text-blue-400" />
              <p className="text-blue-400 font-medium">Drop files here</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
