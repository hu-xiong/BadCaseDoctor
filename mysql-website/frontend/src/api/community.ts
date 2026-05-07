import apiClient from './axios'

export interface CommunityPost {
  id: number
  title: string
  content: string
  author: {
    id: number
    username: string
    avatar?: string
  }
  category: string
  tags: string[]
  createdAt: string
  updatedAt: string
  viewCount: number
  replyCount: number
}

export interface CreatePostData {
  title: string
  content: string
  category: string
  tags: string[]
}

export const getPosts = (params?: { page?: number; limit?: number; category?: string }) => {
  return apiClient.get('/community/posts', { params })
}

export const getPostDetail = (id: number) => {
  return apiClient.get(`/community/posts/${id}`)
}

export const createPost = (data: CreatePostData) => {
  return apiClient.post('/community/posts', data)
}

export const getCategories = () => {
  return apiClient.get('/community/categories')
}
