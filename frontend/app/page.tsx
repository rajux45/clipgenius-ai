import Link from "next/link";
import { ArrowRight, Mic2, Scissors, Wand2, Globe, Calendar, BarChart3 } from "lucide-react";
import { Logo } from "@/components/Logo";

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between px-6 lg:px-12 py-5">
        <Logo />
        <nav className="flex items-center gap-3">
          <Link href="/login" className="btn-ghost">
            Sign in
          </Link>
          <Link href="/signup" className="btn-primary">
            Get started <ArrowRight size={16} />
          </Link>
        </nav>
      </header>

      <main className="px-6 lg:px-12">
        <section className="max-w-5xl mx-auto pt-12 pb-24 text-center">
          <span className="badge bg-accent/10 text-accent border border-accent/20">AI-native short-form pipeline</span>
          <h1 className="mt-5 text-4xl md:text-6xl font-semibold leading-[1.05] tracking-tight">
            Turn one long video into <br className="hidden md:block" />
            <span className="bg-gradient-to-r from-accent to-accent2 bg-clip-text text-transparent">
              ten viral shorts
            </span>{" "}
            — in any language.
          </h1>
          <p className="mt-6 text-lg text-muted max-w-2xl mx-auto">
            Drop a YouTube URL or upload a file. ClipGenius transcribes, finds the most viral
            moments, reframes vertically, dubs in 10+ languages and posts to YouTube Shorts and
            Instagram Reels on your schedule.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <Link href="/signup" className="btn-primary">
              Start for free <ArrowRight size={16} />
            </Link>
            <Link href="/login" className="btn-secondary">
              Sign in
            </Link>
          </div>
        </section>

        <section className="max-w-6xl mx-auto grid md:grid-cols-3 gap-4 pb-24">
          <Feature icon={Scissors} title="Smart clipping">
            We score every moment in the transcript on energy, keywords and pause patterns, then
            let GPT pick the strongest 5–10 clips with hooks.
          </Feature>
          <Feature icon={Wand2} title="Vertical reframing">
            Face-aware center crop converts horizontal video to 1080×1920 with smooth tracking,
            burned-in dynamic captions and keyword highlights.
          </Feature>
          <Feature icon={Globe} title="Multi-language dubbing">
            Translate the transcript and synthesise voice with neural TTS, then mux back over the
            video — one click, ten languages.
          </Feature>
          <Feature icon={Mic2} title="Hooks & metadata">
            Per-platform titles, descriptions and hashtags optimised for YouTube Shorts and
            Instagram Reels.
          </Feature>
          <Feature icon={Calendar} title="Auto-posting">
            Connect your accounts and schedule across platforms. We handle uploads via the
            official APIs.
          </Feature>
          <Feature icon={BarChart3} title="Analytics">
            Track views, likes and comments per clip across your connected accounts.
          </Feature>
        </section>

        <footer className="border-t border-border py-8 text-center text-sm text-muted">
          © {new Date().getFullYear()} ClipGenius AI. Built with FastAPI, Next.js, Whisper and FFmpeg.
        </footer>
      </main>
    </div>
  );
}

function Feature({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card hover:border-accent/40 transition">
      <div className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent">
        <Icon size={18} />
      </div>
      <h3 className="mt-3 text-lg font-medium">{title}</h3>
      <p className="mt-1 text-sm text-muted">{children}</p>
    </div>
  );
}
