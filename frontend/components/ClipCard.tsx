"use client";

import { useState } from "react";
import toast from "react-hot-toast";
import { api } from "@/lib/api";
import type { Clip, Platform } from "@/lib/types";
import { fmtDuration, statusColor } from "@/lib/utils";
import { Calendar, Edit3, Save, X, Youtube, Instagram } from "lucide-react";

export default function ClipCard({
  clip,
  videoLanguages,
  videoPlatforms,
  onUpdated,
}: {
  clip: Clip;
  videoLanguages: string[];
  videoPlatforms: string[];
  onUpdated: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(clip.title);
  const [hook, setHook] = useState(clip.hook || "");
  const [scheduling, setScheduling] = useState<Platform | null>(null);
  const [language, setLanguage] = useState(videoLanguages[0] || "en");
  const [scheduledAt, setScheduledAt] = useState("");
  const [saving, setSaving] = useState(false);

  const videoUrl = clip.dubs?.[language]?.url || clip.dubs?.[language]?.s3_key || clip.s3_key;

  async function save() {
    setSaving(true);
    try {
      await api(`/api/v1/clips/${clip.id}`, {
        method: "PATCH",
        json: { title, hook },
      });
      toast.success("Saved");
      setEditing(false);
      onUpdated();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function schedule(platform: Platform) {
    if (!scheduledAt) return toast.error("Pick a date/time");
    try {
      await api("/api/v1/posts", {
        method: "POST",
        json: {
          clip_id: clip.id,
          platform,
          language,
          scheduled_at: new Date(scheduledAt).toISOString(),
        },
      });
      toast.success(`Scheduled for ${platform}`);
      setScheduling(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Schedule failed");
    }
  }

  return (
    <div className="card flex flex-col gap-3">
      <div className="aspect-[9/16] bg-bg rounded-lg overflow-hidden border border-border relative">
        {videoUrl ? (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video src={videoUrl} controls className="w-full h-full object-cover" preload="metadata" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-muted text-xs">
            {clip.status}
          </div>
        )}
        <span className={`absolute top-2 right-2 badge ${statusColor(clip.status)}`}>
          {clip.status}
        </span>
      </div>

      {!editing ? (
        <>
          <div>
            <h3 className="font-medium line-clamp-2">{clip.title}</h3>
            {clip.hook && <p className="text-sm text-muted line-clamp-2 mt-1">{clip.hook}</p>}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted">
            <span>{fmtDuration(clip.duration_seconds)}</span>
            <span>Score {(clip.score * 100).toFixed(0)}</span>
          </div>
        </>
      ) : (
        <>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" />
          <textarea
            className="input min-h-[80px]"
            value={hook}
            onChange={(e) => setHook(e.target.value)}
            placeholder="Hook"
          />
        </>
      )}

      {videoLanguages.length > 1 && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted">Lang</span>
          <select
            className="input py-1 text-xs"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            {videoLanguages.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        {!editing ? (
          <button className="btn-secondary text-xs" onClick={() => setEditing(true)}>
            <Edit3 size={14} /> Edit
          </button>
        ) : (
          <>
            <button className="btn-primary text-xs" onClick={save} disabled={saving}>
              <Save size={14} /> Save
            </button>
            <button className="btn-ghost text-xs" onClick={() => setEditing(false)}>
              <X size={14} /> Cancel
            </button>
          </>
        )}
        {videoPlatforms.includes("youtube") && (
          <button
            className="btn-secondary text-xs"
            onClick={() => setScheduling(scheduling === "youtube" ? null : "youtube")}
            disabled={clip.status !== "ready"}
          >
            <Youtube size={14} /> YouTube
          </button>
        )}
        {videoPlatforms.includes("instagram") && (
          <button
            className="btn-secondary text-xs"
            onClick={() => setScheduling(scheduling === "instagram" ? null : "instagram")}
            disabled={clip.status !== "ready"}
          >
            <Instagram size={14} /> Instagram
          </button>
        )}
      </div>

      {scheduling && (
        <div className="border-t border-border pt-3 mt-1 space-y-2">
          <label className="text-xs text-muted">Schedule {scheduling} post</label>
          <input
            type="datetime-local"
            className="input text-xs"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
          />
          <button className="btn-primary text-xs w-full" onClick={() => schedule(scheduling)}>
            <Calendar size={14} /> Schedule
          </button>
        </div>
      )}
    </div>
  );
}
