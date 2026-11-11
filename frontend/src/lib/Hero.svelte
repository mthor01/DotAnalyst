<script lang="ts">
  import { heroIcon, heroName } from './constants.svelte'

  let { id }: { id: number } = $props()
</script>

<span class="hero">
  {#if heroIcon(id)}<img src={heroIcon(id)} alt="" width="20" height="20" loading="lazy" />{/if}
  {heroName(id)}
</span>

<style>
  .hero {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
</style>
