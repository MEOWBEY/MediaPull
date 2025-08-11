import sys
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import re
import os

import requests
import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv

load_dotenv()

class AppConfig:
    def __init__(self):
        self.debug_enabled = os.getenv('DEBUG', 'false').lower() == 'true'
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.allowed_origins = os.getenv('CORS_ORIGINS', '*').split(',')
        self.max_formats = int(os.getenv('MAX_FORMATS', 10))
        self.timeout_seconds = int(os.getenv('REQUEST_TIMEOUT', 30))
        self.retry_count = int(os.getenv('MAX_RETRIES', 2))

config = AppConfig()

class ExtractRequest(BaseModel):
    url: str
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, url):
        if not url or not url.strip():
            raise ValueError('URL cannot be empty')
        return url.strip()

class Format(BaseModel):
    url: str
    ext: str
    format_id: str
    height: Optional[int] = None
    width: Optional[int] = None
    filesize: Optional[int] = None
    bitrate: Optional[float] = None  # Changed to float - bitrates can be fractional
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    quality: Optional[float] = None

class VideoData(BaseModel):
    title: str
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    uploader: Optional[str] = None
    formats: List[Format]

class ExtractResponse(BaseModel):
    success: bool
    video: Optional[VideoData] = None
    method: Optional[str] = None
    error: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    service: str
    version: str

app = FastAPI(
    title="Video URL Extractor API",
    description="Extract video URLs and metadata from various video platforms",
    version="2.0.0",
    debug=config.debug_enabled
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=getattr(logging, config.log_level.upper()),
    format='%(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

class URLUtils:
    @staticmethod
    def is_direct_video(url: str) -> bool:
        video_exts = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.3gp']
        return any(ext in url.lower() for ext in video_exts)

    @staticmethod
    def is_valid_url(url: str) -> bool:
        try:
            parsed = urlparse(url)
            return bool(parsed.netloc and parsed.scheme in ['http', 'https'])
        except Exception:
            return False

class VideoExtractor:
    @staticmethod
    def get_ydl_config(use_generic: bool = False) -> Dict[str, Any]:
        """Configure yt-dlp with optimal settings for video extraction"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }
        
        base_config = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'extract_flat': False,
            'ignoreerrors': True,
            'noplaylist': True,
            'no_download': True,
            'retries': config.retry_count,
            'http_headers': headers,
            'geo_bypass': True,
            'socket_timeout': config.timeout_seconds,
            'extractor_retries': config.retry_count,
            'fragment_retries': config.retry_count,
        }
        
        if use_generic:
            base_config.update({
                'force_generic_extractor': True,
                'no_check_certificate': True,
            })
        
        return base_config

    @staticmethod
    async def extract_info(url: str) -> Dict[str, Any]:
        """Main extraction logic with fallback methods"""
        if not URLUtils.is_valid_url(url):
            raise ValueError("Invalid URL format")
        
        if URLUtils.is_direct_video(url):
            return await VideoExtractor._handle_direct_video(url)
        
        # Try primary yt-dlp extraction
        try:
            return await VideoExtractor._extract_with_ydl(url, use_generic=False)
        except Exception as primary_error:
            logger.warning(f"Primary extraction failed: {str(primary_error)}")
            # Fallback to generic extractor
            try:
                return await VideoExtractor._extract_with_ydl(url, use_generic=True)
            except Exception as fallback_error:
                logger.warning(f"Generic extraction failed: {str(fallback_error)}")
                # Last resort: web scraping
                return await VideoExtractor._scrape_page(url)

    @staticmethod
    async def _handle_direct_video(url: str) -> Dict[str, Any]:
        """Handle direct video file URLs (mp4, webm, etc.)"""
        try:
            response = requests.head(url, timeout=config.timeout_seconds, allow_redirects=True)
            response.raise_for_status()
            
            filename = url.split('/')[-1].split('?')[0] or 'video.mp4'
            ext = filename.split('.')[-1] if '.' in filename else 'mp4'
            content_length = response.headers.get('content-length')
            
            return {
                'title': filename.rsplit('.', 1)[0],
                'thumbnail': '',
                'duration': 0,
                'uploader': 'Direct File',
                'webpage_url': url,
                'formats': [{
                    'url': url,
                    'ext': ext,
                    'format_id': 'direct',
                    'height': 720,
                    'filesize': int(content_length) if content_length else None,
                    'quality': 1
                }],
                'method': 'direct_file'
            }
        except Exception as e:
            raise Exception(f"Could not process direct video URL: {str(e)}")

    @staticmethod
    async def _extract_with_ydl(url: str, use_generic: bool = False) -> Dict[str, Any]:
        """Extract using yt-dlp with either specific or generic extractor"""
        ydl_config = VideoExtractor.get_ydl_config(use_generic)
        
        try:
            with yt_dlp.YoutubeDL(ydl_config) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    raise Exception("No video information extracted")
                
                # Process and clean format data
                raw_formats = info.get('formats', [])
                clean_formats = []
                
                for fmt in raw_formats[:config.max_formats]:
                    if fmt.get('url'):
                        clean_formats.append({
                            'url': fmt.get('url'),
                            'ext': fmt.get('ext', 'mp4'),
                            'format_id': fmt.get('format_id', 'unknown'),
                            'height': int(fmt['height']) if fmt.get('height') is not None else None,
                            'width': int(fmt['width']) if fmt.get('width') is not None else None,
                            'filesize': int(fmt['filesize']) if fmt.get('filesize') is not None else None,
                            'tbr': float(fmt['tbr']) if fmt.get('tbr') is not None else None,
                            'vcodec': fmt.get('vcodec'),
                            'acodec': fmt.get('acodec'),
                            'quality': float(fmt['quality']) if fmt.get('quality') is not None else None
                        })
                
                if not clean_formats:
                    raise Exception("No valid video formats found")
                
                return {
                    'title': info.get('title', 'Unknown Video'),
                    'thumbnail': info.get('thumbnail'),
                    'duration': info.get('duration'),
                    'uploader': info.get('uploader'),
                    'webpage_url': info.get('webpage_url', url),
                    'formats': clean_formats,
                    'method': 'generic_ydl' if use_generic else 'ydl'
                }
                
        except Exception as e:
            raise Exception(f"yt-dlp failed: {str(e)}")

    @staticmethod
    async def _scrape_page(url: str) -> Dict[str, Any]:
        """Last resort: scrape webpage for video URLs using regex patterns"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=config.timeout_seconds)
            response.raise_for_status()
            
            content = response.text
            
            # Regex patterns for common video file extensions
            patterns = [
                r'https?://[^"\s<>]+\.mp4[^"\s<>]*',
                r'https?://[^"\s<>]+\.webm[^"\s<>]*',
                r'https?://[^"\s<>]+\.m3u8[^"\s<>]*',
                r'https?://[^"\s<>]+\.mkv[^"\s<>]*',
            ]
            
            found_urls = set()
            
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches[:config.max_formats]:
                    clean_url = match.strip('"\'<>')
                    if clean_url and len(clean_url) > 10:
                        found_urls.add(clean_url)
            
            urls_list = list(found_urls)[:config.max_formats]
            
            if not urls_list:
                raise Exception("No video URLs found in page")
            
            scraped_formats = []
            for i, video_url in enumerate(urls_list):
                # Determine file extension from URL
                ext = 'mp4'
                if '.webm' in video_url.lower():
                    ext = 'webm'
                elif '.m3u8' in video_url.lower():
                    ext = 'm3u8'
                elif '.mkv' in video_url.lower():
                    ext = 'mkv'
                
                scraped_formats.append({
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
                'formats': scraped_formats,
                'method': 'scraped'
            }
            
        except Exception as e:
            raise Exception(f"Scraping failed: {str(e)}")

@app.post("/extract-videos", response_model=ExtractResponse)
async def extract_videos(request: ExtractRequest):
    """Extract video URLs and metadata from given URL"""
    try:
        url = request.url
        logger.info(f"Processing URL: {url}")
        
        video_info = await VideoExtractor.extract_info(url)
        raw_formats = video_info.get('formats', [])
        
        # Sort by video quality (height) descending
        valid_formats = [fmt for fmt in raw_formats if fmt.get('url')][:config.max_formats]
        sorted_formats = sorted(valid_formats, key=lambda x: x.get('height') or 0, reverse=True)
        
        format_objects = [
            Format(
                url=fmt.get('url'),
                ext=fmt.get('ext', 'mp4'),
                format_id=fmt.get('format_id', 'unknown'),
                height=fmt.get('height'),
                width=fmt.get('width'),
                filesize=fmt.get('filesize'),
                bitrate=fmt.get('tbr'),  # tbr maps to bitrate
                video_codec=fmt.get('vcodec'),
                audio_codec=fmt.get('acodec'),
                quality=fmt.get('quality')
            )
            for fmt in sorted_formats
        ]
        
        video_data = VideoData(
            title=video_info.get('title', 'Unknown'),
            duration=video_info.get('duration'),
            thumbnail=video_info.get('thumbnail'),
            uploader=video_info.get('uploader'),
            formats=format_objects
        )
        
        response = ExtractResponse(
            success=True,
            video=video_data,
            method=video_info.get('method')
        )
        
        logger.info(f"Successfully extracted {len(sorted_formats)} formats")
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"Extraction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

@app.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        service="video-extractor",
        version="2.0.0"
    )

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="operational",
        timestamp=datetime.now().isoformat(),
        service="video-extractor-api",
        version="2.0.0"
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"success": False, "error": "API endpoint not found"}
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"}
    )

@app.exception_handler(429)
async def rate_limit_handler(request: Request, exc):
    return JSONResponse(
        status_code=429,
        content={"success": False, "error": "Rate limit exceeded"}
    )

if __name__ == '__main__':
    import uvicorn
    print("Starting FastAPI Video Extractor Server")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=config.debug_enabled)