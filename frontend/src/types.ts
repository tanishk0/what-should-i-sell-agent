export interface Citation {
  source: string;
  engine?: string;
  search_id?: string;
  serpapi_json_url?: string;
  product_url?: string;
  review_url?: string;
  retrieved_at?: string;
}

export interface ComplaintEvidence {
  review_id: string;
  product_id: string;
  product_title: string;
  rating?: number | null;
  original_text: string;
  evidence_quote?: string | null;
  evidence_verified: boolean;
  url: string;
  citation: Citation;
}

export interface ProblemCluster {
  id: string;
  problem: string;
  category: string;
  description: string;
  supporting_reviews: ComplaintEvidence[];
  supporting_products: string[];
  unaffected_products: string[];
  review_count: number;
  product_count: number;
  product_prevalence_pct: number;
  avg_severity: number;
  is_widespread_gap: boolean;
}

export interface CompetitorRow {
  rank: number;
  title: string;
  price: string;
  rating: string;
  review_count: string;
  complaints_count: number;
  url: string;
}

export interface CitationItem {
  id: string;
  kind: "review" | "product" | "search";
  label: string;
  source: string;
  url: string;
}

export interface MarketGapReport {
  query: string;
  market: string;
  currency: string;
  created_at: string;
  total_competitors_found: number;
  total_competitors_analyzed: number;
  total_reviews_analyzed: number;
  total_complaints_found: number;
  summary: string;
  has_insufficient_evidence: boolean;
  competitors: CompetitorRow[];
  problems: ProblemCluster[];
  citations: CitationItem[];
  metadata?: Record<string, any>;
}

export interface ProductDetail {
  id: string;
  title: string;
  url: string;
  price?: number | null;
  rating?: number | null;
  review_count?: number | null;
  score?: number;
  sources?: string[];
}

export interface PriceRange {
  min?: number | null;
  max?: number | null;
  currency: string;
}

export type ResearchStage =
  | "finding_competitors"
  | "collecting_reviews"
  | "analyzing_complaints"
  | "validating_evidence"
  | "preparing_report"
  | "done"
  | "failed";

export interface ResearchJob {
  id: string;
  query: string;
  market: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: ResearchStage;
  progress: number;
  message: string;
  created_at: string;
  updated_at: string;
  error?: string | null;
  report?: MarketGapReport | null;
  price_range?: PriceRange | null;
  product_details?: Record<string, ProductDetail> | null;
}

export interface MarketOption {
  code: string;
  name: string;
  domain: string;
  currency: string;
}
