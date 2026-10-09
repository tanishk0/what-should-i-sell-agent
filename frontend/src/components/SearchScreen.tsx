import React, { useState } from "react";
import { Search, Globe, ArrowRight, ShieldCheck, Database, Layers } from "lucide-react";
import type { MarketOption } from "../types";

interface SearchScreenProps {
  markets: MarketOption[];
  selectedMarket: string;
  onMarketChange: (m: string) => void;
  onSearch: (query: string, market: string) => void;
  isLoading: boolean;
}

export const SearchScreen: React.FC<SearchScreenProps> = ({
  markets,
  selectedMarket,
  onMarketChange,
  onSearch,
  isLoading,
}) => {
  const [query, setQuery] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim() && !isLoading) {
      onSearch(query.trim(), selectedMarket);
    }
  };

  const exampleSearches = [
    "men boxers",
    "lunch boxes",
    "yoga mats",
    "iphone cases",
    "sunglasses",
  ];

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col justify-between max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-16 sm:py-24">
      <div className="flex-1 flex flex-col items-center justify-center text-center max-w-3xl mx-auto">
        {/* Subtle pill tag */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs text-slate-300 font-medium mb-8">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
          <span>Amazon Market-Gap Intelligence</span>
        </div>

        {/* Headline */}
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight text-white mb-6 leading-[1.1]">
          Find what customers hate about existing products.
        </h1>

        {/* Supporting text */}
        <p className="text-base sm:text-lg text-slate-400 max-w-2xl mb-12 leading-relaxed">
          MarketGap analyzes customer reviews across competing Amazon products to uncover
          systemic defects, recurring friction, and verified buyer complaints.
        </p>

        {/* Search & Marketplace Form */}
        <form onSubmit={handleSubmit} className="w-full max-w-2xl">
          <div className="bg-[#12141d] p-2 rounded-xl border border-slate-800 shadow-2xl shadow-black/60 focus-within:border-slate-700 transition-all flex flex-col sm:flex-row gap-2">
            {/* Input field */}
            <div className="relative flex-1 flex items-center">
              <Search className="w-5 h-5 text-slate-500 absolute left-3.5 pointer-events-none" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Enter product category or niche, e.g. men boxers..."
                className="w-full pl-11 pr-4 py-3 bg-transparent text-slate-100 placeholder:text-slate-500 text-sm sm:text-base focus:outline-none"
                disabled={isLoading}
                autoFocus
              />
            </div>

            {/* Marketplace dropdown */}
            <div className="flex items-center gap-2 px-2 border-t sm:border-t-0 sm:border-l border-slate-800/80 pt-2 sm:pt-0">
              <div className="relative flex items-center">
                <Globe className="w-4 h-4 text-slate-500 absolute left-2.5 pointer-events-none" />
                <select
                  value={selectedMarket}
                  onChange={(e) => onMarketChange(e.target.value)}
                  className="pl-8 pr-7 py-2 bg-slate-900/90 hover:bg-slate-800 text-xs font-medium text-slate-300 rounded-lg border border-slate-800 focus:outline-none cursor-pointer transition-colors appearance-none"
                  disabled={isLoading}
                >
                  {markets.map((m) => (
                    <option key={m.code} value={m.code}>
                      {m.code.toUpperCase()} ({m.domain})
                    </option>
                  ))}
                </select>
              </div>

              {/* Submit CTA */}
              <button
                type="submit"
                disabled={!query.trim() || isLoading}
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm shadow-indigo-500/20 active:scale-[0.98] shrink-0"
              >
                <span>Analyze market</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Example searches */}
          <div className="flex flex-wrap items-center justify-center gap-2 mt-5 text-xs text-slate-400">
            <span className="text-slate-500 font-medium">Try searching:</span>
            {exampleSearches.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setQuery(example);
                  onSearch(example, selectedMarket);
                }}
                className="px-2.5 py-1 rounded-md bg-slate-900/80 hover:bg-slate-800 border border-slate-800 text-slate-300 hover:text-white transition-colors cursor-pointer"
              >
                {example}
              </button>
            ))}
          </div>
        </form>

        {/* Feature pillars */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-3xl mt-20 pt-10 border-t border-slate-800/60 text-left">
          <div className="p-4 rounded-lg bg-[#0e1017] border border-slate-800/80">
            <div className="w-7 h-7 rounded-md bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-3">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <h3 className="text-sm font-semibold text-slate-200 mb-1">Verbatim Quotes</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Every complaint is matched word-for-word against real customer reviews. Zero synthetic hallucinations.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-[#0e1017] border border-slate-800/80">
            <div className="w-7 h-7 rounded-md bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-3">
              <Layers className="w-4 h-4" />
            </div>
            <h3 className="text-sm font-semibold text-slate-200 mb-1">Cross-Competitor Prevalence</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Distinguishes between isolated product defects and widespread market gaps affecting multiple brands.
            </p>
          </div>

          <div className="p-4 rounded-lg bg-[#0e1017] border border-slate-800/80">
            <div className="w-7 h-7 rounded-md bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-3">
              <Database className="w-4 h-4" />
            </div>
            <h3 className="text-sm font-semibold text-slate-200 mb-1">Counter-Evidence Visible</h3>
            <p className="text-xs text-slate-400 leading-relaxed">
              Highlights unaffected competitors and evidence boundaries so you make informed, risk-aware decisions.
            </p>
          </div>
        </div>
      </div>

      {/* Footer disclaimer */}
      <div className="text-center pt-10 text-[11px] text-slate-600 font-mono">
        MarketGap identifies verified market problems. It does not recommend speculative product designs or tell sellers what to build.
      </div>
    </div>
  );
};
