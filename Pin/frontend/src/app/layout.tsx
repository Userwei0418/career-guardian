import type { Metadata } from 'next'
import { ToastProvider } from '@/components/Toast'
import './globals.css'

export const metadata: Metadata = {
  title: '职涯通 - 聚合招聘信息',
  description: '聚合来自企业官网、招聘站点等多渠道的招聘信息，帮助应届生更方便地发现校招、实习、全职机会',
  icons: {
    icon: '/favicon.ico',
  },
} 

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-gray-50/80">
        <header className="bg-white border-b border-gray-100">
          <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <a href="/" className="flex items-center gap-2.5">
              <img src="/logo.png" alt="职涯通" className="h-8 w-8 rounded-lg" />
              <span className="text-xl font-semibold text-gray-900">职涯通</span>
            </a>
            <nav className="flex items-center gap-8">
              <a href="/jobs" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">找职位</a>
              <a href="/companies" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">找公司</a>
              <a href="/analysis" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">数据分析</a>
              <a href="/about" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">关于</a>
              <span className="w-px h-4 bg-gray-200"></span>
              <a href="/admin" className="text-sm font-medium text-blue-600 hover:text-blue-700 transition-colors">管理后台</a>
            </nav>
          </div>
        </header>
        <ToastProvider>
          <main>{children}</main>
        </ToastProvider>
        <footer className="border-t border-gray-100 bg-white">
          <div className="max-w-7xl mx-auto px-6 py-6 text-center text-sm text-gray-400">
            <p>职涯通 - 聚合招聘信息，仅做导航，跳转原站投递</p>
          </div>
        </footer>
      </body>
    </html>
  )
}
