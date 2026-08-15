"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";

interface FileItem {
  id: number;
  crawl_job_id: string;
  name: string;
  type: string;
}

export default function FilesBrowser() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const comId = searchParams.get("com_id") || "";

  const [files, setFiles] = useState<FileItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetchFiles = useCallback(async () => {
    if (!comId) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/files/browse?com_id=${comId}&file_type=html`);
      const data = await res.json();
      setFiles(data.files || []);
    } catch {}
    finally { setLoading(false); }
  }, [comId]);

  const fetchContent = useCallback(async (crawlJobId: string) => {
    setSelectedFile(crawlJobId);
    try {
      const res = await fetch(`/api/files/content?crawl_job_id=${crawlJobId}`);
      setFileContent(await res.json());
    } catch {}
  }, []);

  useEffect(() => { fetchFiles(); }, [fetchFiles]);

  return (
    <div className="h-screen flex flex-col">
      <div className="bg-white border-b px-6 py-3 flex items-center gap-2 text-sm">
        <Link href="/admin/crawl" className="text-blue-500 hover:underline">Back</Link>
        <span className="text-gray-400">/</span>
        <span className="text-gray-600">{comId}</span>
        <div className="flex-1" />
        <span className="text-xs text-gray-400">{files.length} items</span>
      </div>
      <div className="flex-1 flex overflow-hidden">
        <div className="w-2/5 border-r overflow-y-auto bg-gray-50">
          {loading ? (
            <div className="p-4 text-center text-gray-400">Loading...</div>
          ) : files.length === 0 ? (
            <div className="p-4 text-center text-gray-400">No data</div>
          ) : (
            <div className="divide-y">
              {files.map(f => (
                <div
                  key={f.crawl_job_id}
                  onClick={() => fetchContent(f.crawl_job_id)}
                  className={`px-4 py-3 cursor-pointer hover:bg-white ${selectedFile === f.crawl_job_id ? "bg-white border-l-2 border-blue-500 bg-blue-50/30" : ""}`}
                >
                  <div className="text-sm truncate">{f.name}</div>
                  <div className="text-xs text-gray-400 mt-0.5">{f.crawl_job_id.slice(0, 16)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex-1 overflow-hidden flex flex-col">
          {selectedFile ? (
            <div className="flex-1 overflow-auto">
              {fileContent ? (
                <FileContentViewer content={fileContent} />
              ) : (
                <div className="p-4 text-gray-400">Loading...</div>
              )}
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-400">Select item</div>
          )}
        </div>
      </div>
    </div>
  );
}

function FileContentViewer({ content }: { content: any }) {
  const [tab, setTab] = useState("html");
  return (
    <div className="h-full flex flex-col">
      <div className="bg-gray-100 px-4 py-2 flex gap-2">
        {["html", "json", "model"].map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1 rounded text-sm ${tab === t ? "bg-blue-500 text-white" : "bg-white"}`}>
            {t === "html" ? "HTML" : t === "json" ? "JSON" : "Model"}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-auto">
        <pre className="p-4 text-xs font-mono whitespace-pre-wrap break-all bg-gray-900 text-green-400 min-h-full">
          {tab === "html" && (content.html_content || "No HTML")}
          {tab === "json" && JSON.stringify(content.json_content, null, 2)}
          {tab === "model" && JSON.stringify(content.model_content, null, 2)}
        </pre>
      </div>
    </div>
  );
}
