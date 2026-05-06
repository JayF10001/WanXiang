#!/usr/bin/env python
# -*- coding: utf-8 -*-
#python ChatBackend/youtube.py --titles "热点新闻" "科技新闻"
import os
import sys
import json
import argparse
import tempfile
import datetime
import shutil
import subprocess
from typing import List, Dict, Any, Optional, Tuple
import yt_dlp
import time
from dateutil.relativedelta import relativedelta
from dateutil import parser as date_parser

def search_and_get_subtitles(titles, max_results=1, cookies_path=None, output_file=None):
    """
    搜索最近一年内观看量最高的视频，并获取中文VTT字幕和视频信息。
    如果最高观看量的视频不可用或无中文字幕，则尝试次高者，以此类推。

    Args:
        titles: 标题列表
        max_results: 每个标题返回的最大结果数 (基于观看量筛选)
        cookies_path: cookies路径
        output_file: 输出文件路径
    """
    results = {}

    # ---> Adjust date filter to last 1 year <-----
    one_year_ago = datetime.datetime.now() - relativedelta(years=1)
    one_year_ago_str = one_year_ago.strftime('%Y%m%d')
    # ---> End of date filter adjustment <---------

    for title in titles:
        print(f"搜索标题: {title} (最近一年)")
        title_results = []

        try:
            # 设置yt-dlp选项 for initial search (filter by date, request VTT)
            ydl_opts = {
                'quiet': False,
                'ignoreerrors': True,
                'extract_flat': 'in_playlist',
                'playlistend': max_results * 5, # Fetch more results initially to sort by views later
                # ---> Update dateafter and subtitlesformat <-----
                'dateafter': one_year_ago_str,
                'format': 'best',
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['zh-Hans', 'zh-CN', 'zh', 'en'],
                'subtitlesformat': 'vtt', # Request VTT format
                'outtmpl': '%(id)s.%(ext)s',
                 # ---> End of update <---------------------------
            }

            # 添加cookies认证
            if cookies_path:
                ydl_opts['cookies_from_browser'] = cookies_path

            # 首先搜索视频 (get potential candidates)
            search_candidates = []
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Fetch more results than needed initially for sorting
                search_url = f"ytsearch{max_results * 10}:{title}" # Fetch more to increase chance of finding high-view videos
                search_result = ydl.extract_info(search_url, download=False)

                if not search_result or 'entries' not in search_result:
                    print(f"未找到视频: {title}")
                    results[title] = []
                    continue

                # Store potential candidates (IDs and basic info if available)
                for entry in search_result['entries']:
                    if entry and entry.get('id'):
                        # Store basic info available from search results if needed for pre-filtering
                        search_candidates.append({
                             'id': entry['id'],
                             'view_count': entry.get('view_count'), # Get view count if available
                             'url': f"https://www.youtube.com/watch?v={entry['id']}"
                         })

            # Sort candidates by view count (descending) - ensures we try highest views first
            search_candidates.sort(key=lambda x: x.get('view_count', 0) or 0, reverse=True)

            # Process candidates until max_results with Chinese subtitles are found
            processed_count = 0
            for candidate in search_candidates:
                # Stop if we have found enough successful results for this title
                if processed_count >= max_results:
                    print(f"已找到 {max_results} 个带中文字幕的视频，停止处理标题 '{title}' 的其余候选视频。")
                    break

                video_id = candidate['id']
                video_url = candidate['url']
                print(f"尝试处理候选视频 ({candidate.get('view_count', 'N/A')} views): {video_url}")

                # Use CLI execution to get details and VTT
                temp_dir = tempfile.mkdtemp()
                info = None
                vtt_content = None
                found_chinese_vtt = False # Flag to track if Chinese VTT was found

                try:
                    # Construct the CLI command for VTT (prioritizing Chinese subs)
                    output_template = os.path.join(temp_dir, '%(id)s').replace('\\', '/')
                    # Explicitly list Chinese first in --sub-langs for priority
                    sub_langs_pref = 'zh-Hans,zh-CN,zh,en' 
                    cmd = [
                        'yt-dlp',
                        '--write-subs',
                        '--write-auto-subs',
                        '--sub-langs', sub_langs_pref,
                        '--sub-format', 'vtt',
                        '--skip-download',
                        '--print-json',
                        '-o', f'{output_template}.%(ext)s',
                    ]
                    if cookies_path:
                        cmd.extend(['--cookies-from-browser', cookies_path])
                    cmd.append(video_url)

                    # Execute the command
                    # print(f"Executing command: {' '.join(cmd)}") # Uncomment for debugging
                    process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', check=False)

                    # Check for yt-dlp execution errors
                    if process.returncode != 0:
                        print(f"  - yt-dlp CLI error for {video_url}. Stderr: {process.stderr[:500]}...") # Show partial stderr
                        if "Sign in to confirm" in process.stderr:
                            print("  - Authentication error. Check cookies.")
                        # Continue to the next candidate
                        continue # Don't proceed further for this candidate
                    else:
                        # Try parsing JSON output from stdout
                        try:
                            info = json.loads(process.stdout)
                        except json.JSONDecodeError:
                            print(f"  - Failed to parse yt-dlp JSON output for {video_url}")
                            # Continue to the next candidate
                            continue # Don't proceed further for this candidate

                    # If info was successfully parsed, try find and read CHINESE VTT
                    if info:
                        video_info = {
                            "title": info.get('title', ''),
                            "video_id": info.get('id', ''),
                            "url": info.get('webpage_url', ''),
                            "channel": info.get('uploader', ''),
                            "channel_id": info.get('channel_id', ''),
                            "channel_url": info.get('channel_url', ''),
                            "upload_date": info.get('upload_date', ''),
                            "duration": info.get('duration', 0),
                            "view_count": info.get('view_count', 0),
                            "like_count": info.get('like_count', 0),
                            "description": info.get('description', '')
                        }

                        # ---> Specifically look for Chinese VTT files <-----
                        chinese_lang_suffixes = ['.zh-Hans.vtt', '.zh-CN.vtt', '.zh.vtt']
                        all_vtt_files = [f for f in os.listdir(temp_dir) if f.endswith('.vtt')]
                        
                        for vtt_file in all_vtt_files:
                            if any(vtt_file.endswith(lang_suffix) for lang_suffix in chinese_lang_suffixes):
                                vtt_path = os.path.join(temp_dir, vtt_file)
                                try:
                                    with open(vtt_path, 'r', encoding='utf-8') as f:
                                        vtt_content = f.read()
                                    print(f"  + Successfully read Chinese VTT subtitles from {vtt_file}")
                                    found_chinese_vtt = True
                                    break # Stop after finding the first Chinese VTT
                                except Exception as e:
                                    print(f"  - Error reading Chinese VTT file {vtt_path}: {e}")
                                    # Keep found_chinese_vtt as False, potentially try next candidate
                        
                        if not found_chinese_vtt:
                            print(f"  - No Chinese VTT subtitles found for {video_url}. Skipping.")
                            # Continue to the next candidate
                            continue # Don't proceed further for this candidate
                        # ---> End of Chinese VTT check <------------------

                        # --- Success Case --- 
                        # Only reach here if info is valid AND found_chinese_vtt is True
                        result = {
                            "video_info": video_info,
                            "vtt_content": vtt_content # vtt_content will have value here
                        }
                        title_results.append(result)
                        processed_count += 1 # Increment success counter
                        print(f"  => Successfully processed video with Chinese subtitles. ({processed_count}/{max_results} for title '{title}')")

                    else: 
                        # This case should ideally not be reached if JSON parsing failed above
                        print(f"  - No video info obtained for {video_url}. Skipping.")
                        # Continue to the next candidate
                        continue 

                except Exception as e:
                    print(f"  - Unexpected error processing candidate {video_url}: {str(e)}")
                    # Continue to the next candidate in case of unexpected errors during processing
                    continue 
                finally:
                    # Clean up temp directory for the current candidate
                    try:
                        shutil.rmtree(temp_dir)
                    except OSError as e:
                        print(f"清理临时目录时出错 {temp_dir}: {e}")
            
            # After checking all candidates for a title
            if processed_count < max_results:
                print(f"警告: 标题 '{title}' 只找到了 {processed_count} 个 (少于要求的 {max_results} 个) 带中文字幕的视频。")

        except Exception as e:
            print(f"搜索标题 '{title}' 时发生严重错误: {str(e)}")

        # Store results for the current title (even if fewer than max_results)
        results[title] = title_results

    # ---> Modify output logic to append/merge with existing file <-----
    output_filename = output_file if output_file else "analyze.json"
    existing_data = {}

    # Try to read existing data
    if os.path.exists(output_filename):
        try:
            with open(output_filename, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                if not isinstance(existing_data, dict):
                    print(f"警告: 文件 {output_filename} 存在但不是有效的JSON对象。将覆盖文件。")
                    existing_data = {}
        except json.JSONDecodeError:
            print(f"警告: 文件 {output_filename} 存在但包含无效的JSON。将覆盖文件。")
            existing_data = {}
        except Exception as e:
            print(f"读取现有文件 {output_filename} 时出错: {e}。将尝试覆盖。")
            existing_data = {}

    # Merge new results into existing data
    # For each new title, update or add its list of videos
    for title, video_list in results.items():
        if title in existing_data:
            # Simple merge: append new videos to existing list (avoid duplicates if needed later)
            # You might want more sophisticated merging logic depending on requirements
            # e.g., replacing based on video_id or updating existing entries.
            # For now, just appending:
            if isinstance(existing_data[title], list):
                 existing_data[title].extend(video_list)
            else: # Overwrite if existing value wasn't a list
                 existing_data[title] = video_list
        else:
            existing_data[title] = video_list

    # Write the merged data back to the file
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        print(f"结果已合并并保存到: {output_filename}")
    except Exception as e:
        print(f"写入文件 {output_filename} 时出错: {e}")
        # Optionally print the results to console if writing failed
        # print("未能写入文件，在控制台输出结果:")
        # print(json.dumps(existing_data, ensure_ascii=False, indent=2))

    # If no output file was specified (implicitly using default analyze.json)
    # or if an output file *was* specified, we don't need the console dump anymore
    # else:
    #     print(json.dumps(results, ensure_ascii=False, indent=2))
    # ---> End of output logic modification <-------------------------

    return existing_data # Return the merged data

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='YouTube视频搜索与VTT字幕提取工具 (最近一年, 按观看量排序, 追加到JSON)') # Updated description
    parser.add_argument('--titles', '-t', nargs='+', required=True, help='要搜索的标题列表', default="李刚被捕")
    parser.add_argument('--max-results', '-m', type=int, default=1, help='每个标题返回的最高观看量视频数')
    # ---> Update default output filename <-----
    parser.add_argument('--output', '-o', default="analyze.json", help='输出结果追加到的JSON文件 (默认为 analyze.json)')
    # ---> End of update <------------------
    parser.add_argument('--cookies', default="firefox:C:\\Users\\MOXU\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\21uzfwea.default-release",
                      help='cookies认证，格式为 "firefox:配置文件夹完整路径"')
    
    args = parser.parse_args()
    
    # 显示当前配置
    print(f"使用cookies: {args.cookies}")
    print(f"搜索标题数量: {len(args.titles)}")
    print(f"每个标题最大结果数: {args.max_results}")
    
    try:
        # 搜索视频并获取字幕
        search_and_get_subtitles(
            titles=args.titles,
            max_results=args.max_results,
            cookies_path=args.cookies,
            output_file=args.output
        )
        
        return 0
    
    except Exception as e:
        print(f"错误: {str(e)}")
        print("\n可能的解决方案:")
        print("1. 确保您已登录到YouTube (在浏览器中)")
        print("2. 确保cookies路径正确")
        print(f"   当前使用的cookies: {args.cookies}")
        print("3. 您可以手动测试以下命令确认能否正常工作:")
        print(f'   yt-dlp --write-subs --write-auto-subs --sub-langs "zh-Hans" --skip-download --cookies-from-browser "{args.cookies}" "https://www.youtube.com/watch?v=4MkkxgAw30U"')
        
        return 1

if __name__ == "__main__":
    sys.exit(main()) 