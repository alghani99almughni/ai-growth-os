import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Voice | Your business, always heard",
  description: "A multilingual AI voice receptionist for businesses. Start with a zero-paid-AI-token local voice engine.",
  applicationName: "AI Voice",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}