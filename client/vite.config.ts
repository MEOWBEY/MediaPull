import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { vite as vidstack } from 'vidstack/plugins';
import path from 'path';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit(), vidstack()],
	resolve: {
		alias: {
			$lib: path.resolve('./src/lib')
		}
	}
});
