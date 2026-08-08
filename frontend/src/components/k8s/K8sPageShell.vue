<template>
  <div class="fade-in workbench-page-shell k8s-page-shell">
    <section class="hero panel k8s-hero">
      <div class="release-hero-copy">
        <div class="release-hero-title-row release-hero-title-inline">
          <span class="release-header-icon k8s-header-icon"><el-icon><component :is="icon" /></el-icon></span>
          <h2>{{ title }}</h2>
          <p class="subtitle inline-subtitle k8s-hero-desc">{{ desc }}</p>
        </div>
      </div>
    </section>

    <div v-if="cards.length" class="audit-grid k8s-top-stats">
      <div
        v-for="card in cards"
        :key="card.label"
        class="audit-card audit-card--inline k8s-summary-card"
        :class="card.tone"
      >
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-value">{{ card.value }}</div>
      </div>
    </div>

    <slot />
  </div>
</template>

<script setup>
import '@/assets/k8s.css'

defineProps({
  title: { type: String, required: true },
  desc: { type: String, default: '' },
  icon: { type: String, default: 'Monitor' },
  cards: { type: Array, default: () => [] },
})
</script>
