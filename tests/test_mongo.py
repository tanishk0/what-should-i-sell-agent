from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from wsis.db import MongoStorage
from wsis.reviews.models import (
    AspectInsight,
    ProductReviews,
    Review,
    ReviewCitation,
    ReviewIntelligence,
)
from wsis.reviews.problem_models import ProblemAnalysis, ProblemCluster
from wsis.schema import Citation, Listing, Product, ResearchSet, SearchRecord


def _make_dummy_research_set() -> ResearchSet:
    cit = Citation(source="amazon", engine="amazon", search_id="s1")
    listing = Listing(
        source="amazon",
        source_product_id="B001",
        title="Test Yoga Mat",
        url="https://amazon.com/dp/B001",
        price=29.99,
        currency="USD",
        citation=cit,
    )
    product = Product(
        id="B001",
        title="Test Yoga Mat",
        url="https://amazon.com/dp/B001",
        price=29.99,
        sources=["amazon"],
        listings=[listing],
        relevance=1.0,
        score=0.9,
    )
    search = SearchRecord(
        source="amazon",
        engine="amazon",
        params={"q": "yoga mat"},
    )
    return ResearchSet(
        query="yoga mat",
        market="us",
        currency="USD",
        created_at=datetime.now(timezone.utc),
        searches=[search],
        products=[product],
    )


def test_mongo_from_env_none(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGO_URI", raising=False)
    assert MongoStorage.from_env() is None


def test_mongo_from_env_configured(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGO_DB_NAME", "custom_wsis")
    storage = MongoStorage.from_env()
    assert storage is not None
    assert storage.uri == "mongodb://localhost:27017"
    assert storage.db_name == "custom_wsis"


def test_mongo_save_research_set():
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_client.__getitem__.return_value = mock_db

    storage = MongoStorage(uri="mongodb://localhost:27017", db_name="test_db", client=mock_client)

    rs = _make_dummy_research_set()
    run_id = storage.save_research_set(rs, run_id="run-123")

    assert run_id == "run-123"
    # Verify research_runs replacement
    mock_db.research_runs.replace_one.assert_called_once()
    args, kwargs = mock_db.research_runs.replace_one.call_args
    assert args[0] == {"_id": "run-123"}
    assert args[1]["query"] == "yoga mat"
    assert kwargs.get("upsert") is True

    # Verify products replacement
    mock_db.products.replace_one.assert_called_once()
    prod_args, prod_kwargs = mock_db.products.replace_one.call_args
    assert prod_args[0] == {"run_id": "run-123", "id": "B001"}
    assert prod_args[1]["title"] == "Test Yoga Mat"


def test_mongo_save_reviews_and_problems():
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_client.__getitem__.return_value = mock_db

    storage = MongoStorage(uri="mongodb://localhost:27017", db_name="test_db", client=mock_client)

    rev_cit = ReviewCitation(
        source="amazon",
        engine="amazon_product",
        product_url="https://amazon.com/dp/B001",
    )
    rev_intel = ReviewIntelligence(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        llm_model="test-model",
        products=[
            ProductReviews(
                product_id="B001",
                product_title="Test Yoga Mat",
                product_url="https://amazon.com/dp/B001",
                rank=1,
            )
        ],
    )
    prob_analysis = ProblemAnalysis(
        query="yoga mat",
        market="us",
        created_at=datetime.now(timezone.utc),
        total_reviews_analyzed=10,
        total_complaints_analyzed=5,
        clusters=[
            ProblemCluster(
                id="prob-1",
                name="Slippery surface",
                category="performance",
                description="Mat becomes slippery when sweaty.",
                total_complaints=5,
                opportunity_score=0.85,
            )
        ],
    )

    rev_doc_id = storage.save_review_intelligence(rev_intel, run_id="run-123")
    assert rev_doc_id == "run-123_reviews"
    mock_db.review_intelligence.replace_one.assert_called_once()

    prob_doc_id = storage.save_problem_analysis(prob_analysis, run_id="run-123")
    assert prob_doc_id == "run-123_problems"
    mock_db.problem_analyses.replace_one.assert_called_once()
    mock_db.problem_clusters.replace_one.assert_called_once()


def test_mongo_ping():
    mock_client = MagicMock()
    mock_client.admin.command.return_value = {"ok": 1}
    storage = MongoStorage(uri="mongodb://localhost:27017", client=mock_client)
    assert storage.ping() is True

    from pymongo.errors import ConnectionFailure

    mock_client.admin.command.side_effect = ConnectionFailure("network error")
    assert storage.ping() is False
