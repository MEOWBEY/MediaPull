import os
import sys
import logging
import requests
import yt_dlp
import re
from datetime import datetime
from urllib.parse import urlparse, quote
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =============================================================================

class Config:
    PORT = int(os.getenv('PORT', 5000))
    HOST = os.getenv('HOST', '0.0.0.0')
    DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')
    MAX_FORMATS = int(os.getenv('MAX_FORMATS', 15))

# =============================================================================

app = Flask(__name__)
CORS(app, origins=Config.CORS_ORIGINS)

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# =============================================================================

class VideoUtils:
    @staticmethod
    def is_direct_video_url(url):
        """Check if URL points directly to a video file"""
        video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v']
        return any(ext in url.lower() for ext in video_extensions)

    @staticmethod
    def get_video_type(url):
        """Detect video stream type from URL"""
        if not url:
            return 'unknown'
        url_lower = url.lower()
        if '.m3u8' in url_lower:
            return 'hls'
        elif '.mpd' in url_lower:
            return 'dash'
        elif '.ts' in url_lower:
            return 'hls_fragment'
        elif any(ext in url_lower for ext in ['.mp4', '.webm', '.mkv', '.avi']):
            return 'direct'
        return 'unknown'

    @staticmethod
    def format_filesize(bytes_size):
        """Convert bytes to human-readable format"""
        if not bytes_size or not isinstance(bytes_size, (int, float)):
            return "Unknown"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024:
                return f"{bytes_size:.1f} {unit}" if bytes_size < 10 else f"{bytes_size:.0f} {unit}"
            bytes_size /= 1024
        return f"{bytes_size:.1f} PB"

# =============================================================================

class VideoProcessor:
    @staticmethod
    def get_ydl_options(use_fallback=False):
        """Get yt-dlp options with optional fallback settings"""
        base_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'bv*+ba/best',
            'extract_flat': False,
            'ignoreerrors': True,
            'noplaylist': True,
            'playlistend': 20,
            'max_downloads': 100,
            'sleep_interval_requests': 1.0,
            'retries': 5,
            'fragment_retries': 5,
            'concurrent_fragment_downloads': 2,
            'source_address': '0.0.0.0',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'no_color': True,
            'progress_with_newline': True,
            'cachedir': False,
            'default_search': 'auto',
        }
        
        if use_fallback:
            # Enhanced options for difficult sites
            base_opts.update({
                'force_generic_extractor': True,
                'no_check_certificate': True,
                'extractor_retries': 3,
                'socket_timeout': 120,
            })
            logger.info("Using fallback yt-dlp options")
        
        return base_opts

    @staticmethod
    def extract_video_info(url):
        """Extract video information with automatic fallback including scraping"""
        logger.info(f"Processing URL: {url}")
        
        # Handle direct video URLs first
        if VideoUtils.is_direct_video_url(url):
            logger.info("Direct video URL detected")
            return VideoProcessor._handle_direct_video(url)
        
        # Try primary yt-dlp extraction
        try:
            return VideoProcessor._extract_with_ytdlp(url, use_fallback=False)
        except Exception as e:
            logger.warning(f"Primary yt-dlp extraction failed: {str(e)}")
            
            # Try fallback yt-dlp extraction
            try:
                logger.info("Attempting fallback yt-dlp extraction...")
                return VideoProcessor._extract_with_ytdlp(url, use_fallback=True)
            except Exception as fallback_error:
                logger.warning(f"Fallback yt-dlp extraction failed: {str(fallback_error)}")
                
                # Last resort: page scraping
                logger.info("Attempting page scraping as final fallback...")
                return VideoProcessor._scrape_video_urls(url)

    @staticmethod
    def _handle_direct_video(url):
        """Handle direct video file URLs"""
        try:
            response = requests.head(url, timeout=10)
            filename = url.split('/')[-1].split('?')[0] or 'video.mp4'
            
            return {
                'title': filename.rsplit('.', 1)[0],
                'thumbnail': '',
                'duration': 0,
                'uploader': 'Direct Link',
                'webpage_url': url,
                'formats': [{
                    'url': url,
                    'ext': filename.split('.')[-1] if '.' in filename else 'mp4',
                    'format_id': 'direct',
                    'vcodec': 'h264',
                    'acodec': 'aac',
                    'filesize': int(response.headers.get('content-length', 0)) or None,
                    'height': 720,
                    'width': 1280
                }],
                'extraction_method': 'direct'
            }
        except Exception as e:
            logger.error(f"Error handling direct video: {str(e)}")
            raise Exception(f"Could not process direct video URL: {str(e)}")

    @staticmethod
    def _extract_with_ytdlp(url, use_fallback=False):
        """Extract video info using yt-dlp"""
        ydl_opts = VideoProcessor.get_ydl_options(use_fallback)
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("No video information extracted")
                
                formats = info.get('formats', [])
                valid_formats = [f for f in formats if f.get('url')]
                
                if not valid_formats:
                    raise Exception("No valid video formats found")
                
                logger.info(f"yt-dlp found {len(valid_formats)} valid formats")
                return {
                    'title': info.get('title', 'Unknown Video'),
                    'thumbnail': info.get('thumbnail', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'webpage_url': info.get('webpage_url', url),
                    'formats': valid_formats,
                    'extraction_method': 'fallback_ytdlp' if use_fallback else 'primary_ytdlp'
                }
                
        except Exception as e:
            logger.error(f"yt-dlp extraction error: {str(e)}")
            raise

    @staticmethod
    def _scrape_video_urls(url):
        """Last resort: scrape page for video URLs"""
        logger.info("Attempting page scraping for video URLs")
        
        try:
            # Fetch the page content
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            response = requests.get(url, headers=headers, timeout=120)
            
            if response.status_code != 200:
                raise Exception(f"Failed to fetch page: HTTP {response.status_code}")
            
            content = response.text
            logger.info(f"Page content length: {len(content)} characters")
            
            # Enhanced video URL patterns
            video_patterns = [
                # Direct video files
                r'https?://[^"\s<>]+\.mp4[^"\s<>]*',
                r'https?://[^"\s<>]+\.webm[^"\s<>]*',
                r'https?://[^"\s<>]+\.mkv[^"\s<>]*',
                r'https?://[^"\s<>]+\.avi[^"\s<>]*',
                r'https?://[^"\s<>]+\.mov[^"\s<>]*',
                r'https?://[^"\s<>]+\.flv[^"\s<>]*',
                # Streaming formats
                r'https?://[^"\s<>]+\.m3u8[^"\s<>]*',
                r'https?://[^"\s<>]+\.mpd[^"\s<>]*',
                # Common video hosting patterns
                r'https?://[^"\s<>]*cloudfront[^"\s<>]*\.mp4[^"\s<>]*',
                r'https?://[^"\s<>]*amazonaws[^"\s<>]*\.mp4[^"\s<>]*',
                r'https?://[^"\s<>]*cdn[^"\s<>]*\.mp4[^"\s<>]*',
            ]
            
            found_urls = set()  # Use set to avoid duplicates
            
            for pattern in video_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Clean up the URL
                    clean_url = match.strip('"\'<>')
                    if clean_url and len(clean_url) > 20:  # Basic validation
                        found_urls.add(clean_url)
            
            found_urls = list(found_urls)
            logger.info(f"Scraped {len(found_urls)} potential video URLs")
            
            if not found_urls:
                raise Exception("No video URLs found in page content")
            
            # Log sample URLs for debugging
            for i, video_url in enumerate(found_urls[:3]):
                logger.info(f"Scraped URL {i+1}: {video_url[:80]}...")
            
            # Create format entries with better metadata
            formats = []
            for video_url in found_urls[:Config.MAX_FORMATS]:  # Limit number of scraped URLs
                ext = 'mp4'  # default
                height = 0
                
                # Try to determine extension and quality from URL
                url_lower = video_url.lower()
                if '.webm' in url_lower:
                    ext = 'webm'
                elif '.mkv' in url_lower:
                    ext = 'mkv'
                elif '.m3u8' in url_lower:
                    ext = 'm3u8'
                elif '.mpd' in url_lower:
                    ext = 'mpd'
                
                # Try to extract quality from URL patterns
                quality_matches = re.search(r'(\d{3,4})p?', video_url)
                if quality_matches:
                    try:
                        height = int(quality_matches.group(1))
                    except:
                        pass
                
                formats.append({
                    'url': video_url,
                    'ext': ext,
                    'format_id': f'scraped_{len(formats)}',
                    'vcodec': 'unknown',
                    'acodec': 'unknown' if ext not in ['m3u8', 'mpd'] else 'aac',
                    'height': height,
                    'width': int(height * 16/9) if height > 0 else 0,
                    'filesize': None
                })
            
            # Get domain for metadata
            try:
                domain = urlparse(url).netloc
                title = f"Video from {domain}"
            except:
                title = "Scraped Video"
            
            logger.info(f"Successfully created {len(formats)} formats from scraped URLs")
            
            return {
                'title': title,
                'thumbnail': '',
                'duration': 0,
                'uploader': domain if 'domain' in locals() else 'Unknown',
                'webpage_url': url,
                'formats': formats,
                'extraction_method': 'scraped'
            }
            
        except Exception as e:
            logger.error(f"Page scraping failed: {str(e)}")
            raise Exception(f"All extraction methods failed. Last error: {str(e)}")

# =============================================================================

@app.route('/extract-videos', methods=['POST'])
def extract_videos():
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({"success": False, "error": "URL is required in request body"}), 400
        
        url = data['url'].strip()
        if not url:
            return jsonify({"success": False, "error": "URL cannot be empty"}), 400
        
        # Extract raw video info with fallback methods
        video_info = VideoProcessor.extract_video_info(url)
        formats = video_info.get('formats', [])
        
        # Filter valid formats and limit count
        valid_formats = [f for f in formats if f.get('url')]
        
        # Sort by quality (height) descending and limit
        sorted_formats = sorted(
            valid_formats, 
            key=lambda x: (
                x.get('height', 0),
                x.get('width', 0),
                1 if x.get('ext') == 'mp4' else 0,
                x.get('tbr', 0)
            ), 
            reverse=True
        )[:Config.MAX_FORMATS]
        
        # Return minimal processed data - let frontend handle formatting
        response_data = {
            "success": True,
            "video": {
                "title": video_info.get('title'),
                "duration": video_info.get('duration'),
                "formats": sorted_formats
            }
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"success": False, "error": f"Failed to extract video: {str(e)}"}), 500

# =============================================================================

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# =============================================================================

if __name__ == '__main__':
    logger.info("Starting Enhanced Video Server v3.1.0")
    logger.info(f"Host: {Config.HOST}:{Config.PORT}")
    logger.info(f"Debug: {Config.DEBUG}")
    logger.info(f"Max Formats: {Config.MAX_FORMATS}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG, threaded=True)