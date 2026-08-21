import type { Lang } from './types';

export type BatchMediaKind = 'raster' | 'gif' | 'svg' | 'video' | 'unknown';
export type BatchItemStatus =
  | 'pending'
  | 'prepared'
  | 'generated'
  | 'mapped'
  | 'completed'
  | 'skipped'
  | 'needs_review';

export interface BatchTargetLocation {
  mode: 'replace' | 'insert';
  currentUrl?: string;
}

export interface BatchPreparedAsset {
  sourcePath: string;
  outputPath: string;
  framePaths?: string[];
  svgTexts?: string[];
}

export interface BatchImageItem {
  id: string;
  order: number;
  slug: string;
  sourceUrl: string;
  sourceAlt: string;
  sourceFormat: string;
  mediaKind: BatchMediaKind;
  target: BatchTargetLocation;
  duplicateOf?: string;
  sourceHash?: string;
  status: BatchItemStatus;
  privacyReview: boolean;
  privacyFindings?: string[];
  complexityReasons: string[];
  prompt: string;
  prepared?: BatchPreparedAsset;
  localOutput?: string;
  cdnUrl?: string;
  englishAlt?: string;
  note?: string;
}

export interface BatchImageStats {
  total: number;
  pending: number;
  prepared: number;
  generated: number;
  mapped: number;
  completed: number;
  skipped: number;
  needsReview: number;
  duplicates: number;
  byKind: Record<BatchMediaKind, number>;
}

export interface BatchImageJob {
  version: 2;
  key: string;
  scope: string;
  sourceLang: Lang;
  targetLang: Lang;
  createdAt: string;
  updatedAt: string;
  items: BatchImageItem[];
  stats: BatchImageStats;
}

export interface BatchMappingInput {
  id: string;
  cdnUrl?: string;
  englishAlt?: string;
  localOutput?: string;
  status?: BatchItemStatus;
  note?: string;
}

export interface BatchApplyResult {
  dryRun?: boolean;
  changedFiles: string[];
  appliedIds: string[];
  skipped: Array<{ id: string; reason: string }>;
}
