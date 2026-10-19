/**
 * METIS'in yayınlandığı alt yol (ör. '/metis'; kökteyse ''). Sunucu index.html'e `<base href="/metis/">` yazar; arayüz
 * göreli yollarla derlendiği için aynı paket hem kökte hem bir alt yolda çalışır (çok amaçlı sunucu, 2026-10-19).
 */
export const BASE_PATH = (document.querySelector('base')?.getAttribute('href') ?? '/').replace(/\/+$/, '');

/** API adresi: apiUrl('/attachments/1/download') → '/metis/api/v1/attachments/1/download'. */
export const apiUrl = (path: string) => `${BASE_PATH}/api/v1${path}`;
