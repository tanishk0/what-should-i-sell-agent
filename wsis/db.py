"""MongoDB persistence layer for WSIS market research results.

Collections:
- research_runs: Full ResearchSet runs (searches, products, stats, timestamps)
- products: Canonical competitor products (for cross-run queries and ranking)
- review_intelligence: Full ReviewIntelligence runs (analyzed competitor reviews & buyer frustrations)
- problem_analyses: Step 3 clustered recurring problem themes with opportunity scores
- problem_clusters: Individual problem clusters indexed by category & opportunity score
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import pymongo
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from .config import get_mongo_db_name, get_mongo_uri
from .reviews.models import ReviewIntelligence
from .reviews.problem_models import ProblemAnalysis
from .schema import ResearchSet

logger = logging.getLogger("wsis.db")


class MongoStorage:
    """Manages connection and document storage for WSIS in MongoDB."""

    def __init__(
        self,
        uri: str,
        db_name: str = "wsis",
        client: Optional[MongoClient] = None,
        timeout_ms: int = 3000,
    ) -> None:
        self.uri = uri
        self.db_name = db_name
        self.timeout_ms = timeout_ms
        self._client: Optional[MongoClient] = client
        self._db: Optional[Database] = None

    @classmethod
    def from_env(cls) -> Optional[MongoStorage]:
        """Factory creating storage from environment variables if configured."""
        uri = get_mongo_uri()
        if not uri:
            return None
        db_name = get_mongo_db_name()
        return cls(uri=uri, db_name=db_name)

    @property
    def client(self) -> MongoClient:
        if self._client is None:
            self._client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=self.timeout_ms,
                connectTimeoutMS=self.timeout_ms,
            )
        return self._client

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = self.client[self.db_name]
        return self._db

    def ping(self) -> bool:
        """Verify that the MongoDB server is reachable."""
        try:
            self.client.admin.command("ping")
            return True
        except PyMongoError as err:
            logger.warning(f"MongoDB ping failed: {err}")
            return False

    def init_indexes(self) -> None:
        """Create helpful indexes on collections."""
        try:
            self.db.research_runs.create_index([("query", pymongo.ASCENDING), ("market", pymongo.ASCENDING)])
            self.db.research_runs.create_index([("created_at", pymongo.DESCENDING)])

            self.db.products.create_index([("run_id", pymongo.ASCENDING), ("id", pymongo.ASCENDING)], unique=True)
            self.db.products.create_index([("query", pymongo.ASCENDING), ("score", pymongo.DESCENDING)])

            self.db.review_intelligence.create_index([("run_id", pymongo.ASCENDING)], unique=True)
            self.db.review_intelligence.create_index([("query", pymongo.ASCENDING), ("market", pymongo.ASCENDING)])

            self.db.problem_analyses.create_index([("run_id", pymongo.ASCENDING)], unique=True)
            self.db.problem_analyses.create_index([("query", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])

            self.db.problem_clusters.create_index(
                [("query", pymongo.ASCENDING), ("opportunity_score", pymongo.DESCENDING)]
            )
            self.db.problem_clusters.create_index([("category", pymongo.ASCENDING)])
        except PyMongoError as err:
            logger.warning(f"Failed to create MongoDB indexes: {err}")

    def save_research_set(self, research_set: ResearchSet, run_id: Optional[str] = None) -> str:
        """Store the ResearchSet run and normalize products into the 'products' collection."""
        data = research_set.model_dump()
        actual_run_id = run_id or f"{research_set.query.lower().replace(' ', '-')}-{int(datetime.now(timezone.utc).timestamp())}"
        data["_id"] = actual_run_id
        data["run_id"] = actual_run_id

        # 1. Upsert into research_runs
        self.db.research_runs.replace_one({"_id": actual_run_id}, data, upsert=True)

        # 2. Upsert each product in 'products' collection
        now = datetime.now(timezone.utc)
        for prod in research_set.products:
            prod_doc = prod.model_dump()
            prod_doc["run_id"] = actual_run_id
            prod_doc["query"] = research_set.query
            prod_doc["market"] = research_set.market
            prod_doc["updated_at"] = now
            self.db.products.replace_one(
                {"run_id": actual_run_id, "id": prod.id},
                prod_doc,
                upsert=True,
            )

        return actual_run_id

    def save_review_intelligence(self, rev_intel: ReviewIntelligence, run_id: str) -> str:
        """Store full review intelligence output associated with a research run."""
        data = rev_intel.model_dump()
        doc_id = f"{run_id}_reviews"
        data["_id"] = doc_id
        data["run_id"] = run_id
        data["query"] = rev_intel.query
        data["market"] = rev_intel.market

        self.db.review_intelligence.replace_one({"_id": doc_id}, data, upsert=True)
        return doc_id

    def save_problem_analysis(self, prob_analysis: ProblemAnalysis, run_id: str) -> str:
        """Store problem analysis and individual problem clusters."""
        data = prob_analysis.model_dump()
        doc_id = f"{run_id}_problems"
        data["_id"] = doc_id
        data["run_id"] = run_id
        data["query"] = prob_analysis.query
        data["market"] = prob_analysis.market

        # 1. Save top-level analysis
        self.db.problem_analyses.replace_one({"_id": doc_id}, data, upsert=True)

        # 2. Save individual problem clusters for cross-run analytics
        now = datetime.now(timezone.utc)
        for cluster in prob_analysis.clusters:
            cluster_doc = cluster.model_dump()
            cluster_doc["run_id"] = run_id
            cluster_doc["query"] = prob_analysis.query
            cluster_doc["market"] = prob_analysis.market
            cluster_doc["created_at"] = now
            cluster_id = f"{run_id}_{cluster.id}"
            cluster_doc["_id"] = cluster_id
            self.db.problem_clusters.replace_one({"_id": cluster_id}, cluster_doc, upsert=True)

        return doc_id

    def close(self) -> None:
        """Close the MongoDB connection pool."""
        if self._client:
            self._client.close()
            self._client = None
