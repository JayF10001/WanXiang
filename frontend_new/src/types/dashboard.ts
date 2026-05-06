export type CommandCenterDistributionItem = {
  name: string;
  value: number;
};

export type CommandCenterEvent = {
  id: string;
  title: string;
  introduction: string;
  type: string;
  x: number;
  y: number;
  platform: string;
  rank: number;
  participants: number;
  spreadSpeed: number;
  spreadRange: number;
  emotion?: {
    schema?: Record<string, number>;
    rationale?: string;
  };
  stance?: {
    schema?: Record<string, number>;
    rationale?: string;
  };
  heatTrend?: Array<{
    date: string;
    value: number;
  }>;
  timeline?: Array<{
    date: string;
    event: string;
  }>;
  wordCloud?: Array<{
    word: string;
    weight: number;
  }>;
  primarySentiment: 'positive' | 'neutral' | 'negative';
};

export type CommandCenterData = {
  summary: {
    totalEvents: number;
    negativeEvents: number;
    positiveEvents: number;
    neutralEvents: number;
    avgSpreadRange: number;
    avgSpreadSpeed: number;
    platformDistribution: CommandCenterDistributionItem[];
    sentimentDistribution: CommandCenterDistributionItem[];
  };
  events: CommandCenterEvent[];
};
