import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import NavBar from "@/components/NavBar";

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
        <AuthProvider>
          <div className="min-h-screen flex flex-col">
            <NavBar />
            <main className="flex-1">{children}</main>
            <footer className="border-t border-gray-800 py-4">
              <div className="max-w-6xl mx-auto px-6 text-center text-xs text-gray-600">
                AECAI &mdash; Computer vision powered fixture counting for
                electrical engineers
              </div>
            </footer>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
