export type ImageAutomationStage =
  | 'queued'
  | 'scanning'
  | 'preparing'
  | 'generating'
  | 'quality_check'
  | 'uploading'
  | 'applying'
  | 'verifying'
  | 'awaiting_auth'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type ImageAutomationItemStatus =
  | 'queued'
  | 'prepared'
  | 'deferred'
  | 'generating'
  | 'generated'
  | 'quality_passed'
  | 'quality_failed'
  | 'mapped'
  | 'applied'
  | 'failed';

export interface ImageAutomationItem {
  id: string;
  slug: string;
  sourceUrl: string;
  status: ImageAutomationItemStatus;
  reason?: string;
  sourcePath?: string;
  outputPath?: string;
  cdnUrl?: string;
  attempts: number;
}

export interface ImageAutomationStats {
  discovered: number;
  eligible: number;
  deferred: number;
  generated: number;
  qualityPassed: number;
  mapped: number;
  applied: number;
  failed: number;
}

export interface ImageAutomationJob {
  version: 1;
  id: string;
  scope: string;
  stage: ImageAutomationStage;
  createdAt: string;
  updatedAt: string;
  startedAt?: string;
  finishedAt?: string;
  cancelRequested?: boolean;
  currentItemId?: string;
  message: string;
  error?: string;
  stats: ImageAutomationStats;
  items: ImageAutomationItem[];
  changedFiles: string[];
  events: Array<{ at: string; stage: ImageAutomationStage; message: string }>;
}

export interface StartImageAutomationInput {
  scope: string;
  uploadPage?: string;
  maxItems?: number;
  force?: boolean;
  planOnly?: boolean;
}
