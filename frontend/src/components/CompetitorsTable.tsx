import React, { useState } from "react";
import { ExternalLink, ArrowUpDown, Star, MessageSquare } from "lucide-react";
import type { CompetitorRow } from "../types";

interface CompetitorsTableProps {
  competitors: CompetitorRow[];
  currency: string;
}

type SortField = "rank" | "rating" | "complaints_count";
type SortDirection = "asc" | "desc";

export const CompetitorsTable: React.FC<CompetitorsTableProps> = ({ competitors }) => {
  const [sortField, setSortField] = useState<SortField>("complaints_count");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const sortedCompetitors = [...competitors].sort((a, b) => {
    let aVal: number = 0;
    let bVal: number = 0;

    if (sortField === "rank") {
      aVal = a.rank;
      bVal = b.rank;
    } else if (sortField === "complaints_count") {
      aVal = a.complaints_count;
      bVal = b.complaints_count;
    } else if (sortField === "rating") {
      aVal = parseFloat(a.rating) || 0;
      bVal = parseFloat(b.rating) || 0;
    }

    if (sortDir === "asc") return aVal - bVal;
    return bVal - aVal;
  });

  return (
    <div className="bg-[#11131a] border border-slate-800 rounded-xl overflow-hidden shadow-sm">
      <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">Competitor Benchmark</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Analyzed marketplace listings sorted by customer complaints and rank
          </p>
        </div>
        <span className="text-xs font-mono text-slate-400 bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-md">
          {competitors.length} Products Benchmark
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-800/80 bg-slate-900/40 text-slate-400 font-mono text-[11px] uppercase tracking-wider">
              <th className="py-3 px-4 w-12 text-center cursor-pointer hover:text-slate-200" onClick={() => handleSort("rank")}>
                <div className="flex items-center justify-center gap-1">
                  <span>#</span>
                  <ArrowUpDown className="w-2.5 h-2.5 opacity-60" />
                </div>
              </th>
              <th className="py-3 px-4 min-w-[280px]">Product Title</th>
              <th className="py-3 px-4 w-28 text-right">Price</th>
              <th className="py-3 px-4 w-24 text-center cursor-pointer hover:text-slate-200" onClick={() => handleSort("rating")}>
                <div className="flex items-center justify-center gap-1">
                  <span>Rating</span>
                  <ArrowUpDown className="w-2.5 h-2.5 opacity-60" />
                </div>
              </th>
              <th className="py-3 px-4 w-28 text-right">Reviews</th>
              <th className="py-3 px-4 w-32 text-center cursor-pointer hover:text-slate-200" onClick={() => handleSort("complaints_count")}>
                <div className="flex items-center justify-center gap-1">
                  <span>Complaints</span>
                  <ArrowUpDown className="w-2.5 h-2.5 opacity-60" />
                </div>
              </th>
              <th className="py-3 px-4 w-20 text-center">Listing</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {sortedCompetitors.map((c) => (
              <tr key={c.rank} className="hover:bg-slate-900/30 transition-colors group">
                <td className="py-3 px-4 text-center font-mono text-slate-500 font-medium">
                  {c.rank}
                </td>
                <td className="py-3 px-4">
                  <div className="font-medium text-slate-200 group-hover:text-white transition-colors line-clamp-1" title={c.title}>
                    {c.title}
                  </div>
                </td>
                <td className="py-3 px-4 text-right font-mono text-slate-300">
                  {c.price}
                </td>
                <td className="py-3 px-4 text-center">
                  {c.rating && c.rating !== "-" ? (
                    <span className="inline-flex items-center gap-1 text-amber-400 font-mono font-medium">
                      <span>{c.rating}</span>
                      <Star className="w-3 h-3 fill-amber-400 text-amber-400" />
                    </span>
                  ) : (
                    <span className="text-slate-600 font-mono">-</span>
                  )}
                </td>
                <td className="py-3 px-4 text-right font-mono text-slate-400">
                  {c.review_count || "-"}
                </td>
                <td className="py-3 px-4 text-center">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-mono text-[11px] font-medium ${
                      c.complaints_count > 0
                        ? "bg-red-500/10 text-red-400 border border-red-500/20"
                        : "bg-slate-800 text-slate-400 border border-slate-700/60"
                    }`}
                  >
                    <MessageSquare className="w-2.5 h-2.5" />
                    <span>{c.complaints_count}</span>
                  </span>
                </td>
                <td className="py-3 px-4 text-center">
                  {c.url ? (
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center justify-center w-7 h-7 rounded-md bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-indigo-400 border border-slate-800 transition-colors"
                      title="Open Amazon product page"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  ) : (
                    <span className="text-slate-600 font-mono text-[11px]">-</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
