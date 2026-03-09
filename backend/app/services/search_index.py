"""Azure AI Search — index creation & management (multi-vector schema)."""

from __future__ import annotations
import logging
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    HnswParameters,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField,
)
from azure.core.credentials import AzureKeyCredential
from app.config import get_settings

logger = logging.getLogger("app.search_index")

_index_client: SearchIndexClient | None = None


def init() -> None:
    """Create the SearchIndexClient and ensure the index exists."""
    global _index_client
    s = get_settings()
    logger.info("SearchIndex init — endpoint=%s", s.azure_search_endpoint)
    _index_client = SearchIndexClient(
        endpoint=s.azure_search_endpoint,
        credential=AzureKeyCredential(s.azure_search_api_key),
    )
    ensure_index()
    logger.info("SearchIndex init OK")


def ensure_index() -> None:
    """Create or update the search index with the multi-vector schema."""
    s = get_settings()
    client = _index_client

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="fileName", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="description", type=SearchFieldDataType.String, analyzer_name="standard.lucene"),
        SearchableField(name="caption", type=SearchFieldDataType.String),
        SearchField(
            name="tags",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            searchable=True,
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="objects",
            type=SearchFieldDataType.Collection(SearchFieldDataType.String),
            filterable=True,
            facetable=True,
        ),
        SimpleField(name="fileSize", type=SearchFieldDataType.Int64, filterable=True, facetable=True, sortable=True),
        SimpleField(name="width", type=SearchFieldDataType.Int32, filterable=True, facetable=True),
        SimpleField(name="height", type=SearchFieldDataType.Int32, filterable=True, facetable=True),
        SimpleField(
            name="uploadDate",
            type=SearchFieldDataType.DateTimeOffset,
            filterable=True,
            facetable=True,
            sortable=True,
        ),
        SimpleField(name="contentType", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="thumbnailUrl", type=SearchFieldDataType.String, retrievable=True),
        SimpleField(name="originalUrl", type=SearchFieldDataType.String, retrievable=True),
        # Vector field 1: AI Vision multimodal (1024-d)
        SearchField(
            name="imageVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=1024,
            vector_search_profile_name="vision-vector-profile",
        ),
        # Vector field 2: Azure OpenAI text-embedding-3-large (3072-d)
        SearchField(
            name="textVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=3072,
            vector_search_profile_name="openai-vector-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-vision",
                parameters=HnswParameters(m=4, ef_construction=400, ef_search=500, metric="cosine"),
            ),
            HnswAlgorithmConfiguration(
                name="hnsw-openai",
                parameters=HnswParameters(m=4, ef_construction=400, ef_search=500, metric="cosine"),
            ),
        ],
        profiles=[
            VectorSearchProfile(name="vision-vector-profile", algorithm_configuration_name="hnsw-vision"),
            VectorSearchProfile(name="openai-vector-profile", algorithm_configuration_name="hnsw-openai"),
        ],
    )

    # Semantic ranking configuration — re-ranks top results using a language model
    semantic_config = SemanticConfiguration(
        name="my-semantic-config",
        prioritized_fields=SemanticPrioritizedFields(
            content_fields=[SemanticField(field_name="description")],
            title_field=SemanticField(field_name="caption"),
            keywords_fields=[SemanticField(field_name="tags")],
        ),
    )
    semantic_search = SemanticSearch(configurations=[semantic_config])

    index = SearchIndex(
        name=s.azure_search_index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )

    logger.info("Creating/updating index '%s' (%d fields, 2 vector profiles)", s.azure_search_index_name, len(fields))
    client.create_or_update_index(index)
    logger.info("Index '%s' ready", s.azure_search_index_name)
