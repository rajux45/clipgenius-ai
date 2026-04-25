"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Home, Upload, Calendar, Settings, LogOut, Video } from "lucide-react";
import { setToken } from "@/lib/api";
import { Logo } from "./Logo";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: Home },
  { href: "/dashboard/upload", label: "New Project", icon: Upload },
  { href: "/dashboard/projects", label: "Projects", icon: Video },
  { href: "/dashboard/schedule", label: "Schedule", icon: Calendar },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  return (
    <aside className="hidden lg:flex w-64 flex-col border-r border-border bg-panel/40 backdrop-blur p-4 sticky top-0 h-screen">
      <div className="px-2 py-3">
        <Logo />
      </div>
      <nav className="flex-1 mt-4 space-y-1">
        {NAV.map((item) => {
          const active =
            item.href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${
                active ? "bg-panel2 text-white" : "text-muted hover:bg-panel2/60 hover:text-white"
              }`}
            >
              <Icon size={16} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <button
        onClick={() => {
          setToken(null);
          router.push("/login");
        }}
        className="mt-auto flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-muted hover:bg-panel2/60 hover:text-white"
      >
        <LogOut size={16} />
        Sign out
      </button>
    </aside>
  );
}
