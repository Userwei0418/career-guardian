import { NextRequest, NextResponse } from 'next/server'

export function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname

  // 排除登录页面
  if (pathname === '/admin/login') {
    return NextResponse.next()
  }

  // 检查是否是需要保护的路径
  if (pathname.startsWith('/admin')) {
    // 检查是否有登录状态
    const user = request.cookies.get('user')?.value
    
    // 如果没有登录，重定向到登录页面
    if (!user) {
      return NextResponse.redirect(new URL('/admin/login', request.url))
    }
  }

  return NextResponse.next()
}

// 配置中间件应用的路径
export const config = {
  matcher: ['/admin/:path*'],
}
