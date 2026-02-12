import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AECAI - Automated Lighting Fixture Takeoff",
  description:
    "Upload electrical drawing PDFs and get automated lighting fixture counts using computer vision.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="min-h-screen flex flex-col">
          <header className="border-b border-gray-800 bg-gray-950">
            <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
              <a href="/" className="flex items-center gap-3">
                <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center font-bold text-sm">
                  AI
                </div>
                <span className="text-lg font-semibold tracking-tight">
                  AECAI
                </span>
              </a>
              <span className="text-xs text-gray-500">
                Automated Lighting Fixture Takeoff
              </span>
            </div>
          </header>
          <main className="flex-1">{children}</main>
          <footer className="border-t border-gray-800 py-4">
            <div className="max-w-6xl mx-auto px-6 text-center text-xs text-gray-600">
              AECAI &mdash; Computer vision powered fixture counting for
              electrical engineers
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
