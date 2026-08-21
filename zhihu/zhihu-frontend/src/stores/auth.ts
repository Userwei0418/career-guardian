import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "@/lib/api";

interface AuthState {
  token: string | null;
  userId: number | null;
  username: string | null;
  isAdmin: boolean;
  isLoggedIn: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
  restore: () => void;
}

export const useAuth = create<AuthState>()(persist((set) => ({
  token: null,
  userId: null,
  username: null,
  isAdmin: false,
  isLoggedIn: false,

  login: async (username, password) => {
    const res = await api.post<{ access_token: string; user_id: number; username: string; is_admin: boolean }>(
      "/auth/login",
      { username, password }
    );
    localStorage.setItem("zhihu_token", res.access_token);
    set({ token: res.access_token, userId: res.user_id, username: res.username, isAdmin: res.is_admin || false, isLoggedIn: true });
  },

  register: async (username, password) => {
    const res = await api.post<{ access_token: string; user_id: number; username: string; is_admin: boolean }>(
      "/auth/register",
      { username, password }
    );
    localStorage.setItem("zhihu_token", res.access_token);
    set({ token: res.access_token, userId: res.user_id, username: res.username, isAdmin: res.is_admin || false, isLoggedIn: true });
  },

  logout: () => {
    localStorage.removeItem("zhihu_token");
    set({ token: null, userId: null, username: null, isAdmin: false, isLoggedIn: false });
  },

  restore: () => {
    const token = localStorage.getItem("zhihu_token");
    if (token) {
      set({ token, isLoggedIn: true });
      api.get<{ id: number; username: string; is_admin: boolean }>("/auth/me").then((user) => {
        set({ token, userId: user.id, username: user.username, isAdmin: user.is_admin || false, isLoggedIn: true });
      }).catch(() => {
        localStorage.removeItem("zhihu_token");
        set({ token: null, userId: null, username: null, isAdmin: false, isLoggedIn: false });
      });
      return;
    }
    set({ token: null, userId: null, username: null, isAdmin: false, isLoggedIn: false });
  },
}), {
  name: "zhihu-auth",
  partialize: (state) => ({ token: state.token, userId: state.userId, username: state.username, isAdmin: state.isAdmin, isLoggedIn: state.isLoggedIn }),
}));
