import React, { useState, useEffect, useRef } from "react";
import { Navbar } from "./components/Navbar";
import { SearchScreen } from "./components/SearchScreen";
import { ProgressScreen } from "./components/ProgressScreen";
import { ReportScreen } from "./components/ReportScreen";
import { fetchMarkets, startResearch, getResearchJob } from "./api";
import type { MarketOption, ResearchJob } from "./types";

export const App: React.FC = () => {
  const [markets, setMarkets] = useState<MarketOption[]>([]);
  const [selectedMarket, setSelectedMarket] = useState<string>("in");
  const [currentJob, setCurrentJob] = useState<ResearchJob | null>(null);
  const [view, setView] = useState<"search" | "progress" | "report">("search");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [lastQuery, setLastQuery] = useState<string>("");

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetchMarkets().then((mList) => {
      setMarkets(mList);
      if (mList.some((m) => m.code === "in")) {
        setSelectedMarket("in");
      } else if (mList.length > 0) {
        setSelectedMarket(mList[0].code);
      }
    });

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const handleStartSearch = async (query: string, market: string) => {
    stopPolling();
    setIsLoading(true);
    setLastQuery(query);

    // Initial placeholder job while server initializes
    const placeholderJob: ResearchJob = {
      id: "init",
      query,
      market,
      status: "queued",
      stage: "finding_competitors",
      progress: 5,
      message: `Connecting to Amazon ${market.toUpperCase()}...`,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    setCurrentJob(placeholderJob);
    setView("progress");

    try {
      const res = await startResearch(query, market);
      const jobId = res.job_id;

      // Start polling
      pollRef.current = setInterval(async () => {
        try {
          const jobData = await getResearchJob(jobId);
          setCurrentJob(jobData);

          if (jobData.status === "completed") {
            stopPolling();
            setIsLoading(false);
            setView("report");
          } else if (jobData.status === "failed") {
            stopPolling();
            setIsLoading(false);
          }
        } catch (err) {
          console.error("Polling error:", err);
        }
      }, 1500);
    } catch (err: any) {
      setIsLoading(false);
      setCurrentJob({
        id: "err",
        query,
        market,
        status: "failed",
        stage: "failed",
        progress: 0,
        message: err.message || "Failed to start market analysis",
        error: err.message || "Network or server failure",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    }
  };

  const handleRetry = () => {
    if (lastQuery) {
      handleStartSearch(lastQuery, selectedMarket);
    }
  };

  const handleReset = () => {
    stopPolling();
    setIsLoading(false);
    setView("search");
  };

  return (
    <div className="min-h-screen bg-[#090a0f] text-slate-100 flex flex-col font-sans selection:bg-indigo-500/30 selection:text-indigo-200">
      <Navbar onReset={handleReset} showReset={view !== "search"} />

      <main className="flex-1">
        {view === "search" && (
          <SearchScreen
            markets={markets}
            selectedMarket={selectedMarket}
            onMarketChange={setSelectedMarket}
            onSearch={handleStartSearch}
            isLoading={isLoading}
          />
        )}

        {view === "progress" && currentJob && (
          <ProgressScreen
            job={currentJob}
            onRetry={handleRetry}
            onCancel={handleReset}
          />
        )}

        {view === "report" && currentJob?.report && (
          <ReportScreen
            report={currentJob.report}
            priceRange={currentJob.price_range}
            productMap={currentJob.product_details}
            onNewSearch={handleReset}
          />
        )}
      </main>
    </div>
  );
};

export default App;
