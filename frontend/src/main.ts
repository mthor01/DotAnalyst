import { mount } from 'svelte'
import App from './App.svelte'
import './app.css'

// charts draw their text on a canvas once, so the font has to be there before the first one renders
document.fonts.load('14px Archivo').finally(() => mount(App, { target: document.getElementById('app')! }))
