"use client";

import { Suspense } from "react";
import FilesBrowser from "./FilesBrowser";

export default function FilesPage() {
  return (
    <Suspense fallback={<div className="h-screen flex items-center justify-center text-gray-400">加载中...</div>}>
      <FilesBrowser />
    </Suspense>
  );
}
