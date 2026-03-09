import { useTranslation } from "react-i18next";
import ResultsGrid from "./ResultsGrid";
import type { SearchResultSet } from "../../types";

interface Props {
  vision: SearchResultSet;
  openai: SearchResultSet;
}

export default function CompareView({ vision, openai }: Props) {
  const { t } = useTranslation();

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      {/* Vision column */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h3 className="text-lg font-semibold text-purple-700">
            {t("search.visionResults")}
          </h3>
          <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">
            {vision.total_count} results
          </span>
        </div>
        <ResultsGrid results={vision.results} />
      </div>

      {/* OpenAI column */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h3 className="text-lg font-semibold text-emerald-700">
            {t("search.openaiResults")}
          </h3>
          <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">
            {openai.total_count} results
          </span>
        </div>
        <ResultsGrid results={openai.results} />
      </div>
    </div>
  );
}
