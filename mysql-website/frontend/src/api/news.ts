import apiClient from './axios'
import { unwrapData, type PaginatedList } from './response'

export interface NewsItem {
  id: number
  title: string
  summary: string
  content: string
  image_url?: string
  status: number
  created_at: string
}

export const getNews = async (params?: { page?: number; page_size?: number }) => {
  const response = await apiClient.get('/news', { params })
  return unwrapData<PaginatedList<NewsItem>>(response)
}

export const getLatestNews = async (limit = 3) => {
  const response = await apiClient.get('/news/latest', { params: { limit } })
  return unwrapData<NewsItem[]>(response)
}

export const getNewsDetail = async (id: number | string) => {
  const response = await apiClient.get(`/news/${id}`)
  return unwrapData<NewsItem>(response)
}
