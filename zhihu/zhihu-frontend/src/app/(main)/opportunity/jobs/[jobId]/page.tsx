import JobDetailWorkspace from "@/components/opportunity/JobDetailWorkspace";

export default async function OpportunityJobDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  let normalizedJobId = jobId;
  try {
    normalizedJobId = decodeURIComponent(jobId);
  } catch {
    // 非法编码交给详情 API 按“不存在”处理，避免页面渲染直接失败。
  }
  return <JobDetailWorkspace jobId={normalizedJobId} />;
}
