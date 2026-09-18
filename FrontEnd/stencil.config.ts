import { Config } from '@stencil/core';

export const config: Config = {
  namespace: 'quill-components',
  devServer: {
    reloadStrategy: 'pageReload',
    basePath: "/www"
  },
  outputTargets: [
    {
      type: 'dist',
      esmLoaderPath: '../loader',
    },
    {
      type: 'dist-custom-elements',
    },
    {
      type: 'docs-readme',
    },
    {
      type: 'www',
      // Must match the real directory name exactly. Lowercase '../backend/www'
      // resolves fine on case-insensitive filesystems (Windows, default macOS)
      // but creates a separate 'backend/' tree on Linux, leaving the real
      // BackEnd/www/ - the one FastAPI serves - untouched by the build.
      dir: '../BackEnd/www',
      serviceWorker: null,
      copy: [
        { src: 'includes', dest: 'includes' }
      ]
    },
  ],
  buildEs5: 'prod',
  testing: {
    collectCoverage: true,
    coverageThreshold: {
      global: {
        branches: 80,
        functions: 80,
        lines: 80,
      },
    },
  },
};
