import Navbar from "@/components/layout/Navbar";
import { ArticleProvider } from "@/context/ArticleContext";

export default function MainLayout({ children }: { children: React.ReactNode }) {
  return (
    <ArticleProvider>
      <div className="min-h-screen bg-[var(--color-bg)]">
        <Navbar />
        <main className="max-w-5xl mx-auto px-6 py-8">{children}</main>
      </div>
    </ArticleProvider>
  );
}
