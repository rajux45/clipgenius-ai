export type VideoStatus =
  | "pending"
  | "downloading"
  | "transcribing"
  | "segmenting"
  | "generating_clips"
  | "completed"
  | "failed";

export type ClipStatus = "pending" | "rendering" | "dubbing" | "ready" | "failed";

export type Platform = "youtube" | "instagram";

export interface Video {
  id: string;
  title: string;
  status: VideoStatus;
  source_type: string;
  source_url?: string | null;
  s3_key?: string | null;
  duration_seconds: number | null;
  languages: string[] | null;
  platforms: string[] | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  clips_count?: number;
}

export interface Clip {
  id: string;
  video_id: string;
  index: number;
  title: string;
  hook: string | null;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number | null;
  score: number;
  transcript: string | null;
  s3_key: string | null;
  thumbnail_s3_key: string | null;
  dubs: Record<string, { url?: string; s3_key?: string; transcript?: string; error?: string }> | null;
  metadata_json: Record<string, unknown> | null;
  status: ClipStatus;
  created_at: string;
}

export type PostStatus = "scheduled" | "publishing" | "published" | "failed" | "canceled";

export interface ScheduledPost {
  id: string;
  clip_id: string;
  platform: Platform;
  language: string;
  title: string | null;
  caption: string | null;
  hashtags: string[] | null;
  scheduled_at: string;
  published_at: string | null;
  status: PostStatus;
  external_id: string | null;
  external_url: string | null;
  error_message: string | null;
  analytics: Record<string, number> | null;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  created_at: string;
}

export interface IntegrationStatus {
  [provider: string]: {
    connected: boolean;
    scope?: string;
    extra?: Record<string, unknown>;
  };
}
