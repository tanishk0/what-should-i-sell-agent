import React from "react";
import { Check, Loader2, AlertCircle, RefreshCw, ArrowLeft } from "lucide-react";
import type { ResearchJob, ResearchStage } from "../types";

interface ProgressScreenProps {
  job: ResearchJob;
  onRetry: () => void;
  onCancel: () => void;
}

interface StageDefinition {
  id: ResearchStage;
  label: string;
  description: string;
}

const STAGES: StageDefinition[] = [
  {
    id: "finding_competitors",
    label: "Finding competing products",
    description: "Scraping marketplace listings and filtering relevant competitors",
  },
  {
    id: "collecting_reviews",
    label: "Collecting customer reviews",
    description: "Fetching verified customer reviews across top ranked products",
  },
  {
    id: "analyzing_complaints",
    label: "Analyzing complaints",
    description: "Classifying review texts for buyer friction and quality defects",
  },
  {
    id: "validating_evidence",
    label: "Validating evidence",
    description: "Grouping problem clusters and verifying verbatim review quotations",
  },
  {
    id: "preparing_report",
    label: "Preparing the report",
    description: "Synthesizing cross-competitor metrics, counter-evidence, and citations",
  },
];

const STAGE_ORDER: ResearchStage[] = [
  "finding_competitors",
  "collecting_reviews",
  "analyzing_complaints",
  "validating_evidence",
  "preparing_report",
  "done",
];

export const ProgressScreen: React.FC<ProgressScreenProps> = ({
  job,
  onRetry,
  onCancel,
}) => {
  const currentStageIndex = STAGE_ORDER.indexOf(job.stage);
  const isFailed = job.status === "failed";

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-16 sm:py-24">
      {/* Header Context */}
      <div className="mb-10 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300 mb-4">
          <span className="text-slate-500">Target Category:</span>
          <span className="font-semibold text-slate-100">"{job.query}"</span>
          <span className="text-slate-600">•</span>
          <span className="text-indigo-400 uppercase">{job.market}</span>
        </div>

        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight text-white mb-2">
          {isFailed ? "Research encountered an error" : "Synthesizing market intelligence"}
        </h2>
        <p className="text-sm text-slate-400">
          {isFailed
            ? "The pipeline was interrupted. Review the error details below."
            : "Processing real-time competitor data. This typically takes 20–45 seconds."}
        </p>
      </div>

      {/* Main Status Container */}
      <div className="bg-[#11131a] border border-slate-800 rounded-xl p-6 sm:p-8 shadow-xl">
        {/* Progress percentage bar */}
        {!isFailed && (
          <div className="mb-8">
            <div className="flex items-center justify-between text-xs font-mono text-slate-400 mb-2">
              <span className="flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                <span className="font-sans text-slate-300 font-medium">Pipeline running</span>
              </span>
              <span>{Math.min(job.progress, 98)}%</span>
            </div>
            <div className="w-full h-1.5 bg-slate-800/80 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full transition-all duration-500 ease-out"
                style={{ width: `${Math.min(job.progress, 98)}%` }}
              />
            </div>
          </div>
        )}

        {/* Real Stages List */}
        <div className="space-y-4">
          {STAGES.map((s, index) => {
            const isCompleted = currentStageIndex > index || job.stage === "done";
            const isCurrent = !isCompleted && job.stage === s.id && !isFailed;

            return (
              <div
                key={s.id}
                className={`flex items-start gap-4 p-3.5 rounded-lg border transition-all ${
                  isCurrent
                    ? "bg-slate-900/80 border-indigo-500/40 shadow-sm"
                    : isCompleted
                    ? "bg-transparent border-slate-800/40 opacity-80"
                    : "bg-transparent border-transparent opacity-40"
                }`}
              >
                {/* Stage Icon */}
                <div className="mt-0.5 shrink-0">
                  {isCompleted ? (
                    <div className="w-5 h-5 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                      <Check className="w-3 h-3 stroke-[3]" />
                    </div>
                  ) : isCurrent ? (
                    <div className="w-5 h-5 rounded-full bg-indigo-500/20 border border-indigo-500/50 flex items-center justify-center text-indigo-400">
                      <Loader2 className="w-3 h-3 animate-spin" />
                    </div>
                  ) : (
                    <div className="w-5 h-5 rounded-full border border-slate-700 bg-slate-900/40 flex items-center justify-center text-[10px] font-mono text-slate-500">
                      {index + 1}
                    </div>
                  )}
                </div>

                {/* Stage Details */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span
                      className={`text-sm font-medium ${
                        isCurrent
                          ? "text-slate-100 font-semibold"
                          : isCompleted
                          ? "text-slate-300"
                          : "text-slate-500"
                      }`}
                    >
                      {s.label}
                    </span>
                    {isCurrent && (
                      <span className="text-[11px] font-mono text-indigo-400 animate-pulse">
                        In progress
                      </span>
                    )}
                    {isCompleted && (
                      <span className="text-[11px] font-mono text-emerald-400/90">
                        Complete
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">{s.description}</p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Live Backend Activity Message */}
        {job.message && !isFailed && (
          <div className="mt-8 pt-5 border-t border-slate-800/60 flex items-center justify-between text-xs font-mono text-slate-400 bg-slate-950/40 px-3.5 py-2.5 rounded-lg border border-slate-800/80">
            <span className="text-slate-500 shrink-0 mr-2">Backend status:</span>
            <span className="text-slate-300 truncate text-right font-sans">{job.message}</span>
          </div>
        )}

        {/* Failure State */}
        {isFailed && (
          <div className="mt-6 p-4 rounded-lg bg-red-950/20 border border-red-900/40 text-red-300 text-xs flex items-start gap-3">
            <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <span className="font-semibold block mb-1">Execution Failure:</span>
              <p className="font-mono text-[11px] text-red-300/80 break-words leading-relaxed">
                {job.error || job.message || "An unknown error occurred during pipeline execution."}
              </p>
            </div>
          </div>
        )}

        {/* Action Controls */}
        <div className="mt-8 pt-6 border-t border-slate-800/60 flex items-center justify-between">
          <button
            onClick={onCancel}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Cancel and return</span>
          </button>

          {isFailed && (
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors shadow-sm cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Analysis</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
