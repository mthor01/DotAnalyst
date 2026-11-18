<script lang="ts">
  import { heroName, heroPortrait } from './constants.svelte'
  let { id }: { id: number } = $props()
</script>

<!-- the picture, named on hover; the name as text only when there is no picture -->
{#if heroPortrait(id)}
  <img class="hero" src={heroPortrait(id)} alt={heroName(id)} title={heroName(id)} width="44" height="25" loading="lazy" />
{:else}
  {heroName(id)}
{/if}

<style>
  .hero {
    display: inline-block;
    vertical-align: middle;
    object-fit: cover;
    border-radius: 3px;
  }
</style>
