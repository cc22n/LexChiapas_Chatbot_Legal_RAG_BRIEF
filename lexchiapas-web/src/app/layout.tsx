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

export const metadata: Metadata = {
  title: "LexChiapas - Asistente legal de Chiapas",
  description:
    "Chatbot que responde preguntas sobre leyes y reglamentos del Estado de Chiapas, citando la ley y el articulo.",
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
