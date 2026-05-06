import { adaptNewsList } from '../../adapters/news';
import { newsListRawMock } from '../../mocks/news/newsList.mock';
import type { NewsItem } from '../../types/news';

export async function getNewsListMock(): Promise<NewsItem[]> {
  return adaptNewsList(newsListRawMock);
}
