import apiClient from './axios'
import { unwrapData, type PaginatedList } from './response'

export interface DocCategory {
  id: number
  name: string
  parent_id: number
  sort_order: number
  children?: DocCategory[]
}

export interface DocPage {
  id: number
  category_id: number
  title: string
  content: string
  slug: string
  status: number
  created_at: string
  updated_at: string
}

export const getDocCategories = async () => {
  const response = await apiClient.get('/docs/categories')
  return unwrapData<DocCategory[]>(response)
}

export const getDocPages = async (params?: { category_id?: number; page?: number; page_size?: number }) => {
  const response = await apiClient.get('/docs/pages', { params })
  return unwrapData<PaginatedList<DocPage>>(response)
}

export const getDocPage = async (id: number | string) => {
  const response = await apiClient.get(`/docs/pages/${id}`)
  return unwrapData<DocPage>(response)
}

export const searchDocs = async (keyword: string) => {
  const response = await apiClient.get('/docs/search', { params: { keyword } })
  return unwrapData<DocPage[]>(response)
}
