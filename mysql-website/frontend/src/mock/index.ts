// Mock data for development

export const mockNews = [
  {
    id: 1,
    title: 'MySQL 8.4 LTS Released',
    summary: 'The new Long Term Support release brings enhanced performance and 8 years of support.',
    content: 'Full article content here...',
    author: 'MySQL Team',
    publishDate: '2024-04-15',
    category: 'Release'
  },
  {
    id: 2,
    title: 'MySQL Tech Talk Series',
    summary: 'Join our monthly webinars covering best practices and new features.',
    content: 'Full article content here...',
    author: 'MySQL Team',
    publishDate: '2024-04-10',
    category: 'Event'
  }
]

export const mockDownloads = [
  {
    id: 1,
    version: '8.4.0 LTS',
    type: 'community',
    date: '2024-04-15',
    size: '243 MB',
    platforms: ['Windows', 'Linux', 'macOS']
  },
  {
    id: 2,
    version: '8.0.36',
    type: 'community',
    date: '2024-02-20',
    size: '238 MB',
    platforms: ['Windows', 'Linux', 'macOS']
  }
]

export const mockCommunityPosts = [
  {
    id: 1,
    title: 'Best practices for MySQL query optimization',
    summary: 'Tips for optimizing MySQL queries...',
    author: { username: 'dbadmin' },
    category: 'tutorials',
    tags: ['optimization', 'performance'],
    createdAt: '2024-04-15',
    viewCount: 1234,
    replyCount: 23
  }
]

export const mockUser = {
  id: 1,
  username: 'demo_user',
  email: 'demo@mysql.com',
  avatar: ''
}
