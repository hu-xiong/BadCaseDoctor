// 与 BadCaseDoctor（5000 / 5173）错开的 MySQL 官网专用端口
export const WEBSITE_BACKEND_PORT = 8090
export const WEBSITE_FRONTEND_PORT = 5180
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || `http://localhost:${WEBSITE_BACKEND_PORT}/api/v1`
export const API_TIMEOUT = 10000

// Pagination
export const DEFAULT_PAGE_SIZE = 10
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

// Storage Keys
export const STORAGE_TOKEN_KEY = 'token'
export const STORAGE_USER_KEY = 'user'
export const STORAGE_THEME_KEY = 'theme'

// MySQL Version Info
export const MYSQL_LATEST_VERSION = '8.4.0'
export const MYSQL_LTS_VERSION = '8.0'
export const MYSQL_RELEASE_DATE = '2024-04-15'

// Download Links (Mock)
export const DOWNLOAD_BASE_URL = 'https://dev.mysql.com/downloads/'

// Social Links
export const SOCIAL_LINKS = {
  twitter: 'https://twitter.com/mysql',
  github: 'https://github.com/mysql/mysql-server',
  facebook: 'https://www.facebook.com/MySQL',
  linkedin: 'https://www.linkedin.com/company/mysql'
}

// Support Links
export const SUPPORT_LINKS = {
  docs: '/docs',
  forum: 'https://forums.mysql.com/',
  stackoverflow: 'https://stackoverflow.com/questions/tagged/mysql',
  bugs: 'https://bugs.mysql.com/'
}
