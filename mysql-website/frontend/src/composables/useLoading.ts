import { ref, onMounted, onUnmounted } from 'vue'

/**
 * Composable for handling loading state
 */
export function useLoading(initialState = false) {
  const isLoading = ref(initialState)
  
  const start = () => {
    isLoading.value = true
  }
  
  const stop = () => {
    isLoading.value = false
  }
  
  return {
    isLoading,
    start,
    stop
  }
}

/**
 * Composable for handling window resize
 */
export function useWindowSize() {
  const width = ref(window.innerWidth)
  const height = ref(window.innerHeight)
  
  const handleResize = () => {
    width.value = window.innerWidth
    height.value = window.innerHeight
  }
  
  onMounted(() => {
    window.addEventListener('resize', handleResize)
  })
  
  onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
  })
  
  return {
    width,
    height,
    isMobile: () => width.value < 768,
    isTablet: () => width.value >= 768 && width.value < 992,
    isDesktop: () => width.value >= 992
  }
}

/**
 * Composable for scroll position
 */
export function useScroll() {
  const scrollY = ref(0)
  const scrollX = ref(0)
  
  const handleScroll = () => {
    scrollY.value = window.scrollY
    scrollX.value = window.scrollX
  }
  
  onMounted(() => {
    window.addEventListener('scroll', handleScroll)
  })
  
  onUnmounted(() => {
    window.removeEventListener('scroll', handleScroll)
  })
  
  return {
    scrollY,
    scrollX,
    isScrolled: (threshold = 0) => scrollY.value > threshold
  }
}

/**
 * Composable for async data fetching
 */
export function useAsyncData<T>(asyncFn: () => Promise<T>) {
  const data = ref<T | null>(null)
  const error = ref<Error | null>(null)
  const { isLoading, start, stop } = useLoading()
  
  const execute = async () => {
    start()
    try {
      data.value = await asyncFn()
      error.value = null
    } catch (e) {
      error.value = e as Error
    } finally {
      stop()
    }
  }
  
  return {
    data,
    error,
    isLoading,
    execute
  }
}
