"use client";

import useSWR from "swr";
import toast from "react-hot-toast";
import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { swrFetcher, api } from "@/lib/api";
import type { IntegrationStatus } from "@/lib/types";
import { Youtube, Instagram, Plug, PlugZap } from "lucide-react";

export default function SettingsPage() {
  const params = useSearchParams();
  const { data, mutate } = useSWR<IntegrationStatus>("/api/v1/integrations/status", swrFetcher);

  useEffect(() => {
    const connected = params.get("connected");
    if (connected) toast.success(`${connected} connected`);
  }, [params]);

  async function connect(provider: "youtube" | "instagram") {
    try {
      const { auth_url } = await api<{ auth_url: string }>(
        `/api/v1/integrations/${provider}/connect`,
      );
      window.location.href = auth_url;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed");
    }
  }

  async function disconnect(provider: string) {
    if (!confirm(`Disconnect ${provider}?`)) return;
    try {
      await api(`/api/v1/integrations/${provider}`, { method: "DELETE" });
      toast.success("Disconnected");
      mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed");
    }
  }

  const yt = data?.["youtube"]?.connected;
  const ig = data?.["instagram"]?.connected;

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-6">Settings</h1>
      <h2 className="text-sm font-medium text-muted mb-3">Integrations</h2>

      <div className="space-y-3">
        <IntegrationRow
          provider="youtube"
          icon={<Youtube size={18} />}
          name="YouTube"
          desc="Upload Shorts via YouTube Data API"
          connected={!!yt}
          extra={data?.["youtube"]?.extra}
          onConnect={() => connect("youtube")}
          onDisconnect={() => disconnect("youtube")}
        />
        <IntegrationRow
          provider="instagram"
          icon={<Instagram size={18} />}
          name="Instagram"
          desc="Publish Reels via Meta Graph API (requires IG Business / Creator account)"
          connected={!!ig}
          extra={data?.["instagram"]?.extra}
          onConnect={() => connect("instagram")}
          onDisconnect={() => disconnect("instagram")}
        />
      </div>
    </div>
  );
}

function IntegrationRow({
  icon,
  name,
  desc,
  connected,
  extra,
  onConnect,
  onDisconnect,
}: {
  provider: string;
  icon: React.ReactNode;
  name: string;
  desc: string;
  connected: boolean;
  extra?: Record<string, unknown>;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  return (
    <div className="card flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-panel2 text-accent">
          {icon}
        </span>
        <div>
          <p className="font-medium flex items-center gap-2">
            {name}
            {connected && <span className="badge bg-success/15 text-success">connected</span>}
          </p>
          <p className="text-xs text-muted mt-0.5">{desc}</p>
          {connected && extra && (
            <p className="text-xs text-muted mt-1">
              {Object.entries(extra)
                .filter(([, v]) => v != null)
                .slice(0, 3)
                .map(([k, v]) => `${k}: ${String(v)}`)
                .join(" · ")}
            </p>
          )}
        </div>
      </div>
      {connected ? (
        <button className="btn-secondary" onClick={onDisconnect}>
          <Plug size={14} /> Disconnect
        </button>
      ) : (
        <button className="btn-primary" onClick={onConnect}>
          <PlugZap size={14} /> Connect
        </button>
      )}
    </div>
  );
}
