# Visual AI Search — Development Plan

## 1. Overview

A web application with **two tabs**:

| Tab | Purpose |
|-----|---------|
| **Upload & Index** | Upload one or more images → extract metadata & embeddings → index in Azure AI Search |
| **Search** | Text search, visual (image) search, or hybrid — with thumbnails, relevance %, facets, pagination, i18n |

The UI supports **English / Spanish** toggle.

---

## 2. Architecture

```
┌─────────────┐        ┌──────────────────┐       ┌──────────────────────┐
│  Frontend    │  REST  │  Backend (FastAPI)│       │  Azure Services      │
│  (React +   │◄──────►│                  │◄─────►│                      │
│   Tailwind)  │        │  /api/upload      │       │  • Azure Blob Storage│
│              │        │  /api/search      │       │  • Azure AI Vision   │
│              │        │  /api/facets      │       │  • Azure OpenAI      │
│              │        │                  │       │  • Azure AI Search   │
└─────────────┘        └──────────────────┘       └──────────────────────┘
```

### Component Responsibilities

| Component | Technology | Role |
|-----------|-----------|------|
| **Frontend** | React 18 + TypeScript + Tailwind CSS | SPA with two tabs, i18n, pagination, facets, **strategy comparison** |
| **Backend** | Python 3.11 + FastAPI | REST API, orchestrates Azure services |
| **Blob Storage** | Azure Blob Storage | Stores original images + thumbnails |
| **AI Vision** | Azure AI Vision 4.0 (Florence) | Image analysis (tags, captions, objects) + **multimodal embeddings** (1024-d, shared text↔image space) |
| **Azure OpenAI** | text-embedding-3-large | **Text embeddings** (3072-d) for text-semantic search |
| **Search Index** | Azure AI Search | **Multi-vector** index (HNSW), full-text, facets, filters |

### Dual Vectorization Strategy

The application indexes **three vectors per document** and supports **two search strategies** the user can toggle/compare:

| Strategy | Text Query Vector | Image Query Vector | Index Vectors Used | Pros |
|----------|-------------------|--------------------|--------------------|------|
| **Strategy A: AI Vision Multimodal** | AI Vision `vectorize(text)` → 1024-d | AI Vision `vectorize(image)` → 1024-d | `imageVector` (1024-d) | Same embedding space for text & images; native cross-modal search |
| **Strategy B: OpenAI Text + Vision Image** | OpenAI `text-embedding-3-large` → 3072-d | AI Vision `vectorize(image)` → 1024-d | `textVector` (3072-d) for text queries, `imageVector` (1024-d) for image queries | Richer text semantics; best-in-class text embeddings |

> **During indexing**, each image gets: (1) `imageVector` from AI Vision, (2) `textVector` from OpenAI embedding of the caption+tags.  
> **During search**, the user selects Strategy A, B, or **Compare** (side-by-side results).

---

## 3. Azure AI Search — Index Schema (Multi-Vector)

```json
{
  "name": "visual-search-index",
  "fields": [
    { "name": "id",            "type": "Edm.String",  "key": true, "filterable": true },
    { "name": "fileName",      "type": "Edm.String",  "searchable": true, "filterable": true },
    { "name": "description",   "type": "Edm.String",  "searchable": true, "analyzer": "standard.lucene" },
    { "name": "caption",       "type": "Edm.String",  "searchable": true },
    { "name": "tags",          "type": "Collection(Edm.String)", "searchable": true, "filterable": true, "facetable": true },
    { "name": "objects",       "type": "Collection(Edm.String)", "filterable": true, "facetable": true },
    { "name": "fileSize",      "type": "Edm.Int64",   "filterable": true, "facetable": true, "sortable": true },
    { "name": "width",         "type": "Edm.Int32",   "filterable": true, "facetable": true },
    { "name": "height",        "type": "Edm.Int32",   "filterable": true, "facetable": true },
    { "name": "uploadDate",    "type": "Edm.DateTimeOffset", "filterable": true, "facetable": true, "sortable": true },
    { "name": "contentType",   "type": "Edm.String",  "filterable": true, "facetable": true },
    { "name": "thumbnailUrl",  "type": "Edm.String",  "retrievable": true },
    { "name": "originalUrl",   "type": "Edm.String",  "retrievable": true },

    // ── Vector field 1: AI Vision multimodal (images + text in same space) ──
    { "name": "imageVector",   "type": "Collection(Edm.Single)", "searchable": true,
      "dimensions": 1024,
      "vectorSearchProfile": "vision-vector-profile" },

    // ── Vector field 2: Azure OpenAI text-embedding-3-large (text semantics) ──
    { "name": "textVector",    "type": "Collection(Edm.Single)", "searchable": true,
      "dimensions": 3072,
      "vectorSearchProfile": "openai-vector-profile" }
  ],
  "vectorSearch": {
    "algorithms": [
      { "name": "hnsw-vision",  "kind": "hnsw", "hnswParameters": { "m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine" } },
      { "name": "hnsw-openai",  "kind": "hnsw", "hnswParameters": { "m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine" } }
    ],
    "profiles": [
      { "name": "vision-vector-profile", "algorithm": "hnsw-vision",
        "vectorizer": "vision-vectorizer" },
      { "name": "openai-vector-profile", "algorithm": "hnsw-openai",
        "vectorizer": "openai-vectorizer" }
    ],
    "vectorizers": [
      {
        "name": "vision-vectorizer",
        "kind": "aiServicesVision",
        "aiServicesVisionParameters": {
          "resourceUri": "<AI_VISION_ENDPOINT>",
          "modelVersion": "2023-04-15"
        }
      },
      {
        "name": "openai-vectorizer",
        "kind": "azureOpenAI",
        "azureOpenAIParameters": {
          "resourceUri": "<AZURE_OPENAI_ENDPOINT>",
          "deploymentId": "text-embedding-3-large",
          "modelName": "text-embedding-3-large"
        }
      }
    ]
  }
}
```

> **Key point**: The index stores **two independent vector fields** per document:  
> - `imageVector` (1024-d) — from **AI Vision 4.0** multimodal embeddings (shared text↔image space)  
> - `textVector` (3072-d) — from **Azure OpenAI** `text-embedding-3-large` applied to the concatenation of caption + tags  
>  
> This enables comparing **Strategy A** (all AI Vision) vs **Strategy B** (OpenAI text + Vision image) at search time.

---

## 4. Backend API Endpoints

### 4.1 `POST /api/upload`

**Flow:**
1. Receive multipart file(s).
2. For each image:
   a. Upload original to **Blob Storage** (`originals/{uuid}.{ext}`).
   b. Generate thumbnail (256×256 max) → upload to Blob Storage (`thumbnails/{uuid}.jpg`).
   c. Call **Azure AI Vision 4.0** `analyze` → extract `caption`, `tags`, `objects`.
   d. Call **Azure AI Vision 4.0** `vectorize` (image) → get `imageVector` (1024-d).
   e. Build text representation: `"{caption}. Tags: {tags joined by comma}"` → call **Azure OpenAI** `text-embedding-3-large` → get `textVector` (3072-d).
   f. Build document with **both vectors** and **upsert** into Azure AI Search index.
3. Return status + indexed document IDs.

> **Note**: Steps (d) and (e) can run **in parallel** (asyncio.gather) to minimize latency.

### 4.2 `POST /api/search`

**Request body:**
```json
{
  "textQuery": "a dog on the beach",     // optional
  "imageFile": "<base64 or multipart>",  // optional
  "strategy": "vision" | "openai" | "compare",  // default: "vision"
  "filters": {                            // optional facet selections
    "tags": ["dog", "beach"],
    "contentType": ["image/jpeg"]
  },
  "page": 1,
  "pageSize": 20
}
```

**Flow:**
1. Vectorize the query inputs depending on the selected `strategy`:

   | Input | Strategy A (AI Vision Multimodal) | Strategy B (OpenAI Text + Vision Image) |
   |-------|----------------------------------|----------------------------------------|
   | `textQuery` | AI Vision `vectorize(text)` → 1024-d → search against `imageVector` | OpenAI `text-embedding-3-large` → 3072-d → search against `textVector` |
   | `imageFile` | AI Vision `vectorize(image)` → 1024-d → search against `imageVector` | AI Vision `vectorize(image)` → 1024-d → search against `imageVector` |
   | Both | Two vector queries on `imageVector` (text+image), merged via RRF | One query on `textVector` (text) + one on `imageVector` (image), merged via RRF |

2. If `strategy = "compare"` → execute **both strategies in parallel**, return two result sets side-by-side.

3. Build Azure AI Search query:
   - `search` parameter (full-text BM25 on `description`, `caption`, `tags`) if text provided.
   - `vector_queries` with the appropriate vector field(s) per strategy.
   - `filter` from facet selections (OData).
   - `facets`: `["tags,count:20", "objects,count:20", "contentType", "fileSize", "uploadDate,interval:month"]`.
   - `top` = pageSize, `skip` = (page-1) × pageSize.
4. Return results with `@search.score` normalized to relevance %.

> **RRF (Reciprocal Rank Fusion)** is used natively by Azure AI Search when multiple vector queries are combined in a single request.

**Response (single strategy):**
```json
{
  "strategy": "vision",
  "totalCount": 342,
  "results": [
    {
      "id": "...",
      "fileName": "beach_dog.jpg",
      "thumbnailUrl": "https://...",
      "originalUrl": "https://...",
      "caption": "A golden retriever playing on a sandy beach",
      "tags": ["dog", "beach", "sand", "water"],
      "relevance": 94.5,
      "fileSize": 2048000,
      "uploadDate": "2025-12-01T10:30:00Z"
    }
  ],
  "facets": {
    "tags": [{"value": "dog", "count": 45}, {"value": "beach", "count": 30}],
    "objects": [{"value": "animal", "count": 50}],
    "contentType": [{"value": "image/jpeg", "count": 300}]
  }
}
```

**Response (compare mode — returns both strategies):**
```json
{
  "strategy": "compare",
  "vision": {
    "totalCount": 342,
    "results": [ ... ],
    "facets": { ... }
  },
  "openai": {
    "totalCount": 338,
    "results": [ ... ],
    "facets": { ... }
  }
}
```

### 4.3 `GET /api/facets`

Returns available facets from the index (for initial filter panel rendering).

---

## 5. Frontend — React Application

### 5.1 Project Structure

```
frontend/
├── public/
├── src/
│   ├── components/
│   │   ├── Layout/
│   │   │   ├── Header.tsx            # Logo, language toggle (EN/ES), navigation
│   │   │   └── TabNavigation.tsx     # Two tabs
│   │   ├── Upload/
│   │   │   ├── UploadTab.tsx         # Main upload view
│   │   │   ├── DropZone.tsx          # Drag & drop area
│   │   │   ├── FilePreview.tsx       # Preview selected files before upload
│   │   │   └── UploadProgress.tsx    # Progress bar per file
│   │   ├── Search/
│   │   │   ├── SearchTab.tsx         # Main search view
│   │   │   ├── TextSearchBar.tsx     # Free-text input
│   │   │   ├── ImageSearchInput.tsx  # Upload image for visual search
│   │   │   ├── StrategySelector.tsx  # Toggle: Vision / OpenAI / Compare
│   │   │   ├── ResultsGrid.tsx       # Thumbnail grid with relevance
│   │   │   ├── CompareView.tsx       # Side-by-side results for compare mode
│   │   │   ├── ResultCard.tsx        # Single result: thumb + % + filename
│   │   │   ├── FacetPanel.tsx        # Sidebar with facet filters
│   │   │   ├── FacetGroup.tsx        # Single facet group (checkboxes)
│   │   │   ├── Pagination.tsx        # Page controls + page-size selector
│   │   │   └── ImageModal.tsx        # Full-size image viewer on click
│   │   └── common/
│   │       ├── Button.tsx
│   │       ├── Spinner.tsx
│   │       └── LanguageToggle.tsx
│   ├── i18n/
│   │   ├── en.json                   # English strings
│   │   ├── es.json                   # Spanish strings
│   │   └── i18nProvider.tsx          # react-i18next setup
│   ├── hooks/
│   │   ├── useSearch.ts              # Search API hook
│   │   ├── useUpload.ts             # Upload API hook
│   │   └── useFacets.ts             # Facet state management
│   ├── services/
│   │   └── api.ts                    # Axios/fetch wrapper
│   ├── types/
│   │   └── index.ts                  # TypeScript interfaces
│   ├── App.tsx
│   └── main.tsx
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── vite.config.ts
```

### 5.2 Key UI Features

| Feature | Detail |
|---------|--------|
| **Language toggle** | EN 🇬🇧 / ES 🇪🇸 button in header; uses `react-i18next` |
| **Upload drag & drop** | Accepts multiple images; shows preview + progress |
| **Text search** | Full-text input with debounce |
| **Visual search** | Upload/drag reference image |
| **Combined search** | Both inputs active simultaneously |
| **Results grid** | Responsive grid of thumbnails |
| **Result card** | Thumbnail (150×150) + relevance badge (e.g. `94.5%`) + filename |
| **Pagination** | Page selector + dropdown: 10 / 20 / 50 / 100 per page |
| **Facets sidebar** | Collapsible groups: Tags, Objects, Content Type, File Size ranges, Date ranges |
| **Image modal** | Click thumbnail → full-size overlay |

---

## 6. Backend — Python Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, CORS, routers
│   ├── config.py                # Pydantic Settings (env vars)
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── upload.py            # POST /api/upload
│   │   └── search.py            # POST /api/search, GET /api/facets
│   ├── services/
│   │   ├── __init__.py
│   │   ├── blob_storage.py      # Upload/download blobs, generate SAS URLs
│   │   ├── vision.py            # Azure AI Vision: analyze + vectorize (image & text)
│   │   ├── openai_embeddings.py # Azure OpenAI: text-embedding-3-large
│   │   ├── search_index.py      # Create/manage AI Search index (multi-vector)
│   │   └── search.py            # Execute searches (Strategy A / B / Compare)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── upload.py            # Request/response models for upload
│   │   └── search.py            # Request/response models for search (incl. strategy)
│   └── utils/
│       ├── __init__.py
│       ├── thumbnails.py        # PIL-based thumbnail generation
│       └── helpers.py           # ID generation, normalization
├── requirements.txt
├── .env.example
└── Dockerfile
```

---

## 7. Required Azure Resources

| Resource | SKU / Tier | Purpose |
|----------|-----------|---------|
| **Azure AI Search** | Standard S1+ (vector search) | Multi-vector index, full-text + vector search, facets |
| **Azure AI Vision** | S1 (multi-service) | Image analysis (tags, captions, objects) + multimodal embeddings (1024-d) |
| **Azure OpenAI** | Standard | `text-embedding-3-large` deployment (3072-d text embeddings) |
| **Azure Blob Storage** | Standard LRS | Store originals + thumbnails |
| **Azure App Service** (optional) | B1+ | Host backend API |
| **Azure Static Web Apps** (optional) | Free/Standard | Host React frontend |

---

## 8. Environment Variables

```env
# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://<name>.search.windows.net
AZURE_SEARCH_API_KEY=<key>
AZURE_SEARCH_INDEX_NAME=visual-search-index

# Azure AI Vision (image analysis + multimodal embeddings)
AZURE_VISION_ENDPOINT=https://<name>.cognitiveservices.azure.com
AZURE_VISION_API_KEY=<key>

# Azure OpenAI (text embeddings)
AZURE_OPENAI_ENDPOINT=https://<name>.openai.azure.com
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING=<connection-string>
AZURE_STORAGE_CONTAINER_ORIGINALS=originals
AZURE_STORAGE_CONTAINER_THUMBNAILS=thumbnails

# App
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:5173
```

---

## 9. Indexing Pipeline — Detailed Flow

```
User uploads image(s)
        │
        ▼
   ┌─────────────┐
   │ FastAPI      │
   │ /api/upload  │
   └──────┬──────┘
          │
   ┌──────▼──────┐      ┌────────────────────┐
   │ Save to Blob │─────►│ originals/{id}.jpg  │
   │ Storage      │      │ thumbnails/{id}.jpg │
   └──────┬──────┘      └────────────────────┘
          │
   ┌──────▼──────────────┐
   │ Azure AI Vision 4.0  │
   │ POST /analyze        │
   │  → caption, tags,    │
   │    objects, metadata  │
   └──────┬──────────────┘
          │
          ├──────────────────────────────────────────┐
          │ (parallel)                                │
   ┌──────▼──────────────┐         ┌─────────────────▼─────────────┐
   │ Azure AI Vision 4.0  │         │ Azure OpenAI                   │
   │ POST /vectorize      │         │ text-embedding-3-large         │
   │ (image bytes)        │         │ Input: "{caption}. Tags: ..."  │
   │  → imageVector       │         │  → textVector                  │
   │    (1024-d)          │         │    (3072-d)                    │
   └──────┬──────────────┘         └─────────────────┬─────────────┘
          │                                           │
          └────────────────┬──────────────────────────┘
                           │
                    ┌──────▼──────────────┐
                    │ Azure AI Search      │
                    │ Index document with: │
                    │  • text fields       │
                    │  • imageVector       │
                    │  • textVector        │
                    │  • facetable fields  │
                    └─────────────────────┘
```

---

## 10. Search Pipeline — Detailed Flow

```
User enters text / uploads image / both  +  selects Strategy (A / B / Compare)
        │
        ▼
   ┌─────────────────┐
   │ FastAPI          │
   │ POST /api/search │
   └──────┬──────────┘
          │
          │  ┌─────────────── Strategy A (vision) ───────────────┐
          │  │ text? → AI Vision vectorize(text) → 1024-d        │
          │  │ image? → AI Vision vectorize(image) → 1024-d      │
          │  │ → vector_queries against imageVector               │
          │  └───────────────────────────────────────────────────┘
          │
          │  ┌─────────────── Strategy B (openai) ───────────────┐
          │  │ text? → OpenAI embed(text) → 3072-d               │
          │  │ image? → AI Vision vectorize(image) → 1024-d      │
          │  │ → vector_queries against textVector + imageVector  │
          │  └───────────────────────────────────────────────────┘
          │
          │  ┌─────────────── Compare mode ──────────────────────┐
          │  │ Execute BOTH strategies in parallel                │
          │  │ Return two result sets side-by-side                │
          │  └───────────────────────────────────────────────────┘
          │
          ▼
   ┌──────────────────────────┐
   │ Azure AI Search           │
   │ Hybrid query:             │
   │  • search = textQuery     │ ← full-text BM25
   │  • vector_queries = [..] │ ← HNSW on appropriate field(s)
   │  • queryType = semantic   │ ← optional L2 reranker
   │  • filter = OData filter  │ ← from facets
   │  • facets = [...]         │
   │  • top / skip             │ ← pagination
   └──────────┬───────────────┘
              │
              ▼
   ┌──────────────────────────┐
   │ Normalize @search.score   │
   │ → relevance %             │
   │ Return results + facets   │
   └──────────────────────────┘
```

---

## 11. Implementation Phases

### Phase 1 — Foundation (Day 1-2)
- [ ] Create backend project with FastAPI boilerplate
- [ ] Create frontend project with Vite + React + Tailwind
- [ ] Set up environment configuration and Azure SDK clients
- [ ] Create Azure AI Search index with the defined schema
- [ ] Set up Blob Storage containers

### Phase 2 — Upload & Indexing (Day 3-4)
- [ ] Implement Blob Storage upload service (originals + thumbnails)
- [ ] Implement Azure AI Vision analysis service (tags, caption, objects)
- [ ] Implement Azure AI Vision vectorization service (image embeddings)
- [ ] Implement `/api/upload` endpoint with full pipeline
- [ ] Build Upload tab UI: drag & drop, preview, progress

### Phase 3 — Search (Day 5-7)
- [ ] Implement text vectorization via AI Vision (Strategy A)
- [ ] Implement text vectorization via Azure OpenAI (Strategy B)
- [ ] Implement hybrid search with strategy selection (A / B / Compare)
- [ ] Implement `/api/search` and `/api/facets` endpoints
- [ ] Build Search tab UI: text input, image input, **strategy toggle**, results grid
- [ ] Build **compare mode** UI (side-by-side results with relevance deltas)
- [ ] Build facet sidebar with filter logic
- [ ] Build pagination with page-size selector

### Phase 4 — Polish (Day 8-9)
- [ ] Implement i18n (EN/ES) with react-i18next
- [ ] Add image modal (full-size viewer)
- [ ] Error handling & loading states
- [ ] Responsive design refinement
- [ ] Relevance score normalization

### Phase 5 — Deployment & Testing (Day 10)
- [ ] Dockerize backend
- [ ] Build frontend for production
- [ ] Deploy to Azure (App Service + Static Web Apps)
- [ ] End-to-end testing

---

## 12. Key Dependencies

### Backend (Python)
```
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
python-multipart>=0.0.9
azure-search-documents>=11.6.0
azure-storage-blob>=12.20.0
azure-ai-vision-imageanalysis>=1.0.0
openai>=1.35.0                   # Azure OpenAI text-embedding-3-large
azure-identity>=1.17.0
httpx>=0.27.0
Pillow>=10.3.0
pydantic-settings>=2.3.0
python-dotenv>=1.0.1
```

### Frontend (Node.js)
```
react + react-dom (18.x)
react-router-dom (6.x)
react-i18next + i18next
axios
tailwindcss (3.x)
@headlessui/react
react-dropzone
lucide-react (icons)
```

---

## 13. Important Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Dual vectorization (AI Vision + OpenAI)** | Allows comparing cross-modal (same space) vs best-in-class text embeddings; user chooses best strategy per use case |
| **Multi-vector index (2 fields)** | Azure AI Search supports multiple vector fields per document; minimal extra storage cost, maximum flexibility |
| **Compare mode (side-by-side)** | Visual comparison of result ranking differences between strategies; invaluable for evaluation |
| **AI Vision 4.0 for image vectors** | Florence model produces 1024-d embeddings for images AND text in the same space → native image↔image and text↔image search |
| **OpenAI text-embedding-3-large** | 3072 dimensions, best-in-class text semantics; may outperform Vision text embeddings for nuanced text queries |
| **Parallel vectorization at index time** | Both vectors generated concurrently (asyncio.gather) → no added latency |
| **Facets on tags + objects** | AI Vision extracts semantic labels automatically → natural facet categories like "dog", "car", "building" |
| **Thumbnail generation server-side** | Consistent 256×256 thumbnails stored in Blob → fast loading, no client resize |
| **Hybrid search (BM25 + vector + RRF)** | Combines keyword precision with semantic recall via native Reciprocal Rank Fusion |
| **react-i18next** | Industry standard for React i18n, supports lazy loading, interpolation |

---

## 14. Strategy Comparison — Expected Behavior

| Scenario | Strategy A (AI Vision) | Strategy B (OpenAI + Vision) | Expected Winner |
|----------|----------------------|-----------------------------|-----------------|
| Simple text: "dog" | Good — Vision multimodal understands basic concepts | Good — OpenAI also handles this well | Tie |
| Complex text: "a golden retriever playing fetch on a sandy beach at sunset" | Decent — limited by 1024-d capacity | Better — 3072-d captures nuance | **B** |
| Abstract text: "loneliness" or "joy" | Limited — Vision trained on visual concepts | Better — OpenAI trained on broad text semantics | **B** |
| Image query (photo of a dog) | Excellent — native image embedding space | Same image vector used | Tie |
| Text + Image combined | Both vectors in same space → natural fusion | Different spaces → RRF fusion across fields | Depends on query |

> The compare mode lets users **empirically validate** which strategy works best for their specific image collection and query patterns.
