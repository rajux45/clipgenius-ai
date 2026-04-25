"use client";

import useSWR from "swr";
import toast from "react-hot-toast";
import { swrFetcher, api } from "@/lib/api";
import type { ScheduledPost } from "@/lib/types";
import { format } from "date-fns";
import { statusColor } from "@/lib/utils";
import { Trash2, ExternalLink } from "lucide-react";

export default function SchedulePage() {
  const { data, mutate, isLoading } = useSWR<ScheduledPost[]>("/api/v1/posts", swrFetcher, {
    refreshInterval: 10000,
  });

  async function cancel(id: string) {
    if (!confirm("Cancel this scheduled post?")) return;
    try {
      await api(`/api/v1/posts/${id}`, { method: "DELETE" });
      toast.success("Canceled");
      mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Cancel failed");
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-6">Scheduled posts</h1>
      {isLoading && <p className="text-muted">Loading…</p>}
      {!isLoading && (!data || data.length === 0) && (
        <div className="card text-center py-10 text-muted">No scheduled posts yet.</div>
      )}
      {data && data.length > 0 && (
        <div className="space-y-3">
          {data.map((p) => (
            <div key={p.id} className="card flex items-center justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="badge bg-panel2 text-muted">{p.platform}</span>
                  <span className="badge bg-panel2 text-muted">{p.language}</span>
                  <span className={`badge ${statusColor(p.status)}`}>{p.status}</span>
                </div>
                <p className="mt-2 font-medium truncate">{p.title || "(no title)"}</p>
                <p className="mt-1 text-xs text-muted">
                  {format(new Date(p.scheduled_at), "PPpp")}
                  {p.published_at && ` · published ${format(new Date(p.published_at), "PPpp")}`}
                </p>
                {p.analytics && (
                  <p className="mt-1 text-xs text-muted">
                    {Object.entries(p.analytics)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(" · ")}
                  </p>
                )}
                {p.error_message && (
                  <p className="mt-1 text-xs text-danger">{p.error_message}</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {p.external_url && (
                  <a
                    className="btn-ghost text-xs"
                    href={p.external_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ExternalLink size={14} /> Open
                  </a>
                )}
                {(p.status === "scheduled" || p.status === "failed") && (
                  <button className="btn-ghost text-xs text-danger" onClick={() => cancel(p.id)}>
                    <Trash2 size={14} /> Cancel
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
