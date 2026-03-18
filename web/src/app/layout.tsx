import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { Providers } from "@/components/providers";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "County GIS Chat",
  description: "Chat with county GIS data",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} font-sans antialiased`}>
        <ClerkProvider signInUrl="/sign-in" signInFallbackRedirectUrl="/" afterSignOutUrl="/sign-in">
          <Providers>{children}</Providers>
        </ClerkProvider>
      </body>
    </html>
  );
}
