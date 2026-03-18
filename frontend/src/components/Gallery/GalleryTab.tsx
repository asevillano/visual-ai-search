import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2, RefreshCcw, ImageOff } from "lucide-react";
import Spinner from "../common/Spinner";
import ImageDetailModal from "../common/ImageDetailModal";
import DocumentCard from "./DocumentCard";
import Pagination from "../Search/Pagination";
import { listDocuments, deleteDocument, deleteAllDocuments } from "../../services/api";
import type { DocumentItem, PageSize } from "../../types";

const DEFAULT_PAGE_SIZE: PageSize = 20;

export default function GalleryTab() {
  const { t } = useTranslation();
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(DEFAULT_PAGE_SIZE);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);
  const [toast, setToast] = useState("");

  const pageSizeRef = useRef(pageSize);
  pageSizeRef.current = pageSize;

  const fetchDocs = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await listDocuments(p, pageSizeRef.current);
      setDocs(res.documents);
      setTotalCount(res.total_count);
      setPage(p);
    } catch (err) {
      console.error("Failed to load documents", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocs(1);
  }, [fetchDocs]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  };

  const handleDeleteOne = async (id: string) => {
    if (!confirm(t("gallery.confirmDeleteOne"))) return;
    setDeleting(true);
    try {
      await deleteDocument(id);
      showToast(t("gallery.deleted", { count: 1 }));
      // Remove locally + close modal if open
      setDocs((prev) => prev.filter((d) => d.id !== id));
      setTotalCount((prev) => Math.max(0, prev - 1));
      setSelectedDoc(null);
    } catch (err) {
      console.error("Delete failed", err);
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteAll = async () => {
    if (!confirm(t("gallery.confirmDeleteAll", { count: totalCount }))) return;
    setDeleting(true);
    try {
      const res = await deleteAllDocuments();
      showToast(t("gallery.deleted", { count: res.deleted }));
      setDocs([]);
      setTotalCount(0);
      setPage(1);
      setSelectedDoc(null);
    } catch (err) {
      console.error("Delete all failed", err);
    } finally {
      setDeleting(false);
    }
  };

  const handlePageSizeChange = (newSize: PageSize) => {
    setPageSize(newSize);
    pageSizeRef.current = newSize;
    fetchDocs(1);
  };

  return (
    <div className="max-w-7xl mx-auto">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-900">{t("gallery.title")}</h2>
          {!loading && (
            <span className="text-sm text-gray-500">
              {t("gallery.totalImages", { count: totalCount })}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchDocs(page)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <RefreshCcw className="h-4 w-4" />
          </button>
          {totalCount > 0 && (
            <button
              onClick={handleDeleteAll}
              disabled={deleting}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50 transition-colors"
            >
              <Trash2 className="h-4 w-4" />
              {deleting ? t("gallery.deleting") : t("gallery.deleteAll")}
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <Spinner className="h-8 w-8 mb-3" />
          <p>{t("gallery.loading")}</p>
        </div>
      ) : docs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400">
          <ImageOff className="h-16 w-16 mb-4" />
          <p className="text-lg">{t("gallery.empty")}</p>
        </div>
      ) : (
        <>
          {/* Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {docs.map((doc) => (
              <DocumentCard
                key={doc.id}
                item={doc}
                onSelect={setSelectedDoc}
                onDelete={handleDeleteOne}
                deleting={deleting}
              />
            ))}
          </div>

          {/* Pagination */}
          <Pagination
            page={page}
            pageSize={pageSize}
            totalCount={totalCount}
            onPageChange={fetchDocs}
            onPageSizeChange={handlePageSizeChange}
          />
        </>
      )}

      {/* Detail modal */}
      {selectedDoc && (
        <ImageDetailModal
          item={selectedDoc}
          onClose={() => setSelectedDoc(null)}
          onDelete={handleDeleteOne}
          deleting={deleting}
        />
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 bg-gray-900 text-white px-4 py-2 rounded-lg shadow-lg text-sm z-50 animate-fadeIn">
          {toast}
        </div>
      )}
    </div>
  );
}
