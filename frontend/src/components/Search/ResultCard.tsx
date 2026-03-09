import { useState } from "react";
import type { SearchResultItem } from "../../types";
import ImageDetailModal from "../common/ImageDetailModal";

interface Props {
  item: SearchResultItem;
}

export default function ResultCard({ item }: Props) {
  const [showModal, setShowModal] = useState(false);

  const relevanceColor =
    item.relevance >= 80
      ? "bg-green-100 text-green-800"
      : item.relevance >= 50
      ? "bg-yellow-100 text-yellow-800"
      : "bg-gray-100 text-gray-700";

  return (
    <>
      <div
        className="group relative bg-white rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-shadow cursor-pointer"
        onClick={() => setShowModal(true)}
      >
        {/* Thumbnail */}
        <div className="aspect-square overflow-hidden bg-gray-100">
          <img
            src={item.thumbnail_url}
            alt={item.caption || item.file_name}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform"
            loading="lazy"
          />
        </div>

        {/* Relevance badge */}
        <div className="absolute top-2 right-2">
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${relevanceColor}`}>
            {item.relevance.toFixed(1)}%
          </span>
        </div>

        {/* Info */}
        <div className="p-2">
          <p className="text-xs font-medium text-gray-900 truncate">{item.file_name}</p>
          {item.caption && (
            <p className="text-xs text-gray-500 truncate mt-0.5">{item.caption}</p>
          )}
        </div>
      </div>

      {/* Unified detail modal */}
      {showModal && <ImageDetailModal item={item} onClose={() => setShowModal(false)} />}
    </>
  );
}
