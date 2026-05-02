"use client";

import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { swrFetcher, api } from "@/lib/api";
import type { Clip, Video } from "@/lib/types";
import { fmtDuration, statusColor } from "@/lib/utils";
import { ArrowLeft, RefreshCw, Trash2, Calendar, Download } from "lucide-react";
import Link from "next/link";
import toast from "react-hot-toast";
import { useState } from "react";
import ClipCard from "@/components/ClipCard";

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const { data: video, mutate: refetchVideo } = useSWR<Video>(
    id ? `/api/v1/videos/${id}` : null,
    swrFetcher,
    { refreshInterval: 5000 },
  );
  const { data: clips, mutate: refetchClips } = useSWR<Clip[]>(
    id ? `/api/v1/clips/by-video/${id}` : null,
    swrFetcher,
    { refreshInterval: 5000 },
  );
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);

  async function onDelete() {
    if (!confirm("Delete this project and all its clips?")) return;
    setDeleting(true);
    try {
      await api(`/api/v1/videos/${id}`, { method: "DELETE" });
      toast.success("Project deleted");
      router.push("/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  async function onExportZip() {
    // Hit the zip endpoint with the auth header and stream the response
    // into a Blob so the browser serves a download prompt. We can't use a
    // plain anchor tag because the endpoint requires a Bearer token.
    setExporting(true);
    const t = toast.loading("Building zip — this can take a bit for large projects");
    try {
      const { getToken } = await import("@/lib/api");
      const base = process.env.NEXT_PUBLIC_API_URL || "https://rah7809-clipgenius-api.hf.space";
      const res = await fetch(`${base.replace(/\/$/, "")}/api/v1/videos/${id}/export.zip`, {
        headers: {
          Authorization: `Bearer ${getToken() || ""}`,
        },
      });
      if (!res.ok) {
        throw new Error(`Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${video?.title || "clipgenius"}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Downloaded zip", { id: t });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed", { id: t });
    } finally {
      setExporting(false);
    }
  }

  if (!video) return <p className="text-muted">Loading…</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <Link href="/dashboard" className="btn-ghost text-sm">
          <ArrowLeft size={16} /> Back to projects
        </Link>
        <div className="flex gap-2">
          <button
            className="btn-secondary"
            onClick={() => {
              refetchVideo();
              refetchClips();
            }}
          >
            <RefreshCw size={16} /> Refresh
          </button>
          <button
            className="btn-secondary"
            onClick={onExportZip}
            disabled={exporting || !clips || clips.length === 0}
            title={!clips || clips.length === 0 ? "No clips yet" : "Download all clips + SRT subtitles as a zip"}
          >
            <Download size={16} /> {exporting ? "Preparing…" : "Download all"}
          </button>
          <button className="btn-secondary text-danger" onClick={onDelete} disabled={deleting}>
            <Trash2 size={16} /> Delete
          </button>
        </div>
      </div>

      <div className="card mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold">{video.title}</h1>
            <div className="mt-2 flex items-center gap-3 text-xs text-muted">
              <span>Duration: {fmtDuration(video.duration_seconds)}</span>
              <span>Source: {video.source_type}</span>
              {video.languages?.map((l) => (
                <span key={l} className="badge bg-panel2">
                  {l}
                </span>
              ))}
            </div>
          </div>
          <span className={`badge ${statusColor(video.status)}`}>{video.status}</span>
        </div>
        {video.error_message && (
          <p className="mt-3 text-sm text-danger">{video.error_message}</p>
        )}
        {video.status !== "completed" && video.status !== "failed" && (
          <p className="mt-3 text-sm text-muted">
            Processing your video — this can take a few minutes for the first clips.
          </p>
        )}
      </div>

      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-medium">Generated clips</h2>
        <Link href="/dashboard/schedule" className="btn-ghost text-sm">
          <Calendar size={16} /> View schedule
        </Link>
      </div>

      {(!clips || clips.length === 0) && (
        <div className="card text-center py-10 text-muted">
          {video.status === "completed" ? "No clips were generated." : "Clips will appear here as they finish rendering…"}
        </div>
      )}

      {clips && clips.length > 0 && (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clips.map((c) => (
            <ClipCard key={c.id} clip={c} videoLanguages={video.languages || ["en"]} videoPlatforms={video.platforms || []} onUpdated={() => refetchClips()} />
          ))}
        </div>
      )}
    </div>
  );
}
