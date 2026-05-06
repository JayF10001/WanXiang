#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
from datetime import datetime
import json

# 确保能够导入项目模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.video_service import VideoService

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='新闻视频处理工具')
    parser.add_argument('news_title', help='新闻标题')
    parser.add_argument('--search-only', action='store_true', help='仅搜索视频而不下载')
    parser.add_argument('--output', '-o', help='输出结果到JSON文件')
    parser.add_argument('--platform', '-p', choices=['youtube', 'bilibili', 'all'], default='all', 
                      help='指定视频平台，默认为all')
    
    args = parser.parse_args()
    
    print(f"开始处理新闻标题: {args.news_title}")
    
    if args.search_only:
        # 仅搜索视频
        if args.platform == 'youtube':
            videos = VideoService._search_youtube_videos(args.news_title)
        elif args.platform == 'bilibili':
            videos = VideoService.search_bilibili_videos(args.news_title)
        else:
            videos = VideoService.search_video_by_news_title(args.news_title)
            
        result = {
            "timestamp": datetime.now().isoformat(),
            "news_title": args.news_title,
            "search_results": videos,
            "count": len(videos),
            "platform": args.platform
        }
    else:
        # 完整处理流程
        result = VideoService.process_news_video(args.news_title, platform=args.platform)
        result["timestamp"] = datetime.now().isoformat()
        result["news_title"] = args.news_title
    
    # 输出结果
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 