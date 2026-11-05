import type { Metadata } from "next";
import { Abril_Fatface, Roboto } from "next/font/google";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { StatusProvider } from "@/components/Status";
import "./globals.css";

const roboto = Roboto({ subsets: ["latin"], weight: ["300", "400", "500", "700"], variable: "--font-roboto", display: "swap" });
const abril = Abril_Fatface({ subsets: ["latin"], weight: "400", variable: "--font-abril", display: "swap" });

export const metadata: Metadata = {
  title: "Community Giving",
  description: "The group decides where the money goes; agents protect it; rules keep it fair; PayPal moves the money.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${roboto.variable} ${abril.variable}`}>
      <body className="flex min-h-screen flex-col antialiased">
        <StatusProvider>
          <Header />
          <main className="flex-1">{children}</main>
          <Footer />
        </StatusProvider>
      </body>
    </html>
  );
}
