import Navbar from "@/components/layout/Navbar";
import { ArticleProvider } from "@/context/ArticleContext";

export default function MainLayout({ children }: { children: React.ReactNode }) {
  return (
    <ArticleProvider>
      <div className="min-h-screen bg-[var(--color-bg)]">
        <Navbar />
        <main className="mx-auto w-full max-w-7xl px-5 py-8 sm:px-6 lg:px-8">{children}</main>
      </div>
    </ArticleProvider>
  );
}
