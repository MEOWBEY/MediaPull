import sys
import logging
import asyncio
from datetime import datetime
from urllib.parse import urlparse
import re
import os

import requests
import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configuration from environment
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*').split(',')
MAX_FORMATS = int(os.getenv('MAX_FORMATS', 25))
TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 90))
MAX_RETRIES = int(os.getenv('MAX_RETRIES', 1))
PORT = int(os.getenv('PORT', 8000))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Video URL Extractor API",
    description="Extract video URLs and metadata from various video platforms",
    version="2.0.0",
    debug=DEBUG
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"]
)

class URLRequest(BaseModel):
    url: str

def is_direct_video(url: str):
    """Check if URL points to direct video file"""
    video_extensions = ['.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.3gp']
    return any(ext in url.lower() for ext in video_extensions)

def is_valid_url(url: str):
    """Validate URL format"""
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc and parsed.scheme in ['http', 'https'])
    except:
        return False

async def handle_direct_video(url: str):
    """Handle direct video file URLs"""
    try:
        response = requests.head(
            url,
            timeout=max(5, TIMEOUT // 2),
            allow_redirects=True,
            headers={'User-Agent': 'Mozilla/5.0 (compatible)'}
        )
        response.raise_for_status()
        
        filename = url.split('/')[-1].split('?')[0] or 'video.mp4'
        ext = filename.split('.')[-1] if '.' in filename else 'mp4'
        
        return {
            'id': filename,
            'title': filename.rsplit('.', 1)[0],
            'thumbnail': None,
            'duration': None,
            'upload_date': None,
            'webpage_url': url,
            'width': None,
            'height': None,
            'aspect_ratio': None,
            'formats': [{
                'url': url,
                'ext': ext,
                'tbr': 'unknown',
                'format_id': 'direct',
                'protocol': 'https',
                'resolution': 'unknown'
            }],
            'method': 'direct'
        }
    except Exception as e:
        raise Exception(f"Could not process direct video URL: {str(e)}")

async def extract_with_ytdlp(url: str, use_generic: bool = False):
    """Extract video info using yt-dlp"""
    def sync_extract():
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        config = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'extract_flat': False,
            'ignoreerrors': True,
            'noplaylist': True,
            'no_download': True,
            'retries': MAX_RETRIES,
            'http_headers': headers,
            'geo_bypass': True,
            'socket_timeout': TIMEOUT,
            'extractor_retries': MAX_RETRIES,
            'fragment_retries': 0,
            'no_color': True,
            'no_progress': True,
            'writesubtitles': False,
            'writeautomaticsub': False,
        }
        
        if use_generic:
            config.update({
                'force_generic_extractor': True,
                'no_check_certificate': True,
            })
            

        with yt_dlp.YoutubeDL(config) as ydl:
            

            info = ydl.extract_info(url, download=False)  
            if not info:
                raise Exception("No video information extracted")
            
            raw_formats = info.get('formats') or []
            clean_formats = []
            for fmt in raw_formats[:MAX_FORMATS]:
                clean_formats.append({
                    'url': fmt.get('url'),
                    'ext': fmt.get('ext', 'mp4'),
                    'tbr': fmt.get('tbr', 'unknown'),
                    'format_id': fmt.get('format_id', fmt.get('format', 'unknown')),
                    'protocol': fmt.get('protocol', 'https'),
                    'resolution': fmt.get('height', 'unknown'),
                })
            
            if not clean_formats:
                raise Exception("No valid video formats found")
                
            return {
                'id': info.get('id') or info.get('title'),
                'title': (info.get('title') or 'Unknown Video')[:200],
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'upload_date': info.get('upload_date'),
                'webpage_url': info.get('webpage_url') or info.get('original_url') or url,
                'width': info.get('width'),
                'height': info.get('height'),
                'aspect_ratio': info.get('aspect_ratio'),
                'formats': clean_formats,
                'method': 'generic_ydl' if use_generic else 'ydl'
            }
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sync_extract)

async def scrape_video_urls(url: str):
    """Fallback: scrape page for video URLs"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; VideoBot/1.0)'}
        response = requests.get(url, headers=headers, timeout=max(5, TIMEOUT // 3), stream=True)
        response.raise_for_status()
        
        content = ''
        for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
            if not chunk:
                break
            content += chunk
            if len(content) > 50000:
                break
        
        patterns = [r'https?://[^"\s<>]+\.mp4[^"\s<>]*', r'https?://[^"\s<>]+\.webm[^"\s<>]*']
        found_urls = []
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                clean_url = match.strip('"\'<>')
                if clean_url and clean_url not in found_urls:
                    found_urls.append(clean_url)
                if len(found_urls) >= MAX_FORMATS:
                    break
            if len(found_urls) >= MAX_FORMATS:
                break
        
        if not found_urls:
            raise Exception("No video URLs found in page")
        
        formats = []
        for i, video_url in enumerate(found_urls):
            formats.append({
                'url': video_url,
                'ext': 'mp4',
                'format_id': f'scraped_{i}',
                'protocol': 'https',
            })
        
        domain = urlparse(url).netloc
        return {
            'id': domain,
            'webpage_url': url,
            'formats': formats,
            'method': 'scraped'
        }
        
    except Exception as e:
        raise Exception(f"Scraping failed: {str(e)}")

async def extract_video_info(url: str):
    """Main extraction logic with fallbacks"""
    if not is_valid_url(url):
        raise ValueError("Invalid URL format")
    
    if is_direct_video(url):
        return await handle_direct_video(url)
    
    # Primary attempt
    try:
        return await asyncio.wait_for(extract_with_ytdlp(url), timeout=TIMEOUT)
    except Exception as e:
        logger.warning(f"Primary extraction failed: {str(e)}")
        
        # Generic fallback
        try:
            return await asyncio.wait_for(extract_with_ytdlp(url, use_generic=True), timeout=max(10, TIMEOUT // 2))
        except Exception as e2:
            logger.warning(f"Generic extraction failed: {str(e2)}")
            
            # Scraping fallback
            return await scrape_video_urls(url)

@app.post("/extract-videos")
async def extract_videos(request: URLRequest):
    """Extract video URLs and metadata"""
    try:
        url = request.url.strip()
        logger.info(f"Extracting: {url}")
        
        result = await extract_video_info(url)
        
        return {
            "success": True,
            "video": result,
            "method": result.get('method')
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Extraction failed")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "video-extractor",
        "version": "2.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI Video Extractor Server")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=PORT, 
        workers=1, 
        access_log=False, 
        reload=DEBUG
    )