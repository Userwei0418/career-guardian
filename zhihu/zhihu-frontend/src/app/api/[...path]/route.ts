import { NextRequest } from "next/server";

const API_ORIGIN = (process.env.GUARDIAN_API_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const MAX_CASHFLOW_MULTIPART_BODY_SIZE = 10 * 1024 * 1024 + 512 * 1024;
const MAX_CASHFLOW_TEXT_JSON_SIZE = 16 * 1024;
const MAX_CASHFLOW_MAPPING_JSON_SIZE = 16 * 1024;
const MAX_CASHFLOW_CANDIDATE_JSON_SIZE = 8 * 1024;
const MAX_CASHFLOW_CONFIRM_JSON_SIZE = 128 * 1024;

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

function cashflowBodyTooLargeResponse(message: string): Response {
  return Response.json(
    {
      error: {
        code: "cashflow_import_too_large",
        message,
        status: 413,
      },
    },
    { status: 413 },
  );
}

function cashflowRequestLimit(method: string, path: string): { bytes: number; message: string } | null {
  if (method === "POST" && ["cashflow/imports", "cashflow/imports/ocr"].includes(path)) {
    return { bytes: MAX_CASHFLOW_MULTIPART_BODY_SIZE, message: "上传请求过大，账单文件不能超过 10MB" };
  }
  if (method === "POST" && path === "cashflow/imports/text") {
    return { bytes: MAX_CASHFLOW_TEXT_JSON_SIZE, message: "文本识别请求过大" };
  }
  if (method === "PUT" && /^cashflow\/imports\/\d+\/mapping$/.test(path)) {
    return { bytes: MAX_CASHFLOW_MAPPING_JSON_SIZE, message: "字段映射请求过大" };
  }
  if (method === "PATCH" && /^cashflow\/imports\/\d+\/candidates\/\d+$/.test(path)) {
    return { bytes: MAX_CASHFLOW_CANDIDATE_JSON_SIZE, message: "候选编辑请求过大" };
  }
  if (method === "POST" && /^cashflow\/imports\/\d+\/confirm$/.test(path)) {
    return { bytes: MAX_CASHFLOW_CONFIRM_JSON_SIZE, message: "确认入账请求过大" };
  }
  return null;
}

function boundedRequestBody(
  body: ReadableStream<Uint8Array>,
  maxBytes: number,
  onTooLarge: () => void,
): ReadableStream<Uint8Array> {
  const reader = body.getReader();
  let received = 0;
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      const chunk = await reader.read();
      if (chunk.done) {
        controller.close();
        return;
      }
      received += chunk.value.byteLength;
      if (received > maxBytes) {
        onTooLarge();
        await reader.cancel("cashflow upload too large");
        controller.error(new Error("cashflow upload too large"));
        return;
      }
      controller.enqueue(chunk.value);
    },
    async cancel(reason) {
      await reader.cancel(reason);
    },
  });
}

async function proxyRequest(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const target = new URL(`${API_ORIGIN}/api/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;
  const isLongRunningAI = path.some((segment) => ["guard", "learning-plan", "resume-drafts", "review-follow-up", "consistency"].includes(segment));
  const isStrategyRepairReplay = path.includes("strategy-repairs") && path.at(-1) === "replay";
  const joinedPath = path.join("/");
  const requestLimit = cashflowRequestLimit(request.method, joinedPath);
  const isCashflowModelIntake = request.method === "POST" && ["cashflow/imports/text", "cashflow/imports/ocr"].includes(joinedPath);

  if (requestLimit) {
    const contentLength = request.headers.get("content-length");
    if (contentLength && /^\d+$/.test(contentLength) && Number(contentLength) > requestLimit.bytes) {
      return cashflowBodyTooLargeResponse(requestLimit.message);
    }
  }

  const headers = new Headers();
  for (const name of ["accept", "authorization", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  let cashflowBodyTooLarge = false;
  const requestBody = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : request.body && requestLimit
      ? boundedRequestBody(request.body, requestLimit.bytes, () => { cashflowBodyTooLarge = true; })
      : request.body ?? undefined;

  try {
    const upstreamRequest: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      body: requestBody,
      cache: "no-store",
      redirect: "follow",
      signal: AbortSignal.timeout(isStrategyRepairReplay ? 190_000 : isCashflowModelIntake ? 120_000 : isLongRunningAI ? 90_000 : 30_000),
    };
    if (requestBody) upstreamRequest.duplex = "half";
    const upstream = await fetch(target, upstreamRequest);
    const responseHeaders = new Headers();
    for (const name of ["content-type", "content-disposition", "x-content-type-options"]) {
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
    if (cashflowBodyTooLarge && requestLimit) return cashflowBodyTooLargeResponse(requestLimit.message);
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
