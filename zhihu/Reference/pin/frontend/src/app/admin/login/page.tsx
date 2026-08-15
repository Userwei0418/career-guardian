'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { login } from '@/lib/auth'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const success = await login(username, password)
    if (success) {
      router.push('/admin')
    } else {
      setError('用户名或密码错误')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50/50">
      <div className="bg-white p-8 rounded-xl w-full max-w-lg">
        <h1 className="text-2xl font-bold mb-6 text-center">管理员登录</h1>
        {error && (
          <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg border border-red-100">
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">用户名</label>
            <input
              type="text"
              className="w-full input-minimal"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">密码</label>
            <input
              type="password"
              className="w-full input-minimal"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <div>
            <button
              type="submit"
              className="w-full btn-primary"
            >
              登录
            </button>
          </div>
        </form>
        <div className="mt-4 text-center text-sm text-gray-600">
        </div>
      </div>
    </div>
  )
}
