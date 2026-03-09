import { useTranslation } from "react-i18next";
import type { Strategy } from "../../types";

interface Props {
  value: Strategy;
  onChange: (s: Strategy) => void;
}

const strategies: Strategy[] = ["vision", "openai", "compare"];

export default function StrategySelector({ value, onChange }: Props) {
  const { t } = useTranslation();

  const labels: Record<Strategy, string> = {
    vision: t("search.strategyVision"),
    openai: t("search.strategyOpenai"),
    compare: t("search.strategyCompare"),
  };

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm font-medium text-gray-600">{t("search.strategy")}:</span>
      <div className="flex bg-gray-100 rounded-lg p-0.5">
        {strategies.map((s) => (
          <button
            key={s}
            onClick={() => onChange(s)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              value === s
                ? "bg-white text-blue-600 shadow-sm"
                : "text-gray-600 hover:text-gray-900"
            }`}
          >
            {labels[s]}
          </button>
        ))}
      </div>
    </div>
  );
}
