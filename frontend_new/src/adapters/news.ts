import type { NewsItem } from '../types/news';

export function adaptNewsList(raw: any): NewsItem[] {
  const items = Array.isArray(raw) ? raw : [];
  return items.map((item: any) => ({
    id: String(item.id ?? ''),
    title: String(item.title ?? ''),
    summary: String(item.summary ?? ''),
    source: item.source ? String(item.source) : undefined,
    category: item.category ? String(item.category) : undefined,
    publishedAt: item.published_at ? String(item.published_at) : undefined,
  }));
}
