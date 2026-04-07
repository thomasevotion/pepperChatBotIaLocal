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
from datetime import datetime
from threading import Thread
from oaichat.oairesponse import OaiResponse

import dotenv
dotenv.load_dotenv()

# Charger les variables d'environnement depuis config.env
try:
    with open('config.env', 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value
except:
    pass

if sys.version_info[0] < 3:
    raise ImportError('OpenAI Chat requires Python 3')

import openai
from openai import OpenAI

class OaiChat:
  def __init__(self,user,prompt=None):
    self.log = None
    self.reset(user,prompt)
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

  def respond(self, inputText, **kwargs):
    start = datetime.now()
    self.moderation = None
    
    self.history.append({'role':'user','content':inputText})
    
    # Mode normal non-streaming pour l'instant (pour ne pas casser le ZMQ actuel)
    # Pour le streaming, on devrait utiliser stream=True et un generateur
    stream = kwargs.get('stream', False)
    response = self.client.chat.completions.create(
      model="gpt-4o-mini",
      messages=self.history,
      max_completion_tokens=4096,
      stream=stream
    )
    
    if stream:
        return response

    r = OaiResponse(response.model_dump_json())
    self.history.append({'role':'assistant','content':r.getText()})
    print('Request delay',datetime.now()-start)
    return r

  def respond_stream(self, inputText):
      return self.respond(inputText, stream=True)


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