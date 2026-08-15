"use client";

import { useSyncExternalStore } from "react";

function subscribeToLocation(callback: () => void) {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
}

function getLocationSearch() {
  return window.location.search;
}

function getServerLocationSearch() {
  return null;
}

export function useRouteEntityId(paramName: string, storedId: number | null) {
  const locationSearch = useSyncExternalStore(
    subscribeToLocation,
    getLocationSearch,
    getServerLocationSearch,
  );
  if (locationSearch === null) return { id: storedId, ready: false };
  const rawValue = new URLSearchParams(locationSearch).get(paramName);
  const routeId = rawValue ? Number(rawValue) : null;
  return {
    id: routeId && Number.isInteger(routeId) && routeId > 0 ? routeId : storedId,
    ready: true,
  };
}
