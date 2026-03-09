import ResultCard from "./ResultCard";
import type { SearchResultItem } from "../../types";

interface Props {
  results: SearchResultItem[];
}

export default function ResultsGrid({ results }: Props) {
  if (results.length === 0) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
      {results.map((r) => (
        <ResultCard key={r.id} item={r} />
      ))}
    </div>
  );
}
