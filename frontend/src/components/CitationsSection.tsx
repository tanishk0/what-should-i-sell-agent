import React from "react";
import { ExternalLink, Database, AlertCircle, CheckCircle } from "lucide-react";
import type { CitationItem } from "../types";

interface CitationsSectionProps {
  citations: CitationItem[];
  hasInsufficientEvidence: boolean;
  totalCompetitorsAnalyzed: number;
  totalReviewsAnalyzed: number;
}

export const CitationsSection: React.FC<CitationsSectionProps> = ({
  citations,
  hasInsufficientEvidence,
  totalCompetitorsAnalyzed,
  totalReviewsAnalyzed,
}) => {
  return (
    <div className="space-y-6">
      {/* Evidence Limitations Banner */}
      <div className="bg-[#11131a] border border-slate-800 rounded-xl p-6 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shrink-0 mt-0.5">
            <Database className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">
              Evidence Boundaries & Limitations
            </h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              This report is programmatically assembled from real Amazon search pages and verified customer reviews.
              It does not infer buyer desires or invent speculative ideas. All metrics reflect the sampled cohort of{" "}
              <span className="text-slate-200 font-medium">{totalCompetitorsAnalyzed} competitor products</span> and{" "}
              <span className="text-slate-200 font-medium">{totalReviewsAnalyzed} analyzed reviews</span>.
            </p>

            {hasInsufficientEvidence ? (
              <div className="mt-4 p-3.5 rounded-lg bg-amber-950/20 border border-amber-900/40 text-amber-300 text-xs flex items-center gap-2.5">
                <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                <span>
                  <strong>Insufficient Evidence Flag:</strong> No recurring functional defects reached the statistical threshold
                  in this review sample. Consider widening the search or testing related category terms.
                </span>
              </div>
            ) : (
              <div className="mt-4 p-3 rounded-lg bg-slate-900/40 border border-slate-800 text-slate-400 text-xs flex items-center gap-2">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span>
                  Sufficient sample confidence: Recurring complaint clusters cross-validated across multiple competing products.
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Raw Verifiable Citations List */}
      <div className="bg-[#11131a] border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-100">Verifiable Source Citations</h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Direct links to raw SerpAPI search snapshots and Amazon product listings
            </p>
          </div>
          <span className="text-xs font-mono text-slate-400 bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-md">
            {citations.length} Citations
          </span>
        </div>

        <div className="divide-y divide-slate-800/50 max-h-96 overflow-y-auto">
          {citations.map((c, i) => (
            <div
              key={c.id || i}
              className="px-6 py-3 flex items-center justify-between text-xs hover:bg-slate-900/30 transition-colors"
            >
              <div className="flex items-center gap-3 truncate mr-4">
                <span className="font-mono text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800 border border-slate-700/60 text-slate-300 shrink-0">
                  {c.kind}
                </span>
                <span className="text-slate-300 truncate font-medium" title={c.label}>
                  {c.label}
                </span>
              </div>

              <a
                href={c.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-mono text-[11px] text-indigo-400 hover:text-indigo-300 shrink-0 transition-colors"
              >
                <span>View Source</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
