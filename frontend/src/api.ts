import type { MarketOption, ResearchJob } from "./types";

const BASE_URL = "/api";

export async function fetchMarkets(): Promise<MarketOption[]> {
  try {
    const res = await fetch(`${BASE_URL}/markets`);
    if (!res.ok) throw new Error(`Failed to load markets (${res.status})`);
    return await res.json();
  } catch (err) {
    // Fallback default markets
    return [
      { code: "in", name: "Amazon India", domain: "amazon.in", currency: "INR" },
      { code: "us", name: "Amazon United States", domain: "amazon.com", currency: "USD" },
      { code: "uk", name: "Amazon United Kingdom", domain: "amazon.co.uk", currency: "GBP" },
      { code: "ca", name: "Amazon Canada", domain: "amazon.ca", currency: "CAD" },
      { code: "de", name: "Amazon Germany", domain: "amazon.de", currency: "EUR" },
    ];
  }
}

export async function startResearch(
  query: string,
  market: string = "in",
  limit: number = 15,
  reviewLimit: number = 5
): Promise<{ job_id: string; status: string; message: string }> {
  const res = await fetch(`${BASE_URL}/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      market,
      limit,
      review_limit: reviewLimit,
    }),
  });

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: "Failed to initiate research" }));
    throw new Error(errData.detail || `Server error (${res.status})`);
  }

  return await res.json();
}

export async function getResearchJob(jobId: string): Promise<ResearchJob> {
  const res = await fetch(`${BASE_URL}/research/${jobId}`);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: "Job not found" }));
    throw new Error(errData.detail || `Server error (${res.status})`);
  }
  return await res.json();
}
