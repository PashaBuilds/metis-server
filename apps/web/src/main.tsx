import '@fontsource/ibm-plex-sans/latin-ext-400.css';
import '@fontsource/ibm-plex-sans/latin-ext-500.css';
import '@fontsource/ibm-plex-sans/latin-ext-600.css';
import '@fontsource/ibm-plex-sans/latin-400.css';
import '@fontsource/ibm-plex-sans/latin-500.css';
import '@fontsource/ibm-plex-sans/latin-600.css';
import '@fontsource/ibm-plex-sans/latin-400-italic.css';
import '@fontsource/ibm-plex-mono/latin-ext-400.css';
import '@fontsource/ibm-plex-mono/latin-400.css';
import '@fontsource/ibm-plex-mono/latin-500.css';
import './design/tokens.css';
import './design/global.css';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ToastProvider, TooltipProvider } from './design/primitives';
import { IzProvider } from './design/iz';
import { ApiError, api } from './lib/api/client';
import type { EvidenceResolver, EvidenceView } from './design/iz';
import { SessionProvider } from './app/session';
import { ThemeSync } from './app/theme';
import { router } from './app/router';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => !(error instanceof ApiError && error.status > 0 && error.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
});

const resolveEvidence: EvidenceResolver = (target) => api.get<EvidenceView>(`/evidence/${target.evidenceId}`, { claim_id: target.claimId });

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <ThemeSync />
        <TooltipProvider>
          <ToastProvider>
            <IzProvider resolver={resolveEvidence}>
              <RouterProvider router={router} />
            </IzProvider>
          </ToastProvider>
        </TooltipProvider>
      </SessionProvider>
    </QueryClientProvider>
  </StrictMode>,
);
