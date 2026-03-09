import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useDropzone } from "react-dropzone";
import { Upload, X, CheckCircle2 } from "lucide-react";
import Spinner from "../common/Spinner";
import { uploadImages } from "../../services/api";
import type { UploadResultItem } from "../../types";

export default function UploadTab() {
  const { t } = useTranslation();
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<UploadResultItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback((accepted: File[]) => {
    setFiles((prev) => [...prev, ...accepted]);
    setResults(null);
    setError(null);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "image/*": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"] },
    multiple: true,
  });

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setError(null);
    setResults(null);
    try {
      const resp = await uploadImages(files);
      setResults(resp.results);
      setFiles([]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">{t("upload.title")}</h2>

      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
          isDragActive
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 hover:border-blue-400 hover:bg-gray-50"
        }`}
      >
        <input {...getInputProps()} />
        <Upload className="mx-auto h-12 w-12 text-gray-400 mb-4" />
        <p className="text-gray-600">
          {isDragActive ? t("upload.dropzoneActive") : t("upload.dropzone")}
        </p>
      </div>

      {/* Selected Files */}
      {files.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-medium text-gray-700">
            {t("upload.selectedFiles")} ({files.length})
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {files.map((file, idx) => (
              <div key={idx} className="relative group">
                <img
                  src={URL.createObjectURL(file)}
                  alt={file.name}
                  className="h-32 w-full object-cover rounded-lg border"
                />
                <button
                  onClick={() => removeFile(idx)}
                  className="absolute top-1 right-1 bg-red-500 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="h-3 w-3" />
                </button>
                <p className="text-xs text-gray-500 mt-1 truncate">{file.name}</p>
              </div>
            ))}
          </div>

          <button
            onClick={handleUpload}
            disabled={uploading}
            className="w-full sm:w-auto px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {uploading ? (
              <>
                <Spinner className="h-5 w-5" />
                {t("upload.uploading")}
              </>
            ) : (
              <>
                <Upload className="h-5 w-5" />
                {t("upload.uploadBtn")}
              </>
            )}
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4">
          {error}
        </div>
      )}

      {/* Success Results */}
      {results && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2 text-green-700 font-medium">
            <CheckCircle2 className="h-5 w-5" />
            {t("upload.success", { count: results.length })}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {results.map((r) => (
              <div key={r.id} className="text-center">
                <img
                  src={r.thumbnail_url}
                  alt={r.file_name}
                  className="h-24 w-full object-cover rounded-lg border"
                />
                <p className="text-xs text-gray-600 mt-1 truncate">{r.file_name}</p>
                <p className="text-xs text-gray-400 italic truncate">{r.caption}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
