import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useDropzone } from "react-dropzone";
import { ImageIcon, X } from "lucide-react";

interface Props {
  file: File | null;
  onChange: (f: File | null) => void;
}

export default function ImageSearchInput({ file, onChange }: Props) {
  const { t } = useTranslation();

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length > 0) onChange(accepted[0]);
    },
    [onChange]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "image/*": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"] },
    multiple: false,
  });

  if (file) {
    return (
      <div className="relative flex items-center gap-3 p-2 border border-blue-200 bg-blue-50 rounded-lg">
        <img
          src={URL.createObjectURL(file)}
          alt="search reference"
          className="h-10 w-10 object-cover rounded"
        />
        <span className="text-sm text-gray-700 truncate flex-1">{file.name}</span>
        <button
          onClick={() => onChange(null)}
          className="text-gray-500 hover:text-red-500 p-1"
          title={t("search.clearImage")}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      {...getRootProps()}
      className={`flex items-center gap-3 p-2.5 border border-dashed rounded-lg cursor-pointer transition-colors ${
        isDragActive
          ? "border-blue-500 bg-blue-50"
          : "border-gray-300 hover:border-blue-400"
      }`}
    >
      <input {...getInputProps()} />
      <ImageIcon className="h-5 w-5 text-gray-400 flex-shrink-0" />
      <span className="text-sm text-gray-500">
        {isDragActive ? t("upload.dropzoneActive") : t("search.imagePlaceholder")}
      </span>
    </div>
  );
}
