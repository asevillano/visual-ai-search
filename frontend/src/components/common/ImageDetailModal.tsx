import { useTranslation } from "react-i18next";
import { X, Download, Trash2, Calendar, Ruler, HardDrive } from "lucide-react";

/**
 * Unified image detail modal — used by both Gallery (Indexed Images)
 * and Search results.  Optional props control gallery-only features
 * (delete) and search-only features (relevance badge).
 */

export interface ImageDetailItem {
  id: string;
  file_name: string;
  thumbnail_url: string;
  original_url: string;
  caption: string;
  tags: string[];
  objects: string[];
  description?: string;
  file_size: number;
  width?: number;
  height?: number;
  upload_date?: string;
  content_type?: string;
  relevance?: number;
}

interface Props {
  item: ImageDetailItem;
  onClose: () => void;
  /** If provided, the delete button is shown (gallery mode). */
  onDelete?: (id: string) => void;
  deleting?: boolean;
}

export default function ImageDetailModal({ item, onClose, onDelete, deleting }: Props) {
  const { t } = useTranslation();

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (iso?: string) => {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const relevanceColor =
    item.relevance !== undefined
      ? item.relevance >= 80
        ? "bg-green-100 text-green-800"
        : item.relevance >= 50
        ? "bg-yellow-100 text-yellow-800"
        : "bg-gray-100 text-gray-700"
      : "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-xl max-w-5xl w-full max-h-[90vh] overflow-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold text-gray-900 truncate">{item.file_name}</h3>
          <div className="flex items-center gap-2">
            {onDelete && (
              <button
                onClick={() => onDelete(item.id)}
                disabled={deleting}
                className="p-2 hover:bg-red-50 rounded-lg text-red-600 disabled:opacity-40"
                title={t("gallery.deleteOne")}
              >
                <Trash2 className="h-5 w-5" />
              </button>
            )}
            <a
              href={item.original_url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-2 hover:bg-gray-100 rounded-lg"
              title={t("modal.download")}
            >
              <Download className="h-5 w-5 text-gray-600" />
            </a>
            <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg" title={t("modal.close")}>
              <X className="h-5 w-5 text-gray-600" />
            </button>
          </div>
        </div>

        <div className="md:flex">
          {/* Image */}
          <div className="md:w-1/2 flex justify-center bg-gray-100 p-4">
            <img
              src={item.original_url}
              alt={item.caption}
              className="max-h-[50vh] object-contain rounded"
            />
          </div>

          {/* Metadata */}
          <div className="md:w-1/2 p-4 space-y-4 overflow-auto max-h-[60vh]">
            {/* Relevance — search results only */}
            {item.relevance !== undefined && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">{t("search.relevance")}</h4>
                <span className={`text-sm font-bold px-2.5 py-0.5 rounded-full ${relevanceColor}`}>
                  {item.relevance.toFixed(1)}%
                </span>
              </div>
            )}

            {/* Caption */}
            {item.caption && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">{t("gallery.caption")}</h4>
                <p className="text-sm text-gray-800">{item.caption}</p>
              </div>
            )}

            {/* Description (GPT details) */}
            {item.description && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">{t("gallery.description")}</h4>
                <p className="text-sm text-gray-700 whitespace-pre-line">{item.description}</p>
              </div>
            )}

            {/* Tags */}
            {item.tags.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">{t("gallery.tags")}</h4>
                <div className="flex flex-wrap gap-1">
                  {item.tags.map((tag) => (
                    <span key={tag} className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Objects */}
            {item.objects.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">{t("gallery.objects")}</h4>
                <div className="flex flex-wrap gap-1">
                  {item.objects.map((obj) => (
                    <span key={obj} className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                      {obj}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* File info */}
            <div className="border-t pt-3 space-y-2 text-sm text-gray-600">
              {item.upload_date && (
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-gray-400" />
                  <span>{t("gallery.uploadDate")}: {formatDate(item.upload_date)}</span>
                </div>
              )}
              {item.width && item.height && (
                <div className="flex items-center gap-2">
                  <Ruler className="h-4 w-4 text-gray-400" />
                  <span>{t("gallery.dimensions")}: {item.width} × {item.height}</span>
                </div>
              )}
              {item.file_size > 0 && (
                <div className="flex items-center gap-2">
                  <HardDrive className="h-4 w-4 text-gray-400" />
                  <span>{t("gallery.fileSize")}: {formatSize(item.file_size)}</span>
                </div>
              )}
              {item.content_type && (
                <div className="text-xs text-gray-400">
                  {item.content_type}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
