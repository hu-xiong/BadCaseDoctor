import apiClient from './axios'
import { unwrapData, type PaginatedList } from './response'

export interface CommunityUser {
  id: number
  username: string
  avatar?: string
  email?: string
}

export interface CommunityPost {
  id: number
  user_id: number
  title: string
  content: string
  category: string
  view_count: number
  like_count: number
  status: number
  created_at: string
  updated_at: string
  user?: CommunityUser
}

export interface CreatePostData {
  title: string
  content: string
  category: string
}

export const getPosts = async (params?: { page?: number; page_size?: number; category?: string }) => {
  const response = await apiClient.get('/community/posts', { params })
  return unwrapData<PaginatedList<CommunityPost>>(response)
}

export const getPostDetail = async (id: number) => {
  const response = await apiClient.get(`/community/posts/${id}`)
  return unwrapData<CommunityPost>(response)
}

export const createPost = async (data: CreatePostData) => {
  const response = await apiClient.post('/community/posts', data)
  return unwrapData<CommunityPost>(response)
}
