import { createRouter, createWebHashHistory } from 'vue-router';
import user from '../store/user.js';
import { getCurrentUser } from '../api.js';

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', name: 'Login', component: () => import('../components/Login.vue') },
  { path: '/register', name: 'Register', component: () => import('../components/Register.vue') },
  { path: '/reset-password', name: 'ResetPassword', component: () => import('../components/ResetPassword.vue') },
  { path: '/forgot-password', name: 'ForgotPassword', component: () => import('../components/ForgotPassword.vue') },
  { 
    path: '/dashboard', 
    name: 'Dashboard', 
    component: () => import('../components/Dashboard.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/project-manage', 
    name: 'ProjectManage', 
    component: () => import('../components/ProjectManage.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/new-project', 
    name: 'NewProject', 
    component: () => import('../components/NewProject.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/project-detail/:id', 
    name: 'ProjectDetail', 
    component: () => import('../components/ProjectDetail.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/badcase-detail', 
    name: 'BadcaseDetail', 
    component: () => import('../components/BadcaseDetail.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/new-badcase', 
    name: 'NewBadcase', 
    component: () => import('../components/NewBadcase.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/import-database', 
    name: 'ImportDatabase', 
    component: () => import('../components/ImportDatabase.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/import-excel', 
    name: 'ImportExcel', 
    component: () => import('../components/ImportExcel.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/chat', 
    name: 'Chat', 
    component: () => import('../components/Chat.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/chat-sessions/:projectId?', 
    name: 'ChatSessions', 
    component: () => import('../components/ChatSessions.vue'),
    meta: { requiresAuth: true }
  },
  { 
    path: '/terminal-test', 
    name: 'TerminalTest', 
    component: () => import('../components/TerminalTest.vue'),
    meta: { requiresAuth: true }
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

// 路由守卫
router.beforeEach(async (to, from, next) => {
  // 如果路由需要认证
  if (to.meta.requiresAuth) {
    // 检查用户是否已登录
    if (!user.value) {
              // 尝试获取用户信息
        try {
          const res = await getCurrentUser();
          if (res.data.success) {
            user.value = res.data.user;
            next();
            return;
          }
        } catch (error) {
          console.error('获取用户信息失败:', error);
        }
      
      // 如果获取用户信息失败，重定向到登录页
      next('/login');
      return;
    }
  }
  
  next();
});

export default router; 