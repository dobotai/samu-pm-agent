#!/usr/bin/env python3
"""
Web tools - fetch URLs and search the web.
"""

import sys
import json
import requests
from urllib.parse import urlparse
import re


def fetch_url(url: str, prompt: str = None) -> dict:
    """Fetch content from a URL and optionally process with a prompt."""
    try:
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme:
            url = "https://" + url
            parsed = urlparse(url)

        if parsed.scheme not in ['http', 'https']:
            return {"error": f"Invalid URL scheme: {parsed.scheme}"}

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '')

        # Handle different content types
        if 'application/json' in content_type:
            try:
                data = response.json()
                content = json.dumps(data, indent=2)[:50000]
            except:
                content = response.text[:50000]
        elif 'text/html' in content_type:
            # Basic HTML to text conversion
            html = response.text
            # Remove scripts and styles
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            # Remove tags
            text = re.sub(r'<[^>]+>', ' ', html)
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            content = text[:50000]
        else:
            content = response.text[:50000]

        result = {
            "url": response.url,
            "status_code": response.status_code,
            "content_type": content_type,
            "content": content,
            "content_length": len(content)
        }

        if len(response.text) > 50000:
            result["truncated"] = True

        return result

    except requests.exceptions.Timeout:
        return {"error": "Request timed out"}
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


def web_search(query: str, num_results: int = 5) -> dict:
    """
    Search the web using DuckDuckGo HTML (no API key needed).
    Returns search results.
    """
    try:
        # Use DuckDuckGo HTML version
        url = "https://html.duckduckgo.com/html/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        data = {'q': query}

        response = requests.post(url, headers=headers, data=data, timeout=15)
        response.raise_for_status()

        # Parse results from HTML
        results = []
        html = response.text

        # Find result links (basic parsing)
        # DuckDuckGo HTML format: <a class="result__a" href="...">title</a>
        pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>'
        matches = re.findall(pattern, html, re.IGNORECASE)

        for i, (link, title) in enumerate(matches[:num_results]):
            # DuckDuckGo uses redirect URLs, try to extract actual URL
            if 'uddg=' in link:
                actual_url = re.search(r'uddg=([^&]+)', link)
                if actual_url:
                    from urllib.parse import unquote
                    link = unquote(actual_url.group(1))

            results.append({
                "title": title.strip(),
                "url": link,
                "position": i + 1
            })

        return {
            "query": query,
            "results": results,
            "count": len(results)
        }

    except Exception as e:
        return {"error": str(e), "query": query}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Missing action parameter",
            "usage": "web_tools.py <action> <params_json>",
            "actions": ["fetch", "search"]
        }))
        sys.exit(1)

    action = sys.argv[1]

    # Parse JSON params
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            # For simple cases, treat as the main parameter
            if action == "fetch":
                params = {"url": sys.argv[2]}
            elif action == "search":
                params = {"query": " ".join(sys.argv[2:])}

    if action == "fetch":
        url = params.get("url")
        if not url:
            print(json.dumps({"error": "url is required"}))
            sys.exit(1)
        result = fetch_url(url, prompt=params.get("prompt"))

    elif action == "search":
        query = params.get("query")
        if not query:
            print(json.dumps({"error": "query is required"}))
            sys.exit(1)
        result = web_search(query, num_results=int(params.get("num_results", 5)))

    else:
        result = {"error": f"Unknown action: {action}", "actions": ["fetch", "search"]}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
