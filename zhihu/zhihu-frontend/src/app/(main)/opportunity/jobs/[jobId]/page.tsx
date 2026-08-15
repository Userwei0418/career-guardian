import JobDetailWorkspace from "@/components/opportunity/JobDetailWorkspace";

export default async function OpportunityJobDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ jobId: string }>;
  searchParams: Promise<{ list_score?: string }>;
}) {
  const { jobId } = await params;
  const query = await searchParams;
  let normalizedJobId = jobId;
  try {
    normalizedJobId = decodeURIComponent(jobId);
  } catch {
    // 非法编码交给详情 API 按“不存在”处理，避免页面渲染直接失败。
  }
  const parsedListScore = Number(query.list_score);
  const listScore = Number.isFinite(parsedListScore) && parsedListScore >= 0 && parsedListScore <= 100 ? parsedListScore : null;
  return <JobDetailWorkspace jobId={normalizedJobId} listScore={listScore} />;
}
