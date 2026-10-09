import React, { useState } from "react";
import {
  Layers,
  Users,
  MessageSquare,
  AlertOctagon,
  Tag,
  ArrowRight,
  ChevronRight,
  Quote,
  ShieldAlert,
  Info,
} from "lucide-react";
import type { MarketGapReport, ProblemCluster, ProductDetail, PriceRange } from "../types";
import { CompetitorsTable } from "./CompetitorsTable";
import { CitationsSection } from "./CitationsSection";
import { EvidenceDrawer } from "./EvidenceDrawer";

interface ReportScreenProps {
  report: MarketGapReport;
  priceRange?: PriceRange | null;
  productMap?: Record<string, ProductDetail> | null;
  onNewSearch: () => void;
}

export const ReportScreen: React.FC<ReportScreenProps> = ({
  report,
  priceRange,
  productMap,
  onNewSearch,
}) => {
  const [activeTab, setActiveTab] = useState<"problems" | "competitors" | "citations">("problems");
  const [selectedProblem, setSelectedProblem] = useState<ProblemCluster | null>(null);

  // Price formatting
  const formattedPriceRange = () => {
    if (priceRange?.min !== undefined && priceRange?.max !== undefined && priceRange.min !== null && priceRange.max !== null) {
      const sym = priceRange.currency === "INR" ? "₹" : "$";
      return `${sym}${Math.round(priceRange.min)} – ${sym}${Math.round(priceRange.max)}`;
    }
    return "-";
  };

  const severityBadge = (sev: number) => {
    if (sev >= 2.5) {
      return (
        <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider bg-red-500/10 text-red-400 border border-red-500/20">
          Critical Defect
        </span>
      );
    }
    if (sev >= 1.8) {
      return (
        <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider bg-amber-500/10 text-amber-400 border border-amber-500/20">
          Significant Friction
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider bg-slate-500/10 text-slate-400 border border-slate-500/20">
        Minor Defect
      </span>
    );
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 space-y-10">
      {/* Overview Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-6 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-medium bg-slate-900 border border-slate-800 text-slate-300">
              Amazon {report.market.toUpperCase()}
            </span>
            <span className="text-slate-600">•</span>
            <span className="text-xs font-mono text-slate-500">
              {new Date(report.created_at).toLocaleDateString()}
            </span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-white capitalize">
            {report.query}
          </h1>
          <p className="text-sm text-slate-400 mt-2 max-w-2xl">
            Evidence-backed market gap analysis synthesized from verified competitor listings and customer reviews.
          </p>
        </div>

        <button
          onClick={onNewSearch}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium text-slate-300 bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 transition-colors shrink-0 cursor-pointer"
        >
          <span>Change category</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Quantitative Metrics Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5 sm:gap-4 font-mono">
        {/* Products Analyzed */}
        <div className="p-4 rounded-xl bg-[#11131a] border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Products</span>
            <Users className="w-4 h-4 text-slate-500" />
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {report.total_competitors_analyzed}
          </div>
          <div className="text-[11px] text-slate-500 mt-1 font-sans">
            of {report.total_competitors_found} found
          </div>
        </div>

        {/* Reviews Analyzed */}
        <div className="p-4 rounded-xl bg-[#11131a] border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Reviews</span>
            <MessageSquare className="w-4 h-4 text-slate-500" />
          </div>
          <div className="text-2xl font-bold text-white tracking-tight">
            {report.total_reviews_analyzed}
          </div>
          <div className="text-[11px] text-slate-500 mt-1 font-sans">
            customer reviews
          </div>
        </div>

        {/* Price Range */}
        <div className="p-4 rounded-xl bg-[#11131a] border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Price Range</span>
            <Tag className="w-4 h-4 text-slate-500" />
          </div>
          <div className="text-xl font-bold text-white tracking-tight truncate" title={formattedPriceRange()}>
            {formattedPriceRange()}
          </div>
          <div className="text-[11px] text-slate-500 mt-1 font-sans">
            in {report.currency}
          </div>
        </div>

        {/* Recurring Problems */}
        <div className="p-4 rounded-xl bg-[#11131a] border border-slate-800">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Problems</span>
            <AlertOctagon className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold text-indigo-400 tracking-tight">
            {report.problems.length}
          </div>
          <div className="text-[11px] text-slate-500 mt-1 font-sans">
            recurring defect clusters
          </div>
        </div>

        {/* Verified Complaints */}
        <div className="p-4 rounded-xl bg-[#11131a] border border-slate-800 col-span-2 sm:col-span-1">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Complaints</span>
            <Layers className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 tracking-tight">
            {report.total_complaints_found}
          </div>
          <div className="text-[11px] text-slate-500 mt-1 font-sans">
            verbatim citations
          </div>
        </div>
      </div>

      {/* Executive Synthesis Summary */}
      <div className="bg-[#11131a] border border-slate-800 rounded-xl p-5 sm:p-6 shadow-sm">
        <div className="flex items-start gap-3">
          <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
          <div>
            <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold mb-1">
              Executive Synthesis
            </h3>
            <p className="text-sm text-slate-200 leading-relaxed font-sans">
              {report.summary}
            </p>
          </div>
        </div>
      </div>

      {/* View Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 text-sm font-medium">
        <button
          onClick={() => setActiveTab("problems")}
          className={`pb-3 px-3 transition-colors relative cursor-pointer ${
            activeTab === "problems"
              ? "text-white font-semibold"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>Customer Problems ({report.problems.length})</span>
          {activeTab === "problems" && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-500 rounded-full" />
          )}
        </button>

        <button
          onClick={() => setActiveTab("competitors")}
          className={`pb-3 px-3 transition-colors relative cursor-pointer ${
            activeTab === "competitors"
              ? "text-white font-semibold"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>Competitor Benchmark ({report.competitors.length})</span>
          {activeTab === "competitors" && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-500 rounded-full" />
          )}
        </button>

        <button
          onClick={() => setActiveTab("citations")}
          className={`pb-3 px-3 transition-colors relative cursor-pointer ${
            activeTab === "citations"
              ? "text-white font-semibold"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>Evidence Limitations & Citations ({report.citations.length})</span>
          {activeTab === "citations" && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-500 rounded-full" />
          )}
        </button>
      </div>

      {/* Tab Content 1: Customer Problems */}
      {activeTab === "problems" && (
        <div className="space-y-4">
          {report.problems.length === 0 ? (
            <div className="p-12 text-center rounded-xl bg-[#11131a] border border-slate-800">
              <ShieldAlert className="w-8 h-8 text-slate-500 mx-auto mb-3" />
              <h3 className="text-base font-semibold text-slate-200 mb-1">
                No Recurring Complaint Clusters Detected
              </h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                Across {report.total_competitors_analyzed} analyzed competitor products, customer reviews did not exhibit recurring
                functional defects that met evidence thresholds.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {report.problems.map((prob) => {
                const topQuote = prob.supporting_reviews.find((r) => r.evidence_quote)?.evidence_quote;

                return (
                  <div
                    key={prob.id}
                    onClick={() => setSelectedProblem(prob)}
                    className="p-5 sm:p-6 rounded-xl bg-[#11131a] hover:bg-[#151822] border border-slate-800 hover:border-slate-700 transition-all cursor-pointer group shadow-sm"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400">
                          {prob.category.replace("_", " ")}
                        </span>
                        {severityBadge(prob.avg_severity)}
                        {prob.is_widespread_gap ? (
                          <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-medium">
                            Widespread Market Gap
                          </span>
                        ) : (
                          <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800/80 text-slate-400 border border-slate-700/60">
                            Isolated Defect
                          </span>
                        )}
                      </div>

                      {/* Prevalence indicator */}
                      <div className="flex items-center gap-4 text-xs font-mono text-slate-400 shrink-0">
                        <div>
                          <span className="text-slate-200 font-semibold">{prob.product_count}</span>
                          <span className="text-slate-500"> of {report.total_competitors_analyzed} brands</span>
                          <span className="text-indigo-400 ml-1.5 font-bold">({prob.product_prevalence_pct}%)</span>
                        </div>
                        <div className="text-slate-600">•</div>
                        <div>
                          <span className="text-slate-200 font-semibold">{prob.review_count}</span>
                          <span className="text-slate-500"> reviews</span>
                        </div>
                      </div>
                    </div>

                    {/* Problem Title & Description */}
                    <div className="mb-4">
                      <h3 className="text-base sm:text-lg font-semibold text-white group-hover:text-indigo-200 transition-colors tracking-tight">
                        {prob.problem}
                      </h3>
                      <p className="text-xs sm:text-sm text-slate-400 mt-1.5 leading-relaxed line-clamp-2">
                        {prob.description}
                      </p>
                    </div>

                    {/* Verbatim quote snippet callout */}
                    {topQuote && (
                      <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 mb-4 flex items-start gap-2.5 text-xs text-amber-200/90 italic">
                        <Quote className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5 opacity-80" />
                        <span className="line-clamp-1">"{topQuote}"</span>
                      </div>
                    )}

                    {/* Bottom CTA / metadata */}
                    <div className="flex items-center justify-between text-xs pt-3 border-t border-slate-800/60">
                      <div className="flex items-center gap-2 text-slate-500 font-mono text-[11px]">
                        <span>Counter-evidence:</span>
                        <span className="text-emerald-400 font-medium">
                          {prob.unaffected_products.length} unaffected competitors
                        </span>
                      </div>

                      <div className="inline-flex items-center gap-1 font-medium text-xs text-indigo-400 group-hover:text-indigo-300 group-hover:translate-x-0.5 transition-all">
                        <span>Inspect Evidence & Quotes</span>
                        <ChevronRight className="w-4 h-4" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab Content 2: Competitor Benchmark */}
      {activeTab === "competitors" && (
        <CompetitorsTable competitors={report.competitors} currency={report.currency} />
      )}

      {/* Tab Content 3: Citations & Limitations */}
      {activeTab === "citations" && (
        <CitationsSection
          citations={report.citations}
          hasInsufficientEvidence={report.has_insufficient_evidence}
          totalCompetitorsAnalyzed={report.total_competitors_analyzed}
          totalReviewsAnalyzed={report.total_reviews_analyzed}
        />
      )}

      {/* Evidence Drawer Modal */}
      <EvidenceDrawer
        problem={selectedProblem}
        onClose={() => setSelectedProblem(null)}
        productMap={productMap}
      />
    </div>
  );
};
