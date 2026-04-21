/**
 * 插件系统 - BadCase Doctor
 * 
 * 插件接口规范和加载机制
 */

// 插件状态
const pluginRegistry = new Map()
const pluginHooks = new Map()

/**
 * 插件定义接口
 * @typedef {Object} PluginDefinition
 * @property {string} id - 插件唯一标识
 * @property {string} name - 插件名称
 * @property {string} version - 插件版本
 * @property {string} description - 插件描述
 * @property {string} author - 插件作者
 * @property {string} [icon] - 插件图标
 * @property {Function} [onLoad] - 加载时回调
 * @property {Function} [onUnload] - 卸载时回调
 * @property {Function} [onMount] - 挂载到DOM时回调
 * @property {Function} [onUnmount] - 从DOM卸载时回调
 * @property {Object} [config] - 插件配置
 */

/**
 * 插件钩子类型
 * @typedef {'beforeCardCreate' | 'afterCardCreate' | 'beforeCardUpdate' | 'afterCardUpdate' | 'beforeCardDelete' | 'afterCardDelete' | 'onSearch' | 'onTabChange' | 'onNavClick' | 'onPlanChange'} HookType
 */

/**
 * 注册插件
 * @param {PluginDefinition} plugin - 插件定义
 * @returns {boolean} 是否注册成功
 */
export function registerPlugin(plugin) {
  if (!plugin.id || !plugin.name) {
    console.error('[PluginSystem] 插件注册失败: 缺少id或name')
    return false
  }
  
  if (pluginRegistry.has(plugin.id)) {
    console.warn(`[PluginSystem] 插件 ${plugin.id} 已存在，将被覆盖`)
  }
  
  pluginRegistry.set(plugin.id, {
    ...plugin,
    enabled: true,
    loaded: false,
    loadedAt: null
  })
  
  console.log(`[PluginSystem] 插件 ${plugin.name} (${plugin.id}) 注册成功`)
  return true
}

/**
 * 卸载插件
 * @param {string} pluginId - 插件ID
 * @returns {boolean} 是否卸载成功
 */
export function unregisterPlugin(pluginId) {
  const plugin = pluginRegistry.get(pluginId)
  if (!plugin) {
    console.warn(`[PluginSystem] 插件 ${pluginId} 不存在`)
    return false
  }
  
  // 调用卸载钩子
  if (plugin.onUnload && plugin.loaded) {
    try {
      plugin.onUnload()
    } catch (e) {
      console.error(`[PluginSystem] 插件 ${pluginId} 卸载时出错:`, e)
    }
  }
  
  pluginRegistry.delete(pluginId)
  console.log(`[PluginSystem] 插件 ${pluginId} 已卸载`)
  return true
}

/**
 * 启用插件
 * @param {string} pluginId - 插件ID
 */
export function enablePlugin(pluginId) {
  const plugin = pluginRegistry.get(pluginId)
  if (plugin) {
    plugin.enabled = true
    console.log(`[PluginSystem] 插件 ${pluginId} 已启用`)
  }
}

/**
 * 禁用插件
 * @param {string} pluginId - 插件ID
 */
export function disablePlugin(pluginId) {
  const plugin = pluginRegistry.get(pluginId)
  if (plugin) {
    plugin.enabled = false
    console.log(`[PluginSystem] 插件 ${pluginId} 已禁用`)
  }
}

/**
 * 注册插件钩子
 * @param {string} pluginId - 插件ID
 * @param {HookType} hookType - 钩子类型
 * @param {Function} callback - 回调函数
 */
export function registerHook(pluginId, hookType, callback) {
  if (!pluginHooks.has(hookType)) {
    pluginHooks.set(hookType, [])
  }
  pluginHooks.get(hookType).push({ pluginId, callback })
}

/**
 * 触发钩子
 * @param {HookType} hookType - 钩子类型
 * @param {*} data - 传递给钩子的数据
 * @returns {Promise<*>} 钩子处理结果
 */
export async function triggerHook(hookType, data) {
  const hooks = pluginHooks.get(hookType) || []
  let result = data
  
  for (const hook of hooks) {
    const plugin = pluginRegistry.get(hook.pluginId)
    if (!plugin || !plugin.enabled) continue
    
    try {
      const hookResult = await hook.callback(result)
      if (hookResult !== undefined) {
        result = hookResult
      }
    } catch (e) {
      console.error(`[PluginSystem] 钩子 ${hookType} 执行失败 (插件: ${hook.pluginId}):`, e)
    }
  }
  
  return result
}

/**
 * 加载所有已注册的插件
 */
export async function loadAllPlugins() {
  for (const [id, plugin] of pluginRegistry) {
    if (!plugin.enabled) continue
    
    try {
      if (plugin.onLoad) {
        await plugin.onLoad()
      }
      plugin.loaded = true
      plugin.loadedAt = new Date()
      console.log(`[PluginSystem] 插件 ${plugin.name} 加载成功`)
    } catch (e) {
      console.error(`[PluginSystem] 插件 ${id} 加载失败:`, e)
      plugin.loaded = false
    }
  }
}

/**
 * 获取所有已注册的插件
 * @returns {PluginDefinition[]} 插件列表
 */
export function getAllPlugins() {
  return Array.from(pluginRegistry.values())
}

/**
 * 获取启用的插件
 * @returns {PluginDefinition[]} 启用的插件列表
 */
export function getEnabledPlugins() {
  return getAllPlugins().filter(p => p.enabled)
}

/**
 * 检查插件是否存在
 * @param {string} pluginId - 插件ID
 * @returns {boolean} 是否存在
 */
export function hasPlugin(pluginId) {
  return pluginRegistry.has(pluginId)
}

/**
 * 获取插件信息
 * @param {string} pluginId - 插件ID
 * @returns {PluginDefinition|undefined} 插件定义
 */
export function getPlugin(pluginId) {
  return pluginRegistry.get(pluginId)
}

// ==================== 预留的插件扩展点 ====================

/**
 * 卡片类型扩展钩子 - 允许插件添加自定义卡片类型
 * @param {Object} context - 上下文
 * @param {Object} context.projectId - 项目ID
 * @returns {Promise<Array>} 返回自定义卡片类型列表
 */
export async function getCustomCardTypes(context) {
  return triggerHook('getCustomCardTypes', context)
}

/**
 * 卡片字段扩展钩子 - 允许插件添加自定义卡片字段
 * @param {Object} context - 上下文
 * @param {string} context.cardType - 卡片类型
 * @param {Object} context.card - 卡片数据
 * @returns {Promise<Object>} 返回扩展的字段配置
 */
export async function getExtendedCardFields(context) {
  return triggerHook('getExtendedCardFields', context)
}

/**
 * 搜索扩展钩子 - 允许插件扩展搜索功能
 * @param {Object} context - 上下文
 * @param {string} context.query - 搜索关键词
 * @param {Array} context.results - 已有搜索结果
 * @returns {Promise<Array>} 返回扩展的搜索结果
 */
export async function extendSearch(context) {
  return triggerHook('extendSearch', context)
}

/**
 * 导航扩展钩子 - 允许插件添加自定义导航项
 * @param {Array} navItems - 已有导航项
 * @returns {Promise<Array>} 返回扩展的导航项
 */
export async function extendNavigation(navItems) {
  return triggerHook('extendNavigation', navItems)
}

/**
 * 状态扩展钩子 - 允许插件添加自定义状态
 * @param {Object} context - 上下文
 * @param {string} context.cardType - 卡片类型
 * @returns {Promise<Array>} 返回扩展的状态列表
 */
export async function getExtendedStatuses(context) {
  return triggerHook('getExtendedStatuses', context)
}

// ==================== 示例插件定义 ====================

/**
 * 内置示例插件 - 演示插件系统用法
 */
export const examplePlugin = {
  id: 'example-plugin',
  name: '示例插件',
  version: '1.0.0',
  description: '用于演示插件系统的示例插件',
  author: 'BadCase Doctor Team',
  icon: '🧩',
  
  onLoad() {
    console.log('[ExamplePlugin] 插件加载中...')
    
    // 注册卡片类型扩展
    registerHook(this.id, 'getCustomCardTypes', async (context) => {
      console.log('[ExamplePlugin] 卡片类型扩展被调用')
      return [
        { code: 'enhancement', name: '功能增强', icon: '✨', color: '#9c27b0' },
        { code: 'question', name: '问题咨询', icon: '❓', color: '#2196f3' }
      ]
    })
    
    // 注册状态扩展
    registerHook(this.id, 'getExtendedStatuses', async (context) => {
      console.log('[ExamplePlugin] 状态扩展被调用')
      return ['needs_review', 'approved', 'rejected']
    })
    
    console.log('[ExamplePlugin] 插件加载完成')
  },
  
  onUnload() {
    console.log('[ExamplePlugin] 插件已卸载')
  }
}

export default {
  registerPlugin,
  unregisterPlugin,
  enablePlugin,
  disablePlugin,
  registerHook,
  triggerHook,
  loadAllPlugins,
  getAllPlugins,
  getEnabledPlugins,
  hasPlugin,
  getPlugin,
  getCustomCardTypes,
  getExtendedCardFields,
  extendSearch,
  extendNavigation,
  getExtendedStatuses,
  examplePlugin
}
