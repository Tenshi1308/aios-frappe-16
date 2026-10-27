import DOMPurify from 'dompurify';
import MarkdownIt from 'markdown-it';

/**
 * Renderer markdown untuk bubble chat dan pratinjau artefak.
 * - HTML mentah DINONAKTIFKAN (html: false) sehingga teks dari model tidak
 *   bisa menyuntikkan elemen <script>/<iframe>.
 * - Output disanitasi lagi dengan DOMPurify sebagai lapis kedua sebelum
 *   dipasang lewat v-html (persetujuan owner #12 fase 2b, guard no-v-html lama
 *   diganti dengan pasangan ini).
 */
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
});

export function renderMarkdown(text: string): string {
  const html = md.render(text ?? '');
  return DOMPurify.sanitize(html, { ADD_ATTR: ['target'] });
}
