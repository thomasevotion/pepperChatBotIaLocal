# -*- coding: utf-8 -*-

###########################################################
# The GPT-3 OpenAI chatbot class definition. Executes a local
# text based chatbot interface using the GPT-3 chatbot. 
#
# Syntax:
#    python3 openaichat.py
#
# Author: Erik Billing, University of Skovde
# Created: June 2022. 
# License: Copyright reserved to the author. 
###########################################################
import os, sys, codecs, json
import requests
from datetime import datetime
from threading import Thread
from oaichat.oairesponse import OaiResponse

import dotenv
dotenv.load_dotenv()

if sys.version_info[0] < 3:
    raise ImportError('OpenAI Chat requires Python 3')

import openai
from openai import OpenAI

class OaiChat:
  def __init__(self,user,prompt=None):
    self.log = None
    self.reset(user,prompt)
    # Defer OpenAI client creation unless needed (allows local LLM without OpenAI key)
    self.client = None
    self._local_llm_url = os.getenv('LOCAL_LLM_URL')
    self._local_llm_model = os.getenv('LOCAL_LLM_MODEL') or 'gemma2:9b'
    self._use_streaming = (os.getenv('USE_STREAMING','false').lower() == 'true')
    if not self._local_llm_url:
      # Only init OpenAI client if we're not using a local LLM
      self.client = OpenAI(api_key = os.getenv('OPENAI_KEY'))

  def reset(self,user,prompt=None):
    self.user = user
    self.history = self.loadPrompt(prompt or os.getenv('OPENAI_PROMPTFILE'))
    self.resetRequestLog()

  def resetRequestLog(self):
    # if (self.log): self.log.close()
    # logdir = os.getenv('LOGDIR')
    # if not os.path.isdir(logdir): os.mkdir(logdir)
    # log = 'requests.%s.%s.log'%(self.user,datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    # self.log = open(os.path.join(logdir,log),'a')
    # print('Logging requests to',log)
    pass

  def respond(self, inputText):
    start = datetime.now()
    self.moderation = None
    #moderator = Thread(target=self.getModeration,args=(inputText,))
    #moderator.start()
    self.history.append({'role':'user','content':inputText})
    # Route either to local LLM (if configured) or OpenAI
    if self._local_llm_url:
      text = self._respond_local_llm()
      # Synthesize an OpenAI-like response structure for compatibility
      response = {
        'choices': [
          {
            'message': {
              'content': text
            }
          }
        ]
      }
    else:
      if self.client is None:
        self.client = OpenAI(api_key = os.getenv('OPENAI_KEY'))
      response = self.client.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        #response_format={ "type": "json_object" },
        #user=self.user,
        messages=self.history,
        # temperature=0.7,
        max_tokens=150,
        # top_p=1,
        # frequency_penalty=1,
        # presence_penalty=0
      )
    #moderator.join()
    #print('Moderation:',self.moderation)
    #print(response.choices[0].message.content)
    r = OaiResponse(response.model_dump_json() if hasattr(response, 'model_dump_json') else json.dumps(response))

    self.history.append({'role':'assistant','content':r.getText()})
    print('Request delay',datetime.now()-start)
    return r

  def _build_local_prompt(self):
    # Concatenate chat history into a single prompt compatible with simple generate APIs
    parts = []
    for message in self.history:
      role = message.get('role','user')
      content = message.get('content','')
      if role == 'system':
        parts.append('System: ' + content)
      elif role == 'assistant':
        parts.append('Assistant: ' + content)
      else:
        parts.append('User: ' + content)
    return '\n'.join(parts).strip()

  def _respond_local_llm(self):
    url = self._local_llm_url.rstrip('/')
    model = self._local_llm_model
    prompt = self._build_local_prompt()
    payload = {
      'model': model,
      'prompt': prompt,
      'stream': self._use_streaming
    }
    if self._use_streaming:
      response_text = ''
      with requests.post(f"{url}/api/generate", json=payload, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
          if not line:
            continue
          try:
            data = json.loads(line.decode('utf-8'))
          except Exception:
            continue
          token = data.get('response') or ''
          if token:
            response_text += token
          if data.get('done'):
            break
      return response_text.strip()
    else:
      resp = requests.post(f"{url}/api/generate", json=payload, timeout=600)
      resp.raise_for_status()
      data = resp.json()
      return (data.get('response') or '').strip()

  def loadPrompt(self,promptFile):
    promptFile = promptFile or 'openai.prompt'
    promptPath = promptFile if os.path.isfile(promptFile) else os.path.join(os.path.dirname(__file__),promptFile)
    prompt = [] # [{"role": "system", "content": "You are a helpful robot designed to output JSON."}]
    if not os.path.isfile(promptPath):
      print('WARNING: Unable to locate OpenAI prompt file',promptFile)
    else:
      with codecs.open(promptPath,encoding='utf-8') as f:
        prompt.append({'role':'system','content':f.read()})
    return prompt
    
if __name__ == '__main__':
  chat = OaiChat()

  while True:
    try:
      s = input('> ')
    except KeyboardInterrupt:
      break
    if s:
      print(chat.history)
      print(chat.respond(s).getText())
    else:
        break
  print('Closing GPT Server')