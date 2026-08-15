// 简单的认证管理

interface User {
  id: string
  username: string
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
}

let authState: AuthState = {
  user: null,
  isAuthenticated: false
}

let listeners: Array<(state: AuthState) => void> = []

// 检查是否在浏览器环境中
const isBrowser = typeof window !== 'undefined'

// 从localStorage恢复登录状态
const loadUserFromStorage = () => {
  if (isBrowser) {
    const savedUser = localStorage.getItem('user')
    if (savedUser) {
      try {
        const user = JSON.parse(savedUser)
        authState = {
          user,
          isAuthenticated: true
        }
        notifyListeners()
      } catch (error) {
        localStorage.removeItem('user')
      }
    }
  }
}

// 通知所有监听器
const notifyListeners = () => {
  listeners.forEach(listener => listener({ ...authState }))
}

// 登录
const login = async (username: string, password: string): Promise<boolean> => {
  // 简单的登录验证，实际项目中应该调用API
  if (username === 'admin' && password === 'password') {
    const userData = { id: '1', username }
    authState = {
      user: userData,
      isAuthenticated: true
    }
    if (isBrowser) {
      localStorage.setItem('user', JSON.stringify(userData))
      // 设置cookie，供中间件使用
      document.cookie = `user=${JSON.stringify(userData)}; path=/; max-age=86400`
    }
    notifyListeners()
    return true
  }
  return false
}

// 登出
const logout = () => {
  authState = {
    user: null,
    isAuthenticated: false
  }
  if (isBrowser) {
    localStorage.removeItem('user')
    // 清除cookie
    document.cookie = 'user=; path=/; max-age=0'
  }
  notifyListeners()
}

// 订阅认证状态变化
const subscribe = (listener: (state: AuthState) => void) => {
  listeners.push(listener)
  // 立即通知当前状态
  listener({ ...authState })
  
  // 返回取消订阅函数
  return () => {
    listeners = listeners.filter(l => l !== listener)
  }
}

// 初始化时加载用户
if (isBrowser) {
  loadUserFromStorage()
}

export { login, logout, subscribe, authState }
