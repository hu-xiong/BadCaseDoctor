import apiClient from './axios'

export interface NewsItem {
  id: number
  title: string
  summary: string
  content: string
  author: string
  publishDate: string
  category: string
  imageUrl?: string
}

export const getNews = (params?: { page?: number; limit?: number; category?: string }) => {
  return apiClient.get('/news', { params })
}

export const getNewsDetail = (id: number) => {
  return apiClient.get(`/news/${id}`)
}

export const getNewsCategories = () => {
  return apiClient.get('/news/categories')
}
