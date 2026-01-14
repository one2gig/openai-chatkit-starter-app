"""Vercel serverless function for creating ChatKit sessions."""

import json
import os
import uuid
from http.server import BaseHTTPRequestHandler
from urllib import request as urllib_request
from urllib.error import HTTPError

class handler(BaseHTTPRequestHandler):
    """Vercel Python serverless function handler."""
    
    def do_POST(self):
        """Handle POST requests."""
        # Get API key from environment
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            self.send_error_response(500, "Missing OPENAI_API_KEY")
            return
        
        # Parse request body
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body_bytes = self.rfile.read(content_length)
            body = json.loads(body_bytes) if body_bytes else {}
        except (ValueError, json.JSONDecodeError):
            body = {}
        
        # Get workflow ID
        workflow_id = None
        if 'workflow' in body and isinstance(body['workflow'], dict):
            workflow_id = body['workflow'].get('id')
        workflow_id = workflow_id or body.get('workflowId') or os.getenv('VITE_CHATKIT_WORKFLOW_ID')
        
        if not workflow_id:
            self.send_error_response(400, "Missing workflow id")
            return
        
        # Get or create user ID from cookie
        cookie_header = self.headers.get('Cookie', '')
        user_id = self.get_cookie_value(cookie_header, 'chatkit_session_id')
        new_cookie = user_id is None
        if new_cookie:
            user_id = str(uuid.uuid4())
        
        # Call OpenAI ChatKit API
        api_base = os.getenv('CHATKIT_API_BASE') or os.getenv('VITE_CHATKIT_API_BASE') or 'https://api.openai.com'
        url = f"{api_base}/v1/chatkit/sessions"
        
        payload = json.dumps({
            "workflow": {"id": workflow_id},
            "user": user_id
        }).encode()
        
        req = urllib_request.Request(
            url,
            data=payload,
            headers={
                'Authorization': f'Bearer {api_key}',
                'OpenAI-Beta': 'chatkit_beta=v1',
                'Content-Type': 'application/json'
            },
            method='POST'
        )
        
        try:
            with urllib_request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read())
                client_secret = result.get('client_secret')
                
                if not client_secret:
                    self.send_error_response(502, "Missing client secret")
                    return
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                
                if new_cookie:
                    self.send_header('Set-Cookie', f'chatkit_session_id={user_id}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax')
                
                self.end_headers()
                self.wfile.write(json.dumps({"client_secret": client_secret}).encode())
                
        except HTTPError as e:
            try:
                error_body = json.loads(e.read())
                error_msg = error_body.get('error', str(e))
            except:
                error_msg = str(e)
            
            self.send_error_response(e.code, error_msg)
            
        except Exception as e:
            self.send_error_response(502, f"Failed to reach ChatKit API: {str(e)}")
    
    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def send_error_response(self, code, message):
        """Send JSON error response."""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())
    
    @staticmethod
    def get_cookie_value(cookie_header, name):
        """Extract cookie value by name."""
        for cookie in cookie_header.split(';'):
            cookie = cookie.strip()
            if cookie.startswith(f'{name}='):
                return cookie.split('=', 1)[1]
        return None

