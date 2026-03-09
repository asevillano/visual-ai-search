import { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import TextSearchBar from "./TextSearchBar";
import ImageSearchInput from "./ImageSearchInput";
import StrategySelector from "./StrategySelector";
import ResultsGrid from "./ResultsGrid";
import CompareView from "./CompareView";
import FacetPanel from "./FacetPanel";
import Pagination from "./Pagination";
import Spinner from "../common/Spinner";
import { searchImages, getAppConfig } from "../../services/api";
import type { Strategy, SearchStrategyConfig, PageSize, SearchResponse, FacetValue } from "../../types";

export default function SearchTab() {
  const { t } = useTranslation();

  const [strategyConfig, setStrategyConfig] = useState<SearchStrategyConfig>("all");
  const [textQuery, setTextQuery] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [strategy, setStrategy] = useState<Strategy>("vision");
  const [filters, setFilters] = useState<Record<string, string[]>>({});

  // Fetch backend config once on mount
  useEffect(() => {
    getAppConfig()
      .then((cfg) => {
        setStrategyConfig(cfg.search_strategy);
        if (cfg.search_strategy !== "all") {
          setStrategy(cfg.search_strategy as Strategy);
        }
      })
      .catch(() => { /* keep default "all" */ });
  }, []);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(20);
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const doSearch = useCallback(
    async (p = page) => {
      if (!textQuery && !imageFile) return;
      setLoading(true);
      setError(null);
      try {
        const resp = await searchImages({
          textQuery: textQuery || undefined,
          imageFile: imageFile || undefined,
          strategy,
          filters: Object.keys(filters).length > 0 ? filters : undefined,
          page: p,
          pageSize,
        });
        setResponse(resp);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Search failed");
      } finally {
        setLoading(false);
      }
    },
    [textQuery, imageFile, strategy, filters, page, pageSize]
  );

  const handleSearch = () => {
    setPage(1);
    doSearch(1);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    doSearch(newPage);
  };

  const handlePageSizeChange = (size: PageSize) => {
    setPageSize(size);
    setPage(1);
    doSearch(1);
  };

  const handleFilterChange = (facetName: string, values: string[]) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (values.length === 0) {
        delete next[facetName];
      } else {
        next[facetName] = values;
      }
      return next;
    });
  };

  const clearFilters = () => setFilters({});

  // Get facets from the first available result set
  const activeFacets: Record<string, FacetValue[]> =
    response?.vision?.facets || response?.openai?.facets || {};

  const activeResult = response?.vision || response?.openai;
  const totalCount = activeResult?.total_count || 0;

  return (
    <div className="max-w-7xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">{t("search.title")}</h2>

      {/* Search Controls */}
      <div className="space-y-4 mb-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <TextSearchBar
            value={textQuery}
            onChange={setTextQuery}
            onSearch={handleSearch}
          />
          <ImageSearchInput file={imageFile} onChange={setImageFile} />
        </div>

        <div className="flex flex-wrap items-center gap-4">
          {strategyConfig === "all" && (
            <StrategySelector value={strategy} onChange={setStrategy} />
          )}
          <button
            onClick={handleSearch}
            disabled={loading || (!textQuery && !imageFile)}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <>
                <Spinner className="h-4 w-4" />
                {t("search.searching")}
              </>
            ) : (
              t("search.searchBtn")
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 mb-6">
          {error}
        </div>
      )}

      {/* Results */}
      {response && (
        <div className="flex gap-6">
          {/* Facets Sidebar */}
          <div className="hidden lg:block w-64 flex-shrink-0">
            <FacetPanel
              facets={activeFacets}
              selected={filters}
              onChange={handleFilterChange}
              onClear={clearFilters}
            />
          </div>

          {/* Main content */}
          <div className="flex-1 min-w-0">
            {response.mode === "compare" && response.vision && response.openai ? (
              <CompareView vision={response.vision} openai={response.openai} />
            ) : activeResult ? (
              <>
                <p className="text-sm text-gray-500 mb-4">
                  {t("search.results", { count: totalCount })}
                </p>
                <ResultsGrid results={activeResult.results} />
              </>
            ) : (
              <p className="text-gray-500 text-center py-12">{t("search.noResults")}</p>
            )}

            {/* Pagination */}
            {totalCount > 0 && response.mode !== "compare" && (
              <Pagination
                page={page}
                pageSize={pageSize}
                totalCount={totalCount}
                onPageChange={handlePageChange}
                onPageSizeChange={handlePageSizeChange}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
