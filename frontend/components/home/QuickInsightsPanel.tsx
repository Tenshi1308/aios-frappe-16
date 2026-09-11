"use client";

import type { Branch } from "@/lib/branches";

// Memenuhi FR-04: Panel kiri placeholder (Quick-boxes) 
// Menampilkan metrik skeleton (Revenue, Growth, Active Issues, dll.)

export default function QuickInsightsPanel({ branch }: { branch: Branch }) {
  return (
    <aside className="quick-insights-panel">
      <div className="qi-header">
        <h3>{branch.name} Insights</h3>
        <span className="qi-badge">Live Syncing</span>
      </div>
      
      <div className="qi-content">
        <div className="qi-box">
          <div className="qi-box-title">Revenue (Est)</div>
          <div className="qi-skeleton qi-skeleton-large"></div>
          <div className="qi-skeleton qi-skeleton-small mt-2"></div>
        </div>
        
        <div className="qi-box">
          <div className="qi-box-title">Growth Trajectory</div>
          <div className="qi-skeleton qi-skeleton-chart"></div>
        </div>
        
        <div className="qi-box">
          <div className="qi-box-title">Active Alerts</div>
          <div className="qi-skeleton qi-skeleton-medium"></div>
          <div className="qi-skeleton qi-skeleton-medium mt-2"></div>
        </div>
      </div>
    </aside>
  );
}
