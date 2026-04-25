import type { Metadata } from "next";
import { Toaster } from "react-hot-toast";
import "./globals.css";

export const metadata: Metadata = {
  title: "ClipGenius AI — Repurpose long videos into viral shorts",
  description:
    "Turn YouTube videos into viral 9:16 shorts in any language. Auto-generate clips, dub them, schedule across YouTube Shorts and Instagram Reels.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: "#1a1a25",
              color: "#fff",
              border: "1px solid #26263a",
            },
          }}
        />
      </body>
    </html>
  );
}
