import os
import sys
import logging
import requests
import yt_dlp
import re
from datetime import datetime
from urllib.parse import urlparse, quote
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

class Config:
    PORT = int(os.getenv('PORT', 5000))
    HOST = os.getenv('HOST', '0.0.0.0')
    DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')
    MAX_FORMATS = int(os.getenv('MAX_FORMATS', 15))

# =============================================================================
# Application Setup
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
# Utility Functions
# =============================================================================

class VideoUtils:
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
    def is_direct_video_url(url):
        """Check if URL points directly to a video file"""
        video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v']
        return any(ext in url.lower() for ext in video_extensions)

    @staticmethod
    def get_best_format(formats):
        """Get the best quality format from available formats"""
        if not formats:
            return None
        
        # Prefer combined video+audio formats
        combined = [f for f in formats if f.get('vcodec', 'none') != 'none' and f.get('acodec', 'none') != 'none']
        if combined:
            return max(combined, key=lambda x: (x.get('height', 0), 1 if x.get('ext') == 'mp4' else 0))
        
        # Fallback to video-only formats
        video_only = [f for f in formats if f.get('vcodec', 'none') != 'none']
        if video_only:
            return max(video_only, key=lambda x: x.get('height', 0))
        
        # Last resort: audio-only or any format
        return formats[0]

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

    @staticmethod
    def format_duration(seconds):
        """Convert seconds to HH:MM:SS format"""
        if not seconds or not isinstance(seconds, (int, float)):
            return "Unknown"
        
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    @staticmethod
    def get_quality_label(format_info):
        """Generate quality label for format"""
        if not format_info:
            return "Unknown"
            
        height = format_info.get('height', 0)
        ext = format_info.get('ext', 'unknown').upper()
        has_video = format_info.get('vcodec', 'none') != 'none'
        has_audio = format_info.get('acodec', 'none') != 'none'
        
        if '.m3u8' in format_info.get('url', '').lower():
            return f"{height}p HLS" if height > 0 else "HLS Stream"
        elif '.mpd' in format_info.get('url', '').lower():
            return f"{height}p DASH" if height > 0 else "DASH Stream"
        elif has_video and has_audio:
            return f"{height}p ({ext})" if height > 0 else f"Video ({ext})"
        elif has_video:
            return f"{height}p Video Only ({ext})" if height > 0 else f"Video Only ({ext})"
        elif has_audio:
            return f"Audio Only ({ext})"
        
        return f"Unknown ({ext})"

# =============================================================================
# Video Processing
# =============================================================================

class VideoProcessor:
    @staticmethod
    def get_ydl_options(use_fallback=False):
        """Get yt-dlp options with optional fallback settings"""
        base_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'all',  # Get all available formats
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        }
        
        if use_fallback:
            # Enhanced options for difficult sites
            base_opts.update({
                'ignoreerrors': True,
                'no_check_certificate': True,
                'prefer_insecure': True,
                'geo_bypass': True,
                'extractor_retries': 5,
                'socket_timeout': 60,
                'retries': 3
            })
            logger.info("Using fallback extraction options")
        
        return base_opts

    @staticmethod
    def extract_video_info(url):
        """Extract video information using yt-dlp with automatic fallback"""
        logger.info(f"Processing URL: {url}")
        
        # Handle direct video URLs
        if VideoUtils.is_direct_video_url(url):
            logger.info("Direct video URL detected")
            return VideoProcessor._handle_direct_video(url)
        
        # Try primary extraction
        try:
            return VideoProcessor._extract_with_ytdlp(url, use_fallback=False)
        except Exception as e:
            logger.warning(f"Primary extraction failed: {str(e)}")
            logger.info("Attempting fallback extraction...")
            
            try:
                return VideoProcessor._extract_with_ytdlp(url, use_fallback=True)
            except Exception as fallback_error:
                logger.warning(f"Fallback extraction failed: {str(fallback_error)}")
                logger.info("Attempting page scraping...")
                return VideoProcessor._scrape_video_urls(url)

    @staticmethod
    def _handle_direct_video(url):
        """Handle direct video file URLs"""
        try:
            response = requests.head(url, timeout=40)
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
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise Exception("No video information extracted")
            
            formats = info.get('formats', [])
            
            # Handle single URL case
            if not formats and info.get('url'):
                formats = [{
                    'url': info['url'],
                    'ext': info.get('ext', 'mp4'),
                    'format_id': 'single',
                    'vcodec': 'unknown',
                    'acodec': 'unknown'
                }]
            
            # Filter out invalid formats
            valid_formats = [f for f in formats if f.get('url')]
            
            if not valid_formats:
                raise Exception("No valid video formats found")
            
            logger.info(f"Found {len(valid_formats)} valid formats")
            
            # Log sample URLs for debugging
            for i, fmt in enumerate(valid_formats[:3]):
                logger.info(f"Format {i+1}: {fmt.get('url', '')[:100]}... ({fmt.get('ext')}, {fmt.get('height', 0)}p)")
            
            best_format = VideoUtils.get_best_format(valid_formats)
            
            return {
                'title': info.get('title', 'Unknown Video'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'webpage_url': info.get('webpage_url', url),
                'formats': valid_formats,
                'best_format': best_format,
                'extraction_method': 'fallback' if use_fallback else 'primary'
            }

    @staticmethod
    def _scrape_video_urls(url):
        """Last resort: scrape page for video URLs"""
        logger.info("Attempting page scraping for video URLs")
        
        try:
            response = requests.get(url, timeout=120, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if response.status_code != 200:
                raise Exception(f"Failed to fetch page: {response.status_code}")
            
            # Look for video URLs in page content
            video_patterns = [
                r'https?://[^"\s]+\.mp4[^"\s]*',
                r'https?://[^"\s]+\.webm[^"\s]*',
                r'https?://[^"\s]+\.m3u8[^"\s]*',
                r'https?://[^"\s]+\.mpd[^"\s]*'
            ]
            
            found_urls = []
            for pattern in video_patterns:
                matches = re.findall(pattern, response.text, re.IGNORECASE)
                found_urls.extend([url.strip('"\'') for url in matches])
            
            # Remove duplicates
            found_urls = list(set(found_urls))
            
            logger.info(f"Scraped {len(found_urls)} potential video URLs")
            
            if not found_urls:
                raise Exception("No video URLs found in page content")
            
            # Log found URLs
            for i, video_url in enumerate(found_urls[:3]):
                logger.info(f"Scraped URL {i+1}: {video_url[:100]}...")
            
            # Create format entries
            formats = []
            for video_url in found_urls:
                formats.append({
                    'url': video_url,
                    'ext': 'mp4',
                    'format_id': 'scraped',
                    'vcodec': 'unknown',
                    'acodec': 'unknown',
                    'height': 0
                })
            
            domain = urlparse(url).netloc
            
            return {
                'title': f"Video from {domain}",
                'thumbnail': '',
                'duration': 0,
                'uploader': domain,
                'webpage_url': url,
                'formats': formats,
                'best_format': formats[0] if formats else None,
                'extraction_method': 'scraped'
            }
            
        except Exception as e:
            logger.error(f"Page scraping failed: {str(e)}")
            raise Exception(f"All extraction methods failed: {str(e)}")

    @staticmethod
    def create_streaming_headers(referer=None, user_agent=None):
        """Create headers for video streaming"""
        headers = {
            'User-Agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive'
        }
        
        if referer:
            headers['Referer'] = referer
            try:
                origin = urlparse(referer).netloc
                if origin:
                    headers['Origin'] = f"https://{origin}"
            except:
                pass
        
        return headers

    @staticmethod
    def stream_video_content(video_url, referer=None, user_agent=None, range_header=None):
        """Stream video content with proper headers"""
        headers = VideoProcessor.create_streaming_headers(referer, user_agent)
        
        if range_header:
            headers['Range'] = range_header
        
        try:
            response = requests.get(
                video_url,
                headers=headers,
                stream=True,
                allow_redirects=True,
                timeout=60
            )
            
            if response.status_code not in [200, 206]:
                return None, None, response.status_code
            
            response_headers = {
                'Content-Type': response.headers.get('content-type', 'video/mp4'),
                'Accept-Ranges': response.headers.get('accept-ranges', 'bytes'),
                'Cache-Control': 'public, max-age=3600',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
                'Access-Control-Allow-Headers': 'Range, Content-Type'
            }
            
            # Add content length and range if available
            if response.headers.get('content-length'):
                response_headers['Content-Length'] = response.headers['content-length']
            if response.headers.get('content-range'):
                response_headers['Content-Range'] = response.headers['content-range']
            
            return response, response_headers, response.status_code
            
        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            return None, None, 500

# =============================================================================
# API Routes
# =============================================================================

@app.route('/', methods=['GET'])
def home():
    """Service information endpoint"""
    return jsonify({
        "service": "Enhanced Video Extraction & Streaming Server",
        "version": "3.0.0",
        "status": "running",
        "features": [
            "Multi-format video extraction",
            "Direct video streaming",
            "Automatic fallback extraction",
            "Page scraping support",
            "HLS/DASH streaming support"
        ],
        "endpoints": {
            "health": "/health",
            "extract_videos": "/extract-videos (POST)",
            "stream_video": "/stream-video (GET)"
        },
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test yt-dlp availability
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            pass
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "yt_dlp_available": True,
            "python_version": sys.version.split()[0]
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 503

@app.route('/extract-videos', methods=['POST'])
def extract_videos():
    """Extract video information and formats"""
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({
                "success": False,
                "error": "URL is required in request body"
            }), 400
        
        url = data['url'].strip()
        if not url:
            return jsonify({
                "success": False,
                "error": "URL cannot be empty"
            }), 400
        
        # Extract video information
        try:
            video_info = VideoProcessor.extract_video_info(url)
        except Exception as e:
            logger.error(f"Extraction failed: {str(e)}")
            return jsonify({
                "success": False,
                "error": f"Could not extract video: {str(e)}"
            }), 400
        
        # Process formats for response
        videos = []
        formats = video_info.get('formats', [])
        best_format = video_info.get('best_format')
        
        # Add best quality option first
        if best_format:
            videos.append({
                'title': video_info['title'],
                'thumbnail': video_info['thumbnail'],
                'duration': VideoUtils.format_duration(video_info['duration']),
                'uploader': video_info['uploader'],
                'filename': f"{video_info['title']}.{best_format.get('ext', 'mp4')}",
                'downloadUrl': best_format['url'],
                'streamUrl': f"/stream-video?url={quote(best_format['url'], safe='')}&referer={quote(video_info['webpage_url'], safe='')}",
                'quality': VideoUtils.get_quality_label(best_format),
                'format': best_format.get('ext', 'mp4'),
                'filesize': VideoUtils.format_filesize(best_format.get('filesize')),
                'hasVideo': best_format.get('vcodec', 'none') != 'none',
                'hasAudio': best_format.get('acodec', 'none') != 'none',
                'resolution': f"{best_format.get('width', 0)}x{best_format.get('height', 0)}",
                'videoType': VideoUtils.get_video_type(best_format['url']),
                'isDirectStream': True
            })
        
        # Add other formats (limited by MAX_FORMATS)
        processed_count = 1  # Already added best format
        for fmt in formats:
            if processed_count >= Config.MAX_FORMATS or not fmt.get('url'):
                break
            
            # Skip if it's the same as best format
            if best_format and fmt.get('url') == best_format.get('url'):
                continue
            
            has_video = fmt.get('vcodec', 'none') != 'none'
            has_audio = fmt.get('acodec', 'none') != 'none'
            
            if not has_video and not has_audio:
                continue
            
            videos.append({
                'title': video_info['title'],
                'thumbnail': video_info['thumbnail'],
                'duration': VideoUtils.format_duration(video_info['duration']),
                'uploader': video_info['uploader'],
                'filename': f"{video_info['title']}.{fmt.get('ext', 'mp4')}",
                'downloadUrl': fmt['url'],
                'streamUrl': f"/stream-video?url={quote(fmt['url'], safe='')}&referer={quote(video_info['webpage_url'], safe='')}",
                'quality': VideoUtils.get_quality_label(fmt),
                'format': fmt.get('ext', 'unknown'),
                'filesize': VideoUtils.format_filesize(fmt.get('filesize')),
                'hasVideo': has_video,
                'hasAudio': has_audio,
                'resolution': f"{fmt.get('width', 0)}x{fmt.get('height', 0)}" if has_video else 'Audio Only',
                'videoType': VideoUtils.get_video_type(fmt['url']),
                'isDirectStream': False
            })
            processed_count += 1
        
        extraction_method = video_info.get('extraction_method', 'unknown')
        logger.info(f"Successfully extracted {len(videos)} formats using {extraction_method} method")
        
        return jsonify({
            "success": True,
            "videos": videos,
            "metadata": {
                "title": video_info['title'],
                "thumbnail": video_info['thumbnail'],
                "duration": VideoUtils.format_duration(video_info['duration']),
                "uploader": video_info['uploader'],
                "webpage_url": video_info['webpage_url'],
                "total_formats": len(videos),
                "extraction_method": extraction_method
            }
        })
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal server error occurred"
        }), 500

@app.route('/stream-video', methods=['GET'])
def stream_video():
    """Stream video content"""
    video_url = request.args.get('url')
    referer = request.args.get('referer', '')
    user_agent = request.args.get('userAgent')
    
    if not video_url:
        return jsonify({"error": "Video URL is required"}), 400
    
    range_header = request.headers.get('Range')
    logger.info(f"Streaming: {video_url[:100]}...")
    
    try:
        response, headers, status_code = VideoProcessor.stream_video_content(
            video_url, referer, user_agent, range_header
        )
        
        if not response:
            return jsonify({"error": "Failed to stream video"}), status_code
        
        def generate():
            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            except Exception as e:
                logger.error(f"Streaming error: {str(e)}")
            finally:
                response.close()
        
        return Response(
            stream_with_context(generate()),
            status=status_code,
            headers=headers
        )
        
    except Exception as e:
        logger.error(f"Stream error: {str(e)}")
        return jsonify({"error": "Streaming failed"}), 500

# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {str(error)}")
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500

# =============================================================================
# Application Entry Point
# =============================================================================

if __name__ == '__main__':
    logger.info("Starting Enhanced Video Server v3.0.0")
    logger.info(f"Host: {Config.HOST}:{Config.PORT}")
    logger.info(f"Debug: {Config.DEBUG}")
    logger.info(f"Max Formats: {Config.MAX_FORMATS}")
    
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
        threaded=True
    )