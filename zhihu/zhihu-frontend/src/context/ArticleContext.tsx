"use client";

import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import ArticleDrawer from "@/components/ui/ArticleDrawer";

interface ArticleContextType {
  openArticle: (slug: string) => void;
  closeArticle: () => void;
}

const ArticleContext = createContext<ArticleContextType>({
  openArticle: () => {},
  closeArticle: () => {},
});

export function useArticleDrawer() {
  return useContext(ArticleContext);
}

export function ArticleProvider({ children }: { children: ReactNode }) {
  const [slug, setSlug] = useState<string | null>(null);

  const openArticle = useCallback((s: string) => setSlug(s), []);
  const closeArticle = useCallback(() => setSlug(null), []);

  return (
    <ArticleContext.Provider value={{ openArticle, closeArticle }}>
      {children}
      <ArticleDrawer slug={slug} onClose={closeArticle} />
    </ArticleContext.Provider>
  );
}
