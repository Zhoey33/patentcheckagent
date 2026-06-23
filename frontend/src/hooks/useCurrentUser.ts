"use client";

// 这个文件用于在业务页面中获取当前登录用户并处理未登录跳转。

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { apiFetch, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";

export function useCurrentUser() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<User>("/api/auth/me")
      .then(setUser)
      .catch((error) => {
        if (error instanceof ApiError && error.status === 401) {
          router.push("/login");
        }
      })
      .finally(() => setLoading(false));
  }, [router]);

  return { user, loading };
}
