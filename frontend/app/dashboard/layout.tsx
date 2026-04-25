import { AuthGuard } from "@/components/AuthGuard";
import { Sidebar } from "@/components/Sidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="min-h-screen flex">
        <Sidebar />
        <main className="flex-1 px-6 lg:px-10 py-8 max-w-6xl mx-auto w-full">{children}</main>
      </div>
    </AuthGuard>
  );
}
