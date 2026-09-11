import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIOS — AI Operating System",
  description: "Platform AI yang menempel pada sistem Anda. Client system stays, AIOS adapts.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body className="antialiased">{children}</body>
    </html>
  );
}
