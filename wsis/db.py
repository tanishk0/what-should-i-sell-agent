"""MongoDB persistence layer for WSIS market research results.

Collections:
- research_runs: Full ResearchSet runs (searches, products, stats, timestamps)
- products: Canonical competitor products (for cross-run queries and ranking)
- review_intelligence: Full ReviewIntelligence runs (analyzed competitor reviews & buyer frustrations)
- problem_analyses: Step 3 clustered recurring problem themes with opportunity scores
- problem_clusters: Individual problem clusters indexed by category & opportunity score
- opportunity_analyses: Step 4 candidate product opportunities addressing recurring problems
- candidate_opportunities: Individual candidate opportunities indexed by priority_score & category
- challenge_runs: Step 5 agentic challenge loop runs stress-testing hypotheses
- final_opportunities: Validated and re-ranked final product opportunities
- competitor_assessments: Step 6 competitor benchmark matrices & strategic market gap analysis
- product_specs: Step 7 evidence-traceable actionable product specifications
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import pymongo
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from .assessment.models import CompetitorAssessment
from .challenge.models import ChallengeLoopAnalysis
from .config import get_mongo_db_name, get_mongo_uri
from .opportunities.models import OpportunityAnalysis
from .reviews.models import ReviewIntelligence
from .reviews.problem_models import ProblemAnalysis
from .schema import ResearchSet
from .spec.models import ProductSpec

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

            self.db.opportunity_analyses.create_index([("run_id", pymongo.ASCENDING)], unique=True)
            self.db.opportunity_analyses.create_index([("query", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])

            self.db.candidate_opportunities.create_index(
                [("query", pymongo.ASCENDING), ("priority_score", pymongo.DESCENDING)]
            )
            self.db.candidate_opportunities.create_index([("problem_id", pymongo.ASCENDING)])
            self.db.candidate_opportunities.create_index([("category", pymongo.ASCENDING)])

            self.db.challenge_runs.create_index([("run_id", pymongo.ASCENDING)], unique=True)
            self.db.challenge_runs.create_index([("query", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])

            self.db.final_opportunities.create_index(
                [("query", pymongo.ASCENDING), ("final_score", pymongo.DESCENDING)]
            )
            self.db.final_opportunities.create_index([("verdict", pymongo.ASCENDING)])
            self.db.final_opportunities.create_index([("recommendation", pymongo.ASCENDING)])

            self.db.competitor_assessments.create_index([("run_id", pymongo.ASCENDING)], unique=True)
            self.db.competitor_assessments.create_index([("query", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])
            self.db.competitor_profiles.create_index([("run_id", pymongo.ASCENDING), ("id", pymongo.ASCENDING)])

            self.db.product_specs.create_index([("run_id", pymongo.ASCENDING)], unique=True)
            self.db.product_specs.create_index([("query", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)])
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

    def save_opportunity_analysis(self, opp_analysis: OpportunityAnalysis, run_id: str) -> str:
        """Store candidate opportunities analysis and individual opportunities."""
        data = opp_analysis.model_dump()
        doc_id = f"{run_id}_opportunities"
        data["_id"] = doc_id
        data["run_id"] = run_id
        data["query"] = opp_analysis.query
        data["market"] = opp_analysis.market

        # 1. Save top-level analysis
        self.db.opportunity_analyses.replace_one({"_id": doc_id}, data, upsert=True)

        # 2. Save individual candidate opportunities for cross-run queries & ranking
        now = datetime.now(timezone.utc)
        for opp in opp_analysis.opportunities:
            opp_doc = opp.model_dump()
            opp_doc["run_id"] = run_id
            opp_doc["query"] = opp_analysis.query
            opp_doc["market"] = opp_analysis.market
            opp_doc["created_at"] = now
            opp_id = f"{run_id}_{opp.id}"
            opp_doc["_id"] = opp_id
            self.db.candidate_opportunities.replace_one({"_id": opp_id}, opp_doc, upsert=True)

        return doc_id

    def save_challenge_analysis(self, challenge_analysis: ChallengeLoopAnalysis, run_id: str) -> str:
        """Store Step 5 challenge loop results and final validated opportunities."""
        data = challenge_analysis.model_dump()
        doc_id = f"{run_id}_challenge"
        data["_id"] = doc_id
        data["run_id"] = run_id
        data["query"] = challenge_analysis.query
        data["market"] = challenge_analysis.market

        # 1. Save top-level challenge analysis
        self.db.challenge_runs.replace_one({"_id": doc_id}, data, upsert=True)

        # 2. Save individual final opportunities for ranking and portfolio review
        now = datetime.now(timezone.utc)
        for opp in challenge_analysis.final_opportunities:
            opp_doc = opp.model_dump()
            opp_doc["run_id"] = run_id
            opp_doc["query"] = challenge_analysis.query
            opp_doc["market"] = challenge_analysis.market
            opp_doc["created_at"] = now
            opp_id = f"{run_id}_final_{opp.opportunity_id}"
            opp_doc["_id"] = opp_id
            self.db.final_opportunities.replace_one({"_id": opp_id}, opp_doc, upsert=True)

        return doc_id

    def save_competitor_assessment(self, assessment: CompetitorAssessment, run_id: str) -> str:
        """Store Step 6 competitor assessment and benchmark profiles."""
        data = assessment.model_dump()
        doc_id = f"{run_id}_assessment"
        data["_id"] = doc_id
        data["run_id"] = run_id
        data["query"] = assessment.query
        data["market"] = assessment.market

        # 1. Save top-level assessment
        self.db.competitor_assessments.replace_one({"_id": doc_id}, data, upsert=True)

        # 2. Save individual competitor profile documents
        now = datetime.now(timezone.utc)
        for comp in assessment.competitors:
            comp_doc = comp.model_dump()
            comp_doc["run_id"] = run_id
            comp_doc["query"] = assessment.query
            comp_doc["market"] = assessment.market
            comp_doc["created_at"] = now
            comp_id = f"{run_id}_comp_{comp.id}"
            comp_doc["_id"] = comp_id
            self.db.competitor_profiles.replace_one({"_id": comp_id}, comp_doc, upsert=True)

        return doc_id

    def save_product_spec(self, spec: ProductSpec, run_id: str) -> str:
        """Store Step 7 evidence-traceable product specification."""
        data = spec.model_dump()
        doc_id = f"{run_id}_spec"
        data["_id"] = doc_id
        data["run_id"] = run_id
        data["query"] = spec.query
        data["market"] = spec.market

        self.db.product_specs.replace_one({"_id": doc_id}, data, upsert=True)
        return doc_id

    def close(self) -> None:
        """Close the MongoDB connection pool."""
        if self._client:
            self._client.close()
            self._client = None
