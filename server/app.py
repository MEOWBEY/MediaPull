import sys
import logging
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import re
import os
from contextlib import asynccontextmanager

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
        self.max_formats = int(os.getenv('MAX_FORMATS', 5))
        self.timeout_seconds = int(os.getenv('REQUEST_TIMEOUT', 90))
        self.retry_count = int(os.getenv('MAX_RETRIES', 1))

config = AppConfig()
extraction_tasks = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app startup and shutdown - cleans up hanging tasks"""
    logger.info("Starting Video Extractor API")
    yield
    logger.info("Shutting down Video Extractor API")
    for task in extraction_tasks.copy():
        if not task.done():
            task.cancel()
    if extraction_tasks:
        await asyncio.gather(*extraction_tasks, return_exceptions=True)

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
    bitrate: Optional[float] = None
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
    debug=config.debug_enabled,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
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
        """Check if URL points directly to a video file"""
        video_exts = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.3gp']
        return any(ext in url.lower() for ext in video_exts)

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Validate URL format"""
        try:
            parsed = urlparse(url)
            return bool(parsed.netloc and parsed.scheme in ['http', 'https'])
        except Exception:
            return False

class VideoExtractor:
    # Limit concurrent extractions to prevent memory overload on low resource vps
    _semaphore = asyncio.Semaphore(2)
    
    @staticmethod
    def get_ydl_config(use_generic: bool = False) -> Dict[str, Any]:
        """Configure yt-dlp optimized for cloud deployment"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        base_config = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best[height<=720]/best',  # Limit quality for faster processing
            'extract_flat': False,
            'ignoreerrors': True,
            'noplaylist': True,
            'no_download': True,
            'retries': config.retry_count,
            'http_headers': headers,
            'geo_bypass': True,
            'socket_timeout': config.timeout_seconds,
            'extractor_retries': config.retry_count,
            'fragment_retries': 0,
            'no_color': True,
            'no_progress': True,
            'writesubtitles': False,
            'writeautomaticsub': False,
        }
        
        if use_generic:
            base_config.update({
                'force_generic_extractor': True,
                'no_check_certificate': True,
            })
        
        return base_config

    @staticmethod
    async def extract_info(url: str) -> Dict[str, Any]:
        """Main extraction with concurrency limit"""
        async with VideoExtractor._semaphore:
            return await VideoExtractor._extract_info_internal(url)
    
    @staticmethod
    async def _extract_info_internal(url: str) -> Dict[str, Any]:
        """Extract with multiple fallback methods"""
        if not URLUtils.is_valid_url(url):
            raise ValueError("Invalid URL format")
        
        if URLUtils.is_direct_video(url):
            return await VideoExtractor._handle_direct_video(url)
        
        # Try primary yt-dlp extraction
        try:
            task = asyncio.create_task(VideoExtractor._extract_with_ydl(url, use_generic=False))
            extraction_tasks.add(task)
            try:
                result = await asyncio.wait_for(task, timeout=config.timeout_seconds)
                return result
            finally:
                extraction_tasks.discard(task)
                
        except (asyncio.TimeoutError, Exception) as primary_error:
            logger.warning(f"Primary extraction failed: {str(primary_error)}")
            
            # Fallback to generic extractor
            try:
                task = asyncio.create_task(VideoExtractor._extract_with_ydl(url, use_generic=True))
                extraction_tasks.add(task)
                try:
                    result = await asyncio.wait_for(task, timeout=config.timeout_seconds // 2)
                    return result
                finally:
                    extraction_tasks.discard(task)
                    
            except (asyncio.TimeoutError, Exception) as fallback_error:
                logger.warning(f"Generic extraction failed: {str(fallback_error)}")
                # Last resort: web scraping
                return await VideoExtractor._scrape_page(url)

    @staticmethod
    async def _handle_direct_video(url: str) -> Dict[str, Any]:
        """Handle direct video file URLs (mp4, webm, etc.)"""
        try:
            response = requests.head(
                url, 
                timeout=config.timeout_seconds // 2, 
                allow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (compatible)'}
            )
            response.raise_for_status()
            
            filename = url.split('/')[-1].split('?')[0] or 'video.mp4'
            ext = filename.split('.')[-1] if '.' in filename else 'mp4'
            content_length = response.headers.get('content-length')
            
            return {
                'title': filename.rsplit('.', 1)[0],
                'thumbnail': None,
                'duration': 0,
                'uploader': 'Direct File',
                'webpage_url': url,
                'formats': [{
                    'url': url,
                    'ext': ext,
                    'format_id': 'direct',
                    'height': 480,
                    'filesize': int(content_length) if content_length and content_length.isdigit() else None,
                    'quality': 1
                }],
                'method': 'direct_file'
            }
        except Exception as e:
            raise Exception(f"Could not process direct video URL: {str(e)}")

    @staticmethod
    async def _extract_with_ydl(url: str, use_generic: bool = False) -> Dict[str, Any]:
        """Extract using yt-dlp in thread pool to avoid blocking event loop"""
        def _extract_sync():
            ydl_config = VideoExtractor.get_ydl_config(use_generic)
            
            try:
                with yt_dlp.YoutubeDL(ydl_config) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    if not info:
                        raise Exception("No video information extracted")
                    
                    raw_formats = info.get('formats', [])
                    clean_formats = []
                    
                    # Limit formats to prevent memory issues
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
                        'title': info.get('title', 'Unknown Video')[:100],  # Truncate long titles
                        'thumbnail': info.get('thumbnail'),
                        'duration': info.get('duration'),
                        'uploader': info.get('uploader', '')[:50] if info.get('uploader') else None,
                        'webpage_url': info.get('webpage_url', url),
                        'formats': clean_formats,
                        'method': 'generic_ydl' if use_generic else 'ydl'
                    }
                    
            except Exception as e:
                raise Exception(f"yt-dlp extraction failed: {str(e)}")
        
        # Run in thread pool to prevent blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _extract_sync)

    @staticmethod
    async def _scrape_page(url: str) -> Dict[str, Any]:
        """Last resort: scrape webpage for video URLs"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; VideoBot/1.0)'
            }
            
            response = requests.get(
                url, 
                headers=headers, 
                timeout=config.timeout_seconds // 3,
                stream=True
            )
            response.raise_for_status()
            
            # Only read first 50KB to avoid memory issues
            content = ''
            for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
                content += chunk
                if len(content) > 50000:
                    break
            
            # Regex patterns for common video file extensions
            patterns = [
                r'https?://[^"\s<>]+\.mp4[^"\s<>]*',
                r'https?://[^"\s<>]+\.webm[^"\s<>]*',
            ]
            
            found_urls = set()
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches[:2]:  # Limit to 2 URLs
                    clean_url = match.strip('"\'<>')
                    if clean_url and len(clean_url) > 10:
                        found_urls.add(clean_url)
            
            urls_list = list(found_urls)[:2]
            
            if not urls_list:
                raise Exception("No video URLs found in page")
            
            scraped_formats = []
            for i, video_url in enumerate(urls_list):
                ext = 'webm' if '.webm' in video_url.lower() else 'mp4'
                
                scraped_formats.append({
                    'url': video_url,
                    'ext': ext,
                    'format_id': f'scraped_{i}',
                    'height': 480,
                    'width': 854,
                    'vcodec': 'h264' if ext == 'mp4' else 'vp8',
                    'acodec': 'aac' if ext == 'mp4' else 'opus',
                    'quality': 1
                })
            
            domain = urlparse(url).netloc
            
            return {
                'title': f"Video from {domain}",
                'thumbnail': None,
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
        
        # Total timeout for entire operation (2 minutes)
        video_info = await asyncio.wait_for(
            VideoExtractor.extract_info(url),
            timeout=config.timeout_seconds * 2
        )
        
        raw_formats = video_info.get('formats', [])
        
        # Sort by quality but prefer smaller files for stability
        valid_formats = [fmt for fmt in raw_formats if fmt.get('url')][:config.max_formats]
        sorted_formats = sorted(
            valid_formats, 
            key=lambda x: (x.get('height') or 0, -(x.get('filesize') or 0)), 
            reverse=True
        )
        
        format_objects = [
            Format(
                url=fmt.get('url'),
                ext=fmt.get('ext', 'mp4'),
                format_id=fmt.get('format_id', 'unknown'),
                height=fmt.get('height'),
                width=fmt.get('width'),
                filesize=fmt.get('filesize'),
                bitrate=fmt.get('tbr'),
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
        
    except asyncio.TimeoutError:
        logger.error(f"Request timeout after {config.timeout_seconds * 2}s")
        raise HTTPException(status_code=408, detail="Request timeout - extraction took too long")
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
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
    logger.error(f"Internal server error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"}
    )

@app.exception_handler(408)
async def timeout_handler(request: Request, exc):
    return JSONResponse(
        status_code=408,
        content={"success": False, "error": "Request timeout"}
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
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=int(os.getenv('PORT', 8000)),
        workers=1,  # Single worker for low resource vps
        access_log=False,
        reload=config.debug_enabled
    )