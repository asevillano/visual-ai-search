import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { FacetValue } from "../../types";

interface Props {
  label: string;
  values: FacetValue[];
  selected: string[];
  onChange: (values: string[]) => void;
}

export default function FacetGroup({ label, values, selected, onChange }: Props) {
  const [open, setOpen] = useState(true);

  const toggle = (val: string) => {
    if (selected.includes(val)) {
      onChange(selected.filter((v) => v !== val));
    } else {
      onChange([...selected, val]);
    }
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 text-sm font-medium text-gray-700 hover:bg-gray-100"
      >
        <span>{label}</span>
        {open ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
      </button>

      {open && (
        <div className="px-3 py-2 space-y-1 max-h-48 overflow-y-auto">
          {[...values].sort((a, b) => a.value.localeCompare(b.value)).map((fv) => (
            <label
              key={fv.value}
              className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-50 rounded px-1 py-0.5"
            >
              <input
                type="checkbox"
                checked={selected.includes(fv.value)}
                onChange={() => toggle(fv.value)}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="flex-1 truncate text-gray-700">{fv.value}</span>
              <span className="text-xs text-gray-400">{fv.count}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
