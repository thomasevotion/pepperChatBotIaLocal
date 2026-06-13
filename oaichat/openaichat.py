# -*- coding: utf-8 -*-

###########################################################
# Gemini chat class - remplace OpenAI GPT.
# Conserve la meme interface qu'avant (OaiChat) pour que
# oaiserver.py, oaiclient.py et module_dialogue.py continuent
# de fonctionner sans modification majeure.
#
# Nouveau : supporte l'envoi d'image (camera Pepper) via image_data.
#
# Author: adapte depuis Erik Billing, University of Skovde
# Requires: pip install google-genai pillow
###########################################################
import os, sys, codecs, json
from datetime import datetime
from oaichat.oairesponse import OaiResponse
MAX_AI_HISTORY_MESSAGES = 5

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
    raise ImportError('Gemini Chat requires Python 3')

from google import genai
from google.genai import types


class OaiChat:

    def __init__(self, user, prompt=None):
        self.log = None
        self.system_instruction = None
        self.history = []
        self.client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
        self.reset(user, prompt)

    def reset(self, user, prompt=None):
        self.user = user
        self.system_instruction, self.history = self.loadPrompt(
            prompt or os.getenv('OPENAI_PROMPTFILE')
        )
        self.resetRequestLog()

    def resetRequestLog(self):
        pass

    def add_to_history(self, user_input, assistant_response):
        """Ajoute un echange complet a l'historique (utilise apres streaming). limite le nombre de messages a MAX_AI_HISTORY_MESSAGES"""
        if len(self.history) >= MAX_AI_HISTORY_MESSAGES:
            self.history = self.history[-(MAX_AI_HISTORY_MESSAGES - 2):]
        self.history.append({'role': 'user', 'content': user_input})
        self.history.append({'role': 'assistant', 'content': assistant_response})

    def _build_gemini_history(self):
        """Convertit l'historique (format OpenAI) vers le format attendu par Gemini."""
        gemini_history = []
        for msg in self.history:
            role = msg['role']
            if role == 'system':
                continue  # Gere par system_instruction dans GenerateContentConfig
            if role == 'assistant':
                role = 'model'
            content = msg.get('content', '')
            if isinstance(content, str) and content:
                gemini_history.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=content)]
                    )
                )
        return gemini_history

    def _decode_image(self, image_data):
        """
        Decompresse et convertit une image capturee par NaoQI (BGR brut en base64)
        en objet PIL.Image utilisable par Gemini.
        Retourne un PIL.Image ou None en cas d'echec.
        """
        try:
            import base64
            import io
            from PIL import Image
            raw_bytes = base64.b64decode(image_data['raw'])
            w, h = int(image_data['width']), int(image_data['height'])
            # Le mode est fourni par _do_capture ('BGR' ou 'RGB')
            mode = image_data.get('mode', 'BGR')
            if mode == 'BGR':
                img_pil = Image.frombytes('RGB', (w, h), raw_bytes, 'raw', 'BGR')
            else:
                img_pil = Image.frombytes('RGB', (w, h), raw_bytes)
            return img_pil
        except Exception as e:
            print('Warning: impossible de decoder image camera: ' + str(e))
            return None

    def respond(self, inputText, image_data=None, **kwargs):
        """
        Envoie inputText a Gemini et retourne un OaiResponse.

        image_data (optionnel) : dict avec les cles :
            'raw'    -> bytes en base64 (BGR, depuis ALVideoDevice Pepper)
            'width'  -> int
            'height' -> int
        """
        start = datetime.now()
        stream = kwargs.get('stream', False)

        # --- Construction des parties du message ---
        parts = [types.Part.from_text(text=inputText)]
        if image_data:
            img_pil = self._decode_image(image_data)
            if img_pil is not None:
                import io
                buf = io.BytesIO()
                img_pil.save(buf, format='JPEG')
                parts.append(
                    types.Part.from_bytes(
                        data=buf.getvalue(),
                        mime_type='image/jpeg'
                    )
                )
                print('Image camera incluse dans la requete Gemini ({}x{})'.format(
                    image_data['width'], image_data['height']
                ))

        # --- Configuration Gemini ---
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction or "You are a helpful assistant.",
        )

        # Modele configurable via GEMINI_MODEL dans .env, sinon gemini-2.5-flash par defaut
        model_name = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')

        # --- Construction de l'historique Gemini ---
        gemini_history = self._build_gemini_history()

        # --- Creation du chat avec historique ---
        chat = self.client.chats.create(
            model=model_name,
            config=config,
            history=gemini_history
        )

        # --- Mode streaming ---
        if stream:
            # L'historique sera mis a jour apres via add_to_history() dans oaiserver.py
            return chat.send_message_stream(parts)

        # --- Mode normal ---
        response = chat.send_message(parts)
        answer = response.text

        # Mettre a jour l'historique de la session
        self.history.append({'role': 'user', 'content': inputText})
        self.history.append({'role': 'assistant', 'content': answer})

        print('Request delay', datetime.now() - start)

        # Retourner un OaiResponse avec un dict compatible format OpenAI
        # (pour que oaiserver.py et oaiclient.py n'aient pas besoin de changer)
        fake = json.dumps({
            'choices': [{'message': {'content': answer, 'role': 'assistant'}}]
        })
        return OaiResponse(fake)

    def respond_stream(self, inputText, image_data=None):
        return self.respond(inputText, image_data=image_data, stream=True)

    def loadPrompt(self, promptFile):
        promptFile = promptFile or 'openai.prompt'
        promptPath = (
            promptFile
            if os.path.isfile(promptFile)
            else os.path.join(os.path.dirname(__file__), promptFile)
        )
        system_instruction = None
        if not os.path.isfile(promptPath):
            print('WARNING: Unable to locate prompt file', promptFile)
        else:
            with codecs.open(promptPath, encoding='utf-8') as f:
                system_instruction = f.read()
        return system_instruction, []


if __name__ == '__main__':
    chat = OaiChat('test')
    while True:
        try:
            s = input('> ')
        except KeyboardInterrupt:
            break
        if s:
            print(chat.respond(s).getText())
        else:
            break
    print('Closing Gemini Chat')
