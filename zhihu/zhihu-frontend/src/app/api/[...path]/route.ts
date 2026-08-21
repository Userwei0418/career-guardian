import { NextRequest } from "next/server";

const API_ORIGIN = (process.env.GUARDIAN_API_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function proxyRequest(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const target = new URL(`${API_ORIGIN}/api/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;
  const isLongRunningAI = path.some((segment) => ["guard", "learning-plan", "resume-drafts", "review-follow-up", "consistency"].includes(segment));
  const isStrategyRepairReplay = path.includes("strategy-repairs") && path.at(-1) === "replay";

  const headers = new Headers();
  for (const name of ["accept", "authorization", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "follow",
      signal: AbortSignal.timeout(isStrategyRepairReplay ? 190_000 : isLongRunningAI ? 90_000 : 30_000),
    });
    const responseHeaders = new Headers();
    for (const name of ["content-type", "content-disposition"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    responseHeaders.set("cache-control", "no-store");
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "api_unavailable",
          message: "职护服务暂时无法访问，请稍后重试",
          status: 502,
        },
      },
      { status: 502 },
    );
  }
}

export const dynamic = "force-dynamic";

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
