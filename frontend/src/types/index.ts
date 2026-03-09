/* ── Shared TypeScript interfaces ── */

export type Strategy = "vision" | "openai" | "compare";
export type SearchStrategyConfig = "all" | "vision" | "openai";
export type PageSize = 10 | 20 | 50 | 100;

export interface AppConfig {
  search_strategy: SearchStrategyConfig;
}

export interface UploadResultItem {
  id: string;
  file_name: string;
  thumbnail_url: string;
  original_url: string;
  caption: string;
  tags: string[];
  objects: string[];
}

export interface UploadResponse {
  status: string;
  count: number;
  results: UploadResultItem[];
}

export interface SearchResultItem {
  id: string;
  file_name: string;
  thumbnail_url: string;
  original_url: string;
  caption: string;
  tags: string[];
  objects: string[];
  description?: string;
  relevance: number;
  file_size: number;
  width?: number;
  height?: number;
  upload_date?: string;
  content_type?: string;
}

export interface FacetValue {
  value: string;
  count: number;
}

export interface SearchResultSet {
  strategy: string;
  total_count: number;
  results: SearchResultItem[];
  facets: Record<string, FacetValue[]>;
}

export interface SearchResponse {
  mode: "single" | "compare";
  vision?: SearchResultSet;
  openai?: SearchResultSet;
}

/* ── Document Management ── */

export interface DocumentItem {
  id: string;
  file_name: string;
  thumbnail_url: string;
  original_url: string;
  caption: string;
  tags: string[];
  objects: string[];
  description?: string;
  file_size: number;
  width?: number;
  height?: number;
  upload_date?: string;
  content_type?: string;
}

export interface DocumentListResponse {
  total_count: number;
  documents: DocumentItem[];
}

export interface DeleteResponse {
  deleted: number;
  ids: string[];
}
