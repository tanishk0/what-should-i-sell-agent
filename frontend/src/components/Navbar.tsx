import React from "react";
import { ShieldCheck, RefreshCw } from "lucide-react";

interface NavbarProps {
  onReset?: () => void;
  showReset?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({ onReset, showReset }) => {
  return (
    <header className="border-b border-slate-800/80 bg-[#0c0d14]/90 backdrop-blur-md sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={onReset}
            className="flex items-center gap-2.5 text-left group transition-opacity"
          >
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400 group-hover:border-indigo-500/50 transition-colors">
              <span className="font-mono font-bold text-sm tracking-tighter">MG</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-semibold tracking-tight text-slate-100">MarketGap</span>
                <span className="hidden sm:inline-flex text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border border-slate-700/80 bg-slate-800/50 text-slate-400">
                  Research Engine
                </span>
              </div>
            </div>
          </button>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-1.5 text-xs font-mono text-slate-400 bg-slate-900/60 border border-slate-800 px-2.5 py-1 rounded-md">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Verbatim Evidence Only</span>
          </div>

          {showReset && onReset && (
            <button
              onClick={onReset}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-slate-300 bg-slate-800/80 hover:bg-slate-700 hover:text-white border border-slate-700/60 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>New Analysis</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
};
