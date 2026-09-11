import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
const TITLE = "LexChiapas - Asistente legal de Chiapas";
const DESCRIPTION =
  "Chatbot que responde preguntas sobre leyes y reglamentos del Estado de Chiapas, citando la ley y el articulo.";

// Fase 9.8/A12: metadataBase + OpenGraph/Twitter para previews al compartir el
// enlace. Sin imagen OG a proposito (no se inventa un asset); si mas adelante
// se agrega un /public/og.png, referenciarlo aca en openGraph.images.
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    type: "website",
    locale: "es_MX",
    siteName: "LexChiapas",
  },
  twitter: {
    card: "summary",
    title: TITLE,
    description: DESCRIPTION,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-zinc-50 dark:bg-zinc-950">
        <DisclaimerBanner />
        {children}
      </body>
    </html>
  );
}
