import axios from "axios";
import type { AppConfig, UploadResponse, SearchResponse, FacetValue, DocumentListResponse, DeleteResponse } from "../types";

const api = axios.create({ baseURL: "/api" });

/* ── Config ── */

export async function getAppConfig(): Promise<AppConfig> {
  const { data } = await api.get<AppConfig>("/config");
  return data;
}

/* ── Upload ── */

export async function uploadImages(files: File[]): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  const { data } = await api.post<UploadResponse>("/upload", formData);
  return data;
}

/* ── Search ── */

export async function searchImages(params: {
  textQuery?: string;
  imageFile?: File;
  strategy: string;
  filters?: Record<string, string[]>;
  page: number;
  pageSize: number;
}): Promise<SearchResponse> {
  const formData = new FormData();
  if (params.textQuery) formData.append("text_query", params.textQuery);
  formData.append("strategy", params.strategy);
  if (params.filters) formData.append("filters", JSON.stringify(params.filters));
  formData.append("page", String(params.page));
  formData.append("page_size", String(params.pageSize));
  if (params.imageFile) formData.append("image_file", params.imageFile);
  const { data } = await api.post<SearchResponse>("/search", formData);
  return data;
}

export async function getFacets(): Promise<Record<string, FacetValue[]>> {
  const { data } = await api.get<Record<string, FacetValue[]>>("/facets");
  return data;
}

/* ── Document management ── */

export async function listDocuments(page = 1, pageSize = 50): Promise<DocumentListResponse> {
  const { data } = await api.get<DocumentListResponse>("/documents", {
    params: { page, page_size: pageSize },
  });
  return data;
}

export async function deleteDocument(id: string): Promise<DeleteResponse> {
  const { data } = await api.delete<DeleteResponse>(`/documents/${id}`);
  return data;
}

export async function deleteAllDocuments(): Promise<DeleteResponse> {
  const { data } = await api.delete<DeleteResponse>("/documents");
  return data;
}
