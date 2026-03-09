import { useTranslation } from "react-i18next";
import FacetGroup from "./FacetGroup";
import type { FacetValue } from "../../types";

interface Props {
  facets: Record<string, FacetValue[]>;
  selected: Record<string, string[]>;
  onChange: (facetName: string, values: string[]) => void;
  onClear: () => void;
}

const FACET_LABEL_KEYS: Record<string, string> = {
  tags: "facets.tags",
  objects: "facets.objects",
  contentType: "facets.contentType",
};

export default function FacetPanel({ facets, selected, onChange, onClear }: Props) {
  const { t } = useTranslation();

  const hasFilters = Object.values(selected).some((v) => v.length > 0);

  return (
    <aside className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">{t("facets.title")}</h3>
        {hasFilters && (
          <button onClick={onClear} className="text-xs text-blue-600 hover:underline">
            {t("facets.clearAll")}
          </button>
        )}
      </div>

      {Object.entries(facets).map(([name, values]) => {
        if (values.length === 0) return null;
        return (
          <FacetGroup
            key={name}
            label={t(FACET_LABEL_KEYS[name] || name)}
            values={values}
            selected={selected[name] || []}
            onChange={(vals) => onChange(name, vals)}
          />
        );
      })}
    </aside>
  );
}
