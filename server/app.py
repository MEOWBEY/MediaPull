import sys
import logging
import requests
import yt_dlp
import re
from datetime import datetime
from urllib.parse import urlparse
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configuration
class Config:
    DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')
    MAX_FORMATS = int(os.getenv('MAX_FORMATS', 10))
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 30))
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', 2))

app = Flask(__name__)
CORS(app, origins=Config.CORS_ORIGINS)

# Logging configuration
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL.upper()),
    format='%(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

@app.before_request
def before_request():
    """Set request timeout"""
    request.environ.setdefault('HTTP_X_REQUEST_START', str(datetime.now().timestamp()))

@app.after_request
def after_request(response):
    """Add headers for compatibility"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

class VideoUtils:
    """Utility functions for video processing"""
    
    @staticmethod
    def is_direct_video_url(url):
        """Check if URL points directly to a video file"""
        video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.3gp']
        return any(ext in url.lower() for ext in video_extensions)

    @staticmethod
    def validate_url(url):
        """Validate URL format and accessibility"""
        try:
            parsed = urlparse(url)
            return bool(parsed.netloc and parsed.scheme in ['http', 'https'])
        except Exception:
            return False

class VideoProcessor:
    """Main video processing class for URL extraction only"""
    
    @staticmethod
    def get_ydl_options(use_fallback=False):
        """Optimized yt-dlp options for URL extraction only"""
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        base_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'extract_flat': False,
            'ignoreerrors': True,
            'noplaylist': True,
            'no_download': True,
            'retries': Config.MAX_RETRIES,
            'http_headers': headers,
            'geo_bypass': True,
            'cachedir': False,
            'socket_timeout': Config.REQUEST_TIMEOUT,
        }
        
        if use_fallback:
            base_opts.update({
                'force_generic_extractor': True,
                'no_check_certificate': True,
            })
        
        return base_opts

    @staticmethod
    def extract_video_info(url):
        """Extract video information with URL extraction focus"""
        
        if not VideoUtils.validate_url(url):
            raise ValueError("Invalid URL format")
        
        if VideoUtils.is_direct_video_url(url):
            return VideoProcessor._handle_direct_video(url)
        
        # Try primary extraction
        try:
            return VideoProcessor._extract_with_ytdlp(url, use_fallback=False)
        except Exception:
            try:
                return VideoProcessor._extract_with_ytdlp(url, use_fallback=True)
            except Exception:
                return VideoProcessor._scrape_video_urls(url)

    @staticmethod
    def _handle_direct_video(url):
        """Handle direct video file URLs"""
        try:
            response = requests.head(url, timeout=Config.REQUEST_TIMEOUT, allow_redirects=True)
            response.raise_for_status()
            
            filename = url.split('/')[-1].split('?')[0] or 'video.mp4'
            ext = filename.split('.')[-1] if '.' in filename else 'mp4'
            content_length = response.headers.get('content-length')
            
            return {
                'title': filename.rsplit('.', 1)[0],
                'thumbnail': '',
                'duration': 0,
                'uploader': 'Direct Link',
                'webpage_url': url,
                'formats': [{
                    'url': url,
                    'ext': ext,
                    'format_id': 'direct',
                    'height': 720,
                    'filesize': int(content_length) if content_length else None,
                    'quality': 1
                }],
                'extraction_method': 'direct'
            }
        except Exception as e:
            logger.error(f"Direct video processing failed: {str(e)}")
            raise Exception(f"Could not process direct video URL: {str(e)}")

    @staticmethod
    def _extract_with_ytdlp(url, use_fallback=False):
        """Extract video information using yt-dlp"""
        ydl_opts = VideoProcessor.get_ydl_options(use_fallback)
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    raise Exception("No video information could be extracted")
                
                # Process formats
                formats = info.get('formats', [])
                valid_formats = []
                
                for fmt in formats[:Config.MAX_FORMATS]:
                    if fmt.get('url'):
                        clean_format = {
                            'url': fmt.get('url'),
                            'ext': fmt.get('ext', 'mp4'),
                            'format_id': fmt.get('format_id', 'unknown'),
                            'height': fmt.get('height', 0),
                            'width': fmt.get('width', 0),
                            'filesize': fmt.get('filesize'),
                            'tbr': fmt.get('tbr'),
                            'vcodec': fmt.get('vcodec', 'unknown'),
                            'acodec': fmt.get('acodec', 'unknown'),
                            'quality': fmt.get('quality', 0)
                        }
                        valid_formats.append(clean_format)
                
                if not valid_formats:
                    raise Exception("No valid video formats found")
                
                logger.info(f"Extracted {len(valid_formats)} valid formats")
                
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
            raise Exception(f"yt-dlp failed: {str(e)}")

    @staticmethod
    def _scrape_video_urls(url):
        """Simple page scraping for video URLs"""
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=Config.REQUEST_TIMEOUT)
            response.raise_for_status()
            
            content = response.text
            
            video_patterns = [
                r'https?://[^"\s<>]+\.mp4[^"\s<>]*',
                r'https?://[^"\s<>]+\.webm[^"\s<>]*',
                r'https?://[^"\s<>]+\.m3u8[^"\s<>]*',
            ]
            
            found_urls = set()
            
            for pattern in video_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches[:Config.MAX_FORMATS]:
                    clean_url = match.strip('"\'<>')
                    if clean_url and len(clean_url) > 10:
                        found_urls.add(clean_url)
            
            found_urls = list(found_urls)[:Config.MAX_FORMATS]
            
            if not found_urls:
                raise Exception("No video URLs found")
            
            # Create format entries
            formats = []
            for i, video_url in enumerate(found_urls):
                ext = 'mp4'
                if '.webm' in video_url.lower():
                    ext = 'webm'
                elif '.m3u8' in video_url.lower():
                    ext = 'm3u8'
                
                formats.append({
                    'url': video_url,
                    'ext': ext,
                    'format_id': f'scraped_{i}',
                    'height': 720,
                    'width': 1280,
                    'vcodec': 'h264' if ext == 'mp4' else 'unknown',
                    'acodec': 'aac' if ext == 'mp4' else 'unknown',
                    'quality': 1
                })
            
            domain = urlparse(url).netloc
            
            return {
                'title': f"Video from {domain}",
                'thumbnail': '',
                'duration': 0,
                'uploader': domain,
                'webpage_url': url,
                'formats': formats,
                'extraction_method': 'scraped'
            }
            
        except Exception as e:
            raise Exception(f"Scraping failed: {str(e)}")

# API Routes
@app.route('/extract-videos', methods=['POST'])
def extract_videos():
    """Main endpoint for video extraction"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({"success": False, "error": "URL is required"}), 400
        
        url = data['url'].strip()
        if not url:
            return jsonify({"success": False, "error": "URL cannot be empty"}), 400
        
        logger.info(f"Processing URL: {url}")
        
        # Extract video information
        video_info = VideoProcessor.extract_video_info(url)
        formats = video_info.get('formats', [])
        
        # Filter and sort formats - get best quality first
        valid_formats = [f for f in formats if f.get('url')][:Config.MAX_FORMATS]
        sorted_formats = sorted(valid_formats, key=lambda x: x.get('height', 0), reverse=True)
        
        response_data = {
            "success": True,
            "video": {
                "title": video_info.get('title'),
                "duration": video_info.get('duration'),
                "thumbnail": video_info.get('thumbnail'),
                "uploader": video_info.get('uploader'),
                "formats": sorted_formats
            },
            "extraction_method": video_info.get('extraction_method')
        }
        
        logger.info(f"Successfully extracted {len(sorted_formats)} formats")
        return jsonify(response_data)
        
    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        return jsonify({"success": False, "error": f"Invalid input: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Extraction failed: {str(e)}")
        return jsonify({"success": False, "error": f"Failed to extract video: {str(e)}"}), 500

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "service": "video-extractor",
        "version": "1.0.0"
    })

@app.route('/health', methods=['GET'])
def health():
    """Additional health endpoint"""
    return jsonify({"status": "ok"})

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({"success": False, "error": "Internal server error"}), 500

@app.errorhandler(429)
def rate_limit_error(error):
    return jsonify({"success": False, "error": "Rate limit exceeded"}), 429

if __name__ == '__main__':
    # For local development only - online server will use gunicorn
    print("Starting Video Server for local development")
    app.run(debug=Config.DEBUG)
