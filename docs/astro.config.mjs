// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
	// Production is served from the public repository at the domain root, so no
	// base path. The domain comes from that repo's Pages settings, not a CNAME.
	// docs-preview.yml overrides both for this repo's github.io project site.
	site: process.env.DOCS_SITE || 'https://actionsmanager.io',
	base: process.env.DOCS_BASE || '/',
	// Emit /path.html: the URL shape the site has always had (url-parity.txt).
	build: { format: 'file' },
	integrations: [
		starlight({
			title: 'ActionsManager Documentation',
			// The ActionsManager shield as the favicon; the header lockup
			// (shield + two-tone wordmark) is the SiteTitle override.
			favicon: '/shield-icon-transparent.svg',
			components: {
				SiteTitle: './src/components/SiteTitle.astro',
				Footer: './src/components/Footer.astro',
				PageTitle: './src/components/PageTitle.astro',
				SocialIcons: './src/components/SocialIcons.astro',
			},
			// Edits go to the public repository, whose docs/ is this site - the
			// private one 404s for readers.
			editLink: { baseUrl: 'https://github.com/dawg-io/actions-manager/edit/main/docs/' },
			// The public repository - the one a docs reader can open.
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/dawg-io/actions-manager' },
			],
			customCss: ['./src/styles/theme.css'],
			// Concepts is deliberately absent until its pages exist (#2075).
			sidebar: [
				{
					label: 'Getting Started',
					items: [
						'getting-started/quick-start',
						'getting-started/installation',
						'getting-started/github-pat-setup',
						'getting-started/github-oauth-setup',
						'getting-started/first-workflow-walkthrough',
						'getting-started/https-setup',
						'getting-started/product-demo',
					],
				},
				{
					label: 'Guides',
					items: [
						'features/projects',
						'features/workflows',
						'features/reusable-workflows',
						'features/reusable-workflow-repository-setup',
						'features/pr-campaigns',
						'features/drift-detection',
						'features/managed-actions',
						'features/rulesets',
						'features/backup-restore',
						'features/permissions',
					],
				},
				{
					label: 'Operations',
					items: ['features/build-detection', 'features/build-metrics', 'features/notifications'],
				},
				{
					label: 'Security',
					items: ['security/security', 'security/privacy', 'security/token-handling'],
				},
				{
					label: 'Troubleshooting',
					items: [
						'troubleshooting/common-errors',
						'troubleshooting/github-permissions',
						'troubleshooting/container-startup',
					],
				},
				{
					label: 'Beta',
					items: ['beta/beta-notes'],
				},
			],
		}),
	],
});
