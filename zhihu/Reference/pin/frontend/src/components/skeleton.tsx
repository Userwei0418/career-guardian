export function SkeletonBox({ className = '' }: { className?: string }) {
  return <div className={"skeleton " + className} />
}

export function StatCardSkeleton() {
  return (
    <div className="bg-white p-5 rounded-xl">
      <SkeletonBox className="h-3.5 w-16 mb-3" />
      <SkeletonBox className="h-7 w-14" />
    </div>
  )
}

export function ChartCardSkeleton({ titleWidth = 'w-32' }: { titleWidth?: string }) {
  return (
    <div className="bg-white p-5 rounded-xl">
      <SkeletonBox className={"h-5 " + titleWidth + " mb-4"} />
      <SkeletonBox className="h-80 w-full" />
    </div>
  )
}

export function JobCardSkeleton() {
  return (
    <div className="bg-white p-5 rounded-xl">
      <div className="flex gap-4">
        <SkeletonBox className="w-10 h-10 rounded-lg flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex justify-between items-start">
            <div className="flex-1">
              <SkeletonBox className="h-4 w-48 mb-2" />
              <SkeletonBox className="h-3.5 w-28" />
            </div>
            <div className="w-20">
              <SkeletonBox className="h-3.5 w-16 ml-auto mb-2" />
              <SkeletonBox className="h-3 w-12 ml-auto" />
            </div>
          </div>
          <div className="flex gap-2 mt-3 flex-wrap">
            <SkeletonBox className="h-5 w-12 rounded-md" />
            <SkeletonBox className="h-5 w-14 rounded-md" />
            <SkeletonBox className="h-5 w-18 rounded-md" />
          </div>
        </div>
      </div>
    </div>
  )
}

export function CompanyCardSkeleton() {
  return (
    <div className="bg-white p-5 rounded-xl h-full">
      <div className="flex items-start gap-4">
        <SkeletonBox className="w-10 h-10 rounded-lg flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <SkeletonBox className="h-4 w-32 mb-2" />
          <SkeletonBox className="h-3.5 w-24 mb-2" />
          <SkeletonBox className="h-3.5 w-20" />
        </div>
      </div>
      <div className="mt-4 pt-4 border-t border-gray-50 flex gap-4">
        <SkeletonBox className="h-3.5 w-12" />
        <SkeletonBox className="h-3.5 w-16" />
      </div>
    </div>
  )
}