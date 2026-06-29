export type Lang = 'en' | 'zh' | 'ja';

export const ALL_LANGS: Lang[] = ['en', 'zh', 'ja'];

export const LANG_LABEL: Record<Lang, string> = {
  en: '英文（en）',
  zh: '中文（zh）',
  ja: '日文（ja）',
};

/** A single proofreading unit: one tab inside one product, identified by its
 *  position key `p{productIdx}t{tabIdx}` (stable across localized tab names). */
export interface ProductTab {
  key: string;
  product: string;
  tab: string;
}

export interface NavPage {
  type: 'page';
  /** Canonical en-relative slug, e.g. `im/chats-overview`. */
  slug: string;
  titleLeft?: string;
  titleRight?: string;
  missing?: boolean;
}

export interface NavGroup {
  type: 'group';
  titleLeft: string;
  titleRight?: string;
  children: NavNode[];
}

export type NavNode = NavPage | NavGroup;

export type BlockType =
  | 'frontmatter'
  | 'heading'
  | 'paragraph'
  | 'list'
  | 'blockquote'
  | 'code'
  | 'thematicBreak'
  | 'mdxJsxFlow'
  | 'mdxEsm'
  | 'mdxExpression'
  | 'table'
  | 'unknown';

export interface Block {
  id: string;
  type: BlockType;
  raw: string;
  startOffset: number;
  endOffset: number;
  editable: boolean;
  depth?: number;
}

export interface FrontmatterMeta {
  title?: string;
  description?: string;
  rest: Record<string, string>;
  raw: string;
  startOffset: number;
  endOffset: number;
}

export interface PageContent {
  path: string;
  content: string;
  blocks: Block[];
  frontmatter: FrontmatterMeta | null;
}

export interface PageBundle {
  slug: string;
  leftLang: Lang;
  rightLang: Lang;
  /** null when the file for that language does not exist (untranslated). */
  left: PageContent | null;
  right: PageContent | null;
}

export interface ApiError {
  error: string;
}
