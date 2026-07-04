import apiClient from './axios'
import { unwrapData, type PaginatedList } from './response'

export interface DownloadItem {
  id: number
  name: string
  version: string
  edition: string
  os: string
  file_path: string
  file_size: number
  sha256: string
  description: string
  download_count: number
  created_at: string
}

export interface DownloadFilter {
  edition?: string
  os?: string
  page?: number
  page_size?: number
}

export const getDownloads = async (filters?: DownloadFilter) => {
  const response = await apiClient.get('/downloads', { params: filters })
  return unwrapData<PaginatedList<DownloadItem>>(response)
}

export const getDownloadDetail = async (id: number) => {
  const response = await apiClient.get(`/downloads/${id}`)
  return unwrapData<DownloadItem>(response)
}

export const recordDownload = async (id: number) => {
  const response = await apiClient.post(`/downloads/${id}/record`)
  return unwrapData(response)
}
