import { FileCode2, FileText, FlaskConical, Image, NotebookPen, Table2 } from 'lucide-react';

export function SourceKindIcon({ kind, size = 16 }: { kind: string; size?: number }) {
  const props = { size, 'aria-hidden': true } as const;
  switch (kind) {
    case 'code':
      return <FileCode2 {...props} />;
    case 'document':
      return <FileText {...props} />;
    case 'image':
      return <Image {...props} />;
    case 'table':
      return <Table2 {...props} />;
    case 'test':
      return <FlaskConical {...props} />;
    default:
      return <NotebookPen {...props} />;
  }
}
