import { Link } from '@tanstack/react-router';
import { EmptyState } from '@/design/primitives';
import { tr } from '@/i18n/tr';

export function NotFound() {
  return (
    <div style={{ padding: 32 }}>
      <EmptyState title={tr.home.notFound} actions={<Link to="/">{tr.home.backHome}</Link>}>
        {tr.home.notFoundText}
      </EmptyState>
    </div>
  );
}
