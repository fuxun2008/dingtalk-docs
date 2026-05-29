export type Lang = 'en' | 'zh' | 'ja';

export interface NavPage {
  type: 'page';
  slug: string;
  titleZh?: string;
  titleEn?: string;
  missing?: boolean;
}

export interface NavGroup {
  type: 'group';
  titleEn: string;
  titleZh?: string;
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
  en: PageContent;
  zh: PageContent;
}

export interface ApiError {
  error: string;
}
