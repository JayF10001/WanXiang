export type KnowledgeBase = {
  id: string;
  name: string;
  description: string;
  scope: string;
  ownerUserId: string;
  createdAt: string;
  updatedAt: string;
};

export type KnowledgeFile = {
  id: string;
  kbId: string;
  ownerUserId: string;
  originalFilename: string;
  filename: string;
  contentType: string;
  size: number;
  storagePath: string;
  sha256: string;
  status: string;
  parseStatus: string;
  parseError?: string | null;
  indexStatus?: string;
  indexError?: string | null;
  chunkCount?: number;
  structuredRecordCount?: number;
  indexedAt?: string;
  parserVersion?: string;
  splitterVersion?: string;
  embeddingVersion?: string;
  structuredParserVersion?: string;
  parseSummary?: {
    fileType?: string;
    contentType?: string;
    extractMode?: string;
    charCount?: number;
    lineCount?: number;
    rowCount?: number;
    columnCount?: number;
    preview?: string;
  };
  uploadSource: string;
  remark?: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
};
