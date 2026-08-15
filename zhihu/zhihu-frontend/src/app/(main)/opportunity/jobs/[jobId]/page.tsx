import JobDetailWorkspace from "@/components/opportunity/JobDetailWorkspace";

export default async function OpportunityJobDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return <JobDetailWorkspace jobId={jobId} />;
}
