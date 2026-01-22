import { ref, onMounted, onUnmounted } from 'vue'

/**
 * Throttle function to limit execution rate
 * @param {Function} fn - Function to throttle
 * @param {number} wait - Wait time in ms
 * @returns {Function} Throttled function
 */
function throttle(fn, wait) {
  let lastTime = 0
  return function (...args) {
    const now = Date.now()
    if (now - lastTime >= wait) {
      lastTime = now
      fn.apply(this, args)
    }
  }
}

/**
 * Composable для отслеживания размера экрана
 * @param {number} breakpoint - Точка перелома (по умолчанию 768)
 * @returns {{ isMobile: import('vue').Ref<boolean> }}
 */
export function useResponsive(breakpoint = 768) {
  const isMobile = ref(window.innerWidth <= breakpoint)

  const updateMobile = () => {
    isMobile.value = window.innerWidth <= breakpoint
  }

  // Throttle resize handler to 100ms for better performance
  const throttledUpdate = throttle(updateMobile, 100)

  onMounted(() => window.addEventListener('resize', throttledUpdate))
  onUnmounted(() => window.removeEventListener('resize', throttledUpdate))

  return { isMobile }
}
