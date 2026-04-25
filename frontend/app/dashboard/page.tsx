"use client";

import Link from "next/link";
import useSWR from "swr";
import { swrFetcher } from "@/lib/api";
import type { Video } from "@/lib/types";
import { Plus, Video as VideoIcon } from "lucide-react";
import { fmtDuration, statusColor } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";

export default function DashboardHome() {
  const { data: videos, isLoading } = useSWR<Video[]>("/api/v1/videos", swrFetcher, {
    refreshInterval: 5000,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold">Your projects</h1>
          <p className="text-muted text-sm mt-1">
            Long-form videos you have repurposed into short-form clips.
          </p>
        </div>
        <Link href="/dashboard/upload" className="btn-primary">
          <Plus size={16} /> New project
        </Link>
      </div>

      {isLoading && <p className="text-muted">Loading…</p>}
      {!isLoading && (!videos || videos.length === 0) && (
        <div className="card text-center py-16">
          <VideoIcon className="mx-auto text-muted" size={32} />
          <h3 className="mt-3 text-lg font-medium">No projects yet</h3>
          <p className="text-muted text-sm mt-1">
            Drop a YouTube URL or upload a video to generate viral shorts.
          </p>
          <Link href="/dashboard/upload" className="btn-primary mt-5 inline-flex">
            <Plus size={16} /> Create your first project
          </Link>
        </div>
      )}
      {videos && videos.length > 0 && (
        <div className="grid md:grid-cols-2 gap-4">
          {videos.map((v) => (
            <Link
              key={v.id}
              href={`/dashboard/projects/${v.id}`}
              className="card hover:border-accent/40 transition"
            >
              <div className="flex items-start justify-between">
                <h3 className="font-medium line-clamp-2">{v.title}</h3>
                <span className={`badge ${statusColor(v.status)}`}>{v.status}</span>
              </div>
              <div className="mt-3 flex items-center gap-4 text-xs text-muted">
                <span>Duration: {fmtDuration(v.duration_seconds)}</span>
                <span>{v.clips_count ?? 0} clips</span>
                <span>{formatDistanceToNow(new Date(v.created_at))} ago</span>
              </div>
              {v.languages && v.languages.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {v.languages.map((l) => (
                    <span key={l} className="badge bg-panel2 text-muted">
                      {l}
                    </span>
                  ))}
                </div>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
