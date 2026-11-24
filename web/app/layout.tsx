import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Doc Processor",
  description: "Upload a document and follow its processing status.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>
        <header className="site-header">
          <h1>Doc Processor</h1>
          <p className="site-subtitle">
            Sube un documento y sigue su procesamiento en vivo.
          </p>
        </header>
        <main className="site-main">{children}</main>
      </body>
    </html>
  );
}
