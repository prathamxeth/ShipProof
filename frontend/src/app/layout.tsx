import type { Metadata } from "next";
import "./globals.css";
import HoloBackground from "@/components/ui/HoloBackground";
import LiquidFilters from "@/components/ui/LiquidFilters";

export const metadata: Metadata = {
  title: "ShipProof — AI Store Guardian & Self-Healing Checkout",
  description: "Autonomous 24/7 AI Store Guardian & Self-Healing Checkout. Simulates customer journeys and auto-repairs store issues.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full antialiased">
      <body className="min-h-full w-full bg-[#100e17] text-zinc-100 antialiased selection:bg-[#1863dc]/30 selection:text-white relative overflow-x-hidden">
        <LiquidFilters />
        <HoloBackground />
        <div className="relative z-10 min-h-screen w-full flex flex-col">
          {children}
        </div>
      </body>
    </html>
  );
}
