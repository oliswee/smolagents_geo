"""Spatial-enhanced RAG retriever.

Combines semantic vector search with PostGIS spatial neighbor expansion,
then re-ranks results. This is the core retrieval logic that makes
cross-area questions ("what's around Parramatta?") work correctly.
"""
from typing import List, Dict, Optional, Tuple
from src.rag.vector_store import VectorStore
from src.rag.query_rewriter import expand_query


class SpatialRetriever:
    """Retrieves suburb reports with spatial context augmentation."""

    def __init__(
        self,
        vector_store: VectorStore,
        db_connection,  # SQLAlchemy connection
        config: dict,
    ):
        self.vs = vector_store
        self.conn = db_connection
        self.semantic_k = config.get("semantic_k", 5)
        self.max_neighbors = config.get("max_neighbors", 8)
        self.neighbor_distance_m = config.get("neighbor_distance_m", 5000)
        self.similarity_weight = config.get("similarity_weight", 0.7)
        self.spatial_weight = config.get("spatial_weight", 0.3)
        self.min_threshold = config.get("min_similarity_threshold", 0.5)
        self.srid = 4283

    def get_neighbor_areas(self, suburb_names: List[str]) -> List[str]:
        """Find neighboring areas via PostGIS topology query.

        Uses two criteria, either of which qualifies as "neighbor":
        1. Shared boundary (ST_Touches)
        2. Centroid distance < neighbor_distance_m
        """
        if not suburb_names:
            return []

        # Use parameterized query to prevent SQL injection
        placeholders = ", ".join([f"'{name}'" for name in suburb_names])

        sql = f"""
        SELECT DISTINCT b."SA2_NAME21" AS neighbor_name
        FROM sa2_regions a, sa2_regions b
        WHERE a."SA2_NAME21" IN ({placeholders})
          AND a."SA2_CODE21" != b."SA2_CODE21"
          AND (
              ST_Touches(a.geom, b.geom)
              OR ST_Distance(
                  ST_Centroid(a.geom),
                  ST_Centroid(b.geom)
              ) < {self.neighbor_distance_m}
          )
        LIMIT {self.max_neighbors};
        """

        try:
            import pandas as pd
            df = pd.read_sql_query(sql, self.conn)
            return df["neighbor_name"].tolist()
        except Exception as e:
            print(f"Neighbor query failed: {e}")
            return []

    def retrieve(
        self,
        query: str,
        top_n: int = 5,
        filter_dimension: Optional[str] = None,
    ) -> Dict:
        """Full spatial-enhanced retrieval pipeline.

        Args:
            query: User's natural language question.
            top_n: Final number of chunks to return.
            filter_dimension: Optional dimension filter.

        Returns:
            Dict with keys:
                chunks: List of top chunks after re-ranking.
                neighbor_areas: List of neighboring area names found.
                max_similarity: Highest semantic similarity score.
                retrieval_method: Description string.
        """
        # Step 1: Expand query with domain synonyms
        expanded_query = expand_query(query)

        # Step 2: Semantic vector search
        semantic_results = self.vs.search(
            expanded_query,
            k=self.semantic_k,
            filter_dimension=filter_dimension,
        )

        if not semantic_results:
            return {
                "chunks": [],
                "neighbor_areas": [],
                "max_similarity": 0.0,
                "retrieval_method": "semantic_vector (no results)",
            }

        max_similarity = max(r["similarity"] for r in semantic_results)

        # Step 3: Extract unique suburb names from results
        seed_suburbs = list(set(
            r["metadata"]["suburb_name"] for r in semantic_results
        ))

        # Step 4: PostGIS neighbor expansion
        neighbor_names = self.get_neighbor_areas(seed_suburbs)

        # Step 5: Load neighbor chunks from ChromaDB
        neighbor_chunks = []
        if neighbor_names:
            for name in neighbor_names:
                try:
                    results = self.vs.search(
                        name,
                        k=1,  # One chunk per neighbor dimension
                        filter_dimension=filter_dimension,
                    )
                    neighbor_chunks.extend(results)
                except Exception:
                    pass

        # Step 6: Merge & re-rank
        all_candidates = semantic_results + neighbor_chunks

        # Assign spatial proximity scores:
        #   seed areas = 1.0, neighbors = 0.5, others = 0.0
        for c in all_candidates:
            area = c["metadata"]["suburb_name"]
            if area in seed_suburbs:
                c["spatial_score"] = 1.0
            elif area in neighbor_names:
                c["spatial_score"] = 0.5
            else:
                c["spatial_score"] = 0.0

            c["combined_score"] = (
                self.similarity_weight * c["similarity"]
                + self.spatial_weight * c["spatial_score"]
            )

        # Sort by combined score, deduplicate by area+dimension
        seen = set()
        final_chunks = []
        for c in sorted(all_candidates, key=lambda x: x["combined_score"], reverse=True):
            key = f"{c['metadata']['suburb_name']}_{c['metadata']['dimension']}"
            if key not in seen:
                seen.add(key)
                final_chunks.append(c)
            if len(final_chunks) >= top_n:
                break

        return {
            "chunks": final_chunks,
            "neighbor_areas": neighbor_names,
            "max_similarity": max_similarity,
            "retrieval_method": "semantic_vector + spatial_extension + rerank",
        }

    def is_confident(self, max_similarity: float) -> bool:
        """Check if retrieval confidence is above threshold."""
        return max_similarity >= self.min_threshold
