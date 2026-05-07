import apiClient from './axios'

export interface DocNode {
  id: string
  title: string
  content?: string
  children?: DocNode[]
}

export const getDocsTree = () => {
  return apiClient.get('/docs/tree')
}

export const getDocContent = (id: string) => {
  return apiClient.get(`/docs/${id}`)
}

export const searchDocs = (query: string) => {
  return apiClient.get('/docs/search', { params: { q: query } })
}
