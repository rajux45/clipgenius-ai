"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { swrFetcher, getToken, setToken } from "@/lib/api";
import type { User } from "@/lib/types";

export function useCurrentUser() {
  const token = typeof window !== "undefined" ? getToken() : null;
  const { data, error, isLoading, mutate } = useSWR<User>(token ? "/api/v1/auth/me" : null, swrFetcher, {
    shouldRetryOnError: false,
  });
  return { user: data, isLoading, error, mutate };
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, isLoading, error } = useCurrentUser();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isLoading) {
      if (error || !user) {
        setToken(null);
        router.replace("/login");
      } else {
        setReady(true);
      }
    }
  }, [isLoading, user, error, router]);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">Loading…</div>
    );
  }
  return <>{children}</>;
}
