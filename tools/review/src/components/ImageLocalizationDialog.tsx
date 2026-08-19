import { useEffect, useMemo, useRef, useState } from 'react';
import { buildMediaRaw } from '../lib/media';

const CDN_UPLOAD_STORAGE_KEY = 'review.cdnUploadPage';

interface ImageLocalizationDialogProps {
  open: boolean;
  sourceUrl: string;
  sourceAlt: string;
  initialCdnUrl: string;
  initialEnglishAlt: string;
  templateRaw: string;
  targetExists: boolean;
  onSubmit: (raw: string) => void;
  onCancel: () => void;
}

function isSafeHttpUrl(value: string): boolean {
  return /^https?:\/\/\S+$/i.test(value.trim());
}

function generationInstruction(sourceUrl: string): string {
  return [
    '将这张宜搭中文产品截图转换为英文版。',
    '保持原图尺寸、布局、颜色、图标和交互状态，只替换图中可见的中文文字。',
    '英文文案要符合宜搭产品术语，并检查截图中不含手机号、邮箱、token、二维码、UID 等敏感信息。',
    `原图：${sourceUrl}`,
  ].join('\n');
}

async function copyText(value: string): Promise<void> {
  await navigator.clipboard.writeText(value);
}

export function ImageLocalizationDialog({
  open,
  sourceUrl,
  sourceAlt,
  initialCdnUrl,
  initialEnglishAlt,
  templateRaw,
  targetExists,
  onSubmit,
  onCancel,
}: ImageLocalizationDialogProps) {
  const [cdnUrl, setCdnUrl] = useState('');
  const [englishAlt, setEnglishAlt] = useState('');
  const [uploadPage, setUploadPage] = useState('');
  const [copied, setCopied] = useState<string | null>(null);
  const cdnRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setCdnUrl(initialCdnUrl);
    setEnglishAlt(initialEnglishAlt || sourceAlt);
    setUploadPage(window.localStorage.getItem(CDN_UPLOAD_STORAGE_KEY) ?? '');
    setCopied(null);
    queueMicrotask(() => cdnRef.current?.focus());
  }, [open, initialCdnUrl, initialEnglishAlt, sourceAlt]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  const previewRaw = useMemo(
    () => cdnUrl.trim() ? buildMediaRaw('image', cdnUrl, englishAlt, templateRaw) : '',
    [cdnUrl, englishAlt, templateRaw],
  );

  if (!open) return null;

  const canSubmit = isSafeHttpUrl(cdnUrl);
  const rememberUploadPage = (value: string) => {
    setUploadPage(value);
    if (value.trim()) window.localStorage.setItem(CDN_UPLOAD_STORAGE_KEY, value.trim());
    else window.localStorage.removeItem(CDN_UPLOAD_STORAGE_KEY);
  };
  const markCopied = (key: string, value: string) => {
    void copyText(value).then(() => {
      setCopied(key);
      window.setTimeout(() => setCopied((current) => current === key ? null : current), 1200);
    });
  };

  return (
    <div className="dialog-mask" onClick={onCancel}>
      <div className="dialog image-localization-dialog" role="dialog" onClick={(event) => event.stopPropagation()}>
        <h3 className="dialog-title">英文图片本地化</h3>
        <div className="localization-status">
          {targetExists ? '已定位到英文图片，提交后将替换' : '英文侧缺图，提交后将按中文位置插入'}
        </div>

        <div className="localization-source">
          <img src={sourceUrl} alt={sourceAlt || '待本地化的中文截图'} />
          <div className="localization-source-actions">
            <button type="button" className="btn btn-ghost" onClick={() => markCopied('source', sourceUrl)}>
              {copied === 'source' ? '已复制' : '复制原图地址'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => markCopied('prompt', generationInstruction(sourceUrl))}
            >
              {copied === 'prompt' ? '已复制' : '复制生成任务'}
            </button>
          </div>
        </div>

        <ol className="localization-steps">
          <li>使用 Codex 按原图布局生成英文截图，并完成隐私检查。</li>
          <li>在团队 CDN 网页上传英文图，获取公网地址。</li>
          <li>将 CDN 地址粘贴到下方，提交并保存英文文档。</li>
        </ol>

        <label className="insert-dialog-field">
          <span className="insert-dialog-field-label">CDN 上传页（仅保存在当前浏览器）</span>
          <div className="localization-inline-field">
            <input
              type="url"
              className="insert-dialog-input"
              value={uploadPage}
              onChange={(event) => rememberUploadPage(event.target.value)}
              placeholder="https://..."
              spellCheck={false}
            />
            <button
              type="button"
              className="btn btn-ghost"
              disabled={!isSafeHttpUrl(uploadPage)}
              onClick={() => window.open(uploadPage.trim(), '_blank', 'noopener,noreferrer')}
            >
              打开上传页
            </button>
          </div>
        </label>

        <label className="insert-dialog-field">
          <span className="insert-dialog-field-label">英文图片 CDN 地址<span className="insert-dialog-required">*</span></span>
          <input
            ref={cdnRef}
            type="url"
            className="insert-dialog-input"
            value={cdnUrl}
            onChange={(event) => setCdnUrl(event.target.value)}
            placeholder="https://..."
            spellCheck={false}
          />
        </label>

        <label className="insert-dialog-field">
          <span className="insert-dialog-field-label">英文 alt</span>
          <input
            type="text"
            className="insert-dialog-input"
            value={englishAlt}
            onChange={(event) => setEnglishAlt(event.target.value)}
            placeholder="Describe the screenshot in English"
            spellCheck={false}
          />
        </label>

        <div className="insert-dialog-preview-label">将写入英文 MDX</div>
        <pre className="insert-dialog-preview">{previewRaw || '（填入 CDN 地址后预览）'}</pre>

        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>取消</button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canSubmit}
            onClick={() => canSubmit && onSubmit(previewRaw)}
          >
            {targetExists ? '替换英文图' : '插入英文图'}
          </button>
        </div>
      </div>
    </div>
  );
}
