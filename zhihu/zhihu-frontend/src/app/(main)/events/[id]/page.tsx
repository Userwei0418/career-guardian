import CareerEventWorkspace from "@/components/events/CareerEventWorkspace";

export default async function CareerEventPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <CareerEventWorkspace eventId={Number(id)} />;
}
