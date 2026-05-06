export type RagAnswerSource = {
  title?: string;
  url?: string;
  sourceType?: string;
  snippet?: string;
  summary?: string;
  credibility?: string;
  publishedAt?: string;
  citationCount?: number;
  score?: number;
  keywordScore?: number;
  vectorScore?: number;
  record?: {
    province?: string;
    ticketNo?: string;
    schoolName?: string;
    studentName?: string;
    subjectName?: string;
    groupName?: string;
    award?: string;
    qualifiedForFinal?: boolean | null;
    qualifiedForFinalLabel?: string;
  };
};

export type RagAnswerCitation = {
  id?: string;
  title?: string;
  sourceTitle?: string;
  sourceUrl?: string;
  quote?: string;
  sourceType?: string;
  credibility?: string;
  publishedAt?: string;
  sourceId?: string;
  fileId?: string;
  score?: number;
  keywordScore?: number;
  vectorScore?: number;
  record?: {
    province?: string;
    ticketNo?: string;
    schoolName?: string;
    studentName?: string;
    subjectName?: string;
    groupName?: string;
    award?: string;
    qualifiedForFinal?: boolean | null;
    qualifiedForFinalLabel?: string;
  };
};

export type RagAnswerResult = {
  answer?: string;
  facts?: string[];
  toVerify?: string[];
  analysis?: string[];
  sources?: RagAnswerSource[];
  citations?: RagAnswerCitation[];
  confidence?: string;
  groundingStatus?: string;
  usedRealtimeRetrieval?: boolean;
  structuredRecordCount?: number;
  structuredAggregations?: {
    totalMatchedCount?: number;
    finalistCount?: number;
    uniqueSchoolCount?: number;
    countsBySchool?: Array<{ name?: string; count?: number }>;
    countsByAward?: Array<{ name?: string; count?: number }>;
    countsBySubject?: Array<{ name?: string; count?: number }>;
    countsByGroup?: Array<{ name?: string; count?: number }>;
  };
  structuredRecords?: Array<{
    sourceId?: string;
    fileId?: string;
    title?: string;
    score?: number;
    keywordScore?: number;
    vectorScore?: number;
    record?: {
      province?: string;
      ticketNo?: string;
      schoolName?: string;
      studentName?: string;
      subjectName?: string;
      groupName?: string;
      award?: string;
      qualifiedForFinal?: boolean | null;
      qualifiedForFinalLabel?: string;
    };
  }>;
};
