"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import toast from "react-hot-toast";
import { api, getToken } from "@/lib/api";
import { SUPPORTED_LANGUAGES } from "@/lib/utils";
import { Upload, Link as LinkIcon, Sparkles } from "lucide-react";
import type { Video } from "@/lib/types";

const PLATFORMS = [
  { id: "youtube", label: "YouTube Shorts" },
  { id: "instagram", label: "Instagram Reels" },
];

export default function UploadPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"url" | "file">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [languages, setLanguages] = useState<string[]>(["en"]);
  const [platforms, setPlatforms] = useState<string[]>(["youtube"]);
  const [loading, setLoading] = useState(false);

  function toggle(arr: string[], v: string): string[] {
    return arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (mode === "url" && !url) return toast.error("Enter a YouTube URL");
    if (mode === "file" && !file) return toast.error("Choose a video file");
    if (languages.length === 0) return toast.error("Select at least one language");
    if (platforms.length === 0) return toast.error("Select at least one platform");

    setLoading(true);
    try {
      let video: Video;
      if (mode === "url") {
        video = await api<Video>("/api/v1/videos", {
          method: "POST",
          json: {
            source_url: url,
            title: title || undefined,
            languages,
            platforms,
          },
        });
      } else {
        const fd = new FormData();
        fd.append("file", file as File);
        if (title) fd.append("title", title);
        fd.append("languages", languages.join(","));
        fd.append("platforms", platforms.join(","));
        const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
        const res = await fetch(`${apiBase}/api/v1/videos/upload`, {
          method: "POST",
          headers: { Authorization: `Bearer ${getToken()}` },
          body: fd,
        });
        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || "Upload failed");
        }
        video = await res.json();
      }
      toast.success("Project queued — clips will appear in a few minutes.");
      router.push(`/dashboard/projects/${video.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to start project");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-8">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent">
          <Sparkles size={18} />
        </span>
        <div>
          <h1 className="text-2xl font-semibold">New project</h1>
          <p className="text-muted text-sm">
            Drop a YouTube URL or upload a video — we&apos;ll do the rest.
          </p>
        </div>
      </div>

      <form onSubmit={onSubmit} className="space-y-6 max-w-3xl">
        <div className="card">
          <div className="flex gap-2 mb-4">
            <button
              type="button"
              className={`btn ${mode === "url" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setMode("url")}
            >
              <LinkIcon size={16} /> YouTube URL
            </button>
            <button
              type="button"
              className={`btn ${mode === "file" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setMode("file")}
            >
              <Upload size={16} /> Upload file
            </button>
          </div>
          {mode === "url" ? (
            <div>
              <label className="text-xs text-muted">YouTube URL</label>
              <input
                className="input mt-1"
                placeholder="https://www.youtube.com/watch?v=..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
          ) : (
            <div>
              <label className="text-xs text-muted">Video file (mp4 / mov / mkv)</label>
              <input
                type="file"
                accept="video/*"
                className="input mt-1 file:mr-3 file:py-1 file:px-3 file:rounded-md file:border-0 file:bg-accent file:text-white file:cursor-pointer"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </div>
          )}
          <div className="mt-4">
            <label className="text-xs text-muted">Title (optional)</label>
            <input
              className="input mt-1"
              placeholder="Project title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
        </div>

        <div className="card">
          <label className="text-sm font-medium">Output languages</label>
          <p className="text-xs text-muted mt-1">
            English clips are always rendered. Additional languages will be dubbed.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {SUPPORTED_LANGUAGES.map((l) => (
              <button
                type="button"
                key={l.code}
                onClick={() => setLanguages(toggle(languages, l.code))}
                className={`badge px-3 py-1 cursor-pointer ${
                  languages.includes(l.code)
                    ? "bg-accent/20 text-accent border border-accent/40"
                    : "bg-panel2 text-muted border border-border"
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        <div className="card">
          <label className="text-sm font-medium">Target platforms</label>
          <div className="mt-3 flex flex-wrap gap-2">
            {PLATFORMS.map((p) => (
              <button
                type="button"
                key={p.id}
                onClick={() => setPlatforms(toggle(platforms, p.id))}
                className={`badge px-3 py-1 cursor-pointer ${
                  platforms.includes(p.id)
                    ? "bg-accent/20 text-accent border border-accent/40"
                    : "bg-panel2 text-muted border border-border"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <button className="btn-primary" disabled={loading}>
          {loading ? "Queuing…" : "Generate clips"}
        </button>
      </form>
    </div>
  );
}
