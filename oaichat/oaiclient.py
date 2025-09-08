# Python 2 compatible OaiClient
import os
import json
import requests

try:
    import zmq
except Exception:
    zmq = None


class OaiClient(object):
    def __init__(self, user=None):
        self.user = user or 'User'
        self.local_url = os.getenv('LOCAL_LLM_URL')
        self.local_model = os.getenv('LOCAL_LLM_MODEL') or 'gemma2:9b'
        self.use_streaming = (os.getenv('USE_STREAMING', 'false').lower() == 'true')
        self._zmq_socket = None
        # Maintain a minimal history so the local LLM can be guided by the prompt
        self._system_prompt = self._load_system_prompt()
        self._history = []  # list of (role, content)

    def reset(self):
        self._history = []

    def _ensure_zmq(self):
        if self._zmq_socket is not None:
            return
        if zmq is None:
            raise RuntimeError('pyzmq not available and LOCAL_LLM_URL not set')
        address = os.getenv('CHATBOT_SERVER_ADDRESS') or 'tcp://127.0.0.1:5555'
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(address)
        self._zmq_socket = socket

    def respond(self, message):
        # store user turn
        self._history.append(('user', message))
        if self.local_url:
            url = self.local_url.rstrip('/') + '/api/generate'
            prompt = self._build_prompt()
            payload = {
                'model': self.local_model,
                'prompt': prompt,
                'stream': False
            }
            resp = requests.post(url, json=payload, timeout=600)
            resp.raise_for_status()
            data = resp.json()
            text = (data.get('response') or '').strip()
            self._history.append(('assistant', text))
            return text
        else:
            # fallback to ZMQ server
            self._ensure_zmq()
            req = {
                'user': self.user,
                'input': message
            }
            self._zmq_socket.send_json(req)
            res = self._zmq_socket.recv_json()
            # Expect OpenAI-like response from server
            try:
                choices = res.get('choices') or []
                if choices:
                    text = (choices[0].get('message') or {}).get('content', '').strip()
                    self._history.append(('assistant', text))
                    return text
            except Exception:
                pass
            # Fallback: try direct text field
            text = (res.get('text') or '').strip()
            self._history.append(('assistant', text))
            return text

    def stream_respond(self, message):
        # store user turn
        self._history.append(('user', message))
        if not self.local_url:
            # No streaming over ZMQ; yield full response at once
            yield self.respond(message)
            return
        url = self.local_url.rstrip('/') + '/api/generate'
        prompt = self._build_prompt()
        payload = {
            'model': self.local_model,
            'prompt': prompt,
            'stream': True
        }
        try:
            resp = requests.post(url, json=payload, stream=True, timeout=600)
            acc = []
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode('utf-8'))
                except Exception:
                    continue
                token = data.get('response') or ''
                if token:
                    acc.append(token)
                    yield token
                if data.get('done'):
                    break
            # store assistant turn
            try:
                self._history.append(('assistant', ''.join(acc)))
            except Exception:
                pass
        except Exception as e:
            # Fallback: non-streaming
            try:
                yield self.respond(message)
            except Exception:
                yield ''

    def _load_system_prompt(self):
        # Allow selecting a prompt file via env, default to 'nao.prompt' if present
        prompt_file = os.getenv('DIALOGUE_START_PROMPTFILE') or os.getenv('OPENAI_PROMPTFILE')
        if not prompt_file:
            # try defaults
            for name in ['nao.prompt', 'pepper.prompt', 'oaichat/openai.prompt']:
                if os.path.isfile(name):
                    prompt_file = name
                    break
        if prompt_file and os.path.isfile(prompt_file):
            try:
                with open(prompt_file, 'rb') as f:
                    content = f.read()
                try:
                    return content.decode('utf-8')
                except Exception:
                    try:
                        return content.decode('cp1252')
                    except Exception:
                        return ''
            except Exception:
                return ''
        return ''

    def _build_prompt(self):
        parts = []
        if self._system_prompt:
            parts.append('System: ' + self._system_prompt.strip())
        for role, content in self._history:
            if role == 'assistant':
                parts.append('Assistant: ' + content)
            else:
                parts.append('User: ' + content)
        return '\n'.join(parts).strip()
