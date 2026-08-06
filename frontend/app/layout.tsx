import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Workflow Orchestrator",
  description: "Build, run, and inspect LLM workflows",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <header className="site-header">
            <Link href="/">Workflow Orchestrator</Link>
          </header>
          <main className="page">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
