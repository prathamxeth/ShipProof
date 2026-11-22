import type { Metadata } from "next";
import "./globals.css";
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
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full w-full text-[#1c2a22] antialiased selection:bg-[#2d4a3e]/15 selection:text-[#1c2a22] relative overflow-x-hidden">
        <LiquidFilters />
        {/* Full-bleed Springlight Meadow Background with Ambient Atmosphere Veil */}
        <div
          className="fixed inset-0 z-0 pointer-events-none"
          style={{
            backgroundImage: "url('/images/shipproof-spring-bg.jpeg')",
            backgroundSize: "cover",
            backgroundPosition: "center",
            backgroundRepeat: "no-repeat",
            backgroundAttachment: "fixed",
          }}
        >
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background:
                "radial-gradient(circle at 50% 15%, rgba(255, 255, 255, 0.25), transparent 70%), linear-gradient(to bottom, rgba(247, 245, 239, 0.35) 0%, rgba(247, 245, 239, 0.15) 50%, rgba(247, 245, 239, 0.45) 100%)",
            }}
          />
        </div>
        <div className="relative z-10 min-h-screen w-full flex flex-col">
          {children}
        </div>
      </body>
    </html>
  );
}
