<script lang="ts" module>
  import { BarChart, LineChart } from 'echarts/charts'
  import {
    GridComponent,
    MarkLineComponent,
    TitleComponent,
    TooltipComponent,
  } from 'echarts/components'
  import * as echarts from 'echarts/core'
  import { LabelLayout } from 'echarts/features'
  import { CanvasRenderer } from 'echarts/renderers'

  echarts.use([
    BarChart,
    LineChart,
    GridComponent,
    MarkLineComponent,
    TitleComponent,
    TooltipComponent,
    LabelLayout,
    CanvasRenderer,
  ])

  /** Colours a chart may use, read from the page's CSS variables so light and dark stay in one place. */
  const INK_KEYS = [
    'surface', 'text', 'text-2', 'muted', 'grid', 'axis',
    'series-1', 'series-2', 'series-3', 'series-4', 'series-5', 'radiant', 'dire',
  ] as const // prettier-ignore
  export type Ink = Record<(typeof INK_KEYS)[number], string>
</script>

<script lang="ts">
  import type { EChartsCoreOption } from 'echarts/core'
  import { onMount } from 'svelte'

  let { option, label, height = 320 }: { option: (ink: Ink) => EChartsCoreOption; label: string; height?: number } =
    $props()

  let el: HTMLDivElement
  const scheme = matchMedia('(prefers-color-scheme: dark)')
  let dark = $state(scheme.matches)

  onMount(() => {
    const chart = echarts.init(el)
    const resize = new ResizeObserver(() => chart.resize())
    resize.observe(el)
    const onScheme = () => (dark = scheme.matches)
    scheme.addEventListener('change', onScheme)
    return () => {
      scheme.removeEventListener('change', onScheme)
      resize.disconnect()
      chart.dispose()
    }
  })

  $effect(() => {
    dark // the CSS variables change with the colour scheme, so read them again
    const css = getComputedStyle(el)
    const ink = Object.fromEntries(INK_KEYS.map((k) => [k, css.getPropertyValue(`--${k}`).trim()])) as Ink
    echarts.getInstanceByDom(el)?.setOption(option(ink), true)
  })
</script>

<div bind:this={el} role="img" aria-label={label} style:height="{height}px"></div>
