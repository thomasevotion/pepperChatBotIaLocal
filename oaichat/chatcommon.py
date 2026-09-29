# -*- coding: utf-8 -*-

###########################################################
# Elements communs aux backends de chat (Gemini en ligne, Ollama local) :
# catalogue emotion_tag, consignes de prompt, chargement du prompt systeme.
# Aucune dependance reseau ici : importable sans google-genai.
###########################################################
import os, codecs, json

MAX_AI_HISTORY_MESSAGES = 11

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_emotion_catalog():
    """Charge une fois le catalogue tag/description_courte depuis animations_map.json
    (racine du repo), pour l'injecter dans le prompt systeme de dialogue. Exclut le pool
    d'inactivite (idle_pool) : ces animations sont reservees a la logique 300s, jamais
    un choix du LLM."""
    map_path = os.path.join(_REPO_ROOT, 'animations_map.json')
    try:
        with codecs.open(map_path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print('WARNING: impossible de charger animations_map.json pour le catalogue emotion_tag:', e)
        return set(), u''
    idle_set = set(data.get('idle_pool', []))
    valid_tags = set()
    lines = []
    for anim in data.get('animations', []):
        tag = anim['tag']
        if tag in idle_set:
            continue
        valid_tags.add(tag)
        lines.append(u'- {} : {}'.format(tag, anim.get('description_courte', '')))
    return valid_tags, u'\n'.join(lines)


VALID_EMOTION_TAGS, _EMOTION_CATALOG_TEXT = _load_emotion_catalog()

# Injecte le catalogue UNE FOIS dans le texte du prompt systeme de classification d'emotion_tag
# (construit une seule fois par reset(), pas recalcule a chaque tour). Le format de reponse
# (JSON strict, emotion_tag limite a un tag existant ou null) est impose par un schema cote
# backend (response_schema Gemini / format Ollama), pas par ce texte : ce texte ne porte que la
# consigne semantique de choix du tag.
EMOTION_JSON_INSTRUCTION = (
    u"\n\n---\n"
    u"Tu dois choisir un emotion_tag qui couvre deux cas :\n"
    u"- Une demande explicite de l'utilisateur (ex: \"prends une photo\", \"montre tes muscles\", "
    u"\"chante joyeux anniversaire\") -> le tag d'action correspondant exactement, quelle que soit la "
    u"langue parlee.\n"
    u"- Le sens reel et le ton de l'echange (surprise, joie, tristesse, confusion, embarras...), pas "
    u"seulement des mots-cles litteraux (exemple : \"j'ai gagne un million d'euros\" -> un tag positif/"
    u"surpris, pas neutre).\n"
    u"Si rien de la liste ne correspond vraiment, choisis null : Pepper utilisera alors son geste de "
    u"parole par defaut (bras qui bougent naturellement), jamais un tag force ou hors liste.\n\n"
    u"Tags disponibles (tag : description) :\n"
    + _EMOTION_CATALOG_TEXT
)

# Rappel de la regle de langue place juste avant la generation (fin du system_instruction).
# Mesure : sans ce rappel final, la reponse ignore intermittemment la langue parlee par
# l'utilisateur (ex: "Can you play guitar?" -> reponse en francais) alors que la regle de langue
# de la persona est correcte mais noyee tout en haut du prompt - reproduit ~60-70% du temps sur
# des questions anglaises courtes en test. Repeter la regle ici, au plus pres du point de
# generation, restaure la conformite (voir tests dans la PR).
LANGUAGE_PRIORITY_INSTRUCTION = (
    u"\n\n---\n"
    u"RAPPEL PRIORITAIRE SUR LA LANGUE (au-dessus de tout ce qui precede) :\n"
    u"Ta reponse doit TOUJOURS etre redigee dans la langue que l'utilisateur vient de parler dans "
    u"son dernier message, sauf s'il a explicitement demande de changer de langue. Ne reponds "
    u"jamais en francais par defaut simplement parce que cette langue apparait ailleurs dans ces "
    u"instructions."
)


def load_config_system_prompt():
    config_path = os.path.join(_REPO_ROOT, 'PepperWebLocal', 'client.json')
    try:
        with codecs.open(config_path, encoding='utf-8') as f:
            config = json.load(f)
        prompt = config.get('llm', {}).get('systemPrompt')
        if prompt:
            print('Prompt IA charge depuis PepperWebLocal/client.json')
            return prompt
    except Exception:
        pass
    return None


def load_prompt(promptFile):
    """Retourne (system_instruction, history) : prompt de PepperWebLocal/client.json en priorite,
    sinon le fichier .prompt donne (chemin direct ou relatif au dossier oaichat/)."""
    config_prompt = load_config_system_prompt()
    if config_prompt:
        return config_prompt, [{'role': 'system', 'content': config_prompt}]

    promptFile = promptFile or 'openai.prompt'
    promptPath = (
        promptFile
        if os.path.isfile(promptFile)
        else os.path.join(os.path.dirname(os.path.abspath(__file__)), promptFile)
    )
    system_instruction = None
    if not os.path.isfile(promptPath):
        print('WARNING: Unable to locate prompt file', promptFile)
    else:
        with codecs.open(promptPath, encoding='utf-8') as f:
            system_instruction = f.read()
    history = []
    if system_instruction:
        history.append({'role': 'system', 'content': system_instruction})
    return system_instruction, history


def trim_history(history):
    """Garde le prompt systeme puis les derniers echanges user/assistant."""
    while len(history) > MAX_AI_HISTORY_MESSAGES:
        if history and isinstance(history[0], dict) and history[0].get('role') == 'system':
            del history[1:3]
        else:
            del history[0:2]
