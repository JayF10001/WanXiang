type DataSourceMode = 'mock' | 'api';

const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost']);

function normalizeFrontendApiBase(baseUrl: string): string {
  if (!import.meta.env.DEV || typeof window === 'undefined') {
    return baseUrl;
  }

  try {
    const resolvedUrl = new URL(baseUrl, window.location.origin);
    const isRelativeBase = !/^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(baseUrl);
    if (isRelativeBase) {
      return baseUrl;
    }

    const currentHost = window.location.hostname;
    const apiHost = resolvedUrl.hostname;
    if (!LOOPBACK_HOSTS.has(apiHost)) {
      return resolvedUrl.toString().replace(/\/$/, '');
    }

    if (apiHost !== currentHost && (LOOPBACK_HOSTS.has(currentHost) || import.meta.env.DEV)) {
      resolvedUrl.hostname = currentHost;
    }

    return resolvedUrl.toString().replace(/\/$/, '');
  } catch {
    return baseUrl;
  }
}

export const runtimeConfig = {
  dataSourceMode: ((import.meta.env.VITE_DATA_SOURCE_MODE as DataSourceMode | undefined) ?? 'api'),
  frontendApiBaseUrl: normalizeFrontendApiBase(import.meta.env.VITE_FRONTEND_API_BASE ?? '/api'),
};

export type { DataSourceMode };
