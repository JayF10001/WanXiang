# import argparse
# import json
# import datetime
# import subprocess
# import yt_dlp
# import os
# from dateutil.relativedelta import relativedelta

# def search_videos(query, max_results=5):
#     """Search for videos with the given query and return their IDs."""
#     current_date = datetime.datetime.now()
#     six_months_ago = current_date - relativedelta(months=6)
#     six_months_ago_str = six_months_ago.strftime("%Y%m%d")
    
#     search_params = {
#         'format': 'bestaudio/best',
#         'quiet': True,
#         'no_warnings': True,
#         'ignoreerrors': True,
#         'extract_flat': True,
#         'playlistend': max_results * 3,  # Get more results to filter later
#         'default_search': 'ytsearch',
#         'dateafter': six_months_ago_str  # Only videos from the last 6 months
#     }
    
#     with yt_dlp.YoutubeDL(search_params) as ydl:
#         search_results = ydl.extract_info(f"ytsearch{max_results*3}:{query}", download=False)
        
#     video_ids = []
#     if search_results and 'entries' in search_results:
#         # Get all video IDs from search results
#         for entry in search_results['entries']:
#             if entry and 'id' in entry:
#                 video_ids.append(entry['id'])
    
#     return video_ids[:max_results]

# def get_video_info_with_subtitles(video_ids):
#     """Get detailed information and subtitles for each video."""
#     results = []
    
#     for video_id in video_ids:
#         video_url = f"https://www.youtube.com/watch?v={video_id}"
        
#         # Options for extracting video info and subtitles
#         ydl_opts = {
#             'writesubtitles': True,
#             'writeautomaticsub': True,
#             'subtitleslangs': ['en', 'zh-Hans', 'zh-Hant'],  # English and Chinese subtitles
#             'skip_download': True,
#             'quiet': True,
#             'no_warnings': True,
#             'ignoreerrors': True,
#         }
        
#         try:
#             with yt_dlp.YoutubeDL(ydl_opts) as ydl:
#                 video_info = ydl.extract_info(video_url, download=False)
                
#             # Extract subtitles separately
#             subtitle_data = {}
#             for lang in ['en', 'zh-Hans', 'zh-Hant']:
#                 subtitle_file = f"{video_id}.{lang}.vtt"
#                 if os.path.exists(subtitle_file):
#                     with open(subtitle_file, 'r', encoding='utf-8') as f:
#                         subtitle_data[lang] = f.read()
#                     # Clean up the subtitle file
#                     os.remove(subtitle_file)
                
#                 # Try auto-generated subtitles if regular ones don't exist
#                 auto_subtitle_file = f"{video_id}.{lang}.auto.vtt"
#                 if os.path.exists(auto_subtitle_file) and lang not in subtitle_data:
#                     with open(auto_subtitle_file, 'r', encoding='utf-8') as f:
#                         subtitle_data[f"{lang}_auto"] = f.read()
#                     # Clean up the subtitle file
#                     os.remove(auto_subtitle_file)
            
#             # Extract important metadata
#             metadata = {
#                 'id': video_info.get('id'),
#                 'title': video_info.get('title'),
#                 'url': video_info.get('webpage_url'),
#                 'upload_date': video_info.get('upload_date'),
#                 'view_count': video_info.get('view_count'),
#                 'like_count': video_info.get('like_count'),
#                 'duration': video_info.get('duration'),
#                 'uploader': video_info.get('uploader'),
#                 'uploader_url': video_info.get('uploader_url'),
#                 'description': video_info.get('description'),
#                 'thumbnail': video_info.get('thumbnail'),
#                 'categories': video_info.get('categories'),
#                 'tags': video_info.get('tags'),
#             }
            
#             # Combine metadata and subtitles
#             video_data = {
#                 'metadata': metadata,
#                 'subtitles': subtitle_data
#             }
            
#             results.append(video_data)
            
#         except Exception as e:
#             print(f"Error processing video {video_id}: {e}")
    
#     # Sort by like count (descending)
#     results.sort(key=lambda x: x['metadata'].get('like_count', 0) or 0, reverse=True)
#     return results

# def main():
#     parser = argparse.ArgumentParser(description='Search YouTube for videos and extract their subtitles and metadata.')
#     parser.add_argument('query', help='The search query')
#     parser.add_argument('--max-results', type=int, default=5, help='Maximum number of results to return')
#     parser.add_argument('--output', default='video_results.json', help='Output JSON file')
    
#     args = parser.parse_args()
    
#     # Check if yt-dlp is installed, if not install it
#     try:
#         import yt_dlp
#     except ImportError:
#         print("Installing yt-dlp...")
#         subprocess.check_call(["pip", "install", "yt-dlp", "python-dateutil"])
#         # Reimport after installation
#         import yt_dlp
    
#     print(f"Searching for videos related to: {args.query}")
#     video_ids = search_videos(args.query, args.max_results)
    
#     if not video_ids:
#         print("No videos found.")
#         return
    
#     print(f"Found {len(video_ids)} videos. Gathering detailed information and subtitles...")
#     video_results = get_video_info_with_subtitles(video_ids)
    
#     # Save results to JSON file
#     with open(args.output, 'w', encoding='utf-8') as f:
#         json.dump(video_results, f, ensure_ascii=False, indent=2)
    
#     print(f"Results saved to {args.output}")

# if __name__ == "__main__":
#     main() 