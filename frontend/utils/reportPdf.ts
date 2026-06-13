export type ReportFileExt = 'pdf' | 'txt' | 'unsupported';

export function detectReportFileExt(url: string): ReportFileExt {
  const path = (url || '').split('?')[0].split('#')[0].toLowerCase();
  if (path.endsWith('.pdf')) return 'pdf';
  if (path.endsWith('.txt')) return 'txt';
  return 'unsupported';
}

export function getReportOpenFileType(ext: ReportFileExt): 'pdf' | undefined {
  return ext === 'pdf' ? 'pdf' : undefined;
}

export function safeReportFileName(name: string, ext: ReportFileExt): string {
  const clean = (name || '测品报告')
    .replace(/[\\/:*?"<>|\r\n\t]+/g, '_')
    .replace(/\s+/g, '_')
    .replace(/^[._\s]+|[._\s]+$/g, '')
    .slice(0, 60) || '测品报告';
  return `${clean}.${ext}`;
}

export function isPdfHeader(input: ArrayBuffer | string | null | undefined): boolean {
  if (!input) return false;
  if (typeof input === 'string') return input.startsWith('%PDF-');

  const bytes = new Uint8Array(input.slice(0, 5));
  const expected = [37, 80, 68, 70, 45]; // %PDF-
  return expected.every((value, index) => bytes[index] === value);
}

export function previewFileHeader(input: ArrayBuffer | string | null | undefined): string {
  if (!input) return '';
  if (typeof input === 'string') return input.slice(0, 32);
  const bytes = new Uint8Array(input.slice(0, 32));
  return Array.from(bytes)
    .map(byte => (byte >= 32 && byte <= 126 ? String.fromCharCode(byte) : '.'))
    .join('');
}
