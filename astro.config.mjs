// @ts-check
import { defineConfig } from 'astro/config';

// Deployed as a GitHub Pages project site:
// https://junyu-jiang0508.github.io/communication_phd/
export default defineConfig({
  site: 'https://junyu-jiang0508.github.io',
  base: '/communication_phd',
  trailingSlash: 'always',
  build: {
    format: 'directory',
  },
});
