import { Trash2 } from "lucide-react";
import type { DocumentItem } from "../../types";

interface Props {
  item: DocumentItem;
  onSelect: (item: DocumentItem) => void;
  onDelete: (id: string) => void;
  deleting: boolean;
}

export default function DocumentCard({ item, onSelect, onDelete, deleting }: Props) {
  return (
    <div className="group relative bg-white rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-shadow">
      {/* Thumbnail — click opens detail */}
      <div
        className="aspect-square overflow-hidden bg-gray-100 cursor-pointer"
        onClick={() => onSelect(item)}
      >
        <img
          src={item.thumbnail_url}
          alt={item.caption || item.file_name}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform"
          loading="lazy"
        />
      </div>

      {/* Delete button — top right */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete(item.id);
        }}
        disabled={deleting}
        className="absolute top-2 right-2 p-1.5 bg-white/90 hover:bg-red-50 rounded-full shadow-sm
                   opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-40"
        title="Delete"
      >
        <Trash2 className="h-4 w-4 text-red-500" />
      </button>

      {/* Info */}
      <div className="p-2 cursor-pointer" onClick={() => onSelect(item)}>
        <p className="text-xs font-medium text-gray-900 truncate">{item.file_name}</p>
        {item.caption && (
          <p className="text-xs text-gray-500 truncate mt-0.5">{item.caption}</p>
        )}
        {item.tags.length > 0 && (
          <div className="flex flex-wrap gap-0.5 mt-1">
            {item.tags.slice(0, 4).map((tag) => (
              <span key={tag} className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
                {tag}
              </span>
            ))}
            {item.tags.length > 4 && (
              <span className="text-[10px] text-gray-400">+{item.tags.length - 4}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
