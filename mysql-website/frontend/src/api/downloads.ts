import apiClient from './axios'

export interface DownloadVersion {
  id: number
  name: string
  version: string
  type: 'enterprise' | 'community' | 'cluster'
  releaseDate: string
  size: string
  sha256: string
  downloadUrl: string
}

export interface DownloadFilter {
  type?: 'enterprise' | 'community' | 'cluster'
  os?: 'windows' | 'linux' | 'macos'
  version?: string
}

export const getDownloads = (filters?: DownloadFilter) => {
  return apiClient.get('/downloads', { params: filters })
}

export const getDownloadVersions = () => {
  return apiClient.get('/downloads/versions')
}
