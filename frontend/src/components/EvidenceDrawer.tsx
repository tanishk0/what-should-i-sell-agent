import React, { useEffect } from "react";
import {
  X,
  ShieldCheck,
  ExternalLink,
  Quote,
  Star,
  CheckCircle2,
  AlertTriangle,
  Info,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import type { ProblemCluster, ProductDetail } from "../types";

interface EvidenceDrawerProps {
  problem: ProblemCluster | null;
  onClose: () => void;
  productMap?: Record<string, ProductDetail> | null;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({
  problem,
  onClose,
  productMap,
}) => {
  const [expandedReviews, setExpandedReviews] = React.useState<Record<string, boolean>>({});

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (problem) {
      document.body.style.overflow = "hidden";
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.body.style.overflow = "auto";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [problem, onClose]);

  if (!problem) return null;

  const toggleExpand = (id: string) => {
    setExpandedReviews((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const severityBadge = (sev: number) => {
    if (sev >= 2.5) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertTriangle className="w-3 h-3" />
          <span>Deal-breaker / Critical (Severity {sev.toFixed(1)}/3)</span>
        </span>
      );
    }
    if (sev >= 1.8) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <AlertTriangle className="w-3 h-3" />
          <span>Significant Friction (Severity {sev.toFixed(1)}/3)</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-slate-500/10 text-slate-400 border border-slate-500/20">
        <Info className="w-3 h-3" />
        <span>Minor Defect (Severity {sev.toFixed(1)}/3)</span>
      </span>
    );
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/75 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10 sm:pl-16">
        <div className="w-screen max-w-2xl bg-[#0e1017] border-l border-slate-800 shadow-2xl flex flex-col">
          {/* Drawer Header */}
          <div className="px-6 py-5 border-b border-slate-800 flex items-start justify-between bg-[#12141e]/70">
            <div className="pr-4">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider bg-slate-800 text-slate-300 border border-slate-700/60">
                  {problem.category.replace("_", " ")}
                </span>
                {severityBadge(problem.avg_severity)}
                {problem.is_widespread_gap && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                    Widespread Market Gap
                  </span>
                )}
              </div>
              <h2 className="text-lg sm:text-xl font-semibold text-white tracking-tight leading-snug">
                {problem.problem}
              </h2>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer shrink-0"
              title="Close drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto px-6 py-6 space-y-8 divide-y divide-slate-800/60 text-sm">
            {/* Description & Metrics */}
            <div>
              <h4 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-2 font-medium">
                Problem Definition & Impact
              </h4>
              <p className="text-slate-300 leading-relaxed text-sm bg-slate-900/50 p-4 rounded-lg border border-slate-800/80">
                {problem.description}
              </p>

              {/* Metric badges */}
              <div className="grid grid-cols-3 gap-3 mt-4 text-center font-mono">
                <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800/80">
                  <div className="text-lg font-bold text-slate-100">{problem.review_count}</div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">
                    Verified Reviews
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800/80">
                  <div className="text-lg font-bold text-slate-100">{problem.product_count}</div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">
                    Products Affected
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800/80">
                  <div className="text-lg font-bold text-indigo-400">
                    {problem.product_prevalence_pct}%
                  </div>
                  <div className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">
                    Market Prevalence
                  </div>
                </div>
              </div>
            </div>

            {/* Verbatim Supporting Evidence Quotes */}
            <div className="pt-6">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-xs font-mono uppercase tracking-wider text-slate-400 font-medium">
                  Supporting Customer Evidence ({problem.supporting_reviews.length} Citations)
                </h4>
                <span className="text-[11px] font-mono text-emerald-400 flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Substrings Verified</span>
                </span>
              </div>

              <div className="space-y-4">
                {problem.supporting_reviews.map((rev) => {
                  const isExpanded = !!expandedReviews[rev.review_id];
                  return (
                    <div
                      key={rev.review_id}
                      className="bg-slate-900/60 border border-slate-800 rounded-lg p-4 transition-all"
                    >
                      {/* Product attribution */}
                      <div className="flex items-center justify-between text-xs text-slate-400 mb-2.5 pb-2 border-b border-slate-800/60">
                        <div className="flex items-center gap-1.5 truncate max-w-[70%]">
                          <span className="text-slate-500 font-mono text-[10px]">Product:</span>
                          <span className="text-slate-300 font-medium truncate" title={rev.product_title}>
                            {rev.product_title}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {rev.rating !== null && rev.rating !== undefined && (
                            <span className="inline-flex items-center gap-0.5 font-mono text-amber-400 text-[11px]">
                              <span>{rev.rating}</span>
                              <Star className="w-2.5 h-2.5 fill-amber-400" />
                            </span>
                          )}
                          {rev.url && (
                            <a
                              href={rev.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-slate-400 hover:text-indigo-400 transition-colors"
                              title="View Amazon review source"
                            >
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>
                      </div>

                      {/* Verbatim Quote Highlight */}
                      {rev.evidence_quote ? (
                        <div className="p-2.5 rounded bg-amber-500/5 border-l-2 border-amber-500/80 mb-2">
                          <div className="flex items-start gap-2">
                            <Quote className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5 opacity-80" />
                            <span className="text-xs font-medium text-amber-200/90 italic leading-relaxed">
                              "{rev.evidence_quote}"
                            </span>
                          </div>
                        </div>
                      ) : null}

                      {/* Full Review Text Snippet */}
                      <div className="text-xs text-slate-400 leading-relaxed font-sans mt-2">
                        {isExpanded ? (
                          rev.original_text
                        ) : (
                          <span>
                            {rev.original_text.slice(0, 160)}
                            {rev.original_text.length > 160 ? "..." : ""}
                          </span>
                        )}
                      </div>

                      {rev.original_text.length > 160 && (
                        <button
                          onClick={() => toggleExpand(rev.review_id)}
                          className="mt-2 text-[11px] font-mono text-indigo-400 hover:text-indigo-300 flex items-center gap-1 cursor-pointer"
                        >
                          {isExpanded ? (
                            <>
                              <span>Show less</span>
                              <ChevronUp className="w-3 h-3" />
                            </>
                          ) : (
                            <>
                              <span>Show full review ({rev.original_text.length} chars)</span>
                              <ChevronDown className="w-3 h-3" />
                            </>
                          )}
                        </button>
                      )}

                      {/* Verifiable SerpAPI Citation link */}
                      {rev.citation?.serpapi_json_url && (
                        <div className="mt-2.5 pt-2 border-t border-slate-800/40 text-[10px] font-mono text-slate-500 flex items-center justify-between">
                          <span>SerpAPI engine: {rev.citation.engine || "amazon_product"}</span>
                          <a
                            href={rev.citation.serpapi_json_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-400 hover:text-indigo-400 underline"
                          >
                            Raw SerpAPI JSON
                          </a>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Affected Products Section */}
            <div className="pt-6">
              <h4 className="text-xs font-mono uppercase tracking-wider text-slate-400 mb-3 font-medium">
                Affected Competitor Products ({problem.supporting_products.length})
              </h4>
              <ul className="space-y-2">
                {problem.supporting_products.map((pid) => {
                  const detail = productMap?.[pid];
                  return (
                    <li
                      key={pid}
                      className="p-3 rounded-lg bg-slate-900/40 border border-slate-800/80 flex items-center justify-between text-xs"
                    >
                      <div className="truncate mr-3">
                        <span className="text-slate-200 font-medium truncate block">
                          {detail?.title || pid}
                        </span>
                        <span className="text-[10px] font-mono text-slate-500">ID: {pid}</span>
                      </div>
                      {detail?.url && (
                        <a
                          href={detail.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-slate-400 hover:text-indigo-400 shrink-0"
                          title="Open listing"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>

            {/* Counter-Evidence (Unaffected Products) */}
            <div className="pt-6">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <h4 className="text-xs font-mono uppercase tracking-wider text-slate-300 font-medium">
                  Counter-Evidence: Unaffected Competitors ({problem.unaffected_products.length})
                </h4>
              </div>
              <p className="text-xs text-slate-400 mb-3 leading-relaxed">
                In our analyzed competitor set, these products did <span className="text-slate-200 font-medium">not</span> exhibit
                this specific complaint in customer reviews. This indicates that this defect is avoidable.
              </p>

              {problem.unaffected_products.length > 0 ? (
                <ul className="space-y-2">
                  {problem.unaffected_products.map((pid) => {
                    const detail = productMap?.[pid];
                    return (
                      <li
                        key={pid}
                        className="p-3 rounded-lg bg-emerald-950/10 border border-emerald-900/30 flex items-center justify-between text-xs"
                      >
                        <div className="truncate mr-3">
                          <span className="text-slate-300 font-medium truncate block">
                            {detail?.title || pid}
                          </span>
                          <span className="text-[10px] font-mono text-slate-500">ID: {pid}</span>
                        </div>
                        {detail?.url && (
                          <a
                            href={detail.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-slate-400 hover:text-emerald-400 shrink-0"
                            title="Open listing"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className="p-3 rounded-lg bg-slate-900/30 border border-slate-800 text-xs text-slate-500 font-mono">
                  All analyzed products in this batch suffered from this friction.
                </div>
              )}
            </div>

            {/* Limitations & Caveats */}
            <div className="pt-6 pb-2">
              <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800/80 text-xs text-slate-400 space-y-2">
                <div className="flex items-center gap-2 font-mono text-slate-300 font-semibold text-[11px] uppercase tracking-wider">
                  <Info className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Evidence Limitations & Boundaries</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Findings are bounded by the top {problem.product_count + problem.unaffected_products.length} sampled listings
                  and recent verified customer reviews. This analysis reflects observed buyer sentiment, not absolute engineering lab tests.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
