import { defineAsyncComponent } from 'vue'

/**
 * 插件卡片注册表（本地目录版本）
 * - 把插件放在 electron-vue3/src/plugins/<yourPlugin>/ 下
 * - 在此处注册即可在左侧“插件”面板展示并挂载
 */
export const pluginCards = [
  {
    id: 'example',
    title: '示例插件',
    icon: '🧩',
    description: '演示如何在左侧插件面板挂载自定义 UI。',
    version: '0.1.0',
    author: 'BadCase Doctor',
    order: 0,
    component: defineAsyncComponent(() => import('./example/ExamplePanel.vue')),
    visible: () => true
  }
]

