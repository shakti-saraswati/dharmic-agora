"""
AKASHA-RAG: Enterprise RAG Pipeline
Extracted from NVIDIA Enterprise RAG Blueprint
Integrated with SAB Knowledge Graph (Indra's Net)

Core capabilities:
- Multi-modal document ingestion (PDF, text, tables, charts)
- GPU-accelerated embeddings (NeMo Retriever)
- Vector search with Milvus/cuVS
- Semantic retrieval with reranking
- SAB Knowledge Graph bridge
"""

import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import numpy as np

# Placeholder for actual NVIDIA imports
# from nemoretriever import NVEmbedQAModel, NVRerankQAModel
# from milvus import MilvusClient


@dataclass
class Document:
    """Represents an ingested document chunk"""
    id: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None
    source_file: str = ""
    chunk_index: int = 0


@dataclass
class SearchResult:
    """Result from vector search"""
    document: Document
    score: float
    rerank_score: Optional[float] = None


class AkashaRAGPipeline:
    """
    Enterprise RAG Pipeline - AKASHA Module
    
    Mirrors NVIDIA's Enterprise RAG Blueprint:
    - Document ingestion with multi-modal support
    - GPU-accelerated embedding generation
    - Hybrid search (dense + sparse)
    - Reranking for accuracy
    - SAB Knowledge Graph integration
    """
    
    def __init__(
        self,
        collection_name: str = "akasha_knowledge",
        embedding_model: str = "nvidia/llama-3.2-nv-embedqa-1b-v2",
        rerank_model: str = "nvidia/llama-3.2-nv-rerankqa-1b-v2",
        sab_bridge_enabled: bool = True
    ):
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.rerank_model = rerank_model
        self.sab_bridge_enabled = sab_bridge_enabled
        
        # Initialize components (placeholders for actual NVIDIA/Milvus init)
        self.documents: Dict[str, Document] = {}
        self.embedding_cache: Dict[str, List[float]] = {}
        
        # SAB Knowledge Graph connection
        self.sab_knowledge_nodes: List[Dict] = []

        # Optional Milvus connection
        self.use_milvus = False
        self._milvus_collection = None
        milvus_host = os.getenv("MILVUS_HOST", "localhost")
        milvus_port = os.getenv("MILVUS_PORT", "19530")
        if os.getenv("USE_MILVUS", "false").lower() == "true":
            try:
                from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility
                connections.connect(alias="default", host=milvus_host, port=milvus_port)
                if not utility.has_collection(self.collection_name):
                    fields = [
                        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
                        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=3072),
                        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=4096),
                    ]
                    schema = CollectionSchema(fields, description="AKASHA RAG embeddings")
                    self._milvus_collection = Collection(self.collection_name, schema)
                else:
                    self._milvus_collection = Collection(self.collection_name)

                # Ensure index exists
                if not self._milvus_collection.indexes:
                    index_params = {
                        "index_type": "IVF_FLAT",
                        "metric_type": "IP",
                        "params": {"nlist": 128}
                    }
                    self._milvus_collection.create_index(field_name="embedding", index_params=index_params)

                self._milvus_collection.load()
                self.use_milvus = True
            except Exception as e:
                # Fallback to in-memory if Milvus unavailable
                self.use_milvus = False
        
    def ingest_document(
        self,
        file_path: str,
        file_type: str = "auto",
        metadata: Optional[Dict] = None
    ) -> List[Document]:
        """
        Ingest document into RAG pipeline
        
        Supports: PDF, TXT, CSV, MD, and structured data
        Multi-modal: extracts text, tables, charts (via NeMo Retriever)
        """
        if metadata is None:
            metadata = {}

        # Enforce Redis-backed queue/state when configured.
        # Default is strict to prevent fire-and-forget ingestion drift.
        self._enforce_ingestion_governance(metadata)
        
        # Detect file type
        if file_type == "auto":
            file_type = self._detect_file_type(file_path)
        
        # Extract content based on type
        if file_type == "pdf":
            chunks = self._extract_pdf(file_path, metadata)
        elif file_type == "txt":
            chunks = self._extract_txt(file_path, metadata)
        elif file_type == "csv":
            chunks = self._extract_csv(file_path, metadata)
        else:
            chunks = self._extract_generic(file_path, metadata)
        
        # Generate embeddings (GPU-accelerated via NeMo)
        for chunk in chunks:
            chunk.embedding = self._generate_embedding(chunk.content)
            chunk.id = self._generate_id(chunk.content)
            self.documents[chunk.id] = chunk

            # Optional Milvus insert
            if self.use_milvus and self._milvus_collection is not None:
                try:
                    self._milvus_collection.insert([
                        [chunk.id],
                        [chunk.embedding],
                        [chunk.content[:4096]]
                    ])
                except Exception:
                    pass
            
            # SAB Knowledge Graph integration
            if self.sab_bridge_enabled:
                self._add_to_sab_knowledge(chunk)
        
        return chunks

    def _enforce_ingestion_governance(self, metadata: Dict[str, Any]) -> None:
        """Require queue/state metadata for ingestion when strict mode is enabled."""
        require_queue = os.getenv("REQUIRE_REDIS_QUEUE", "true").lower() == "true"
        if not require_queue:
            return

        required_keys = ["job_id", "queue", "state"]
        missing = [k for k in required_keys if not metadata.get(k)]
        if missing:
            raise ValueError(
                "Redis-backed ingestion governance active. Missing metadata keys: "
                + ", ".join(missing)
            )

    def search(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = True,
        filters: Optional[Dict] = None
    ) -> List[SearchResult]:
        """
        Semantic search with optional reranking
        
        Implements:
        - Dense retrieval via vector similarity
        - Optional sparse retrieval (keywords)
        - Cross-encoder reranking for accuracy
        """
        # Generate query embedding
        query_embedding = self._generate_embedding(query)
        
        # Dense retrieval (GPU-accelerated via Milvus/cuVS)
        candidates = self._dense_search(query_embedding, top_k * 2, filters)
        
        # Reranking (via NeMo Retriever reranker)
        if rerank:
            candidates = self._rerank(query, candidates, top_k)
        
        return candidates[:top_k]
    
    def query_with_context(
        self,
        query: str,
        system_prompt: Optional[str] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Full RAG query: retrieve context, generate answer
        
        Returns structured result with sources, confidence, and SAB provenance
        """
        # Retrieve relevant documents
        results = self.search(query, top_k=top_k)
        
        # Build context
        context = "\n\n".join([
            f"[Source {i+1}] {r.document.content[:500]}..."
            for i, r in enumerate(results)
        ])
        
        # SAB Knowledge Graph augmentation
        sab_context = ""
        if self.sab_bridge_enabled:
            sab_context = self._query_sab_knowledge(query)
        
        # Construct prompt (for LLM generation)
        full_prompt = f"""Context from knowledge base:
{context}

{sab_context}

Question: {query}

Answer based on the provided context."""
        
        return {
            "query": query,
            "context": context,
            "sab_context": sab_context,
            "sources": [r.document.metadata for r in results],
            "scores": [r.score for r in results],
            "prompt": full_prompt,
            "document_count": len(self.documents),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    # === Private methods ===
    
    def _detect_file_type(self, file_path: str) -> str:
        """Auto-detect file type from extension"""
        ext = os.path.splitext(file_path)[1].lower()
        type_map = {
            ".pdf": "pdf",
            ".txt": "txt",
            ".csv": "csv",
            ".md": "txt",
            ".json": "json"
        }
        return type_map.get(ext, "txt")
    
    def _extract_pdf(self, file_path: str, metadata: Dict) -> List[Document]:
        """Extract text/structure from PDF, preferring LlamaParse when enabled."""
        content = None
        parse_mode = "fallback"

        use_llamaparse = os.getenv("USE_LLAMAPARSE", "true").lower() == "true"
        if use_llamaparse:
            try:
                from integration.llamaparse_ingest import parse_pdf_to_markdown
                content = parse_pdf_to_markdown(file_path)
                parse_mode = "llamaparse"
            except Exception:
                # Hard fallback for continuity; caller can detect mode in metadata.
                content = None

        if not content:
            # Conservative fallback path (placeholder for PyMuPDF/NeMo extraction).
            with open(file_path, 'rb'):
                content = f"[PDF content from {os.path.basename(file_path)}]"

        text_chunks = self._chunk_text(content, chunk_size=512, overlap=50)

        chunks: List[Document] = []
        for i, chunk_text in enumerate(text_chunks):
            chunks.append(Document(
                id="",
                content=chunk_text,
                metadata={**metadata, "file_type": "pdf", "parse_mode": parse_mode},
                source_file=file_path,
                chunk_index=i
            ))

        return chunks
    
    def _extract_txt(self, file_path: str, metadata: Dict) -> List[Document]:
        """Extract text from txt/md files"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        text_chunks = self._chunk_text(content, chunk_size=512, overlap=50)
        
        return [
            Document(
                id="",
                content=chunk,
                metadata={**metadata, "file_type": "txt"},
                source_file=file_path,
                chunk_index=i
            )
            for i, chunk in enumerate(text_chunks)
        ]
    
    def _extract_csv(self, file_path: str, metadata: Dict) -> List[Document]:
        """Extract structured data from CSV"""
        import csv
        
        chunks = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            # Convert rows to text descriptions
            for i, row in enumerate(rows[:100]):  # Limit to first 100 rows for MVP
                row_text = " | ".join([f"{k}: {v}" for k, v in row.items()])
                chunks.append(Document(
                    id="",
                    content=row_text,
                    metadata={**metadata, "file_type": "csv", "row_index": i},
                    source_file=file_path,
                    chunk_index=i
                ))
        
        return chunks
    
    def _extract_generic(self, file_path: str, metadata: Dict) -> List[Document]:
        """Generic extraction fallback"""
        return self._extract_txt(file_path, metadata)
    
    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
        """Simple sliding window chunking"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap
        
        return chunks
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding via NVIDIA NIM (NeMo Retriever)"""
        nvidia_api_key = os.getenv("NVIDIA_API_KEY")
        model = os.getenv("NVIDIA_EMBED_MODEL", "nvidia/llama-3.2-nv-embedqa-1b-v2")
        
        if not nvidia_api_key:
            # Fallback to deterministic mock for offline testing
            text_hash = hashlib.md5(text.encode()).hexdigest()
            np.random.seed(int(text_hash[:8], 16))
            return np.random.randn(3072).tolist()
        
        import requests
        
        response = requests.post(
            "https://integrate.api.nvidia.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {nvidia_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "input": text
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    
    def _dense_search(
        self,
        query_embedding: List[float],
        top_k: int,
        filters: Optional[Dict]
    ) -> List[SearchResult]:
        """Dense vector search (GPU-accelerated via Milvus/cuVS)"""
        # Placeholder: actual implementation uses Milvus GPU search
        # Returns top-k documents by cosine similarity
        
        # If Milvus enabled, use vector search
        if self.use_milvus and self._milvus_collection is not None:
            try:
                search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
                res = self._milvus_collection.search(
                    [query_embedding],
                    "embedding",
                    search_params,
                    limit=top_k,
                    output_fields=["id", "text"]
                )
                results = []
                for hits in res:
                    for hit in hits:
                        doc_id = hit.entity.get("id")
                        if doc_id in self.documents:
                            results.append(SearchResult(document=self.documents[doc_id], score=float(hit.score)))
                return results
            except Exception:
                pass
        
        # Fallback to in-memory cosine similarity
        results = []
        query_vec = np.array(query_embedding)
        for doc_id, doc in self.documents.items():
            if doc.embedding:
                doc_vec = np.array(doc.embedding)
                similarity = np.dot(query_vec, doc_vec) / (
                    np.linalg.norm(query_vec) * np.linalg.norm(doc_vec)
                )
                results.append(SearchResult(document=doc, score=float(similarity)))
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def _rerank(
        self,
        query: str,
        candidates: List[SearchResult],
        top_k: int
    ) -> List[SearchResult]:
        """Rerank candidates via cross-encoder (NeMo Retriever reranker)"""
        # Placeholder: actual implementation uses nv-rerankqa model
        # Reorders candidates for better relevance
        
        # Simulate reranking (slight score adjustment)
        for result in candidates:
            # Add small boost for keyword matches
            query_words = set(query.lower().split())
            content_words = set(result.document.content.lower().split())
            overlap = len(query_words & content_words)
            result.rerank_score = result.score + (overlap * 0.01)
        
        # Sort by rerank score
        candidates.sort(key=lambda x: x.rerank_score or x.score, reverse=True)
        return candidates
    
    def _generate_id(self, content: str) -> str:
        """Generate unique ID for document chunk"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    # === SAB Knowledge Graph Integration ===
    
    def _add_to_sab_knowledge(self, document: Document):
        """Add document to SAB Knowledge Graph (Indra's Net)"""
        # Bridge to SAB's Indra's Net - fractal knowledge graph
        knowledge_node = {
            "id": document.id,
            "type": "document_chunk",
            "content_hash": hashlib.sha256(document.content.encode()).hexdigest()[:16],
            "source": document.source_file,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": document.metadata,
            # SAB-specific fields
            "energy_signature": self._calculate_energy(document.content),
            "clarity_score": self._calculate_clarity(document.content),
            "coherence_vector": self._extract_concepts(document.content),
            "connected_to": []  # Will be populated by SAB graph
        }
        
        self.sab_knowledge_nodes.append(knowledge_node)
    
    def _query_sab_knowledge(self, query: str) -> str:
        """Query SAB Knowledge Graph for additional context"""
        # Retrieve SAB-specific insights
        if not self.sab_knowledge_nodes:
            return ""
        
        # Find relevant SAB nodes (simplified)
        relevant_nodes = [
            node for node in self.sab_knowledge_nodes
            if any(term in node.get("coherence_vector", []) 
                   for term in query.lower().split())
        ][:3]
        
        if not relevant_nodes:
            return ""
        
        sab_context = "SA Knowledge Graph Context:\n"
        for node in relevant_nodes:
            sab_context += f"- {node['type']} from {node['source']} "
            sab_context += f"(clarity: {node.get('clarity_score', 0):.2f})\n"
        
        return sab_context
    
    def _calculate_energy(self, text: str) -> float:
        """Calculate 'energy' signature (SAB metric)"""
        # Placeholder: actual SAB implementation uses more sophisticated measures
        return min(1.0, len(text) / 1000)
    
    def _calculate_clarity(self, text: str) -> float:
        """Calculate clarity score (SAB metric)"""
        # Placeholder: coherence of language, structure
        sentences = text.split('.')
        return min(1.0, len([s for s in sentences if len(s) > 10]) / max(1, len(sentences)))
    
    def _extract_concepts(self, text: str) -> List[str]:
        """Extract key concepts for SAB coherence vector"""
        # Placeholder: keyword extraction
        words = text.lower().split()
        # Return most frequent non-trivial words
        from collections import Counter
        return [word for word, _ in Counter(words).most_common(5) 
                if len(word) > 4]


# === Example Usage ===

def main():
    """Example: AKASHA RAG Pipeline in action"""
    
    # Initialize pipeline
    rag = AkashaRAGPipeline(
        collection_name="example_knowledge",
        sab_bridge_enabled=True
    )
    
    # Simulate document ingestion
    print("AKASHA RAG Pipeline")
    print("=" * 50)
    print(f"Collection: {rag.collection_name}")
    print(f"Embedding model: {rag.embedding_model}")
    print(f"Rerank model: {rag.rerank_model}")
    print(f"SAB bridge: {'enabled' if rag.sab_bridge_enabled else 'disabled'}")
    print()
    
    # Note: Actual usage requires:
    # - NVIDIA API key
    # - Milvus vector database
    # - Document files
    
    print("To use:")
    print("1. Set NVIDIA_API_KEY environment variable")
    print("2. Ensure Milvus is running")
    print("3. Call rag.ingest_document('path/to/file.pdf')")
    print("4. Call rag.search('your query')")
    print("5. Call rag.query_with_context('your question')")


if __name__ == "__main__":
    main()
